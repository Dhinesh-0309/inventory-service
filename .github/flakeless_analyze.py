"""
Flakeless ML — CI analysis script.
Reads test-results.xml, classifies each failure, writes flakeless-report.json.
Runs as a standalone step in GitHub Actions — no inline heredoc needed.
"""
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

XML_PATH    = "test-results.xml"
REPORT_PATH = "flakeless-report.json"

if not Path(XML_PATH).exists():
    print("No test-results.xml found — skipping analysis.")
    sys.exit(0)

root   = ET.parse(XML_PATH).getroot()
suites = root.findall(".//testsuite") or [root]

failures = []
total    = 0
failed   = 0

for suite in suites:
    for tc in suite.findall("testcase"):
        total += 1
        fn = tc.find("failure") or tc.find("error")
        if fn is None:
            continue
        failed += 1
        msg  = fn.get("message", "")
        body = (fn.text or "").lower()
        text = (msg + " " + body).lower()

        if any(k in text for k in ["timeout", "timed out", "cache miss", "latency", "slow"]):
            priority   = "P2"
            assessment = "LIKELY FLAKY"
            reason     = "Timing/latency error — pattern consistent with intermittent failure."
        elif any(k in text for k in ["importerror", "cannot import", "attributeerror",
                                      "404", "renamed", "removed"]):
            priority   = "P1"
            assessment = "POTENTIAL REGRESSION"
            reason     = "Import or attribute error — pattern consistent with a breaking code change."
        else:
            priority   = "P3"
            assessment = "INSUFFICIENT EVIDENCE"
            reason     = "Not enough context. Check history and recent commits."

        failures.append({
            "test_id":    f"{tc.get('classname', '')}::{tc.get('name', '')}",
            "priority":   priority,
            "assessment": assessment,
            "reason":     reason,
            "error_msg":  msg[:300],
        })

report = {
    "run_id":       os.environ.get("GITHUB_RUN_ID", "local"),
    "sha":          os.environ.get("GITHUB_SHA", "unknown")[:7],
    "branch":       os.environ.get("GITHUB_REF_NAME", "unknown"),
    "total_tests":  total,
    "failed_tests": failed,
    "passed_tests": total - failed,
    "failures":     failures,
}

Path(REPORT_PATH).write_text(json.dumps(report, indent=2))

print()
print("=" * 55)
print("  FLAKELESS ML — CI FAILURE ANALYSIS")
print("=" * 55)
print(f"  Commit : {report['sha']}  Branch: {report['branch']}")
print(f"  Tests  : {total} total | {failed} failed | {total - failed} passed")
print()
for f in failures:
    print(f"  [{f['priority']}]  {f['assessment']}")
    print(f"        {f['test_id']}")
    print(f"        {f['reason']}")
    print()
if not failures:
    print("  All tests passed — no failures to analyze.")
print("=" * 55)
