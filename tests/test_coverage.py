"""Tests for reports/coverage.py — F4 (get_coverage) and F5 (get_pr_coverage)."""

import pytest
import requests_mock as requests_mock_lib

from sonar_report.client import SonarClient
from sonar_report.reports.coverage import get_coverage, get_pr_coverage

BASE_URL = "https://sonar.example.com"
TOKEN = "test-token"
PROJECT = "my-project"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

@pytest.fixture
def client():
    return SonarClient(BASE_URL, TOKEN)


def _measure(metric: str, value, *, period: bool = False) -> dict:
    """Build a SonarQube measure dict.  Use *period=True* to simulate the
    legacy ``period`` format used by older SonarQube instances."""
    if period:
        return {"metric": metric, "period": {"index": 1, "value": str(value)}}
    return {"metric": metric, "value": str(value)}


def _component(measures: list[dict]) -> dict:
    return {"component": {"key": PROJECT, "measures": measures}}


def _mock_measures(m, measures):
    m.get(f"{BASE_URL}/api/measures/component", json=_component(measures))


# --------------------------------------------------------------------------- #
# get_coverage (F4)
# --------------------------------------------------------------------------- #

class TestGetCoverage:
    def test_report_type(self, client):
        with requests_mock_lib.Mocker() as m:
            _mock_measures(m, [])
            result = get_coverage(client, PROJECT, "main")
        assert result["report_type"] == "coverage"

    def test_project_key_and_branch_present(self, client):
        with requests_mock_lib.Mocker() as m:
            _mock_measures(m, [])
            result = get_coverage(client, PROJECT, "develop")
        assert result["project_key"] == PROJECT
        assert result["branch"] == "develop"

    def test_generated_at_present(self, client):
        with requests_mock_lib.Mocker() as m:
            _mock_measures(m, [])
            result = get_coverage(client, PROJECT, "main")
        assert "generated_at" in result

    def test_float_metric_parsed_correctly(self, client):
        with requests_mock_lib.Mocker() as m:
            _mock_measures(m, [_measure("coverage", "85.5")])
            result = get_coverage(client, PROJECT, "main")
        assert result["metrics"]["coverage"] == 85.5

    def test_whole_number_metric_returned_as_int(self, client):
        """88.0 should come back as 88, not 88.0."""
        with requests_mock_lib.Mocker() as m:
            _mock_measures(m, [_measure("line_coverage", "88.0")])
            result = get_coverage(client, PROJECT, "main")
        assert result["metrics"]["line_coverage"] == 88
        assert isinstance(result["metrics"]["line_coverage"], int)

    def test_new_code_section_strips_new_prefix(self, client):
        with requests_mock_lib.Mocker() as m:
            _mock_measures(m, [
                _measure("new_coverage", "80.5"),
                _measure("new_lines_to_cover", "200"),
            ])
            result = get_coverage(client, PROJECT, "main")
        new = result["new_code"]
        assert "coverage" in new          # new_coverage → coverage
        assert "lines_to_cover" in new    # new_lines_to_cover → lines_to_cover
        assert new["coverage"] == 80.5

    def test_missing_metrics_yield_none(self, client):
        with requests_mock_lib.Mocker() as m:
            _mock_measures(m, [])
            result = get_coverage(client, PROJECT, "main")
        assert result["metrics"]["coverage"] is None
        assert result["new_code"]["coverage"] is None

    def test_legacy_period_format_parsed(self, client):
        """Older SQ versions deliver new-code metric values inside 'period'."""
        with requests_mock_lib.Mocker() as m:
            _mock_measures(m, [_measure("new_coverage", "77.3", period=True)])
            result = get_coverage(client, PROJECT, "main")
        assert result["new_code"]["coverage"] == 77.3

    def test_branch_param_sent_to_api(self, client):
        with requests_mock_lib.Mocker() as m:
            _mock_measures(m, [])
            get_coverage(client, PROJECT, "release")
        assert m.last_request.qs["branch"] == ["release"]


# --------------------------------------------------------------------------- #
# get_pr_coverage (F5)
# --------------------------------------------------------------------------- #

class TestGetPrCoverage:
    def test_report_type(self, client):
        with requests_mock_lib.Mocker() as m:
            _mock_measures(m, [])
            result = get_pr_coverage(client, PROJECT, "42")
        assert result["report_type"] == "pr_coverage"

    def test_pull_request_id_present(self, client):
        with requests_mock_lib.Mocker() as m:
            _mock_measures(m, [])
            result = get_pr_coverage(client, PROJECT, "42")
        assert result["pull_request"] == "42"

    def test_no_metrics_key(self, client):
        """PR reports have no 'metrics' section — only 'new_code'."""
        with requests_mock_lib.Mocker() as m:
            _mock_measures(m, [])
            result = get_pr_coverage(client, PROJECT, "42")
        assert "metrics" not in result
        assert "new_code" in result

    def test_new_code_values_populated(self, client):
        with requests_mock_lib.Mocker() as m:
            _mock_measures(m, [
                _measure("new_coverage", "79.1"),
                _measure("new_uncovered_lines", "15"),
            ])
            result = get_pr_coverage(client, PROJECT, "42")
        assert result["new_code"]["coverage"] == 79.1
        assert result["new_code"]["uncovered_lines"] == 15

    def test_pullrequest_param_sent_to_api(self, client):
        with requests_mock_lib.Mocker() as m:
            _mock_measures(m, [])
            get_pr_coverage(client, PROJECT, "99")
        assert m.last_request.qs["pullrequest"] == ["99"]
