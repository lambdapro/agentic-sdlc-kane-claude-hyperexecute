# Agentic SDLC Pipeline

This file is the natural language instruction file for the agentic CI/CD pipeline.
Any CI tool invokes a stage by running:
  claude -p "Execute stage: <STAGE_NAME> from PIPELINE.md"

Claude Code reads this file, finds the matching stage, and executes it autonomously
using the tools available (file read/write, kane-cli, bash commands).

---

## Stage: ANALYZE_REQUIREMENTS

**Goal:** Parse requirements and confirm each acceptance criterion is observable on the live site.

Instructions:
1. Read all files inside `requirements/` directory
2. Extract every acceptance criterion as a structured item with fields:
   - id: sequential (AC-001, AC-002, ...)
   - title: short label
   - description: full acceptance criterion text
   - url: https://www.americanexpress.com/
3. For each acceptance criterion, run a kane-cli verification:
   ```
   kane-cli run "<criterion as objective>" --url https://www.americanexpress.com/ \
     --username $LT_USERNAME --access-key $LT_ACCESS_KEY \
     --agent --headless --timeout 120 --max-steps 15
   ```
4. Parse the run_end event (last line of stdout) for each kane run:
   - Record status (passed/failed), one_liner, final_state, duration
5. Write output to `requirements/analyzed_requirements.json` with schema:
   ```json
   [
     {
       "id": "AC-001",
       "title": "...",
       "description": "...",
       "url": "https://www.americanexpress.com/",
       "kane_status": "passed|failed",
       "kane_summary": "...",
       "kane_final_state": {},
       "last_analyzed": "<ISO date>"
     }
   ]
   ```
6. Print a summary table: requirement ID, title, Kane status

---

## Stage: MANAGE_SCENARIOS

**Goal:** Synchronise scenarios.json with the analyzed requirements — update changed, add new, deprecate removed.

Instructions:
1. Load `requirements/analyzed_requirements.json`
2. Load `scenarios/scenarios.json` (treat as empty array if file is missing or empty)
3. For each analyzed requirement:
   a. Check if a scenario exists with matching `requirement_id`
   b. If **exists and description unchanged**: leave as-is, status stays "active"
   c. If **exists but description changed**: update `title`, `steps`, `expected_result`,
      `kane_objective`; set `status` to "updated"; update `last_verified`
   d. If **no matching scenario**: create a new scenario entry with status "new"
4. For any scenario whose `requirement_id` is no longer in analyzed_requirements: set status "deprecated"
5. New scenario schema:
   ```json
   {
     "id": "SC-001",
     "requirement_id": "AC-001",
     "title": "<short descriptive title>",
     "steps": [
       "Navigate to americanexpress.com",
       "Click on credit cards navigation link",
       "Verify card listing section appears with multiple tiles"
     ],
     "expected_result": "<what success looks like>",
     "status": "new|active|updated|deprecated",
     "kane_objective": "<full plain-English objective for kane-cli run>",
     "kane_url": "https://www.americanexpress.com/",
     "test_case_id": "TC-001",
     "last_verified": "<ISO date>"
   }
   ```
6. Save updated array to `scenarios/scenarios.json`
7. Print summary: N active, N updated, N new, N deprecated

---

## Stage: GENERATE_TESTS

**Goal:** Generate or update Selenium Python test cases for all new/updated scenarios.

Instructions:
1. Load `scenarios/scenarios.json`
2. Filter scenarios where `status` is "new" or "updated"
3. Load existing `tests/selenium/test_credit_cards.py` if it exists
4. For each new/updated scenario:
   a. Check if a test function named `test_<scenario_id_lowercase>` already exists in the file
   b. If exists: update the test body to match the new scenario steps and expected_result
   c. If not exists: append a new test function
5. Each test function must:
   - Be decorated with `@pytest.mark.scenario("<scenario_id>")` and `@pytest.mark.requirement("<requirement_id>")`
   - Use the `driver` fixture from conftest.py
   - Use the `CreditCardsPage` page object from `tests/selenium/pages/credit_cards_page.py`
   - Assert the expected_result condition
   - Have a docstring matching the scenario title
6. Also update `kane/objectives.json` — add/update entries for new/updated scenarios
7. Write the updated test file and objectives file
8. Print: N tests added, N tests updated

---

## Stage: SELECT_TESTS

**Goal:** Decide which tests to run based on what changed, and write an execution manifest.

Instructions:
1. Load `scenarios/scenarios.json`
2. Load `kane/objectives.json`
3. Build a selection list:
   - Always include: scenarios with status "new" or "updated"
   - Include on full run (FULL_RUN env var == "true"): all "active" scenarios
   - Exclude: "deprecated" scenarios
4. Write `reports/test_execution_manifest.json`:
   ```json
   {
     "run_type": "incremental|full",
     "selected_scenarios": ["SC-001", "SC-002"],
     "selected_test_ids": ["TC-001", "TC-002"],
     "excluded_scenarios": ["SC-005"],
     "exclusion_reason": {"SC-005": "deprecated"},
     "generated_at": "<ISO datetime>"
   }
   ```
5. Write `reports/pytest_selection.txt` — one test node ID per line (e.g. `tests/selenium/test_credit_cards.py::test_sc_001`)
6. Print the selection summary

---

## Stage: TRACEABILITY_REPORT

**Goal:** Generate a full traceability matrix linking requirements → scenarios → test cases → results.

Instructions:
1. Load `requirements/analyzed_requirements.json`
2. Load `scenarios/scenarios.json`
3. Load `reports/test_execution_manifest.json`
4. Load pytest HTML/JSON report from `reports/` (parse junit XML if present, else infer from artifacts)
5. Load kane-cli results from `reports/kane_results.json` if present
6. Build the matrix table with columns:
   Requirement ID | Acceptance Criterion | Scenario ID | Test Case ID | Kane AI Result | Selenium Result | Overall
7. Compute:
   - Total requirements covered
   - Pass rate (passed / total executed)
   - Any untested requirements
   - Any failing scenarios
8. Write `reports/traceability_matrix.md` as a full markdown document with the table + summary stats

---

## Stage: RELEASE_RECOMMENDATION

**Goal:** Analyse the traceability matrix and produce a QA release recommendation.

Instructions:
1. Load `reports/traceability_matrix.md`
2. Load `scenarios/scenarios.json`
3. Evaluate:
   - GREEN (approve release) if: pass rate >= 90% AND no critical scenarios failing AND all requirements have at least one test
   - YELLOW (conditional approval) if: pass rate >= 75% AND failing tests are non-critical (marked low/medium priority)
   - RED (block release) if: pass rate < 75% OR any critical scenario is failing OR requirements exist with zero test coverage
4. Write `reports/release_recommendation.md`:
   ```markdown
   # QA Release Recommendation

   **Verdict:** ✅ GREEN / ⚠️ YELLOW / ❌ RED

   ## Summary
   - Requirements covered: N/N
   - Scenarios executed: N
   - Pass rate: N% (N passed, N failed)

   ## Failing Scenarios
   | Scenario | Test | Failure Reason | Severity |
   ...

   ## Untested Requirements
   ...

   ## Recommendation
   <Plain English paragraph: should QA sign off or not, and why>
   ```
5. Print the verdict and one-line reason to stdout
