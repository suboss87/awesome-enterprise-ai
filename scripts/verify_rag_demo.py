"""Reproduce the pinned RAG demo; any unexpected outcome fails verification."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def verify(checkout):
    reports = []
    with tempfile.TemporaryDirectory(prefix="rag-scope-verify-") as temporary:
        for corrected in (False, True):
            command = [sys.executable, "examples/sqlite_acl_demo.py"]
            if corrected:
                command.append("--sync-permissions")
            fixture = subprocess.run(command, cwd=checkout, check=True,
                                     capture_output=True, text=True, timeout=30)
            path = Path(temporary) / ("corrected.jsonl" if corrected else "stale.jsonl")
            path.write_text(fixture.stdout)
            result = subprocess.run(
                [sys.executable, "-m", "rag_scope_check", str(path),
                 "--min-cohort-recall", "0.8", "--max-underfill-rate", "0", "--format", "json"],
                cwd=checkout, capture_output=True, text=True, timeout=30)
            expected_exit = 0 if corrected else 1
            if result.returncode != expected_exit:
                raise ValueError(f"Expected exit {expected_exit}, got {result.returncode}: {result.stderr}")
            report = json.loads(result.stdout)
            if report["limits"] != {"min_cohort_recall": 0.8, "max_underfill_rate": 0.0,
                                   "max_policy_age_hours": None}:
                raise ValueError("Gate did not use the requested thresholds")
            expected = {
                "verdict": "PASS" if corrected else "FAIL",
                "recall": 1.0 if corrected else 0.0,
                "underfill": 0.0 if corrected else 1.0,
            }
            if report["case_count"] != 1 or len(report["cohorts"]) != 1 or len(report["cases"]) != 1:
                raise ValueError("Expected exactly one case and cohort")
            cohort = report["cohorts"][0]
            if (report["verdict"] != expected["verdict"]
                    or cohort["mean_authorized_recall"] != expected["recall"]
                    or cohort["underfill_rate"] != expected["underfill"]
                    or cohort["leaking_cases"] != 0
                    or report["cases"][0]["leaked_doc_ids"] != []):
                raise ValueError(f"Unexpected demo measurements: {report}")
            reports.append(report)
            print(f"{'corrected' if corrected else 'stale'}: expected {expected['verdict']}, "
                  f"recall={expected['recall']}, underfill={expected['underfill']}, zero leaks")
    if reports[0]["limits"] != reports[1]["limits"]:
        raise ValueError("Failure and correction used different thresholds")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 scripts/verify_rag_demo.py /path/to/rag-scope-check")
    verify(Path(sys.argv[1]).resolve())
