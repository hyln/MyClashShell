"""将 Clash / mihomo 风格 ``rules`` 列表转为 Xray / v2ray-core 的 ``routing`` 片段。

仅覆盖常见字面规则（与 ``install/templates/rules.yaml`` 一致的那类），**不**支持
``RULE-SET`` / ``GEOSITE`` 等需外部资源的条目。无法识别的行会跳过（调用方可打日志）。

语义说明：与 Clash 仍可能有细微差别（例如 ``no-resolve``、进程名匹配在不同内核版本上的行为）。
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_VIA_NAMES = frozenset({"Via-Proxy", "VIA-PROXY", "via-proxy"})


def _split_rule_line(line: str) -> tuple[str, list[str], str] | None:
    s = line.strip()
    if not s:
        return None
    parts = [p.strip() for p in s.split(",")]
    if len(parts) < 2:
        return None
    if parts[-1].lower() == "no-resolve":
        parts = parts[:-1]
    if len(parts) < 2:
        return None
    return parts[0].upper(), parts[1:-1], parts[-1]


def _domain_xray_token(kind: str, arg: str) -> str | None:
    arg = arg.strip()
    if not arg:
        return None
    if kind == "DOMAIN":
        if "*" in arg:
            escaped = re.escape(arg).replace(r"\*", ".*")
            return f"regexp:{escaped}"
        return f"full:{arg}"
    if kind == "DOMAIN-SUFFIX":
        return f"domain:{arg}"
    if kind == "DOMAIN-KEYWORD":
        return f"keyword:{arg}"
    return None


def _map_policy(
    policy: str,
    *,
    use_balancer: bool,
    balancer_tag: str,
    fixed_proxy_tag: str,
) -> tuple[str | None, str | None]:
    p = policy.strip()
    if p == "DIRECT":
        return "direct", None
    if p in _VIA_NAMES:
        if use_balancer:
            return None, balancer_tag
        return fixed_proxy_tag, None
    if p == "REJECT":
        return "block", None
    logger.warning("v2ray 规则转换：不支持的策略 %r，已跳过", policy)
    return None, None


def _field_rule(
    *,
    outbound_tag: str | None,
    balancer_tag: str | None,
    domain: list[str] | None = None,
    ip: list[str] | None = None,
    source_process_name: list[str] | None = None,
) -> dict[str, Any]:
    r: dict[str, Any] = {"type": "field", "network": "tcp,udp"}
    if domain:
        r["domain"] = domain
    if ip:
        r["ip"] = ip
    if source_process_name:
        r["sourceProcessName"] = source_process_name
    if outbound_tag:
        r["outboundTag"] = outbound_tag
    if balancer_tag:
        r["balancerTag"] = balancer_tag
    return r


def clash_rules_to_v2ray_routing(
    clash_rules: list[str],
    *,
    proxy_tags: list[str],
    fixed_proxy_tag: str,
    use_balancer: bool,
    balancer_tag: str = "proxy",
) -> dict[str, Any] | None:
    """返回含 ``domainStrategy``、``rules`` 的字典；无法生成任何规则时返回 ``None``。

    - ``use_balancer`` 为真时，Clash 中指向 ``Via-Proxy`` 的规则使用 ``balancerTag``。
    - 否则全部走 ``fixed_proxy_tag``（单节点或用户固定节点时应传入对应 outbound tag）。
    """
    if not clash_rules:
        return None
    if use_balancer and not proxy_tags:
        return None
    if not use_balancer and not fixed_proxy_tag:
        return None

    v2_rules: list[dict[str, Any]] = []
    has_geoip = False
    needs_block = False

    for raw in clash_rules:
        if not isinstance(raw, str):
            continue
        parsed = _split_rule_line(raw)
        if not parsed:
            continue
        kind, middle, policy = parsed
        ob, bal = _map_policy(
            policy,
            use_balancer=use_balancer,
            balancer_tag=balancer_tag,
            fixed_proxy_tag=fixed_proxy_tag,
        )
        if not ob and not bal:
            continue
        if ob == "block":
            needs_block = True

        if kind in ("DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD"):
            if len(middle) != 1:
                continue
            tok = _domain_xray_token(kind, middle[0])
            if not tok:
                continue
            v2_rules.append(
                _field_rule(
                    outbound_tag=ob,
                    balancer_tag=bal,
                    domain=[tok],
                )
            )
            continue

        if kind in ("IP-CIDR", "IP-CIDR6"):
            if len(middle) != 1:
                continue
            cidr = middle[0].strip()
            if not cidr:
                continue
            v2_rules.append(
                _field_rule(
                    outbound_tag=ob,
                    balancer_tag=bal,
                    ip=[cidr],
                )
            )
            continue

        if kind == "GEOIP":
            if len(middle) != 1:
                continue
            code = middle[0].strip()
            if not code:
                continue
            has_geoip = True
            v2_rules.append(
                _field_rule(
                    outbound_tag=ob,
                    balancer_tag=bal,
                    ip=[f"geoip:{code.lower()}"],
                )
            )
            continue

        if kind == "PROCESS-NAME":
            if not middle:
                continue
            name = ",".join(middle).strip()
            if not name:
                continue
            v2_rules.append(
                _field_rule(
                    outbound_tag=ob,
                    balancer_tag=bal,
                    source_process_name=[name],
                )
            )
            continue

        if kind == "MATCH":
            v2_rules.append(_field_rule(outbound_tag=ob, balancer_tag=bal))
            continue

        if kind in ("RULE-SET", "GEOSITE", "AND", "OR", "NOT", "SUB-RULE"):
            logger.warning("v2ray 规则转换：暂不支持的类型 %s，已跳过", kind)
            continue

    if not v2_rules:
        return None

    domain_strategy = "IPIfNonMatch" if has_geoip else "AsIs"
    return {
        "domainStrategy": domain_strategy,
        "rules": v2_rules,
        "needs_block": needs_block,
    }


def routing_with_proxy_balancer(
    base: dict[str, Any],
    *,
    proxy_tags: list[str],
    strategy: str = "random",
) -> dict[str, Any]:
    """在 ``base`` 上注入多节点 ``balancers``（与原先 ``_assemble_v2ray_config`` 行为一致）。"""
    out = dict(base)
    tags = [t for t in proxy_tags if t]
    if len(tags) > 1:
        out["balancers"] = [
            {
                "tag": "proxy",
                "selector": tags,
                "strategy": {"type": strategy},
            }
        ]
    return out
