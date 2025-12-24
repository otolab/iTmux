"""iTmux CLI entry point."""

import asyncio
import os
import sys
import click
import iterm2
from pathlib import Path

from .config import ConfigManager, DEFAULT_CONFIG_PATH
from .orchestrator import ProjectOrchestrator
from .iterm2_bridge import ITerm2Bridge
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


async def get_bridge() -> ITerm2Bridge:
    """iTerm2に接続してBridgeインスタンスを作成."""
    connection = await iterm2.Connection.async_create()
    app = await iterm2.async_get_app(connection)
    return ITerm2Bridge(connection, app)


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
@click.argument("session", required=False)
def add(project: str | None, session: str | None):
    """Add a new session to a project."""
    async def _add():
        orchestrator = await get_orchestrator()
        await orchestrator.add(project, session)

    try:
        asyncio.run(_add())
        click.echo(f"✓ Added session to project: {project or 'current'}")
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
            click.echo(f"  {project_name} ({info['count']} sessions)")
            for session in info['sessions']:
                click.echo(f"    - {session}")
    except ConfigError as e:
        click.echo(f"✗ Config Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"✗ Unexpected error: {e}", err=True)
        sys.exit(1)


@main.group()
def gateway():
    """Gateway management commands."""
    pass


@gateway.command()
def status():
    """Check gateway status."""
    async def _status():
        bridge = await get_bridge()
        return await bridge.get_gateway_status()

    try:
        status = asyncio.run(_status())
        if status:
            click.echo("Gateway status:")
            click.echo(f"  Connection ID: {status['connection_id']}")
            click.echo(f"  Created at: {status['created_at']}")
            click.echo(f"  Alive: {status['alive']}")
        else:
            click.echo("No gateway found.")
    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)


@gateway.command()
def create():
    """Create or get existing gateway."""
    async def _create():
        bridge = await get_bridge()
        _, conn = await bridge.get_or_create_gateway()
        return conn.connection_id

    try:
        conn_id = asyncio.run(_create())
        click.echo("✓ Gateway ready:")
        click.echo(f"  Connection ID: {conn_id}")
    except ITerm2Error as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"✗ Unexpected error: {e}", err=True)
        sys.exit(1)


@gateway.command()
def close():
    """Close gateway (detaches all tmux sessions)."""
    async def _close():
        bridge = await get_bridge()
        await bridge.close_gateway()

    try:
        asyncio.run(_close())
        click.echo("✓ Gateway closed")
    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
