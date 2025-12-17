"""iTmux CLI entry point."""

import click


@click.group()
@click.version_option()
def main():
    """iTerm2 + tmux orchestration tool for project-based window management."""
    pass


@main.command()
@click.argument("project")
def open(project: str):
    """Open or restore a project window set."""
    click.echo(f"Opening project: {project}")
    # TODO: Implement project opening logic


@main.command()
@click.argument("project")
def close(project: str):
    """Close and detach a project window set."""
    click.echo(f"Closing project: {project}")
    # TODO: Implement project closing logic


@main.command()
def list():
    """List all managed projects."""
    click.echo("Managed projects:")
    # TODO: Implement project listing logic


if __name__ == "__main__":
    main()
