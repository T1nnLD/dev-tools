import yaml
import argparse
import subprocess as sp
from pydantic import BaseModel
from pydantic import field_validator
from dev_tools.logging import log
from time import sleep
from rich.console import Console
from typing import List, Optional
import os

class Config(BaseModel):
    branch: str
    interval: float = 1
    ignore: Optional[List[str]] = None  # Список путей/паттернов для игнора
    deploy: Optional[List[str]] = None  # Список команд для deploy после sync

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

def generate_sudoers_file(config: Config):
    if not config.deploy:
        return  # Нет deploy — ничего не делаем

    username = os.getlogin()  # Текущий пользователь
    sudoers_file = "/etc/sudoers.d/deploy-access"
    sudoers_content = f"{username} ALL=(ALL) NOPASSWD: "

    # Извлекаем команды с sudo и форматируем для sudoers
    sudo_commands = []
    for cmd in config.deploy:
        if cmd.startswith("sudo "):
            full_cmd = cmd[5:].strip()
            parts = full_cmd.split()
            if not parts:
                continue

            # Находим полный путь к бинарнику
            bin_path = sp.run(["which", parts[0]], capture_output=True, text=True).stdout.strip()
            if not bin_path:
                log(f"[WARN] Command not found: {parts[0]}", "yellow")
                continue

            sudo_cmd = bin_path + " " + " ".join(parts[1:])
            sudo_commands.append(sudo_cmd)

    if not sudo_commands:
        return

    sudoers_content += ", ".join(sudo_commands)
    sudoers_content += "\n"

    # Проверяем существующий файл
    try:
        with open(sudoers_file, "r") as f:
            existing = f.read()
            if existing == sudoers_content:
                log("Sudoers file already up-to-date", "green")
                return
    except FileNotFoundError:
        pass

    # Записываем через sudo tee
    try:
        sp.run(["sudo", "tee", sudoers_file], input=sudoers_content, text=True, check=True)
        sp.run(["sudo", "chmod", "0440", sudoers_file], check=True)
        log("Sudoers file generated/updated successfully", "green")
    except sp.CalledProcessError as e:
        log(f"[ERR] Failed to generate sudoers: {e}", "red")

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
                             "ignore": ['git-sync.conf.yaml'],
                             "deploy": []
                            }
                        }
                
                yaml.dump(config, file, indent=2)
                log(f"Configuration file generated with branch: {current_branch}")
            exit(0)

        with open(args.c, "r") as file:
            config = Config(**yaml.safe_load(file)["config"])

        log(f"{config}")

        # Генерируем sudoers на основе deploy
        generate_sudoers_file(config)

        # Применяем skip-worktree один раз при старте, если ignore есть
        if config.ignore:
            apply_skip_worktree(config.ignore)

        console = Console()  # Глобальный console для очистки

        while True:
            #console.clear()  # Стираем предыдущие выводы перед новой проверкой
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

                        if config.deploy:
                            console.print("\n    [bold yellow]Deploying ...[/]")
                            for raw_cmd in config.deploy:
                                cmd = raw_cmd.strip()
                                background = cmd.endswith("&")
                                cmd = cmd.rstrip("&").strip()   # убираем & из команды

                                with console.status(f"       [bold yellow]Running: {cmd} ...[/]", spinner="dots"):
                                    if background:
                                        # Запускаем в фоне и НЕ ждём
                                        sp.Popen(cmd, shell=True)
                                        console.print("       started in background", style="bold green")
                                    else:
                                        # Обычная команда — ждём завершения
                                        deploy_result = sp.run(cmd, shell=True, capture_output=True, text=True)
                                        if deploy_result.returncode != 0:
                                            console.print(f"       [bold red][ERR] Deploy command failed[/]: {deploy_result.stderr.strip()}")
                                        else:
                                            console.print(f"       done (output: {deploy_result.stdout.strip()})", style="bold green")
            sleep(config.interval)
    except KeyboardInterrupt:
        log('exiting...')
        exit(0)

if __name__ == "__main__":
    main()
