"""Host-side runner; contracts stay outside the lesson's namespace."""
import hashlib
import subprocess

from check_course import parse_json, read_file
from prepare_runtime import ROOT, DISTRO, linux_path


PROFILES = {"stdlib": {}, "numpy": {"numpy": "1.26.4"},
            "pandas": {"numpy": "1.26.4", "pandas": "2.2.3"}}


def profile_for(environment):
    for profile, packages in PROFILES.items():
        if environment == {"python": "3.11.15", "packages": packages}:
            return profile
    raise ValueError("当前隔离环境支持 Python 3.11.15、NumPy 1.26.4、pandas 2.2.3 的三种组合")


def run_sandbox(course, profile, timeout=45):
    command = ["wsl.exe", "-d", DISTRO, "--exec", "/usr/bin/python3",
               linux_path(ROOT / "sandbox_linux.py"), linux_path(course), profile, "--timeout", str(timeout)]
    result = subprocess.run(command, capture_output=True, timeout=timeout + 35,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError("隔离环境启动失败：" + result.stderr.decode("utf-8", "replace")[-3000:])
    envelope = parse_json(result.stdout)
    if envelope["exit_code"] != 0 or envelope["timed_out"] or envelope["output_overflow"]:
        envelope["run"] = {"schema_version": 1, "complete": False, "steps": [],
                           "runner_error": "执行超时或中断；" + envelope["stderr"][-2000:]}
    else:
        try:
            envelope["run"] = parse_json(envelope["stdout"].encode("utf-8"))
        except (ValueError, TypeError):
            envelope["run"] = {"schema_version": 1, "complete": False, "steps": [],
                               "runner_error": "执行记录无法读取"}
    return envelope


def execute_course(course, manifest, destination):
    """Copy only declared learner files to a fresh, read-only sandbox mount."""
    destination.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for name in manifest["learner_files"]:
        data = read_file(course, name)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    result = run_sandbox(destination, profile_for(manifest["environment"]))
    result["input_hashes"] = hashes
    observed = result["run"]
    result["environment_matches"] = (observed.get("python") == manifest["environment"]["python"]
                                      and observed.get("packages") == manifest["environment"]["packages"])
    return result
