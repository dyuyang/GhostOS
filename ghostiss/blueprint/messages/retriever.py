from typing import Optional, Iterable
from abc import ABC, abstractmethod
from ghostiss.blueprint.messages.message import Message


class Retriever(ABC):
    """
    生成一个 Retriever 对象, 可以用三种方式拉取输出消息.
    1. 先读取 header, 然后读取 msg packs
    2. 直接读取 messages, 会是 buff 后的结果.
    3. 直接读取所有的 packs, 自己拼装.
    """

    @abstractmethod
    def packs(self) -> Iterable[Message]:
        pass

    @abstractmethod
    def messages(self) -> Iterable[Message]:
        pass
