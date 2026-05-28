"""
Main orchestrator for the Repo Upgrade + Autonomous Validation Skill.

Modes:
  --mode analyze  : Read-only repo analysis, prints RepoProfile (no branch created)
  --mode inject   : Clone + inject files + push (no GHA trigger)
  --mode run      : Full pipeline — inject + trigger + watch + collect + RCA (default)

Usage:
    python ci/repo_upgrade_orchestrator.py \
        --repo-url https://github.com/lambdapro/contosotraders-cloudtesting-copilot-HEx \
        --requirement "The application top banner should display a Memorial Day Sale banner." \
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
if str(_CI_DIR) not in sys.path:
    sys.path.insert(0, str(_CI_DIR))

import repo_analyzer
import testmd_generator
import test_analyzer
import test_injector
import hyperexecute_builder
import gha_injector
import rca_parser

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    config_path = Path(__file__).parent.parent / "agentic-stlc.config.yaml"
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
    # Check if there's anything to commit
    status = _run_capture(["git", "status", "--porcelain"], cwd=workspace_path)
    if not status:
        print("[orchestrator] nothing to commit — files already up to date")
        return _run_capture(["git", "rev-parse", "HEAD"], cwd=workspace_path)
    _run(["git", "commit", "-m", message], cwd=workspace_path)
    _run(["git", "push", "origin", branch, "--force-with-lease"], cwd=workspace_path)
    sha = _run_capture(["git", "rev-parse", "HEAD"], cwd=workspace_path)
    print(f"[orchestrator] pushed {branch} -> {sha[:8]}")
    return sha


def trigger_workflow(owner: str, name: str, branch: str, workflow: str = "agentic-validate.yml") -> str:
    """Trigger GHA workflow and return the run ID."""
    _run(["gh", "workflow", "run", workflow, "--repo", f"{owner}/{name}", "--ref", branch])
    time.sleep(5)  # brief wait for GHA to register the run
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
# Stage: build Kane objective
# ---------------------------------------------------------------------------

def build_kane_objective(requirement: str, repo_profile: repo_analyzer.RepoProfile) -> str:
    """Generate a precise Kane AI objective for the requirement."""
    app_url = repo_profile.target_url or repo_profile.app_url_local
    req_lower = requirement.lower()

    if any(w in req_lower for w in ("banner", "promotional", "sale", "offer", "announcement")):
        # Extract expected text
        m = re.search(r'"([^"]+)"', requirement)
        expected = m.group(1) if m else "Memorial Day Sale"
        return (
            f"Go to {app_url} — wait for the full page to load — "
            f"look near the top of the page (above or inside the header navigation) for a "
            f"promotional banner, announcement bar, or highlighted strip — "
            f'verify the banner text contains "{expected}" — '
            f"stop immediately once confirmed. "
            f"If no banner is visible after the page loads, report failure and describe "
            f"what the header area currently shows."
        )

    # Generic objective
    return (
        f"Go to {app_url} — wait for the page to load — "
        f"verify the following requirement: {requirement} — "
        f"stop immediately once confirmed."
    )


# ---------------------------------------------------------------------------
# Mode: analyze
# ---------------------------------------------------------------------------

def cmd_analyze(args: argparse.Namespace) -> None:
    profile = repo_analyzer.analyze(args.repo_url, getattr(args, "target_url", ""))
    print("\n=== RepoProfile ===")
    for k, v in profile.__dict__.items():
        print(f"  {k}: {v!r}")

    if args.requirement:
        slug = _slug(args.requirement)
        print(f"\n=== Plan ===")
        print(f"  TestMD to generate: kane/testmd/{slug}_test.md")
        print(f"  Test file to update: {profile.test_dir}/verifymsg.spec.ts")
        print(f"  HE config to create: {profile.app_working_dir}/hyperexecute-agentic.yaml")
        print(f"  GHA workflow: .github/workflows/agentic-validate.yml")
        print(f"  Kane mode: {profile.kane_mode}")
        print(f"  Browsers in matrix: Chrome, Firefox, Edge")


# ---------------------------------------------------------------------------
# Mode: inject
# ---------------------------------------------------------------------------

def cmd_inject(args: argparse.Namespace, config: dict) -> str:
    """Clone repo, inject files, push feature branch. Returns workspace path."""
    workspace_dir = config.get("repo_upgrade", {}).get("workspace_dir", "workspace")
    workspace_path = clone_repo(args.repo_url, workspace_dir)

    branch = args.branch or f"feature/agentic-{_slug(args.requirement)}"
    create_branch(workspace_path, branch)
    print(f"[orchestrator] on branch {branch}")

    profile = repo_analyzer.analyze(args.repo_url, getattr(args, "target_url", ""))

    # Load config for TMS IDs
    kane_cfg = config.get("kaneai", {})
    project_id = os.getenv("KANE_PROJECT_ID", "") or kane_cfg.get("project_id", "")
    folder_id = os.getenv("KANE_FOLDER_ID", "") or kane_cfg.get("folder_id", "")

    # Stage C: Generate TestMD files
    print("\n[Stage C] Generating TestMD files...")
    testmd_files = testmd_generator.generate(
        requirements=[args.requirement],
        repo_profile=profile,
        workspace_dir=workspace_path,
        project_id=project_id,
        folder_id=folder_id,
    )

    # Stage D: Analyze existing tests
    print("\n[Stage D] Analyzing existing tests...")
    tp = test_analyzer.extract_patterns(
        owner=profile.owner,
        name=profile.name,
        test_files=profile.existing_test_files,
        requirement=args.requirement,
    )

    # Stage E: Inject / update Playwright tests
    print("\n[Stage E] Injecting Playwright tests...")
    modified_tests = test_injector.inject(
        requirement=args.requirement,
        repo_profile=profile,
        test_profile=tp,
        workspace_dir=workspace_path,
    )

    # Build list of test files for HE config (relative to app_working_dir)
    he_test_files: list[str] = []
    app_wd = profile.app_working_dir
    for f in modified_tests:
        rel = f[len(app_wd) + 1:] if app_wd and f.startswith(app_wd + "/") else f
        he_test_files.append(rel)
    if not he_test_files:
        he_test_files = [f"{profile.test_dir}/verifymsg.spec.ts"]

    # Stage F: Build HyperExecute YAML
    print("\n[Stage F] Building HyperExecute YAML...")
    he_config_name = config.get("repo_upgrade", {}).get("he_config_name", "hyperexecute-agentic.yaml")
    hyperexecute_builder.build(
        repo_profile=profile,
        test_files=he_test_files,
        workspace_dir=workspace_path,
        output_name=he_config_name,
    )

    # Stage G: Inject GHA workflow
    print("\n[Stage G] Injecting GitHub Actions workflow...")
    kane_objective = build_kane_objective(args.requirement, profile)
    gha_injector.inject(
        repo_profile=profile,
        kane_objective=kane_objective,
        workspace_dir=workspace_path,
        he_config_name=he_config_name,
    )

    # Copy rca_parser.py into target repo so GHA job 3 can find it
    rca_dest = Path(workspace_path) / "ci" / "rca_parser.py"
    rca_dest.parent.mkdir(parents=True, exist_ok=True)
    src = Path(__file__).parent / "rca_parser.py"
    rca_dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"[orchestrator] copied rca_parser.py -> {rca_dest.relative_to(workspace_path)}")

    # Commit and push
    print("\n[Stage H] Committing and pushing...")
    req_slug = _slug(args.requirement)
    commit_and_push(
        workspace_path, branch,
        f"feat: inject agentic validation for [{req_slug}]\n\n"
        f"Requirement: {args.requirement}\n\n"
        f"Generated by Agentic STLC repo-upgrade skill.\n"
        f"Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>",
    )

    print(f"\n[orchestrator] inject complete -> branch: {branch}")
    print(f"  TestMD: {testmd_files}")
    print(f"  Tests:  {modified_tests}")
    return workspace_path


# ---------------------------------------------------------------------------
# Mode: run (full pipeline)
# ---------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace, config: dict) -> None:
    workspace_path = cmd_inject(args, config)

    profile = repo_analyzer.analyze(args.repo_url)
    branch = args.branch or f"feature/agentic-{_slug(args.requirement)}"
    workflow = config.get("repo_upgrade", {}).get("gha_workflow_name", "agentic-validate.yml")

    # Stage I: Trigger GHA
    print(f"\n[Stage I] Triggering workflow {workflow} on {profile.owner}/{profile.name}@{branch}...")
    run_id = trigger_workflow(profile.owner, profile.name, branch, workflow)
    if not run_id:
        print("[orchestrator] warning: could not retrieve run ID — check GHA manually")
        print(f"  https://github.com/{profile.owner}/{profile.name}/actions")
        return

    monitor_url = f"https://github.com/{profile.owner}/{profile.name}/actions/runs/{run_id}"
    print(f"\n  Monitor: {monitor_url}")

    # Stage J: Watch until completion
    print("\n[Stage J] Watching pipeline (Kane -> HyperExecute -> RCA)...")
    exit_code = watch_run(profile.owner, profile.name, run_id)

    # Stage K: Download artifacts
    artifacts_dir = str(Path(workspace_path) / "reports" / "gha_artifacts")
    print(f"\n[Stage K] Downloading artifacts to {artifacts_dir}...")
    download_artifacts(profile.owner, profile.name, run_id, artifacts_dir)

    # Parse RCA result if downloaded
    rca_json = Path(artifacts_dir) / "rca-summary" / "rca_result.json"
    if rca_json.exists():
        result = json.loads(rca_json.read_text())
        print("\n=== RCA Results ===")
        print(f"  Verdict: {result.get('overall_verdict', 'UNKNOWN')}")
        print(f"  Kane: {result.get('kane_pass_count', 0)} passed / {result.get('kane_fail_count', 0)} failed")
        print(f"  Playwright: {result.get('playwright_pass_count', 0)} passed / {result.get('playwright_fail_count', 0)} failed")
        if result.get("fix_suggestions"):
            print("\n  Fix Suggestions:")
            for fix in result["fix_suggestions"]:
                print(f"    [{fix.get('type')}] {fix.get('component')}: {fix.get('suggestion', '')[:200]}")
    else:
        # Run locally if artifact wasn't downloaded
        kane_dir = Path(artifacts_dir) / "kane-results"
        playwright_dir = Path(artifacts_dir) / "playwright-reports"
        output = Path(workspace_path) / "reports" / "rca_result.json"
        if kane_dir.exists() or playwright_dir.exists():
            rca_parser.run(
                str(kane_dir), str(playwright_dir), str(output), ""
            )

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
    parser.add_argument("--target-url", default="", help="Deployed app URL for Kane cloud mode")
    parser.add_argument("--mode", choices=["analyze", "inject", "run"], default="run",
                        help="Pipeline mode: analyze (read-only), inject (no trigger), run (full)")
    args = parser.parse_args()

    config = _load_config()

    if args.mode == "analyze":
        cmd_analyze(args)
    elif args.mode == "inject":
        cmd_inject(args, config)
    else:
        if not args.requirement:
            parser.error("--requirement is required for inject and run modes")
        cmd_run(args, config)


if __name__ == "__main__":
    main()
