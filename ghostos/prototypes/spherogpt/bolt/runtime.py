from abc import ABC, abstractmethod
from typing import Optional, Self
from ghostos.entity import ModelEntity
from spherov2.sphero_edu import SpheroEduAPI
from pydantic import BaseModel, Field

_STOPPED = bool


class BoltBallMovement(BaseModel, ABC):
    desc: str = Field("", description="description of the command")
    stop_at_first: bool = Field(default=False, description="stop the world at first")

    @abstractmethod
    def start(self, api: SpheroEduAPI) -> None:
        pass

    @abstractmethod
    def run_frame(self, api: SpheroEduAPI, passed: float) -> _STOPPED:
        pass

    def succeed_log(self, passed: float) -> str:
        if not self.desc:
            return ""
        return f"done `{self.desc}` after {round(passed, 4)} seconds"

    def interrupt_log(self, reason: str, passed: float) -> str:
        return f"interrupt `{self.desc}` running because `{reason}` after {round(passed, 4)} seconds"

    @abstractmethod
    def on_event(self, event_type: str) -> Optional[Self]:
        pass


class BoltLedMatrixAnimation(ModelEntity, ABC):

    @abstractmethod
    def start(self, api: SpheroEduAPI) -> None:
        pass


class SpheroBoltRuntime(ABC):

    @abstractmethod
    def get_task_id(self) -> str:
        pass

    @abstractmethod
    def add_movement(self, command: BoltBallMovement):
        pass

    @abstractmethod
    def set_charging_callback(self, event: str):
        pass

    @abstractmethod
    def set_off_charging_callback(self, event: str):
        pass

    @abstractmethod
    def add_animation(self, command: BoltLedMatrixAnimation):
        pass

    @abstractmethod
    def bootstrap(self):
        pass

    @abstractmethod
    def close(self):
        pass
