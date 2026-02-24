"""CLI entry point — command definitions using Click.

Commands:
    init          Generate a template config file
    pr-issues     F1 - New issues introduced by a PR
    new-issues    F2 - New issues on main (leak period)
    all-issues    F3 - All non-accepted issues on main
    coverage      F4/F5 - Coverage metrics on main or a PR
"""

import json
import sys
from typing import Any

import click

from sonar_report import __version__


# ---------------------------------------------------------------------------
# Helpers shared by all data commands
# ---------------------------------------------------------------------------

def _make_client(ctx: click.Context):
    """Load config and return a ready SonarClient. Exits on error."""
    from sonar_report.client import SonarClient
    from sonar_report.config import ConfigError, load

    obj = ctx.obj
    try:
        config = load(obj["config_path"])
    except ConfigError as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        sys.exit(1)

    if obj["verbose"]:
        click.echo(f"[verbose] Connecting to {config.url}", err=True)

    return config, SonarClient(url=config.url, token=config.token)


def _emit_json(data: Any, ctx: click.Context) -> None:
    """Write JSON to stdout or to the file specified by --output."""
    obj = ctx.obj
    indent = 2 if obj["pretty"] else None
    text = json.dumps(data, indent=indent, ensure_ascii=False)

    output_path: str | None = obj["output_path"]
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
        click.echo(f"Report written to '{output_path}'", err=True)
    else:
        click.echo(text)


def _handle_client_errors(func):
    """Decorator that catches SonarClient exceptions and exits cleanly."""
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        from sonar_report.client import (
            AuthenticationError,
            NetworkError,
            NotFoundError,
            SonarClientError,
        )
        from sonar_report.config import ProjectNotFoundError

        try:
            return func(*args, **kwargs)
        except ProjectNotFoundError as exc:
            click.echo(f"Project error: {exc}", err=True)
            sys.exit(1)
        except AuthenticationError as exc:
            click.echo(f"Authentication error: {exc}", err=True)
            sys.exit(1)
        except NotFoundError as exc:
            click.echo(f"Not found: {exc}", err=True)
            sys.exit(1)
        except NetworkError as exc:
            click.echo(f"Network error: {exc}", err=True)
            sys.exit(1)
        except SonarClientError as exc:
            click.echo(f"SonarQube error: {exc}", err=True)
            sys.exit(1)

    return wrapper


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.option("--config", "config_path", default="sonar-config.yaml", show_default=True,
              help="Path to the configuration file.")
@click.option("--output", "output_path", default=None,
              help="Write JSON output to a file instead of stdout.")
@click.option("--pretty", is_flag=True, default=False,
              help="Pretty-print the JSON output.")
@click.option("--branch", default="main", show_default=True,
              help="Target branch (overrides config default).")
@click.option("--verbose", is_flag=True, default=False,
              help="Enable verbose logging.")
@click.version_option(__version__, prog_name="sonar-report")
@click.pass_context
def cli(ctx: click.Context, config_path: str, output_path: str | None,
        pretty: bool, branch: str, verbose: bool) -> None:
    """SonarQube report tool — query issues and coverage, export as JSON."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path
    ctx.obj["output_path"] = output_path
    ctx.obj["pretty"] = pretty
    ctx.obj["branch"] = branch
    ctx.obj["verbose"] = verbose


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

@cli.command("init")
@click.option("--output", "output_path", default="sonar-config.yaml", show_default=True,
              help="Path where the template config file will be written.")
def init_command(output_path: str) -> None:
    """Generate a template sonar-config.yaml file."""
    from sonar_report.config import ConfigError, generate_template
    try:
        generate_template(output_path)
        click.echo(f"Template written to '{output_path}'.")
        click.echo("Edit it with your server URL, token and project key mappings.")
    except ConfigError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# pr-issues  (F1)
# ---------------------------------------------------------------------------

@cli.command("pr-issues")
@click.argument("project")
@click.argument("pr_id")
@click.pass_context
@_handle_client_errors
def pr_issues_command(ctx: click.Context, project: str, pr_id: str) -> None:
    """F1 — New issues introduced by pull request PR_ID."""
    from sonar_report.reports.issues import get_pr_issues

    config, client = _make_client(ctx)
    project_key = config.resolve_project(project)

    if ctx.obj["verbose"]:
        click.echo(f"[verbose] Fetching PR issues for {project_key} PR#{pr_id}", err=True)

    report = get_pr_issues(client, project_key, pr_id)
    _emit_json(report, ctx)


# ---------------------------------------------------------------------------
# new-issues  (F2)
# ---------------------------------------------------------------------------

@cli.command("new-issues")
@click.argument("project")
@click.pass_context
@_handle_client_errors
def new_issues_command(ctx: click.Context, project: str) -> None:
    """F2 — New issues on the main branch (leak period)."""
    from sonar_report.reports.issues import get_new_issues

    config, client = _make_client(ctx)
    project_key = config.resolve_project(project)
    branch = ctx.obj["branch"]

    if ctx.obj["verbose"]:
        click.echo(f"[verbose] Fetching new issues for {project_key} on branch '{branch}'", err=True)

    report = get_new_issues(client, project_key, branch)
    _emit_json(report, ctx)


# ---------------------------------------------------------------------------
# all-issues  (F3)
# ---------------------------------------------------------------------------

@cli.command("all-issues")
@click.argument("project")
@click.pass_context
@_handle_client_errors
def all_issues_command(ctx: click.Context, project: str) -> None:
    """F3 — All non-accepted open issues on the main branch."""
    from sonar_report.reports.issues import get_all_issues

    config, client = _make_client(ctx)
    project_key = config.resolve_project(project)
    branch = ctx.obj["branch"]

    if ctx.obj["verbose"]:
        click.echo(f"[verbose] Fetching all issues for {project_key} on branch '{branch}'", err=True)

    report = get_all_issues(client, project_key, branch)
    _emit_json(report, ctx)


# ---------------------------------------------------------------------------
# coverage  (F4 / F5)
# ---------------------------------------------------------------------------

@cli.command("coverage")
@click.argument("project")
@click.option("--pr", "pr_id", default=None,
              help="Pull request ID. If omitted, fetches main branch coverage.")
@click.pass_context
@_handle_client_errors
def coverage_command(ctx: click.Context, project: str, pr_id: str | None) -> None:
    """F4/F5 — Coverage metrics for the main branch or a pull request."""
    from sonar_report.reports.coverage import get_coverage, get_pr_coverage

    config, client = _make_client(ctx)
    project_key = config.resolve_project(project)

    if pr_id:
        if ctx.obj["verbose"]:
            click.echo(f"[verbose] Fetching coverage for {project_key} PR#{pr_id}", err=True)
        report = get_pr_coverage(client, project_key, pr_id)
    else:
        branch = ctx.obj["branch"]
        if ctx.obj["verbose"]:
            click.echo(f"[verbose] Fetching coverage for {project_key} on branch '{branch}'", err=True)
        report = get_coverage(client, project_key, branch)

    _emit_json(report, ctx)
