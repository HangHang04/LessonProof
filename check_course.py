"""Inspect a local course package using only data reads; never run lesson code."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys
from urllib.parse import urlsplit
from uuid import uuid4

from lessonproof import _unique_object, validate_contract


ROOT = Path(__file__).resolve().parent
REQUIRED = {"lesson.md", "lesson.ipynb", "acceptance.json", "reference.md", "LICENSE.md"}
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,64}")
SHA256 = re.compile(r"[0-9a-f]{64}")


def course_file(root, name):
    """Resolve portable relative paths, including Windows junctions/symlinks."""
    if (not isinstance(name, str) or not name or "\\" in name or ":" in name
            or any(ord(char) < 32 for char in name)
            or PurePosixPath(name).is_absolute()
            or any(part in ("", ".", "..") or part.endswith((" ", "."))
                   or PureWindowsPath(part).is_reserved() for part in name.split("/"))):
        raise ValueError(f"路径必须是课程包内的规范相对路径：{name!r}")
    target = (root / name).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"路径指向课程包外：{name}")
    if not target.is_file():
        raise ValueError(f"缺少文件：{name}")
    return target


def read_file(root, name):
    with course_file(root, name).open("rb") as source:
        size = os.fstat(source.fileno()).st_size
        if size > 8 * 1024 * 1024:
            raise ValueError(f"文件超过本阶段的 8 MiB 上限：{name}")
        data = source.read(size + 1)
    if len(data) != size:
        raise ValueError(f"文件读取期间发生变化，请重新检查：{name}")
    return data


def parse_json(data):
    value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
    json.dumps(value, allow_nan=False)
    return value


def require(condition, message):
    if not condition:
        raise ValueError(message)


def notebook_steps(notebook):
    require(isinstance(notebook, dict), "Notebook 必须是 JSON 对象")
    require(type(notebook.get("nbformat")) is int and notebook["nbformat"] == 4
            and type(notebook.get("nbformat_minor")) is int and notebook["nbformat_minor"] == 5,
            "本阶段的 Notebook 格式为 nbformat 4.5")
    require(isinstance(notebook.get("metadata"), dict), "Notebook 缺少 metadata 对象")
    require(isinstance(notebook.get("cells"), list) and notebook["cells"], "Notebook 缺少 cells")
    seen, code_ids = set(), []
    for cell in notebook["cells"]:
        require(isinstance(cell, dict), "Notebook 的 cell 必须是对象")
        identifier = cell.get("id")
        require(isinstance(identifier, str) and IDENTIFIER.fullmatch(identifier), "Notebook 的 cell id 无效")
        require(identifier not in seen, f"Notebook 重复 cell id：{identifier}")
        seen.add(identifier)
        require(cell.get("cell_type") in ("code", "markdown", "raw"), f"未知 cell_type：{identifier}")
        require(isinstance(cell.get("metadata"), dict), f"cell 缺少 metadata：{identifier}")
        source = cell.get("source")
        require(isinstance(source, str) or (isinstance(source, list)
                and all(isinstance(line, str) for line in source)), f"cell source 无效：{identifier}")
        if cell["cell_type"] == "code":
            require("execution_count" in cell and cell["execution_count"] is None
                    and cell.get("outputs") == [], f"待试跑 cell 应清空执行编号与输出：{identifier}")
            code_ids.append(identifier)
    require(code_ids, "Notebook 至少需要一个代码步骤")
    return code_ids


def lesson_steps(lesson):
    identifiers, fence = [], None
    for line in lesson.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if marker:
            delimiter, suffix = marker.groups()
            if fence is None:
                fence = delimiter
            elif delimiter[0] == fence[0] and len(delimiter) >= len(fence) and not suffix.strip():
                fence = None
        elif fence is None:
            heading = re.fullmatch(r"## 步骤 ([A-Za-z0-9_-]{1,64})\s*", line)
            if heading:
                identifiers.append(heading[1])
    return identifiers


def check_course(directory):
    """Return material readiness and its evidence; execution is always not_run."""
    report = {"schema_version": 1, "check_kind": "course_package_preflight",
              "material_status": "blocked", "execution_status": "not_run",
              "course_path": str(directory), "findings": [], "file_hashes": {}}
    try:
        root = Path(directory).resolve(strict=True)
        require(root.is_dir(), "课程路径必须是目录")
        report["course_path"] = str(root)
        raw_manifest = read_file(root, "course.json")
        report["manifest_sha256"] = hashlib.sha256(raw_manifest).hexdigest()
        manifest = parse_json(raw_manifest)
        require(isinstance(manifest, dict) and type(manifest.get("schema_version")) is int
                and manifest["schema_version"] == 1, "课程清单 schema_version 必须为整数 1")
        for field in ("lesson_id", "title", "source_kind"):
            require(isinstance(manifest.get(field), str) and manifest[field].strip(), f"课程清单缺少 {field}")
            report[field] = manifest[field]
        environment = manifest.get("environment")
        require(isinstance(environment, dict) and isinstance(environment.get("python"), str)
                and re.fullmatch(r"\d+\.\d+\.\d+", environment["python"]), "环境应声明具体 Python 版本")
        packages = environment.get("packages")
        require(isinstance(packages, dict) and all(isinstance(k, str) and k.strip()
                and isinstance(v, str) and re.fullmatch(r"\d+\.\d+\.\d+", v)
                for k, v in packages.items()), "环境应列出包名与具体版本；标准库课程填空对象")
        report["declared_environment"] = environment
        files = manifest.get("files")
        require(isinstance(files, dict) and REQUIRED <= files.keys(), "清单应包含讲义、Notebook、验收、参考和许可文件")
        require("course.json" not in files, "清单自身的校验值由检查报告记录")
        contents = {}
        for name, digest in files.items():
            require(isinstance(digest, str) and SHA256.fullmatch(digest), f"无效 SHA-256：{name}")
            try:
                data = read_file(root, name)
                observed = hashlib.sha256(data).hexdigest()
                report["file_hashes"][name] = observed
                contents[name] = data
                if observed != digest:
                    report["findings"].append({"code": "hash_mismatch", "file": name,
                        "message": "文件与登记版本不一致", "expected": digest, "actual": observed})
            except (OSError, ValueError, RuntimeError) as error:
                report["findings"].append({"code": "file_unavailable", "file": name, "message": str(error)})
        if report["findings"]:
            return report

        learner_files = manifest.get("learner_files")
        require(isinstance(learner_files, list) and all(isinstance(name, str) for name in learner_files),
                "learner_files 应列出学生材料")
        require(len(learner_files) == len(set(learner_files)) and {"lesson.md", "lesson.ipynb", "LICENSE.md"}
                <= set(learner_files) <= files.keys(), "学生材料应包含讲义、Notebook、许可，且全部登记")
        require(not {"acceptance.json", "reference.md"} & set(learner_files), "验收目标与参考资料应独立于学生材料")
        report["learner_files"] = learner_files
        sources = manifest.get("sources")
        require(isinstance(sources, list) and sources, "清单缺少来源记录")
        for source in sources:
            require(isinstance(source, dict), "来源记录必须是对象")
            url = source.get("url")
            require(isinstance(url, str) and urlsplit(url).scheme == "https" and urlsplit(url).netloc,
                    "来源需使用 HTTPS 地址")
            require(isinstance(source.get("revision"), str)
                    and re.fullmatch(r"[0-9a-f]{40}", source["revision"]), "来源需固定完整提交版本")
            require(isinstance(source.get("sha256"), str) and SHA256.fullmatch(source["sha256"]),
                    "来源缺少原文件 SHA-256")
            targets = source.get("applies_to")
            require(isinstance(targets, list) and targets and all(isinstance(name, str) and name in files for name in targets),
                    "来源对应的本地文件未登记")
            require(isinstance(source.get("adaptation"), str) and source["adaptation"].strip(), "来源缺少改编说明")
            if source["adaptation"] == "verbatim":
                require(all(report["file_hashes"][name] == source["sha256"] for name in targets), "原样保存的来源文件校验值不一致")
        report["sources"] = sources

        contract = parse_json(contents["acceptance.json"])
        expected = validate_contract(contract)
        require(contract.get("lesson_id") == manifest["lesson_id"], "验收标准的 lesson_id 与课程不一致")
        ids = [step["id"] for step in expected]
        require(all(IDENTIFIER.fullmatch(identifier) for identifier in ids), "步骤 ID 应符合 Notebook 4.5 格式")
        require(notebook_steps(parse_json(contents["lesson.ipynb"])) == ids, "Notebook 步骤与验收标准的 ID 或顺序不一致")
        require(lesson_steps(contents["lesson.md"].decode("utf-8")) == ids, "讲义步骤与验收标准的 ID 或顺序不一致")
        steps = manifest.get("steps")
        require(isinstance(steps, list) and all(isinstance(step, dict) for step in steps)
                and [step.get("id") for step in steps] == ids, "课程清单步骤与验收标准不一致")
        for step in steps:
            inputs = step.get("inputs")
            # ponytail: inspect declared inputs; dynamic Python paths need the later sandbox runner.
            require(isinstance(inputs, list) and all(isinstance(name, str) and name in learner_files for name in inputs),
                    f"步骤 {step['id']} 引用的输入文件未列入学生材料")
        require(contents["reference.md"].decode("utf-8").strip() and contents["LICENSE.md"].decode("utf-8").strip(),
                "参考或许可文件为空")
        report["contract_sha256"] = report["file_hashes"]["acceptance.json"]
        report["steps"] = [{"id": step["id"], "inputs": step["inputs"], "expected_outcome": expect["expect"]["outcome"]}
                           for step, expect in zip(steps, expected)]
        report["material_status"] = "ready"
    except (OSError, ValueError, TypeError, RuntimeError, RecursionError) as error:
        report["findings"].append({"code": "invalid_package", "message": str(error)})
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="检查课程包材料与步骤，生成试跑准备报告。")
    parser.add_argument("course_directory", type=Path)
    args = parser.parse_args(argv)
    report = check_course(args.course_directory)
    label = "可进入试跑" if report["material_status"] == "ready" else "材料需补齐或修正"
    print(f"{report.get('title', args.course_directory)}：{label}；课程执行：尚未试跑。")
    for finding in report["findings"]:
        print(f"- {finding.get('file', '课程包')}：{finding['message']}")
    try:
        output_root = (ROOT / "work" / "checks").resolve()
        require(output_root.is_relative_to(ROOT), "报告目录必须位于项目 work 内")
        require(not output_root.is_relative_to(args.course_directory.resolve()), "报告目录不能位于被检查的课程包内")
        output = output_root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
        output.mkdir(parents=True, exist_ok=False)
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        lines = ["# LessonProof 课程包检查报告", "", f"课程：{report.get('title', args.course_directory)}", "",
                 f"材料状态：**{label}**。课程执行：**尚未试跑**。", "",
                 "本报告来自本地材料与步骤检查。来源记录由课程包提供，本次检查不重新访问上游；环境为声明值，尚待沙箱验证。", "",
                 f"课程清单 SHA-256：`{report.get('manifest_sha256', '不可用')}`", "",
                 f"验收标准 SHA-256：`{report.get('contract_sha256', '不可用')}`", ""]
        if report.get("steps"):
            lines += ["| 步骤 | 声明输入 | 预期行为 |", "| --- | --- | --- |"]
            lines += [f"| {step['id']} | {', '.join(step['inputs']) or '—'} | {'教学预期报错' if step['expected_outcome'] == 'error' else '正常执行'} |"
                      for step in report["steps"]]
        lines += ["", "问题记录："]
        lines += [f"- {finding.get('file', '课程包')}：{finding['message']}" for finding in report["findings"]] or ["材料检查项均满足。"]
        (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"报告：{output / 'report.md'}")
    except (OSError, ValueError, RuntimeError) as error:
        print(f"报告保存失败：{error}", file=sys.stderr)
        return 2
    return 0 if report["material_status"] == "ready" else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
