"""WSL-side launcher. Only the disposable child receives course code."""
import argparse
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / "work" / "sandbox"


def launch(course, profile, timeout=45):
    course = Path(course).resolve(strict=True)
    if not course.is_relative_to(ROOT / "work") or not course.is_dir():
        raise ValueError("Sandbox input must be a project working copy")
    if profile not in ("stdlib", "numpy", "pandas"):
        raise ValueError("Unsupported environment profile")
    command = [str(RUNTIME / "bubblewrap/usr/bin/bwrap"), "--unshare-all", "--unshare-user", "--disable-userns",
               "--die-with-parent", "--new-session", "--cap-drop", "ALL", "--uid", "65534", "--gid", "65534",
               "--clearenv", "--setenv", "HOME", "/tmp", "--setenv", "LANG", "C.UTF-8",
               "--setenv", "OPENBLAS_NUM_THREADS", "1", "--setenv", "OMP_NUM_THREADS", "1",
               "--setenv", "NUMEXPR_NUM_THREADS", "1", "--ro-bind", "/usr/lib", "/usr/lib",
               "--symlink", "usr/lib", "/lib", "--ro-bind", "/usr/lib64", "/usr/lib64",
               "--symlink", "usr/lib64", "/lib64", "--ro-bind", str(RUNTIME / "python"), "/runtime",
               "--ro-bind", str(RUNTIME / "profiles" / profile), "/runtime/lib/python3.11/site-packages",
               "--ro-bind", str(ROOT / "sandbox_worker.py"), "/worker.py", "--ro-bind", str(course), "/course",
               "--proc", "/proc", "--dev", "/dev", "--size", "67108864", "--tmpfs", "/tmp",
               "--dir", "/etc", "--chdir", "/course", "/runtime/bin/python3.11", "-I", "-B", "/worker.py"]
    started = time.perf_counter()
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                   start_new_session=True, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
        expired = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            expired = True
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        stdout.seek(0)
        stderr.seek(0)
        raw, errors = stdout.read(1024 * 1024 + 1), stderr.read(65536)
    return {"exit_code": process.returncode, "timed_out": expired,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "stdout": raw.decode("utf-8", "replace"), "stderr": errors.decode("utf-8", "replace"),
            "output_overflow": len(raw) > 1024 * 1024,
            "isolation": {"backend": "wsl_bubblewrap", "network": "isolated", "inputs": "read_only",
                          "temporary_storage_mib": 64, "memory_limit_mib": 1536,
                          "cpu_limit_seconds": 30, "wall_limit_seconds": timeout, "profile": profile}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("course")
    parser.add_argument("profile", choices=("stdlib", "numpy", "pandas"))
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024 * 1024, 2 * 1024 * 1024))
    print(json.dumps(launch(args.course, args.profile, args.timeout), ensure_ascii=False))
