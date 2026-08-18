"""tmuxセッションへの作業ディレクトリ（cwd）適用."""

from pathlib import Path
from typing import Optional

from ..exceptions import CwdError


def validate_cwd_path(cwd: Path) -> None:
    """cwd が存在するディレクトリか検証（runtime 用）.

    Args:
        cwd: 検証するパス

    Raises:
        CwdError: パスが存在しない、またはディレクトリでない
    """
    if not cwd.exists():
        raise CwdError(f"Directory does not exist: {cwd}")
    if not cwd.is_dir():
        raise CwdError(f"Not a directory: {cwd}")


def cwd_creation_args(cwd: Optional[Path]) -> list[str]:
    """tmux new-session / new-window の -c 引数."""
    if cwd is None:
        return []
    return ["-c", str(cwd)]
