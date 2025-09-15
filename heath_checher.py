
import argparse
import yaml
import requests
from collections import defaultdict, deque
from datetime import datetime
from time import perf_counter, sleep
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Json, HttpUrl

from rich import print
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.layout import Layout
from rich.rule import Rule

from tg_alarm import send_alarm


# Храним историю латентностей по каждому эндпойнту (ограничим, например, 120 точками)
HISTORY_LEN = 120
endpoints_resp_times: Dict[str, deque[int]] = defaultdict(lambda: deque(maxlen=HISTORY_LEN))

console = Console()


class Point(BaseModel):
    url: HttpUrl | str
    method: str
    # data принимает либо JSON-строку, либо None; при валидации JSON-строка станет dict
    data: Optional[Json[Dict[str, Any]]] = None


class Config(BaseModel):
    tg_id: int
    points: List[Point]


def check(url: str, tg_id: int, method: str, data: Optional[dict[str, Any]] = None) -> int:
    """
    Возвращает время ответа в миллисекундах (целое число).
    Если запрос упал — возвращает -1 и шлёт alarm.
    """
    try:
        start_ms = perf_counter() * 1000.0

        m = method.upper()
        if m == "GET":
            requests.get(url)
        elif m == "POST":
            if data is None:
                raise ValueError("json data missing")
            requests.post(url, json=data)
        elif m == "OPTIONS":
            requests.options(url, )
        else:
            raise ValueError(f"Unsupported method: {method}")

        latency_ms = int(perf_counter() * 1000.0 - start_ms)
        return latency_ms if latency_ms >= 0 else 0
    except Exception:
        send_alarm(tg_id, "[ERR] service not responding")
        return -1


# ---------- спарклайн без rich.plot ----------
BARS = "▁▂▃▄▅▆▇█"

def make_sparkline(values: List[Optional[int]], width: int = 48) -> Text:
    """
    Преобразует список значений (мс, None для пропусков) в строку-спарклайн фиксированной ширины.
    Ошибки (-1) должны быть заранее заменены на None.
    """
    txt = Text()

    if not values:
        txt.append("no data", style="dim")
        return txt

    # Урезаем/растягиваем до нужной ширины (простая дискретизация)
    if len(values) > width:
        step = len(values) / width
        sampled = []
        acc = 0.0
        for _ in range(width):
            lo = int(round(acc))
            acc += step
            hi = max(lo + 1, int(round(acc)))
            window = [v for v in values[lo:hi] if v is not None]
            sampled.append(sum(window) / len(window) if window else None)
    else:
        # Паддинг None слева до ширины
        sampled = [None] * (width - len(values)) + values

    # Нормализация по максимуму (игнорим None)
    finite_vals = [v for v in sampled if v is not None]
    vmax = max(finite_vals) if finite_vals else 1

    for v in sampled:
        if v is None:
            txt.append("·", style="dim")  # таймаут/пробел
        else:
            # индекс столбика 0..7
            idx = int((v / vmax) * (len(BARS) - 1)) if vmax > 0 else 0
            txt.append(BARS[idx])

    return txt


def _panel_for_endpoint(url: str, times: deque[int]) -> Panel:
    """
    Рендер одной панели: статус + спарклайн латентности.
    """
    last = times[-1] if times else -1
    is_ok = last > 0

    status_text = Text("status: ")
    status_text.append("Respond" if is_ok else "Not Respond", style=("bold green" if is_ok else "bold red"))

    if last >= 0:
        status_text.append(f"   last: {last} ms", style="dim")
    else:
        status_text.append("   last: timeout/error", style="dim")

    # Список для графика: -1 -> None
    series = [t if t >= 0 else None for t in times]
    spark = make_sparkline(series, width=48)

    # Подписи min/avg/max (по валидным значениям)
    vals = [t for t in times if t >= 0]
    stats = Text()
    if vals:
        mn, mx = min(vals), max(vals)
        avg = int(sum(vals) / len(vals))
        stats.append(f"min {mn} ms  avg {avg} ms  max {mx} ms", style="dim")
    else:
        stats.append("no successful samples yet", style="dim")

    body = Group(
        status_text,
        Rule(style="dim"),
        spark,
        stats,
    )

    return Panel(
        body,
        title=str(url),
        border_style=("green" if is_ok else "red"),
        padding=(1, 2),
    )


def render() -> Layout:
    """
    Главный рендер TUI: шапка + колонки панелей по URL.
    """
    layout = Layout(name="root")
    layout.split(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1),
        Layout(name="footer", size=3)
    )

    # Шапка
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header_text = Text.assemble(
        ("Health checker", "bold"),
        ("  •  ", "dim"),
        (now, "dim"),
    )
    layout["header"].update(Panel(header_text, border_style="cyan", padding=(0, 2)))

    # Тело
    panels = [
        _panel_for_endpoint(url, times)
        for url, times in endpoints_resp_times.items()
    ]
    layout["body"].update(Columns(panels, expand=True, 
                          #equal=True
                                  ))
    layout["footer"].update(Panel(
                "[bold]Горячие клавиши:[/bold]   [yellow bold]Ctrl+C[/yellow bold] — выход\n",
                border_style="magenta",
                padding=(0, 2),
            ))
    return layout


def health_checker(conf_path: str, interval: int = 10, watch: bool = False) -> None:
    with open(conf_path, "r", encoding="utf-8") as config_file:
        conf = Config(**yaml.load(config_file, Loader=yaml.SafeLoader))

    # Инициализируем ключи (создаст пустые deque)
    for p in conf.points:
        _ = endpoints_resp_times[str(p.url)]

    if not watch:
        # Обычный лог без TUI
        while True:
            for point in conf.points:
                t = check(str(point.url), conf.tg_id, point.method, point.data)
                endpoints_resp_times[str(point.url)].append(t)
                if t > 0:
                    print(f'[green][OK][/green] Endpoint "{point.url}" responding in {t} ms')
                else:
                    print(f'[red][ERR][/red] Endpoint "{point.url}" not responding')
            sleep(interval)
    else:
        # Живой TUI
        with Live(render(), refresh_per_second=4, screen=True, console=console) as live:
            while True:
                for point in conf.points:
                    t = check(str(point.url), conf.tg_id, point.method, point.data)
                    endpoints_resp_times[str(point.url)].append(t)
                live.update(render())
                sleep(interval)


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser()

        parser.add_argument("-c", type=str, required=True, help="path to config")
        parser.add_argument("-i", type=int, default=10, help="interval between checks (seconds)")
        parser.add_argument("-w", action="store_true", help="watch mode: show TUI with response time plots")

        args = parser.parse_args()

        health_checker(args.c, args.i, args.w)
    except KeyboardInterrupt:
        exit(0)

