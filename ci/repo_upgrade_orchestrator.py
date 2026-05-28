"""
Main orchestrator for the Repo Upgrade + Autonomous Validation Skill.

All Agentic STLC pipeline files are injected into .agentic/ inside the target
repo so the project's own source tree is never modified.

The .agentic/ folder contains:
  ci/                           <- All 25 pipeline Python scripts
  requirements.txt              <- Python deps (mcp, httpx, playwright, pytest...)
  pytest.ini
  hyperexecute.yaml             <- Adapted for target app URL
  agentic-stlc.config.yaml     <- Adapted for target repo
  requirements/search.txt      <- The business requirement (input to pipeline)
  scenarios/scenarios.json     <- Empty; populated by pipeline Stage 2
  tests/playwright/conftest.py <- LambdaTest Playwright fixture

GitHub Actions then runs .agentic/ci/analyze_requirements.py (Stage 1 / Kane AI)
and .agentic/ci/agent.py (Stages 2-7 / Orchestrator) — all processing in CI.

Modes:
  --mode analyze  : Read-only repo analysis, prints RepoProfile (no branch created)
  --mode inject   : Clone + inject pipeline into .agentic/ + push (no GHA trigger)
  --mode run      : Full pipeline — inject + trigger + watch + collect (default)

Usage:
    python ci/repo_upgrade_orchestrator.py \\
        --repo-url https://github.com/lambdapro/contosotraders-cloudtesting-copilot-HEx \\
        --requirement "The application top banner should display a Memorial Day Sale banner." \\
        --target-url https://contoso-traders.lambdatest.io \\
        --branch feature/agentic-memorial-day-banner
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Ensure ci/ is on sys.path
_CI_DIR = Path(__file__).parent
_REPO_ROOT = _CI_DIR.parent
if str(_CI_DIR) not in sys.path:
    sys.path.insert(0, str(_CI_DIR))

import repo_analyzer
import gha_injector

# ---------------------------------------------------------------------------
# Pipeline CI scripts copied from orchestration repo -> .agentic/ci/
# Skill-specific scripts (repo_upgrade_*, gha_injector, etc.) are excluded.
# ---------------------------------------------------------------------------

_PIPELINE_CI_FILES = [
    "ci/analyze_requirements.py",
    "ci/agent.py",
    "ci/manage_scenarios.py",
    "ci/generate_tests_from_scenarios.py",
    "ci/select_tests.py",
    "ci/build_traceability.py",
    "ci/release_recommendation.py",
    "ci/write_github_summary.py",
    "ci/analyze_hyperexecute_failures.py",
    "ci/fetch_api_details.py",
    "ci/run_pytest_node.py",
    "ci/stage_utils.py",
    "ci/pipeline_metrics.py",
    "ci/notify_agent.py",
    "ci/fetch_rca.py",
    "ci/quality_gates.py",
    "ci/scenario_confidence.py",
    "ci/coverage_analysis.py",
    "ci/impact_analysis.py",
    "ci/failure_intelligence.py",
    "ci/self_healing.py",
    "ci/normalize_artifacts.py",
    "ci/collect_kane_exports.py",
    "ci/rca_enrichment.py",
    "ci/validate_report.py",
    "ci/rca_parser.py",
]

# Files copied from repo root -> .agentic/
_PIPELINE_ROOT_FILES = [
    ("requirements.txt",                 "requirements.txt"),
    ("pytest.ini",                       "pytest.ini"),
    ("tests/playwright/conftest.py",     "tests/playwright/conftest.py"),
]

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    config_path = _REPO_ROOT / "agentic-stlc.config.yaml"
    if not config_path.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(config_path.read_text()) or {}
    except Exception:
        return {}


def _slug(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:50].strip("-")


# ---------------------------------------------------------------------------
# Git + GitHub helpers
# ---------------------------------------------------------------------------

def _clean_env() -> dict:
    """Return os.environ without GH_TOKEN so gh uses keyring auth."""
    env = {**os.environ}
    env.pop("GH_TOKEN", None)
    return env


def _run(cmd: list[str], cwd: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    print(f"[orchestrator] $ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=False, env=_clean_env())


def _run_capture(cmd: list[str], cwd: str | None = None) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=_clean_env())
    return result.stdout.strip()


def clone_repo(repo_url: str, workspace_dir: str) -> str:
    """Clone the target repo into workspace_dir/{repo_name}. Returns the clone path."""
    owner_name = re.search(r"github\.com/([^/]+/[^/]+?)(?:\.git)?$", repo_url.rstrip("/"))
    if not owner_name:
        raise ValueError(f"Cannot parse repo name from {repo_url}")
    repo_name = owner_name.group(1).split("/")[1]
    clone_path = Path(workspace_dir) / repo_name
    if clone_path.exists():
        print(f"[orchestrator] workspace already exists at {clone_path}, pulling latest")
        _run(["git", "fetch", "origin"], cwd=str(clone_path))
    else:
        clone_path.parent.mkdir(parents=True, exist_ok=True)
        # core.longpaths=true avoids Windows 260-char path failures on repos
        # that have long log or artifact filenames checked in.
        _run(["git", "clone", "-c", "core.longpaths=true", repo_url, str(clone_path)])
    return str(clone_path)


def create_branch(workspace_path: str, branch: str) -> None:
    _run(["git", "checkout", "-B", branch], cwd=workspace_path)


def commit_and_push(workspace_path: str, branch: str, message: str) -> str:
    _run(["git", "add", "."], cwd=workspace_path)
    status = _run_capture(["git", "status", "--porcelain"], cwd=workspace_path)
    if not status:
        print("[orchestrator] nothing to commit — files already up to date")
        return _run_capture(["git", "rev-parse", "HEAD"], cwd=workspace_path)
    _run(["git", "commit", "-m", message], cwd=workspace_path)
    _run(["git", "push", "origin", branch, "--force-with-lease"], cwd=workspace_path)
    sha = _run_capture(["git", "rev-parse", "HEAD"], cwd=workspace_path)
    print(f"[orchestrator] pushed {branch} -> {sha[:8]}")
    return sha


def trigger_workflow(owner: str, name: str, branch: str, workflow: str = "agentic-stlc.yml") -> str:
    """Trigger GHA workflow and return the run ID."""
    _run(["gh", "workflow", "run", workflow, "--repo", f"{owner}/{name}", "--ref", branch])
    time.sleep(5)
    result = subprocess.run(
        ["gh", "run", "list", "--repo", f"{owner}/{name}", "--branch", branch,
         "--workflow", workflow, "--limit", "1", "--json", "databaseId"],
        capture_output=True, text=True,
    )
    try:
        runs = json.loads(result.stdout)
        if runs:
            run_id = str(runs[0]["databaseId"])
            print(f"[orchestrator] triggered run #{run_id}")
            return run_id
    except Exception:
        pass
    return ""


def watch_run(owner: str, name: str, run_id: str) -> int:
    """Watch a GHA run until completion. Returns exit code."""
    monitor_url = f"https://github.com/{owner}/{name}/actions/runs/{run_id}"
    print(f"[orchestrator] monitoring: {monitor_url}")
    result = subprocess.run(
        ["gh", "run", "watch", run_id, "--repo", f"{owner}/{name}", "--exit-status"],
        check=False,
    )
    return result.returncode


def download_artifacts(owner: str, name: str, run_id: str, dest_dir: str) -> list[str]:
    """Download all artifacts from a run."""
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["gh", "run", "download", run_id, "--repo", f"{owner}/{name}", "--dir", dest_dir],
        check=False,
    )
    downloaded = [str(p) for p in Path(dest_dir).iterdir() if p.is_dir()]
    print(f"[orchestrator] downloaded {len(downloaded)} artifacts to {dest_dir}")
    return downloaded


# ---------------------------------------------------------------------------
# Stage C: Bootstrap .agentic/ in the target repo
# ---------------------------------------------------------------------------

def bootstrap_agentic_dir(
    workspace_path: str,
    profile: repo_analyzer.RepoProfile,
    requirement: str,
    config: dict,
) -> Path:
    """
    Create .agentic/ in the target repo with the full Agentic STLC pipeline.
    Returns the path to the .agentic/ directory.

    The target repo's own source tree is never touched. All pipeline files,
    Python deps, config, and the requirement input live under .agentic/.
    GitHub Actions runs everything from that subdirectory.
    """
    dest_agentic = Path(workspace_path) / ".agentic"
    dest_agentic.mkdir(parents=True, exist_ok=True)
    print(f"[Stage C] Bootstrapping {dest_agentic} ...")

    # 1. Copy core CI pipeline scripts
    _copy_ci_scripts(dest_agentic)

    # 2. Copy support files (requirements.txt, pytest.ini, conftest.py)
    _copy_support_files(dest_agentic)

    # 3. Write adapted hyperexecute.yaml
    _write_hyperexecute_yaml(dest_agentic, profile)

    # 4. Write adapted agentic-stlc.config.yaml
    _write_agentic_config(dest_agentic, profile, config)

    # 5. Write requirement into .agentic/requirements/search.txt
    _write_requirements_file(dest_agentic, requirement, profile)

    # 6. Initialize empty state files (pipeline populates them in CI)
    _init_state_files(dest_agentic)

    total = len(_PIPELINE_CI_FILES) + len(_PIPELINE_ROOT_FILES) + 5
    print(f"[Stage C] done — {total} files written to .agentic/")
    return dest_agentic


def _copy_ci_scripts(dest_agentic: Path) -> None:
    ci_dest = dest_agentic / "ci"
    ci_dest.mkdir(parents=True, exist_ok=True)
    for rel_path in _PIPELINE_CI_FILES:
        src = _REPO_ROOT / rel_path
        if not src.exists():
            print(f"  [warn] source not found: {rel_path}")
            continue
        # rel_path is "ci/foo.py" — dest_name is "foo.py"
        dest = ci_dest / src.name
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"  copied {len(_PIPELINE_CI_FILES)} CI scripts -> .agentic/ci/")


def _copy_support_files(dest_agentic: Path) -> None:
    for src_rel, dest_rel in _PIPELINE_ROOT_FILES:
        src = _REPO_ROOT / src_rel
        if not src.exists():
            print(f"  [warn] source not found: {src_rel}")
            continue
        dest = dest_agentic / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"  copied {len(_PIPELINE_ROOT_FILES)} support files")


def _write_hyperexecute_yaml(dest_agentic: Path, profile: repo_analyzer.RepoProfile) -> None:
    src = _REPO_ROOT / "hyperexecute.yaml"
    if not src.exists():
        print("  [warn] hyperexecute.yaml not found in orchestration repo")
        return

    content = src.read_text(encoding="utf-8")

    # Point TARGET_URL at the target app
    target_url = profile.target_url or profile.app_url_local or ""
    if target_url:
        content = re.sub(r'TARGET_URL:.*', f'TARGET_URL: "{target_url}"', content)

    # Update job labels for the target repo
    repo_label = profile.name.lower()
    content = re.sub(
        r'jobLabel:.*?(?=\n\S|\Z)',
        f'jobLabel:\n  - {repo_label}\n  - agentic-stlc\n  - playwright',
        content,
        flags=re.DOTALL,
    )

    (dest_agentic / "hyperexecute.yaml").write_text(content, encoding="utf-8")
    print("  wrote .agentic/hyperexecute.yaml")


def _write_agentic_config(
    dest_agentic: Path,
    profile: repo_analyzer.RepoProfile,
    config: dict,
) -> None:
    target_url = profile.target_url or profile.app_url_local or ""
    kane_cfg = config.get("kaneai", {})
    project_id = kane_cfg.get("project_id", "")
    folder_id = kane_cfg.get("folder_id", "")

    content = f"""\
# Agentic STLC Platform — Project Configuration
# Auto-generated by Agentic STLC repo-upgrade skill
# Repository: {profile.repo_url}

version: "1.0"

project:
  name: "{profile.name.lower()}-stlc"
  description: "Agentic STLC pipeline for {profile.name}"
  repository: "{profile.repo_url}"
  branch: "{profile.default_branch}"

requirements:
  format: "acceptance_criteria"
  paths:
    - "requirements/search.txt"
  output_path: "requirements/analyzed_requirements.json"
  encoding: "utf-8"

scenarios:
  path: "scenarios/scenarios.json"
  id_prefix: "SC"
  id_start: 1

framework:
  type: "playwright"
  language: "python"
  test_dir: "tests/playwright"
  test_file: "tests/playwright/test_powerapps.py"

target:
  url: "{target_url}"
  environment: "staging"

execution:
  provider: "hyperexecute"
  mode: "incremental"
  concurrency: 5
  timeout_seconds: 90
  retries: 1
  browsers:
    - chrome
  platforms:
    - windows10

hyperexecute:
  config_file: "hyperexecute.yaml"
  cli_path: "./hyperexecute"
  project: "{profile.name.lower()}-stlc"
  region: "us"

kaneai:
  enabled: true
  parallel_workers: 10
  timeout_seconds: 120
  project_id: "{project_id}"
  folder_id: "{folder_id}"
  use_testmd: true
  testmd_output_dir: "kane/testmd"

reporting:
  output_dir: "reports"
  formats:
    - json
    - markdown
  github_summary: true
  artifacts:
    - "reports/"
    - "scenarios/scenarios.json"
    - "tests/playwright/test_powerapps.py"

quality_gates:
  min_coverage_pct: 50
  min_pass_rate: 75
  max_flaky: 5
  require_critical_coverage: true
  max_high_risk_uncovered: 999
  min_he_pct: 0
  confidence:
    enabled: true
    gate_severity: "WARNING"
"""
    (dest_agentic / "agentic-stlc.config.yaml").write_text(content, encoding="utf-8")
    print("  wrote .agentic/agentic-stlc.config.yaml")


def _write_requirements_file(dest_agentic: Path, requirement: str, profile: repo_analyzer.RepoProfile) -> None:
    req_dir = dest_agentic / "requirements"
    req_dir.mkdir(parents=True, exist_ok=True)
    content = f"""\
Title: {profile.name} — Agentic STLC Requirements
# Auto-generated by Agentic STLC repo-upgrade skill

As a user
I want to use {profile.name}
So that I can complete my goals

Acceptance Criteria:
{requirement}
"""
    (req_dir / "search.txt").write_text(content, encoding="utf-8")
    print("  wrote .agentic/requirements/search.txt")


def _init_state_files(dest_agentic: Path) -> None:
    """Initialize empty state files — pipeline populates them during CI runs."""
    init = {
        "scenarios/scenarios.json": "[]",
        "requirements/analyzed_requirements.json": "[]",
        "kane/objectives.json": "{}",
    }
    for rel, content in init.items():
        p = dest_agentic / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text(content, encoding="utf-8")
    (dest_agentic / "reports").mkdir(parents=True, exist_ok=True)
    print("  initialized state files (scenarios.json, analyzed_requirements.json, reports/)")


# ---------------------------------------------------------------------------
# Mode: analyze
# ---------------------------------------------------------------------------

def cmd_analyze(args: argparse.Namespace) -> None:
    profile = repo_analyzer.analyze(args.repo_url, getattr(args, "target_url", ""))
    print("\n=== RepoProfile ===")
    for k, v in profile.__dict__.items():
        print(f"  {k}: {v!r}")

    if args.requirement:
        print(f"\n=== .agentic/ structure to be injected ===")
        print(f"  .agentic/ci/                    <- {len(_PIPELINE_CI_FILES)} pipeline scripts")
        print(f"  .agentic/requirements/search.txt <- requirement input")
        print(f"  .agentic/hyperexecute.yaml       <- adapted for {profile.name}")
        print(f"  .agentic/agentic-stlc.config.yaml")
        print(f"  .agentic/requirements.txt + pytest.ini + tests/playwright/conftest.py")
        print(f"\n=== GHA Pipeline Flow ===")
        print(f"  Job 1 (analyze)     <- KaneAI verifies requirement against {profile.target_url or profile.app_url_local}")
        print(f"  Job 2 (orchestrate) <- Scenario sync, test gen, HyperExecute, traceability")
        print(f"  Job 3 (summary)     <- Verdict: GREEN / YELLOW / RED")


# ---------------------------------------------------------------------------
# Mode: inject
# ---------------------------------------------------------------------------

def cmd_inject(args: argparse.Namespace, config: dict) -> str:
    """Clone repo, bootstrap .agentic/, inject workflow, push. Returns workspace path."""
    workspace_dir = config.get("repo_upgrade", {}).get("workspace_dir", "workspace")
    workspace_path = clone_repo(args.repo_url, workspace_dir)

    branch = args.branch or f"feature/agentic-{_slug(args.requirement)}"
    create_branch(workspace_path, branch)
    print(f"[orchestrator] on branch {branch}")

    profile = repo_analyzer.analyze(args.repo_url, getattr(args, "target_url", ""))

    # Stage C: Bootstrap .agentic/ with complete pipeline
    bootstrap_agentic_dir(workspace_path, profile, args.requirement, config)

    # Stage D: Inject GHA workflow
    print("\n[Stage D] Injecting GitHub Actions workflow...")
    kane_cfg = config.get("kaneai", {})
    project_id = os.getenv("KANE_PROJECT_ID", "") or kane_cfg.get("project_id", "")
    folder_id = os.getenv("KANE_FOLDER_ID", "") or kane_cfg.get("folder_id", "")
    gha_injector.inject(
        repo_profile=profile,
        workspace_dir=workspace_path,
        kane_project_id=project_id,
        kane_folder_id=folder_id,
    )

    # Stage E: Commit and push
    print("\n[Stage E] Committing and pushing...")
    req_slug = _slug(args.requirement)
    commit_and_push(
        workspace_path, branch,
        f"feat: inject agentic STLC pipeline for [{req_slug}]\n\n"
        f"Requirement: {args.requirement}\n\n"
        f"Injects the complete Agentic STLC pipeline into .agentic/ — the\n"
        f"target repo's source tree is untouched. GitHub Actions runs all\n"
        f"stages (KaneAI verification, HyperExecute, traceability, verdict)\n"
        f"from .agentic/ci/ autonomously.\n\n"
        f"Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>",
    )

    print(f"\n[orchestrator] inject complete")
    print(f"  Branch:   {branch}")
    print(f"  Pipeline: .agentic/ ({len(_PIPELINE_CI_FILES)} CI scripts + workflow)")
    print(f"  Trigger:  push to {branch} will start agentic-stlc.yml automatically")
    return workspace_path


# ---------------------------------------------------------------------------
# Mode: run (full pipeline)
# ---------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace, config: dict) -> None:
    workspace_path = cmd_inject(args, config)

    profile = repo_analyzer.analyze(args.repo_url)
    branch = args.branch or f"feature/agentic-{_slug(args.requirement)}"
    workflow = "agentic-stlc.yml"

    # Stage F: Trigger GHA
    print(f"\n[Stage F] Triggering {workflow} on {profile.owner}/{profile.name}@{branch}...")
    run_id = trigger_workflow(profile.owner, profile.name, branch, workflow)
    if not run_id:
        print("[orchestrator] warning: could not retrieve run ID — check GHA manually")
        print(f"  https://github.com/{profile.owner}/{profile.name}/actions")
        return

    monitor_url = f"https://github.com/{profile.owner}/{profile.name}/actions/runs/{run_id}"
    print(f"\n  Monitor: {monitor_url}")
    print(f"\n  Pipeline stages:")
    print(f"    Job 1 (analyze)     -> Kane AI verifies acceptance criteria")
    print(f"    Job 2 (orchestrate) -> Scenario sync, test gen, HyperExecute, traceability")
    print(f"    Job 3 (summary)     -> GREEN / YELLOW / RED verdict")

    # Stage G: Watch until completion
    print("\n[Stage G] Watching pipeline...")
    exit_code = watch_run(profile.owner, profile.name, run_id)

    # Stage H: Download artifacts
    artifacts_dir = str(Path(workspace_path) / "reports" / "gha_artifacts")
    print(f"\n[Stage H] Downloading artifacts to {artifacts_dir}...")
    download_artifacts(profile.owner, profile.name, run_id, artifacts_dir)

    # Display verdict from pipeline-reports artifact
    rec_json = Path(artifacts_dir) / "pipeline-reports" / "release_recommendation.json"
    if rec_json.exists():
        result = json.loads(rec_json.read_text())
        print("\n=== Release Verdict ===")
        print(f"  Verdict:   {result.get('verdict', 'UNKNOWN')}")
        print(f"  Pass rate: {result.get('pass_rate', 0)}%")
        if result.get("failing_requirements"):
            print("\n  Failing requirements:")
            for req in result["failing_requirements"][:5]:
                print(f"    - {req}")

    matrix_md = Path(artifacts_dir) / "pipeline-reports" / "traceability_matrix.md"
    if matrix_md.exists():
        lines = matrix_md.read_text().splitlines()[:15]
        print("\n=== Traceability Matrix (excerpt) ===")
        for line in lines:
            print(f"  {line}")

    print(f"\n[orchestrator] pipeline complete — exit_code={exit_code}")
    print(f"  GHA run: {monitor_url}")
    sys.exit(exit_code)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Repo Upgrade + Autonomous Validation Orchestrator")
    parser.add_argument("--repo-url", required=True, help="Target GitHub repo URL")
    parser.add_argument("--requirement", default="", help="Business requirement to inject and validate")
    parser.add_argument("--branch", default="", help="Feature branch name (auto-generated if omitted)")
    parser.add_argument("--target-url", default="", help="Deployed app URL for Kane to test against")
    parser.add_argument("--mode", choices=["analyze", "inject", "run"], default="run",
                        help="Pipeline mode: analyze (read-only), inject (no trigger), run (full)")
    args = parser.parse_args()

    config = _load_config()

    if args.mode == "analyze":
        cmd_analyze(args)
    elif args.mode == "inject":
        if not args.requirement:
            parser.error("--requirement is required for inject and run modes")
        cmd_inject(args, config)
    else:
        if not args.requirement:
            parser.error("--requirement is required for inject and run modes")
        cmd_run(args, config)


if __name__ == "__main__":
    main()
