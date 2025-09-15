import os
import argparse

import subprocess as sp

from time import sleep
from tg_alarm import send_alarm 

def analyze(path, mode, tgid, interval):
    while True:
        sp.run(
            f'''tail -F {os.path.normpath(path)} | while IFS= read -r line; do
                printf '%s\n' "$line" | grep -Eiq -- "{mode}" && \
                python tg_alarm.py {tgid} "$(printf "%s" "$line") this stroke get from {path} log file" && \
                sleep {interval}
            done''',
            shell=True
        )

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=str, help="path to log file for analyze and notification of warnings and/or errors")
    parser.add_argument("mode", type=str, help="mode for working, e.g, \"<some text 1>|<some text 2>\" - this mode finding strokes equas \"some text 1\" and \"some text 2\" and notification, '|' the seporator")
    parser.add_argument("tgid", type=str, help="your telegram chat id for sending notification about errors")
    parser.add_argument("-i", type=int ,default=1, help="interval for scaning, default 1s")

    args = parser.parse_args()

    analyze(args.file, args.mode, args.tgid, args.i)


