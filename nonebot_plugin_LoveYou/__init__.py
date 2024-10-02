import os   # noqa
from nonebot import logger   # noqa
DATA_DIR = os.path.join(os.path.dirname(__file__), 'LoveYou_data')  # noqa
logger.info(f'LoveYou数据目录{DATA_DIR}')   # noqa
from .message_handler import start_bot, init_msg
from .love_manager import db_path, update_love, get_both_love, get_range, generate_codes, read_five_codes, read_love
from .AI_chat import qingyunke, baidu_ai,  love_score, new_msg_judge
from .others import image_to_base64
from .wordbank import get_global_reply, groups_reply, pic_support, RL_support
import snownlp
import re
from typing import Union
import asyncio
from .perm import super_admin_action
from .sensitive_test import sensitive_word
from nonebot import on_message, on_notice, get_driver
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent, Message, MessageSegment
from nonebot.rule import is_type
from nonebot.adapters.onebot.v11 import GroupIncreaseNoticeEvent
from nonebot_plugin_waiter import waiter
from .config import result
from nonebot.exception import StopPropagation


(
    bot_name, baseline, rate, master,
    search_love_reply, botreact, model, role,
    API_Key, Secret_Key, tank_enable, Ca, Cb,
    lv_enable, La, Lb, Lc, Ld,
    Le, Lf, Lg, Lh, Li, Lj,
    lv1_reply, lv2_reply, lv3_reply, lv4_reply, lv5_reply, memory
) = result
driver = get_driver()


@driver.on_startup
async def start():
    await start_bot()
    global Draft, black_white_list, admin_group, groupmember, app, Msg_Transmitter, msg_checker
    msg_checker = init_msg()
    from .message_handler import Draft, black_white_list, admin_group, groupmember, app, Msg_Transmitter


rule = is_type(PrivateMessageEvent, GroupMessageEvent)
notice_rule = is_type(GroupIncreaseNoticeEvent)
# 标记isAchieve，检查黑白名单，进行消息传递
pre_process = on_message(rule=rule, priority=1, block=False)
first_process = on_message(rule=rule, priority=2, block=False)  # 主功能
second_process = on_message(rule=rule, priority=3, block=False)  # 词库
third_process = on_message(rule=rule, priority=4, block=False)  # AI对话

friend_process = on_message(rule=rule, priority=2, block=False)

join_group = on_notice(rule=notice_rule, priority=4, block=False)  # 群绑定

Audit_mode = False


@join_group.handle()
async def join_new_group(bot: Bot, event: GroupIncreaseNoticeEvent):
    if Audit_mode:
        return
    admin_qq = str(event.user_id)
    groupid = str(event.group_id)
    logger.info(f'bot被拉入新群聊.邀请人{admin_qq}  群聊{groupid}')
    await asyncio.sleep(5)
    await bot.send_group_msg(group_id=groupid, message='群友们好喵~\n原来是你把我拉进来的呢\n你可以在180s内@我并发送指令\n/群绑定 [群号]\n注意:绑定结果不可修改,会影响bot功能,请务必认真绑定喵~')

    @waiter(waits=["message"], keep_session=True, rule=rule)
    async def get_reply(new_event: GroupMessageEvent):
        """等待指定用户回复"""
        msg = new_event.get_plaintext()
        if msg.startswith(' '):
            msg = msg.replace(' ', '', 1)
        if msg.startswith('/群绑定 ') and msg.replace('/群绑定 ', '', 1).isdigit():
            return msg.replace('/群绑定 ', '', 1), new_event
        elif msg == '/群绑定':
            await bot.send(new_event, '格式错误喵~\n正确格式: /群绑定 [群号]')
    real_id, new_event = await get_reply.wait(timeout=180, default=None)
    if real_id:
        exist_id = Draft.set_real_group(groupid, real_id)
        if exist_id:
            await bot.send(event, f'本群已经绑定为{exist_id}\n如有修改需求,请联系开发者')
            raise StopPropagation
        else:
            await black_white_list.add_to_whitelist('groupid', groupid)
            await admin_group.write_admin(groupid, 'high', admin_qq, db_path)
            await bot.send(new_event, f'\n本群成功绑定为 {real_id} 并被添加入白名单\n你已经被设置为本群bot高管喵~\n想要成为超管?使用/悄悄话 记得附上你的QQ喵~')
            raise StopPropagation


@pre_process.handle()
async def pre_stage(bot: Bot, event: GroupMessageEvent):
    qq = str(event.user_id)
    groupid = str(event.group_id)
    asyncio.create_task(
        groupmember.create_and_insert_if_not_exists(groupid, qq))
    reply = await Msg_Transmitter.get_Msg(
        qq, groupid)
    if reply:
        await bot.send(event, f'\n主人有话给您:\n{reply}')
    group_type = await black_white_list.check_in_list('groupid', groupid)
    qq_type = await black_white_list.check_in_list('userid', qq)
    if (group_type == 'blacklist' or qq_type == 'blacklist') and (qq != master and qq not in super_admins and not qq_type == 'whitelist'):
        logger.debug(f'{qq} 尝试在 {groupid} 与bot互动,由于黑名单被阻止')
        raise StopPropagation


@first_process.handle()
async def main_function(bot: Bot, event: GroupMessageEvent):
    msg = event.get_plaintext()
    row_message = event.get_message()

    image = None
    for seg in row_message:
        if seg.type == 'image':
            image = seg.data.get('url')
            break
    if msg.startswith(' '):
        msg = msg.replace(' ', '', 1)
    msg_checker.dispatch(message=msg, bot=bot, event=event, image=image)


@friend_process.handle()
async def fdsacfvsgv(bot: Bot, event: PrivateMessageEvent):
    qq = str(event.user_id)
    msg = event.get_plaintext()
    row_message = event.get_message()

    image = None
    for seg in row_message:
        if seg.type == 'image':
            image = seg.data.get('url')
            break
    if msg.startswith(' '):
        msg = msg.replace(' ', '', 1)
    msg_checker.dispatch(message=msg, bot=bot, event=event, image=image)
    global super_admins
    if qq == master and msg.startswith('/code '):

        msg = msg.replace('/code ', '', 1)
        tells = await read_five_codes(msg)
        message = f'适用于{msg}的密码'
        formatted_message = '\n'.join([message] + tells)
        await bot.send(event, formatted_message)

    elif msg == '/我的ID' or msg == '/我的ID ':

        await bot.send(event, f'你的ID是{qq}')

    elif msg.startswith('/sa add ') and qq == master:

        target = msg.replace('/sa add ', '', 1)
        super_admins = await super_admin_action(target, 'add')
        await bot.send(event, f'已尝试注册{target}为超管')

    elif msg.startswith('/sa del ') and qq == master:

        target = msg.replace('/sa del ', '', 1)
        super_admins = await super_admin_action(target, 'remove')
        await bot.send(event, f'已尝试取消{target}为超管')

    elif msg == '/审核模式' and qq == master:

        global Audit_mode
        if Audit_mode:
            Audit_mode = False
            logger.warning('审核模式关闭')
            await bot.send(event, '审核模式关闭')
        else:
            Audit_mode = True
            logger.warning('审核模式开启')
            await bot.send(event, '审核模式开启')
    elif qq == master and msg.startswith('/encode alias '):
        msg = msg.replace('/encode alias ', '')
        b = int(0)
        await bot.send(event, '确认无误请回复"确认"')
        logger.debug('alias_code生成中')

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
                logger.debug('alias_code生成完毕')
            except Exception as e:
                logger.debug(e)
                await bot.send(event, '数值不合法')
                logger.debug('alias_code生成失败')
        else:
            await bot.send(event, '已取消code生成')
            logger.debug('alias_code取消生成')
    elif qq == master and msg.startswith('/encode love '):
        msg = msg.replace('/encode love ', '')
        b = int(1)
        await bot.send(event, '确认无误请回复"确认"')
        logger.debug('love_code生成中')

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
                logger.debug('love_code生成完毕')
            except:
                await bot.send(event, '数值不合法')
                logger.debug('love_code生成失败')
        else:
            await bot.send(event, '已取消code生成')
            logger.debug('love_code取消生成')
    elif qq == master and msg.startswith('/encode pic '):
        msg = msg.replace('/encode pic ', '')
        b = int(2)
        await bot.send(event, '确认无误请回复"确认"')
        logger.debug('pic_code生成中')

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
                logger.debug('pic_code生成完毕')
            except:
                await bot.send(event, '数值不合法')
                logger.debug('pic_code生成失败')
        else:
            await bot.send(event, '已取消code生成')
            logger.debug('pic_code取消生成')
    elif msg == '/web' and (qq == master or qq in super_admins):

        code = app.generate_webcode()
        await bot.send(event, f'请在30s内使用秘钥\n{code}')


@second_process.handle()  # 词库功能实现
async def word_bank(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    async def handle_reply(event, message, reply, love, qq, name, int_love, str_love, groupid=None):
        reply = str(reply)

        if reply.startswith('RL'):
            reply, love = RL_support(reply)

        def sentiment_check(
            s: snownlp.SnowNLP): return s.sentiments <= 0.75 if '[pos]' in reply else s.sentiments >= 0.25 if '[nag]' in reply else False

        if sentiment_check(snownlp.SnowNLP(message)):
            return

        reply = process_message(
            reply, qq, name, int_love, str_love, love, bot_name)

        if '[cut]' in reply:
            await send_cut_messages(event, reply, groupid)
        else:
            await send_message(event, reply, groupid)

        if love and love != 'None':
            await update_love(qq, love)

    def process_message(reply: str, qq: str, name: str, int_love: int | str, str_love: str, love: int | str, bot_name: str):
        replacements = {
            '[qq]': qq,
            '[sender]': name,
            '[intlove]': str(int_love),
            '[love]': str_love,
            '[bot]': bot_name,
            '[vary]': str(love),
            '\\n': '\n'
        }
        for k, v in replacements.items():
            reply = reply.replace(k, v)
        return reply.replace('[pos]', '').replace('[nag]', '')

    async def send_cut_messages(event, reply: str, groupid):
        for segment in reply.split('[cut]'):
            segment, pic = pic_support(segment)
            if pic:
                path = os.path.join(DATA_DIR, 'pic', f"{groupid}" if groupid else "", pic)  # noqa
                message = Message()
                message += MessageSegment.text(segment)
                pic = image_to_base64(path)
                message += MessageSegment.image(f"base64://{pic}")
                await bot.send(event, message)
            else:
                await bot.send(event, segment)
            await asyncio.sleep(1.5)

    async def send_message(event, reply: str, groupid):
        reply, pic = pic_support(reply)
        if pic:
            path = os.path.join(DATA_DIR, 'pic', f"{groupid}" if groupid else "", pic)   # noqa
            message = Message()
            message += MessageSegment.text(reply)
            pic = image_to_base64(path)
            message += MessageSegment.image(f"base64://{pic}")
            await bot.send(event, message)
        else:
            await bot.send(event, reply)

    try:
        groupid = str(event.group_id)
    except AttributeError:
        groupid = '-1'
    message = event.get_plaintext()
    if message.startswith(' '):
        message = message.replace(' ', '', 1)

    if Audit_mode:
        group_type = await black_white_list.check_in_list('groupid', groupid)
        if group_type != 'whitelist':
            await bot.send(event, '你的消息已被记录喵~使用 我的好感 查看好感度')
            raise StopPropagation

    qq = str(event.user_id)

    int_love, str_love = await get_both_love(qq)
    name = event.sender.nickname
    message = message.replace(bot_name, '[bot]').replace('\n', '\\n')

    global_reply = get_global_reply(message, int_love)
    if global_reply == (None, None):
        global_reply = None
    reply, love = global_reply or (groups_reply(groupid, message, int_love))
    groupid = None if global_reply is not None else groupid

    if not reply:
        return

    try:
        await handle_reply(event, message, reply, love, qq, name, int_love, str_love, groupid)
        raise StopPropagation
    except StopPropagation:
        raise
    except Exception as e:
        logger.warning(e)


@third_process.handle()
async def AI_chatting(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    try:
        groupid = str(event.group_id)
    except AttributeError:
        groupid = '-1'
    group_type = await black_white_list.check_in_list('groupid', groupid)
    if (Audit_mode and group_type != 'whitelist'):
        raise StopPropagation
    message = event.get_plaintext()
    row_message = event.get_message()
    image = None
    for seg in row_message:
        if seg.type == 'image':
            image = seg.data.get('url')
            break
    if message.startswith(' '):
        message = message.replace(' ', '', 1)
    qq = str(event.user_id)

    def del_face(text: str) -> str:
        face_del = r'\{face:\d+\}'
        result = re.sub(face_del, '', text)
        return result
    if image or message.startswith(' /') or message.startswith('/') or message == ' 确认' or message == ' 确认 ':
        return
    if not message:
        return None
    check = sensitive_word(message)
    if check:

        return
    reply = None
    name = str(event.sender.nickname)
    if memory != False:
        intlove = await read_love(qq)
    else:
        intlove = 0
    if message:
        s = snownlp.SnowNLP(message)
        sentiment_score = float(s.sentiments)
        a = new_msg_judge(message)
        if sentiment_score <= 0.1 or model == 'qingyunke':
            message = message.replace(bot_name, '菲菲')
            reply = await qingyunke(message)
        else:
            lv = get_range(intlove)
            if lv == None and intlove > 0:
                lv = 5
            elif lv == None and intlove <= 0:
                lv = 1
            reply = await baidu_ai(message, qq, intlove, name, lv)
        message = message.replace('菲菲', '')
        love = love_score(message)
        if love != 0 and a == True:
            await update_love(qq, love)
            logger.debug(qq+'情感运算'+str(love))
        elif a == False:
            await update_love(qq, -abs(love))
            logger.debug('重复消息')
        if reply != None:
            reply = str(reply)
            reply = reply.replace('菲菲', bot_name)
            reply = del_face(reply)
            await bot.send(event, reply)
        raise StopPropagation
