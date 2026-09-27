"""Run candidate gates and save exact source/binary identity; never certify gameplay or activate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[2]


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True, encoding="utf-8").strip()


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        result = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
        return result.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--native", action="store_true", help="Replay installed production Agent against local facilities; no game input")
    args = parser.parse_args()
    if git("status", "--porcelain=v1", "--untracked-files=all"):
        parser.error("Commit the candidate first: validation must identify a clean source revision")
    upstream = git("rev-parse", "--verify", f"{args.upstream}^{{commit}}")
    git("merge-base", "--is-ancestor", upstream, "HEAD")
    output = ROOT / ".cache/fixed-delivery-validation"
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "source_sha": git("rev-parse", "HEAD"), "source_tree": git("rev-parse", "HEAD^{tree}"),
        "upstream_sha": upstream, "submodules": git("submodule", "status", "--recursive").splitlines(),
        "started_at": datetime.now(timezone.utc).isoformat(), "status": "running", "checks": [],
        "gameplay": "pending", "activation": "not_performed", "maa_version": "5.13.0",
    }
    report_path = output / "report.json"

    def save() -> None:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")

    tests = sorted(str(path.relative_to(ROOT)) for folder in ("AutoDelivery", "DeliveryJobs", "SeizeDeliveryJobs")
                   for path in (ROOT / "tools/pipeline-generate" / folder).glob("*.test.mjs"))
    maa = ["node", "node_modules/@nekosu/maa-tools/bin/maa-tools"]
    config = "tools/fixed-delivery/maatools.config.mts"
    commands = [
        ("tool-tests", [sys.executable, "-m", "unittest", "discover", "-s", "tools/fixed-delivery/tests"]),
        ("contract", [sys.executable, "tools/fixed-delivery/check_compatibility.py", "--json"]),
        ("generator-tests", ["node", "--test", *tests]),
        ("go-tests", ["go", "-C", "agent/go-service", "test", "./autodelivery"]),
        ("cpp-tests", ["ctest", "--test-dir", ".cache/cpp-build-utf8", "--output-on-failure", "--no-tests=error"]),
        ("schema", [sys.executable, "tools/validate_schema.py", "--resource-dirs", "assets/resource",
                    "--exclude-dirs", "assets/resource/gamedata", "assets/resource/image", "assets/resource/model",
                    "--task-dirs", "assets/tasks"]),
        ("resource-check", [*maa, "check", config]),
        ("node-tests", [*maa, "test", config]),
    ]
    if args.native:
        commands.append(("native-replay", [sys.executable, "tools/fixed-delivery/replay_routes.py"]))
    save()
    try:
        for name, command in commands:
            print(f"Running {name}", flush=True)
            log = output / f"{name}.log"
            with log.open("w", encoding="utf-8") as stream:
                result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
            report["checks"].append({"name": name, "command": command, "exit_code": result.returncode,
                                     "log": log.name, "log_sha256": sha256(log)})
            save()
            if result.returncode:
                raise RuntimeError(f"{name} failed; see {log}")
        if git("status", "--porcelain=v1", "--untracked-files=all"):
            raise RuntimeError("Source changed during validation")
        for relative in ("agent/cpp-algo.exe", "agent/go-service.exe", "data/MapNavigator/fixed_zipline_routes.json",
                         "data/AutoDelivery/catalog.json", "maafw/MaaFramework.dll"):
            path = ROOT / "install" / relative
            report.setdefault("install_hashes", {})[relative] = sha256(path)
        if sha256(ROOT / ".cache/cpp-build-utf8/bin/cpp-algo.exe") != report["install_hashes"]["agent/cpp-algo.exe"]:
            raise RuntimeError("Installed C++ Agent differs from the tested build")
        report["status"] = "ready_for_gameplay" if args.native else "offline_checks_passed_replay_pending"
        report["completed_at"] = datetime.now(timezone.utc).isoformat()
        save()
        print(f"{report['status']}: {report_path}")
        return 0
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        report["status"] = "failed"
        report["error"] = str(error)
        save()
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
