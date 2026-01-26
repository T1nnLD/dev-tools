import time
from rich import print as rprint

FMT:str = "[bold {color}]{time}[/] => {text}"

def log(text: str, color: str = "yellow", fmt: str = FMT):
    time_now = time.strftime("%H:%M:%S", time.localtime())
    rprint(fmt.format(color=color, text=text, time=time_now))

