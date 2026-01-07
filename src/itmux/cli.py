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


def run_async_command(coro, success_message: str, handle_value_error: bool = False):
    """非同期コマンドを実行し、共通のエラーハンドリングを適用.

    Args:
        coro: 実行する非同期コルーチン
        success_message: 成功時のメッセージ
        handle_value_error: ValueErrorをハンドリングするか
    """
    try:
        asyncio.run(coro)
        click.echo(success_message)
    except ValueError as e:
        if handle_value_error:
            click.echo(f"✗ Error: {e}", err=True)
            sys.exit(1)
        raise
    except ProjectNotFoundError as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)
    except ITerm2Error as e:
        click.echo(f"✗ iTerm2 Error: {e}", err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"✗ Config Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"✗ Unexpected error: {e}", err=True)
        sys.exit(1)


@click.group()
@click.version_option()
def main():
    """iTerm2 + tmux orchestration tool for project-based window management."""
    # hookから呼び出すコマンドパスを環境変数に設定（未設定の場合のみ）
    if "ITMUX_COMMAND" not in os.environ:
        # sys.argv[0]を絶対パスに変換
        command_path = os.path.abspath(sys.argv[0])
        os.environ["ITMUX_COMMAND"] = command_path


@main.command()
@click.argument("project")
@click.option("--no-default", is_flag=True, help="Do not create default window if project has no windows")
def open(project: str, no_default: bool):
    """Open or restore a project window set."""
    async def _open():
        orchestrator = await get_orchestrator()
        await orchestrator.open(project, create_default=not no_default)

    run_async_command(_open(), f"✓ Opened project: {project}")


@main.command()
@click.argument("project", required=False)
@click.option("--all", is_flag=True, help="Sync all projects (check session existence)")
def sync(project: str | None, all: bool):
    """Sync project configuration with current tmux session state."""
    async def _sync():
        orchestrator = await get_orchestrator()
        await orchestrator.sync(project, sync_all=all)

    message = "✓ Synced all projects" if all else f"✓ Synced project: {project or 'current'}"
    run_async_command(_sync(), message, handle_value_error=True)


@main.command()
@click.argument("project", required=False)
@click.option("--debounce", is_flag=True, help="Enable debounce (skip if saved within 1 second)")
def save(project: str | None, debounce: bool):
    """Save tmux session state with tmux-resurrect."""
    async def _save():
        orchestrator = await get_orchestrator()
        orchestrator.save(project, debounce=debounce)

    message = f"✓ Saved session: {project or 'current'}"
    run_async_command(_save(), message, handle_value_error=True)


@main.command()
@click.argument("project", required=False)
def close(project: str | None):
    """Close and detach a project window set."""
    async def _close():
        orchestrator = await get_orchestrator()
        await orchestrator.close(project)

    run_async_command(_close(), f"✓ Closed project: {project or 'current'}", handle_value_error=True)


@main.command()
@click.argument("project", required=False)
@click.argument("window", required=False)
def add(project: str | None, window: str | None):
    """Add a new window to a project."""
    async def _add():
        orchestrator = await get_orchestrator()
        await orchestrator.add(project, window)

    run_async_command(_add(), f"✓ Added window to project: {project or 'current'}", handle_value_error=True)


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
