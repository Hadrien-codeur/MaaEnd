"""Fetch a pinned upstream revision and merge it in an isolated candidate worktree."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=check, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )


def value(root: Path, *args: str) -> str:
    return git(root, *args).stdout.strip()


def changed(root: Path, base: str, head: str) -> list[str]:
    return value(root, "diff", "--name-only", base, head).splitlines()


def stage(root: Path, target: str, remote: str, branch: str, candidate: Path | None = None) -> dict:
    root = Path(value(root, "rev-parse", "--show-toplevel")).resolve()
    dirty = value(root, "status", "--porcelain=v1", "--untracked-files=all")
    if dirty:
        raise ValueError("Source worktree must be clean; commit the adaptation/tools before staging")
    baseline = value(root, "rev-parse", "HEAD")
    # Fetch into an explicit tracking ref: remote.origin.fetch may be unset in this project.
    tracking = f"refs/remotes/{remote}/{branch}"
    git(root, "fetch", "--no-recurse-submodules", remote, f"+refs/heads/{branch}:{tracking}")
    upstream = value(root, "rev-parse", "--verify", f"{target}^{{commit}}")
    if git(root, "merge-base", "--is-ancestor", upstream, tracking, check=False).returncode:
        raise ValueError("Pinned target is not part of the freshly fetched upstream branch")
    base = value(root, "merge-base", baseline, upstream)
    if upstream == base:
        raise ValueError("Baseline already contains the target upstream revision")
    common_dir = Path(value(root, "rev-parse", "--git-common-dir"))
    if not common_dir.is_absolute():
        common_dir = root / common_dir
    cache = common_dir.resolve().parent / ".cache"
    candidate = (candidate or cache / f"fixed-delivery-update-{upstream[:12]}").resolve()
    if not candidate.is_relative_to(cache) or candidate == cache or candidate.exists():
        raise ValueError("Candidate must be a new directory below the shared repository's .cache")
    candidate_branch = f"codex/fixed-delivery-update-{upstream[:12]}"
    report = {
        "baseline_sha": baseline, "previous_upstream_sha": base, "upstream_sha": upstream,
        "upstream_changes": changed(root, base, upstream),
        "adapter_changes": changed(root, base, baseline),
        "commits": value(root, "log", "--format=%H %s", f"{base}..{upstream}").splitlines(),
        "candidate": str(candidate), "branch": candidate_branch,
        "status": "pending", "validation": "not_run", "activation": "not_performed",
    }
    report["overlap"] = sorted(set(report["upstream_changes"]) & set(report["adapter_changes"]))
    git(root, "worktree", "add", "-b", candidate_branch, str(candidate), baseline)
    merge = git(candidate, "merge", "--no-commit", "--no-ff", upstream, check=False)
    report["merge_output"] = merge.stdout + merge.stderr
    report["conflicts"] = value(candidate, "diff", "--name-only", "--diff-filter=U").splitlines()
    report["status"] = "merge_failed" if merge.returncode else "merged_needs_validation"
    report_path = candidate / ".cache" / "upstream-update.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--target", required=True, help="Reviewed upstream commit SHA; never an implicit latest")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default="v2")
    parser.add_argument("--candidate", type=Path)
    args = parser.parse_args()
    try:
        report = stage(args.root, args.target, args.remote, args.branch, args.candidate)
        print(json.dumps(report, ensure_ascii=False, indent=4))
        return 1 if report["status"] == "merge_failed" else 0
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Update stopped: {error}", file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
