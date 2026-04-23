import re


def is_valid_url(url):
    # 定义一个常见的网址正则表达式
    url_regex = re.compile(
        r'^(https?|ftp)://[^\s/$.?#].[^\s]*$', re.IGNORECASE)
    
    return re.match(url_regex, url) is not None


if __name__ == "__main__":
    print(is_valid_url("https://www.example.com"))  # True
    print(is_valid_url("ftp://ftp.example.com"))    # True
    print(is_valid_url("invalid-url"))               # False