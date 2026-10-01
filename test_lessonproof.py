import copy
import json
from pathlib import Path
import unittest

from lessonproof import assess_run


CONTRACT = json.loads((Path(__file__).parent / "examples" / "library" / "acceptance.json").read_text(encoding="utf-8"))
RUN = {"schema_version": 1, "complete": True, "steps": [
    {"id": "load-data", "outcome": "ok", "stdout": "", "stderr": ""},
    {"id": "summarize", "outcome": "ok", "stdout": '{"book_count": 3, "total_borrows": 10}\n', "stderr": ""},
]}


class AcceptanceTests(unittest.TestCase):
    def test_correct_output_and_input_immutability(self):
        contract, run = copy.deepcopy(CONTRACT), copy.deepcopy(RUN)
        self.assertEqual(assess_run(contract, run)["status"], "passed")
        self.assertEqual(contract, CONTRACT)
        self.assertEqual(run, RUN)

    def test_running_code_with_wrong_result_fails(self):
        run = copy.deepcopy(RUN)
        run["steps"][1]["stdout"] = '{"book_count": 3, "total_borrows": 30}'
        result = assess_run(CONTRACT, run)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["findings"][-1]["reason"], "output_mismatch")

    def test_expected_error_requires_matching_type_and_message(self):
        contract, run = copy.deepcopy(CONTRACT), copy.deepcopy(RUN)
        contract["steps"][1]["expect"] = {"outcome": "error", "error_type": "ValueError", "message_contains": "unknown"}
        run["steps"][1].update(outcome="error", stdout="", error_type="ValueError", error_message="unknown value")
        self.assertEqual(assess_run(contract, run)["status"], "passed")
        run["steps"][1]["error_type"] = "KeyError"
        self.assertEqual(assess_run(contract, run)["status"], "failed")
        run["steps"][1].update(error_type="ValueError", error_message="different problem")
        self.assertEqual(assess_run(contract, run)["status"], "failed")

    def test_missing_and_interrupted_execution_are_inconclusive(self):
        run = copy.deepcopy(RUN)
        run["steps"].pop()
        self.assertEqual(assess_run(CONTRACT, run)["status"], "inconclusive")
        run = copy.deepcopy(RUN)
        run["complete"] = False
        self.assertEqual(assess_run(CONTRACT, run)["status"], "inconclusive")
        run["steps"][1]["outcome"] = "unavailable"
        self.assertEqual(assess_run(CONTRACT, run)["status"], "inconclusive")

    def test_unexpected_exception_is_failure(self):
        run = copy.deepcopy(RUN)
        run["steps"][0].update(outcome="error", error_type="FileNotFoundError", error_message="loans.csv")
        self.assertEqual(assess_run(CONTRACT, run)["status"], "failed")

    def test_reordered_or_undocumented_actions_fail(self):
        run = copy.deepcopy(RUN)
        run["steps"].reverse()
        self.assertEqual(assess_run(CONTRACT, run)["status"], "failed")
        run = copy.deepcopy(RUN)
        run["steps"].append({"id": "extra-install", "outcome": "ok", "stdout": "", "stderr": ""})
        self.assertEqual(assess_run(CONTRACT, run)["status"], "failed")

    def test_json_values_are_checked_strictly(self):
        contract = {"schema_version": 1, "steps": [{"id": "count", "expect": {"outcome": "ok", "stdout_json": {"count": 1}}}]}
        for output in ('{"count": true}', '{"count": NaN}', 'not json', '{"count": 1, "extra": 2}', '{"count": 99, "count": 1}'):
            with self.subTest(output=output):
                run = {"schema_version": 1, "complete": True, "steps": [{"id": "count", "outcome": "ok", "stdout": output, "stderr": ""}]}
                self.assertEqual(assess_run(contract, run)["status"], "failed")

    def test_malformed_evidence_or_contract_is_rejected(self):
        invalid_runs = []
        run = copy.deepcopy(RUN)
        run["complete"] = "true"
        invalid_runs.append(run)
        run = copy.deepcopy(RUN)
        run["steps"].append(copy.deepcopy(run["steps"][0]))
        invalid_runs.append(run)
        run = copy.deepcopy(RUN)
        del run["steps"][0]["stdout"]
        invalid_runs.append(run)
        for run in invalid_runs:
            with self.subTest(run=run), self.assertRaises(ValueError):
                assess_run(CONTRACT, run)
        contract = copy.deepcopy(CONTRACT)
        contract["steps"][0]["expect"]["stdotu"] = ""
        with self.assertRaises(ValueError):
            assess_run(contract, RUN)
        with self.assertRaises(ValueError):
            assess_run({"schema_version": 1, "steps": []}, RUN)


if __name__ == "__main__":
    unittest.main()
