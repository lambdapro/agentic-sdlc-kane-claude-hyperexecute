import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", default="requirements/analyzed_requirements.json")
    parser.add_argument("--scenarios", default="scenarios/scenarios.json")
    return parser.parse_args()


def load_json(path, default):
    file_path = Path(path)
    if not file_path.exists():
        return default
    content = file_path.read_text(encoding="utf-8").strip()
    if not content:
        return default
    return json.loads(content)


def title_and_steps(requirement):
    requirement_id = requirement["id"]
    description = requirement["description"].lower()
    if requirement_id == "AC-001" or "available credit cards" in description:
        return (
            "Navigate to credit cards section and view available card list",
            [
                "Navigate to https://www.americanexpress.com/",
                "Locate and click the Credit Cards navigation link",
                "Verify the credit cards listing page loads",
                "Verify multiple card tiles are visible on the page",
            ],
            "A list of available American Express credit cards is displayed with card tiles and filter options visible",
        )
    if "use filters" in description:
        return (
            "Filter credit cards by category (rewards, travel, cashback)",
            [
                "Navigate to https://www.americanexpress.com/",
                "Go to the credit cards section",
                "Locate filter chips such as Travel, Cash Back, or Rewards",
                "Click a filter chip",
                "Verify the card list updates to show filtered results",
            ],
            "Filtered credit card results are displayed below the filter chips after applying a filter",
        )
    if "click on a credit card" in description:
        return (
            "Click a credit card to view details including benefits, fees, and rewards",
            [
                "Navigate to https://www.americanexpress.com/",
                "Go to the credit cards section",
                "Click on any credit card tile or View Details link",
                "Verify the card detail page loads",
                "Verify benefits, annual fee, and rewards information is visible",
            ],
            "Card detail page is displayed showing benefits, annual fee, and rewards or points information",
        )
    if "without logging in" in description:
        return (
            "View card highlights and comparison without logging in",
            [
                "Navigate to https://www.americanexpress.com/ without logging in",
                "Go to the credit cards section",
                "Verify card highlights or comparison section is visible",
                "Verify no login prompt blocks the content",
            ],
            "Card highlights and featured benefits are visible on the credit cards page without requiring login",
        )
    return (
        "Search results are relevant to selected filters or criteria",
        [
            "Navigate to https://www.americanexpress.com/",
            "Go to the credit cards section",
            "Apply a filter such as Travel",
            "Verify the displayed cards are relevant to the selected filter",
            "Check that card descriptions or labels match the filter category",
        ],
        "Cards shown after applying a filter are relevant to the selected category, such as travel cards appearing when the Travel filter is applied",
    )


def main():
    args = parse_args()
    requirements = load_json(args.requirements, [])
    scenarios = load_json(args.scenarios, [])
    existing_by_requirement = {scenario["requirement_id"]: scenario for scenario in scenarios}
    today = datetime.now(timezone.utc).date().isoformat()

    updated = []
    counts = {"active": 0, "updated": 0, "new": 0, "deprecated": 0}
    active_requirement_ids = set()

    for index, requirement in enumerate(requirements, start=1):
        active_requirement_ids.add(requirement["id"])
        title, steps, expected = title_and_steps(requirement)
        scenario = existing_by_requirement.get(requirement["id"])
        status = "new"
        if scenario:
            status = "active" if scenario.get("source_description") == requirement["description"] else "updated"
        else:
            scenario = {}

        record = {
            "id": scenario.get("id", f"SC-{index:03d}"),
            "requirement_id": requirement["id"],
            "title": title,
            "steps": steps,
            "expected_result": expected,
            "status": status,
            "kane_objective": requirement["description"],
            "kane_url": requirement["url"],
            "kane_last_status": requirement.get("kane_status", "pending"),
            "test_case_id": scenario.get("test_case_id", f"TC-{index:03d}"),
            "last_verified": today,
            "source_description": requirement["description"],
        }

        if requirement.get("kane_status") == "failed":
            record["kane_failure_reason"] = requirement.get("kane_summary", "")

        updated.append(record)
        counts[status] += 1

    for scenario in scenarios:
        if scenario["requirement_id"] in active_requirement_ids:
            continue
        deprecated = dict(scenario)
        deprecated["status"] = "deprecated"
        updated.append(deprecated)
        counts["deprecated"] += 1

    output = Path(args.scenarios)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")

    print(
        f"active={counts['active']} updated={counts['updated']} new={counts['new']} deprecated={counts['deprecated']}"
    )


if __name__ == "__main__":
    main()
