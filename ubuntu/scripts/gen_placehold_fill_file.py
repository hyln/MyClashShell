#!/usr/bin/env python3
import re
import sys
import os
# 定义函数：扫描占位符并替换为给定的替换值
def replace_placeholders(file_path,outpath, replacements):
    # 定义占位符的正则表达式，假设格式为 <|PLACEHOLD_X|>
    pattern = r"<\|PLACEHOLD_\d+\|>"

    # 打开文件并读取内容
    with open(file_path, 'r') as file:
        content = file.read()

    # 使用正则表达式查找所有匹配的占位符
    placeholders = re.findall(pattern, content)

    # 输出占位符个数
    # print(f"文件 '{file_path}' 中的占位符数量: {len(placeholders)}")
    
    # 输出找到的占位符
    # print("找到的占位符：")
    # for placeholder in placeholders:
    #     print(placeholder)

    # 确保替换值的数量与占位符的数量相同
    if len(replacements) != len(placeholders):
        print("错误：替换值的数量与占位符的数量不匹配！")
        return

    # 逐个替换占位符
    for i, placeholder in enumerate(placeholders):
        content = content.replace(placeholder, replacements[i])

    # 输出修改后的内容
    # print("\n替换后的内容：")
    print(content)
    try:
        # 将替换后的内容写回文件
        with open(outpath, 'w') as file:
            file.write(content)
    except PermissionError as e:
        print(f"PermissionError: {e} \n请以root用户运行此脚本！")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: ${MYCLASH_ROOT_PWD}/ubuntu/scripts/gen_placehold_fill_file.py <file_path> <outpath> <replacements>")
        print("Example: ${MYCLASH_ROOT_PWD}/ubuntu/scripts/gen_placehold_fill_file.py ${MYCLASH_ROOT_PWD}/ubuntu/template/myclash.service ${MYCLASH_ROOT_PWD}/tmp/myclash.service ${MYCLASH_ROOT_PWD} ${MYCLASH_ROOT_PWD} ${MYCLASH_ROOT_PWD} ${MYCLASH_ROOT_PWD}")
        sys.exit(1)
    replacements = sys.argv[3:]
    replace_placeholders(sys.argv[1], sys.argv[2], replacements)
    # # 示例调用
    # # 提供替换值列表，替换占位符为指定的值
    # replacements = ["1.0.0", f"{myclash_root_pwd}"]
