"""Run actual isolation probes: python verify_sandbox.py (requires prepared WSL)."""
import json
from pathlib import Path
from uuid import uuid4

from prepare_runtime import ROOT
from runner import run_sandbox


def probe(source, timeout=15):
    folder = ROOT / "work" / "sandbox-probes" / uuid4().hex
    folder.mkdir(parents=True)
    (folder / "lesson.ipynb").write_text(json.dumps({"cells": [
        {"id": "probe", "cell_type": "code", "source": source}]}), encoding="utf-8")
    return run_sandbox(folder, "stdlib", timeout)


def main():
    result = probe('''import json, os, socket
from pathlib import Path
checks = {"uid": os.getuid(), "host_hidden": not Path("/mnt").exists() and not Path("/home").exists(),
          "contract_hidden": not Path("/course/acceptance.json").exists()}
try:
    Path("/course/changed.txt").write_text("test")
    checks["read_only"] = False
except OSError:
    checks["read_only"] = True
try:
    socket.create_connection(("1.1.1.1", 443), timeout=1)
    checks["network_isolated"] = False
except OSError:
    checks["network_isolated"] = True
Path("/tmp/probe.txt").write_text("temporary")
checks["temporary_write"] = Path("/tmp/probe.txt").read_text() == "temporary"
print(json.dumps(checks))
''')
    assert result["exit_code"] == 0, result
    step = result["run"]["steps"][0]
    assert step["outcome"] == "ok", step
    checks = json.loads(step["stdout"])
    assert checks == {"uid": 65534, "host_hidden": True, "contract_hidden": True,
                      "read_only": True, "network_isolated": True, "temporary_write": True}, checks
    timeout = probe("while True: pass", timeout=2)
    assert timeout["timed_out"] and not timeout["run"]["complete"], timeout
    print("隔离验证通过：网络、主机路径、验收文件、只读输入、临时目录及超时终止。")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    main()
