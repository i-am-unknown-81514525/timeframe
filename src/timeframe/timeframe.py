from __future__ import annotations

import types
from typing import *
import enum
import time
import traceback


class Emoji(enum.Enum):
    SUCCESS = '✅'
    FUTURE = '🟨'
    LOADING = '⏳'
    ISSUE = '⚠️'
    FAILED = '❌'

    @classmethod
    def translate(cls, state: State) -> Emoji:
        check_state = State(state)
        return Emoji(getattr(cls, check_state.name))


class State(enum.Enum):
    FUTURE = 0x4000
    SUCCESS = 0x8000
    LOADING = 0xb000
    ISSUE = 0xf000
    FAILED = 0xffff

    @classmethod
    def translate(cls, state: Emoji) -> State:
        check_state = Emoji(state)
        return State(getattr(cls, check_state.name))


class IterationCompleted(StopIteration):
    pass


class IterationFailed(StopIteration):
    pass


class BaseFrame:
    def __init__(self, name: Optional[str] = None):
        self._name = name
        self._start: Optional[float] = None
        self.state: State = State.FUTURE
        self._end: Optional[float] = None

    @property
    def duration(self) -> float:
        if not self._start:
            return 0
        if not self._end:
            return time.perf_counter() - self._start
        return self._end - self._start

    def start(self) -> Self:
        self._start = time.perf_counter()
        self.state = State.LOADING
        return self

    def end(self) -> Self:
        self._end = time.perf_counter()
        if isinstance(self, (Action, Event, TimeFrame)):
            if self._frames:
                for frame in self._frames:
                    if frame.state != State.FAILED:
                        break
                else:
                    self.state = State.FAILED
        if self.state != State.ISSUE and self.state != State.FAILED:
            self.state = State.SUCCESS
        return self

    def failed(self, is_issue: bool = False, tb: Optional[str] = None) -> Self:
        self._end = time.perf_counter()
        self.state = State.FAILED if not is_issue else State.ISSUE
        if self.state == State.FAILED:
            if isinstance(self, Attempt):
                self._parent.state = State.ISSUE
            if isinstance(self, (Event, Action)):
                self._parent.state = State.FAILED
        if tb and self.state == State.FAILED:
            added_string1 = ''
            if isinstance(self, (Attempt, Event, Action)):
                added_string1 += f'from parent \'{self._parent._name}\' '
                added_string1 += f'at TimeFrame \'{self._main._name}\''
            if isinstance(self, TimeFrame):
                added_string1 += f'at TimeFrame \'{self._name}\''
            formatted = f'[{time.perf_counter():08.3f}s] Error raised on {self.__class__.__name__} \'{self._name}\' {added_string1}:\n{tb}'
            if isinstance(self, (Attempt, Event, Action)):
                self._main._tb.append(formatted)
            if isinstance(self, TimeFrame):
                self._tb.append(formatted)
        return self

    def __repr__(self) -> str:
        return f"{Emoji.translate(self.state).value}-{self._name} ({self.duration:08.3f}s)"

    def __str__(self) -> str:
        return self.__repr__()

    def __len__(self) -> int:
        data = getattr(self, '_frames', None)
        if data is None:
            return 1
        else:
            return sum([len(item) for item in data]) + 1

    def __enter__(self) -> Self:
        return self.start()

    def __exit__(self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException],
                 exc_tb: Optional[types.TracebackType]) -> bool:
        if exc_type is None or exc_type == IterationCompleted:
            self.end()
        else:
            self.failed(tb='\n'.join(traceback.format_exception(exc_type, exc_val, exc_tb)))
        if isinstance(self, Attempt):
            if self.state != State.FAILED:
                raise IterationCompleted(f'Task have been completed')
            if self._parent.curr_retries >= self._parent.retries:
                raise IterationFailed(f'Failed after retry of {self._parent.curr_retries} attempts')
        return True


class Attempt(BaseFrame):
    def __init__(self, main: TimeFrame, parent: Action):
        self._main = main
        self._parent = parent
        super().__init__(name=f'Attempt #{self._parent.curr_retries + 1}')


class Action(BaseFrame):
    def __init__(self, main: TimeFrame, parent: Event, name: Optional[str] = None, retries: int = 3):
        self._main = main
        self._parent = parent
        self._frames: MutableSequence[Attempt] = []
        self._retries = retries
        self._curr_retries = 0
        super().__init__(name=name)

    def create(self) -> Attempt:
        frame = Attempt(main=self._main, parent=self)
        self._frames.append(frame)
        self._curr_retries += 1
        return frame

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> Attempt:
        if self._curr_retries >= self._retries:
            raise StopIteration
        if len(self._frames) >= 1:
            if self._frames[-1].state == State.LOADING:
                self._frames[-1].state = State.SUCCESS
            if self._frames[-1].state == State.SUCCESS:
                raise StopIteration
        return self.create()

    @property
    def curr_retries(self) -> int:
        return self._curr_retries

    @property
    def retries(self) -> int:
        return self._retries


class Event(BaseFrame):
    def __init__(self, main: TimeFrame, parent: TimeFrame, name: Optional[str] = None):
        self._main = main
        self._parent = parent
        self._frames: MutableSequence[Action] = []
        super().__init__(name=name)

    def create(self, name: Optional[str] = None, retries: int = 3) -> Action:
        event = Action(main=self._main, parent=self, name=name, retries=retries)
        self._frames.append(event)
        return event


def _get_space_dc(index: int) -> str:
    if index == 2:
        return '> '
    if index == 3:
        return '> - '
    return ''


class TimeFrame(BaseFrame):
    def __init__(self, name: Optional[str] = None):
        self._frames: MutableSequence[Event] = []
        self._tb: list[str] = []
        super().__init__(name=name)

    def create(self, name: Optional[str] = None) -> Event:
        group = Event(main=self, parent=self, name=name)
        self._frames.append(group)
        return group

    def frame_format_dc(self, limit: int = 1024) -> str | bool:
        for lim in range(3, 0, -1):
            formatted = self._format_dc(limit=lim)
            if len(formatted) <= limit:
                return formatted
        else:
            return False

    def _format_dc(self, limit: int = 3) -> str:
        content = [f'Total: {self.duration:08.3f}s (Total Frames: {len(self)})']
        self._recur_dc(content, self, limit=limit)
        return '\n'.join(content)

    def _recur_dc(self, content: list[str], source: TimeFrame | Event | Action | Attempt, index: int = 0,
                  limit: int = 3) -> None:
        if index != 0:
            content += [f'{_get_space_dc(index)}{source.__repr__()}']
        index += 1
        if index > limit or isinstance(source, Attempt):
            return
        if isinstance(source, Action) and len(source._frames) == 1:
            return
        for item in source._frames:
            self._recur_dc(content, index=index, source=item, limit=limit)

    def frame_format_mono(self) -> str:
        content = [f'Total: {self.duration:08.3f}s (Total Frames: {len(self)})']
        self._recur_mono(content, self, index=0)
        return '\n'.join(content)

    def _recur_mono(self, content: list[str], source: TimeFrame | Event | Action | Attempt, index: int = 0, ) -> None:
        content += [f'{"  " * index}{source.__repr__()}']
        if isinstance(source, Attempt):
            return
        if isinstance(source, Action) and len(source._frames) == 1:
            return
        index += 1
        for item in source._frames:
            self._recur_mono(content, index=index, source=item)

    def traceback_format(self) -> str:
        return '\n'.join(self._tb)