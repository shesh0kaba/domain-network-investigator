"""Build the standalone skill ZIP, excluding research and interpreter caches."""
import argparse
import hashlib
import zipfile
from pathlib import Path

NAME = "domain-network-investigator"
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills" / NAME


def source_files():
    files = [SOURCE / "SKILL.md", SOURCE / "LICENSE"]
    for folder, suffix in (("scripts", ".py"), ("references", ".md"), ("agents", ".yaml")):
        files.extend(sorted((SOURCE / folder).glob("*" + suffix)))
    if any(not path.is_file() for path in files):
        raise ValueError("A required skill file is missing")
    return files


def package(out):
    out = Path(out).resolve()
    if out.is_relative_to(SOURCE):
        raise ValueError("Build outside the source skill")
    out.mkdir(parents=True, exist_ok=True)
    archive = out / (NAME + ".zip")
    if archive.exists():
        raise FileExistsError("Package already exists; use a new output directory")
    files = source_files()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            info = zipfile.ZipInfo((Path(NAME) / path.relative_to(SOURCE)).as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (out / "SHA256SUMS.txt").write_text(digest + "  " + archive.name + "\n", encoding="utf-8")
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(package(args.out))
    except (ValueError, FileExistsError) as exc:
        parser.error(str(exc))
