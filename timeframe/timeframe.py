from __future__ import annotations

import asyncio
import types
from typing import *
from collections.abc import Callable
import enum
import time
import traceback
import inspect

A = TypeVar('A')
K = TypeVar('K')


class Emoji(enum.Enum):
    SUCCESS = '✅'
    FUTURE = '🟨'
    LOADING = '⏳'
    ISSUE = '⚠️'
    FAILED = '❌'
    FATAL = '🛑'

    @classmethod
    def translate(cls, state: State) -> Emoji:
        check_state = State(state)
        return Emoji(getattr(cls, check_state.name))


class State(enum.Enum):
    FUTURE = 0x4000
    LOADING = 0x8000
    SUCCESS = 0xb000
    ISSUE = 0xf000
    FAILED = 0xfff0
    FATAL = 0xffff

    @classmethod
    def translate(cls, state: Emoji) -> State:
        check_state = Emoji(state)
        return State(getattr(cls, check_state.name))


class IterationCompleted(StopIteration):
    pass


class IterationFailed(StopIteration):
    pass


def get_exc_src(exc_type: Type[BaseException]) -> str:
    return exc_type.__module__ + "." if exc_type.__module__ is not None and exc_type.__module__ != str.__module__ else ""


class BaseFrame:
    def __init__(self, name: Optional[str] = None):
        self._name = name
        self._start: Optional[float] = None
        self._state: State = State.FUTURE
        self._end: Optional[float] = None

    @property
    def state(self) -> State:
        return self._state

    @state.setter
    def state(self, state: State) -> None:
        if not isinstance(state, State):
            raise ValueError(f'You can only set state with State enum')
        if state.value <= self._state.value:
            return
        self._state = state

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
                    if frame.state not in (State.FAILED, State.FATAL):
                        break
                else:
                    self.state = State.FAILED
        if self.state not in (State.ISSUE, State.FAILED, State.FATAL):
            self.state = State.SUCCESS
        return self

    def failed(self, is_issue: bool = False, tb: Optional[str] = None) -> Self:
        self._end = time.perf_counter()
        if self.state not in (State.FATAL, State.FAILED):
            self.state = State.FAILED if not is_issue else State.ISSUE
        if self.state == State.ISSUE:
            return self
        if isinstance(self, Attempt):
            self._parent.state = State.ISSUE
        if isinstance(self, (Event, Action)):
            self._parent.state = State.FAILED
        if tb:
            added_string1 = ''
            if isinstance(self, (Attempt, Event, Action)):
                added_string1 += f'from parent \'{self._parent._name}\' '
                added_string1 += f'at TimeFrame \'{self._main._name}\''
            if isinstance(self, TimeFrame):
                added_string1 += f'at TimeFrame \'{self._name}\''
            formatted = f'[{time.perf_counter():08.3f}s] Error raised on {self.__class__.__name__} \'{self._name}\' {added_string1} with State {self.state.name}:\n{tb}'
            if isinstance(self, (Attempt, Event, Action)):
                self._main._tb.append(formatted)
            if isinstance(self, TimeFrame):
                self._tb.append(formatted)
        return self

    def __repr__(self) -> str:
        return f"{Emoji.translate(self.state).value}-{self._name}" + ("" if self.duration < 0.001 and self.state in (
            State.LOADING, State.FUTURE) else f" ({self.duration:08.3f}s)")  # isinstance(self, Attempt) and

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
            if self.state not in (State.FAILED, State.FATAL):
                raise IterationCompleted(f'Task have been completed')
            if self._parent.curr_retries >= self._parent.retries:
                raise IterationFailed(f'Failed after retry of {self._parent.curr_retries} attempts')
        return True

    async def __aenter__(self) -> Self:
        return self.__enter__()

    async def __aexit__(self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException],
                        exc_tb: Optional[types.TracebackType]) -> bool:
        try:
            result = self.__exit__(exc_type, exc_val, exc_tb)
            return result
        except IterationCompleted:
            return True
        except Exception:
            return False


class Attempt(BaseFrame):
    def __init__(self, main: TimeFrame[A, K], parent: Action):
        self._main = main
        self._parent = parent
        self._add_string = ''
        self._rt_completed: bool = False
        super().__init__(name=f'Attempt #{self._parent.curr_retries + 1}')

    def __exit__(self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException],
                 exc_tb: Optional[types.TracebackType]) -> bool:
        if exc_type is None:
            return super().__exit__(exc_type, exc_val, exc_tb)
        if (exc_type in self._parent.ignore_retries or
                (self._parent._check_exc_subclass and
                 issubclass(exc_type, tuple(self._parent._ignore_retries)))):
            self.state = State.FATAL
            self._add_string += f'Ignore retries by exception: {get_exc_src(exc_type)}{exc_type.__name__}'
            super().__exit__(exc_type, exc_val, exc_tb)
            return False
        return super().__exit__(exc_type, exc_val, exc_tb)

    def __enter__(self) -> Self:
        if not self._rt_completed:
            self._main._trigger_sync()
            self._rt_completed = True
        return super().__enter__()

    async def __aenter__(self) -> Self:
        await self._main._trigger_async()
        self._rt_completed = True
        return self.__enter__()

    def __repr__(self) -> str:
        return super().__repr__() + (f" ({self._add_string})" if self._add_string else "")


class Action(BaseFrame):
    def __init__(self, main: TimeFrame[A, K], parent: Event, name: Optional[str] = None, retries: int = 3,
                 ignore_retries: Optional[Sequence[Type[BaseException]]] = None, check_exc_subclass: bool = False):
        real_ignore_retries: Sequence[Type[BaseException]] = ignore_retries or ()
        self._ignore_retries = real_ignore_retries
        self._main = main
        self._parent = parent
        self._frames: MutableSequence[Attempt] = []
        self._retries = retries
        self._curr_retries = 0
        self._check_exc_subclass = check_exc_subclass
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

    @property
    def ignore_retries(self) -> Sequence[Type[BaseException]]:
        return self._ignore_retries


class Event(BaseFrame):
    def __init__(self, main: TimeFrame[A, K], parent: TimeFrame[A, K], name: Optional[str] = None):
        self._main = main
        self._parent = parent
        self._frames: MutableSequence[Action] = []
        super().__init__(name=name)

    def create(self, name: Optional[str] = None, retries: int = 3,
               ignore_retries: Optional[Sequence[Type[BaseException]]] = None) -> Action:
        event = Action(main=self._main, parent=self, name=name, retries=retries, ignore_retries=ignore_retries)
        self._frames.append(event)
        return event


def _get_space_dc(index: int) -> str:
    if index == 2:
        return '> '
    if index == 3:
        return '> - '
    return ''


class TimeFrame(BaseFrame, Generic[A, K]):
    def __init__(self, *args: A, name: Optional[str] = None, rt: Union[Callable[..., Any], None] = None, **kwargs: K):
        self._frames: MutableSequence[Event] = []
        self._tb: list[str] = []
        self._rt: tuple[Optional[Callable[..., Any]], tuple[A, ...], dict[str, K]] = (rt, args, kwargs)
        self._re: Any = None
        self._rt_completed: bool = False
        super().__init__(name=name)

    @property
    def _init_content(self) -> list[str]:
        total_or_current = 'Current' if self.state in (State.LOADING, State.FUTURE) else 'Total'
        content = [f'{total_or_current}: {self.duration:08.3f}s ({total_or_current} Frames: {len(self)})']
        return content

    def create(self, name: Optional[str] = None) -> Event:
        group = Event(main=self, parent=self, name=name)
        self._frames.append(group)
        return group

    def _check_recur(self, source: TimeFrame[A, K] | Event | Action | Attempt) -> TypeGuard[Union[TimeFrame[A, K] | Event | Action]]:
        """Return a boolean value on whether it should continue recurring or stop"""
        if isinstance(source, Attempt):
            return False
        if isinstance(source, Action) and len(source._frames) == 1 and source._frames[0].state == State.SUCCESS:
            return False
        return True

    def frame_format_dc(self, limit: int = 1024) -> str | bool:
        for lim in range(3, 0, -1):
            formatted = self._format_dc(limit=lim)
            if len(formatted) <= limit:
                return formatted
        else:
            return False

    def _format_dc(self, limit: int = 3) -> str:
        content = self._init_content
        self._recur_dc(content, self, limit=limit)
        return '\n'.join(content)

    def _recur_dc(self, content: list[str], source: TimeFrame[A, K] | Event | Action | Attempt, index: int = 0,
                  limit: int = 3) -> None:
        if index != 0:
            content += [f'{_get_space_dc(index)}{source.__repr__()}']
        index += 1
        if index > limit or not self._check_recur(source):
            return

        for item in source._frames:
            self._recur_dc(content, index=index, source=item, limit=limit)

    def frame_format_mono(self) -> str:
        content = self._init_content
        self._recur_mono(content, self, index=0)
        return '\n'.join(content)

    def print_mono(self) -> None:
        print(self.frame_format_mono())

    def _recur_mono(self, content: list[str], source: TimeFrame[A, K] | Event | Action | Attempt,
                    index: int = 0, ) -> None:
        content += [f'{"  " * index}{source.__repr__()}']
        if not self._check_recur(source):
            return
        index += 1
        for item in source._frames:
            self._recur_mono(content, index=index, source=item)

    def frame_format_custom(self, style: tuple[str | None, str | None, str | None, str | None] = (
            None, '\n', '-  ', '> - ')) -> str:
        """Use None on the index you don't want it to display in `style`, default at normal markdown settings"""
        content = self._init_content
        self._recur_custom(content, self, style=style)
        return '\n'.join(content)

    def _recur_custom(self, content: list[str], source: TimeFrame[A, K] | Event | Action | Attempt,
                      style: tuple[str | None, str | None, str | None, str | None], index: int = 0, ) -> None:
        if style[index] is not None:
            content += [f'{style[index]}{source.__repr__()}']
        index += 1
        if not self._check_recur(source):
            return
        for item in source._frames:
            self._recur_custom(content, index=index, source=item, style=style)

    async def _trigger_async(self) -> Any:
        if self._rt[0] is not None:
            _rt = cast(tuple[Callable[..., Any], tuple[A, ...], dict[str, K]], self._rt)
            if inspect.iscoroutinefunction(self._rt[0]):
                self._re = await _rt[0](self, *_rt[1], **_rt[2])
            else:
                self._re = await asyncio.to_thread(_rt[0], self, *_rt[1], **_rt[2])
            return self._re

    def _trigger_sync(self) -> Any:
        if self._rt[0] is not None:
            _rt = cast(tuple[Callable[..., Any], tuple[A, ...], dict[str, K]], self._rt)
            _re = _rt[0](self, *_rt[1], **_rt[2])
            if inspect.isawaitable(_re):
                import threading
                thread = threading.Thread(target=asyncio.run, args=(_re,))
                # self._re = asyncio.get_running_loop().run_until_complete(_re)
                thread.start()
                thread.join(timeout=0.2)
            else:
                self._re = _re
            return self._re

    def traceback_format(self) -> str:
        return '\n'.join(self._tb)

    def __exit__(self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException],
                 exc_tb: Optional[types.TracebackType]) -> bool:
        if not self._rt_completed:
            self._trigger_sync()
            self._rt_completed = True
        return super().__exit__(exc_type, exc_val, exc_tb)

    async def __aexit__(self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException],
                 exc_tb: Optional[types.TracebackType]) -> bool:
        await self._trigger_async()
        self._rt_completed = True
        return await self.__aexit__(exc_type, exc_val, exc_tb)
