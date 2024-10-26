import asyncio
from abc import ABC, abstractmethod
from typing import List, Dict, Any, TypedDict, Union, Set, Optional
from nonebot.exception import StopPropagation
from .love_manager import db_path, update_love, update_alias, read_alias, get_both_love, read_pic, find_qq_by_conditions, start_db, del_qq_record, info_qq, read_love, get_loverank, get_range, replace_qq, read_five_codes, generate_codes, check_code, decrement_count, write_str_love, write_pic, global_compare, get_low_ten_qqs, get_real_id, update_real_id
from .AI_chat import clear_memory
from .others import DailyCacheDecorator, tell_record, read_five_tells, code_record, check_images_similarity, download, check_group_folder, find_images
from .draftbottles import DraftBottle, start_server, init_app
from .wordbank import group_del, group_write, lock_row, load_info, find_row, del_row,  init_wordbank
from .Grouper import GroupMembers
from .battlefieldQueen import NFManager
from threading import Thread
import re
import asyncio
import sqlite3
from PIL import Image
import base64
import httpx
import io
import random
import time
import os
from .pic_gen import pic_reply
from .perm import AdminManager, MsgManager, super_admin_record, BlackWhiteList, super_admin_action
from .sensitive_test import sensitive_word
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent, Message, MessageSegment
from nonebot.rule import is_type
from nonebot_plugin_waiter import waiter
from .config import result
from nonebot.exception import StopPropagation
from nonebot import logger
(
    bot_name, baseline, rate, master,
    search_love_reply, botreact, model, role,
    API_Key, Secret_Key, tank_enable, Ca, Cb,
    lv_enable, La, Lb, Lc, Ld,
    Le, Lf, Lg, Lh, Li, Lj,
    lv1_reply, lv2_reply, lv3_reply, lv4_reply, lv5_reply, memory
) = result
rule = is_type(PrivateMessageEvent,
               Union[GroupMessageEvent, PrivateMessageEvent])


async def start_bot():
    global Draft, admin_group, Msg_Transmitter, daily_decorator, black_white_list, super_admins, app, groupmember, bf_nf
    Draft = DraftBottle()
    admin_group = AdminManager()
    Msg_Transmitter = MsgManager()
    daily_decorator = DailyCacheDecorator()
    black_white_list = BlackWhiteList()
    groupmember = GroupMembers()
    bf_nf = NFManager()
    init_wordbank()
    start_db()
    await Msg_Transmitter.load_data()
    await black_white_list._load_lists()
    super_admins = await super_admin_action(None, 'get')
    logger.info('漂流瓶|消息传递|签到装饰器|黑白名单 初始化完成')
    if botreact != True or model == 'qingyunke':
        pass
    else:
        os.environ["QIANFAN_AK"] = API_Key
        os.environ["QIANFAN_SK"] = Secret_Key
        logger.info('AI初始化完成')
    init_app()
    server_thread = Thread(target=start_server)
    server_thread.start()
    from .draftbottles import app
    logger.info('WEB审核上线')


class Handler(ABC):
    def __init__(self, block: bool = True):
        self.block = block

    @abstractmethod
    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        pass

    def is_super_admin(self, qq: str) -> bool:
        return qq == master or qq in super_admins

    def is_group_admin(self, qq: str, groupid: str) -> Optional[str]:
        return 'high' if self.is_super_admin(qq) else admin_group.check_admin(groupid, qq)

    def is_PrivateMessageEvent(self, event: Union[GroupMessageEvent, PrivateMessageEvent]):
        return event.message_type == 'private'


class GetCode(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if qq == master and self.is_PrivateMessageEvent(event):
            msg = msg.replace('/code ', '', 1)
            tells = await read_five_codes(msg)
            message = f'适用于{msg}的密码'
            formatted_message = '\n'.join([message] + tells)
            await bot.send(event, formatted_message)


class SuperAdminCommandHandler(Handler):
    def __init__(self, block: bool = True) -> None:
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], **kwargs: Any) -> None:
        if qq == master:
            if msg.startswith('/sa add '):
                target = msg.replace('/sa add ', '', 1)
                await self.process_super_admin_action(target, 'add', bot, event)
            elif msg.startswith('/sa del '):
                target = msg.replace('/sa del ', '', 1)
                await self.process_super_admin_action(target, 'remove', bot, event)

    async def process_super_admin_action(self, target: str, action: str, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]) -> None:
        global super_admins
        if action == 'add':
            if target not in super_admins:
                super_admins = await super_admin_action(target, 'add')
                await bot.send(event, f'已尝试添加{target}为超管')
            else:
                await bot.send(event, f'{target}已经是超管')
        elif action == 'remove':
            if target in super_admins:
                super_admins = await super_admin_action(target, 'remove')
                await bot.send(event, f'已尝试取消{target}为超管')
            else:
                await bot.send(event, f'{target}不是超管')
        logger.debug(f'执行了超管操作：{action} {target}')


class GetUserID(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        await bot.send(event, f'你的ID是{qq}')
        logger.debug('ID查询')


class BF_addQueen(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if groupid!='143':
            return
        name = msg.replace("/addnf ", "", 1)
        result=bf_nf.check_server_exists(name)
        try:
            await bf_nf.add_nf(name, type=1, qq=qq)
            if result:
                await bot.send(event, f"{name} 已添加入列表。请使用 战地1小电视 手动搜索，确认你的目标服务器位于服务器搜索结果第一位")
            else:
                await bot.send(event, f'{name} 已添加入列表,但未查询到该服务器')
        except sqlite3.IntegrityError:
            await bot.send(event, '该服务器已存在于队列,添加失败')


class BF_removeQueen(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if groupid!='143':
            return
        name = msg.replace("/delnf ", "", 1)
        await bf_nf.cancel_nf(name)
        await bot.send(event, f"{name} 已移出列表")


class BF_showQueen(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        record = await bf_nf.show_nf(1)
        top_record = record['top_record']
        if not top_record:
            msg_to_send = f"\n当前正在暖服 {top_record['name']}:\n未查询到详细信息"
            msg_to_send2 = '\n'.join(f"{record['name']}  : {record['time']}" for record in records)
            await bot.send(event, f'{msg_to_send}\n暖服队列:\n{msg_to_send2}')
            return
        records = record['records']
        msg_to_send = f"\n当前正在暖服 {top_record['name']}:\n{top_record["prefix"]}\n人数: {
            top_record["playerAmount"]}/{top_record["maxPlayers"]}   地图:{top_record["currentMap"]}"
        msg_to_send2 = '\n'.join(f"{record['name']}  : {record['time']}" for record in records)
        await bot.send(event, f'{msg_to_send}\n暖服队列:\n{msg_to_send2}')


class GetWebCode(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if self.is_super_admin(qq) and self.is_PrivateMessageEvent(event):
            code = app.generate_webcode()
            await bot.send(event, f'请在30s内使用秘钥\n{code}')


class GetGroupID(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        await bot.send(event, f'本群ID是{groupid}')
        logger.debug('群ID查询')


class DFpic(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        image_url = "https://img.paulzzh.com/touhou/random?size=all&size=konachan"
        async with httpx.AsyncClient() as client:
            response = await client.get(image_url, follow_redirects=True)

            # 将HTTP响应内容读入BytesIO对象
            image_data = io.BytesIO(response.content)

            # 使用Pillow打开图片
        try:
            img = Image.open(image_data)

            jpeg_image_data = io.BytesIO()
            img.save(jpeg_image_data, format='JPEG', quality=30)
            jpeg_image_data.seek(0)  # 重置文件指针到开始位置

            # 将图片数据编码为base64
            base64_encoded = base64.b64encode(
                jpeg_image_data.getvalue()).decode('utf-8')

            # 发送base64编码的图片
            await bot.send(event, MessageSegment.image(f'base64://{base64_encoded}'))
        except:
            await bot.send(event, "无法获取图片，请稍后再试喵~")
            raise


class DraftThrow(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if msg == '/扔漂流瓶':
            msg = '/扔漂流瓶 '
        msg = msg.replace('/扔漂流瓶 ', '', 1)
        check = sensitive_word(msg)
        if (msg == '' and not image) or check != None:
            await bot.send(event, f'你的瓶子被{bot_name}吃了喵~')
            return
        if not Draft.is_formated(msg):
            await bot.send(event, f"""\n条件语句格式错误:请符合 [参数=目标:消息 else 消息] 或 [参数=目标:消息] 的格式输入变量
\n支持参数:
\nuserid 触发漂流瓶的用户ID
\ngroupid 触发漂流瓶的群聊ID
\nlove 触发漂流瓶的用户好感度
\nGtype 触发漂流瓶的群聊类型
\nalias 触发漂流瓶的用户别名
\ntime 触发漂流瓶的时间
\n在目标中,可使用 , 来指定多个目标
\n当参数为time时,目标和消息随意填写即可
\n当参数为love时,目标只能是两个值,且必须为*或数字,而且第一个值不大于第二个值""")
            return
        try:
            bottleid = await Draft.insert_bottle(qq, msg, groupid, image)
        except ValueError:
            await bot.send(event, f'\n你发送的图片过大,无法上传。漂流瓶被{bot_name}吃了喵~')
            raise StopPropagation
        await bot.send(event, f'\n你的漂流瓶已经被投入这汪洋大海~\n它的编号是{bottleid}')
        logger.debug('扔出漂流瓶')


class DraftSeeSee(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self,  bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if not self.is_super_admin(qq):
            return
        msg = msg.replace('/bo开盒 ', '', 1).replace('/bo开盒', '', 1)
        ids = await Draft.get_bottle_ids_by_userid(msg)
        if not ids:
            await bot.send(event, f'\n{msg}没有任何漂流瓶记录')
            return
        ids = '\n'.join(ids)
        await bot.send(event, f'\n{msg}有以下漂流瓶记录,可使用/boinfo查询\n{ids}')
        await super_admin_record(f'{qq}查询了{msg}的漂流瓶记录')


class DraftGetter(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self,  bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        try:
            bottle = await Draft.get_bottle(groupid)
            if bottle:
                boid = bottle['id']
                bomessage: str = bottle['message']
                bomessage = await Draft.msg_process(bomessage, qq, groupid)
                likes = bottle['likes']
                dislikes = bottle['dislikes']
                image = bottle['image_base64']
                real_groupid = bottle['groupid']
                if not real_groupid:
                    real_groupid = '尚未绑定'
                reply = f'\n漂流瓶编号{boid}\n来源群: {real_groupid}\n{likes}😆            {
                    dislikes}🤢\n{bomessage}'
                # 这个括号不要动，动了有BUG。vscode红点就红点吧
                if image:
                    message = Message()
                    message += MessageSegment.text(f'{reply}')
                    message += MessageSegment.image(f'base64://{image}')
                    await bot.send(event, message)
                else:
                    await bot.send(event, f'{reply}')
                logger.debug('发送漂流瓶')
            else:
                reply = '大海空荡荡,要不要扔一个漂流瓶喵?'
                await bot.send(event, f'{reply}')
        except Exception as e:
            logger.warning(e)
            await bot.send(event, '处理错误')
            return


class DraftType(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        type = await Draft.get_types_for_groupid(groupid)
        await bot.send(event, f'本群漂流瓶类型为 {type}')
        logger.debug('查询漂流瓶群聊类型')


class DraftHappy(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if msg == '/happy':
            msg = '/happy '
        msg = msg.replace('/happy ', '', 1)
        if not msg:
            await bot.send(event, '请给出要点赞的漂流瓶编号喵~')
            return
        success = await Draft.like_bottle(qq, msg)
        if success:
            await update_love(qq, -2)
            await bot.send(event, '成功点赞喵~')
            logger.debug('点赞成功')
        else:
            await bot.send(event, '点赞失败,可能已经为该漂流瓶点过 赞/踩 喵~')
            logger.debug('点赞失败')


class DraftShit(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if msg == '/shit':
            msg = '/shit '
        msg = msg.replace('/shit ', '', 1)
        if not msg:
            await bot.send(event, '请给出要点踩的漂流瓶编号喵~')
            return
        success = await Draft.dislike_bottle(qq, msg)
        if success:
            await bot.send(event, '成功点踩喵~')
            logger.debug('点踩成功')
        else:
            await bot.send(event, '点踩失败,可能已经为该漂流瓶点过 赞/踩 喵~')
            logger.debug('点踩失败')


class DraftClean(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if not self.is_super_admin(qq):
            return
        try:
            await Draft.clean_old_bottles()
            await bot.send(event, '成功结算漂流瓶好感度奖励')
        except:
            await bot.send(event, '处理错误')
            raise
        await super_admin_record(f'{qq}执行了漂流瓶结算')
        logger.info('漂流瓶结算')


class DraftBlock(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if self.is_group_admin(qq, groupid) != 'high':
            return
        msg = msg.replace('/block ', '', 1).replace('/block', '', 1)
        if not msg:
            await bot.send(event, '请给出要屏蔽的漂流瓶编号喵~')
            return
        try:
            await Draft.block_bottle(msg)
            await bot.send(event, '成功屏蔽喵~')
            logger.debug(f'{qq}屏蔽了{msg}')
        except:
            await bot.send(event, '屏蔽失败,可能该漂流瓶不存在喵~')


class DraftUnBlock(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if not self.is_super_admin(qq):
            return
        msg = msg.replace('/unblock ', '', 1).replace('/unblock', '', 1)
        if not msg:
            await bot.send(event, '请给出要屏蔽的漂流瓶编号喵~')
            return
        try:
            await Draft.unblock_bottle(msg)
            await bot.send(event, '成功解除屏蔽喵~')
            logger.debug(f'{qq}解除屏蔽了{msg}')
            await super_admin_record(f'{qq}解除了{msg}的屏蔽')
        except:
            await bot.send(event, '解除屏蔽失败,可能该漂流瓶不存在喵~')


class DraftTypeList(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if not self.is_group_admin(qq, groupid):
            return
        list = await Draft.list_types()
        reply = "\n".join(f"{key}：{value}" for key, value in list)
        await bot.send(event, f'\n各群聊类型如下\n{reply}')


class DraftChangeType(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if not self.is_group_admin(qq, groupid):
            return
        msg = msg.replace('/ChangeGtype ', '',
                          1).replace("/ChangeGtype ", '', 1)
        check = sensitive_word(msg)
        if check:
            await bot.send(event, f'你发送的类型因为 {check} 被{bot_name}吃掉了')
            return
        listt = msg.split(' ')
        if not listt:
            await bot.send(event, '你没有指定类型喵~')
            return
        await Draft.modify_type(groupid, listt)
        await bot.send(event, '本群漂流瓶类型修改完成了喵~')
        logger.debug(f'{groupid}修改漂流瓶类型为{listt}')


class LoveChange(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if not qq == master:
            return
        try:
            msg = msg.replace('/cl ', '')
            words = msg.split(' ')
            target = words[0]
            love = int(words[1])
            await update_love(target, love)
            logger.debug(f'为{target}增加好感{love}')
            await bot.send(event, '好的喵主人~')
        except:
            await bot.send(event, '失败了喵~')


class DailySign(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        @daily_decorator.decorator
        def sign_daily(qq):
            logger.debug(f'{qq}完成签到')
            return True
        daily = sign_daily(qq)

        if daily == True:
            await update_love(qq, random.randint(1, 5))
            _, strlove = await get_both_love(qq)
            await bot.send(event, f'签到成功！当前你的好感度是 {strlove} ')
        else:
            love = random.randint(-5, -1)
            await update_love(qq, love)
            logger.debug(f'{qq}重复签到')
            await bot.send(event, f'你今天已经签到过了,倒扣好感喵~')


class TellYou(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        msg = msg.replace('/悄悄话', '', 1).replace(' ', '', 1)
        if msg == '':
            await bot.send(event, '为什么不说话呢?害羞嘛?有话要说的话,咱建议附上QQ号和群号喵~')
            return
        elif image:
            await bot.send(event, f'{bot_name}现在还没法记录图片喵~\n如果需要记录图片,请上传图片链接')
            return
        await tell_record(msg, qq, groupid)
        logger.info(f'{qq}有消息发送至管理者')
        await bot.send(event, '我已经把话捎给主人了喵~\n如果希望得到反馈,请附上你的QQ号和所在群的群号喵~')


class ShowYou(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        await super_admin_record(f'{qq}查阅了用户留言')
        tells = await read_five_tells()
        if tells == []:
            await bot.send(event, '\n当前没有用户留言')
            return
        global tellst
        tellst = '\n用户留言'
        for tell in tells:
            tellst = f'{tellst}\n{tell}'
        await bot.send(event, tellst)
        del tellst


class BindYou(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if msg == '/绑定':
            msg = '/绑定 '
        real_qq = msg.replace('/绑定 ', '', 1)
        if not real_qq:
            await bot.send(event, '请输入QQ号喵~')
            return
        int(real_qq)
        url = event.avatar
        image_urls = [
            f'https://q2.qlogo.cn/headimg_dl?dst_uin={real_qq}&spec=5', url]

        # 检查所有哈希值是否相同
        are_identical = await check_images_similarity(image_urls)
        if are_identical:
            logger.debug(f'{qq}绑定成功')
            exist = await get_real_id(qq)
            if not exist:
                await update_real_id(qq, real_qq)
                await bot.send(event, f'你已成功绑定为{real_qq}')
        else:
            logger.debug(f'{qq}绑定失败')
            await bot.send(event, '请绑定自己的QQ号喵~')


class OpenYou(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], **kwargs: Any) -> None:
        if not self.is_super_admin(qq):
            return

        target = msg.replace('/开盒 ', '', 1)

        # 记录管理员操作
        asyncio.create_task(super_admin_record(f'{qq} 定向开盒 {target}'))

        try:
            # 使用正则表达式解析消息中的条件
            pattern = re.compile(r'(\w+)\s*=\s*([^,，]+)\s*(?=,|，|$)')
            matches = pattern.findall(target)

            # 构建搜索字典
            search_dict = {key: value for key, value in matches}

            # 如果没有找到任何键值对，假设整个字符串是一个别名
            if not search_dict and target:
                search_dict['alias'] = target

            # 调用查找函数
            result, conditions = await find_qq_by_conditions(search_dict)
        except Exception as e:
            logger.warning(f"处理错误: {e}")
            await bot.send(event, '处理错误,请检查输入格式')
            return

        # 构建回复消息
        condition_str = ', '.join([f"{k}={v}" for k, v in conditions.items()])
        reply = '\n'.join(result)
        await bot.send(event, f'\n基于 {condition_str} 查询,可能的结果如下:\n{reply}')


class KillYou(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if not self.is_super_admin(qq):
            return
        msg = msg.replace('/kill ', '', 1)
        target = msg.split(' ')[0]
        if target in super_admins or target == master:
            await super_admin_record(f'{qq}尝试违规删除{target}的记录')
            await bot.send(event, '警告！禁止的行为')
            return
        msg = msg.replace(f'{target} ', '').replace(target, '')
        list = msg.split(' ')
        result = await del_qq_record(target, list)
        if result:
            await super_admin_record(f'{qq}删除了{target}的{list}记录')
            await bot.send(event, f'已成功删除{target}的数据喵~')
            logger.debug(f'{target}的记录被删除')
        else:
            await bot.send(event, f'{target}的数据不存在喵~')


class GetAlias(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        logger.debug(f'{qq}尝试获得别名')
        name = await read_alias(qq)
        if name != '':
            await bot.send(event, f'\n你已经拥有别名 {name} 了喵~')
        else:
            await bot.send(event, '\n请在120s内发送您要设置的QQ别名喵~\n请以/开头\n不允许为纯数字')

            @waiter(waits=["message"], keep_session=True, rule=rule)
            async def get_alias(event: Union[GroupMessageEvent, PrivateMessageEvent]):
                """等待指定用户回复来获得别名"""
                msg = event.get_plaintext()
                if msg.startswith(' '):
                    msg = msg.replace(' ', '', 1)
                if msg.startswith('/'):
                    msg = msg.replace('/', '', 1)
                    try:
                        int(msg.replace(' ', ''))
                    except ValueError:
                        return msg
            msg = await get_alias.wait(timeout=120, default=False)

            if not msg:
                return
            sen = sensitive_word(msg)
            if sen is None:
                await update_alias(qq, msg)
                await bot.send(event, '您的QQ别名已设置为:'+msg+' 喵~')
            else:
                sen = sen.replace('.txt', '')
                await bot.send(event, f'你说啊,{qq},在网上搞这些真的有意思吗\n原因:{sen}\n莫  谈  国  事')


class MsgYou(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if not self.is_super_admin(qq):
            return
        if image:
            await bot.send(event, '不支持图片喵~')
            raise StopPropagation
        try:
            msg = msg.replace('/Msg ', '', 1)
            list = msg.split(' ', 1)
            if ',' in list[0]:
                target = list[0].split(',', 1)
            elif '，' in list[0]:
                target = list[0].split('，', 1)
            else:
                raise Exception
            target = [None if x == '*' else x for x in target]
            await Msg_Transmitter.set_Msg(target[0], list[1], target[1])
            await bot.send(event, f'已向{target}投放消息: {list[1]}')
            await super_admin_record(f'{qq}向{target}投放消息: {list[1]}')
        except:
            await bot.send(event, '处理错误')


class OpenToSeeYou(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if not self.is_super_admin(qq):
            return
        target = msg.replace('/dbinfo ', '', 1)
        result = await info_qq(target)
        if result is None:
            await bot.send(event, f'{target}不存在')
            raise StopPropagation
        reply = f"查询信息如下\nQQ:{result['QQ']}\nalias:{
            result['alias']}\nextra:{result['extra']}\nlove:{result['love']}"
        if result['pic']:
            await bot.send(event, f'{reply}')
            message = Message()
            message += MessageSegment.text(f'{target}设置了图片')
            message += MessageSegment.image(f'base64://{result['pic']}')
            await bot.send(event, message)
        else:
            await bot.send(event, f'{reply}\npic:未设置')
        logger.debug('查询数据库')
        await super_admin_record(f'{qq}查询了{target}的数据')


class ForgetYou(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        await clear_memory(qq)
        await bot.send(event, '刚刚我们说什么了喵~')
        logger.debug(f'{qq}记忆清除')


class SetSenior(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if qq == master:
            msg = msg.replace('/set senior ', '')
            await admin_group.write_admin(groupid, 'high', msg, db_path)
            await bot.send(event, '成功设置高管喵~')
            logger.debug('设置'+msg+'为'+groupid+'高管')


class SetAdmin(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if self.is_group_admin(qq, groupid) == 'high':
            msg = msg.replace('/set admin ', '')
            await admin_group.write_admin(groupid, 'common', msg, db_path)
            await bot.send(event, '成功设置管理喵~')
            logger.debug('设置'+msg+'为'+groupid+'管理')


class DelSenior(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if qq == master:
            msg = msg.replace('/del senior ', '')
            await admin_group.del_admin_high(groupid, msg)
            await bot.send(event, '成功取消高管喵~')
            logger.debug('取消'+msg+'为'+groupid+'高管')


class DelReply(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if self.is_group_admin(qq, groupid):
            if msg == '/删除':
                await bot.send(event, '未找到目标喵~')
                return
            question = msg.replace('/删除 ', '', 1)
            await group_del(groupid, question)
            await bot.send(event, '成功删除回复喵~')


class SetExactReply(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if self.is_group_admin(qq, groupid):
            msg = msg.replace('/精确问 ', '', 1)
            check = sensitive_word(msg)
            if check:
                logger.debug(f'由于 {check} 添加被拒绝')
                await bot.send(event, '添加被拒绝喵~')
                return
            msg = msg.split(' ', 1)
            try:
                question = msg[0]
                answer = msg[1]
                if (not answer and not image) or not question:
                    raise IndexError
            except IndexError:
                await bot.send(event, '格式错误喵~ 指令格式为 /精确问 [问题] [回答]')
                raise StopPropagation
            if image:
                await bot.send(event, '\n出于安全性考虑,暂不支持添加图片,如有需要,请联系开发者手动添加喵~')
                return
                path = check_group_folder(groupid)
                filename = str(time.time() * 1000)
                await download(image, filename=f'{path}{filename}.jpeg')
                add = find_images(path, filename)
                answer = f'{answer}[pic={add}]'
            await group_write(groupid, question, answer, '1')
            await bot.send(event, '成功设置回复喵~')
            logger.debug('写入新回复')


class SetFuzzyReply(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if self.is_group_admin(qq, groupid):
            msg = msg.replace('/模糊问 ', '', 1)
            check = sensitive_word(msg)
            if check:
                await bot.send(event, '添加被拒绝喵~')
                logger.debug(f'由于 {check} 添加被拒绝')
                return
            msg = msg.split(' ', 1)
            try:
                question = msg[0]
                answer = msg[1]
                if (not answer and not image) or not question:
                    raise IndexError
            except IndexError:
                await bot.send(event, '格式错误喵~ 指令格式为 /模糊问 [问题] [回答]')
                raise StopPropagation
            if image:
                await bot.send(event, '\n出于安全性考虑,暂不支持添加图片,如有需要,请联系开发者手动添加喵~')
                return
                path = check_group_folder(groupid)
                filename = str(time.time() * 1000)
                await download(image, filename=f'{path}{filename}.jpeg')
                add = find_images(path, filename)
                answer = f'{answer}[pic={add}]'
            await group_write(groupid, question, answer, '2')
            await bot.send(event, '成功设置回复喵~')
            logger.debug('写入新回复')


class DelAdmin(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if self.is_group_admin(qq, groupid) == 'high':
            msg = msg.replace('/del admin ', '')
            await admin_group.del_admin(groupid, msg)
            await bot.send(event, '成功取消管理喵~')
            logger.debug('取消'+msg+'为'+groupid+'管理')


class DelRowReply(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if self.is_group_admin(qq, groupid):
            msg = msg.replace('/dr ', '', 1)
            msg = msg.split(' ')
            try:
                msg = [int(s) for s in msg]
                success, fail = await del_row(groupid, msg)
                if success == 0 and fail == 0:
                    raise Exception
                msg = '成功删除'+str(success)+'行，删除失败(由于锁定)'+str(fail)+'行喵~'
                await bot.send(event, msg)
            except:
                await bot.send(event, '删除指定行失败喵~')


class FindReply(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if self.is_group_admin(qq, groupid):
            query = msg.replace('/查询 ', '', 1)

            answers = find_row(groupid, query)

            if not answers:
                await bot.send(event, f'未查询到{query}的相关回复喵~')
                return

            reply_message = f'查询到{query}有以下回复喵:\n'
            for answer in answers:
                reply_message += f'{answer}\n'

            await bot.send(event, reply_message + '请使用/dr指令删除指定行喵~')


class LockReply(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if self.is_group_admin(qq, groupid) == 'high':
            msg = msg.replace('/lock ', '', 1)
            msg = msg.split(' ')
            try:
                await lock_row(groupid, msg, 0)
                await bot.send(event, '锁定成功喵~')
            except:
                await bot.send(event, '输入不合法喵~行号可通过 /查询 指令获取喵~')


class UnLockReply(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if self.is_group_admin(qq, groupid) == 'high':
            msg = msg.replace('/unlock ', '', 1)
            msg = msg.split(' ')
            try:
                await lock_row(groupid, msg, 1)
                await bot.send(event, '解锁成功喵~')
            except:
                await bot.send(event, '输入不合法喵~行号可通过 /查询 指令获取喵~')


class InfoReply(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if self.is_group_admin(qq, groupid) == 'high':
            msg = msg.replace('/info ', '')
            try:
                msg = int(msg)
                data = load_info(groupid, msg)
                if data == None:
                    raise Exception
                else:
                    reply = f"""触发词: {data[0]}\n回复: {data[1]}\n好感增减范围: {data[2]}\n好感触发: {
                        data[3]}\n类型: {data[4]}(1=精确, 2=模糊)\n状态: {data[5]}"""
                await bot.send(event, reply)
            except:
                await bot.send(event, '输入不合法喵~行号可通过 /查询 指令获取喵~')


class LoveMyRank(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        name = await replace_qq(qq)
        _ = await read_love(qq)
        rank, total = await get_loverank(qq)
        await bot.send(event, f'\n{name}的好感排名为[{rank}/{total}]')
        logger.debug('完成个人排名')


class BaseLoveRank(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def get_qq_list(self, groupid: str) -> list:
        raise NotImplementedError

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], **kwargs: Any) -> None:
        # 获取全局的好感度列表
        qq_list = await self.get_qq_list(groupid)
        if not qq_list:
            await bot.send(event, '当前没有可用的好感度数据喵~')
            return

        # 并发获取每个成员的好感度信息
        tasks = [get_both_love(mid) for mid in qq_list]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 构建包含 id 的完整结果
        full_results = [(mid, *res) for mid, res in zip(qq_list, results)]

        # 替换 QQ 为昵称
        replace_tasks = [replace_qq(mid) for mid, _, _ in full_results]
        replaced_ids = await asyncio.gather(*replace_tasks)

        # 格式化输出
        formatted_list = []
        for i, (_, _, str_value) in enumerate(full_results):
            name = replaced_ids[i] if isinstance(
                replaced_ids[i], str) else f"QQ {qq_list[i]}"
            if isinstance(str_value, Exception):
                logger.error(f"处理QQ {qq_list[i]} 的好感度信息时出错: {str_value}")
                formatted_list.append(f"{name}: 无法获取好感度信息")
            else:
                formatted_list.append(f"{name}: {str_value}")

        # 拼接成最终的消息
        reply_message = f"\n好♡感♡排♡行\n{
            '\n'.join(formatted_list)}\n--------\n喵呜~~~"
        await bot.send(event, reply_message)


class LoveGroupRank(BaseLoveRank):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def get_qq_list(self, groupid: str) -> list:
        return await groupmember.get_top_users_by_groupid(groupid)


class LoveRank(BaseLoveRank):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def get_qq_list(self, groupid: str) -> list:
        return await global_compare()


class LoveLowRank(BaseLoveRank):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def get_qq_list(self, groupid: str) -> list:
        return await get_low_ten_qqs()


class CodeHandler(Handler):
    def __init__(self, block: bool = True, code_type: str = ''):
        super().__init__(block)
        self.code_type = code_type

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], **kwargs: Any) -> None:
        # 移除命令前缀
        msg = msg.replace(f'/code {self.code_type} ', '')

        # 检查code是否正确
        b = await check_code(msg, self.code_type, qq)
        if not b:
            await bot.send(event, '无效的code喵~')
            return

        logger.debug('code正确')
        await code_record(qq + f'使用{msg}作为{self.code_type}')

        # 发送提示消息
        prompt_message = self.get_prompt_message()
        await bot.send(event, prompt_message)

        # 等待用户输入
        user_input = await self.wait_for_user_input(bot, event, timeout=120)
        if not user_input:
            await bot.send(event, f'{self.code_type}设置超时,code已经自动返还')
            return

        # 处理敏感词
        sen = sensitive_word(user_input)
        if sen is not None:
            sen = sen.replace('.txt', '')
            await bot.send(event, f'你说啊,{qq},在网上搞这些真的有意思吗\n原因:{sen}\n本次code不会被返还喵~\n莫  谈  国  事')
            return

        # 减少code计数
        count = await decrement_count(msg, self.code_type)

        # 设置别名、好感后缀或图片
        success_message = await self.set_value(qq, user_input)
        if count != -1:
            await bot.send(event, f'{success_message}\n当前code还可用{count}次')
        else:
            await bot.send(event, f'{success_message}\n当前code不再可用')

    def get_prompt_message(self) -> str:
        raise NotImplementedError

    async def wait_for_user_input(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], timeout: int) -> Optional[str]:
        raise NotImplementedError

    async def set_value(self, qq: str, value: str) -> str:
        raise NotImplementedError


class CodeAlias(CodeHandler):
    def __init__(self, block: bool = True):
        super().__init__(block, code_type='alias')

    def get_prompt_message(self) -> str:
        return '\n请在120s内发送您要设置的QQ别名喵~\n请以/开头喵~\n不允许为纯数字'

    async def wait_for_user_input(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], timeout: int) -> Optional[str]:
        @waiter(waits=["message"], keep_session=True, rule=rule)
        async def get_alias(event: Union[GroupMessageEvent, PrivateMessageEvent]):
            msg = event.get_plaintext()
            if msg.startswith(' '):
                msg = msg.replace(' ', '', 1)
            if msg.startswith('/'):
                msg = msg.replace('/', '', 1)
                try:
                    int(msg.replace(' ', ''))
                except ValueError:
                    return msg
        return await get_alias.wait(timeout=timeout, default=None)

    async def set_value(self, qq: str, value: str) -> str:
        await update_alias(qq, value)
        return f'您的QQ别名已设置为: {value} 喵~'


class EnCode(Handler):
    def __init__(self, block: bool = True) -> None:
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], **kwargs: Any) -> None:
        if not (qq == master and self.is_PrivateMessageEvent(event)):
            return

        if msg.startswith('/encode alias '):
            await self.encode_command(bot, event, msg, 0, 'alias')
        elif msg.startswith('/encode love '):
            await self.encode_command(bot, event, msg, 1, 'love')
        elif msg.startswith('/encode pic '):
            await self.encode_command(bot, event, msg, 2, 'pic')

    async def encode_command(self, bot: Bot, event: PrivateMessageEvent, msg: str, b: int, log_prefix: str):
        msg = msg.replace(f'/encode {log_prefix} ', '', 1)
        await bot.send(event, '确认无误请回复"确认"')
        logger.debug(f'{log_prefix}生成中')

        # 等待用户回复
        @waiter(waits=["message"], keep_session=True, rule=rule)
        async def get_reply(event: PrivateMessageEvent):
            """等待指定用户回复"""
            return event.get_plaintext()

        new_msg = await get_reply.wait(timeout=120, default=None)
        if new_msg == '确认':
            try:
                msg = int(msg)
                await generate_codes(msg, b)
                await bot.send(event, '生成完毕')
                logger.debug(f'{log_prefix}生成完毕')
            except Exception as e:
                logger.debug(e)
                await bot.send(event, '数值不合法')
                logger.debug(f'{log_prefix}生成失败')
        else:
            await bot.send(event, '已取消code生成')
            logger.debug(f'{log_prefix}取消生成')


class CodeLove(CodeHandler):
    def __init__(self, block: bool = True):
        super().__init__(block, code_type='love')

    def get_prompt_message(self) -> str:
        return '\n请在120s内发送您要设置的好感后缀喵~\n请以/开头喵~\n不允许为纯数字'

    async def wait_for_user_input(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], timeout: int) -> Optional[str]:
        @waiter(waits=["message"], keep_session=True, rule=rule)
        async def get_extra(event: Union[GroupMessageEvent, PrivateMessageEvent]):
            msg = event.get_plaintext().replace('/', '', 1)
            if msg.startswith(' '):
                msg = msg.replace(' ', '', 1)
            return msg
        return await get_extra.wait(timeout=timeout, default=None)

    async def set_value(self, qq: str, value: str) -> str:
        await write_str_love(qq, value)
        return f'您的好感后缀已设置为: {value} 喵~'


class CodePic(CodeHandler):
    def __init__(self, block: bool = True):
        super().__init__(block, code_type='pic')

    def get_prompt_message(self) -> str:
        return '\n请在120s内发送您要设置的图片喵~'

    async def wait_for_user_input(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], timeout: int) -> Optional[str]:
        @waiter(waits=["message"], keep_session=True, rule=rule)
        async def get_pic(event: Union[GroupMessageEvent, PrivateMessageEvent]):
            row_message = event.get_message()
            for seg in row_message:
                if seg.type == 'image':
                    return seg.data.get('url')
        return await get_pic.wait(timeout=timeout, default=None)

    async def set_value(self, qq: str, value: str) -> str:
        await write_pic(qq, value)
        return f'您的背景已设置喵~\n审核完成后将自动启用新背景'


class WhitelistBlacklistHandler(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if not self.is_super_admin(qq):
            await bot.send(event, '权限不足喵~')
            return

        match = re.match(r'/(add|del)\s*(white|black)\s*([gu])(\d+)', msg)
        if not match:
            await bot.send(event, '指令格式错误喵~')
            return

        action, list_type, target_type, target = match.groups()
        target_type = 'groupid' if target_type == 'g' else 'userid'
        list_type = 'whitelist' if list_type == 'white' else 'blacklist'

        try:
            int(target)
        except ValueError:
            await bot.send(event, '数值不合法,操作错误')
            return

        if action == 'add':
            result = await self.add_to_list(list_type, target_type, target, qq)
        elif action == 'del':
            result = await self.remove_from_list(list_type, target_type, target, qq)

        await bot.send(event, f'{result[0]}')

    async def add_to_list(self, list_type: str, target_type: str, target: str, operator: str) -> tuple:
        if list_type == 'whitelist':
            result = await black_white_list.add_to_whitelist(target_type, target)
            await super_admin_record(f'{operator}将 {target} 添加为{target_type}白名单')
            logger.debug(f'{target} 添加为{target_type}白名单')
        elif list_type == 'blacklist':
            result = await black_white_list.add_to_blacklist(target_type, target)
            await super_admin_record(f'{operator}将 {target} 添加为{target_type}黑名单')
            logger.debug(f'{target} 添加为{target_type}黑名单')
        return result

    async def remove_from_list(self, list_type: str, target_type: str, target: str, operator: str) -> tuple:
        if list_type == 'whitelist':
            result = await black_white_list.remove_from_whitelist(target_type, target)
            await super_admin_record(f'{operator}将 {target} 移除{target_type}白名单')
            logger.debug(f'{target} 移除{target_type}白名单')
        elif list_type == 'blacklist':
            result = await black_white_list.remove_from_blacklist(target_type, target)
            await super_admin_record(f'{operator}将 {target} 移除{target_type}黑名单')
            logger.debug(f'{target} 移除{target_type}黑名单')
        return result


class LoveMy(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        int_love, str_love = await get_both_love(qq)

        name = str(event.sender.nickname)
        lv = get_range(int_love)

        # 定义不同好感等级的回复模板
        reply_templates = {
            1: lv1_reply,
            2: lv2_reply,
            3: lv3_reply,
            4: lv4_reply,
            5: lv5_reply,
        }

        # 处理图片回复
        if lv_enable:
            pre_pic = await read_pic(qq)
            if pre_pic:
                url = event.avatar
                pic = await pic_reply(qq, pre_pic, name, url)
                message = MessageSegment.image(f"base64://{pic}")
                await bot.send(event, message)
            else:
                reply_template = reply_templates.get(lv, None)
                if reply_template:
                    reply = await self.format_reply(
                        reply_template, name, int_love, str_love, bot_name, qq)
                    await bot.send(event, '\n' + reply)
                else:
                    logger.warning('好感等级未能覆盖所有用户')
                    if int_love <= La:
                        await bot.send(event, f'{bot_name}不想理你\n{str_love}')
                    else:
                        await bot.send(event, f'{bot_name}很中意你\n{str_love}')
        else:
            await bot.send(event, f'你的好感度是：\n{str_love}\n————————\n(ˉ▽￣～) 切~~')

    async def format_reply(self, template: str, name: str, int_love: int, str_love: str, bot_name: str, qq: str) -> str:
        """格式化回复模板"""
        name = await replace_qq(qq)
        reply = template.replace('[qq]', qq).replace('[sender]', name).replace(
            '[intlove]', str(int_love)).replace('[love]', str_love).replace('[bot]', bot_name)
        return reply

    async def remove_from_list(self, list_type: str, target_type: str, target: str, operator: str) -> tuple:
        if list_type == 'whitelist':
            result = await black_white_list.remove_from_whitelist(target_type, target)
            await super_admin_record(f'{operator}将 {target} 移除{target_type}白名单')
            logger.debug(f'{target} 移除{target_type}白名单')
        elif list_type == 'blacklist':
            result = await black_white_list.remove_from_blacklist(target_type, target)
            await super_admin_record(f'{operator}将 {target} 移除{target_type}黑名单')
            logger.debug(f'{target} 移除{target_type}黑名单')
        return result


class DraftInfo(Handler):
    def __init__(self, block: bool = True):
        super().__init__(block)

    async def handle(self, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], msg: str, qq: str, groupid: str, image: Optional[str], ** kwargs: Any) -> None:
        if not self.is_super_admin(qq):
            return
        msg = msg.replace('/boinfo ', '', 1)
        if not msg:
            await bot.send(event, '请给出要检查的漂流瓶编号喵~')
            return
        try:
            bottle = await Draft.get_bottle_by_id_bo(msg)
            if bottle:
                boid = bottle['id']
                userid = bottle['userid']
                bomessage = bottle['message']
                timestamp = bottle['timestamp']
                likes = bottle['likes']
                dislikes = bottle['dislikes']
                image = bottle['image_base64']
                block = bottle['blocked']
                draw_count = bottle['draw_count']
                last_drawn = bottle['last_drawn']
                real_groupid = bottle['groupid']
                if block:
                    block = 'True'
                else:
                    block = 'False'
                reply = f"""\n编号{boid}\nuserid: {userid}\n来源群: {real_groupid}\n发布时间: {timestamp}\n最近展示时间: {last_drawn}\n展示总数: {
                    draw_count}\n是否被屏蔽: {block}\n{likes}😆            {dislikes}🤢\n{bomessage}"""
                if image:
                    message = Message()
                    message += MessageSegment.text(f'{reply}')
                    message += MessageSegment.image(f'base64://{image}')
                    await bot.send(event, message)
                else:
                    await bot.send(event, f'{reply}')
            else:
                await bot.send(event, '查阅失败,可能该漂流瓶不存在喵~')
            logger.debug(f'{qq}查看了{msg}')
            await super_admin_record(f'{qq}查看了{msg}')
        except Exception as e:
            logger.warning(e)
            await bot.send(event, '查阅失败,可能该漂流瓶不存在喵~')


class PrivateVars(TypedDict):
    private_var_for_func1: str
    private_var_for_func2: str
    private_var_for_func3: str


class MessageHandlerManager:
    def __init__(self):
        self.handlers_in_list: Dict[Set[str], List[Handler]] = {}
        self.handlers_startswith: Dict[str, List[Handler]] = {}
        self.handlers_equals: Dict[str, List[Handler]] = {}

    def add_handler_in_list(self, key_set: Set[str], handlers: List[Handler]):
        """添加列表指令"""
        if key_set not in self.handlers_in_list:
            self.handlers_in_list[key_set] = []
        self.handlers_in_list[key_set].extend(handlers)

    def add_handler_startswith(self, prefix: str, handlers: List[Handler]):
        """添加开头指令"""
        if prefix not in self.handlers_startswith:
            self.handlers_startswith[prefix] = []
        self.handlers_startswith[prefix].extend(handlers)

    def add_handler_equals(self, key: str, handlers: List[Handler]):
        """添加精准指令"""
        if key not in self.handlers_equals:
            self.handlers_equals[key] = []
        self.handlers_equals[key].extend(handlers)

    def dispatch(self, message: str, bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], image: Optional[str], private_vars: Union[Dict[str, Any], None] = None) -> None:
        """消息派发,执行对应逻辑

        Args:
            message (str): 消息(纯文本)
            bot (Bot): Bot对象
            event (Union[Union[GroupMessageEvent,PrivateMessageEvent],PrivateMessageEvent]): 消息事件.私信消息groupid按照-1处理
            image (Optional[str]): 图片url.仅支持单张图片
            private_vars (Union[Dict[str, Any], None], optional): 可选的附加参数,需与匹配类适配

        Raises:
            StopPropagation: 阻断事件传播
        """
        try:
            groupid = str(event.group_id)
        except AttributeError:
            groupid = '-1'
        # 检查字符串是否在集合中
        for key_set, handler_list in self.handlers_in_list.items():
            if message in key_set:
                for handler in handler_list:
                    asyncio.create_task(handler.handle(msg=message, image=image, qq=str(event.user_id), groupid=groupid,
                                                       bot=bot, event=event, **(private_vars or {})))
                    if handler.block:
                        raise StopPropagation

        # 检查字符串是否以某个前缀开始
        for prefix, handler_list in self.handlers_startswith.items():
            if message.startswith(prefix):
                for handler in handler_list:
                    asyncio.create_task(handler.handle(msg=message, image=image, qq=str(event.user_id), groupid=groupid,
                                                       bot=bot, event=event, **(private_vars or {})))
                    if handler.block:
                        raise StopPropagation

        # 检查字符串是否等于某个特定值
        for key, handler_list in self.handlers_equals.items():
            if message == key:
                for handler in handler_list:
                    asyncio.create_task(handler.handle(msg=message, image=image, qq=str(event.user_id), groupid=groupid,
                                                       bot=bot, event=event, **(private_vars or {})))
                    if handler.block:
                        raise StopPropagation


def init_msg():
    in_list = [
        (frozenset(['/我的id ', '/我的ID ', '/我的id', '/我的ID']), [GetUserID()]),
        (frozenset(['/本群id ', '/本群ID ', '/本群id', '/本群ID']), [GetGroupID()]),
        (frozenset(["/随机东方", "/随机东方 "]), [DFpic()]),
        (frozenset(["/捞漂流瓶 ", "/捞漂流瓶"]), [DraftGetter()]),
        (frozenset(['/Gtype ', '/Gtype']), [DraftType()]),
        (frozenset(['/clean', '/clean ']), [DraftClean()]),
        (frozenset(['/Gtypelist ', '/Gtypelist']), [DraftTypeList()]),
        (frozenset(['/签到 ', '/签到']), [DailySign()]),
        (frozenset(['/获得别名 ', '/获得别名']), [GetAlias()]),
        (frozenset(['/show ', '/show']), [ShowYou()]),
        (frozenset(['/clear ', '/clear']), [ForgetYou()]),
        (frozenset(['/我的好感度 ', '/我的好感 ', '/我的好感', '/我的好感度']),
         [LoveMy()]),
        (frozenset(['/我的排名 ', '/我的排名']), [LoveMyRank()]),
        (frozenset(['/好感排行 ', '/好感排行']), [LoveRank()]),
        (frozenset(['/好人榜', '/好人榜 ']), [LoveLowRank()]),
        (frozenset(['/本群好感排行 ', '/本群好感排行']),
         [LoveGroupRank()]),
        (frozenset(['/web', '/web ']), [GetWebCode()]),
        (frozenset(['/nf', '/nf ']), [BF_showQueen()])
    ]
    a_startswitch = [
        ('/扔漂流瓶', [DraftThrow()]),
        ('/bo开盒', [DraftSeeSee()]),
        ('/happy', [DraftHappy()]),
        ('/shit', [DraftShit()]),
        ('/block', [DraftBlock()]),
        ('/unblock', [DraftUnBlock()]),
        ('/boinfo', [DraftInfo()]),
        ('/ChangeGtype', [DraftChangeType()]),
        ('/cl ', [LoveChange()]),
        ('/悄悄话', [TellYou()]),
        ('/绑定', [BindYou()]),
        ('/开盒 ', [OpenYou()]),
        ('/kill ', [KillYou()]),
        ('/Msg', [MsgYou()]),
        ('/dbinfo ', [OpenToSeeYou()]),
        ('/set senior ', [SetSenior()]),
        ('/set admin ', [SetAdmin()]),
        ('/del senior ', [DelSenior()]),
        ('/del admin ', [DelAdmin()]),
        ('/删除', [DelReply()]),
        ('/精确问', [SetExactReply()]),
        ('/模糊问', [SetFuzzyReply()]),
        ('/查询', [FindReply()]),
        ('/add white', [WhitelistBlacklistHandler()]),
        ('/del white', [WhitelistBlacklistHandler()]),
        ('/add black', [WhitelistBlacklistHandler()]),
        ('/del black', [WhitelistBlacklistHandler()]),
        ('/dr ', [DelRowReply()]),
        ('/lock ', [LockReply()]),
        ('/unlock ', [UnLockReply()]),
        ('/info ', [InfoReply()]),
        ('/code alias ', [CodeAlias()]),
        ('/code love ', [CodeLove()]),
        ('/code pic ', [CodePic()]),
        ('/code ', [GetCode()]),
        ('/sa ', [SuperAdminCommandHandler()]),
        ('/addnf ', [BF_addQueen()]),
        ('/delnf ', [BF_removeQueen()]),
        ('/encode ', [EnCode()])
    ]

    equals = []
    msg_checker = MessageHandlerManager()
    for commands, handlers in in_list:
        msg_checker.add_handler_in_list(commands, handlers)
    for command, handlers in a_startswitch:
        msg_checker.add_handler_startswith(command, handlers)
    for command, handlers in equals:
        msg_checker.add_handler_equals(command, handlers)
    return msg_checker
