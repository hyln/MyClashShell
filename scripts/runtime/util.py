import re
import requests
import json

def is_valid_url(url):
    # 定义一个常见的网址正则表达式
    url_regex = re.compile(
        r'^(https?|ftp)://[^\s/$.?#].[^\s]*$', re.IGNORECASE)
    
    return re.match(url_regex, url) is not None

def update_config_by_api(yaml_path): 
    '''
    通过restapi更新配置文件
    '''
    url = "http://127.0.0.1:9090/configs"
    payload = json.dumps({
    "path": yaml_path
    })
    headers = {
    'Content-Type': 'application/json'
    }
    
    response = requests.request("PUT", url, headers=headers, data=payload)
    if(response.text):
        print(response.text)
        return False
    else:
        return True
if __name__ == "__main__":
    print(is_valid_url("https://www.example.com"))  # True
    print(is_valid_url("ftp://ftp.example.com"))    # True
    print(is_valid_url("invalid-url"))               # False