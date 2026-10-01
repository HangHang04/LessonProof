"""Workflow invariants without network, GPU or executing course code."""
import copy
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler
import zipfile

import app
import ai_review
from ai_review import validate_review
import workbench as work


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        (work.ROOT / "work").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=work.ROOT / "work", prefix="unit-")
        self.assertTrue(Path(self.temporary.name).resolve().is_relative_to(work.ROOT / "work"))
        self.storage = patch.object(work, "STORE", Path(self.temporary.name))
        self.storage.start()

    def tearDown(self):
        self.storage.stop()
        self.temporary.cleanup()

    def reviewed(self, sample="pandas-error-version", findings=True):
        job = work.create_job(sample)
        old = "ValueError: Cannot convert NA to integer"
        new = "IntCastingNaNError: Cannot convert non-finite values (NA or inf) to integer"
        ai = {"summary": "用于验证流程的固定模型响应。", "findings": [], "patches": []}
        if findings:
            ai["findings"] = [{"step_id": "cast-weight", "explanation": "错误说明与实际环境不一致", "evidence_quote": old}]
            ai["patches"] = [{"file": "lesson.md", "cell_id": "", "old_text": old, "new_text": new, "reason": "保留教学报错，更新说明"}]
        job["runs"] = [{"id": "test", "version_hash": job["version_hash"], "ai": ai, "ai_status": "completed",
                        "assessment": {"status": "passed"}, "sources": [{"matched": True}]}]
        job["phase"] = "needs_review" if findings else "awaiting_approval"
        work.save(job)
        return job

    def test_teacher_must_approve_current_complete_revision(self):
        job = work.create_job("numpy-data")
        with self.assertRaises(ValueError):
            work.approve(job["id"], job["version_hash"], True)
        job = self.reviewed("numpy-data", False)
        with self.assertRaises(ValueError):
            work.approve(job["id"], "stale-version", True)
        with self.assertRaises(ValueError):
            work.approve(job["id"], job["version_hash"], False)
        job["runs"][-1]["assessment"]["status"] = "failed"
        work.save(job)
        with self.assertRaises(ValueError):
            work.approve(job["id"], job["version_hash"], True)
        job["runs"][-1]["assessment"]["status"] = "passed"
        work.save(job)
        self.assertEqual(work.approve(job["id"], job["version_hash"], True)["phase"], "approved")

    def test_invalid_model_reply_gets_one_logged_correction_then_fails_closed(self):
        job = self.reviewed()
        root = work.revision_dir(job)
        lesson = work.read_file(root, "lesson.md").decode("utf-8")
        notebook = work.parse_json(work.read_file(root, "lesson.ipynb"))
        invalid = copy.deepcopy(job["runs"][-1]["ai"])
        invalid["patches"][0]["new_text"] = invalid["patches"][0]["old_text"]
        clean = {"summary": "核对一致", "findings": [], "patches": []}
        def response(value):
            handle = io.BytesIO(json.dumps({"done": True, "message": {"content": json.dumps(value)}}).encode())
            handle.status = 200
            return handle
        run = {"steps": [{"id": "cast-weight", "outcome": "error", "error_type": "IndexError", "error_message": "test"}]}
        for replies, succeeds in (([invalid, clean], True), ([invalid, invalid], False)):
            logs = []
            with patch.object(ai_review.LOCAL_HTTP, "open", side_effect=[response(value) for value in replies]):
                if succeeds:
                    self.assertEqual(ai_review.review(lesson, notebook, run, logs.append), clean)
                else:
                    with self.assertRaises(ValueError):
                        ai_review.review(lesson, notebook, run, logs.append)
            self.assertEqual(len(logs), 2)
            self.assertIn("error", logs[0])
            self.assertIn("error_text", logs[0]["request"]["messages"][1]["content"])
            self.assertEqual([entry["attempt"] for entry in logs], [1, 2])

    def test_repair_preserves_contract_and_teaching_code_then_requires_rerun(self):
        job = self.reviewed()
        root = work.revision_dir(job)
        original = {name: work.read_file(root, name) for name in ("acceptance.json", "lesson.ipynb", "data/surveys.csv")}
        updated = work.apply_proposal(job["id"], job["version_hash"])
        self.assertEqual(updated["phase"], "ready")
        self.assertNotEqual(updated["version_hash"], job["version_hash"])
        self.assertEqual(updated["contract_sha256"], job["contract_sha256"])
        for name, data in original.items():
            current = work.read_file(work.revision_dir(updated), name)
            self.assertEqual(data, current)
        with self.assertRaises(ValueError):
            work.approve(updated["id"], updated["version_hash"], True)
        self.assertIn(b"ValueError", work.read_file(root, "lesson.md"))

    def test_external_material_and_contract_changes_invalidate_approval(self):
        for name in ("lesson.md", "acceptance.json"):
            job = self.reviewed("numpy-data", False)
            work.approve(job["id"], job["version_hash"], True)
            target = work.revision_dir(job) / name
            target.write_bytes(target.read_bytes() + b"\n")
            with self.assertRaises(ValueError):
                work.deliver(job["id"], job["version_hash"])

    def test_teacher_can_record_false_positive_but_cannot_override_failed_execution(self):
        job = self.reviewed()
        reason = "已核对当前讲义与实际输出，异常类型和消息逐字一致，属于重复提醒。"
        job["runs"][-1]["assessment"]["status"] = "failed"
        work.save(job)
        with self.assertRaises(ValueError): work.resolve_findings(job["id"], job["version_hash"], reason)
        job["runs"][-1]["assessment"]["status"] = "passed"
        work.save(job)
        with self.assertRaises(ValueError): work.resolve_findings(job["id"], job["version_hash"], "跳过")
        resolved = work.resolve_findings(job["id"], job["version_hash"], reason)
        self.assertEqual(resolved["review_decision"]["reason"], reason)
        self.assertIsNone(resolved["approval"])
        self.assertEqual(work.approve(job["id"], job["version_hash"], True)["phase"], "approved")

    def test_ai_quotes_and_patch_targets_are_validated(self):
        job = self.reviewed()
        root = work.revision_dir(job)
        lesson = work.read_file(root, "lesson.md").decode()
        notebook = json.loads(work.read_file(root, "lesson.ipynb"))
        for change in ("quote", "file", "match", "step"):
            ai = copy.deepcopy(job["runs"][-1]["ai"])
            if change == "quote": ai["findings"][0]["evidence_quote"] = "fabricated source quote"
            if change == "file": ai["patches"][0]["file"] = "acceptance.json"
            if change == "match": ai["patches"][0]["old_text"] = "not in source"
            if change == "step": ai["findings"][0]["step_id"] = "unplanned"
            with self.assertRaises(ValueError): validate_review(ai, lesson, notebook)

    def test_invalid_patch_does_not_commit_a_revision(self):
        job = self.reviewed()
        job["runs"][-1]["ai"]["patches"][0].update(old_text="## 步骤 cast-weight", new_text="## 步骤 renamed")
        work.save(job)
        with self.assertRaises(ValueError): work.apply_proposal(job["id"], job["version_hash"])
        self.assertEqual(work.load(job["id"])["revision"], 0)
        self.assertFalse((work.job_dir(job["id"]) / "revisions/1").exists())

    def test_zip_rejects_traversal_collisions_and_git_configuration(self):
        for name in ("../outside.txt", "/outside", "C:/outside", "..\\outside", "CON", ".git/config", ".gitattributes"):
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,"w") as archive:
                archive.writestr("course.json", "{}")
                archive.writestr(name,"test")
            with self.assertRaises(ValueError): work.create_job(upload=stream.getvalue())
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,"w") as archive:
            archive.writestr("course.json", "{}")
            archive.writestr("Course.json", "{}")
        with self.assertRaises(ValueError): work.create_job(upload=stream.getvalue())

    def test_source_fetch_is_limited_to_pinned_github_files(self):
        for url in ("http://127.0.0.1/", "https://example.com/data", "https://raw.githubusercontent.com/owner/repo/main/file"):
            with self.assertRaises(ValueError):
                work.verify_sources({"sources":[{"url":url,"revision":"a"*40,"sha256":"b"*64}]}, lambda _: None)

    def test_http_rejects_cross_origin_and_missing_token(self):
        server=app.ThreadingHTTPServer(("127.0.0.1",0),app.Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True)
        worker.start()
        url=f"http://127.0.0.1:{server.server_port}"
        client=build_opener(ProxyHandler({}))
        try:
            with client.open(url) as response: self.assertIn(b"lessonproof-token",response.read())
            for headers in ({}, {"X-LessonProof-Token":app.TOKEN,"Origin":"https://untrusted.example"},
                            {"X-LessonProof-Token":app.TOKEN,"Host":"attacker.example"}):
                with self.assertRaises(HTTPError): client.open(Request(url+"/api/jobs",headers=headers))
            with client.open(Request(url+"/api/jobs",headers={"X-LessonProof-Token":app.TOKEN})) as response:
                self.assertEqual(json.loads(response.read()),[])
        finally:
            server.shutdown();server.server_close();worker.join()


if __name__ == "__main__":
    unittest.main()
