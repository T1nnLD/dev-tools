import time
from rich import print as rprint

def log(text: str, color: str, fmt: str = "[bold {color}]{time}[/] => {text}"):
    time_now = time.strftime("%H:%M:%S", time.localtime())
    rprint(fmt.format(color=color, text=text, time=time_now))

