from time import sleep
from rich import print
from typing import Callable
from functools import wraps
from threading import Thread
from time import perf_counter
from asyncio import iscoroutinefunction

import asyncio

def timer_ms(label: None | str = None, fmt: str = "[bold yellow]{label}[/] worked in [yellow bold]{time:.2f}[/]"):
    def dec(f):
        if iscoroutinefunction(f):
            @wraps(f)
            async def wrapper(*args, **kwargs):
                start = perf_counter()
                try:
                    return await f(*args, **kwargs)
                finally:
                    time = (perf_counter() - start) * 1000
                    if label:
                        Thread(target=print, args=(fmt.format(label=label, time=time),)).start()
                    else:
                        Thread(target=print, args=(fmt.format(label=f.__name__, time=time),)).start()
            return wrapper
        else:
            @wraps(f)
            def wrapper(*args, **kwargs):
                start = perf_counter()
                try:
                    return f(*args, **kwargs)
                finally:
                    time = (perf_counter() - start) * 1000
                    if label:
                        Thread(target=print, args=(fmt.format(label=label, time=time),)).start()
                    else:
                        Thread(target=print, args=(fmt.format(label=f.__name__, time=time),)).start()
            return wrapper
    return dec


@timer_ms("test_timer")
def test_func(time=1):
    sleep(time)

@timer_ms()
async def test_async_func(time=1):
    sleep(time)
test_func()
asyncio.run(test_async_func())
