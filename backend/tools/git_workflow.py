#!/usr/bin/env python3
"""
Nate Git Workflow Automation

Automates Git workflows for code changes:
- Auto-create feature branches
- Commit changes with descriptive messages
- Run tests before committing
- Generate PRs for Angela's review
"""

import subprocess
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List


def _run_git_command(cmd: List[str], cwd: str) -> Dict[str, Any]:
    """Run a git command and return results."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "exit_code": result.returncode
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "exit_code": -1
        }


def create_feature_branch(
    repo_path: str,
    feature_name: str,
    base_branch: str = "main"
) -> Dict[str, Any]:
    """
    Create a new feature branch for Nate's work.

    Args:
        repo_path: Path to git repository
        feature_name: Short description of feature
        base_branch: Branch to base from (default: main)

    Returns:
        Dict with branch creation results
    """
    # Generate branch name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    branch_name = f"nate/{feature_name.lower().replace(' ', '-')}_{timestamp}"

    # Check current status
    status = _run_git_command(["git", "status", "--porcelain"], repo_path)
    if not status["success"]:
        return {
            "status": "error",
            "message": "Failed to check git status",
            "details": status
        }

    has_changes = bool(status["stdout"])

    # Create and checkout branch
    result = _run_git_command(
        ["git", "checkout", "-b", branch_name],
        repo_path
    )

    if not result["success"]:
        return {
            "status": "error",
            "message": f"Failed to create branch: {result.get('stderr', 'Unknown error')}",
            "branch_name": branch_name
        }

    return {
        "status": "success",
        "branch_name": branch_name,
        "base_branch": base_branch,
        "has_uncommitted_changes": has_changes,
        "message": f"Created and switched to branch: {branch_name}"
    }


def commit_changes(
    repo_path: str,
    message: str,
    files: Optional[List[str]] = None,
    run_tests: bool = True
) -> Dict[str, Any]:
    """
    Commit changes with automatic testing.

    Args:
        repo_path: Path to git repository
        message: Commit message
        files: Specific files to commit (None = all changes)
        run_tests: Whether to run tests before committing

    Returns:
        Dict with commit results
    """
    repo = Path(repo_path)

    # Check for changes
    status = _run_git_command(["git", "status", "--porcelain"], repo_path)
    if not status["success"]:
        return {
            "status": "error",
            "message": "Failed to check git status"
        }

    if not status["stdout"]:
        return {
            "status": "info",
            "message": "No changes to commit"
        }

    # Run tests if requested
    test_results = None
    if run_tests:
        # Check if pytest is available
        pytest_check = _run_git_command(["which", "pytest"], repo_path)
        if pytest_check["success"]:
            # Run tests
            test_result = _run_git_command(
                ["pytest", "-x", "--tb=short"],
                repo_path
            )
            test_results = {
                "passed": test_result["success"],
                "output": test_result["stdout"],
                "exit_code": test_result["exit_code"]
            }

            if not test_result["success"]:
                return {
                    "status": "error",
                    "message": "Tests failed, aborting commit",
                    "test_results": test_results
                }

    # Stage files
    if files:
        for file in files:
            add_result = _run_git_command(["git", "add", file], repo_path)
            if not add_result["success"]:
                return {
                    "status": "error",
                    "message": f"Failed to stage file: {file}",
                    "details": add_result
                }
    else:
        # Stage all changes
        add_result = _run_git_command(["git", "add", "-A"], repo_path)
        if not add_result["success"]:
            return {
                "status": "error",
                "message": "Failed to stage changes",
                "details": add_result
            }

    # Commit
    commit_result = _run_git_command(
        ["git", "commit", "-m", message],
        repo_path
    )

    if not commit_result["success"]:
        return {
            "status": "error",
            "message": "Failed to commit changes",
            "details": commit_result
        }

    # Get commit hash
    hash_result = _run_git_command(["git", "rev-parse", "HEAD"], repo_path)
    commit_hash = hash_result["stdout"] if hash_result["success"] else "unknown"

    return {
        "status": "success",
        "message": "Changes committed successfully",
        "commit_hash": commit_hash[:8],
        "commit_message": message,
        "test_results": test_results
    }


def create_pull_request(
    repo_path: str,
    title: str,
    body: str,
    base_branch: str = "main"
) -> Dict[str, Any]:
    """
    Create a pull request using GitHub CLI.

    Args:
        repo_path: Path to git repository
        title: PR title
        body: PR description
        base_branch: Target branch for PR

    Returns:
        Dict with PR creation results
    """
    # Check if gh CLI is available
    gh_check = _run_git_command(["which", "gh"], repo_path)
    if not gh_check["success"]:
        return {
            "status": "error",
            "message": "GitHub CLI (gh) not installed. Cannot create PR automatically.",
            "instructions": "Push branch and create PR manually, or install gh CLI"
        }

    # Get current branch
    branch_result = _run_git_command(
        ["git", "branch", "--show-current"],
        repo_path
    )
    if not branch_result["success"]:
        return {
            "status": "error",
            "message": "Failed to get current branch"
        }

    current_branch = branch_result["stdout"]

    # Push branch
    push_result = _run_git_command(
        ["git", "push", "-u", "origin", current_branch],
        repo_path
    )
    if not push_result["success"]:
        return {
            "status": "error",
            "message": "Failed to push branch",
            "branch": current_branch,
            "details": push_result
        }

    # Create PR using gh CLI
    pr_result = _run_git_command(
        ["gh", "pr", "create",
         "--title", title,
         "--body", body,
         "--base", base_branch],
        repo_path
    )

    if not pr_result["success"]:
        return {
            "status": "error",
            "message": "Failed to create PR",
            "details": pr_result
        }

    # Extract PR URL from output
    pr_url = pr_result["stdout"].strip()

    return {
        "status": "success",
        "message": "Pull request created successfully",
        "pr_url": pr_url,
        "branch": current_branch,
        "base_branch": base_branch
    }


def automated_workflow(
    repo_path: str,
    feature_name: str,
    commit_message: str,
    pr_title: str,
    pr_body: str,
    files: Optional[List[str]] = None,
    run_tests: bool = True,
    base_branch: str = "main"
) -> Dict[str, Any]:
    """
    Execute complete automated Git workflow:
    1. Create feature branch
    2. Commit changes
    3. Run tests
    4. Create PR

    Args:
        repo_path: Path to git repository
        feature_name: Feature name for branch
        commit_message: Commit message
        pr_title: Pull request title
        pr_body: Pull request description
        files: Specific files to commit
        run_tests: Whether to run tests
        base_branch: Base branch for PR

    Returns:
        Dict with workflow results
    """
    results = {
        "steps": [],
        "status": "in_progress"
    }

    # Step 1: Create feature branch
    branch_result = create_feature_branch(repo_path, feature_name, base_branch)
    results["steps"].append({
        "step": "create_branch",
        "result": branch_result
    })

    if branch_result["status"] != "success":
        results["status"] = "error"
        results["failed_at"] = "create_branch"
        return results

    # Step 2: Commit changes
    commit_result = commit_changes(repo_path, commit_message, files, run_tests)
    results["steps"].append({
        "step": "commit_changes",
        "result": commit_result
    })

    if commit_result["status"] != "success":
        results["status"] = "error"
        results["failed_at"] = "commit_changes"
        return results

    # Step 3: Create PR
    pr_result = create_pull_request(repo_path, pr_title, pr_body, base_branch)
    results["steps"].append({
        "step": "create_pr",
        "result": pr_result
    })

    if pr_result["status"] != "success":
        results["status"] = "warning"
        results["message"] = "Changes committed but PR creation failed"
        return results

    results["status"] = "success"
    results["message"] = "Complete workflow executed successfully"
    results["pr_url"] = pr_result.get("pr_url")
    results["branch"] = branch_result["branch_name"]

    return results


def get_current_status(repo_path: str) -> Dict[str, Any]:
    """Get current Git status and branch info."""
    # Current branch
    branch_result = _run_git_command(
        ["git", "branch", "--show-current"],
        repo_path
    )

    # Status
    status_result = _run_git_command(
        ["git", "status", "--porcelain"],
        repo_path
    )

    # Recent commits
    log_result = _run_git_command(
        ["git", "log", "--oneline", "-5"],
        repo_path
    )

    return {
        "current_branch": branch_result.get("stdout", "unknown"),
        "has_changes": bool(status_result.get("stdout")),
        "changes": status_result.get("stdout", "").split("\n") if status_result.get("stdout") else [],
        "recent_commits": log_result.get("stdout", "").split("\n") if log_result.get("stdout") else []
    }
