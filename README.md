# Agentic SDLC — AmEx Credit Cards

An end-to-end **agentic Software Development Lifecycle** demonstration where plain-English requirements automatically drive scenario generation, test creation, parallel cloud execution, and a QA release recommendation — with no manual scripting.

## How It Works

```
requirements/search.txt  (plain English user story)
        │
        ▼
Stage 1: ANALYZE_REQUIREMENTS
  Claude Code + Kane CLI browse americanexpress.com
  and confirm each acceptance criterion is observable on the live site
        │
        ▼
Stage 2: MANAGE_SCENARIOS
  Diffs scenarios.json — updates changed, adds new, deprecates removed
        │
        ▼
Stage 3: GENERATE_TESTS
  Writes/updates Selenium Python test cases for every new or changed scenario
        │
        ▼
Stage 4: SELECT_TESTS → HyperExecute
  Claude picks which tests to run, HyperExecute runs them in parallel (4 VMs)
        │
        ▼
Stage 5: TRACEABILITY_REPORT + RELEASE_RECOMMENDATION
  Requirement → Scenario → Test → Result matrix + GREEN/YELLOW/RED QA verdict
```

The entire pipeline is controlled by **`PIPELINE.md`** — a plain-English instruction file. Claude Code reads it and executes each stage autonomously. The same command works in GitHub Actions, GitLab CI, Jenkins, or Bitbucket:

```bash
claude -p "Execute stage: <STAGE_NAME> from PIPELINE.md"
```

---

## Repository Structure

```
.
├── PIPELINE.md                          # Natural language CI instruction file
├── CLAUDE.md                            # Claude Code project configuration
├── hyperexecute.yaml                    # HyperExecute cloud execution config
├── requirements.txt                     # Python dependencies
│
├── requirements/
│   └── search.txt                       # Input: plain-English user story
│
├── scenarios/
│   └── scenarios.json                   # Managed test scenarios (auto-updated)
│
├── kane/
│   └── objectives.json                  # Kane CLI objectives per scenario
│
├── tests/selenium/
│   ├── conftest.py                      # pytest fixtures + LambdaTest WebDriver
│   ├── pages/
│   │   └── credit_cards_page.py         # Page Object Model
│   └── test_credit_cards.py             # 5 Selenium test cases (TC-001 to TC-005)
│
├── reports/                             # Runtime output — gitignored
│   ├── traceability_matrix.md
│   └── release_recommendation.md
│
└── .github/workflows/
    └── agentic-sdlc.yml                 # 5-stage GitHub Actions pipeline
```

---

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Node.js | 18+ | https://nodejs.org |
| Python | 3.11+ | https://python.org |
| Google Chrome | Latest | https://www.google.com/chrome |
| Kane CLI | Latest | `npm install -g @testmuai/kane-cli` |
| Claude Code | Latest | `npm install -g @anthropic-ai/claude-code` |

---

## Quick Start

### 1. Clone and install

```bash
git clone <your-repo-url>
cd amex

# Install Kane CLI and Claude Code
npm install -g @testmuai/kane-cli @anthropic-ai/claude-code

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Set credentials

All three tools — Claude Code, Kane CLI, and HyperExecute — authenticate from environment variables. Set them once and every tool picks them up automatically.

```bash
# LambdaTest (Kane CLI + HyperExecute)
export LT_USERNAME=your_lambdatest_username
export LT_ACCESS_KEY=your_lambdatest_access_key

# Anthropic (Claude Code)
export ANTHROPIC_API_KEY=your_anthropic_api_key
```

To persist across terminal sessions, add the exports to your shell profile:

```bash
# ~/.zshrc or ~/.bashrc
echo 'export LT_USERNAME=your_lambdatest_username' >> ~/.zshrc
echo 'export LT_ACCESS_KEY=your_lambdatest_access_key' >> ~/.zshrc
echo 'export ANTHROPIC_API_KEY=your_anthropic_api_key' >> ~/.zshrc
source ~/.zshrc
```

**Where to get each credential:**

| Credential | Source |
|---|---|
| `LT_USERNAME` | [LambdaTest Dashboard → Settings → Keys](https://accounts.lambdatest.com/security) |
| `LT_ACCESS_KEY` | Same page as above |
| `ANTHROPIC_API_KEY` | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) |

### 3. Authenticate each tool

**Claude Code** — picks up `ANTHROPIC_API_KEY` automatically. Verify:
```bash
claude --version
```

**Kane CLI** — authenticate using Basic Auth (works in all contexts including CI and agent mode where a browser cannot open):
```bash
kane-cli login --username $LT_USERNAME --access-key $LT_ACCESS_KEY

# Verify
kane-cli whoami
```

**HyperExecute CLI** — no separate login needed. Credentials are passed via `--user` and `--key` flags at runtime, which read from the environment:
```bash
./hyperexecute --user $LT_USERNAME --key $LT_ACCESS_KEY --config hyperexecute.yaml
```

---

## Running the Agentic Pipeline Locally

Run all stages in sequence:

```bash
claude -p "Execute stage: ANALYZE_REQUIREMENTS from PIPELINE.md"
claude -p "Execute stage: MANAGE_SCENARIOS from PIPELINE.md"
claude -p "Execute stage: GENERATE_TESTS from PIPELINE.md"
claude -p "Execute stage: SELECT_TESTS from PIPELINE.md"
claude -p "Execute stage: TRACEABILITY_REPORT from PIPELINE.md"
claude -p "Execute stage: RELEASE_RECOMMENDATION from PIPELINE.md"
```

Run a single stage at any time — useful when iterating on requirements:

```bash
# Re-analyze after editing requirements/search.txt
claude -p "Execute stage: ANALYZE_REQUIREMENTS from PIPELINE.md"

# Regenerate tests after scenarios change
claude -p "Execute stage: GENERATE_TESTS from PIPELINE.md"

# Rebuild the traceability matrix after a test run
claude -p "Execute stage: TRACEABILITY_REPORT from PIPELINE.md"
```

---

## Running Tests Directly

### Locally — headless Chrome, no LambdaTest grid

```bash
pytest tests/selenium/ -v
```

### Single test case

```bash
pytest tests/selenium/test_credit_cards.py::test_sc_001_navigate_to_credit_cards_and_view_list -v
```

### Filter by scenario keyword

```bash
pytest tests/selenium/ -v -k "sc_001 or sc_002"
```

### With HTML report

```bash
pytest tests/selenium/ -v --html=reports/results.html --self-contained-html
```

### On LambdaTest remote grid

```bash
export LT_USERNAME=your_username
export LT_ACCESS_KEY=your_access_key

pytest tests/selenium/ -v --html=reports/results.html --self-contained-html
```

### On HyperExecute — parallel cloud execution across 4 VMs

```bash
# Linux
curl -O https://downloads.lambdatest.com/hyperexecute/linux/hyperexecute
chmod +x hyperexecute

# macOS
# curl -O https://downloads.lambdatest.com/hyperexecute/darwin/hyperexecute
# chmod +x hyperexecute

# Windows PowerShell
# Invoke-WebRequest -Uri https://downloads.lambdatest.com/hyperexecute/windows/hyperexecute.exe -OutFile hyperexecute.exe

./hyperexecute --user $LT_USERNAME --key $LT_ACCESS_KEY --config hyperexecute.yaml
```

---

## Kane CLI — Manual Scenario Verification

Run any scenario objective directly against the live site and get a structured result:

```bash
# SC-001: Verify credit card listing is visible
kane-cli run \
  "Navigate to the credit cards section of americanexpress.com and verify a list of available credit cards is displayed" \
  --url https://www.americanexpress.com/ \
  --username $LT_USERNAME --access-key $LT_ACCESS_KEY \
  --agent --headless --timeout 120

# SC-002: Verify filters work
kane-cli run \
  "Navigate to the credit cards section of americanexpress.com, apply a Travel filter, and verify filtered card results appear" \
  --url https://www.americanexpress.com/ \
  --username $LT_USERNAME --access-key $LT_ACCESS_KEY \
  --agent --headless --timeout 120

# SC-004: Verify card highlights visible without logging in
kane-cli run \
  "Navigate to the credit cards section of americanexpress.com and verify card highlights are visible without logging in" \
  --url https://www.americanexpress.com/ \
  --username $LT_USERNAME --access-key $LT_ACCESS_KEY \
  --agent --headless --timeout 120
```

Parse the result of any Kane run:

```bash
kane-cli run "..." --agent --headless 2>/dev/null | tail -1 | jq \
  '{status, one_liner, duration, final_state}'
```

Run all Kane objectives in parallel:

```bash
RESULTS_DIR=$(mktemp -d)

for obj in $(jq -r '.[] | @base64' kane/objectives.json); do
  data=$(echo "$obj" | base64 --decode)
  id=$(echo "$data" | jq -r '.scenario_id')
  objective=$(echo "$data" | jq -r '.objective')
  url=$(echo "$data" | jq -r '.url')
  timeout=$(echo "$data" | jq -r '.timeout')

  kane-cli run "$objective" \
    --url "$url" \
    --username $LT_USERNAME --access-key $LT_ACCESS_KEY \
    --agent --headless --timeout "$timeout" \
    > "$RESULTS_DIR/$id.ndjson" 2>&1 &
done

wait

echo "| Scenario | Status | Duration | Summary |"
echo "|----------|--------|----------|---------|"
for f in "$RESULTS_DIR"/*.ndjson; do
  id=$(basename "$f" .ndjson)
  result=$(tail -1 "$f")
  status=$(echo "$result" | jq -r '.status')
  duration=$(echo "$result" | jq -r '.duration')
  summary=$(echo "$result" | jq -r '.one_liner')
  echo "| $id | $status | ${duration}s | $summary |"
done
```

---

## GitHub Actions

The pipeline triggers automatically when any file in `requirements/` is changed.

### Required secrets — Settings → Secrets and variables → Actions

| Secret | Description |
|---|---|
| `LT_USERNAME` | LambdaTest username |
| `LT_ACCESS_KEY` | LambdaTest access key |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude Code |

### Trigger the pipeline by pushing a requirement change

```bash
# Edit requirements
vim requirements/search.txt

git add requirements/search.txt
git commit -m "feat: update credit card browsing requirements"
git push
```

This triggers the full 5-stage pipeline automatically.

### Manual trigger — run all tests

Go to **Actions → Agentic SDLC Pipeline → Run workflow**, check **"Run all tests"**, and click **Run workflow**. This includes all active scenarios, not just changed ones.

---

## Adapting to Other CI/CD Tools

Every stage is one portable command. Copy it verbatim into any CI tool's job definition.

### GitLab CI

```yaml
stages:
  - analyze
  - scenarios
  - tests
  - execute
  - report

analyze-requirements:
  stage: analyze
  image: node:20
  script:
    - npm install -g @testmuai/kane-cli @anthropic-ai/claude-code
    - claude -p "Execute stage: ANALYZE_REQUIREMENTS from PIPELINE.md"
  artifacts:
    paths: [requirements/analyzed_requirements.json]

manage-scenarios:
  stage: scenarios
  image: node:20
  script:
    - npm install -g @anthropic-ai/claude-code
    - claude -p "Execute stage: MANAGE_SCENARIOS from PIPELINE.md"
  artifacts:
    paths: [scenarios/scenarios.json]
```

### Jenkins (Declarative Pipeline)

```groovy
pipeline {
    agent any
    environment {
        LT_USERNAME     = credentials('lt-username')
        LT_ACCESS_KEY   = credentials('lt-access-key')
        ANTHROPIC_API_KEY = credentials('anthropic-api-key')
    }
    stages {
        stage('Analyze Requirements') {
            steps { sh 'claude -p "Execute stage: ANALYZE_REQUIREMENTS from PIPELINE.md"' }
        }
        stage('Manage Scenarios') {
            steps { sh 'claude -p "Execute stage: MANAGE_SCENARIOS from PIPELINE.md"' }
        }
        stage('Generate Tests') {
            steps { sh 'claude -p "Execute stage: GENERATE_TESTS from PIPELINE.md"' }
        }
        stage('Execute on HyperExecute') {
            steps {
                sh 'curl -O https://downloads.lambdatest.com/hyperexecute/linux/hyperexecute && chmod +x hyperexecute'
                sh './hyperexecute --user $LT_USERNAME --key $LT_ACCESS_KEY --config hyperexecute.yaml'
            }
        }
        stage('Traceability + Recommendation') {
            steps {
                sh 'claude -p "Execute stage: TRACEABILITY_REPORT from PIPELINE.md"'
                sh 'claude -p "Execute stage: RELEASE_RECOMMENDATION from PIPELINE.md"'
            }
        }
    }
    post {
        always { archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true }
    }
}
```

### Bitbucket Pipelines

```yaml
pipelines:
  default:
    - step:
        name: Analyze Requirements
        image: node:20
        script:
          - npm install -g @testmuai/kane-cli @anthropic-ai/claude-code
          - claude -p "Execute stage: ANALYZE_REQUIREMENTS from PIPELINE.md"
        artifacts: [requirements/analyzed_requirements.json]
    - step:
        name: Manage Scenarios
        image: node:20
        script:
          - npm install -g @anthropic-ai/claude-code
          - claude -p "Execute stage: MANAGE_SCENARIOS from PIPELINE.md"
```

---

## Traceability Matrix

After a pipeline run, `reports/traceability_matrix.md` maps every requirement to its result:

| Requirement | Acceptance Criterion | Scenario | Test Case | Kane AI | Selenium | Status |
|---|---|---|---|---|---|---|
| Browse credit cards | View list of cards | SC-001 | TC-001 | Passed | Passed | ✅ |
| Filter cards | Apply category filters | SC-002 | TC-002 | Passed | Passed | ✅ |
| View card details | Click card → detail page | SC-003 | TC-003 | Failed | Flaky | ⚠️ |
| No-login highlights | Highlights without login | SC-004 | TC-004 | Passed | Passed | ✅ |
| Relevant results | Results match filter | SC-005 | TC-005 | Passed | Passed | ✅ |

`reports/release_recommendation.md` gives the final **GREEN / YELLOW / RED** verdict with reasoning.

---

## Scenario and Test Mapping

| Scenario | Test Function | Acceptance Criterion |
|---|---|---|
| SC-001 | `test_sc_001_navigate_to_credit_cards_and_view_list` | Navigate to credit cards and view list |
| SC-002 | `test_sc_002_filter_cards_by_category` | Use filters to refine results |
| SC-003 | `test_sc_003_click_card_view_details` | Click card to view details (benefits, fees, rewards) |
| SC-004 | `test_sc_004_card_highlights_visible_without_login` | View highlights without logging in |
| SC-005 | `test_sc_005_relevant_results_for_selected_filter` | Relevant results for selected filter |

---

## Adding New Requirements

1. Edit `requirements/search.txt` — add new user stories or acceptance criteria
2. Push the change — GitHub Actions triggers automatically, **or** run locally:

```bash
claude -p "Execute stage: ANALYZE_REQUIREMENTS from PIPELINE.md"
claude -p "Execute stage: MANAGE_SCENARIOS from PIPELINE.md"
claude -p "Execute stage: GENERATE_TESTS from PIPELINE.md"
```

New scenarios and Selenium test cases are created automatically. No manual scripting needed.
