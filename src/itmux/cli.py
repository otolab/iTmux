"""iTmux CLI entry point."""

import asyncio
import os
import sys
import click
import iterm2
from pathlib import Path

from .config import ConfigManager, DEFAULT_CONFIG_PATH
from .orchestrator import ProjectOrchestrator
from .iterm2 import ITerm2Bridge
from .exceptions import ProjectNotFoundError, ITerm2Error, ConfigError


async def get_orchestrator() -> ProjectOrchestrator:
    """iTerm2に接続してOrchestratorインスタンスを作成."""
    connection = await iterm2.Connection.async_create()
    app = await iterm2.async_get_app(connection)

    # 環境変数があれば優先、なければDEFAULT_CONFIG_PATHを使用
    config_path_str = os.environ.get("ITMUX_CONFIG_PATH")
    config_path = Path(config_path_str) if config_path_str else DEFAULT_CONFIG_PATH

    config_manager = ConfigManager(config_path)
    bridge = ITerm2Bridge(connection, app)

    return ProjectOrchestrator(config_manager, bridge)


@click.group()
@click.version_option()
def main():
    """iTerm2 + tmux orchestration tool for project-based window management."""
    pass


@main.command()
@click.argument("project")
def open(project: str):
    """Open or restore a project window set."""
    async def _open():
        orchestrator = await get_orchestrator()
        await orchestrator.open(project)

    try:
        asyncio.run(_open())
        click.echo(f"✓ Opened project: {project}")
    except ProjectNotFoundError as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)
    except ITerm2Error as e:
        click.echo(f"✗ iTerm2 Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"✗ Unexpected error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("project", required=False)
def sync(project: str | None):
    """Sync project configuration with current tmux session state."""
    async def _sync():
        orchestrator = await get_orchestrator()
        await orchestrator.sync(project)

    try:
        asyncio.run(_sync())
        click.echo(f"✓ Synced project: {project or 'current'}")
    except ValueError as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)
    except ProjectNotFoundError as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)
    except ITerm2Error as e:
        click.echo(f"✗ iTerm2 Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"✗ Unexpected error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("project", required=False)
def close(project: str | None):
    """Close and detach a project window set."""
    async def _close():
        orchestrator = await get_orchestrator()
        await orchestrator.close(project)

    try:
        asyncio.run(_close())
        click.echo(f"✓ Closed project: {project or 'current'}")
    except ValueError as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)
    except ProjectNotFoundError as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)
    except ITerm2Error as e:
        click.echo(f"✗ iTerm2 Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"✗ Unexpected error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("project", required=False)
@click.argument("window", required=False)
def add(project: str | None, window: str | None):
    """Add a new window to a project."""
    async def _add():
        orchestrator = await get_orchestrator()
        await orchestrator.add(project, window)

    try:
        asyncio.run(_add())
        click.echo(f"✓ Added window to project: {project or 'current'}")
    except ValueError as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)
    except ProjectNotFoundError as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)
    except ITerm2Error as e:
        click.echo(f"✗ iTerm2 Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"✗ Unexpected error: {e}", err=True)
        sys.exit(1)


@main.command()
def list():
    """List all managed projects."""
    async def _list():
        orchestrator = await get_orchestrator()
        return orchestrator.list()

    try:
        projects = asyncio.run(_list())

        if not projects:
            click.echo("No projects configured.")
            return

        click.echo("Projects:")
        for project_name, info in projects.items():
            click.echo(f"  {project_name} ({info['count']} windows)")
            for window in info['windows']:
                click.echo(f"    - {window}")
    except ConfigError as e:
        click.echo(f"✗ Config Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"✗ Unexpected error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
