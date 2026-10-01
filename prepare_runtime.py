"""Prepare project-local Python and bubblewrap for the WSL lesson runner."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import zipfile
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / "work" / "sandbox"
DISTRO = "Ubuntu-24.04"
PYTHON_URL = "https://releases.astral.sh/github/python-build-standalone/releases/download/20260602/cpython-3.11.15%2B20260602-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
PYTHON_SHA = "4b79bcb83a22961c8972f8d1d4780bd8925f0b52688d95b090a488f31c8b1139"
BWRAP_URL = "https://security.ubuntu.com/ubuntu/pool/main/b/bubblewrap/bubblewrap_0.9.0-1ubuntu0.1_amd64.deb"
BWRAP_SHA = "1b506492bd9c7fd0cdb4f02ac822f1d3e336b0aead5113c1239baf8db5db562a"


def linux_path(path):
    path = Path(path).resolve()
    if os.name != "nt":
        return str(path)
    if not path.drive or len(path.drive) != 2:
        raise ValueError("WSL 运行目录需要位于本地盘符下")
    return "/mnt/" + path.drive[0].lower() + path.as_posix()[2:]


def wsl(*args, **kwargs):
    return subprocess.run(["wsl.exe", "-d", DISTRO, "--exec", *args], check=True,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), **kwargs)


def download(url, destination, digest):
    if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == digest:
        return
    temporary = destination.with_suffix(destination.suffix + ".download")
    with urlopen(Request(url, headers={"User-Agent": "LessonProof-runtime-setup"}), timeout=60) as response, temporary.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    if hashlib.sha256(temporary.read_bytes()).hexdigest() != digest:
        raise ValueError(f"下载校验失败：{destination.name}")
    temporary.replace(destination)


def main():
    if os.name != "nt":
        raise SystemExit("此准备入口用于 Windows + Ubuntu-24.04 WSL。")
    if not RUNTIME.resolve().is_relative_to(ROOT):
        raise ValueError("运行环境目录应位于项目内")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    wsl("unshare", "--user", "--map-root-user", "--net", "--pid", "--fork", "/bin/true", timeout=20)
    print("准备隔离运行工具和固定版本 Python…", flush=True)
    download(BWRAP_URL, RUNTIME / "bubblewrap.deb", BWRAP_SHA)
    download(PYTHON_URL, RUNTIME / "python.tar.gz", PYTHON_SHA)
    base = linux_path(RUNTIME)
    wsl("dpkg-deb", "-x", base + "/bubblewrap.deb", base + "/bubblewrap", timeout=30)
    if not (RUNTIME / "python" / "bin" / "python3.11").exists():
        wsl("tar", "-xzf", base + "/python.tar.gz", "-C", base, timeout=120)
    wheels = RUNTIME / "wheels"
    wheels.mkdir(exist_ok=True)
    print("下载课程环境依赖到项目目录…", flush=True)
    subprocess.run(["uv", "--cache-dir", str(RUNTIME / "download-cache"), "tool", "run", "--from", "pip", "pip",
                    "--isolated", "download", "--index-url", "https://pypi.org/simple",
                    "--dest", str(wheels), "--python-version", "311", "--implementation", "cp", "--abi", "cp311",
                    "--platform", "manylinux_2_17_x86_64", "--only-binary=:all:", "--require-hashes",
                    "-r", str(ROOT / "runtime-requirements.txt")], check=True)
    expected = {line.split("--hash=sha256:")[1].strip() for line in (ROOT / "runtime-requirements.txt").read_text().splitlines() if line.strip()}
    selected = [wheel for wheel in wheels.glob("*.whl") if hashlib.sha256(wheel.read_bytes()).hexdigest() in expected]
    if len(selected) != len(expected):
        raise ValueError("课程依赖文件校验不完整")
    python = base + "/python/bin/python3.11"
    (RUNTIME / "profiles" / "stdlib").mkdir(parents=True, exist_ok=True)
    # These six wheels use a flat purelib/platlib layout. Extracting on Windows
    # avoids thousands of slow cross-filesystem writes through WSL's /mnt mount.
    for profile in ("numpy", "pandas"):
        target = RUNTIME / "profiles" / profile
        if not target.resolve().is_relative_to(RUNTIME.resolve()):
            raise ValueError("课程依赖目录越界")
        target.mkdir(parents=True, exist_ok=True)
        for wheel in selected:
            if profile == "numpy" and not wheel.name.startswith("numpy-"):
                continue
            with zipfile.ZipFile(wheel) as archive:
                for member in archive.infolist():
                    destination = (target / member.filename).resolve()
                    if not destination.is_relative_to(target.resolve()) or ".data/" in member.filename:
                        raise ValueError("依赖包布局不受支持")
                archive.extractall(target)
    wsl(python, "--version", timeout=30)
    wsl(base + "/bubblewrap/usr/bin/bwrap", "--version", timeout=15)
    print("运行环境准备完成。", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
