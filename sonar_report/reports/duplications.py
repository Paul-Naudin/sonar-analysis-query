"""Duplication report generators.

Functions:
    get_duplications(client, project_key, *, branch, pr_id) -> dict  [F7]

Queries ``/api/measures/component`` for project-level metrics,
``/api/measures/component_tree`` for per-file metrics, and
``/api/duplications/show`` for the actual duplicated blocks.
"""

from datetime import datetime, timezone

from sonar_report.client import SonarClient

# Metrics fetched at project and file level
_DUPLICATION_METRICS = [
    "duplicated_lines",
    "duplicated_blocks",
    "duplicated_files",
    "duplicated_lines_density",
    "ncloc",
]

_FILE_METRICS = [
    "duplicated_lines",
    "duplicated_blocks",
    "duplicated_lines_density",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_duplications(
    client: SonarClient,
    project_key: str,
    *,
    branch: str | None = None,
    pr_id: str | None = None,
) -> dict:
    """F7 — Duplication report for a branch or pull request.

    Returns project-level summary, per-file duplication metrics (only files
    with duplications), and the detailed duplicated blocks for each file.

    Exactly one of *branch* or *pr_id* must be provided.
    """
    if not branch and not pr_id:
        raise ValueError("Provide either branch or pr_id.")

    location: dict = {"pullRequest": pr_id} if pr_id else {"branch": branch}

    # ------------------------------------------------------------------ #
    # Step 1 — project-level metrics
    # ------------------------------------------------------------------ #
    proj_data = client.get("/api/measures/component", {
        "component": project_key,
        "metricKeys": ",".join(_DUPLICATION_METRICS),
        **location,
    })
    proj_measures = _measures_to_dict(
        proj_data.get("component", {}).get("measures", [])
    )

    # ------------------------------------------------------------------ #
    # Step 2 — per-file duplication metrics (only files with duplications)
    # ------------------------------------------------------------------ #
    tree_params = {
        "component": project_key,
        "metricKeys": ",".join(_FILE_METRICS),
        "qualifiers": "FIL",
        "metricSort": "duplicated_lines",
        "metricSortFilter": "withMeasuresOnly",
        "s": "metric",
        "asc": "false",
        "ps": 500,
        **location,
    }
    components = client.get_paginated(
        "/api/measures/component_tree",
        tree_params,
        results_key="components",
    )

    # Keep only files that actually have duplications
    dup_files = [c for c in components if _file_dup_lines(c) > 0]

    # ------------------------------------------------------------------ #
    # Step 3 — fetch detailed blocks per file
    # ------------------------------------------------------------------ #
    files_report: list[dict] = []
    for comp in dup_files:
        blocks_data = client.get("/api/duplications/show", {
            "key": comp["key"],
            **location,
        })
        blocks = _parse_duplication_blocks(blocks_data)

        file_measures = _measures_to_dict(comp.get("measures", []))
        files_report.append({
            "path": comp.get("path", comp["key"]),
            "duplicated_lines": _int_val(file_measures.get("duplicated_lines")),
            "duplicated_blocks": _int_val(file_measures.get("duplicated_blocks")),
            "duplicated_lines_density": file_measures.get("duplicated_lines_density"),
            "duplication_details": blocks,
        })

    # ------------------------------------------------------------------ #
    # Build report
    # ------------------------------------------------------------------ #
    report: dict = {
        "report_type": "duplications",
        "project_key": project_key,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "duplicated_lines": _int_val(proj_measures.get("duplicated_lines")),
            "duplicated_blocks": _int_val(proj_measures.get("duplicated_blocks")),
            "duplicated_files": _int_val(proj_measures.get("duplicated_files")),
            "duplicated_lines_density": proj_measures.get("duplicated_lines_density"),
            "ncloc": _int_val(proj_measures.get("ncloc")),
            "files_in_report": len(files_report),
        },
        "files": files_report,
    }
    if pr_id:
        report["pull_request"] = pr_id
    else:
        report["branch"] = branch

    return report


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _measures_to_dict(measures: list[dict]) -> dict:
    """Convert SonarQube measures list to {metric: parsed_value}."""
    result = {}
    for m in measures:
        val = m.get("value")
        if val is None:
            period = m.get("period")
            val = period.get("value") if isinstance(period, dict) else None
        if val is not None:
            try:
                f = float(val)
                result[m["metric"]] = int(f) if f == int(f) else f
            except (ValueError, TypeError):
                result[m["metric"]] = val
        else:
            result[m["metric"]] = None
    return result


def _int_val(v) -> int:
    """Coerce a value to int, defaulting to 0."""
    if v is None:
        return 0
    try:
        return int(v)
    except (ValueError, TypeError):
        return 0


def _file_dup_lines(comp: dict) -> int:
    """Return duplicated_lines count from a component_tree component."""
    for m in comp.get("measures", []):
        if m["metric"] == "duplicated_lines":
            try:
                return int(float(m["value"]))
            except (KeyError, ValueError):
                return 0
    return 0


def _parse_duplication_blocks(data: dict) -> list[dict]:
    """Parse /api/duplications/show response into a clean list of blocks.

    Each block becomes:
    {
        "from_line": 47,
        "size": 40,
        "duplicated_in": [
            {"path": "src/.../Other.java", "from_line": 47, "size": 40},
            ...
        ]
    }
    """
    files_map: dict[str, str] = {}
    for ref, info in data.get("files", {}).items():
        files_map[ref] = info.get("name", info.get("key", f"ref-{ref}"))

    result: list[dict] = []
    for dup in data.get("duplications", []):
        blocks = dup.get("blocks", [])
        if len(blocks) < 2:
            continue

        # First block is the source file being queried
        source = blocks[0]
        targets = blocks[1:]

        result.append({
            "from_line": source.get("from"),
            "size": source.get("size"),
            "duplicated_in": [
                {
                    "path": files_map.get(str(t.get("_ref")), f"unknown-{t.get('_ref')}"),
                    "from_line": t.get("from"),
                    "size": t.get("size"),
                }
                for t in targets
            ],
        })

    return result
