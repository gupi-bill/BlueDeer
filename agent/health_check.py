"""BlueDeer Agent Health Check."""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


class Result:
    def __init__(self, name, passed, detail="", suggestion=""):
        self.name = name
        self.passed = passed
        self.detail = detail
        self.suggestion = suggestion

    def to_dict(self):
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "suggestion": self.suggestion,
        }


def _ensure_sys_path():
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def check_python():
    v = sys.version_info
    ok = v.major == 3 and v.minor >= 9
    return Result(
        "Python version", ok,
        f"{v.major}.{v.minor}.{v.micro}",
        "Python 3.9+ required" if not ok else "",
    )


def check_imports():
    _ensure_sys_path()
    mods = ["core", "web_server", "agent", "memory_archive"]
    missing = [m for m in mods if importlib.util.find_spec(m) is None]
    ok = len(missing) == 0
    if missing:
        detail = "missing: " + ", ".join(missing)
    else:
        detail = "OK (" + str(len(mods)) + " modules)"
    sug = "pip install -r requirements.txt" if missing else ""
    return Result("Core imports", ok, detail, sug)


def check_project():
    root = Path(__file__).resolve().parents[1]
    expected = ["core", "web_server", "tests", "agent", "BlueDeer-Agent", "BlueDeer-Console"]
    missing = [d for d in expected if not (root / d).is_dir()]
    ok = len(missing) == 0
    if missing:
        detail = "missing dirs: " + ", ".join(missing)
    else:
        detail = "OK (" + str(len(expected)) + " dirs)"
    return Result("Project structure", ok, detail)


def check_config():
    root = Path(__file__).resolve().parents[1]
    candidates = [
        root / "agent" / "config.json",
        root / "BlueDeer-Agent" / "bluedeer" / "config.json",
        root / "BlueDeer-Agent" / "config.json",
    ]
    found = None
    for c in candidates:
        if c.exists():
            found = c
            break
    if not found:
        return Result("Config", False, "config.json not found in expected locations", "")
    try:
        cfg = json.loads(found.read_text(encoding="utf-8"))
        api_model = cfg.get("api_model", "unknown")
        return Result("Config", True, "model=" + str(api_model) + " @ " + found.name, "")
    except Exception as e:
        return Result("Config", False, "JSON error: " + str(e), "")


def check_deps():
    deps = ["fastapi", "uvicorn", "sqlalchemy", "pydantic"]
    missing = [d for d in deps if importlib.util.find_spec(d) is None]
    ok = len(missing) == 0
    if missing:
        detail = "missing: " + ", ".join(missing)
    else:
        detail = "all ok"
    sug = "pip install fastapi uvicorn sqlalchemy pydantic" if missing else ""
    return Result("Dependencies", ok, detail, sug)


def check_ruff():
    try:
        root = Path(__file__).resolve().parents[1]
        r = subprocess.run(
            [sys.executable, "-m", "ruff", "check", ".", "--no-cache"],
            capture_output=True, text=True, cwd=root, timeout=60,
        )
        count = 0
        for line in r.stdout.splitlines():
            if line.startswith("Found"):
                try:
                    count = int(line.split()[0])
                except ValueError:
                    pass
                break
        ok = count == 0
        detail = "Found " + str(count) + " errors" if count > 0 else "0 errors"
        return Result("Ruff", ok, detail)
    except FileNotFoundError:
        return Result("Ruff", False, "ruff not installed", "pip install ruff")
    except subprocess.TimeoutExpired:
        return Result("Ruff", False, "timeout")
    except Exception as e:
        return Result("Ruff", False, "error: " + str(e))


def check_tests():
    try:
        root = Path(__file__).resolve().parents[1]
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line"],
            capture_output=True, text=True, cwd=root, timeout=120,
        )
        out = r.stdout + r.stderr
        passed = failed = 0
        for line in out.splitlines():
            lw = line.lower()
            for kw in ("passed", "failed"):
                if kw in lw:
                    parts = line.split()
                    for i, p in enumerate(parts):
                        if p == kw and i > 0:
                            try:
                                val = int(parts[i - 1])
                                if kw == "passed":
                                    passed = val
                                else:
                                    failed = val
                            except ValueError:
                                pass
        ok = failed == 0 and passed > 0
        detail = str(passed) + " passed, " + str(failed) + " failed"
        sug = "fix failing tests" if failed > 0 else ""
        return Result("Tests", ok, detail, sug)
    except FileNotFoundError:
        return Result("Tests", False, "pytest not installed", "pip install pytest")
    except subprocess.TimeoutExpired:
        return Result("Tests", False, "timeout")
    except Exception as e:
        return Result("Tests", False, "error: " + str(e))


def check_git():
    try:
        root = Path(__file__).resolve().parents[1]
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=root, timeout=10,
        )
        changes = r.stdout.strip()
        ok = changes == ""
        if not changes:
            detail = "working tree clean"
        else:
            detail = str(len(changes.splitlines())) + " changes"
        sug = "git add and git commit" if changes else ""
        return Result("Git", ok, detail, sug)
    except FileNotFoundError:
        return Result("Git", False, "git not installed")
    except Exception as e:
        return Result("Git", False, "error: " + str(e))


def check_secrets():
    root = Path(__file__).resolve().parents[1]
    patterns = ["sk-live-", "ghp_", "ghs_"]
    skip_dirs = {".git", "__pycache__", "node_modules", "data", "vector_db", ".venv", ".cache"}
    skip_ext = {".db", ".json", ".log", ".txt", ".md", ".html", ".css", ".js"}
    skip_files = {"health_check.py"}
    found = []
    for pat in patterns:
        r = subprocess.run(
            ["git", "log", "--all", "--pretty=format:", "--name-only"],
            capture_output=True, text=True, cwd=root, timeout=10,
        )
        for line in r.stdout.splitlines():
            fp = root / line.strip()
            if not fp.exists():
                continue
            rel = str(fp.relative_to(root))
            skip = any(d in rel.split("\\") or d in rel.split("/") for d in skip_dirs)
            if skip or fp.suffix in skip_ext or "test_" in fp.name or fp.name in skip_files:
                continue
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
                if pat in content:
                    found.append(fp.name + " (" + pat + ")")
            except Exception:
                pass
    ok = len(found) == 0
    detail = "found " + str(len(found)) + " potential secrets" if found else "no secrets detected"
    sug = "remove hardcoded keys" if found else ""
    return Result("Secrets check", ok, detail, sug)


def run_checks(quick=False):
    checks = [check_python, check_imports, check_project, check_config, check_deps, check_secrets, check_git]
    if not quick:
        checks.extend([check_ruff, check_tests])
    results = []
    for ck in checks:
        try:
            r = ck()
            if isinstance(r, tuple):
                r = r[0]
            results.append(r)
        except Exception as e:
            results.append(Result(ck.__name__, False, "error: " + str(e)))
    return results


def print_report(results, json_out=False):
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    report = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "results": [r.to_dict() for r in results],
        "summary": "PASS" if failed == 0 else "FAIL",
    }
    if json_out:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return report
    print("=" * 60)
    print("  BlueDeer Agent Health Check")
    print("=" * 60)
    print()
    for r in results:
        icon = "OK" if r.passed else "FAIL"
        reset = "\033[0m"
        yellow = "\033[93m"
        green = "\033[92m"
        red = "\033[91m"
        if r.passed:
            color = green
        else:
            color = red
        print("  [" + icon + "] " + r.name)
        print("        " + r.detail)
        if r.suggestion:
            print("        " + yellow + "Suggestion: " + r.suggestion + reset)
        print()
    status = str(passed) + "/" + str(total) + " passed"
    if failed > 0:
        status = color + status + " (" + str(failed) + " failed)" + reset
    else:
        status = color + status + reset
    print("-" * 60)
    print("  Total: " + status)
    print("=" * 60)
    return report


def main():
    parser = argparse.ArgumentParser(description="BlueDeer Agent Health Check")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--quick", action="store_true", help="Quick mode")
    args = parser.parse_args()
    results = run_checks(quick=args.quick)
    print_report(results, json_out=args.json)
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
