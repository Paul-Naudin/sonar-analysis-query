"""SonarQube API client.

Usage:
    client = SonarClient(url="https://sonar.example.com", token="squ_xxx")
    data   = client.get("/api/issues/search", {"componentKeys": "my-project"})
    issues = client.get_paginated("/api/issues/search", params, results_key="issues")
"""

import warnings
from typing import Any

import requests

PAGE_SIZE = 500
PAGINATION_WARNING_THRESHOLD = 10_000


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SonarClientError(Exception):
    """Base exception for all client errors."""


class AuthenticationError(SonarClientError):
    """Raised on HTTP 401 — invalid or expired token."""


class NotFoundError(SonarClientError):
    """Raised on HTTP 404 — project, PR or resource not found."""


class NetworkError(SonarClientError):
    """Raised on connection timeout or unreachable server."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class SonarClient:
    """Thin wrapper around the SonarQube REST API."""

    def __init__(self, url: str, token: str, timeout: int = 30) -> None:
        self.base_url = url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._session = requests.Session()
        # SonarQube auth: token as username, empty password
        self._session.auth = (token, "")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict:
        """Perform a single GET request and return the parsed JSON response.

        Raises:
            AuthenticationError: HTTP 401
            NotFoundError:       HTTP 404
            SonarClientError:    Any other non-2xx response
            NetworkError:        Timeout or connection failure
        """
        return self._request(endpoint, params or {})

    def get_paginated(
        self,
        endpoint: str,
        params: dict[str, Any],
        results_key: str,
    ) -> list[dict]:
        """Fetch all pages for an endpoint and return a flat list of results.

        SonarQube paginates via ``p`` (page number) and ``ps`` (page size).
        The total result count is in ``response["paging"]["total"]``.

        Emits a warning when total > PAGINATION_WARNING_THRESHOLD (10 000)
        because SonarQube refuses to page beyond that limit.

        Args:
            endpoint:    API path, e.g. ``/api/issues/search``
            params:      Query parameters (do not include ``p`` or ``ps``)
            results_key: Key in the response JSON that holds the results list
                         (e.g. ``"issues"`` or ``"components"``)
        """
        all_results: list[dict] = []
        page = 1
        _warning_emitted = False

        while True:
            page_params = {**params, "ps": PAGE_SIZE, "p": page}
            data = self._request(endpoint, page_params)

            results = data.get(results_key, [])
            all_results.extend(results)

            paging = data.get("paging", {})
            total: int = paging.get("total", len(all_results))

            if total > PAGINATION_WARNING_THRESHOLD and not _warning_emitted:
                warnings.warn(
                    f"Result set exceeds {PAGINATION_WARNING_THRESHOLD} items (total={total}). "
                    "SonarQube caps pagination at 10 000 — some results may be missing. "
                    "Consider filtering by severity or type to reduce the result set.",
                    UserWarning,
                    stacklevel=2,
                )
                _warning_emitted = True

            # Stop when we've fetched everything
            if len(all_results) >= total or not results:
                break

            page += 1

        return all_results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _request(self, endpoint: str, params: dict[str, Any]) -> dict:
        url = f"{self.base_url}{endpoint}"
        try:
            response = self._session.get(url, params=params, timeout=self._timeout)
        except requests.exceptions.Timeout as exc:
            raise NetworkError(
                f"Request timed out after {self._timeout}s while contacting '{url}'"
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise NetworkError(
                f"Unable to reach SonarQube server at '{self.base_url}'"
            ) from exc

        if response.status_code == 401:
            raise AuthenticationError(
                "Authentication failed — check that your token is valid and not expired."
            )
        if response.status_code == 404:
            raise NotFoundError(
                f"Resource not found: {url}"
            )
        if not response.ok:
            raise SonarClientError(
                f"Unexpected response {response.status_code} from {url}: {response.text[:200]}"
            )

        return response.json()

