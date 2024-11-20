from typing import Optional, List, Iterable, Dict, Any, Self
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from ghostos.core.messages import Message, copy_messages, Role
from ghostos.core.moss.pycontext import PyContext
from ghostos.core.llms import Prompt
from ghostos.core.runtime.events import Event, EventTypes
from ghostos.helpers import uuid, timestamp
from contextlib import contextmanager

__all__ = [
    'GoThreads', 'GoThreadInfo', 'Turn',
    'thread_to_prompt',
]


class Turn(BaseModel):
    """
    single turn in the thread
    """
    turn_id: str = Field(
        default_factory=uuid,
        description="id of the turn"
    )
    event: Optional[Event] = Field(
        default=None,
        description="event of the turn"
    )
    added: List[Message] = Field(
        default_factory=list,
        description="The new messages that generated by ghost during this turn of chat or thinking."
                    "Shall append to messages after updating.",
    )
    pycontext: PyContext = Field(
        default_factory=PyContext,
        description="The PyContext instance",
    )
    created: int = Field(
        default_factory=timestamp,
    )
    extra: Dict[str, Any] = Field(default_factory=dict, description="extra information")

    @classmethod
    def new(
            cls,
            event: Optional[Event],
            *,
            turn_id: Optional[str] = None,
            pycontext: Optional[PyContext] = None,
    ) -> "Turn":
        data = {"event": event}
        if turn_id is None and event is not None:
            turn_id = event.event_id
        if turn_id:
            data["turn_id"] = turn_id
        if pycontext is not None:
            data["pycontext"] = pycontext
        return cls(**data)

    def append(self, *messages: Message, pycontext: Optional[PyContext] = None) -> None:
        self.added.extend(messages)
        if pycontext is not None:
            self.pycontext = pycontext

    def event_messages(self, show_instruction: bool = False) -> Iterable[Message]:
        if not self.event:
            return []
        yield from self.iter_event_message(self.event, show_instruction)

    @staticmethod
    def iter_event_message(event: Event, show_instruction: bool = True) -> Iterable[Message]:
        yield from event.iter_message(show_instruction)

    def messages(self) -> Iterable[Message]:
        yield from self.event_messages()
        if self.added:
            yield from self.added

    def is_empty(self) -> bool:
        return (self.event is None or self.event.is_empty()) and not self.added

    def is_from_client(self) -> bool:
        return self.event is not None and self.event.from_task_id is None


class GoThreadInfo(BaseModel):
    """
    对话历史.
    存储时应该使用别的数据结构.
    """
    id: str = Field(
        default_factory=uuid,
        description="The id of the thread, also a fork id",
    )

    extra: Dict[str, Any] = Field(
        default_factory=dict,
        description="extra information",
    )

    root_id: Optional[str] = Field(
        default=None,
        description="The id of the root thread if the thread is a fork",
    )
    parent_id: Optional[str] = Field(
        default=None,
        description="The id of the parent thread if the thread is a fork",
    )
    on_created: Turn = Field(
        default_factory=Turn,
        description="the turn that thread was created",
    )
    history: List[Turn] = Field(
        default_factory=list,
        description="the history turns"
    )
    current: Optional[Turn] = Field(
        default=None,
        description="the current turn",
    )

    @classmethod
    def new(
            cls,
            event: Optional[Event],
            *,
            pycontext: Optional[PyContext] = None,
            thread_id: Optional[str] = None,
            root_id: Optional[str] = None,
            parent_id: Optional[str] = None,
    ) -> "GoThreadInfo":
        """
        初始化一个 Thread.
        :param event: 首轮输入的信息.
        :param pycontext: 初始化时的 pycontext.
        :param thread_id: 指定的 thread id.
        :param root_id: 指定的 root id.
        :param parent_id: 任务的 parent id.
        :return:
        """

        data = {
            "on_created": Turn.new(event=event, turn_id=thread_id, pycontext=pycontext),
        }
        if thread_id is not None:
            data["thread_id"] = thread_id
        if root_id is not None:
            data["root_id"] = root_id
        if parent_id is not None:
            data["parent_id"] = parent_id
        return GoThreadInfo(**data)

    def last_turn(self) -> Turn:
        """
        返回历史最后一个回合的数据.
        """
        if self.current is not None:
            return self.current
        if len(self.history) > 0:
            return self.history[-1]
        return self.on_created

    def get_history_messages(self) -> Iterable[Message]:
        """
        返回所有的历史消息.
        """
        yield from self.on_created.messages()
        if self.history:
            for turn in self.history:
                yield from turn.messages()

    def get_pycontext(self) -> PyContext:
        """
        返回最后一轮的 pycontext.
        """
        return self.last_turn().pycontext

    def update_pycontext(self, pycontext: PyContext) -> None:
        if self.current is None:
            self.new_turn(None)
        self.current.pycontext = pycontext

    def get_updated_copy(self) -> "GoThreadInfo":
        """
        更新 thread 的 current turn 到 history turns.
        :return:
        """
        if self.current is None:
            return self
        copied = self.model_copy(deep=True)
        if copied.current is not None:
            copied.history.append(copied.current)
            copied.current = None
        return copied

    def turns(self) -> Iterable[Turn]:
        """
        遍历所有的 turns.
        """
        yield self.on_created
        if self.history:
            for turn in self.history:
                yield turn
        if self.current is not None:
            yield self.current

    def new_turn(
            self,
            event: Optional[Event],
            *,
            turn_id: Optional[str] = None,
            pycontext: Optional[PyContext] = None,
    ) -> None:
        """
        新建一个 turn 到 current turn.
        :param event: 用事件来创建回合.
        :param turn_id:
        :param pycontext:
        """
        if self.current is not None:
            self.history.append(self.current)
            self.current = None
        if pycontext is None:
            last_turn = self.last_turn()
            pycontext = last_turn.pycontext
        if turn_id is None and event is not None:
            turn_id = event.event_id
        new_turn = Turn.new(event=event, turn_id=turn_id, pycontext=pycontext)
        self.current = new_turn

    def append(self, *messages: Message, pycontext: Optional[PyContext] = None) -> None:
        """
        添加新的消息体.
        :param messages:
        :param pycontext:
        :return:
        """
        if self.current is None:
            self.new_turn(None)
        if messages or pycontext:
            self.current.append(*messages, pycontext=pycontext)

    def get_added(self) -> List[Message]:
        if self.current is None:
            return []
        return self.current.added

    def get_current_event(self) -> Optional[Event]:
        if self.current is None:
            return None
        return self.current.event

    def fork(self, tid: Optional[str] = None) -> "GoThreadInfo":
        tid = tid if tid else uuid()
        root_id = self.root_id if self.root_id else self.id
        parent_id = self.id
        thread = self.model_copy(update=dict(id=tid, root_id=root_id, parent_id=parent_id), deep=True)
        return thread

    def reset_history(self, messages: Iterable[Message]) -> Self:
        forked = self.fork()
        forked.history = []
        forked.current = None
        on_created = Turn.new(event=None)
        on_created.append(*messages)
        forked.on_created = on_created
        return forked

    def thread_copy(self, update: Optional[dict] = None) -> "GoThreadInfo":
        return self.model_copy(update=update, deep=True)

    def to_prompt(self, system: List[Message], stages: Optional[List[str]] = None) -> Prompt:
        turn_id = self.last_turn().turn_id
        history = list(self.get_history_messages())
        inputs = []
        appending = []
        current_turn = self.current
        if current_turn is not None:
            inputs = list(current_turn.event_messages(show_instruction=True))
            appending = current_turn.added

        prompt = Prompt(
            description=f"created from thread {self.id} turn {turn_id}",
            system=system,
            history=copy_messages(history, stages),
            inputs=copy_messages(inputs, stages),
            added=copy_messages(appending, stages),
        )
        return prompt


def thread_to_prompt(
        prompt_id: str,
        system: List[Message],
        thread: GoThreadInfo,
        stages: Optional[List[str]] = None
) -> Prompt:
    """
    将 thread 转换成基准的 chat.
    """
    if stages is None:
        stages = [""]
    history = list(thread.get_history_messages())
    inputs = []
    appending = []
    current_turn = thread.current
    if current_turn is not None:
        inputs = list(current_turn.event_messages())
        appending = current_turn.added

    prompt = Prompt(
        id=prompt_id,
        system=system,
        history=copy_messages(history, stages),
        inputs=copy_messages(inputs, stages),
        added=copy_messages(appending, stages),
    )
    return prompt


class GoThreads(ABC):
    """
    the repository to save and load threads
    """

    @abstractmethod
    def get_thread(self, thread_id: str, create: bool = False) -> Optional[GoThreadInfo]:
        """
        获取一个 Thread 实例. 如果不存在的话, 返回 None.
        :param thread_id: thread_id
        :param create: 如果
        :return:
        """
        pass

    @abstractmethod
    def save_thread(self, thread: GoThreadInfo) -> None:
        pass

    @abstractmethod
    def fork_thread(self, thread: GoThreadInfo) -> GoThreadInfo:
        pass

    @contextmanager
    def transaction(self):
        yield
