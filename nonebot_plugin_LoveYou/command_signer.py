import threading
from typing import Any, Optional, Union
from abc import ABC, abstractmethod, ABCMeta
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent
from nonebot import logger


class SingletonABCMeta(ABCMeta):
    _instances = {}
    _lock: threading.Lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    instance = super(SingletonABCMeta, cls).__call__(
                        *args, **kwargs)
                    cls._instances[cls] = instance
                    try:
                        handler_id = instance.handler_id
                        logger.info(f'成功注册处理ID为 {handler_id} 的实例 {instance}')
                    except AttributeError:
                        logger.info(f'成功注册处理实例 {instance}')
        return cls._instances[cls]


class BasicHandler(ABC, metaclass=SingletonABCMeta):
    """处理器基类

    - 必须实现异步方法 handle

    - 可使用的方法:
        - is_PrivateMessageEvent 判断当前消息事件是否为私聊消息
        - get_self_id 获取当前处理器实例的处理ID
        - get_handler_by_id 通过处理ID获取处理器实例
        - get_handler_id 通过处理器实例获取处理ID


    - 可重写方法 (按执行顺序排列) :
        - should_handle 异步  该处理器是否应当执行 , 必须返回bool
        - should_block 异步  该处理器是否阻断传播 , 必须返回bool
    """

    def __init__(self, block: bool = True):
        self.block = block
        self.handler_id: int = HandlerManager.get_id(self)

    @abstractmethod
    async def handle(self, bot: Bot = None, event: Union[GroupMessageEvent, PrivateMessageEvent] = None, msg: str = None, qq: str = None, groupid: str = None, image: Optional[str] = None, ** kwargs: Any) -> None:
        """处理接收到的消息。

        参数:
            bot (Bot): 机器人实例
            event (Union[GroupMessageEvent, PrivateMessageEvent]): 消息事件
            msg (str): 处理后的消息文本
            qq (str): 发送者的QQ号
            groupid (str): 群组ID（私聊时为 -1 ）
            image (Optional[str]): 图片URL（如果有,且最多一张）
            **kwargs (BasicHandler): 其他关键字参数
        """
        pass

    @staticmethod
    def is_PrivateMessageEvent(event: Union[GroupMessageEvent, PrivateMessageEvent]):
        return event.message_type == 'private'

    async def should_handle(self, ** kwargs: Any) -> bool:
        return True

    async def should_block(self, ** kwargs: Any) -> bool:
        return self.block

    def get_self_id(self) -> int:
        return self.handler_id

    @staticmethod
    def get_handler_by_id(handler_id: int) -> Optional['BasicHandler']:
        return HandlerManager.get_handler(handler_id)

    @staticmethod
    def get_handler_id(handler: 'BasicHandler') -> int:
        return HandlerManager.get_id(handler)


class HandlerManager:
    _id_to_handler: dict[int, BasicHandler] = {}
    _handler_to_id: dict[BasicHandler, int] = {}
    _next_id: int = 1
    _lock: threading.Lock = threading.Lock()

    @classmethod
    def get_id(cls, handler: BasicHandler) -> int:
        if handler in cls._handler_to_id:
            return cls._handler_to_id[handler]

        with cls._lock:
            if handler in cls._handler_to_id:
                return cls._handler_to_id[handler]

            new_id = cls._next_id
            cls._id_to_handler[new_id] = handler
            cls._handler_to_id[handler] = new_id
            cls._next_id += 1

            return new_id

    @classmethod
    def get_handler(cls, id: int) -> Optional[BasicHandler]:
        return cls._id_to_handler.get(id)

    @classmethod
    def remove_handler(cls, handler: BasicHandler) -> bool:
        with cls._lock:
            if handler in cls._handler_to_id:
                handler_id = cls._handler_to_id.pop(handler)
                del cls._id_to_handler[handler_id]
                return True
            return False


if __name__ == '__main__':
    class HandlerA(BasicHandler):
        async def handle(self, bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, msg: str, qq: str, groupid: str, image: str | None, **kwargs: Any) -> None:
            print(f'{self.handler_id} and Handler is running')

    print(HandlerA().handler_id)
    print(HandlerA().handler_id)

    print(HandlerA().handler_id)
    B = HandlerA(False)
    print(f'{BasicHandler.get_handler_by_id(1)}')
    print(B.handler_id)
    print(f'{SingletonABCMeta._instances}')
