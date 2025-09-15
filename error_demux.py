
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Панельный просмотр дубликатов строк в логах (2 панели в ряд) + горячая клавиша 'q' для выхода.

Примеры запуска:
  # разовый отчёт по двум логам, топ-15 строк
  python logs_panels.py app.log nginx.error.log -n 15

  # режим слежения раз в 0.5 сек, без учёта регистра, полноэкран
  python logs_panels.py app.log nginx.error.log other.log --watch --refresh 0.5 --ignore-case --fullscreen
"""

import argparse
import sys
import time
import os
from pathlib import Path
from collections import Counter
from typing import Dict, List, Tuple

from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.console import Console

console = Console()


# ============================
# Клавиши: кросс-платформенно
# ============================
if os.name == "nt":
    import msvcrt

    def poll_key() -> str | None:
        """Вернёт символ, если нажата клавиша; иначе None (Windows)."""
        if msvcrt.kbhit():
            ch = msvcrt.getwch()  # unicode
            # Проглотим код расширенной клавиши (стрелки и т.п.)
            if ch in ("\x00", "\xe0") and msvcrt.kbhit():
                _ = msvcrt.getwch()
                return None
            return ch
        return None

    class raw_mode:
        """Заглушка для Windows (режим терминала не требуется)."""
        def __init__(self, *_): pass
        def __enter__(self): return self
        def __exit__(self, *exc): return False

else:
    # POSIX (Linux/macOS)
    import termios
    import tty
    import select

    def poll_key() -> str | None:
        """Вернёт символ, если нажата клавиша; иначе None (POSIX)."""
        r, _, _ = select.select([sys.stdin], [], [], 0)
        if r:
            try:
                ch = sys.stdin.read(1)
                return ch
            except (IOError, OSError):
                return None
        return None

    class raw_mode:
        """Переводит TTY в 'cbreak' на время работы цикла."""
        def __init__(self, stream):
            self.stream = stream
            self.fd = stream.fileno()
            self.attrs = None

        def __enter__(self):
            if self.stream.isatty():
                self.attrs = termios.tcgetattr(self.fd)
                tty.setcbreak(self.fd)
            return self

        def __exit__(self, exc_type, exc, tb):
            if self.attrs is not None:
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.attrs)
            return False


# ============================
# Подсчёт повторяющихся строк
# ============================
def log_parse(path: str, *, strip=True, ignore_case=False) -> Counter:
    """
    Читает файл построчно и возвращает Counter по строкам.
    """
    cnt = Counter()
    p = Path(path)
    if not p.exists():
        return cnt

    with p.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            s = line.rstrip("\n")
            if strip:
                s = s.strip()
            if ignore_case and isinstance(s, str):
                s = s.lower()
            if s:
                cnt[s] += 1
    return cnt


def build_report(paths: List[str], *, strip=True, ignore_case=False) -> Dict[str, Counter]:
    """
    Собирает отчёт: {путь: Counter(...)} для всех файлов.
    """
    return {path: log_parse(path, strip=strip, ignore_case=ignore_case) for path in paths}


# ============================
# Рендеринг Rich Layout
# ============================
def make_panel(path: str, counter: Counter, top: int = 10) -> Panel:
    """
    Создаёт панель с топ-N строками и их количеством.
    """
    p = Path(path)
    title = f"[bold]{p.name}[/] — {p}"

    if not counter:
        body = "[dim]нет записей или файл не найден[/dim]"
    else:
        lines = [f"[bold]{n}×[/]  {msg}" for msg, n in counter.most_common(top)]
        body = "\n".join(lines)

    return Panel(
        body,
        title=title,
        border_style="cyan",
        padding=(1, 2),
    )


def chunk_pairs(items: List[Tuple[str, Counter]]) -> List[List[Tuple[str, Counter]]]:
    """
    Разбивает список на куски по 2 элемента: [[a,b], [c,d], [e]]
    """
    return [items[i:i + 2] for i in range(0, len(items), 2)]


def build_layout(report: Dict[str, Counter], *, top: int = 10, show_help: bool = True) -> Layout:
    """
    Строит Layout, где каждая строка содержит до двух панелей.
    Нижняя строка — статус/подсказки.
    """
    root = Layout(name="root")
    body = Layout(name="body", ratio=1)
    footer = Layout(name="footer", size=3)

    items = list(report.items())
    if not items:
        body.update(Panel("[dim]Нет входных файлов[/dim]", title="Логи"))
    else:
        rows: List[Layout] = []
        pairs = chunk_pairs(items)
        for idx, pair in enumerate(pairs):
            row = Layout(name=f"row{idx}")
            if len(pair) == 2:
                (p1, c1), (p2, c2) = pair
                row.split_row(
                    Layout(make_panel(p1, c1, top=top), ratio=1, name=f"cell{idx}a"),
                    Layout(make_panel(p2, c2, top=top), ratio=1, name=f"cell{idx}b"),
                )
            else:
                (p1, c1) = pair[0]
                row.split_row(
                    Layout(make_panel(p1, c1, top=top), ratio=1, name=f"cell{idx}a"),
                )
            rows.append(row)
        body.split_column(*rows)

    if show_help:
        footer.update(
            Panel(
                "[bold]Горячие клавиши:[/bold]  [yellow bold]Q[/yellow bold] — выход   •   [yellow bold]Ctrl+C[/yellow bold] — аварийный выход\n"
                "[dim]Подсказка:[/dim] используйте --watch для автообновления, --refresh для интервала.",
                border_style="magenta",
                padding=(0, 2),
            )
        )
    else:
        footer.update(Panel("", border_style="magenta"))

    root.split_column(body, footer)
    return root


# ============================
# Основная логика (CLI)
# ============================
def run_once(paths: List[str], *, top: int, strip: bool, ignore_case: bool) -> None:
    report = build_report(paths, strip=strip, ignore_case=ignore_case)
    layout = build_layout(report, top=top)
    # Отрисуем один кадр и выйдем
    with Live(layout, refresh_per_second=8, screen=False):
        time.sleep(0.05)


def run_watch(
    paths: List[str],
    *,
    top: int,
    strip: bool,
    ignore_case: bool,
    refresh_sec: float,
    fullscreen: bool,
) -> None:
    """
    Периодически перечитывает файлы и обновляет лэйаут. Выход по клавише 'q'.
    """
    def render():
        rep = build_report(paths, strip=strip, ignore_case=ignore_case)
        return build_layout(rep, top=top, show_help=True)

    # Live рисует интерфейс; raw_mode включает моментальное чтение клавиш (на Unix)
    with Live(render(), refresh_per_second=max(2, int(1 / max(0.05, min(refresh_sec, 1.0)))), screen=fullscreen) as live, \
         raw_mode(sys.stdin):
        try:
            while True:
                # Обработка горячих клавиш
                key = poll_key()
                if key in ("q", "Q"):
                    break

                # Периодическое обновление
                time.sleep(refresh_sec)
                live.update(render())
        except KeyboardInterrupt:
            # Корректно выходим при Ctrl+C
            pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Панельный просмотр дубликатов строк в логах (2 панели в ряд) + выход по 'q'."
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="Пути к лог-файлам."
    )
    parser.add_argument(
        "--top", "-n",
        type=int,
        default=10,
        help="Сколько верхних записей показывать для каждого файла (по умолчанию 10)."
    )
    parser.add_argument(
        "--ignore-case", "-i",
        action="store_true",
        help="Считать строки без учёта регистра."
    )
    parser.add_argument(
        "--no-strip",
        action="store_true",
        help="Не обрезать пробелы по краям строк."
    )
    parser.add_argument(
        "--watch", "-w",
        action="store_true",
        help="Режим слежения: периодически перечитывать файлы и обновлять экран."
    )
    parser.add_argument(
        "--refresh",
        type=float,
        default=1.0,
        help="Интервал обновления в секундах в режиме --watch (по умолчанию 1.0)."
    )
    parser.add_argument(
        "--fullscreen", "-f",
        action="store_true",
        help="Включить полноэкранный режим в --watch."
    )
    return parser.parse_args()


def main():
    args = parse_args()

    paths = [str(Path(p)) for p in args.files]
    strip = not args.no_strip
    ignore_case = args.ignore_case

    if args.watch:
        run_watch(
            paths,
            top=args.top,
            strip=strip,
            ignore_case=ignore_case,
            refresh_sec=max(0.1, args.refresh),
            fullscreen=args.fullscreen,
        )
    else:
        run_once(
            paths,
            top=args.top,
            strip=strip,
            ignore_case=ignore_case,
        )


if __name__ == "__main__":
    main()

