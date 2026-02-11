import yaml
import argparse
import subprocess as sp
from pydantic import BaseModel
from pydantic import field_validator
from dev_tools.logging import log
from time import sleep
from rich.console import Console
from rich.spinner import Spinner


class Config(BaseModel):
    branch: str
    interval: float = 1
    strategy: str

    @field_validator("strategy")
    def check_strategy(cls, v: str) -> str:
        if v != "sync" and v != "manual":
            raise ValueError('strategy can only be "sync" or "manual"!')
        return v.title()

    @field_validator("interval")
    def check_interval(cls, v: float) -> float:
        if v < 0:
            raise ValueError("interval cannot be negative")
        return v


def get_diff(branch: str) -> bool:
    # Create a console and spinner for animation
    console = Console()
    spinner = Spinner("dots", "checking for differences")
    with console.status("[bold green]Checking for differences...", spinner="dots"):
        # TODO: Consider using non-shell execution to prevent potential shell injection
        output = sp.run(
            f"git fetch && git diff {branch} origin/{branch}",
            capture_output=True,
            shell=True,
            stdout=sp.PIPE,
            stderr=sp.PIPE,
        )
    if output.stderr.decode():
        log(f"[ERR] {output.stderr.decode()}", "red")
        # TODO: Add more sophisticated error handling based on specific git error types
        return False
    if output.stdout.decode():
        return True
    else:
        return False


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-c",
        type=str,
        default="./git-sync.conf.yaml",
        help="path to config, default value = ./git-sync.conf.yaml",
    )
    parser.add_argument(
        "--generate-config", action="store_true", help="generate baseline config"
    )
    args = parser.parse_args()

    if args.generate_config:
        # Get the current branch name
        result = sp.run(
            ["git", "branch", "--show-current"], capture_output=True, text=True
        )
        current_branch = result.stdout.strip() if result.stdout.strip() else "main"

        with open("./git-sync.conf.yaml", "w") as file:
            config = {
                "config": {"branch": current_branch, "interval": 1, "strategy": "sync"}
            }
            yaml.dump(config, file, indent=2)
            log(f"Configuration file generated with branch: {current_branch}")
            exit(0)

    with open(args.c, "r") as file:
        config = Config(**yaml.safe_load(file)["config"])

    log(f"{config}")

    while True:
        if get_diff(config.branch):
            if config.strategy == "sync":
                # Add spinner animation for git pull
                console = Console()
                with console.status(
                    "[bold green]Pulling repository...", spinner="dots"
                ):
                    # TODO: Consider using non-shell execution to prevent potential shell injection
                    sp.run("git pull", shell=True)
                log("repository pulled", "green")
            elif config.strategy == "manual":
                selected = False
                while not selected:
                    solution = input(
                        "The differences between the repositories are hidden, do a git pull? [Y/n]"
                    )
                    if solution.lower() == "" or solution.lower() == "y":
                        # Add spinner animation for git pull
                        console = Console()
                        with console.status(
                            "[bold green]Pulling repository...", spinner="dots"
                        ):
                            # TODO: Consider using non-shell execution to prevent potential shell injection
                            sp.run("git pull", shell=True)
                        log("repository pulled", "green")
                        selected = True
                    elif solution.lower() == "n":
                        log("the repository state has not changed")
                        selected = True

        sleep(config.interval)


if __name__ == "__main__":
    main()
