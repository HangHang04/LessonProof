import contextlib
import csv
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from check_course import check_course, main, read_file


BENCHMARKS = Path(__file__).resolve().parent / "benchmarks"


class CoursePackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="lessonproof-")
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.course = self.workspace / "课程 [样本]"
        shutil.copytree(BENCHMARKS / "numpy-data", self.course)

    def change_json(self, name, change):
        value = json.loads((BENCHMARKS / "numpy-data" / name).read_text(encoding="utf-8"))
        change(value)
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        (self.course / name).write_bytes(raw)
        if name != "course.json":
            manifest = json.loads((BENCHMARKS / "numpy-data" / "course.json").read_text(encoding="utf-8"))
            manifest["files"][name] = hashlib.sha256(raw).hexdigest()
            (self.course / "course.json").write_text(json.dumps(manifest), encoding="utf-8")
        return check_course(self.course)

    def test_bounded_read_rejects_oversize_and_size_changes(self):
        target = self.course / "bounded.bin"
        target.write_bytes(b"small")
        self.assertEqual(read_file(self.course.resolve(), "bounded.bin"), b"small")
        with patch("check_course.os.fstat") as stat:
            stat.return_value.st_size = 4
            with self.assertRaisesRegex(ValueError, "读取期间"):
                read_file(self.course.resolve(), "bounded.bin")
        with target.open("wb") as handle:
            handle.truncate(8 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, "8 MiB"):
            read_file(self.course.resolve(), "bounded.bin")

    def test_three_public_packages_are_ready_without_modification_or_execution(self):
        for name in ("numpy-data", "expected-index-error", "pandas-error-version"):
            with self.subTest(course=name):
                directory = BENCHMARKS / name
                original = {p.relative_to(directory): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
                result = check_course(directory)
                self.assertEqual(result["material_status"], "ready", result)
                self.assertEqual(result["execution_status"], "not_run")
                self.assertEqual(result["contract_sha256"], hashlib.sha256(original[Path("acceptance.json")]).hexdigest())
                self.assertEqual(original, {p.relative_to(directory): p.read_bytes() for p in directory.rglob("*") if p.is_file()})
                if name != "numpy-data":
                    self.assertIn("error", [step["expected_outcome"] for step in result["steps"]])

    def test_missing_and_changed_input_files_are_blocked(self):
        path = self.course / "data" / "inflammation-01.csv"
        original = path.read_bytes()
        path.unlink()
        result = check_course(self.course)
        self.assertEqual(result["material_status"], "blocked")
        self.assertEqual(result["findings"][0]["code"], "file_unavailable")
        path.write_bytes(original + b"0,0\n")
        result = check_course(self.course)
        self.assertEqual(result["findings"][0]["code"], "hash_mismatch")

    def test_reference_values_match_data_and_historical_revision(self):
        normal = BENCHMARKS / "numpy-data"
        with (normal / "data" / "inflammation-01.csv").open(encoding="utf-8", newline="") as source:
            rows = [[int(value) for value in row] for row in csv.reader(source)]
        values = [value for row in rows for value in row]
        contract = json.loads((normal / "acceptance.json").read_text(encoding="utf-8"))
        self.assertEqual({len(row) for row in rows}, {40})
        self.assertEqual(contract["steps"][1]["expect"]["stdout_json"],
                         {"shape": [len(rows), 40], "first_value": rows[0][0], "middle_value": rows[29][19]})
        self.assertEqual(contract["steps"][2]["expect"]["stdout_json"],
                         {"minimum": min(values), "maximum": max(values),
                          "mean_5dp": format(Decimal(sum(values)) / len(values), ".5f")})
        historical = BENCHMARKS / "pandas-error-version"
        with (historical / "data" / "surveys.csv").open(encoding="utf-8", newline="") as source:
            subset = list(csv.DictReader(source))
        self.assertEqual([row["record_id"] for row in subset], ["1", "2", "63", "64", "65"])
        self.assertEqual([row["weight"] for row in subset], ["", "", "40", "48", "29"])
        before = (historical / "upstream-before.md").read_text(encoding="utf-8")
        after = (historical / "upstream-after.md").read_text(encoding="utf-8")
        self.assertIn("`ValueError: Cannot convert NA to integer`", before)
        self.assertNotIn("`ValueError: Cannot convert NA to integer`", after)
        for excerpt in (before, after):
            self.assertIn("surveys_df['weight'].astype(\"int\")", excerpt)
            self.assertIn("pandas.errors.IntCastingNaNError", excerpt)

    def test_notebook_damage_and_step_mismatch_are_blocked(self):
        changes = [lambda n: n.update(cells=[]), lambda n: n.update(nbformat=True),
                   lambda n: n["cells"][0].update(source=42),
                   lambda n: n["cells"][1].update(id=n["cells"][0]["id"]),
                   lambda n: n["cells"].reverse(),
                   lambda n: n["cells"][0].update(id="unplanned"),
                   lambda n: n["cells"][0].update(outputs=[{"output_type": "stream", "name": "stdout", "text": "old result"}])]
        for change in changes:
            with self.subTest(change=change):
                self.assertEqual(self.change_json("lesson.ipynb", change)["material_status"], "blocked")

    def test_contract_and_manifest_references_are_checked(self):
        for change in (lambda c: c["steps"][0]["expect"].update(outcome="anything"),
                       lambda c: c.update(lesson_id="another-course"),
                       lambda c: c["steps"].append(c["steps"][0])):
            with self.subTest(change=change):
                self.assertEqual(self.change_json("acceptance.json", change)["material_status"], "blocked")
        (self.course / "acceptance.json").write_bytes((BENCHMARKS / "numpy-data" / "acceptance.json").read_bytes())
        result = self.change_json("course.json", lambda c: c["steps"][0].update(inputs=["data/missing.csv"]))
        self.assertEqual(result["material_status"], "blocked")
        self.assertIn("输入文件", result["findings"][0]["message"])

    def test_paths_cannot_escape_the_course_or_use_windows_aliases(self):
        outside = self.workspace / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        for name in ("../outside.txt", str(outside), "C:/outside.txt", "//host/share/file", "data\\file.csv",
                     "data/inflammation-01.csv:stream", "data/../../outside.txt", "NUL", "data /file"):
            with self.subTest(path=name):
                result = self.change_json("course.json", lambda c: c["files"].update({name: "0" * 64}))
                self.assertEqual(result["material_status"], "blocked")
                self.assertNotIn(name, result["file_hashes"])

    def link_directory(self, link, outside):
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            if os.name != "nt" or getattr(error, "winerror", None) != 1314:
                raise
            shell = shutil.which("pwsh") or shutil.which("powershell")
            self.assertIsNotNone(shell, "PowerShell is required to check Windows junctions")
            script = self.workspace / "junction.ps1"
            script.write_text("param([string]$Link, [string]$Destination)\n"
                              "New-Item -ItemType Junction -Path $Link -Target $Destination -ErrorAction Stop | Out-Null\n",
                              encoding="utf-8")
            subprocess.run([shell, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(script), str(link), str(outside)],
                           capture_output=True, check=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)

    def test_link_outside_the_package_is_blocked_before_read(self):
        outside = self.workspace / "outside"
        outside.mkdir()
        (outside / "private.txt").write_text("private", encoding="utf-8")
        self.link_directory(self.course / "linked", outside)
        result = self.change_json("course.json", lambda c: c["files"].update({"linked/private.txt": "0" * 64}))
        self.assertEqual(result["material_status"], "blocked")
        self.assertNotIn("linked/private.txt", result["file_hashes"])

    def test_report_directory_link_cannot_write_outside_project(self):
        project, outside = self.workspace / "project", self.workspace / "outside"
        project.mkdir()
        outside.mkdir()
        self.link_directory(project / "work", outside)
        with patch("check_course.ROOT", project), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([str(self.course)]), 2)
        self.assertEqual(list(outside.iterdir()), [])

    def test_lesson_headings_must_match_and_fenced_examples_are_not_steps(self):
        original = (self.course / "lesson.md").read_text(encoding="utf-8")
        for guide, expected in ((original.replace("## 步骤 load-data", "## 步骤 another-step"), "blocked"),
                                (original + "\n```markdown\n## 步骤 example-only\n```\n", "ready")):
            with self.subTest(expected=expected):
                raw = guide.encode("utf-8")
                (self.course / "lesson.md").write_bytes(raw)
                result = self.change_json("course.json", lambda c: c["files"].update({"lesson.md": hashlib.sha256(raw).hexdigest()}))
                self.assertEqual(result["material_status"], expected, result)

    def test_inspection_does_not_run_notebook_code(self):
        result = self.change_json("lesson.ipynb", lambda n: n["cells"][0].update(
            source=["from pathlib import Path\n", f"Path({str(self.workspace / 'executed.txt')!r}).write_text('executed')\n"]))
        self.assertEqual(result["material_status"], "ready")
        self.assertFalse((self.workspace / "executed.txt").exists())
        self.assertEqual(result["execution_status"], "not_run")

    def test_ambiguous_or_invalid_json_is_blocked(self):
        path = self.course / "course.json"
        for raw in ('{"schema_version": 1, "schema_version": 2}', '{"schema_version": NaN}', '{', '[]'):
            with self.subTest(raw=raw):
                path.write_text(raw, encoding="utf-8")
                self.assertEqual(check_course(self.course)["material_status"], "blocked")

    def test_cli_saves_separate_reports_and_returns_a_failure_code(self):
        project = self.workspace / "project"
        project.mkdir()
        with patch("check_course.ROOT", project), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(self.course)]), 0)
            (self.course / "lesson.ipynb").unlink()
            self.assertEqual(main([str(self.course)]), 1)
        reports = list((project / "work" / "checks").glob("*/report.json"))
        self.assertEqual(len(reports), 2)
        results = [json.loads(path.read_text(encoding="utf-8")) for path in reports]
        self.assertEqual({result["material_status"] for result in results}, {"ready", "blocked"})
        self.assertTrue(all(result["execution_status"] == "not_run" for result in results))
        self.assertTrue(all(path.with_suffix(".md").is_file() for path in reports))


if __name__ == "__main__":
    unittest.main()
