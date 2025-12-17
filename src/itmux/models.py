"""iTmux data models using Pydantic."""

from typing import Optional
from pydantic import BaseModel, Field, field_validator


class WindowSize(BaseModel):
    """tmuxウィンドウサイズ."""

    columns: int = Field(gt=0, description="列数（横幅）")
    lines: int = Field(gt=0, description="行数（縦幅）")

    @field_validator("columns", "lines")
    @classmethod
    def validate_positive(cls, v: int) -> int:
        """正の整数であることを検証."""
        if v <= 0:
            raise ValueError("must be positive")
        return v


class SessionConfig(BaseModel):
    """tmuxセッション設定."""

    name: str = Field(min_length=1, description="セッション名")
    window_size: Optional[WindowSize] = Field(
        default=None, description="ウィンドウサイズ（省略時はデフォルト）"
    )

    @field_validator("name")
    @classmethod
    def validate_session_name(cls, v: str) -> str:
        """tmux互換の命名規則を検証."""
        # tmuxセッション名で使用不可な文字
        invalid_chars = [".", ":", "[", "]"]
        for char in invalid_chars:
            if char in v:
                raise ValueError(f'session name cannot contain "{char}"')
        return v


class ProjectConfig(BaseModel):
    """プロジェクト設定."""

    name: str = Field(min_length=1, description="プロジェクト名")
    tmux_sessions: list[SessionConfig] = Field(
        default_factory=list, description="tmuxセッションリスト"
    )

    @field_validator("tmux_sessions")
    @classmethod
    def validate_unique_sessions(
        cls, v: list[SessionConfig]
    ) -> list[SessionConfig]:
        """セッション名の重複チェック."""
        names = [s.name for s in v]
        if len(names) != len(set(names)):
            raise ValueError("session names must be unique")
        return v


class Config(BaseModel):
    """全体設定."""

    projects: dict[str, ProjectConfig] = Field(
        default_factory=dict, description="プロジェクト定義"
    )

    @field_validator("projects")
    @classmethod
    def validate_project_names_match_keys(
        cls, v: dict[str, ProjectConfig]
    ) -> dict[str, ProjectConfig]:
        """キーとProjectConfig.nameの一致を検証."""
        for key, project in v.items():
            if key != project.name:
                raise ValueError(
                    f'project key "{key}" does not match name "{project.name}"'
                )
        return v
