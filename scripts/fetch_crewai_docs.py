"""Fetch the pinned, sparse CrewAI documentation snapshot for local experiments."""

from pathlib import Path
import json
import subprocess


ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "scenarios" / "crewai" / "manifest.json").read_text(encoding="utf-8"))
target = ROOT / manifest["local_checkout"]
commit = manifest["upstream_commit"]


def git(*args: str) -> None:
    subprocess.run(["git", "-c", f"safe.directory={target.as_posix()}", *args], check=True)


if target.exists():
    if not (target / ".git").is_dir():
        raise SystemExit(f"Existing path is not a Git checkout: {target}")
    current = subprocess.check_output(
        ["git", "-c", f"safe.directory={target.as_posix()}", "-C", str(target), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    if current != commit:
        raise SystemExit(f"Existing checkout is at {current}, expected {commit}; inspect it before changing it")
else:
    target.parent.mkdir(parents=True, exist_ok=True)
    git("clone", "--filter=blob:none", "--sparse", "--no-checkout", manifest["upstream_repo"], str(target))
    git("-C", str(target), "fetch", "--depth=1", "origin", commit)
    git("-C", str(target), "checkout", "--detach", commit)

git("-C", str(target), "sparse-checkout", "set", "--no-cone", *("/" + path for path in manifest["files"]))
print(f"CrewAI documentation ready at {target} ({commit})")
