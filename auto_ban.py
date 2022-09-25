import json
import time
from typing import Dict, TypedDict

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bilibili_api import Credential, live, sync

import login

lottery_danmu_list = [
    "老板大气！点点红包抽礼物",
    "点点红包，关注主播抽礼物～",
    "喜欢主播加关注，点点红包抽礼物",
    "红包抽礼物，开启今日好运！",
    "中奖喷雾！中奖喷雾！",
]
with open("emoji.json", "r", encoding="utf-8") as f:
    emoji_list = json.load(f)


class Lottery(TypedDict):
    """用户弹幕列表
    user_name: 用户名
    lottery_danmu_time: 发送抽奖弹幕的时间
    danmu_num: 发送弹幕的数量"""

    user_name: str
    lottery_danmu_time: int
    danmu_num: int


room_id = 1184275
# room_id = 22140083  # 阿屑的直播间号
room = live.LiveDanmaku(room_id)  # wss连接到直播间弹幕
user_list: Dict[int, Lottery] = dict()  # 监测用户列表以及数据记录
sched = AsyncIOScheduler(timezone="Asia/Shanghai")  # 定时任务框架


def login_room():
    """通过 login.py 登录到 LiveRoom

    Returns:
        LiveRoom: bilibili_api 包的直播间操作类
    """
    cookies = login.bzlogin()

    SESSDATA = cookies["SESSDATA"]
    BILI_JCT = cookies["bili_jct"]
    BUVID3 = cookies["buvid3"]

    # 实例化 Credential 类
    credential = Credential(sessdata=SESSDATA, bili_jct=BILI_JCT, buvid3=BUVID3)
    live_room = live.LiveRoom(room_id, credential)
    return live_room


async def ban(uid: int, name: str):
    """禁言用户

    Args:
        uid (int): 用户 b 站 uid
        name (str): 用户 b 站昵称
    """
    res = await live_room.ban_user(uid)
    if not res:
        print(f"已禁言 {name}")
    else:
        print(res)


async def new_user_list(uid: int, name: str):
    """添加到监测用户列表

    Args:
        uid (int): UID
        name (str): 昵称
    """
    # 新建 Lottery 对象
    user_list[uid] = Lottery(
        user_name=name,
        lottery_danmu_time=int(time.time()),
        danmu_num=0,
    )
    # 开启一个监控，每 3 秒检测一次是否超时
    sched.add_job(check, "interval", seconds=3, args=[uid], id=str(uid))
    print(f"正在监测{name}弹幕活动")


async def update_user_list(uid: int):
    """更新监测用户弹幕数记录

    Args:
        uid (int): UID
    """
    user = user_list.get(uid)
    if user:
        # 如果用户列表中有该用户 则更新他的弹幕数量
        user["danmu_num"] += 1
        if user["danmu_num"] >= 3:  # 超过 3 条自动禁言
            await ban(uid, user["user_name"])
            sched.remove_job(str(uid))
            user_list.pop(uid)


async def zero_user_list(uid: int):
    """弹幕数量记录归零

    Args:
        uid (int): UID
    """
    user = user_list.get(uid)
    if user:
        # 如果用户列表中有该用户 则归零他的弹幕数量
        user["danmu_num"] = 0


@room.on("DANMU_MSG")
async def on_danmaku(event):
    """收到弹幕并处理

    Args:
        event (json): 弹幕事件
    """
    info = event["data"]["info"]
    medal = info[3]
    # 脚本检测
    if (not medal) or (medal[3] != 1184275):  # 不戴鸽宝牌子的小心点捏
        danmu = info[1]
        uid = info[2][0]
        name = info[2][1]
        if danmu in lottery_danmu_list:
            await new_user_list(uid, name)  # 抽奖就开始监测
        elif danmu in emoji_list:
            await update_user_list(uid)  # 发表情包更新记录数量
        else:
            await zero_user_list(uid)  # 发其他弹幕则记录数量归零


async def check(uid: int):
    """检查监测任务是否超时

    Args:
        uid (int): UID
    """
    user = user_list.get(uid)
    if user:
        if int(time.time()) - user.get("lottery_danmu_time", 0) >= 180:  # 超过 180 秒后停止监测
            sched.remove_job(str(uid))  # 移除该监控任务
            user_list.pop(uid)  # 将该用户从列表中弹出


if __name__ == "__main__":
    live_room = login_room()
    sched.start()
    sync(room.connect())
