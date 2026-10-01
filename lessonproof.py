"""Validate execution evidence against a fixed lesson contract; never execute code."""

import json


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _steps(document, name):
    if not isinstance(document, dict) or type(document.get("schema_version")) is not int:
        raise ValueError(f"{name}: schema_version must be integer 1")
    if document["schema_version"] != 1 or not isinstance(document.get("steps"), list):
        raise ValueError(f"{name}: unsupported schema or missing steps")
    identifiers = set()
    for step in document["steps"]:
        if not isinstance(step, dict) or not isinstance(step.get("id"), str) or not step["id"].strip():
            raise ValueError(f"{name}: each step needs a non-empty string id")
        if step["id"] in identifiers:
            raise ValueError(f"{name}: duplicate step id {step['id']}")
        identifiers.add(step["id"])
    return document["steps"]


def validate_contract(contract):
    """Validate the fixed expectations without requiring execution evidence."""
    expected_steps = _steps(contract, "contract")
    if not expected_steps:
        raise ValueError("contract: at least one step is required")

    for step in expected_steps:
        expect = step.get("expect")
        if not isinstance(expect, dict) or expect.get("outcome") not in ("ok", "error"):
            raise ValueError("contract: expect.outcome must be ok or error")
        if set(expect) - {"outcome", "stdout", "stdout_json", "error_type", "message_contains"}:
            raise ValueError("contract: unknown expectation field")
        if "stdout" in expect and not isinstance(expect["stdout"], str):
            raise ValueError("contract: stdout must be a string")
        if "stdout" in expect and "stdout_json" in expect:
            raise ValueError("contract: choose stdout or stdout_json")
        if "stdout_json" in expect:
            _json(expect["stdout_json"])
        if expect["outcome"] == "error":
            if not isinstance(expect.get("error_type"), str) or not expect["error_type"]:
                raise ValueError("contract: expected error needs error_type")
        elif "error_type" in expect or "message_contains" in expect:
            raise ValueError("contract: error expectations require outcome=error")
        if "message_contains" in expect and not isinstance(expect["message_contains"], str):
            raise ValueError("contract: message_contains must be a string")
    return expected_steps


def assess_run(contract, run):
    """Return passed/failed/inconclusive, with one evidence finding per check."""
    expected_steps = validate_contract(contract)
    actual_steps = _steps(run, "run")
    if type(run.get("complete")) is not bool:
        raise ValueError("run: complete must be a boolean")

    for step in actual_steps:
        if step.get("outcome") not in ("ok", "error", "unavailable"):
            raise ValueError("run: unsupported outcome")
        for field in ("stdout", "stderr"):
            if not isinstance(step.get(field), str):
                raise ValueError(f"run: {field} must be a string")
        if step["outcome"] == "error":
            for field in ("error_type", "error_message"):
                if not isinstance(step.get(field), str):
                    raise ValueError(f"run: error needs {field}")

    findings = []

    def add(step_id, status, reason, evidence=None):
        findings.append({"step_id": step_id, "status": status, "reason": reason, "evidence": evidence})

    expected_ids = [step["id"] for step in expected_steps]
    actual_ids = [step["id"] for step in actual_steps]
    known_ids = [identifier for identifier in actual_ids if identifier in expected_ids]
    if known_ids != [identifier for identifier in expected_ids if identifier in known_ids]:
        add(None, "failed", "step_order_mismatch", actual_ids)
    for identifier in actual_ids:
        if identifier not in expected_ids:
            add(identifier, "failed", "unplanned_step")
    if not run["complete"]:
        add(None, "inconclusive", "execution_incomplete", run.get("runner_error"))

    actual_by_id = {step["id"]: step for step in actual_steps}
    for planned in expected_steps:
        identifier, expect = planned["id"], planned["expect"]
        actual = actual_by_id.get(identifier)
        if actual is None or actual["outcome"] == "unavailable":
            add(identifier, "inconclusive", "missing_execution_evidence", actual)
            continue
        if actual["outcome"] != expect["outcome"]:
            add(identifier, "failed", "unexpected_outcome", actual)
            continue
        if expect["outcome"] == "error":
            if actual["error_type"] != expect["error_type"]:
                add(identifier, "failed", "unexpected_error_type", actual)
                continue
            if expect.get("message_contains", "") not in actual["error_message"]:
                add(identifier, "failed", "unexpected_error_message", actual)
                continue
        if "stdout" in expect and actual["stdout"].strip() != expect["stdout"].strip():
            add(identifier, "failed", "stdout_mismatch", {"expected": expect["stdout"], "actual": actual["stdout"]})
            continue
        if "stdout_json" in expect:
            try:
                observed = json.loads(actual["stdout"], object_pairs_hook=_unique_object)
                matches = _json(observed) == _json(expect["stdout_json"])
            except (ValueError, TypeError):
                add(identifier, "failed", "invalid_json_output", actual["stdout"])
                continue
            if not matches:
                add(identifier, "failed", "output_mismatch", {"expected": expect["stdout_json"], "actual": observed})
                continue
        add(identifier, "passed", "expectation_met")

    statuses = {finding["status"] for finding in findings}
    status = "failed" if "failed" in statuses else "inconclusive" if "inconclusive" in statuses else "passed"
    return {"status": status, "findings": findings}
