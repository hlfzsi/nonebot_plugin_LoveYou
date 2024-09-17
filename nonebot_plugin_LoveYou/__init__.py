import os   # noqa
from nonebot import logger   # noqa
DATA_DIR = os.path.join(os.path.dirname(__file__), 'LoveYou_data')  # noqa
logger.info(f'LoveYou数据目录{DATA_DIR}')   # noqa
from .love_manager import db_path, update_love, update_alias, read_alias, get_both_love, read_pic, find_qq_by_alias, start_db, del_qq_record, info_qq, read_love, get_loverank, get_range, replace_qq, read_five_codes, generate_codes, check_code, decrement_count, write_str_love, write_pic, global_compare, get_low_ten_qqs, get_real_id, update_real_id
from .AI_chat import qingyunke, baidu_ai, clear_memory, love_score, new_msg_judge
from .others import DailyCacheDecorator, tell_record, read_five_tells, code_record, check_images_similarity, download, check_group_folder, image_to_base64
from .draftbottles import DriftBottle, start_server, init_app
from .wordbank import group_del, group_write, lock_row, load_info, find_row, del_row, get_global_reply, groups_reply, pic_support, RL_support, init_wordbank
from .tank import hidden_pic
import snownlp
from threading import Thread
import re
import asyncio
import random
import glob
import time
from .pic_gen import pic_reply
from .perm import AdminManager, MsgManager, super_admin_record, BlackWhiteList, super_admin_action
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


def mark_achieve():
    '''用于标记已经处理的事件'''
    global isAchieve
    isAchieve = True


@driver.on_startup
async def start():
    global Draft, admin_group, Msg_Transmitter, daily_decorator, black_white_list, super_admins, app
    Draft = DriftBottle()
    admin_group = AdminManager()
    Msg_Transmitter = MsgManager()
    daily_decorator = DailyCacheDecorator()
    black_white_list = BlackWhiteList()
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


rule = is_type(PrivateMessageEvent, GroupMessageEvent)
notice_rule = is_type(GroupIncreaseNoticeEvent)
# 标记isAchieve，检查黑白名单，进行消息传递
pre_process = on_message(rule=rule, priority=1, block=False)
first_process = on_message(rule=rule, priority=2, block=False)  # 主功能
second_process = on_message(rule=rule, priority=3, block=False)  # 词库
third_process = on_message(rule=rule, priority=4, block=False)  # AI对话

friend_process = on_message(rule=rule, priority=1, block=False)

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
    await bot.send_group_msg(group_id=groupid, message='\n群友们好喵~\n原来是你把我拉进来的呢\n你可以在180s内@我并发送指令\n/群绑定 [群号]\n注意:绑定结果不可修改,会影响bot功能,请务必认真绑定喵~')

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
            black_white_list.add_to_whitelist('groupid', groupid)
            admin_group.write_admin(groupid, 'high', admin_qq, db_path)
            await bot.send(new_event, f'\n本群成功绑定为 {real_id} 并被添加入白名单\n你已经被设置为本群bot高管喵~\n想要成为超管?使用/悄悄话 记得附上你的QQ喵~')
            raise StopPropagation


@pre_process.handle()
async def pre_stage(bot: Bot, event: GroupMessageEvent):
    qq = str(event.user_id)
    groupid = str(event.group_id)
    reply = await Msg_Transmitter.get_Msg(
        qq, groupid)
    if reply:
        await bot.send(event, f'\n主人有话给您:\n{reply}')
    group_type = await black_white_list.check_in_list('groupid', groupid)
    qq_type = await black_white_list.check_in_list('userid', qq)
    if (group_type == 'blacklist' or qq_type == 'blacklist') and (qq != master and qq not in super_admins and not qq_type == 'whitelist'):
        logger.debug(f'{qq} 尝试在 {groupid} 与bot互动,由于黑名单被阻止')
        raise StopPropagation
    else:
        global isAchieve
        isAchieve = False


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
    groupid = str(event.group_id)
    qq = str(event.user_id)
    admin_lv = admin_group.check_admin(groupid, qq)

    def find_images(path, filename):
        image_formats = ['*.jpeg', '*.jpg', '*.png']
        for format_ in image_formats:
            files = glob.glob(os.path.join(path, filename + format_))
            if files:
                return os.path.basename(files[0])
        return None

    if msg == '/我的id ' or msg == '/我的ID ' or msg == '/我的id' or msg == '/我的ID':
        await bot.send(event, f'你的ID是{qq}')
        logger.debug('ID查询')
        mark_achieve()

    elif msg == '/本群id ' or msg == '/本群ID ' or msg == '/本群id' or msg == '/本群ID':
        await bot.send(event, f'本群ID是{groupid}')
        logger.debug('群ID查询')
        mark_achieve()

    elif msg.startswith('/扔漂流瓶 ') or msg == '/扔漂流瓶':
        if msg == '/扔漂流瓶':
            msg = '/扔漂流瓶 '
        mark_achieve()
        msg = msg.replace('[图片]', '').replace('/扔漂流瓶 ', '', 1)
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
            bottleid = Draft.insert_bottle(qq, msg, groupid, image)
        except ValueError:
            await bot.send(event, f'\n你发送的图片过大,无法上传。漂流瓶被{bot_name}吃了喵~')
            raise StopPropagation
        await bot.send(event, f'\n你的漂流瓶已经被投入这汪洋大海~\n它的编号是{bottleid}')
        logger.debug('扔出漂流瓶')

    elif msg.startswith('/bo开盒 ') and (qq == master or qq in super_admins):
        mark_achieve()
        msg = msg.replace('/bo开盒 ', '', 1)
        ids = Draft.get_bottle_ids_by_userid(msg)
        if not ids:
            await bot.send(event, f'\n{msg}没有任何漂流瓶记录')
            return
        ids = '\n'.join(ids)
        await bot.send(event, f'\n{msg}有以下漂流瓶记录,可使用/boinfo查询\n{ids}')
        await super_admin_record(f'{qq}查询了{msg}的漂流瓶记录')

    elif msg == '/捞漂流瓶 ' or msg == '/捞漂流瓶':
        mark_achieve()
        try:
            bottle = Draft.get_bottle(groupid)
            if bottle:
                boid = bottle['id']
                bomessage: str = bottle['message']
                bomessage = Draft.msg_process(bomessage, qq, groupid)
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

    elif msg == '/Gtype ' or msg == '/Gtype':
        mark_achieve()
        type = Draft.get_types_for_groupid(groupid)
        await bot.send(event, f'本群漂流瓶类型为 {type}')
        logger.debug('查询漂流瓶群聊类型')

    elif msg.startswith('/happy ') or msg == '/happy':
        if msg == '/happy':
            msg = '/happy '
        mark_achieve()
        msg = msg.replace('/happy ', '', 1)
        if not msg:
            await bot.send(event, '请给出要点赞的漂流瓶编号喵~')
            return
        success = Draft.like_bottle(qq, msg)
        if success:
            await update_love(qq, -2)
            await bot.send(event, '成功点赞喵~')
            logger.debug('点赞成功')
        else:
            await bot.send(event, '点赞失败,可能已经为该漂流瓶点过 赞/踩 喵~')
            logger.debug('点赞失败')

    elif msg.startswith('/shit ') or msg == '/shit':
        if msg == '/shit':
            msg = '/shit '
        mark_achieve()
        msg = msg.replace('/shit ', '', 1)
        if not msg:
            await bot.send(event, '请给出要点踩的漂流瓶编号喵~')
            return
        success = Draft.dislike_bottle(qq, msg)
        if success:
            await bot.send(event, '成功点踩喵~')
            logger.debug('点踩成功')
        else:
            await bot.send(event, '点踩失败,可能已经为该漂流瓶点过 赞/踩 喵~')
            logger.debug('点踩失败')

    elif (msg == '/clean' or msg == '/clean ') and (qq == master or qq in super_admins):
        mark_achieve()
        try:
            Draft.clean_old_bottles()
            await bot.send(event, '成功结算漂流瓶好感度奖励')
        except:
            await bot.send(event, '处理错误')
            return
        await super_admin_record(f'{qq}执行了漂流瓶结算')
        logger.info('漂流瓶结算')

    elif msg.startswith('/block ') and (qq == master or qq in super_admins or admin_lv != False):
        mark_achieve()
        msg = msg.replace('/block ', '', 1)
        if not msg:
            await bot.send(event, '请给出要屏蔽的漂流瓶编号喵~')
            return
        try:
            Draft.block_bottle(msg)
            await bot.send(event, '成功屏蔽喵~')
            logger.debug(f'{qq}屏蔽了{msg}')
        except:
            await bot.send(event, '屏蔽失败,可能该漂流瓶不存在喵~')

    elif msg.startswith('/unblock ') and (qq == master or qq in super_admins):
        mark_achieve()
        msg = msg.replace('/unblock ', '', 1)
        if not msg:
            await bot.send(event, '请给出要屏蔽的漂流瓶编号喵~')
            return
        try:
            Draft.unblock_bottle(msg)
            await bot.send(event, '成功解除屏蔽喵~')
            logger.debug(f'{qq}解除屏蔽了{msg}')
            await super_admin_record(f'{qq}解除了{msg}的屏蔽')
        except:
            await bot.send(event, '解除屏蔽失败,可能该漂流瓶不存在喵~')

    elif msg.startswith('/boinfo ') and (qq == master or qq in super_admins):
        mark_achieve()
        msg = msg.replace('/boinfo ', '', 1)
        if not msg:
            await bot.send(event, '请给出要检查的漂流瓶编号喵~')
            return
        try:
            bottle = Draft.get_bottle_by_id(msg)
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

    elif msg == '/Gtypelist ' or msg == '/Gtypelist' and (qq == master or qq in super_admins or admin_lv != False):
        mark_achieve()
        list = Draft.list_types()
        reply = "\n".join(f"{key}：{value}" for key, value in list)
        await bot.send(event, f'\n各群聊类型如下\n{reply}')

    elif msg.startswith('/ChangeGtype ') and (qq == master or qq in super_admins or admin_lv != False):
        mark_achieve()
        msg = msg.replace('/ChangeGtype ', '', 1)
        check = sensitive_word(msg)
        if check:
            await bot.send(event, f'你发送的类型因为 {check} 被{bot_name}吃掉了')
            return
        list = msg.split(' ')
        if not list:
            await bot.send(event, '你没有指定类型喵~')
            return
        Draft.modify_type(groupid, list)
        await bot.send(event, '本群漂流瓶类型修改完成了喵~')
        logger.debug(f'{groupid}修改漂流瓶类型为{list}')

    elif msg.startswith('/cl ') and qq == master:
        mark_achieve()
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

    elif msg == '/签到' or msg == '/签到 ':
        mark_achieve()

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

    elif msg == '/获得别名 ' or msg == '/获得别名':
        mark_achieve()
        logger.debug(f'{qq}尝试获得别名')
        name = await read_alias(qq)
        if name != '':
            await bot.send(event, f'\n你已经拥有别名 {name} 了喵~')
        else:
            await bot.send(event, '\n请在120s内发送您要设置的QQ别名喵~\n请以/开头\n不允许为纯数字')

            @waiter(waits=["message"], keep_session=True, rule=rule)
            async def get_alias(event: GroupMessageEvent):
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
                raise StopPropagation
            sen = sensitive_word(msg)
            if sen is None:
                await update_alias(qq, msg)
                await bot.send(event, '您的QQ别名已设置为:'+msg+' 喵~')
            else:
                sen = sen.replace('.txt', '')
                await bot.send(event, f'你说啊,{qq},在网上搞这些真的有意思吗\n原因:{sen}\n莫  谈  国  事')

    elif msg.startswith('/悄悄话'):
        mark_achieve()
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

    elif (msg == '/show' or msg == '/show ') and (qq == master or qq in super_admins):
        mark_achieve()
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

    elif msg.startswith('/绑定 ') or msg == '/绑定':
        if msg == '/绑定':
            msg = '/绑定 '
        real_qq = msg.replace('/绑定 ', '', 1)
        mark_achieve()
        if not real_qq:
            await bot.send(event, '请输入QQ号喵~')
            raise StopPropagation
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

    elif msg.startswith('/showpic ') and (qq == master or qq in super_admins):
        mark_achieve()
        msg = msg.replace('/showpic ', '', 1)
        pic = await read_pic(msg, True)
        if pic == '':
            await bot.send(event, f'{msg}没有设置图片')
        else:
            message = Message()
            message += MessageSegment.text(f'{msg}设置图片')
            message += MessageSegment.image(f'base64://{pic}')
            await bot.send(event, message)
            await super_admin_record(f'{qq}查阅了{msg}的图片信息')

    elif msg.startswith('/开盒 ') and (qq == master or qq in super_admins):
        mark_achieve()
        target_alias = msg.replace('/开盒 ', '', 1)
        await bot.send(event, "\n如无补充信息,请回复任意信息\n如有补充,在120秒内按照 [参数]=[数值] 格式补充\n以','分隔参数")
        await super_admin_record(f'{qq}定向查询了{target_alias}的数据')
        logger.debug(f'尝试匹配{target_alias}')

        @waiter(waits=["message"], keep_session=True, rule=rule)
        async def get_reply(event2: GroupMessageEvent):
            """等待指定用户回复"""
            return event2.get_plaintext()
        new_msg = await get_reply.wait(timeout=120, default=None)

        try:
            items = new_msg.split(',')
            search_dict = {item.split('=')[0].strip(): item.split('=')[
                1] for item in items}

            result = await find_qq_by_alias(target_alias, search_dict)
        except IndexError:
            result = await find_qq_by_alias(target_alias)
        except Exception as e:
            logger.warning(e)
            await bot.send(event, '处理错误,请检查输入格式')
            raise StopPropagation
        reply = '\n'.join(result)
        await bot.send(event, f'\n可能的结果如下:\n{reply}')

    elif msg.startswith('/kill ') and (qq == master or qq in super_admins):
        mark_achieve()
        msg = msg.replace('/kill ', '', 1)
        target = msg.split(' ')[0]
        if target in super_admins or target == master:
            await super_admin_record(f'{qq}尝试违规删除{target}的记录')
            await bot.send(event, '警告！禁止的行为')
            raise StopPropagation
        msg = msg.replace(f'{target} ', '').replace(target, '')
        list = msg.split(' ')
        result = await del_qq_record(target, list)
        if result:
            await super_admin_record(f'{qq}删除了{target}的{list}记录')
            await bot.send(event, f'已成功删除{target}的数据喵~')
            logger.debug(f'{target}的记录被删除')
        else:
            await bot.send(event, f'{target}的数据不存在喵~')

    elif msg.startswith('/Msg ') and (qq == master or qq in super_admins):
        mark_achieve()
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

    elif msg.startswith('/dbinfo ') and (qq == master or qq in super_admins):
        mark_achieve()
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

    elif (msg == '/clear ' or msg == '/clear') and botreact == 'True':
        await clear_memory(qq)
        await bot.send(event, '刚刚我们说什么了喵~')
        mark_achieve()
        logger.debug(f'{qq}记忆清除')
    elif msg.startswith('/set senior '):
        if qq == master:
            msg = msg.replace('/set senior ', '')
            await admin_group.write_admin(groupid, 'high', msg, db_path)
            await bot.send(event, '成功设置高管喵~')
            logger.debug('设置'+msg+'为'+groupid+'高管')
            mark_achieve()
    elif msg.startswith('/set admin '):
        if qq == master or admin_lv == 'high':
            msg = msg.replace('/set admin ', '')
            await admin_group.write_admin(groupid, 'common', msg, db_path)
            await bot.send(event, '成功设置管理喵~')
            logger.debug('设置'+msg+'为'+groupid+'管理')
            mark_achieve()
    elif msg.startswith('/del admin '):
        if qq == master or admin_lv == 'high':
            msg = msg.replace('/del admin ', '')
            await admin_group.del_admin(groupid, msg)
            await bot.send(event, '成功取消管理喵~')
            logger.debug('取消'+msg+'为'+groupid+'管理')
            mark_achieve()
    elif msg.startswith('/del senior '):
        if qq == master:
            msg = msg.replace('/del senior ', '')
            await admin_group.del_admin_high(groupid, msg)
            await bot.send(event, '成功取消高管喵~')
            logger.debug('取消'+msg+'为'+groupid+'高管')
            mark_achieve()
    elif msg.startswith('/删除 '):
        if qq == master or admin_lv != False:
            question = msg.replace('/删除 ', '')
            await group_del(groupid, question)
            await bot.send(event, '成功删除回复喵~')
            mark_achieve()
    elif msg.startswith('/精确问 '):
        if qq == master or admin_lv != False:
            msg = msg.replace('/精确问 ', '')
            check = sensitive_word(msg)
            if check:
                logger.debug(f'由于 {check} 添加被拒绝')
                await bot.send(event, '添加被拒绝喵~')
                mark_achieve()
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
                path = check_group_folder(groupid)
                filename = str(time.time() * 1000)
                await download(image, filename=f'{path}{filename}.jpeg')
                add = find_images(path, filename)
                answer = f'{answer}[pic={add}]'
            await group_write(groupid, question, answer, '1')
            await bot.send(event, '成功设置回复喵~')
            logger.debug('写入新回复')
            mark_achieve()
    elif msg.startswith('/模糊问 '):
        if qq == master or admin_lv != False:
            msg = msg.replace('/模糊问 ', '')
            check = sensitive_word(msg)
            if check:
                await bot.send(event, '添加被拒绝喵~')
                logger.debug(f'由于 {check} 添加被拒绝')
                mark_achieve()
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
                path = check_group_folder(groupid)
                filename = str(time.time() * 1000)
                await download(image, filename=f'{path}{filename}.jpeg')
                add = find_images(path, filename)
                answer = f'{answer}[pic={add}]'
            await group_write(groupid, question, answer, '2')
            await bot.send(event, '成功设置回复喵~')
            logger.debug('写入新回复')
            mark_achieve()
    elif msg.startswith('/查询 '):
        if qq == master or admin_lv != False:
            msg = msg.replace('/查询 ', '')
            answers = find_row(groupid, msg)
            global reply_answer
            reply_answer = '查询到'+msg+'有以下回复喵:\n'
            for answer in answers:
                reply_answer = reply_answer+answer+'\n'
            await bot.send(event, reply_answer+'请使用/dr指令删除指定行喵~')
            del reply_answer
            mark_achieve()
    elif msg.startswith('/dr '):
        if qq == master or admin_lv != False:
            msg = msg.replace('/dr ', '')
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
            finally:
                mark_achieve()
    elif msg.startswith('/lock '):
        if qq == master or admin_lv == 'high':
            msg = msg.replace('/lock ', '')
            msg = msg.split(' ')
            try:
                await lock_row(groupid, msg, 0)
                await bot.send(event, '锁定成功喵~')
            except:
                await bot.send(event, '输入不合法喵~行号可通过 查询 指令获取喵~')
            finally:
                mark_achieve()
    elif msg.startswith('/unlock '):
        if qq == master or admin_lv == 'high':
            msg = msg.replace('/unlock ', '')
            msg = msg.split(' ')
            try:
                await lock_row(groupid, msg, 1)
                await bot.send(event, '解锁成功喵~')
            except:
                await bot.send(event, '输入不合法喵~行号可通过 查询 指令获取喵~')
            finally:
                mark_achieve()
    elif msg.startswith('/info '):
        if qq == master or admin_lv != False:
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
                await bot.send(event, '输入不合法喵~行号可通过 查询 指令获取喵~')
            finally:
                mark_achieve()

    elif msg.startswith('/add gwhite ') and (qq == master or qq in super_admins):
        mark_achieve()
        target = msg.replace('/add gwhite ', '', 1)
        try:
            int(target)
        except ValueError:
            await bot.send(event, '数值不合法,添加错误')
            return
        result = await black_white_list.add_to_whitelist('groupid', target)
        await super_admin_record(f'{qq}将 {groupid} 添加为群白名单')
        logger.debug(f'{target} 添加为群白名单')
        await bot.send(event, f'{result[0]}')
    elif msg.startswith('/del gwhite ') and (qq == master or qq in super_admins):
        mark_achieve()
        target = msg.replace('/del gwhite ', '', 1)
        try:
            int(target)
        except ValueError:
            await bot.send(event, '数值不合法,移除错误')
            return
        await super_admin_record(f'{qq}将 {target} 移除群白名单')
        logger.debug(f'{target} 移除群白名单')
        result = await black_white_list.remove_from_whitelist('groupid', target)
        await bot.send(event, f'{result[0]}')

    elif msg.startswith('/add uwhite ') and (qq == master or qq in super_admins):
        mark_achieve()
        target = msg.replace('/add uwhite ', '', 1)
        try:
            int(target)
        except ValueError:
            await bot.send(event, '数值不合法,添加错误')
            return
        result = await black_white_list.add_to_whitelist('userid', target)
        await super_admin_record(f'{qq}将 {target} 添加为用户白名单')
        logger.debug(f'{target} 添加为用户白名单')
        await bot.send(event, f'{result[0]}')
    elif msg.startswith('/del uwhite ') and (qq == master or qq in super_admins):
        mark_achieve()
        target = msg.replace('/del uwhite ', '', 1)
        try:
            int(target)
        except ValueError:
            await bot.send(event, '数值不合法,移除错误')
            return
        await super_admin_record(f'{qq}将 {target} 移除用户白名单')
        logger.debug(f'{target} 移除用户白名单')
        result = await black_white_list.remove_from_whitelist('userid', target)
        await bot.send(event, f'{result[0]}')
    elif msg.startswith('/add ublack ') and (qq == master or qq in super_admins):
        mark_achieve()
        target = msg.replace('/add ublack ', '', 1)
        try:
            int(target)
        except ValueError:
            await bot.send(event, '数值不合法,添加错误')
            return
        result = await black_white_list.add_to_blacklist('userid', target)
        await super_admin_record(f'{qq}将 {target} 添加为用户黑名单')
        logger.debug(f'{target} 添加为用户黑名单')
        await bot.send(event, f'{result[0]}')
    elif msg.startswith('/del ublack ') and (qq == master or qq in super_admins):
        mark_achieve()
        target = msg.replace('/del ublack ', '', 1)
        try:
            int(target)
        except ValueError:
            await bot.send(event, '数值不合法,移除错误')
            return
        await super_admin_record(f'{qq}将 {target} 移除用户黑名单')
        logger.debug(f'{target} 移除用户黑名单')
        result = await black_white_list.remove_from_blacklist('userid', target)
        await bot.send(event, f'{result[0]}')
    elif msg in ['/我的好感度 ', '/我的好感 ', '/我的好感', '/我的好感度']:
        int_love, str_love = await get_both_love(qq)
        if str_love != '' or None:
            if lv_enable != True:
                await bot.send(event, '你的好感度是：\n'+str_love+'\n————————\n(ˉ▽￣～) 切~~')
                mark_achieve()
            elif lv_enable == True:
                name = event.sender.nickname
                name = str(name)
                lv = get_range(int_love)
                logger.debug('用户好感等级'+str(lv))
                pre_pic = await read_pic(qq)
                if pre_pic != '':
                    url = event.avatar
                    pic = await pic_reply(qq, pre_pic, name, url)
                    message = Message()
                    message += MessageSegment.image(f"base64://{pic}")
                    await bot.send(event, message)
                elif lv == 1:
                    lv1_need_reply = lv1_reply.replace('[qq]', qq).replace('[sender]', name).replace(
                        '[intlove]', str(int_love)).replace('[love]', str_love).replace('[bot]', bot_name)
                    name = await replace_qq(qq)
                    lv1_need_reply = lv1_need_reply.replace(qq, name)
                    await bot.send(event, '\n'+lv1_need_reply)
                elif lv == 2:
                    lv2_need_reply = lv2_reply.replace('[qq]', qq).replace('[sender]', name).replace(
                        '[intlove]', str(int_love)).replace('[love]', str_love).replace('[bot]', bot_name)
                    name = await replace_qq(qq)
                    lv2_need_reply = lv2_need_reply.replace(qq, name)
                    await bot.send(event,  '\n'+lv2_need_reply)
                elif lv == 3:
                    lv3_need_reply = lv3_reply.replace('[qq]', qq).replace('[sender]', name).replace(
                        '[intlove]', str(int_love)).replace('[love]', str_love).replace('[bot]', bot_name)
                    name = await replace_qq(qq)
                    lv3_need_reply = lv3_need_reply.replace(qq, name)
                    await bot.send(event, '\n'+lv3_need_reply)
                elif lv == 4:
                    lv4_need_reply = lv4_reply.replace('[qq]', qq).replace('[sender]', name).replace(
                        '[intlove]', str(int_love)).replace('[love]', str_love).replace('[bot]', bot_name)
                    name = await replace_qq(qq)
                    lv4_need_reply = lv4_need_reply.replace(qq, name)
                    await bot.send(event, '\n'+lv4_need_reply)

                elif lv == 5:
                    lv5_need_reply = lv5_reply.replace('[qq]', qq).replace('[sender]', name).replace(
                        '[intlove]', str(int_love)).replace('[love]', str_love).replace('[bot]', bot_name)
                    name = await replace_qq(qq)
                    lv5_need_reply = lv5_need_reply.replace(qq, name)
                    await bot.send(event, '\n'+lv5_need_reply)
                else:
                    logger.warning('好感等级未能覆盖所有用户')
                    if int_love <= La:
                        await bot.send(event, bot_name+'不想理你\n'+str_love)
                    else:
                        await bot.send(event, bot_name+'很中意你\n'+str_love)
                mark_achieve()
    elif msg in ['/我的排名 ', '/我的排名']:
        qq = str(event.user_id)
        name = event.sender.nickname
        _ = await read_love(qq)
        rank, total = await get_loverank(qq)
        await bot.send(event, f'\n{name}的好感排名为[{rank}/{total}]')
        logger.debug('完成个人排名')
        mark_achieve()
    elif msg.startswith('/code alias '):
        mark_achieve()
        msg = msg.replace(' /code alias ', '')
        b = await check_code(msg, 'alias', qq)
        if b:
            logger.debug('code正确')
            await code_record(qq+f'使用{msg}作为QQ别名')
            await bot.send(event, '\n请在120s内发送您要设置的QQ别名喵~\n请以/开头喵~\n不允许为纯数字')

            @waiter(waits=["message"], keep_session=True, rule=rule)
            async def get_alias(event: GroupMessageEvent):
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
                await bot.send(event, '别名设置超时,code已经自动返还')
                raise StopPropagation
            sen = sensitive_word(msg)
            count = await decrement_count(msg, 'alias')
            if sen is None:
                await update_alias(qq, msg)
                if count != -1:
                    await bot.send(event, f'您的QQ别名已设置为: {msg} 喵~\n当前code还可用{count}次')
                else:
                    await bot.send(event, f'您的QQ别名已设置为: {msg} 喵~\n当前code不再可用')
            else:
                sen = sen.replace('.txt', '')
                await bot.send(event, f'你说啊,{qq},在网上搞这些真的有意思吗\n原因:{sen}\n本次code不会被返还喵~\n莫  谈  国  事')
    elif msg.startswith('/code love '):
        mark_achieve()
        msg = msg.replace(' /code love ', '')
        b = await check_code(msg, 'love', qq)
        if b:
            logger.debug('code正确')
            await code_record(qq+f'使用{msg}作为好感后缀')
            await bot.send(event, '\n请在120s内发送您要设置的好感后缀喵~\n请以/开头喵~\n不允许为纯数字')

            @waiter(waits=["message"], keep_session=True, rule=rule)
            async def get_extra(event: GroupMessageEvent):
                """等待指定用户回复来获得后缀"""
                msg = event.get_plaintext().replace('/', '', 1)
                if msg.startswith(' '):
                    msg = msg.replace(' ', '', 1)
                return msg
            msg = await get_extra.wait(timeout=120, default=False)
            if not msg:
                await bot.send(event, '好感后缀设置超时,code已经自动返还')
                raise StopPropagation
            sen = sensitive_word(msg)
            count = await decrement_count(msg, 'love')
            if sen is None:
                await write_str_love(qq, msg)
                if count != -1:
                    await bot.send(event, f'您的好感后缀已设置为: {msg} 喵~\n当前code还可用{count}次')
                else:
                    await bot.send(event, f'您的好感后缀已设置为: {msg} 喵~\n当前code不再可用')
            else:
                sen = sen.replace('.txt', '')
                await bot.send(event, f'你说啊,{qq},在网上搞这些真的有意思吗\n原因:{sen}\n本次code不会被返还喵~\n莫  谈  国  事')
    elif msg.startswith('/code pic '):
        mark_achieve()
        msg = msg.replace('/code pic ', '')
        b = await check_code(msg, 'pic', qq)
        if b == True:
            logger.debug('code正确')
            await code_record(qq+'使用'+msg+'作为pic')
            await bot.send(event, '\n请在120s内发送您要设置的图片喵~')

            @waiter(waits=["message"], keep_session=True, rule=rule)
            async def get_pic(event: GroupMessageEvent):
                row_message = event.get_message()
                image = None
                for seg in row_message:
                    if seg.type == 'image':
                        image = seg.data.get('url')
                        break
                if image:
                    return image
            url = await get_pic.wait(timeout=120, default=None)
            if not url:
                await bot.send(event, '背景设置超时,code不会自动返还,请联系开发者')
                raise StopPropagation
            count = await decrement_count(msg, 'pic')
            await write_pic(qq, url)
            if count != -1:
                await bot.send(event, f'您的背景已设置喵~\n当前code还可用{count}次')
            else:
                await bot.send(event, f'您的背景已设置喵~\n当前code不再可用')
    elif msg in ['/好感排行', '/好感排行 ']:
        mark_achieve()
        qq_list = await global_compare()
        if qq_list is not None:
            formatted_list = '\n'.join(
                f"{await replace_qq(str(iq))}: {await get_both_love(iq)[1]}"
                for iq in qq_list
            )
            reply_message = f"\n好♡感♡排♡行\n{formatted_list}\n--------\n喵呜~~~"
            await bot.send(event, reply_message)
    elif msg in ['/好人榜', '/好人榜 ']:
        mark_achieve()
        qq_list = await get_low_ten_qqs()
        if qq_list is not None:
            formatted_list = '\n'.join(
                f"{await replace_qq(str(iq))}: {await get_both_love(iq)[1]}"
                for iq in qq_list
            )
            reply_message = f"\n好♡感♡排♡行\n{formatted_list}\n--------\n喵呜~~~"
            await bot.send(event, reply_message)
    elif msg in ['/本群好感排行', '/本群好感排行 ']:
        members = await bot.get_group_member_list(group_id=groupid)
        reply_a = '本群 好♡感♡排♡行\n'
        logger.debug(f'{members}')

        # 获取所有成员的 ID
        member_ids = [str(member['user_id']) for member in members]

        # 并发获取每个成员的好感度信息
        tasks = [get_both_love(mid) for mid in member_ids]
        results = await asyncio.gather(*tasks)

        # 构建包含 id 的完整结果
        full_results = [(mid, *res) for mid, res in zip(member_ids, results)]

        # 按照 int_value 降序排序
        sorted_results = sorted(full_results, key=lambda x: x[1], reverse=True)

        # 获取前 10 个结果
        top_10_results = sorted_results[:10]

        replace_tasks = [replace_qq(mid) for mid, _, _ in top_10_results]
        replaced_ids = await asyncio.gather(*replace_tasks)

        # 格式化输出
        formatted_top_10 = [
            f"{replaced_ids[i]} : {str_value}"
            for i, (_, _, str_value) in enumerate(top_10_results)
        ]

        # 构造最终回复消息
        final_reply = ''.join(formatted_top_10) + '\n--------\n喵呜~~~'
        await bot.send(event, reply_a + final_reply)

        mark_achieve()
    elif msg in ['/gtank', '/gtank ']:
        @waiter(waits=["message"], keep_session=True, rule=rule)
        async def get_pic(event: GroupMessageEvent):
            row_message = event.get_message()
            image = None
            for seg in row_message:
                if seg.type == 'image':
                    image = seg.data.get('url')
                    break
            if image:
                return image
        mark_achieve()
        if not image:
            await bot.send(event, '请在120s内发送表图喵~\n如果提示上传错误, 说明你发送的图片过大, 请减小图片体积')
            out_image = await get_pic.wait(timeout=120, default=None)
            if not out_image:
                raise StopPropagation
        else:
            out_image = image
        await bot.send(event, '请在120s内发送里图喵~')
        hidden_image = await get_pic.wait(timeout=120, default=None)
        if not hidden_image:
            raise StopPropagation
        tank = await hidden_pic(out_image, hidden_image, 0)
        logger.debug('合成幻影坦克')
        message = Message()
        message += MessageSegment.image(f"base64://{tank}")
        await bot.send(event, message)
    elif msg in ['/gcotank', '/gcotank ']:
        @waiter(waits=["message"], keep_session=True, rule=rule)
        async def get_pic(event: GroupMessageEvent):
            row_message = event.get_message()
            image = None
            for seg in row_message:
                if seg.type == 'image':
                    image = seg.data.get('url')
                    break
            if image:
                return image
        mark_achieve()
        if not image:
            await bot.send(event, '请在120s内发送表图喵~\n如果提示上传错误, 说明你发送的图片过大, 请减小图片体积')
            out_image = await get_pic.wait(timeout=120, default=None)
            if not out_image:
                raise StopPropagation
        else:
            out_image = image
        await bot.send(event, '请在120s内发送里图喵~')
        hidden_image = await get_pic.wait(timeout=120, default=None)
        if not hidden_image:
            raise StopPropagation
        tank = await hidden_pic(out_image, hidden_image, 1)
        logger.debug('合成幻影坦克')
        message = Message()
        message += MessageSegment.image(f"base64://{tank}")
        await bot.send(event, message)
    if isAchieve:
        raise StopPropagation


@friend_process.handle()
async def fdsacfvsgv(bot: Bot, event: PrivateMessageEvent):
    qq = str(event.user_id)
    msg = event.get_plaintext()
    global super_admins
    if qq == master and msg.startswith('/code '):
        mark_achieve()
        msg = msg.replace('/code ', '', 1)
        tells = await read_five_codes(msg)
        message = f'适用于{msg}的密码'
        formatted_message = '\n'.join([message] + tells)
        await bot.send(event, formatted_message)

    elif msg == '/我的ID' or msg == '/我的ID ':
        mark_achieve()
        await bot.send(event, f'你的ID是{qq}')

    elif msg.startswith('/sa add ') and qq == master:
        mark_achieve()
        target = msg.replace('/sa add ', '', 1)
        super_admins = await super_admin_action(target, 'add')
        await bot.send(event, f'已尝试注册{target}为超管')

    elif msg.startswith('/sa del ') and qq == master:
        mark_achieve()
        target = msg.replace('/sa del ', '', 1)
        super_admins = await super_admin_action(target, 'remove')
        await bot.send(event, f'已尝试取消{target}为超管')

    elif msg == '/审核模式' and qq == master:
        mark_achieve()
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
        mark_achieve()
        code = app.generate_webcode()
        await bot.send(event, f'请在30s内使用秘钥\n{code}')
    if isAchieve:
        raise StopPropagation


@second_process.handle()  # 词库功能实现
async def word_bank(bot: Bot, event: GroupMessageEvent):
    async def handle_reply(event, message, reply, love, qq, name, int_love, str_love, groupid=None):
        reply = str(reply)
        mark_achieve()

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
            time.sleep(1.5)

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

    if isAchieve:
        raise StopPropagation

    groupid = str(event.group_id)
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
    message = message.replace(qq, '[qq]').replace(name, '[sender]').replace(str(
        int_love), '[intlove]').replace(str_love, '[love]').replace(bot_name, '[bot]').replace('\n', '\\n')

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
async def AI_chatting(bot: Bot, event: GroupMessageEvent):
    groupid = str(event.group_id)
    group_type = await black_white_list.check_in_list('groupid', groupid)
    if (Audit_mode and group_type != 'whitelist') or isAchieve:
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
        mark_achieve()
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
