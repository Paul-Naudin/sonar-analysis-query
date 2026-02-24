"""Coverage report generators.

Functions:
    get_coverage(client, project_key, branch)     -> dict  [F4]
    get_pr_coverage(client, project_key, pr_id)   -> dict  [F5]

Both functions query ``/api/measures/component`` and return a structured dict
with ``metrics`` (current-code) and/or ``new_code`` sections.
"""

from datetime import datetime, timezone

# --------------------------------------------------------------------------- #
# Metric key lists
# --------------------------------------------------------------------------- #

#: Current-code metrics fetched for F4
_BRANCH_METRICS: list[str] = [
    "coverage",
    "line_coverage",
    "branch_coverage",
    "lines_to_cover",
    "uncovered_lines",
    "uncovered_conditions",
    "conditions_to_cover",
]

#: New-code / leak-period metrics fetched for F4 and F5
_NEW_CODE_METRICS: list[str] = [
    "new_coverage",
    "new_line_coverage",
    "new_branch_coverage",
    "new_lines_to_cover",
    "new_uncovered_lines",
    "new_uncovered_conditions",
    "new_conditions_to_cover",
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _parse_value(raw: dict):
    """Return a numeric value from a SonarQube measure dict, or None if absent.

    SonarQube stores current-code values under ``"value"`` and (in older
    versions) new-code / leak-period values under ``"period": {"value": ...}``.
    Newer versions expose both; we prefer ``"value"`` when present.
    """
    val = raw.get("value")
    if val is None:
        period = raw.get("period")
        val = period.get("value") if isinstance(period, dict) else None
    if val is None:
        return None
    try:
        f = float(val)
        # Return int when the float is a whole number (e.g. 88.0 → 88)
        return int(f) if f == int(f) else f
    except (ValueError, TypeError):
        return val


def _measures_to_dict(measures: list[dict]) -> dict:
    """Convert a list of SonarQube measure dicts to ``{metric_key: value}``."""
    return {m["metric"]: _parse_value(m) for m in measures}


def _strip_new_prefix(d: dict) -> dict:
    """Return a copy of *d* with the ``new_`` prefix removed from all keys."""
    return {(k[4:] if k.startswith("new_") else k): v for k, v in d.items()}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def get_coverage(client, project_key: str, branch: str) -> dict:
    """F4 — Coverage metrics on *branch*.

    Returns a report dict with two sections:

    * ``metrics``  — current-code coverage figures.
    * ``new_code`` — leak-period (new code) coverage figures
      (keys normalised: ``new_coverage`` → ``coverage``, etc.).
    """
    all_metrics = _BRANCH_METRICS + _NEW_CODE_METRICS
    params = {
        "component": project_key,
        "branch": branch,
        "metricKeys": ",".join(all_metrics),
    }
    data = client.get("/api/measures/component", params=params)
    measures = _measures_to_dict(data.get("component", {}).get("measures", []))

    current = {k: measures.get(k) for k in _BRANCH_METRICS}
    new_raw = {k: measures.get(k) for k in _NEW_CODE_METRICS}
    new_code = _strip_new_prefix(new_raw)

    return {
        "report_type": "coverage",
        "project_key": project_key,
        "branch": branch,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": current,
        "new_code": new_code,
    }


def get_pr_coverage(client, project_key: str, pr_id: str) -> dict:
    """F5 — Coverage metrics for pull request *pr_id*.

    On a PR, SonarQube only computes new-code metrics, so the returned report
    contains only a ``new_code`` section (no ``metrics`` key).
    """
    params = {
        "component": project_key,
        "pullRequest": pr_id,
        "metricKeys": ",".join(_NEW_CODE_METRICS),
    }
    data = client.get("/api/measures/component", params=params)
    measures = _measures_to_dict(data.get("component", {}).get("measures", []))

    new_raw = {k: measures.get(k) for k in _NEW_CODE_METRICS}
    new_code = _strip_new_prefix(new_raw)

    return {
        "report_type": "pr_coverage",
        "project_key": project_key,
        "pull_request": pr_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "new_code": new_code,
    }

