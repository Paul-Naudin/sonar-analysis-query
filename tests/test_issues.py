"""Tests for sonar_report/reports/issues.py"""

from sonar_report.reports.issues import (
    _build_summary,
    get_all_issues,
    get_new_issues,
    get_pr_issues,
)

BASE    = "https://sonar.example.com"
PROJECT = "ch.corren.wcs"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_issue(key="i1", severity="MAJOR", type_="CODE_SMELL", status="OPEN") -> dict:
    return {
        "key": key, "rule": "java:S1234", "severity": severity,
        "type": type_, "component": f"{PROJECT}:src/Foo.java",
        "line": 42, "message": "Some issue", "effort": "5min",
        "status": status, "assignee": None, "tags": [],
        "creationDate": "2026-02-23T10:00:00+0000",
    }


def _page(items: list) -> dict:
    return {"issues": items, "paging": {"pageIndex": 1, "pageSize": 500, "total": len(items)}}


def _client():
    from sonar_report.client import SonarClient
    return SonarClient(BASE, "tok")


# ---------------------------------------------------------------------------
# _build_summary
# ---------------------------------------------------------------------------

def test_summary_counts_by_severity():
    issues = [
        {"severity": "MAJOR",    "type": "BUG"},
        {"severity": "CRITICAL", "type": "VULNERABILITY"},
        {"severity": "MAJOR",    "type": "CODE_SMELL"},
    ]
    s = _build_summary(issues)
    assert s["total"] == 3
    assert s["by_severity"]["MAJOR"]    == 2
    assert s["by_severity"]["CRITICAL"] == 1
    assert s["by_severity"]["BLOCKER"]  == 0


def test_summary_counts_by_type():
    issues = [
        {"severity": "MAJOR", "type": "BUG"},
        {"severity": "MAJOR", "type": "BUG"},
        {"severity": "INFO",  "type": "CODE_SMELL"},
    ]
    s = _build_summary(issues)
    assert s["by_type"]["BUG"]           == 2
    assert s["by_type"]["CODE_SMELL"]    == 1
    assert s["by_type"]["VULNERABILITY"] == 0


def test_summary_empty():
    s = _build_summary([])
    assert s["total"] == 0
    assert all(v == 0 for v in s["by_severity"].values())
    assert all(v == 0 for v in s["by_type"].values())


# ---------------------------------------------------------------------------
# get_pr_issues  (F1)
# ---------------------------------------------------------------------------

def test_pr_issues_report_structure(requests_mock):
    items = [_mock_issue("i1"), _mock_issue("i2", severity="CRITICAL", type_="BUG")]
    requests_mock.get(f"{BASE}/api/issues/search", json=_page(items))

    report = get_pr_issues(_client(), PROJECT, "42")

    assert report["report_type"]      == "pr_issues"
    assert report["project_key"]      == PROJECT
    assert report["pull_request"]     == "42"
    assert report["summary"]["total"] == 2
    assert len(report["issues"])      == 2
    assert "generated_at" in report


def test_pr_issues_api_params(requests_mock):
    adapter = requests_mock.get(f"{BASE}/api/issues/search", json=_page([]))
    get_pr_issues(_client(), PROJECT, "99")

    qs = adapter.last_request.qs
    assert qs["componentkeys"] == [PROJECT]
    assert qs["pullrequest"]   == ["99"]
    assert qs["resolved"]      == ["false"]


def test_pr_issues_empty(requests_mock):
    requests_mock.get(f"{BASE}/api/issues/search", json=_page([]))
    report = get_pr_issues(_client(), PROJECT, "1")
    assert report["summary"]["total"] == 0
    assert report["issues"] == []


# ---------------------------------------------------------------------------
# get_new_issues  (F2)
# ---------------------------------------------------------------------------

def test_new_issues_leak_period_param(requests_mock):
    adapter = requests_mock.get(f"{BASE}/api/issues/search", json=_page([]))
    get_new_issues(_client(), PROJECT, "main")

    qs = adapter.last_request.qs
    assert qs["innewcodeperiod"] == ["true"]
    assert qs["branch"]          == ["main"]


def test_new_issues_report_type(requests_mock):
    requests_mock.get(f"{BASE}/api/issues/search", json=_page([_mock_issue()]))
    report = get_new_issues(_client(), PROJECT, "main")
    assert report["report_type"] == "new_issues_main"
    assert report["branch"]      == "main"


# ---------------------------------------------------------------------------
# get_all_issues  (F3)
# ---------------------------------------------------------------------------

def test_all_issues_excludes_accepted_statuses(requests_mock):
    adapter = requests_mock.get(f"{BASE}/api/issues/search", json=_page([]))
    get_all_issues(_client(), PROJECT, "main")

    # requests_mock lowercases query string values
    statuses = adapter.last_request.qs["statuses"][0].upper()
    assert "OPEN"      in statuses
    assert "CONFIRMED" in statuses
    assert "ACCEPTED"  not in statuses
    assert "WONTFIX"   not in statuses


def test_all_issues_report_type(requests_mock):
    requests_mock.get(f"{BASE}/api/issues/search", json=_page([_mock_issue()]))
    report = get_all_issues(_client(), PROJECT, "main")
    assert report["report_type"] == "all_issues_main"


# ---------------------------------------------------------------------------
# Field extraction - only expected keys are kept
# ---------------------------------------------------------------------------

def test_unexpected_fields_are_dropped(requests_mock):
    raw = _mock_issue("i1")
    raw["unexpected_field"] = "should_be_dropped"
    requests_mock.get(f"{BASE}/api/issues/search", json=_page([raw]))

    report = get_all_issues(_client(), PROJECT, "main")
    issue = report["issues"][0]
    assert "unexpected_field" not in issue
    assert "key"      in issue
    assert "severity" in issue
    assert "line"     in issue

