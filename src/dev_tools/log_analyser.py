import os
import argparse

import subprocess as sp

from time import sleep
from .tg_alarm import send_alarm

from os import PathLike

def analyze(path: PathLike | str, mode: str, tgid: int, interval: float = 1) -> None:
    """
    analysis of log files and notification of errors in telegram
    :param path: Path to log file
    :param mode: mode for working, e.g, \"<some text 1>|<some text 2>\" - this mode finding strokes equas \"some text 1\" and \"some text 2\" and notification, '|' the seporator"
    :param tgid: your telegram id for sending notifications about errors
    :param interval: interval for scanning, default 1s
    :return: None
    """
    while True:
        sp.run(
            f'''tail -F {os.path.normpath(path)} | while IFS= read -r line; do
                printf '%s\n' "$line" | grep -Eiq -- "{mode}" && \
                python tg_alarm.py {tgid} "$(printf "%s" "$line") this stroke get from {path} log file" && \
                sleep {interval}
            done''',
            shell=True
        )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=str, help="path to log file for analyze and notification of warnings and/or errors")
    parser.add_argument("mode", type=str, help="mode for working, e.g, \"<some text 1>|<some text 2>\" - this mode finding strokes equas \"some text 1\" and \"some text 2\" and notification, '|' the seporator")
    parser.add_argument("tgid", type=str, help="your telegram chat id for sending notification about errors")
    parser.add_argument("-i", type=int ,default=1, help="interval for scaning, default 1s")

    args = parser.parse_args()

    analyze(args.file, args.mode, args.tgid, args.i)


if __name__ == "__main__":
    main()

