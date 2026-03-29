import requests
import json
import os
url = "http://127.0.0.1:9090/logs"
response = requests.request("GET", url)
print("over")