import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", default="requirements/analyzed_requirements.json")
    parser.add_argument("--scenarios", default="scenarios/scenarios.json")
    parser.add_argument("--manifest", default="reports/test_execution_manifest.json")
    parser.add_argument("--pytest-junit", default="reports/junit.xml")
    parser.add_argument("--kane-results", default="reports/kane_results.json")
    parser.add_argument("--out", default="reports/traceability_matrix.md")
    parser.add_argument("--json-out", default="reports/traceability_matrix.json")
    return parser.parse_args()


FUNCTION_NAMES = {
    "SC-001": "test_sc_001_navigate_to_products_and_view_list",
    "SC-002": "test_sc_002_filter_products_by_category",
    "SC-003": "test_sc_003_click_product_view_details",
    "SC-004": "test_sc_004_product_highlights_visible_without_login",
    "SC-005": "test_sc_005_relevant_results_for_selected_filter",
}


def load_json(path, default):
    file_path = Path(path)
    if not file_path.exists():
        return default
    return json.loads(file_path.read_text(encoding="utf-8"))


def load_kane_execution_results(reports_dir):
    """Read per-test Kane result files written by the test suite."""
    results = {}
    for f in sorted(Path(reports_dir).glob("kane_result_SC-*.json")):
        try:
            item = json.loads(f.read_text(encoding="utf-8"))
            results[item["scenario_id"]] = item
        except Exception:
            continue
    return results


def load_junit_results(path):
    file_path = Path(path)
    if not file_path.exists():
        return {}
    results = {}
    xml_files = [file_path] if file_path.is_file() else sorted(file_path.rglob("*.xml"))
    for xml_file in xml_files:
        try:
            root = ET.fromstring(xml_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        for testcase in root.iter("testcase"):
            name = testcase.attrib.get("name", "")
            result = "passed"
            if testcase.find("failure") is not None or testcase.find("error") is not None:
                result = "failed"
            elif testcase.find("skipped") is not None:
                result = "skipped"
            results[name] = result
    return results


def main():
    args = parse_args()
    requirements = load_json(args.requirements, [])
    scenarios = load_json(args.scenarios, [])
    manifest = load_json(args.manifest, {})
    kane_results = {
        item["requirement_id"]: item for item in load_json(args.kane_results, [])
    }
    # Per-test Kane execution results saved by the test suite (primary source)
    kane_execution = load_kane_execution_results(Path(args.pytest_junit).parent)
    junit_results = load_junit_results(args.pytest_junit)
    scenarios_by_requirement = {scenario["requirement_id"]: scenario for scenario in scenarios}

    rows = []
    executed = 0
    passed = 0
    untested = []
    failing = []

    for requirement in requirements:
        scenario = scenarios_by_requirement.get(requirement["id"])
        test_case_id = scenario.get("test_case_id") if scenario else "n/a"
        scenario_id = scenario.get("id") if scenario else "n/a"
        function_name = FUNCTION_NAMES.get(scenario_id, f"test_{scenario_id.lower().replace('-', '_')}")
        # Kane execution result (saved per-test) is the primary source
        kane_exec = kane_execution.get(scenario_id, {})
        session_link = kane_exec.get("link", "")
        if kane_exec:
            selenium_result = kane_exec.get("status", "not_run")
        else:
            selenium_result = junit_results.get(function_name, "not_run")
        kane_result = kane_results.get(requirement["id"], {}).get("status", requirement.get("kane_status", "unknown"))
        if selenium_result != "not_run":
            overall = selenium_result
            executed += 1
            if selenium_result == "passed":
                passed += 1
        else:
            overall = "passed" if kane_result == "passed" else "failed"
            untested.append(requirement["id"])
        if overall != "passed":
            failing.append(scenario_id)

        rows.append(
            {
                "requirement_id": requirement["id"],
                "acceptance_criterion": requirement["description"],
                "scenario_id": scenario_id,
                "test_case_id": test_case_id,
                "kane_ai_result": kane_result,
                "selenium_result": selenium_result,
                "session_link": session_link,
                "analysis_note": "" if selenium_result != "not_run" else "Test result not yet available.",
                "overall": overall,
            }
        )

    pass_rate = round((passed / executed) * 100, 1) if executed else 0.0
    summary = {
        "run_type": manifest.get("run_type", "unknown"),
        "requirements_covered": len([row for row in rows if row["scenario_id"] != "n/a"]),
        "requirements_total": len(requirements),
        "executed": executed,
        "passed": passed,
        "pass_rate": pass_rate,
        "untested_requirements": untested,
        "failing_scenarios": [scenario_id for scenario_id in failing if scenario_id != "n/a"],
    }

    lines = [
        "# Traceability Matrix",
        "",
        f"- Run type: {summary['run_type']}",
        f"- Requirements covered: {summary['requirements_covered']}/{summary['requirements_total']}",
        f"- Selenium pass rate: {summary['pass_rate']}% ({summary['passed']} passed, {summary['executed'] - summary['passed']} failed or skipped)",
        "",
        "| Requirement ID | Acceptance Criterion | Scenario ID | Test Case ID | Kane Verify | Kane Execute | Session | Overall |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for row in rows:
        link_cell = f"[view]({row['session_link']})" if row.get("session_link") else "-"
        lines.append(
            f"| {row['requirement_id']} | {row['acceptance_criterion']} | {row['scenario_id']} | {row['test_case_id']} | {row['kane_ai_result']} | {row['selenium_result']} | {link_cell} | {row['overall']} |"
        )

    kane_only_issues = [row for row in rows if row["selenium_result"] == "passed" and row["kane_ai_result"] != "passed"]
    if kane_only_issues:
        lines.extend(["", "## Kane Analysis Warnings", ""])
        lines.extend([f"- {row['scenario_id']}: Kane analysis returned `{row['kane_ai_result']}` while Selenium passed." for row in kane_only_issues])

    if summary["untested_requirements"]:
        lines.extend(["", "## Untested Requirements", ""])
        lines.extend([f"- {item}" for item in summary["untested_requirements"]])

    if summary["failing_scenarios"]:
        lines.extend(["", "## Failing Scenarios", ""])
        lines.extend([f"- {item}" for item in summary["failing_scenarios"]])

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    json_path = Path(args.json_out)
    json_path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2) + "\n", encoding="utf-8")

    print(f"traceability_rows={len(rows)} pass_rate={pass_rate}")


if __name__ == "__main__":
    main()
