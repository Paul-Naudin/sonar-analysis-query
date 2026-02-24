# sonar-report

A lightweight CLI tool that queries the [SonarQube REST API](https://next.sonarqube.com/sonarqube/web_api) and exports results as structured JSON — ready for piping into scripts, CI artefacts, or dashboards.

No extra runtime beyond Python and `pip` is required.

---

## Features

| Command | What it returns |
|---------|-----------------|
| `pr-issues <project> <pr-id>` | All unresolved issues introduced by a pull request |
| `new-issues <project>` | Unresolved issues added in the current new-code period (leak period) on a branch |
| `all-issues <project>` | Every non-accepted open issue on a branch (`OPEN`, `CONFIRMED`, `REOPENED`) |
| `coverage <project>` | Coverage metrics for a branch (current code + new-code period) |
| `coverage <project> --pr <pr-id>` | Coverage metrics for a pull request (new-code period only) |

---

## Installation

```bash
git clone https://github.com/Paul-Naudin/sonar-analysis-query.git
cd sonar-analysis-query
pip install -r requirements.txt
```

Python 3.10+ is required.  Compatible with SonarQube 9.x / 10.x and SonarCloud.

---

## Configuration

### 1 — Create the config file

```bash
# Copy the bundled template
cp sonar-config.example.yaml sonar-config.yaml

# — or — let the CLI copy it for you
python -m sonar_report init
```

`sonar-config.yaml` is listed in `.gitignore` so your token is never committed.

### 2 — Edit `sonar-config.yaml`

```yaml
server:
  url: "https://sonar.example.com"   # No trailing slash
  token: "squ_xxxxxxxxxxxx"           # User token (read access is enough)

projects:
  # Short alias -> full SonarQube project key
  my-project: "com.example:my-project"
  frontend:   "com.example:frontend"
```

Every command accepts either the alias (`my-project`) or the raw project key (`com.example:my-project`) — whichever you pass, it resolves correctly.

### Environment variable overrides

`SONAR_URL` and `SONAR_TOKEN` override the values in the file when set:

```bash
export SONAR_URL="https://sonar.example.com"
export SONAR_TOKEN="squ_xxxxxxxxxxxx"
```

This is convenient in CI pipelines where secrets are injected as env vars and the file only needs the `projects` mapping.

---

## Usage

All commands share a common set of global options placed **before** the command name:

```
python -m sonar_report [GLOBAL OPTIONS] <command> [COMMAND OPTIONS] <args>
```

### Global options

| Option | Default | Description |
|--------|---------|-------------|
| `--config <path>` | `sonar-config.yaml` | Path to the YAML config file |
| `--output <path>` | stdout | Write the JSON report to a file instead of stdout |
| `--pretty` | off | Pretty-print (indent) the JSON output |
| `--branch <name>` | `main` | Branch to query for branch-level commands |
| `--verbose` | off | Print HTTP requests and extra debug info to stderr |

---

### `pr-issues` — issues introduced by a pull request

```bash
python -m sonar_report pr-issues <project> <pr-id>

# Examples
python -m sonar_report pr-issues my-project 42
python -m sonar_report --pretty --output pr-42-issues.json pr-issues my-project 42
```

**Sample output**
```json
{
  "report_type": "pr_issues",
  "project_key": "com.example:my-project",
  "pull_request": "42",
  "generated_at": "2024-06-01T10:00:00+00:00",
  "summary": {
    "total": 2,
    "by_severity": { "MAJOR": 1, "MINOR": 1 },
    "by_type":     { "BUG": 1, "CODE_SMELL": 1 }
  },
  "issues": [
    {
      "key": "AYx...",
      "rule": "java:S1481",
      "severity": "MINOR",
      "type": "CODE_SMELL",
      "component": "com.example:my-project:src/main/java/Foo.java",
      "line": 42,
      "message": "Remove this unused 'result' local variable.",
      "effort": "2min",
      "status": "OPEN",
      "assignee": null,
      "tags": ["unused"],
      "creationDate": "2024-06-01T09:55:00+0000"
    }
  ]
}
```

---

### `new-issues` — new issues in the leak period

```bash
python -m sonar_report new-issues <project>

# Target a non-default branch
python -m sonar_report --branch develop new-issues my-project
```

Output structure is identical to `pr-issues` with `"report_type": "new_issues"` and a `"branch"` field instead of `"pull_request"`.

---

### `all-issues` — every open issue on a branch

```bash
python -m sonar_report all-issues <project>

python -m sonar_report --branch release/1.0 all-issues my-project --output issues.json --pretty
```

Returns issues with status `OPEN`, `CONFIRMED`, or `REOPENED` (accepted / won't-fix issues are excluded).  
Output structure is the same as `pr-issues` with `"report_type": "all_issues"`.

> **Note:** If a project has more than 10 000 open issues a warning is printed to stderr but all pages are still collected.

---

### `coverage` — coverage metrics

```bash
# Branch coverage (F4)
python -m sonar_report coverage <project>
python -m sonar_report --branch develop --pretty coverage my-project

# PR coverage (F5)
python -m sonar_report coverage <project> --pr <pr-id>
python -m sonar_report coverage my-project --pr 42
```

| `coverage` option | Description |
|-------------------|-------------|
| `--pr <id>` | Query a pull request instead of a branch |

**Sample output — branch**
```json
{
  "report_type": "coverage",
  "project_key": "com.example:my-project",
  "branch": "main",
  "generated_at": "2024-06-01T10:00:00+00:00",
  "metrics": {
    "coverage": 85.5,
    "line_coverage": 88.2,
    "branch_coverage": 79.3,
    "lines_to_cover": 1200,
    "uncovered_lines": 142,
    "conditions_to_cover": 340,
    "uncovered_conditions": 70
  },
  "new_code": {
    "coverage": 80.1,
    "line_coverage": 82.0,
    "branch_coverage": 75.0,
    "lines_to_cover": 200,
    "uncovered_lines": 40,
    "conditions_to_cover": 60,
    "uncovered_conditions": 15
  }
}
```

**Sample output — pull request** (`--pr`)
```json
{
  "report_type": "pr_coverage",
  "project_key": "com.example:my-project",
  "pull_request": "42",
  "generated_at": "2024-06-01T10:00:00+00:00",
  "new_code": {
    "coverage": 76.4,
    "line_coverage": 78.0,
    "branch_coverage": 71.2,
    "lines_to_cover": 85,
    "uncovered_lines": 20,
    "conditions_to_cover": 30,
    "uncovered_conditions": 9
  }
}
```

> SonarQube stores new-code metric values under either `"value"` (current API) or `"period.value"` (older instances).  Both formats are handled transparently.

---

## CI / scripting examples

```bash
# Fail the pipeline if new issues were introduced by the PR
COUNT=$(python -m sonar_report pr-issues my-project "$PR_ID" | python -c "import sys,json; print(json.load(sys.stdin)['summary']['total'])")
[ "$COUNT" -gt 0 ] && echo "::error::$COUNT new issue(s) detected" && exit 1

# Save a coverage badge value
python -m sonar_report coverage my-project | python -c \
  "import sys,json; d=json.load(sys.stdin); print(d['metrics']['coverage'])"
```

---

## Development

```bash
# Install runtime + dev dependencies
pip install -r requirements.txt
pip install pytest requests-mock

# Run the test suite
pytest tests/ -v

# Run a single test file
pytest tests/test_coverage.py -v
```

All 49 tests run in under 5 seconds (no network calls — `requests-mock` is used throughout).

### Project layout

```
sonar_report/
├── __init__.py        # version
├── __main__.py        # entry-point (python -m sonar_report)
├── cli.py             # Click commands and shared options
├── client.py          # SonarClient — HTTP + pagination
├── config.py          # YAML config loading and project resolution
├── models.py          # (reserved)
└── reports/
    ├── issues.py      # F1 pr-issues / F2 new-issues / F3 all-issues
    └── coverage.py    # F4 branch coverage / F5 PR coverage

tests/
├── test_config.py     # 13 tests
├── test_client.py     # 11 tests
├── test_issues.py     # 11 tests
└── test_coverage.py   # 14 tests
```

---

## Compatibility

| Component | Version |
|-----------|---------|
| Python | 3.10+ |
| SonarQube | 9.x / 10.x |
| SonarCloud | ✓ |
