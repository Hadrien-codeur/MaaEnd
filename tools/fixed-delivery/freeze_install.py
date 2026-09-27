"""Create and verify a local rollback copy, materializing resource links as real files.

The output may include personal configuration and must never be committed or uploaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


MANIFEST = "fixed-delivery-install.json"
EXCLUDED = {".git", "cache", MANIFEST}


def excluded(name: str, parent: Path) -> bool:
    # Imported facilities and account salt live in debug/record and are required for rollback.
    return (name.lower() in EXCLUDED or name.lower().endswith(".webview2")
            or (parent.as_posix().lower() == "debug" and name.lower() != "record"))


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        result = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
        return result.hexdigest()


def inventory(root: Path) -> dict[str, str]:
    result = {}

    def visit(directory: Path, relative: Path) -> None:
        for item in sorted(directory.iterdir()):
            if excluded(item.name, relative):
                continue
            key = relative / item.name
            if item.is_dir():
                visit(item, key)
            elif item.is_file():
                result[key.as_posix()] = digest(item)

    visit(root, Path())
    return result


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()


def assert_independent(root: Path) -> None:
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            info = path.lstat()
            if path.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError(f"Snapshot still contains a filesystem link: {path}")
            if path.is_file() and info.st_nlink > 1:
                raise ValueError(f"Snapshot still contains a shared hardlink: {path}")


def freeze(source: Path, output: Path, repo: Path, upstream: str) -> dict:
    source, output, repo = source.resolve(), output.resolve(), repo.resolve()
    if output.exists() or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("Snapshot must be a new directory outside the source install")
    if not output.is_relative_to(repo / ".cache"):
        raise ValueError("Private rollback snapshots must remain inside the source repository .cache")
    if git(repo, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("Source repository must be clean before freezing")
    upstream = git(repo, "rev-parse", "--verify", f"{upstream}^{{commit}}")
    git(repo, "merge-base", "--is-ancestor", upstream, "HEAD")
    before = inventory(source)
    for required in ("agent/cpp-algo.exe", "agent/go-service.exe", "interface.json", "version.json",
                     "data/MapNavigator/fixed_zipline_routes.json", "data/AutoDelivery/catalog.json"):
        if required not in before:
            raise ValueError(f"Incomplete installation: {required}")
    # copy2 creates independent files even when source files are hardlinks; follow junctions.
    shutil.copytree(source, output, symlinks=False,
                    ignore=lambda directory, names: [name for name in names if excluded(name, Path(directory).relative_to(source))])
    assert_independent(output)
    copied = inventory(output)
    if copied != before or inventory(source) != before:
        raise ValueError(f"Install changed during snapshot or copy differed; incomplete output retained: {output}")
    report = {
        "schema_version": 1, "private_local_only": True,
        "source_sha": git(repo, "rev-parse", "HEAD"), "upstream_sha": upstream,
        "submodules": git(repo, "submodule", "status", "--recursive").splitlines(),
        "versions": json.loads((source / "version.json").read_text(encoding="utf-8-sig")),
        "lock_hashes": {name: digest(repo / name) for name in
                        ("pnpm-lock.yaml", "uv.lock", "agent/go-service/go.mod", "agent/go-service/go.sum")
                        if (repo / name).is_file()},
        "files": copied, "controller": "Win32-Front",
        "acceptance": "See handoff record; this snapshot verifies file identity, not gameplay",
    }
    (output / MANIFEST).write_text(json.dumps(report, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    return report


def verify(root: Path) -> None:
    assert_independent(root)
    report = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    if inventory(root) != report["files"]:
        raise ValueError("Snapshot files differ from the frozen manifest")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--upstream")
    args = parser.parse_args()
    try:
        if args.verify:
            verify(args.verify)
            print("Frozen installation verified")
        else:
            if not all((args.source, args.output, args.repo, args.upstream)):
                parser.error("freezing requires --source, --output, --repo and --upstream")
            report = freeze(args.source, args.output, args.repo, args.upstream)
            print(f"Frozen {len(report['files'])} files at {args.output}; source {report['source_sha']}")
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Freeze/verification failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
