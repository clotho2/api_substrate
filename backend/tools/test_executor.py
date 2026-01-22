#!/usr/bin/env python3
"""
Agent Test Executor - Level 3 Priority 2

Safe test execution with coverage reporting for agent self-maintenance.
This allows the agent to verify code changes don't break anything.

Features:
- Run pytest tests with coverage
- Filter tests by path, pattern, or marker
- Generate coverage reports (terminal and HTML)
- Parse test results for pass/fail/skip counts
- Return detailed failure information
- Timeout protection
"""

import subprocess
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime


# Configuration
_current_file = Path(__file__).resolve()
SUBSTRATE_ROOT = _current_file.parent.parent.parent
TESTS_DIR = SUBSTRATE_ROOT / "tests"
COVERAGE_DIR = SUBSTRATE_ROOT / "htmlcov"
MAX_TEST_DURATION = 300  # 5 minutes max for safety


class TestExecutor:
    """Safe test executor with coverage reporting."""

    def __init__(self):
        """Initialize test executor."""
        pass

    def run_tests(
        self,
        test_path: Optional[str] = None,
        pattern: Optional[str] = None,
        markers: Optional[str] = None,
        coverage: bool = True,
        verbose: bool = True,
        stop_on_first_failure: bool = False,
        timeout: int = MAX_TEST_DURATION
    ) -> Dict[str, Any]:
        """
        Run tests with optional coverage.

        Args:
            test_path: Specific test file or directory (relative to tests/)
            pattern: Test name pattern (pytest -k)
            markers: Test markers to filter by (pytest -m)
            coverage: Generate coverage report
            verbose: Verbose output
            stop_on_first_failure: Stop after first failure (-x)
            timeout: Maximum execution time in seconds

        Returns:
            Dict with status, test results, and coverage info
        """
        try:
            # Build pytest command
            cmd = self._build_pytest_command(
                test_path=test_path,
                pattern=pattern,
                markers=markers,
                coverage=coverage,
                verbose=verbose,
                stop_on_first_failure=stop_on_first_failure
            )

            # Run tests
            start_time = datetime.now()
            result = subprocess.run(
                cmd,
                cwd=str(SUBSTRATE_ROOT),
                capture_output=True,
                text=True,
                timeout=timeout
            )
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            # Parse results
            test_results = self._parse_test_output(result.stdout, result.stderr)
            test_results["duration"] = duration
            test_results["exit_code"] = result.returncode

            # Get coverage if enabled
            coverage_info = None
            if coverage and result.returncode in [0, 1]:  # Tests ran (passed or failed)
                coverage_info = self._get_coverage_summary()

            return {
                "status": "success",
                "tests": test_results,
                "coverage": coverage_info,
                "command": " ".join(cmd)
            }

        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "message": f"Tests timed out after {timeout} seconds",
                "timeout": timeout
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to run tests: {str(e)}"
            }

    def _build_pytest_command(
        self,
        test_path: Optional[str],
        pattern: Optional[str],
        markers: Optional[str],
        coverage: bool,
        verbose: bool,
        stop_on_first_failure: bool
    ) -> List[str]:
        """Build pytest command with options."""
        cmd = ["pytest"]

        # Add test path
        if test_path:
            # Make path relative to SUBSTRATE_ROOT
            if test_path.startswith('/'):
                test_target = test_path
            else:
                test_target = str(TESTS_DIR / test_path)
            cmd.append(test_target)
        else:
            # Run all tests
            cmd.append(str(TESTS_DIR))

        # Add options
        if verbose:
            cmd.append("-v")

        if stop_on_first_failure:
            cmd.append("-x")

        if pattern:
            cmd.extend(["-k", pattern])

        if markers:
            cmd.extend(["-m", markers])

        # Coverage options (only if pytest-cov is available)
        if coverage:
            try:
                # Check if pytest-cov is available
                import pytest_cov
                cmd.extend([
                    "--cov=backend",
                    "--cov-report=term-missing",
                    "--cov-report=html",
                    f"--cov-report=json:{SUBSTRATE_ROOT}/.coverage.json"
                ])
            except ImportError:
                # pytest-cov not installed, skip coverage
                pass

        # Output options
        cmd.extend([
            "--tb=short",  # Shorter traceback format
            "-ra",  # Show summary of all test outcomes
        ])

        return cmd

    def _parse_test_output(self, stdout: str, stderr: str) -> Dict[str, Any]:
        """Parse pytest output to extract test results."""
        results = {
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "errors": 0,
            "total": 0,
            "failures": [],
            "output": stdout
        }

        # Parse summary line like: "5 passed, 2 failed, 1 skipped in 2.34s"
        # Look for each component separately
        passed_match = re.search(r'(\d+)\s+passed', stdout)
        if passed_match:
            results["passed"] = int(passed_match.group(1))

        failed_match = re.search(r'(\d+)\s+failed', stdout)
        if failed_match:
            results["failed"] = int(failed_match.group(1))

        skipped_match = re.search(r'(\d+)\s+skipped', stdout)
        if skipped_match:
            results["skipped"] = int(skipped_match.group(1))

        error_match = re.search(r'(\d+)\s+error', stdout)
        if error_match:
            results["errors"] = int(error_match.group(1))

        results["total"] = results["passed"] + results["failed"] + results["skipped"] + results["errors"]

        # Extract failure details
        if results["failed"] > 0 or results["errors"] > 0:
            results["failures"] = self._extract_failures(stdout)

        return results

    def _extract_failures(self, output: str) -> List[Dict[str, str]]:
        """Extract failure information from pytest output."""
        failures = []

        # Look for FAILED lines
        failed_pattern = r'FAILED (.*?) - (.*?)(?:\n|$)'
        for match in re.finditer(failed_pattern, output):
            test_name = match.group(1)
            error_summary = match.group(2)[:200]  # Limit length

            failures.append({
                "test": test_name,
                "error": error_summary
            })

        return failures

    def _get_coverage_summary(self) -> Optional[Dict[str, Any]]:
        """Get coverage summary from generated report."""
        try:
            coverage_json = SUBSTRATE_ROOT / ".coverage.json"
            if not coverage_json.exists():
                return None

            with open(coverage_json, 'r') as f:
                coverage_data = json.load(f)

            # Extract summary
            totals = coverage_data.get("totals", {})

            summary = {
                "percent_covered": totals.get("percent_covered", 0),
                "num_statements": totals.get("num_statements", 0),
                "covered_lines": totals.get("covered_lines", 0),
                "missing_lines": totals.get("missing_lines", 0),
                "html_report": str(COVERAGE_DIR / "index.html") if COVERAGE_DIR.exists() else None
            }

            # Get per-file coverage for important files
            files = coverage_data.get("files", {})
            file_coverage = []
            for filepath, file_data in list(files.items())[:10]:  # Top 10 files
                file_summary = file_data.get("summary", {})
                file_coverage.append({
                    "file": filepath,
                    "percent_covered": file_summary.get("percent_covered", 0),
                    "missing_lines": file_summary.get("missing_lines", 0)
                })

            summary["file_coverage"] = file_coverage

            return summary

        except Exception as e:
            return {
                "error": f"Failed to parse coverage: {str(e)}"
            }

    def list_tests(self, test_path: Optional[str] = None) -> Dict[str, Any]:
        """List available tests without running them."""
        try:
            cmd = ["pytest", "--collect-only", "-q"]

            if test_path:
                if test_path.startswith('/'):
                    test_target = test_path
                else:
                    test_target = str(TESTS_DIR / test_path)
                cmd.append(test_target)
            else:
                cmd.append(str(TESTS_DIR))

            result = subprocess.run(
                cmd,
                cwd=str(SUBSTRATE_ROOT),
                capture_output=True,
                text=True,
                timeout=30
            )

            # Parse collected tests
            tests = []
            for line in result.stdout.splitlines():
                if "::" in line and not line.startswith(" "):
                    tests.append(line.strip())

            return {
                "status": "success",
                "tests": tests,
                "total": len(tests)
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to list tests: {str(e)}"
            }

    def get_test_history(self, limit: int = 10) -> Dict[str, Any]:
        """Get recent test execution history (if pytest-cache available)."""
        try:
            cache_dir = SUBSTRATE_ROOT / ".pytest_cache"
            if not cache_dir.exists():
                return {
                    "status": "success",
                    "history": [],
                    "message": "No test history available (pytest cache not found)"
                }

            # Try to read lastfailed
            lastfailed_file = cache_dir / "v" / "cache" / "lastfailed"
            if lastfailed_file.exists():
                with open(lastfailed_file, 'r') as f:
                    lastfailed = json.load(f)

                return {
                    "status": "success",
                    "last_failed": list(lastfailed.keys())[:limit]
                }

            return {
                "status": "success",
                "history": [],
                "message": "No recent failures"
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to get test history: {str(e)}"
            }
