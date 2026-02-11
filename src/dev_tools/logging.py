import time
from rich import print as rprint

LOG_FORMAT:str = "[bold {color}]{time}[/] => {text}"

def log(text: str, color: str = "yellow", fmt: str | None = None):
    if not fmt:
        fmt = LOG_FORMAT
    time_now = time.strftime("%H:%M:%S", time.localtime())
    rprint(fmt.format(color=color, text=text, time=time_now))

def set_log_format(new_fmt: str):
    global LOG_FORMAT
    LOG_FORMAT = new_fmt

