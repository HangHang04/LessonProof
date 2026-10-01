"""Real GitHub + sandbox + Ollama + Git integration, separate from human trials."""
import json
import sys
import time
from uuid import uuid4
import zipfile

import workbench as work


def wait_for_run(job):
    work.begin_run(job["id"], job["version_hash"], True)
    deadline = time.monotonic() + 300
    while job["id"] in work.ACTIVE:
        if time.monotonic() > deadline:
            raise TimeoutError("Integration run did not finish in 300 seconds")
        time.sleep(1)
    result = work.load(job["id"])
    assert result["phase"] in ("needs_review", "awaiting_approval"), result.get("error") or result
    run = result["runs"][-1]
    assert run["assessment"]["status"] == "passed" and run["environment_matches"], run
    assert run["ai_status"] == "completed" and all(source["matched"] for source in run["sources"]), run
    return result


def main():
    work.STORE = work.ROOT / "work" / "integration" / uuid4().hex
    results = []
    for sample in work.SAMPLES:
        job = work.create_job(sample)
        original_contract = job["contract_sha256"]
        job = wait_for_run(job)
        print(f"{sample}: {job['phase']}", flush=True)
        if sample == "pandas-error-version":
            proposal = job["runs"][-1]["ai"]
            assert job["phase"] == "needs_review" and proposal["findings"], proposal
            assert proposal["patches"] and all(patch["file"] == "lesson.md" for patch in proposal["patches"]), proposal
            before = work.read_file(work.revision_dir(job), "lesson.ipynb")
            job = work.apply_proposal(job["id"], job["version_hash"])
            assert before == work.read_file(work.revision_dir(job), "lesson.ipynb")
            job = wait_for_run(job)
            print(f"{sample} repaired: {job['phase']}", flush=True)
        assert job["phase"] == "awaiting_approval", job["runs"][-1]
        assert job["contract_sha256"] == original_contract
        job = work.approve(job["id"], job["version_hash"], True)
        job = work.deliver(job["id"], job["version_hash"])
        assert job["delivery"]["readback_matched"]
        again = work.deliver(job["id"], job["version_hash"])
        assert again["delivery"] == job["delivery"], "Repeated delivery must be idempotent"
        with zipfile.ZipFile(work.delivery_file(job["id"], "course.zip")) as archive:
            assert "acceptance.json" not in archive.namelist() and "reference.md" not in archive.namelist()
            if sample == "pandas-error-version":
                assert "IntCastingNaNError: Cannot convert non-finite values (NA or inf) to integer" in archive.read("lesson.md").decode()
        results.append({"sample": sample, "job_id": job["id"], "revision": job["revision"], "delivery": job["delivery"]})
        print(f"{sample}: delivery readback verified", flush=True)
    work.write_json(work.STORE / "verification.json", {"kind": "developer_integration_check", "at": work.now(), "results": results})
    print("真实集成验证通过：" + str(work.STORE / "verification.json"), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
