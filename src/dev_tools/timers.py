
"""
Utilities for measuring execution time.

Includes:
- InterTimer — a simple manual timer with start/stop methods.
- timer_ms decorator — measures runtime of sync and async functions
  and prints the result using rich.print (printing is offloaded to a thread).

Example:
    timer = InterTimer()
    timer.start()
    # ... code ...
    timer.stop("initialization")

    @timer_ms("calc")
    def calc():
        ...

    @timer_ms(fmt="Function {label} took {time:.2f} ms")
    async def task():
        ...
"""

from time import sleep
from rich import print
from typing import Callable, TypeVar, ParamSpec, Awaitable, overload
from functools import wraps
from threading import Thread
from time import perf_counter
from asyncio import iscoroutinefunction

import asyncio

P = ParamSpec("P")
T = TypeVar("T")


class InterTimer:
    """
    Simple interval timer in milliseconds.

    Lets you measure the time span between `start()` and `stop(name)`
    and prints the result using a configurable format string.

    The `fmt` string supports placeholders:
        {label} — a custom label for the interval
        {time}  — elapsed time in milliseconds (float)

    Args:
        fmt: Message template used to print the result.
             Default: "[bold yellow]{label}[/] worked in [yellow bold]{time:.2f}[/]ms"
    """

    def __init__(self, fmt: str = "[bold yellow]{label}[/] worked in [yellow bold]{time:.2f}[/]ms"):
        self.fmt = fmt
        self.start_time: float | None = None

    def start(self) -> None:
        """
        Stores the current time (ms) as the start of the interval.
        """
        self.start_time = perf_counter() * 1000

    def stop(self, name: str) -> None:
        """
        Ends the interval and prints its duration.

        Args:
            name: Label for the interval, inserted into {label}.
        """
        # Guard against calling stop() before start():
        # if that happens, treat "now" as the baseline so the message still prints.
        base = self.start_time if self.start_time is not None else perf_counter() * 1000
        print(self.fmt.format(label=name, time=(perf_counter() * 1000) - base))


# Overloads for precise typing: decorator works with both sync and async functions.
@overload
def timer_ms(
    label: str | None = ...,
    fmt: str = ...
) -> Callable[[Callable[P, T]], Callable[P, T]]: ...
@overload
def timer_ms(
    label: str | None = ...,
    fmt: str = ...
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]: ...


def timer_ms(
    label: str | None = None,
    fmt: str = "[bold yellow]{label}[/] worked in [yellow bold]{time:.2f}[/]ms",
):
    """
    Decorator that measures a function's execution time (milliseconds).

    Supports both regular (sync) and coroutine (async) functions.
    Measurement wraps the original function, and printing is done via
    `rich.print` in a background `Thread` so it doesn’t delay return.

    Args:
        label: Explicit label to use for {label}. If omitted, the function name is used.
        fmt:   Output format string. Placeholders:
               {label} — function label; {time} — duration in ms.

    Returns:
        A wrapper preserving the original function’s signature that prints
        the execution time on each call.
    """
    def dec(f: Callable[P, T] | Callable[P, Awaitable[T]]):
        if iscoroutinefunction(f):
            @wraps(f)
            async def wrapper(*args: P.args, **kwargs: P.kwargs):
                start = perf_counter()
                try:
                    return await f(*args, **kwargs)
                finally:
                    # Convert to milliseconds
                    time_ms = (perf_counter() - start) * 1000
                    msg = fmt.format(label=label or f.__name__, time=time_ms)
                    # Print on a separate thread so the return path stays snappy
                    Thread(target=print, args=(msg,)).start()
            return wrapper  # type: ignore[return-value]
        else:
            @wraps(f)
            def wrapper(*args: P.args, **kwargs: P.kwargs):
                start = perf_counter()
                try:
                    return f(*args, **kwargs)
                finally:
                    time_ms = (perf_counter() - start) * 1000
                    msg = fmt.format(label=label or f.__name__, time=time_ms)
                    Thread(target=print, args=(msg,)).start()
            return wrapper  # type: ignore[return-value]
    return dec


if __name__ == "__main__":
    # Usage example (remove in production if not needed)
    timer = InterTimer()
    timer.start()

    @timer_ms("test_timer")
    def test_func(time: float = 1):
        """Synchronous demo function introducing a delay."""
        sleep(time)

    @timer_ms(fmt="func with name {label} worked in [yellow bold]{time:.2f}ms[/]")
    async def test_async_func(time: float = 1):
        """Async demo function (uses sleep here just for simplicity)."""
        sleep(time)

    test_func()
    asyncio.run(test_async_func())
    timer.stop("main test")

