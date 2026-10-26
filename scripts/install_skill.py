"""Copy the portable skill into Codex or Claude Code without overwriting files."""
import argparse
import shutil
from pathlib import Path

NAME = "domain-network-investigator"
SOURCE = Path(__file__).resolve().parents[1] / "skills" / NAME


def destination(client, project=None, dest=None):
    if project is not None and dest is not None:
        raise ValueError("Choose --project or --dest, not both")
    if dest is not None:
        return Path(dest).expanduser().resolve()
    root = Path(project).expanduser().resolve() if project is not None else Path.home()
    folder = {"codex": ".agents", "claude": ".claude"}[client]
    return root / folder / "skills" / NAME


def install(target):
    target = Path(target).expanduser().resolve()
    if target.exists():
        raise FileExistsError("Installation already exists; preserve local changes before updating: " + str(target))
    if target.is_relative_to(SOURCE):
        raise ValueError("Destination must not be inside the source skill")
    if not (SOURCE / "SKILL.md").is_file():
        raise FileNotFoundError("Missing source SKILL.md")
    shutil.copytree(SOURCE, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store"))
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=("codex", "claude"), required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--project", type=Path, help="Install only for this research project")
    group.add_argument("--dest", type=Path, help="Explicit destination skill folder")
    args = parser.parse_args()
    try:
        result = install(destination(args.client, args.project, args.dest))
    except (ValueError, FileExistsError) as exc:
        parser.error(str(exc))
    print("Installed: " + str(result))
    print("Start a new client session in your research workspace to load the skill.")
