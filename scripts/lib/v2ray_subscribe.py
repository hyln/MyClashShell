"""Download v2ray/Xray subscription URLs.

合并后的完整客户端 JSON 默认写入 ``cache/<订阅名>.json``；可选再写入 ``mcs/configs/v2ray.json``。
``update_proxy_config`` 中阶段 1 只写 cache，阶段 2 再把默认项的 cache 文件复制入 ``mcs``。

若 ``user_config.yaml`` 中含 ``port`` / ``socks-port`` / ``allow-lan``（或 ``allow_lan``）任一项，
则据此生成 v2ray 入站（与 Clash 段语义对齐：``socks-port`` 优先为 SOCKS；``port`` 为 HTTP；
仅 ``port`` 时单 SOCKS 监听该端口）。与 ``socks-in`` / ``http-in`` 同 tag 的已有入站会被覆盖，其它自定义入站保留。
``update_proxy_config`` 在阶段 1 末会对已有 ``cache/<订阅>.json`` 再刷新入站，故只改 ``socks-port`` 不重下订阅也会写入 cache。

多代理 outbound 时默认路由为 **随机 balancer**；若在 ``user_config.yaml`` 设置 ``v2ray_outbound_tag``
为某一节点 tag，则全部流量固定走该 outbound（与 ``myclash v2ray ui`` 里选用节点等价）。

``mcs/configs`` 或 ``cache`` 下同时存在 ``geoip.dat`` 与 ``geosite.dat`` 时，生成路由会为 **私有网段、国内域名与国内 IP**
走 ``direct``，其余再走代理（``v2ray_geo_split: false`` 可关闭）。

Supports:
- JSON body with ``outbounds`` (object or full config) or a JSON array of outbounds
- Text / base64 subscription: one share link per line (``vmess://``, ``vless://``,
  ``trojan://``, ``ss://``)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import subprocess
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any

import yaml

from scripts.lib.paths import mcs_configs_dir, subscribe_cache_dir, v2ray_geo_asset_dir


def _load_v2ray_existing_for_merge(
    myclash_root: Path, profile_name: str, *, include_mcs: bool = True
) -> dict[str, Any] | None:
    """Pick log/inbounds template: optionally ``mcs/…/v2ray.json``, then ``cache/<profile>.json``, then template.

    非当前默认的 v2ray 订阅只更新 ``cache/<profile>.json`` 时应设 ``include_mcs=False``，避免误用
    ``mcs`` 里其它订阅留下的 inbounds。
    """
    candidates: list[Path] = []
    if include_mcs:
        candidates.append(mcs_configs_dir(myclash_root) / "v2ray.json")
    candidates.append(subscribe_cache_dir(myclash_root) / f"{profile_name}.json")
    candidates.append(myclash_root / "install/templates/v2ray-default.json")
    for p in candidates:
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data
    return None


def _b64pad(s: str) -> str:
    pad = 4 - len(s) % 4
    return s + ("=" * pad if pad != 4 else "")


def _safe_b64decode(s: str) -> bytes:
    t = s.strip().replace("-", "+").replace("_", "/")
    return base64.b64decode(_b64pad(t), validate=False)


def _curl_download(url: str, dest: Path, timeout_sec: int = 40) -> tuple[bool, str]:
    """Returns ``(success, stderr_or_diagnostic)`` for logging on failure."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = (
        "unset http_proxy https_proxy https_proxy http_proxy ALL_PROXY all_proxy; "
        f'curl -fsSL --max-time {timeout_sec} -H "User-Agent: v2rayN/6.0" '
        f'-o "{dest}" "{url}"'
    )
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    err = (r.stderr or "").strip()
    ok = r.returncode == 0 and dest.is_file() and dest.stat().st_size > 0
    if ok:
        return True, ""
    extra = err or (r.stdout or "").strip() or f"exit {r.returncode}"
    return False, extra


def _decode_subscription_text(raw_bytes: bytes) -> str:
    text = raw_bytes.decode("utf-8", errors="replace").strip()
    if not text:
        return ""
    # Whole body is base64 (typical provider)
    if "://" not in text[:120] and not text.startswith("{"):
        try:
            dec = _safe_b64decode(text).decode("utf-8", errors="replace").strip()
            if "://" in dec or dec.startswith("{"):
                return dec
        except Exception:
            pass
    return text


def _stream_from_vmess_fields(
    net: str,
    tls_s: str,
    sni: str,
    host: str,
    path: str,
    tcp_type: str,
) -> dict[str, Any]:
    net = (net or "tcp").lower()
    tls_on = str(tls_s or "").lower() in ("tls", "1", "true")
    sec = "tls" if tls_on else "none"
    stream: dict[str, Any] = {"network": net, "security": sec}
    if tls_on:
        ts: dict[str, Any] = {}
        server = (sni or host or "").strip().split(",")[0]
        if server:
            ts["serverName"] = server
            ts["allowInsecure"] = True
        if ts:
            stream["tlsSettings"] = ts
    if net == "ws":
        h = (host or "").strip().split(",")[0]
        stream["wsSettings"] = {
            "path": path or "/",
        }
        if h:
            stream["wsSettings"]["headers"] = {"Host": h}
    elif net == "grpc":
        stream["grpcSettings"] = {"serviceName": (path or "").strip("/") or ""}
    elif net == "h2":
        hosts = [x.strip() for x in (host or "").split(",") if x.strip()]
        stream["httpSettings"] = {"path": path or "/", "host": hosts}
    elif net == "tcp":
        t = (tcp_type or "none").lower()
        if t == "http":
            p = path or "/"
            hs = [x.strip() for x in (host or "").split(",") if x.strip()] or [""]
            stream["tcpSettings"] = {
                "header": {
                    "type": "http",
                    "request": {
                        "version": "1.1",
                        "method": "GET",
                        "path": [p],
                        "headers": {"Host": hs},
                    }
                }
            }
    return stream


def _parse_vmess(uri: str, idx: int) -> dict[str, Any] | None:
    if not uri.startswith("vmess://"):
        return None
    b64 = uri[len("vmess://") :].strip()
    try:
        raw = _safe_b64decode(b64).decode("utf-8", errors="strict")
        o = json.loads(raw)
    except Exception:
        return None
    if not isinstance(o, dict):
        return None
    add = str(o.get("add") or "").strip()
    if not add:
        return None
    try:
        port = int(str(o.get("port") or "443"))
    except ValueError:
        port = 443
    uid = str(o.get("id") or "").strip()
    if not uid:
        return None
    try:
        aid = int(str(o.get("aid") or "0"))
    except ValueError:
        aid = 0
    net = str(o.get("net") or "tcp")
    ps = str(o.get("ps") or f"vmess-{idx}")
    tag = f"sub-{idx}-{re.sub(r'[^a-zA-Z0-9_-]+', '-', ps)[:48]}"
    stream = _stream_from_vmess_fields(
        net,
        str(o.get("tls") or ""),
        str(o.get("sni") or ""),
        str(o.get("host") or ""),
        str(o.get("path") or ""),
        str(o.get("type") or "none"),
    )
    scy = str(o.get("scy") or "auto")
    return {
        "protocol": "vmess",
        "settings": {
            "vnext": [
                {
                    "address": add,
                    "port": port,
                    "users": [{"id": uid, "alterId": aid, "security": scy}],
                }
            ]
        },
        "streamSettings": stream,
        "tag": tag,
    }


def _query_dict(qs: str) -> dict[str, str]:
    return {k: v[0] for k, v in urllib.parse.parse_qs(qs, keep_blank_values=True).items()}


def _parse_vless(uri: str, idx: int) -> dict[str, Any] | None:
    if not uri.lower().startswith("vless://"):
        return None
    rest = uri[8:]
    hash_tag = ""
    if "#" in rest:
        rest, h = rest.split("#", 1)
        hash_tag = urllib.parse.unquote(h)
    qsd = ""
    if "?" in rest:
        rest, qsd = rest.split("?", 1)
    if "@" not in rest:
        return None
    uid, hp = rest.split("@", 1)
    uid = urllib.parse.unquote(uid.strip())
    if ":" not in hp:
        return None
    host, port_s = hp.rsplit(":", 1)
    host = host.strip()
    try:
        port = int(port_s.strip())
    except ValueError:
        return None
    if not uid or not host:
        return None
    q = _query_dict(qsd)
    name = hash_tag or q.get("remarks") or f"vless-{idx}"
    tag = f"sub-{idx}-{re.sub(r'[^a-zA-Z0-9_-]+', '-', name)[:48]}"
    sec = (q.get("security") or "none").lower()
    net = (q.get("type") or "tcp").lower()
    stream: dict[str, Any] = {"network": net, "security": sec}
    if sec == "tls":
        ts: dict[str, Any] = {"allowInsecure": True}
        if q.get("sni"):
            ts["serverName"] = q["sni"]
        if q.get("fp"):
            ts["fingerprint"] = q["fp"]
        stream["tlsSettings"] = ts
    elif sec == "reality":
        ts = {"allowInsecure": True, "serverName": q.get("sni") or "", "publicKey": q.get("pbk") or ""}
        if q.get("sid"):
            ts["shortId"] = q["sid"]
        if q.get("fp"):
            ts["fingerprint"] = q["fp"]
        stream["realitySettings"] = {k: v for k, v in ts.items() if v}
    if net == "ws":
        stream["wsSettings"] = {"path": q.get("path") or "/"}
        if q.get("host"):
            stream["wsSettings"]["headers"] = {"Host": q["host"]}
    elif net == "grpc":
        stream["grpcSettings"] = {"serviceName": (q.get("serviceName") or q.get("path") or "").strip("/")}
    elif net == "tcp" and (q.get("headerType") or "").lower() == "http":
        stream["tcpSettings"] = {
            "header": {
                "type": "http",
                "request": {
                    "version": "1.1",
                    "method": "GET",
                    "path": [q.get("path") or "/"],
                    "headers": {"Host": [q.get("host") or ""]},
                }
            }
        }
    user: dict[str, Any] = {"id": uid, "encryption": q.get("encryption") or "none"}
    if q.get("flow"):
        user["flow"] = q["flow"]
    return {
        "protocol": "vless",
        "settings": {"vnext": [{"address": host, "port": port, "users": [user]}]},
        "streamSettings": stream,
        "tag": tag,
    }


def _parse_trojan(uri: str, idx: int) -> dict[str, Any] | None:
    if not uri.lower().startswith("trojan://"):
        return None
    rest = uri[9:]
    if "#" in rest:
        rest = rest.split("#", 1)[0]
    qsd = ""
    if "?" in rest:
        rest, qsd = rest.split("?", 1)
    if "@" not in rest:
        return None
    password, hp = rest.rsplit("@", 1)
    password = urllib.parse.unquote(password)
    if ":" not in hp:
        return None
    host, port_s = hp.rsplit(":", 1)
    try:
        port = int(port_s.strip())
    except ValueError:
        return None
    q = _query_dict(qsd)
    tag = f"sub-{idx}-trojan"
    stream: dict[str, Any] = {"network": "tcp", "security": "tls"}
    ts: dict[str, Any] = {"allowInsecure": True}
    if q.get("sni") or q.get("peer"):
        ts["serverName"] = q.get("sni") or q.get("peer") or ""
    stream["tlsSettings"] = ts
    return {
        "protocol": "trojan",
        "settings": {"servers": [{"address": host.strip(), "port": port, "password": password}]},
        "streamSettings": stream,
        "tag": tag,
    }


def _parse_ss(uri: str, idx: int) -> dict[str, Any] | None:
    if not uri.lower().startswith("ss://"):
        return None
    body = uri[5:]
    if body.startswith("//"):
        body = body[2:]
    name = ""
    if "#" in body:
        body, frag = body.split("#", 1)
        name = urllib.parse.unquote(frag)
    q = ""
    if "?" in body:
        body, q = body.split("?", 1)
    if "@" in body:
        userinfo, hostport = body.rsplit("@", 1)
        userinfo = urllib.parse.unquote(userinfo)
        method, _, password = userinfo.partition(":")
        if not password and method:
            try:
                decoded = _safe_b64decode(method).decode("utf-8", errors="strict")
                method, _, password = decoded.partition(":")
            except Exception:
                return None
        if ":" not in hostport:
            return None
        host, port_s = hostport.rsplit(":", 1)
        try:
            port = int(port_s.strip())
        except ValueError:
            return None
    else:
        try:
            decoded = _safe_b64decode(body).decode("utf-8", errors="strict")
        except Exception:
            return None
        if "@" not in decoded:
            return None
        userinfo, hostport = decoded.split("@", 1)
        method, _, password = userinfo.partition(":")
        if ":" not in hostport:
            return None
        host, port_s = hostport.rsplit(":", 1)
        try:
            port = int(port_s.strip())
        except ValueError:
            return None
    ps = name or f"ss-{idx}"
    tag = f"sub-{idx}-{re.sub(r'[^a-zA-Z0-9_-]+', '-', ps)[:48]}"
    return {
        "protocol": "shadowsocks",
        "settings": {
            "servers": [
                {
                    "address": host.strip(),
                    "port": port,
                    "method": method.strip(),
                    "password": password,
                }
            ]
        },
        "streamSettings": {"network": "tcp"},
        "tag": tag,
    }


def _line_to_outbound(line: str, idx: int) -> dict[str, Any] | None:
    u = line.strip()
    if not u or u.startswith("#"):
        return None
    for fn in (_parse_vmess, _parse_vless, _parse_trojan, _parse_ss):
        o = fn(u, idx)
        if o is not None:
            return o
    return None


def _parse_json_outbounds(body: str) -> list[dict[str, Any]] | None:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict) and x.get("protocol")]
    if isinstance(data, dict):
        if "outbounds" in data and isinstance(data["outbounds"], list):
            return [x for x in data["outbounds"] if isinstance(x, dict)]
        if data.get("protocol"):
            return [data]
    return None


def parse_subscription_to_outbounds(body: str, logger: logging.Logger) -> list[dict[str, Any]]:
    jo = _parse_json_outbounds(body.strip())
    if jo is not None:
        for i, ob in enumerate(jo):
            if "tag" not in ob or not ob["tag"]:
                ob["tag"] = f"sub-{i}-json"
        logger.info("订阅解析为 JSON outbounds，共 %d 条", len(jo))
        return jo
    lines = [ln.strip() for ln in body.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    out: list[dict[str, Any]] = []
    for i, ln in enumerate(lines):
        ob = _line_to_outbound(ln, i)
        if ob:
            out.append(ob)
        else:
            logger.debug("跳过无法解析的行: %s", ln[:80])
    return out


def _default_inbounds() -> list[dict[str, Any]]:
    return [
        {
            "listen": "127.0.0.1",
            "port": 7890,
            "protocol": "socks",
            "settings": {"udp": True},
            "tag": "socks-in",
        }
    ]


def _truthy_yaml(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in ("1", "true", "yes", "on")


def _coerce_port(val: Any) -> int | None:
    if val is None or val is False:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val if 1 <= val <= 65535 else None
    try:
        i = int(str(val).strip(), 10)
        return i if 1 <= i <= 65535 else None
    except (TypeError, ValueError):
        return None


def _load_user_config_doc(myclash_root: Path) -> dict[str, Any] | None:
    p = myclash_root / "user_config.yaml"
    if not p.is_file():
        return None
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _user_specifies_v2ray_listen(doc: dict[str, Any]) -> bool:
    return any(
        k in doc
        for k in ("allow-lan", "allow_lan", "port", "socks-port", "socks_port")
    )


def _proxy_outbounds_from_saved_v2ray(data: dict[str, Any]) -> list[dict[str, Any]]:
    """从已写入的完整 v2ray JSON 取出代理 outbound（去掉 ``freedom``；``_assemble`` 会再追加 direct 尾节）。"""
    raw = data.get("outbounds")
    if not isinstance(raw, list):
        return []
    return [dict(x) for x in raw if isinstance(x, dict) and x.get("protocol") != "freedom"]


def _inbounds_from_user_and_base(
    user_doc: dict[str, Any] | None,
    base_inbounds: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """user_config 中声明了监听项时，用其生成 socks-in/http-in，并与 base 里其它入站按 tag 合并。"""
    proxy_tags = frozenset({"socks-in", "http-in"})
    base_ok = isinstance(base_inbounds, list) and base_inbounds
    if user_doc and _user_specifies_v2ray_listen(user_doc):
        fresh = _proxy_inbounds_from_user_config(user_doc)
        if not base_ok:
            return fresh
        kept = [x for x in base_inbounds if isinstance(x, dict) and str(x.get("tag") or "") not in proxy_tags]
        return fresh + kept
    if base_ok:
        return list(base_inbounds)
    return _default_inbounds()


def _proxy_inbounds_from_user_config(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """与 user_config 中 Clash 段对齐：SOCKS 用 socks-port（否则用 port），另有 port 且不同时加 HTTP 入站。"""
    listen = "0.0.0.0" if _truthy_yaml(doc.get("allow-lan", doc.get("allow_lan"))) else "127.0.0.1"
    http_p = _coerce_port(doc.get("port"))
    socks_p = _coerce_port(doc.get("socks-port", doc.get("socks_port")))
    out: list[dict[str, Any]] = []
    if socks_p is not None:
        out.append(
            {
                "listen": listen,
                "port": socks_p,
                "protocol": "socks",
                "settings": {"udp": True},
                "tag": "socks-in",
            }
        )
    elif http_p is not None:
        out.append(
            {
                "listen": listen,
                "port": http_p,
                "protocol": "socks",
                "settings": {"udp": True},
                "tag": "socks-in",
            }
        )
    else:
        out.append(
            {
                "listen": listen,
                "port": 7890,
                "protocol": "socks",
                "settings": {"udp": True},
                "tag": "socks-in",
            }
        )
    if http_p is not None and socks_p is not None and http_p != socks_p:
        out.append(
            {
                "listen": listen,
                "port": http_p,
                "protocol": "http",
                "settings": {},
                "tag": "http-in",
            }
        )
    return out


def _user_wants_v2ray_geo_split(user_doc: dict[str, Any] | None) -> bool:
    """``user_config.yaml`` 中 ``v2ray_geo_split: false`` 可关闭分流（即便存在 geoip/geosite）。"""
    if not isinstance(user_doc, dict):
        return True
    return user_doc.get("v2ray_geo_split") is not False


def _prepend_v2ray_geo_rules(proxy_tail: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """私有网段与国内域名/IP 直连，其余回落到紧跟其后的代理规则。"""
    head = [
        {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"},
        {"type": "field", "domain": ["geosite:cn"], "outboundTag": "direct"},
        {"type": "field", "ip": ["geoip:cn"], "outboundTag": "direct"},
    ]
    return head + proxy_tail


def _v2ray_fixed_outbound_tag(user_doc: dict[str, Any] | None) -> str:
    """``user_config.yaml`` 中可选 ``v2ray_outbound_tag``：多节点时固定走该 outbound tag；缺省或无效则多节点用随机 balancer。"""
    if not isinstance(user_doc, dict):
        return ""
    v = user_doc.get("v2ray_outbound_tag")
    if isinstance(v, str) and v.strip():
        return v.strip()
    return ""


def _assemble_v2ray_config(
    existing: dict[str, Any] | None,
    proxy_outbounds: list[dict[str, Any]],
    user_doc: dict[str, Any] | None = None,
    *,
    myclash_root: Path | None = None,
) -> dict[str, Any]:
    base = dict(existing) if isinstance(existing, dict) else {}
    log = base.get("log") if isinstance(base.get("log"), dict) else {"loglevel": "warning"}
    base_inb = base.get("inbounds")
    if not isinstance(base_inb, list):
        base_inb = None
    inb = _inbounds_from_user_and_base(user_doc, base_inb)
    tags = []
    for i, ob in enumerate(proxy_outbounds):
        t = str(ob.get("tag") or f"sub-{i}")
        ob["tag"] = t
        tags.append(t)
    tail = [
        {"protocol": "freedom", "tag": "direct"},
    ]
    outbounds = [*proxy_outbounds, *tail]
    routing: dict[str, Any] = {"domainStrategy": "AsIs", "rules": []}
    balancers: list[dict[str, Any]] | None = None
    if len(tags) == 1:
        tail_rules = [{"type": "field", "network": "tcp,udp", "outboundTag": tags[0]}]
    elif len(tags) > 1:
        fixed = _v2ray_fixed_outbound_tag(user_doc)
        tag_set = frozenset(tags)
        if fixed and fixed in tag_set:
            tail_rules = [{"type": "field", "network": "tcp,udp", "outboundTag": fixed}]
        else:
            balancers = [
                {
                    "tag": "proxy",
                    "selector": tags,
                    "strategy": {"type": "random"},
                }
            ]
            tail_rules = [{"type": "field", "network": "tcp,udp", "balancerTag": "proxy"}]
    else:
        tail_rules = []
    use_geo = (
        myclash_root is not None
        and _user_wants_v2ray_geo_split(user_doc)
        and v2ray_geo_asset_dir(myclash_root) is not None
    )
    if use_geo:
        routing["domainStrategy"] = "IPIfNonMatch"
    if balancers:
        routing["balancers"] = balancers
    routing["rules"] = (
        _prepend_v2ray_geo_rules(tail_rules) if use_geo else tail_rules
    )
    return {"log": log, "inbounds": inb, "outbounds": outbounds, "routing": routing}


def download_v2ray_subscription_outbounds(
    *,
    myclash_root: Path,
    profile_name: str,
    url: str,
    logger: logging.Logger,
    debug: bool = False,
) -> list[dict[str, Any]] | None:
    """Download and parse subscription; returns outbounds or ``None`` on failure."""
    url = (url or "").strip()
    if not url:
        logger.warning("v2ray 订阅 %s 未配置 url，跳过下载", profile_name)
        return None
    cache = subscribe_cache_dir(myclash_root)
    cache.mkdir(parents=True, exist_ok=True)
    logger.info('====Download v2ray sub "%s"====', profile_name)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f"{profile_name}-dl.", suffix=".tmp", dir=str(cache)
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        ok, curl_diag = _curl_download(url, tmp_path)
        if not ok:
            logger.error("v2ray 订阅 %s 下载失败", profile_name)
            if curl_diag:
                logger.error("curl: %s", curl_diag)
            return None
        text = _decode_subscription_text(tmp_path.read_bytes())
    finally:
        tmp_path.unlink(missing_ok=True)
    outbounds = parse_subscription_to_outbounds(text, logger)
    if not outbounds:
        logger.error("v2ray 订阅 %s 解析后无可用节点", profile_name)
        if debug:
            preview = text.strip().replace("\r\n", "\n")[:500]
            logger.debug("订阅正文预览（截断）:\n%s", preview)
    return outbounds


def refresh_v2ray_json_listen_from_user_config(
    *,
    myclash_root: Path,
    profile_name: str,
    logger: logging.Logger,
    write_mcs: bool = False,
    include_mcs: bool | None = None,
) -> bool:
    """已有 ``cache/<profile>.json`` 时，仅按当前 ``user_config`` 的 ``socks-port`` / ``port`` / ``allow-lan`` 等重写入站（无需重新下载订阅）。"""
    cache_path = subscribe_cache_dir(myclash_root) / f"{profile_name}.json"
    if not cache_path.is_file():
        return False
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    obs = _proxy_outbounds_from_saved_v2ray(data)
    if not obs:
        return False
    write_v2ray_json_from_outbounds(
        myclash_root=myclash_root,
        profile_name=profile_name,
        outbounds=obs,
        logger=logger,
        write_mcs=write_mcs,
        include_mcs=include_mcs,
    )
    return True


def write_v2ray_json_from_outbounds(
    *,
    myclash_root: Path,
    profile_name: str,
    outbounds: list[dict[str, Any]],
    logger: logging.Logger,
    write_mcs: bool = True,
    include_mcs: bool | None = None,
) -> None:
    """``include_mcs`` 为 ``None`` 时与 ``write_mcs`` 相同；可在仅写 cache 时仍合并当前 ``mcs/v2ray.json`` 的 inbounds。"""
    use_mcs = write_mcs if include_mcs is None else include_mcs
    existing = _load_v2ray_existing_for_merge(
        myclash_root, profile_name, include_mcs=use_mcs
    )
    user_doc = _load_user_config_doc(myclash_root)
    cfg = _assemble_v2ray_config(
        existing, outbounds, user_doc, myclash_root=myclash_root
    )
    cache_path = subscribe_cache_dir(myclash_root) / f"{profile_name}.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if write_mcs:
        cfg_path = mcs_configs_dir(myclash_root) / "v2ray.json"
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        logger.info(
            "v2ray 配置已写入 %s 与 %s（%d 个代理 outbound），请执行 myclash service restart 使内核重载",
            cache_path,
            cfg_path,
            len(outbounds),
        )
    else:
        logger.info(
            "v2ray 订阅 %s 已写入 %s（%d 个代理 outbound）",
            profile_name,
            cache_path,
            len(outbounds),
        )


def download_and_write_v2ray_config(
    *,
    myclash_root: Path,
    profile_name: str,
    url: str,
    logger: logging.Logger,
) -> bool:
    """Download subscription from ``url``; write cache + ``mcs/configs/v2ray.json``（供切换默认订阅时调用）。"""
    obs = download_v2ray_subscription_outbounds(
        myclash_root=myclash_root,
        profile_name=profile_name,
        url=url,
        logger=logger,
    )
    if not obs:
        return False
    write_v2ray_json_from_outbounds(
        myclash_root=myclash_root,
        profile_name=profile_name,
        outbounds=obs,
        logger=logger,
    )
    return True
