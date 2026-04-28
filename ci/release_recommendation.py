import argparse
import json
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-json", default="reports/traceability_matrix.json")
    parser.add_argument("--out", default="reports/release_recommendation.md")
    return parser.parse_args()


def verdict_for(summary):
    has_untested = bool(summary.get("untested_requirements"))
    has_failures = bool(summary.get("failing_scenarios"))
    pass_rate = summary.get("pass_rate", 0)
    if pass_rate >= 90 and not has_failures and not has_untested:
        return "GREEN", "Approve release because coverage is complete and executed tests passed."
    if pass_rate >= 75 and not has_untested:
        return "YELLOW", "Conditional approval because coverage exists but there are remaining execution issues."
    return "RED", "Block release because pass rate or coverage is below the acceptance threshold."


def main():
    args = parse_args()
    payload = json.loads(Path(args.trace_json).read_text(encoding="utf-8"))
    summary = payload["summary"]
    verdict, recommendation = verdict_for(summary)

    failing = summary.get("failing_scenarios", [])
    untested = summary.get("untested_requirements", [])

    lines = [
        "# QA Release Recommendation",
        "",
        f"**Verdict:** {verdict}",
        "",
        "## Summary",
        f"- Requirements covered: {summary['requirements_covered']}/{summary['requirements_total']}",
        f"- Scenarios executed: {summary['executed']}",
        f"- Pass rate: {summary['pass_rate']}% ({summary['passed']} passed, {summary['executed'] - summary['passed']} failed or skipped)",
        "",
        "## Failing Scenarios",
    ]

    if failing:
        lines.extend([f"- {item}" for item in failing])
    else:
        lines.append("- None")

    lines.extend(["", "## Untested Requirements"])
    if untested:
        lines.extend([f"- {item}" for item in untested])
    else:
        lines.append("- None")

    lines.extend(["", "## Recommendation", recommendation])

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{verdict}: {recommendation}")


if __name__ == "__main__":
    main()
