import json
import time
from typing import Dict, TypedDict

from apscheduler.jobstores.base import ConflictingIdError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bilibili_api import live, sync
from loguru import logger

from create_config import create_config
from login_by_bilibili_api import login_and_save_in_file


logger.add("./log/log_{time}.log", rotation="00:00")

if create_config():
    logger.info("配置文件不存在，已使用模板新建")
else:
    logger.info("配置文件已存在")

with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)
    room_id = config["room_id"]
    lottery_danmu_list = config["lottery_danmu_list"]
    emoji_list = config["emoji"]
    excluded_list = config["excluded"]


class Lottery(TypedDict):
    """用户弹幕列表
    user_name: 用户名
    lottery_danmu_time: 发送抽奖弹幕的时间
    danmu_num: 发送弹幕的数量"""

    user_name: str
    lottery_danmu_time: int
    danmu_num: int


# room_id = 22140083  # 阿屑的直播间号
room = live.LiveDanmaku(room_id)  # wss连接到直播间弹幕
user_list: Dict[int, Lottery] = dict()  # 监测用户列表以及数据记录
sched = AsyncIOScheduler(timezone="Asia/Shanghai")  # 定时任务框架


def login_room():
    """通过 login_by_bilibili_api.py 登录到 LiveRoom

    Returns:
        LiveRoom: bilibili_api 包的直播间操作类
    """
    # 实例化 Credential 类
    credential = login_and_save_in_file()
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
        logger.success("已禁言 {}", name)
    else:
        logger.warning("禁言失败，resp如下：\n{}", res)


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
    try:
        sched.add_job(check, "interval", seconds=3, args=[uid], id=str(uid))
        logger.info("正在监测 {} 弹幕活动", name)
    except ConflictingIdError:
        logger.info("{} 重复抽奖，已重置监测数据", name)


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
    guard = info[7]
    # 脚本检测
    if not guard:
        if (not medal) or (medal[3] != room_id):  # 不戴鸽宝牌子的小心点捏
            danmu = info[1]
            uid = info[2][0]
            name = info[2][1]
            if danmu in lottery_danmu_list:
                await new_user_list(uid, name)  # 抽奖就开始监测
            elif danmu in excluded_list:  # 排除列表
                pass
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
