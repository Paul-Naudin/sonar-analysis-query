"""Tests for sonar_report/reports/duplications.py — F7 (get_duplications)."""

import pytest
import requests_mock as requests_mock_lib

from sonar_report.client import SonarClient
from sonar_report.reports.duplications import get_duplications

BASE_URL = "https://sonar.example.com"
TOKEN = "test-token"
PROJECT = "my-project"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    return SonarClient(BASE_URL, TOKEN)


def _proj_measures(measures: list[dict]) -> dict:
    return {"component": {"key": PROJECT, "measures": measures}}


def _measure(metric: str, value) -> dict:
    return {"metric": metric, "value": str(value)}


def _tree_page(components: list[dict]) -> dict:
    return {
        "components": components,
        "paging": {"pageIndex": 1, "pageSize": 500, "total": len(components)},
    }


def _component(path: str, dup_lines: int, dup_blocks: int, density: float) -> dict:
    return {
        "key": f"{PROJECT}:src/{path}",
        "path": f"src/{path}",
        "qualifier": "FIL",
        "measures": [
            _measure("duplicated_lines", dup_lines),
            _measure("duplicated_blocks", dup_blocks),
            _measure("duplicated_lines_density", density),
        ],
    }


def _duplications_response(blocks: list[list[dict]], files: dict) -> dict:
    return {
        "duplications": [{"blocks": b} for b in blocks],
        "files": files,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetDuplications:
    def test_report_type(self, client):
        with requests_mock_lib.Mocker() as m:
            m.get(f"{BASE_URL}/api/measures/component", json=_proj_measures([]))
            m.get(f"{BASE_URL}/api/measures/component_tree", json=_tree_page([]))
            result = get_duplications(client, PROJECT, branch="main")
        assert result["report_type"] == "duplications"

    def test_branch_present(self, client):
        with requests_mock_lib.Mocker() as m:
            m.get(f"{BASE_URL}/api/measures/component", json=_proj_measures([]))
            m.get(f"{BASE_URL}/api/measures/component_tree", json=_tree_page([]))
            result = get_duplications(client, PROJECT, branch="develop")
        assert result["branch"] == "develop"

    def test_pr_present(self, client):
        with requests_mock_lib.Mocker() as m:
            m.get(f"{BASE_URL}/api/measures/component", json=_proj_measures([]))
            m.get(f"{BASE_URL}/api/measures/component_tree", json=_tree_page([]))
            result = get_duplications(client, PROJECT, pr_id="42")
        assert result["pull_request"] == "42"
        assert "branch" not in result

    def test_generated_at_present(self, client):
        with requests_mock_lib.Mocker() as m:
            m.get(f"{BASE_URL}/api/measures/component", json=_proj_measures([]))
            m.get(f"{BASE_URL}/api/measures/component_tree", json=_tree_page([]))
            result = get_duplications(client, PROJECT, branch="main")
        assert "generated_at" in result

    def test_summary_from_project_measures(self, client):
        measures = [
            _measure("duplicated_lines", 100),
            _measure("duplicated_blocks", 5),
            _measure("duplicated_files", 3),
            _measure("duplicated_lines_density", 4.5),
            _measure("ncloc", 2000),
        ]
        with requests_mock_lib.Mocker() as m:
            m.get(f"{BASE_URL}/api/measures/component", json=_proj_measures(measures))
            m.get(f"{BASE_URL}/api/measures/component_tree", json=_tree_page([]))
            result = get_duplications(client, PROJECT, branch="main")
        s = result["summary"]
        assert s["duplicated_lines"] == 100
        assert s["duplicated_blocks"] == 5
        assert s["duplicated_files"] == 3
        assert s["duplicated_lines_density"] == 4.5
        assert s["ncloc"] == 2000

    def test_empty_project_returns_empty_files(self, client):
        with requests_mock_lib.Mocker() as m:
            m.get(f"{BASE_URL}/api/measures/component", json=_proj_measures([]))
            m.get(f"{BASE_URL}/api/measures/component_tree", json=_tree_page([]))
            result = get_duplications(client, PROJECT, branch="main")
        assert result["files"] == []
        assert result["summary"]["files_in_report"] == 0

    def test_files_with_zero_dup_lines_excluded(self, client):
        comps = [
            _component("Foo.java", 10, 1, 5.0),
            _component("Bar.java", 0, 0, 0.0),
        ]
        dup_resp = _duplications_response(
            [[{"from": 10, "size": 5, "_ref": "1"}, {"from": 10, "size": 5, "_ref": "2"}]],
            {"1": {"name": "src/Foo.java"}, "2": {"name": "src/Other.java"}},
        )
        with requests_mock_lib.Mocker() as m:
            m.get(f"{BASE_URL}/api/measures/component", json=_proj_measures([]))
            m.get(f"{BASE_URL}/api/measures/component_tree", json=_tree_page(comps))
            m.get(f"{BASE_URL}/api/duplications/show", json=dup_resp)
            result = get_duplications(client, PROJECT, branch="main")
        assert len(result["files"]) == 1
        assert result["files"][0]["path"] == "src/Foo.java"

    def test_duplication_blocks_parsed(self, client):
        comp = _component("Foo.java", 40, 2, 44.9)
        dup_resp = _duplications_response(
            [[
                {"from": 47, "size": 40, "_ref": "1"},
                {"from": 47, "size": 40, "_ref": "2"},
            ]],
            {
                "1": {"name": "src/Foo.java"},
                "2": {"name": "src/Bar.java"},
            },
        )
        with requests_mock_lib.Mocker() as m:
            m.get(f"{BASE_URL}/api/measures/component", json=_proj_measures([]))
            m.get(f"{BASE_URL}/api/measures/component_tree", json=_tree_page([comp]))
            m.get(f"{BASE_URL}/api/duplications/show", json=dup_resp)
            result = get_duplications(client, PROJECT, branch="main")

        details = result["files"][0]["duplication_details"]
        assert len(details) == 1
        assert details[0]["from_line"] == 47
        assert details[0]["size"] == 40
        assert len(details[0]["duplicated_in"]) == 1
        assert details[0]["duplicated_in"][0]["path"] == "src/Bar.java"

    def test_multiple_duplication_groups(self, client):
        comp = _component("Foo.java", 40, 2, 44.9)
        dup_resp = _duplications_response(
            [
                [{"from": 10, "size": 20, "_ref": "1"}, {"from": 10, "size": 20, "_ref": "2"}],
                [{"from": 50, "size": 15, "_ref": "1"}, {"from": 30, "size": 15, "_ref": "3"}],
            ],
            {
                "1": {"name": "src/Foo.java"},
                "2": {"name": "src/Bar.java"},
                "3": {"name": "src/Baz.java"},
            },
        )
        with requests_mock_lib.Mocker() as m:
            m.get(f"{BASE_URL}/api/measures/component", json=_proj_measures([]))
            m.get(f"{BASE_URL}/api/measures/component_tree", json=_tree_page([comp]))
            m.get(f"{BASE_URL}/api/duplications/show", json=dup_resp)
            result = get_duplications(client, PROJECT, branch="main")

        details = result["files"][0]["duplication_details"]
        assert len(details) == 2
        assert details[0]["from_line"] == 10
        assert details[1]["from_line"] == 50
        assert details[1]["duplicated_in"][0]["path"] == "src/Baz.java"

    def test_requires_branch_or_pr(self, client):
        with pytest.raises(ValueError, match="branch or pr_id"):
            get_duplications(client, PROJECT)

    def test_file_measures_in_output(self, client):
        comp = _component("Foo.java", 25, 3, 12.5)
        dup_resp = _duplications_response(
            [[{"from": 1, "size": 10, "_ref": "1"}, {"from": 1, "size": 10, "_ref": "2"}]],
            {"1": {"name": "src/Foo.java"}, "2": {"name": "src/Other.java"}},
        )
        with requests_mock_lib.Mocker() as m:
            m.get(f"{BASE_URL}/api/measures/component", json=_proj_measures([]))
            m.get(f"{BASE_URL}/api/measures/component_tree", json=_tree_page([comp]))
            m.get(f"{BASE_URL}/api/duplications/show", json=dup_resp)
            result = get_duplications(client, PROJECT, branch="main")

        f = result["files"][0]
        assert f["duplicated_lines"] == 25
        assert f["duplicated_blocks"] == 3
        assert f["duplicated_lines_density"] == 12.5
