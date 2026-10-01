"""A small, local teacher workflow with immutable revisions and real evidence."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import difflib
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import subprocess
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4
import zipfile

from ai_review import MODEL, OLLAMA, LOCAL_HTTP, review, source_text, validate_review
from check_course import check_course, parse_json, read_file, require
from lessonproof import assess_run
from prepare_runtime import ROOT, RUNTIME
from runner import execute_course, profile_for


STORE = ROOT / "work" / "app"
SAMPLES = {"numpy-data": "数组数据读取与统计", "expected-index-error": "读懂列表越界的错误信息",
           "pandas-error-version": "缺失值与整数转换"}
# ponytail: one local teacher and one GPU; use a task queue if multiple teachers share a server.
LOCK = threading.RLock()
POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lessonproof")
ACTIVE = set()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def job_dir(identifier):
    require(isinstance(identifier, str) and re.fullmatch(r"[a-f0-9]{32}", identifier), "任务编号无效")
    path = (STORE / "jobs" / identifier).resolve()
    require(path.is_relative_to(ROOT / "work") and path.is_relative_to(STORE.resolve()), "工作目录越界")
    return path


def load(identifier):
    path = job_dir(identifier) / "job.json"
    require(path.is_file(), "未找到这次试跑")
    return parse_json(path.read_bytes())


def save(job):
    job["updated_at"] = now()
    write_json(job_dir(job["id"]) / "job.json", job)


def event(job, kind, detail):
    job["history"].append({"at": now(), "kind": kind, "detail": detail, "revision": job["revision"]})


def revision_dir(job):
    return job_dir(job["id"]) / "revisions" / str(job["revision"])


def snapshot_hash(course):
    manifest = parse_json(read_file(course, "course.json"))
    hashes = {name: sha(read_file(course, name)) for name in ["course.json", *manifest["files"]]}
    return sha(json.dumps(hashes, sort_keys=True).encode("utf-8"))


def assert_current(job, version=None):
    require(version is None or version == job["version_hash"], "页面版本已变化，请刷新后再操作")
    root = revision_dir(job)
    require(snapshot_hash(root) == job["version_hash"], "材料在工作台外被更改，请重新导入课程")
    require(sha(read_file(root, "acceptance.json")) == job["contract_sha256"], "原始验收标准发生变化，不能继续")


def extract_upload(data, folder):
    require(len(data) <= 16 * 1024 * 1024, "课程 ZIP 上限为 16 MiB")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        require(0 < len(entries) <= 100, "课程 ZIP 应包含 1—100 个条目")
        require(sum(item.file_size for item in entries) <= 24 * 1024 * 1024, "课程解压后超过 24 MiB")
        seen = set()
        for item in entries:
            name = item.filename.rstrip("/")
            require(name and "\\" not in name and ":" not in name and not PurePosixPath(name).is_absolute()
                    and all(part not in ("", ".", "..") and not part.endswith((".", " "))
                            and not PureWindowsPath(part).is_reserved() for part in name.split("/"))
                    and not any(ord(char) < 32 for char in name), "ZIP 包含越界或不规范路径")
            require(not any(part.casefold().startswith(".git") or part.casefold() == ".lfsconfig"
                            for part in name.split("/")), "课程包不能携带 Git 配置或仓库目录")
            require(name.casefold() not in seen and item.file_size <= 8 * 1024 * 1024, "ZIP 包含重名文件或过大文件")
            require((item.external_attr >> 16) & 0o170000 not in (0o120000, 0o060000, 0o020000), "ZIP 不能包含链接或设备文件")
            seen.add(name.casefold())
        require("course.json" in seen, "请将 course.json 放在 ZIP 根目录")
        for item in entries:
            target = folder / item.filename
            require(target.resolve().is_relative_to(folder.resolve()), "ZIP 路径越界")
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(item))


def create_job(sample=None, upload=None):
    with LOCK:
        identifier = uuid4().hex
        folder = job_dir(identifier) / "revisions" / "0"
        folder.mkdir(parents=True, exist_ok=False)
        if upload is not None:
            extract_upload(upload, folder)
        else:
            require(sample in SAMPLES, "请选择一套内置课程")
            original = ROOT / "benchmarks" / sample
            manifest = parse_json(read_file(original, "course.json"))
            for name in ["course.json", *manifest["files"]]:
                target = folder / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(read_file(original, name))
        report = check_course(folder)
        job = {"id": identifier, "title": str(report.get("title", "导入的课程"))[:180], "sample": sample,
               "created_at": now(), "updated_at": now(), "revision": 0, "phase": "ready" if report["material_status"] == "ready" else "blocked",
               "preflight": report, "version_hash": "", "contract_sha256": report.get("contract_sha256"),
               "history": [], "runs": [], "approval": None, "delivery": None, "review_decision": None, "error": None}
        if report["material_status"] == "ready":
            job["version_hash"] = snapshot_hash(folder)
        event(job, "import", "固定课程原稿与验收标准；" + ("材料检查通过" if job["phase"] == "ready" else "材料需要处理"))
        save(job)
        return job


def list_jobs():
    result = []
    for path in (STORE / "jobs").glob("*/job.json"):
        try:
            job = load(path.parent.name)
            result.append({key: job[key] for key in ("id", "title", "created_at", "updated_at", "revision", "phase", "delivery")})
        except (OSError, ValueError, KeyError):
            continue
    return sorted(result, key=lambda item: item["created_at"], reverse=True)


def detail(identifier):
    with LOCK:
        job = load(identifier)
        if job["phase"] in ("queued", "running", "reviewing", "verifying_sources") and identifier not in ACTIVE:
            job.update(phase="interrupted", error="上次服务停止时任务尚未完成，请重新试跑。")
            save(job)
        if job["preflight"]["material_status"] == "ready":
            root = revision_dir(job)
            job["lesson"] = read_file(root, "lesson.md").decode("utf-8")
            job["notebook"] = parse_json(read_file(root, "lesson.ipynb"))
            job["contract"] = parse_json(read_file(root, "acceptance.json"))
            job["integrity_ok"] = snapshot_hash(root) == job["version_hash"]
        return job


def verify_sources(manifest, log):
    checks = []
    for source in manifest["sources"]:
        url = source["url"]
        parts = urlsplit(url)
        segments = parts.path.strip("/").split("/")
        require(parts.scheme == "https" and parts.netloc == "raw.githubusercontent.com" and not parts.query
                and len(segments) >= 4 and segments[2] == source["revision"], "来源核验仅连接 GitHub 固定提交的原始文件")
        record = {"system": "GitHub", "method": "GET", "url": url, "expected_sha256": source["sha256"]}
        started = time.perf_counter()
        try:
            with urlopen(Request(url, headers={"User-Agent": "LessonProof/0.2"}), timeout=25) as response:
                data = response.read(8 * 1024 * 1024 + 1)
                require(len(data) <= 8 * 1024 * 1024 and urlsplit(response.url).netloc == parts.netloc, "来源响应超出范围")
                record.update(http_status=response.status, observed_sha256=sha(data), bytes=len(data))
                record["matched"] = record["observed_sha256"] == source["sha256"]
        except Exception as error:
            record.update(matched=False, error=str(error))
        record["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
        log(record)
        checks.append({key: value for key, value in record.items() if key != "system"})
    return checks


def begin_run(identifier, version, confirmed):
    require(confirmed is True, "请先确认试跑步骤与教学预期报错")
    with LOCK:
        job = load(identifier)
        require(identifier not in ACTIVE, "本次试跑正在进行")
        require(job["preflight"]["material_status"] == "ready", "请先补齐课程材料")
        assert_current(job, version)
        profile_for(parse_json(read_file(revision_dir(job), "course.json"))["environment"])
        ACTIVE.add(identifier)
        job.update(phase="queued", approval=None, delivery=None, review_decision=None, error=None)
        event(job, "plan_confirmed", "教师确认当前版本的步骤、输入和预期行为")
        save(job)
        POOL.submit(perform_run, identifier)
        return job


def perform_run(identifier):
    run_id = uuid4().hex
    evidence = job_dir(identifier) / "evidence" / run_id
    evidence.mkdir(parents=True)
    calls = []
    def log(record):
        name = f"call-{len(calls) + 1:02d}.json"
        write_json(evidence / name, {"at": now(), **record})
        calls.append({"file": name, "system": record["system"], "method": record["method"],
                      "elapsed_ms": record["elapsed_ms"], "ok": not record.get("error") and record.get("matched", True)})
    def phase(value):
        with LOCK:
            current = load(identifier)
            current["phase"] = value
            save(current)
    record = {"id": run_id, "started_at": now(), "calls": calls}
    try:
        with LOCK:
            job = load(identifier)
            assert_current(job)
            root = revision_dir(job)
            manifest = parse_json(read_file(root, "course.json"))
            contract = parse_json(read_file(root, "acceptance.json"))
            record.update(revision=job["revision"], version_hash=job["version_hash"], contract_sha256=job["contract_sha256"])
        phase("verifying_sources")
        record["sources"] = verify_sources(manifest, log)
        phase("running")
        execution = execute_course(root, manifest, evidence / "input")
        write_json(evidence / "execution.json", execution)
        assessment = assess_run(contract, execution["run"])
        if not execution["environment_matches"]:
            assessment = {"status": "inconclusive", "findings": assessment["findings"] + [
                {"step_id": None, "status": "inconclusive", "reason": "environment_mismatch"}]}
        record.update(assessment=assessment, execution=execution["run"], environment_matches=execution["environment_matches"],
                      isolation=execution["isolation"], elapsed_ms=execution["elapsed_ms"])
        if not execution["run"]["complete"] or not execution["environment_matches"]:
            raise RuntimeError("隔离试跑证据不完整或环境不匹配，请查看执行记录后重试")
        phase("reviewing")
        # The model sees precisely the learner snapshot used by the sandbox.
        learner = evidence / "input"
        record["ai"] = review(read_file(learner, "lesson.md").decode("utf-8"),
                              parse_json(read_file(learner, "lesson.ipynb")), execution["run"], log)
        record["ai_status"] = "completed"
        with LOCK:
            job = load(identifier)
            assert_current(job, record["version_hash"])
            clean = (assessment["status"] == "passed" and not record["ai"]["findings"]
                     and all(item["matched"] for item in record["sources"]))
            job["phase"] = "awaiting_approval" if clean else "needs_review"
    except Exception as error:
        record["error"] = str(error)
        record.setdefault("ai_status", "not_completed")
        with LOCK:
            job = load(identifier)
            job.update(phase="error", error=str(error))
    finally:
        record["finished_at"] = now()
        write_json(evidence / "summary.json", record)
        with LOCK:
            job["runs"].append(record)
            event(job, "run_finished", "实跑及材料审阅完成" if not record.get("error") else "任务中断，证据已保留")
            save(job)
            ACTIVE.discard(identifier)


def latest_run(job):
    require(job["runs"], "请先完成一次试跑")
    run = job["runs"][-1]
    require(run["version_hash"] == job["version_hash"] and not run.get("error"), "当前版本尚未完成试跑")
    return run


def apply_proposal(identifier, version):
    with LOCK:
        job = load(identifier)
        require(identifier not in ACTIVE and job["phase"] == "needs_review", "当前没有可审阅的修订")
        assert_current(job, version)
        run = latest_run(job)
        old_root = revision_dir(job)
        lesson = read_file(old_root, "lesson.md").decode("utf-8")
        notebook = parse_json(read_file(old_root, "lesson.ipynb"))
        proposal = validate_review(run["ai"], lesson, notebook)
        require(proposal["patches"], "AI 尚未提出可应用的修订，请补充材料后重新导入")
        changes = []
        for patch in proposal["patches"]:
            if patch["file"] == "lesson.md":
                before = lesson
                lesson = lesson.replace(patch["old_text"], patch["new_text"], 1)
                after = lesson
            else:
                cell = next(cell for cell in notebook["cells"] if cell["id"] == patch["cell_id"])
                before = source_text(cell)
                cell["source"] = before.replace(patch["old_text"], patch["new_text"], 1)
                after = cell["source"]
            changes.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                               fromfile="原稿/" + patch["file"], tofile="修订/" + patch["file"]))
        final_folder = job_dir(identifier) / "revisions" / str(job["revision"] + 1)
        require(not final_folder.exists(), "修订目录已存在，请重新导入以恢复")
        folder = job_dir(identifier) / "revisions" / ("pending-" + uuid4().hex)
        folder.mkdir()
        previous_manifest = parse_json(read_file(old_root, "course.json"))
        for name in ["course.json", *previous_manifest["files"]]:
            target = folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(read_file(old_root, name))
        changed_files = {patch["file"] for patch in proposal["patches"]}
        if "lesson.md" in changed_files:
            (folder / "lesson.md").write_text(lesson, encoding="utf-8", newline="\n")
        if "lesson.ipynb" in changed_files:
            write_json(folder / "lesson.ipynb", notebook)
        manifest = parse_json(read_file(folder, "course.json"))
        for name in changed_files:
            manifest["files"][name] = sha(read_file(folder, name))
        write_json(folder / "course.json", manifest)
        preflight = check_course(folder)
        require(preflight["material_status"] == "ready" and preflight["contract_sha256"] == job["contract_sha256"],
                "修订破坏了材料结构；原版本已保留，当前修订不予采用")
        folder.rename(final_folder)
        folder = final_folder
        preflight["course_path"] = str(folder)
        job.update(revision=job["revision"] + 1, version_hash=snapshot_hash(folder), preflight=preflight,
                   phase="ready", approval=None, delivery=None, review_decision=None, error=None)
        job["last_diff"] = "".join(changes)
        event(job, "patch_accepted", "教师确认 AI 修订；保存新版本，沿用原验收标准")
        save(job)
        return job


def resolve_findings(identifier, version, reason):
    require(isinstance(reason, str) and 10 <= len(reason.strip()) <= 1000, "请用 10—1000 字说明为什么无需修改")
    with LOCK:
        job = load(identifier)
        require(identifier not in ACTIVE and job["phase"] == "needs_review", "当前没有需要复核的问题")
        assert_current(job, version)
        run = latest_run(job)
        require(run["assessment"]["status"] == "passed" and run["ai_status"] == "completed"
                and all(source["matched"] for source in run["sources"]), "运行结果或来源尚未通过，不能判定为 AI 误报")
        job.update(phase="awaiting_approval", review_decision={"at": now(), "version_hash": version,
                   "run_id": run["id"], "reason": reason.strip(), "decision": "no_change_needed"})
        event(job, "teacher_review", "教师复核判定无需修改：" + reason.strip())
        save(job)
        return job


def approve(identifier, version, confirmed):
    require(confirmed is True, "请确认已阅读讲义、结果和修订")
    with LOCK:
        job = load(identifier)
        require(identifier not in ACTIVE and job["phase"] == "awaiting_approval", "当前课程尚未满足审核条件")
        assert_current(job, version)
        run = latest_run(job)
        decision = job.get("review_decision")
        resolved = decision and decision["version_hash"] == version and decision["run_id"] == run["id"]
        require(run["assessment"]["status"] == "passed" and run["ai_status"] == "completed"
                and (not run["ai"]["findings"] or resolved) and all(source["matched"] for source in run["sources"]), "仍有待处理问题")
        job.update(phase="approved", approval={"at": now(), "version_hash": version, "run_id": run["id"]})
        event(job, "approved", "教师审核通过，审批绑定当前材料版本")
        save(job)
        return job


def git_command(directory, *args):
    # All Git operations share this guard, including retries after partial delivery.
    require(directory.resolve().is_relative_to(STORE.resolve())
            and directory.resolve().is_relative_to(ROOT / "work"), "Git 归档目录越界")
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgSign=false", "-c", "core.longpaths=true",
                             "-C", str(directory), *args], capture_output=True, timeout=30,
                            env=environment,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    require(result.returncode == 0, "本地 Git 归档失败：" + result.stderr.decode("utf-8", "replace")[-1000:])
    return result.stdout


def deliver(identifier, version):
    with LOCK:
        job = load(identifier)
        assert_current(job, version)
        if job["delivery"]:
            return job
        require(job["phase"] == "approved" and job["approval"]["version_hash"] == version, "请先审核这个版本")
        root = revision_dir(job)
        manifest = parse_json(read_file(root, "course.json"))
        files = {name: read_file(root, name) for name in manifest["learner_files"]}
        output = job_dir(identifier) / "deliveries" / version
        output.mkdir(parents=True, exist_ok=True)
        archive = output / "course.zip"
        temporary = output / "course.zip.tmp"
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name, data in files.items():
                bundle.writestr(name, data)
        with zipfile.ZipFile(temporary) as bundle:
            require(set(bundle.namelist()) == set(files) and all(bundle.read(name) == data for name, data in files.items()), "交付包回读不一致")
        temporary.replace(archive)
        repo = output / "git"
        repo.mkdir(exist_ok=True)
        git_command(repo, "init", "--quiet")
        for name, data in files.items():
            target = repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        git_command(repo, "-c", "core.autocrlf=false", "add", "--", *files)
        git_command(repo, "-c", "user.name=LessonProof", "-c", "user.email=lessonproof@localhost", "-c", "core.hooksPath=/dev/null",
                    "commit", "--quiet", "--allow-empty", "-m", "保存教师审核通过的课程版本")
        commit = git_command(repo, "rev-parse", "HEAD").decode().strip()
        require(all(git_command(repo, "show", f"{commit}:{name}") == data for name, data in files.items()), "Git 归档回读不一致")
        job.update(phase="delivered", delivery={"at": now(), "version_hash": version, "zip_sha256": sha(archive.read_bytes()),
                   "git_commit": commit, "files": {name: sha(data) for name, data in files.items()}, "readback_matched": True})
        write_json(output / "receipt.json", job["delivery"])
        event(job, "delivered", "本地课程包与 Git 归档均已回读，逐文件校验一致")
        save(job)
        return job


def delivery_file(identifier, name):
    job = load(identifier)
    require(job["delivery"] is not None and name in ("course.zip", "receipt.json"), "交付文件尚未生成")
    path = job_dir(identifier) / "deliveries" / job["delivery"]["version_hash"] / name
    require(path.resolve().is_relative_to(job_dir(identifier)), "交付路径越界")
    if name == "course.zip":
        require(sha(path.read_bytes()) == job["delivery"]["zip_sha256"], "交付包发生变化，不能下载")
    else:
        require(parse_json(path.read_bytes()) == job["delivery"], "交付回执发生变化，不能下载")
    return path


def evidence_zip(identifier):
    job = load(identifier)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("job.json", json.dumps(job, ensure_ascii=False, indent=2))
        for path in (job_dir(identifier) / "evidence").glob("*/*.json"):
            require(path.resolve().is_relative_to(job_dir(identifier)), "证据目录越界")
            bundle.writestr(path.relative_to(job_dir(identifier)).as_posix(), path.read_bytes())
        for revision in range(job["revision"] + 1):
            root = job_dir(identifier) / "revisions" / str(revision)
            manifest = parse_json(read_file(root, "course.json"))
            for name in ["course.json", *manifest["files"]]:
                bundle.writestr(f"revisions/{revision}/{name}", read_file(root, name))
        bundle.writestr("README.txt", "这是开发与教师审核证据包，包含固定验收标准和参考资料。学生材料另见课程交付包。\n")
    return output.getvalue()


def status():
    state = {"model": MODEL, "ollama": False, "model_installed": False,
             "runtime_prepared": (RUNTIME / "python/bin/python3.11").is_file()
             and (RUNTIME / "bubblewrap/usr/bin/bwrap").is_file()
             and all((RUNTIME / "profiles" / profile).is_dir() for profile in ("stdlib", "numpy", "pandas")),
             "agentarts": "awaiting_account", "teaching_platform": "awaiting_connection"}
    try:
        with LOCAL_HTTP.open(OLLAMA + "/api/tags", timeout=3) as response:
            data = parse_json(response.read(128 * 1024))
            state.update(ollama=True, model_installed=any(model["name"] == MODEL for model in data["models"]))
    except (OSError, ValueError, KeyError):
        pass
    return state
