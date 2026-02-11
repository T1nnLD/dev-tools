

import yaml
import argparse
import subprocess as sp
from pydantic import BaseModel
from pydantic import field_validator
from dev_tools.logging import log
from time import sleep
from rich.console import Console
from typing import List, Optional

class Config(BaseModel):
    branch: str
    interval: float = 1
    ignore: Optional[List[str]] = None  # Список путей/паттернов для игнора

    @field_validator("interval")
    def check_interval(cls, v: float) -> float:
        if v < 0:
            raise ValueError("interval cannot be negative")
        return v

def apply_skip_worktree(ignore_list: List[str]):
    for pattern in ignore_list:
        # Получаем список tracked файлов, matching паттерну (поддержка glob)
        ls_result = sp.run(["git", "ls-files", "--", pattern], capture_output=True, text=True)
        if ls_result.returncode != 0:
            log(f"[WARN] No tracked files found for pattern {pattern}", "yellow")
            continue
        files = ls_result.stdout.strip().splitlines()
        for file in files:
            sp.run(["git", "update-index", "--skip-worktree", file])
            log(f"Applied --skip-worktree to {file}", "yellow")

def has_differences_with_remote(branch: str, ignore_list: Optional[List[str]] = None) -> bool:
    console = Console()
    differences_found = False
    with console.status("[bold green]Checking for differences with remote...", spinner="dots"):
        # Fetch сначала
        fetch_result = sp.run(["git", "fetch"], capture_output=True, text=True)
        if fetch_result.returncode != 0:
            console.print(f"    [ERR] Fetch failed: {fetch_result.stderr.strip()}", style="red")
            return False

        exclude_args = []
        if ignore_list:
            exclude_args = [f":(exclude){pat}" for pat in ignore_list]

        # 1. Проверка local HEAD vs remote (committed различия)
        head_vs_remote = sp.run(
            ["git", "diff", "--quiet", "HEAD", f"origin/{branch}", "--", ".", *exclude_args],
            capture_output=True
        )
        if head_vs_remote.returncode == 1:
            console.print("    Detected committed differences with remote", style="yellow")
            differences_found = True

        # 2. Проверка staged vs remote (staged изменения)
        staged_vs_remote = sp.run(
            ["git", "diff", "--quiet", "--cached", f"origin/{branch}", "--", ".", *exclude_args],
            capture_output=True
        )
        if staged_vs_remote.returncode == 1:
            console.print("    Detected staged changes differing from remote", style="yellow")
            differences_found = True

        # 3. Проверка working dir (unstaged) vs remote (unstaged изменения)
        working_vs_remote = sp.run(
            ["git", "diff", "--quiet", f"origin/{branch}", "--", ".", *exclude_args],
            capture_output=True
        )
        if working_vs_remote.returncode == 1:
            console.print("    Detected unstaged changes in working dir differing from remote", style="yellow")
            differences_found = True

    return differences_found

def main():
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("-c", type=str, default="./git-sync.conf.yaml", help="path to config")
        parser.add_argument("--generate-config", action="store_true", help="generate baseline config")
        args = parser.parse_args()

        if args.generate_config:
            result = sp.run(["git", "branch", "--show-current"], capture_output=True, text=True)
            current_branch = result.stdout.strip() or "main"
            with open("./git-sync.conf.yaml", "w") as file:
                config = {"config": 
                            {"branch": current_branch, 
                            "interval": 1, 
                            "ignore":[
                                'git-sync.conf.yaml'
                              ]
                            }
                        }
                
                yaml.dump(config, file, indent=2)
                log(f"Configuration file generated with branch: {current_branch}")
            exit(0)

        with open(args.c, "r") as file:
            config = Config(**yaml.safe_load(file)["config"])

        log(f"{config}")

        # Применяем skip-worktree один раз при старте, если ignore есть
        if config.ignore:
            apply_skip_worktree(config.ignore)

        console = Console()  # Глобальный console для очистки

        while True:
            console.clear()  # Стираем предыдущие выводы перед новой проверкой
            if has_differences_with_remote(config.branch, config.ignore):
                console.print("\n    [bold yellow]Syncing ...[/]")
                with console.status("       [bold yellow]Performing reset...", spinner="dots",):
                    # Fetch уже сделан, но на всякий
                    sp.run(["git", "fetch"])
                    reset_result = sp.run(
                        ["git", "reset", "--hard", f"origin/{config.branch}"],
                        capture_output=True, check=False
                    )
                    if reset_result.returncode != 0:
                        console.print(f"       [bold red][ERR] Reset failed[/]: {reset_result.stderr.decode().strip()}")
                    else:
                        console.print("       done", style="bold green")

            sleep(config.interval)
    except KeyboardInterrupt:
        log('exiting...')
        exit(0)

if __name__ == "__main__":
    main()

