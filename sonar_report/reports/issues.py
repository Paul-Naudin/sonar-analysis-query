"""Issue report generators.

Functions:
    get_pr_issues(client, project_key, pr_id)        -> dict  [F1]
    get_new_issues(client, project_key, branch)      -> dict  [F2]
    get_all_issues(client, project_key, branch)      -> dict  [F3]
"""

from datetime import datetime, timezone
from typing import Any

from sonar_report.client import SonarClient

# Fields to extract from each raw SonarQube issue
_ISSUE_FIELDS = (
    "key", "rule", "severity", "type", "component", "line",
    "message", "effort", "status", "assignee", "tags", "creationDate",
)

_SEVERITIES = ("BLOCKER", "CRITICAL", "MAJOR", "MINOR", "INFO")
_TYPES      = ("BUG", "VULNERABILITY", "CODE_SMELL")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_pr_issues(client: SonarClient, project_key: str, pr_id: str) -> dict:
    """F1 - Return all issues introduced by a pull request."""
    params = {
        "componentKeys": project_key,
        "pullRequest":   pr_id,
        "resolved":      "false",
    }
    issues = client.get_paginated("/api/issues/search", params, results_key="issues")
    return _build_report(
        report_type="pr_issues",
        project_key=project_key,
        issues=issues,
        extra={"pull_request": pr_id},
    )


def get_new_issues(client: SonarClient, project_key: str, branch: str) -> dict:
    """F2 - Return issues in the new-code period (leak period) on a branch."""
    params = {
        "componentKeys":   project_key,
        "branch":          branch,
        "inNewCodePeriod": "true",
        "resolved":        "false",
    }
    issues = client.get_paginated("/api/issues/search", params, results_key="issues")
    return _build_report(
        report_type=f"new_issues_{branch}",
        project_key=project_key,
        issues=issues,
        extra={"branch": branch},
    )


def get_all_issues(client: SonarClient, project_key: str, branch: str) -> dict:
    """F3 - Return all open, non-accepted issues on a branch."""
    params = {
        "componentKeys": project_key,
        "branch":        branch,
        "resolved":      "false",
        # ACCEPTED / WONTFIX excluded - only genuinely open issues
        "statuses":      "OPEN,CONFIRMED,REOPENED",
    }
    issues = client.get_paginated("/api/issues/search", params, results_key="issues")
    return _build_report(
        report_type=f"all_issues_{branch}",
        project_key=project_key,
        issues=issues,
        extra={"branch": branch},
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_issue(raw: dict[str, Any]) -> dict[str, Any]:
    """Keep only the fields we care about from a raw SonarQube issue."""
    return {field: raw.get(field) for field in _ISSUE_FIELDS}


def _build_summary(issues: list[dict]) -> dict:
    by_severity = {s: 0 for s in _SEVERITIES}
    by_type     = {t: 0 for t in _TYPES}

    for issue in issues:
        sev = issue.get("severity")
        typ = issue.get("type")
        if sev in by_severity:
            by_severity[sev] += 1
        if typ in by_type:
            by_type[typ] += 1

    return {
        "total":       len(issues),
        "by_severity": by_severity,
        "by_type":     by_type,
    }


def _build_report(
    report_type: str,
    project_key: str,
    issues: list[dict],
    extra: dict,
) -> dict:
    cleaned = [_extract_issue(i) for i in issues]
    return {
        "report_type":  report_type,
        "project_key":  project_key,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **extra,
        "summary": _build_summary(cleaned),
        "issues":  cleaned,
    }


