import os
import json

from bilibili_api import CredentialNoBiliJctException, settings, sync, Credential
from bilibili_api.login import (
    Check,
    PhoneNumber,
    login_with_password,
    login_with_qrcode,
    login_with_sms,
    send_sms,
)
from bilibili_api.user import get_self_info


def login_by_password():
    # 密码登录
    username = input("请输入手机号/邮箱：")
    password = input("请输入密码：")
    print("正在登录。")
    c = login_with_password(username, password)
    if isinstance(c, Check):
        # 还需验证
        phone = input("需要验证。请输入手机号：")
        c.set_phone(PhoneNumber(phone, country="+86"))  # 默认设置地区为中国大陆
        c.send_code()
        print("已发送验证码。")
        code = input("请输入验证码：")
        credential = c.login(code)
        print("登录成功！")
    else:
        credential = c
    return credential


def login_by_sms():
    # 验证码登录
    phone = input("请输入手机号：")
    print("正在登录。")
    send_sms(PhoneNumber(phone, country="+86"))  # 默认设置地区为中国大陆
    code = input("请输入验证码：")
    c = login_with_sms(PhoneNumber(phone, country="+86"), code)
    credential = c
    print("登录成功")
    return credential


def login_by_qrcode():
    print("请登录：")
    credential = login_with_qrcode()
    try:
        credential.raise_for_no_bili_jct()  # 判断是否成功
        credential.raise_for_no_sessdata()  # 判断是否成功
    except CredentialNoBiliJctException:
        print("登陆失败。。。")
        exit()
    return credential


def main_login():
    mode = input(
        """请选择登录方式：
    1. 密码登录
    2. 验证码登录
    3. 二维码登录
    请输入 1/2/3
    """
    )

    credential = None

    # 关闭自动打开 geetest 验证窗口
    settings.geetest_auto_open = False

    if mode == "1":
        credential = login_by_password()
    elif mode == "2":
        credential = login_by_sms()
    elif mode == "3":
        credential = login_by_qrcode()
    else:
        print("请输入 1/2/3 ！")
        exit()

    if credential is not None:
        name = sync(get_self_info(credential))["name"]
        print(f"欢迎，{name}!")
        return credential


def login_and_save_in_file():
    nowdir = os.getcwd()
    result_file = os.path.join(nowdir, "bili_credential.json")
    if not os.path.exists(result_file):
        with open(result_file, "w") as f:
            json.dump(dict(), f)
    with open(result_file, "r", encoding="utf-8") as f:
        c = json.load(f)

    try:
        credential = Credential(
            sessdata=c["SESSDATA"],
            bili_jct=c["bili_jct"],
            buvid3=c["buvid3"],
            dedeuserid=c["DedeUserID"],
        )
        print("cookies 存在，已登录")
    except KeyError:
        credential = main_login()
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(credential.get_cookies(), f)

    return credential


if __name__ == "__main__":
    credential = login_and_save_in_file()
    print(credential.get_cookies())