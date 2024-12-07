from typing import Literal, Optional, Callable, Self, Dict

from spherov2.commands.io import FrameRotationOptions

from ghostos.contracts.storage import FileStorage
from ghostos.contracts.workspace import Workspace
from ghostos.entity import ModelEntityMeta, from_entity_model_meta, to_entity_model_meta
from ghostos.helpers import yaml_pretty_dump
from ghostos.prompter import Prompter
from ghostos.container import Container, Provider
from pydantic import BaseModel, Field
from .shell import Ball, Move, CurveRoll
from .runtime import SpheroBoltRuntime, BoltBallMovement
from .movements import (
    GroupMovement,
    RunAPIMovement,
    CurveRollMovement,
)
import yaml

__all__ = ['SpheroBoltBallAPIProvider', 'BallApi']


class SavedMove(BaseModel):
    name: str = Field(description="move name")
    description: str = Field(description="move description")
    move_meta: ModelEntityMeta = Field(description="move meta")

    @classmethod
    def new(cls, name: str, description: str, move: BoltBallMovement) -> Self:
        return SavedMove(
            name=name,
            description=description,
            move_meta=to_entity_model_meta(move),
        )

    def get_move(self) -> BoltBallMovement:
        return from_entity_model_meta(self.move_meta)


class MovesMemoryCache(BaseModel):
    moves: Dict[str, SavedMove] = Field(default_factory=dict)

    def add_saved(self, saved: SavedMove):
        self.moves[saved.name] = saved

    @staticmethod
    def filename(unique_id: str) -> str:
        return f"{unique_id}_sphero_moves.yml"

    def to_content(self) -> str:
        return yaml_pretty_dump(self.model_dump())


class MoveAdapter(Move):

    def __init__(
            self,
            runtime: SpheroBoltRuntime,
            run_immediately: bool,
            event_desc: Optional[str] = None,
    ):
        self._runtime = runtime
        self._run_immediately = run_immediately
        self._move_added: int = 0
        self.buffer: GroupMovement = GroupMovement(desc="", event_desc=event_desc)

    def _add_move(self, movement: BoltBallMovement):
        if self._run_immediately:
            movement.stop_at_first = self._move_added == 0
            self._runtime.add_movement(movement)
        else:
            self._runtime.add_movement(movement)

        self._move_added += 1

    def roll(self, heading: int, speed: int, duration: float) -> Self:
        self._add_move(RunAPIMovement(
            desc="roll",
            method="roll",
            duration=duration,
            args=[heading, speed, duration],
        ))
        return self

    def spin(self, angle: int, duration: float) -> Self:
        self._add_move(RunAPIMovement(
            desc="spin",
            method="spin",
            duration=duration,
            args=[angle, duration],
        ))
        return self

    def set_waddle(self, waddle: bool) -> Self:
        self._add_move(RunAPIMovement(
            desc="set_waddle",
            method="set_waddle",
            duration=0.0,
            args=[waddle],
        ))
        return self

    def roll_curve(self, curve: CurveRoll) -> Self:
        self._add_move(CurveRollMovement(
            desc="roll_curve",
            curve=curve,
        ))
        return self

    def stop_roll(self, heading: int = None) -> Self:
        self._add_move(RunAPIMovement(
            desc="stop_roll",
            method="stop_roll",
            duration=0.0,
            args=[heading],
        ))
        return self

    def reset_aim(self) -> Self:
        self._add_move(RunAPIMovement(
            desc="reset_aim",
            method="reset_aim",
            duration=0.0,
            args=[],
        ))
        return self

    def set_compass_direction(self, direction: int = 0) -> Self:
        self._add_move(RunAPIMovement(
            desc="reset_aim",
            method="reset_aim",
            duration=0.0,
            args=[],
        ))
        return self

    def on_collision(self, log: str = "feeling collision", callback: Optional[Callable[[Self], None]] = None) -> None:
        self._add_event_callback("on_collision", log, callback)

    def _add_event_callback(
            self,
            event_name: str,
            log: str,
            callback: Optional[Callable[[Self], None]] = None,
    ) -> None:
        sub_move = MoveAdapter(
            runtime=self._runtime,
            run_immediately=False,
            event_desc=log,
        )
        if callback is not None:
            callback(sub_move)
        event_move = sub_move.buffer
        event_move.stop_at_first = True
        self.buffer.event_moves[event_name] = event_move

    def on_freefall(self, log: str = "feeling freefall", callback: Optional[Callable[[Self], None]] = None) -> None:
        self._add_event_callback("on_freefall", log, callback)

    def on_landing(self, log: str = "feeling landing", callback: Optional[Callable[[Self], None]] = None) -> Self:
        self._add_event_callback("on_landing", log, callback)


class BallApi(Ball, Prompter):

    def __init__(
            self,
            runtime: SpheroBoltRuntime,
            memory_cache: FileStorage,
    ):
        self._runtime = runtime
        self._memory_cache_storage = memory_cache
        self._memory_cache_file = MovesMemoryCache.filename(self._runtime.get_task_id())
        if self._memory_cache_storage.exists(self._memory_cache_file):
            content = self._memory_cache_storage.get(self._memory_cache_file)
            data = yaml.safe_load(content)
            self._memory_cache = MovesMemoryCache(**data)
        else:
            self._memory_cache = MovesMemoryCache()

    def _save_cache(self):
        content = self._memory_cache.to_content()
        self._memory_cache_storage.put(self._memory_cache_file, content.encode())

    def new_move(self, run_immediately: bool = False) -> Move:
        return MoveAdapter(self._runtime, run_immediately)

    def run(self, move: Move, stop_at_first: bool = True) -> None:
        if not isinstance(move, MoveAdapter):
            raise TypeError(f"move instance must be created by this api new_move()")
        movement = move.buffer
        movement.stop_at_first = stop_at_first
        self._runtime.add_movement(movement)

    def save_move(self, name: str, description: str, move: Move) -> None:
        if not isinstance(move, MoveAdapter):
            raise TypeError(f"move instance must be created by this api new_move()")
        saved_move = SavedMove.new(name=name, description=description, move=move.buffer)
        self._memory_cache.add_saved(saved_move)
        self._save_cache()

    def set_matrix_rotation(self, rotation: Literal[0, 90, 180, 270] = 0) -> None:
        rotations = {
            0: FrameRotationOptions.NORMAL,
            90: FrameRotationOptions.ROTATE_90_DEGREES,
            180: FrameRotationOptions.ROTATE_180_DEGREES,
            270: FrameRotationOptions.ROTATE_270_DEGREES,
        }
        move = RunAPIMovement(
            desc="set_matrix_rotation",
            method="set_matrix_rotation",
            args=[rotations.get(rotation, FrameRotationOptions.NORMAL)]
        )
        self._runtime.add_movement(move)

    def run_move(self, name: str) -> None:
        got = self._memory_cache.moves.get(name, None)
        if got is None:
            raise NotImplementedError(f"move {name} not implemented")
        self.run(got, stop_at_first=True)

    def on_charging(self, log: str = "feeling at charging") -> None:
        self._runtime.set_charging_callback(log)

    def on_not_charging(self, log: str = "feeling stop charging") -> None:
        self._runtime.set_off_charging_callback(log)

    def self_prompt(self, container: Container) -> str:
        if len(self._memory_cache.moves) == 0:
            return ""
        lines = []
        for move in self._memory_cache.moves.values():
            line = f"- `{move.name}`: {move.description}"
            lines.append(line)
        return "saved moves, from name to description:\n".join(lines) + "\n\nyou can run the saved move by it's name"

    def get_title(self) -> str:
        return "SpheroBolt Ball saved moves"


class SpheroBoltBallAPIProvider(Provider[Ball]):

    def singleton(self) -> bool:
        return True

    def factory(self, con: Container) -> Optional[Ball]:
        runtime = con.force_fetch(SpheroBoltRuntime)
        workspace = con.force_fetch(Workspace)
        return BallApi(runtime, workspace.runtime_cache())
