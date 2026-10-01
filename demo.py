"""Replay the repository's first-party development examples in child processes.

This is a developer test tool, not an execution sandbox or an external-course API.
"""

import copy
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

from lessonproof import assess_run


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "examples" / "library"
WORKER = r'''
import contextlib
import io
import json
import platform
import sys
import traceback
from pathlib import Path

notebook = json.loads(Path("lesson.ipynb").read_text(encoding="utf-8"))
namespace = {"__name__": "__lesson__"}
steps = []
for cell in notebook["cells"]:
    if cell["cell_type"] != "code":
        continue
    stdout, stderr = io.StringIO(), io.StringIO()
    step = {"id": cell["id"], "outcome": "ok"}
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            exec(compile("".join(cell["source"]), cell["id"], "exec"), namespace)
        except Exception as error:
            step.update(outcome="error", error_type=type(error).__name__, error_message=str(error))
            traceback.print_exc()
    step.update(stdout=stdout.getvalue(), stderr=stderr.getvalue())
    steps.append(step)
print(json.dumps({"schema_version": 1, "complete": True, "steps": steps,
                  "python": platform.python_version(), "platform": sys.platform}))
'''


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute_case(directory):
    temporary = directory / "tmp"
    temporary.mkdir()
    environment = {"TEMP": str(temporary), "TMP": str(temporary)}
    if "SystemRoot" in os.environ:
        environment["SystemRoot"] = os.environ["SystemRoot"]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", WORKER], cwd=directory, env=environment,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode:
            run = {"schema_version": 1, "complete": False, "steps": [], "runner_error": completed.stderr}
        else:
            run = json.loads(completed.stdout)
    except subprocess.TimeoutExpired:
        run = {"schema_version": 1, "complete": False, "steps": [], "runner_error": "execution_timeout_10s"}
    run["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
    write_json(directory / "execution.json", run)
    return run


def main():
    base = json.loads((SOURCE / "lesson.ipynb").read_text(encoding="utf-8"))
    contract = json.loads((SOURCE / "acceptance.json").read_text(encoding="utf-8"))
    lesson = (SOURCE / "lesson.md").read_text(encoding="utf-8")
    source_hashes = {path.name: fingerprint(path) for path in SOURCE.iterdir() if path.is_file()}

    wrong = copy.deepcopy(base)
    wrong["cells"][1]["source"] = [line.replace("row['borrow_count']", "row['stock_count']") for line in wrong["cells"][1]["source"]]

    teaching = copy.deepcopy(base)
    teaching["cells"].insert(1, {
        "cell_type": "code", "execution_count": None, "id": "expected-error", "metadata": {}, "outputs": [],
        "source": ["# 演示非法整数转换，观察异常后继续下一步。\n", "int('unknown')\n"],
    })
    teaching_contract = copy.deepcopy(contract)
    teaching_contract["steps"].insert(1, {"id": "expected-error", "expect": {
        "outcome": "error", "error_type": "ValueError", "message_contains": "unknown",
    }})
    teaching_lesson = lesson.replace("## 步骤 summarize", "## 步骤 expected-error\n\n执行 `int('unknown')`，观察 ValueError 且信息包含 unknown。这个预期异常是教学目标的一部分，随后继续统计。\n\n## 步骤 summarize")
    teaching_lesson = teaching_lesson.replace("两个步骤按顺序执行成功。", "按顺序执行三个步骤，其中 expected-error 产生预期异常，其余步骤成功。")

    cases = [
        ("normal", "正常课程", base, contract, lesson, "passed"),
        ("wrong-column", "代码读错数据列", wrong, contract, lesson, "failed"),
        ("expected-error", "教学预期报错", teaching, teaching_contract, teaching_lesson, "passed"),
        ("repaired-column", "修订后复验", base, contract, lesson, "passed"),
    ]
    run_root = (ROOT / "work" / "runs").resolve()
    if not run_root.is_relative_to(ROOT):
        raise ValueError("Run output must stay inside the project")
    output = run_root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": 1, "source_kind": "first_party_development_examples",
              "runner": "trusted_local_python", "source_hashes": source_hashes, "cases": []}
    for name, title, notebook, expected, guide, expected_status in cases:
        directory = output / name
        directory.mkdir()
        write_json(directory / "lesson.ipynb", notebook)
        write_json(directory / "acceptance.json", expected)
        (directory / "lesson.md").write_text(guide, encoding="utf-8")
        (directory / "loans.csv").write_bytes((SOURCE / "loans.csv").read_bytes())
        inputs = {name: fingerprint(directory / name) for name in ("lesson.md", "lesson.ipynb", "loans.csv", "acceptance.json")}
        execution = execute_case(directory)
        if any(fingerprint(directory / filename) != digest for filename, digest in inputs.items()):
            raise RuntimeError("A fixture modified its input or contract")
        result = assess_run(expected, execution)
        write_json(directory / "assessment.json", result)
        report["cases"].append({"id": name, "title": title, "expected_status": expected_status,
                                "status": result["status"], "matches_expected": result["status"] == expected_status,
                                "elapsed_ms": execution["elapsed_ms"], "input_hashes": inputs,
                                "findings": result["findings"]})
        print(f"{name}: {result['status']} (expected {expected_status})")

    old = "".join(wrong["cells"][1]["source"])
    new = "".join(base["cells"][1]["source"])
    patch = "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                         fromfile="wrong-column/summarize", tofile="repaired-column/summarize"))
    (output / "repair.diff").write_text(patch, encoding="utf-8")
    report["repair"] = {"source": "developer_provided_revision",
                         "original_case": "wrong-column", "revised_case": "repaired-column",
                         "contract_unchanged": fingerprint(output / "wrong-column" / "acceptance.json") == fingerprint(output / "repaired-column" / "acceptance.json")}
    report["source_unchanged"] = source_hashes == {path.name: fingerprint(path) for path in SOURCE.iterdir() if path.is_file()}
    report["self_check_passed"] = all(case["matches_expected"] for case in report["cases"]) and report["repair"]["contract_unchanged"] and report["source_unchanged"]
    write_json(output / "report.json", report)
    lines = ["# LessonProof 本地样例回放报告", "", "来源：项目原创开发样例。执行方式：本地独立 Python 进程。", "",
             "| 样例 | 预期 | 实际 | 执行耗时 ms |", "| --- | --- | --- | --- |"]
    lines += [f"| {case['title']} | {case['expected_status']} | {case['status']} | {case['elapsed_ms']} |" for case in report["cases"]]
    lines += ["", "## 问题证据"]
    for case in report["cases"]:
        for finding in case["findings"]:
            if finding["status"] != "passed":
                evidence = json.dumps(finding["evidence"], ensure_ascii=False)
                lines += ["", f"- {case['title']} / {finding['step_id']}：{finding['reason']}。", f"  证据：`{evidence}`"]
    lines += ["", "修订来自开发者预先提供的正确版本，使用与故障样例完全相同的验收标准复验。", "",
              "每个样例目录包含课程副本、验收标准、execution.json 和 assessment.json；repair.diff 展示修改。", "",
              "这些运行数据用于开发验收；人工基线、智能体效果和真实试用数据在后续评测中单独采集。", "",
              f"样例自检：{'通过' if report['self_check_passed'] else '失败'}。"]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report: {output / 'report.md'}")
    return 0 if report["self_check_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
