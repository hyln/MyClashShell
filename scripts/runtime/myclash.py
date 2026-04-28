#!/usr/bin/env python3
"""Legacy UDP demo（仓库内已无 ``myclash cfg`` 入口）。"""

import socket
import sys


def send_message() -> None:
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_address = ("127.0.0.1", 12345)
    message = "Hello, Server!"
    client.sendto(message.encode("utf-8"), server_address)
    data, _server = client.recvfrom(1024)
    print(f"Received response: {data.decode('utf-8')}")
    client.close()


if __name__ == "__main__":
    send_message()
    print(sys.argv)
    if len(sys.argv) > 2:
        command = sys.argv[2]
        if command == "check_proxy":
            print("check_proxy")
