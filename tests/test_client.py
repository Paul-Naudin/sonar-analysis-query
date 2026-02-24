"""Tests for sonar_report/client.py"""

import warnings

import pytest
import requests_mock as req_mock

from sonar_report.client import (
    AuthenticationError,
    NetworkError,
    NotFoundError,
    SonarClient,
    SonarClientError,
)

BASE = "https://sonar.example.com"


@pytest.fixture
def client() -> SonarClient:
    return SonarClient(url=BASE, token="squ_test")


# ---------------------------------------------------------------------------
# get() — happy path
# ---------------------------------------------------------------------------

def test_get_returns_parsed_json(client, requests_mock):
    requests_mock.get(f"{BASE}/api/issues/search", json={"issues": [], "paging": {"total": 0}})
    data = client.get("/api/issues/search")
    assert data == {"issues": [], "paging": {"total": 0}}


def test_get_sends_auth_header(client, requests_mock):
    adapter = requests_mock.get(f"{BASE}/api/issues/search", json={})
    client.get("/api/issues/search")
    assert adapter.last_request.headers.get("Authorization") is not None


# ---------------------------------------------------------------------------
# get() — HTTP error codes
# ---------------------------------------------------------------------------

def test_get_401_raises_authentication_error(client, requests_mock):
    requests_mock.get(f"{BASE}/api/issues/search", status_code=401)
    with pytest.raises(AuthenticationError):
        client.get("/api/issues/search")


def test_get_404_raises_not_found_error(client, requests_mock):
    requests_mock.get(f"{BASE}/api/issues/search", status_code=404)
    with pytest.raises(NotFoundError):
        client.get("/api/issues/search")


def test_get_500_raises_sonar_client_error(client, requests_mock):
    requests_mock.get(f"{BASE}/api/issues/search", status_code=500, text="Internal Server Error")
    with pytest.raises(SonarClientError, match="500"):
        client.get("/api/issues/search")


# ---------------------------------------------------------------------------
# get() — network errors
# ---------------------------------------------------------------------------

def test_get_timeout_raises_network_error(client, requests_mock):
    import requests
    requests_mock.get(f"{BASE}/api/issues/search", exc=requests.exceptions.Timeout)
    with pytest.raises(NetworkError, match="timed out"):
        client.get("/api/issues/search")


def test_get_connection_error_raises_network_error(client, requests_mock):
    import requests
    requests_mock.get(f"{BASE}/api/issues/search", exc=requests.exceptions.ConnectionError)
    with pytest.raises(NetworkError, match="Unable to reach"):
        client.get("/api/issues/search")


# ---------------------------------------------------------------------------
# get_paginated() — pagination logic
# ---------------------------------------------------------------------------

def _page(items: list, total: int, page: int) -> dict:
    return {"issues": items, "paging": {"pageIndex": page, "pageSize": 500, "total": total}}


def test_paginated_single_page(client, requests_mock):
    requests_mock.get(
        f"{BASE}/api/issues/search",
        json=_page([{"key": "i1"}, {"key": "i2"}], total=2, page=1),
    )
    results = client.get_paginated("/api/issues/search", {}, results_key="issues")
    assert results == [{"key": "i1"}, {"key": "i2"}]


def test_paginated_multiple_pages(client, requests_mock):
    """Two pages of 2 items each (total=4, page_size mocked to 2)."""
    responses = [
        {"json": _page([{"key": f"i{i}"} for i in range(1, 501)], total=750, page=1)},
        {"json": _page([{"key": f"i{i}"} for i in range(501, 751)], total=750, page=2)},
    ]
    requests_mock.get(f"{BASE}/api/issues/search", responses)
    results = client.get_paginated("/api/issues/search", {}, results_key="issues")
    assert len(results) == 750
    assert results[0]["key"] == "i1"
    assert results[-1]["key"] == "i750"


def test_paginated_empty_result(client, requests_mock):
    requests_mock.get(f"{BASE}/api/issues/search", json=_page([], total=0, page=1))
    results = client.get_paginated("/api/issues/search", {}, results_key="issues")
    assert results == []


def test_paginated_warns_above_10000(client, requests_mock):
    requests_mock.get(
        f"{BASE}/api/issues/search",
        json=_page([{"key": "i1"}], total=10_001, page=1),
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        client.get_paginated("/api/issues/search", {}, results_key="issues")

    assert any("10 000" in str(w.message) for w in caught)

