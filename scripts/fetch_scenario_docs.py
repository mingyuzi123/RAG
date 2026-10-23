"""Fetch a scenario's pinned official Git documentation with sparse checkout."""

from argparse import ArgumentParser
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raglab.store import load_manifest  # noqa: E402


def fetch(manifest_path: Path) -> Path:
    manifest = load_manifest(manifest_path)
    target = (ROOT / manifest["local_checkout"]).resolve()
    expected_parent = (ROOT / "data" / "upstream").resolve()
    if not target.is_relative_to(expected_parent) or target == expected_parent:
        raise ValueError("local_checkout must be inside data/upstream/")
    commit = manifest["upstream_commit"]
    needs_fetch = True
    if target.exists():
        if not (target / ".git").is_dir():
            raise ValueError(f"Existing source path is not a Git checkout: {target}")
        actual = subprocess.run(["git", "-c", f"safe.directory={target.as_posix()}",
                                 "-C", str(target), "rev-parse", "HEAD"],
                                capture_output=True, text=True)
        if actual.returncode == 0 and actual.stdout.strip() != commit:
            raise ValueError(f"Existing source is at {actual.stdout.strip()}, expected {commit}")
        needs_fetch = actual.returncode != 0
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.mkdir()
        subprocess.run(["git", "init", str(target)], check=True)
        subprocess.run(["git", "-C", str(target), "remote", "add", "origin",
                        manifest["upstream_repo"]], check=True)
    if needs_fetch:
        subprocess.run(["git", "-c", f"safe.directory={target.as_posix()}",
                        "-C", str(target), "fetch", "--filter=blob:none", "--depth=1",
                        "origin", commit], check=True)
    subprocess.run(["git", "-c", f"safe.directory={target.as_posix()}", "-C", str(target),
                    "sparse-checkout", "set", "--no-cone",
                    *("/" + path for path in manifest["files"])], check=True)
    subprocess.run(["git", "-c", f"safe.directory={target.as_posix()}", "-C", str(target),
                    "checkout", "--detach", commit], check=True)
    for relative in manifest["files"]:
        if not (target / relative).is_file():
            raise FileNotFoundError(f"Pinned source missing: {relative}")
    return target


def main() -> None:
    cli = ArgumentParser()
    cli.add_argument("--scenario", type=Path, required=True)
    args = cli.parse_args()
    target = fetch(args.scenario)
    print(f"Pinned documentation ready: {target}")


if __name__ == "__main__":
    main()
