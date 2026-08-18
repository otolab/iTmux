"""iTmux data models using Pydantic."""

from pathlib import Path
from typing import Optional, Any
from pydantic import BaseModel, Field, field_validator, model_serializer


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


class WindowConfig(BaseModel):
    """tmuxウィンドウ設定."""

    name: str = Field(min_length=1, description="ウィンドウ名")
    window_size: Optional[WindowSize] = Field(
        default=None, description="ウィンドウサイズ（省略時はデフォルト）"
    )

    @field_validator("name")
    @classmethod
    def validate_window_name(cls, v: str) -> str:
        """tmux互換の命名規則を検証."""
        # tmuxウィンドウ名で使用不可な文字
        invalid_chars = [".", ":", "[", "]"]
        for char in invalid_chars:
            if char in v:
                raise ValueError(f'window name cannot contain "{char}"')
        return v


class ProjectConfig(BaseModel):
    """プロジェクト設定."""

    name: str = Field(min_length=1, description="プロジェクト名")
    description: Optional[str] = Field(default=None, description="プロジェクトの説明")
    cwd: Optional[Path] = Field(default=None, description="作業ディレクトリ")
    environments: dict[str, str] = Field(
        default_factory=dict, description="セッションスコープの環境変数"
    )
    tmux_windows: list[WindowConfig] = Field(
        default_factory=list, description="tmuxウィンドウリスト"
    )

    @field_validator("name")
    @classmethod
    def validate_project_name(cls, v: str) -> str:
        """tmux互換の命名規則を検証."""
        # tmuxセッション名で使用不可な文字
        invalid_chars = [".", ":"]
        for char in invalid_chars:
            if char in v:
                raise ValueError(f'project name cannot contain "{char}"')
        return v

    @field_validator("cwd", mode="before")
    @classmethod
    def normalize_cwd(cls, v: str | Path | None) -> Path | None:
        """cwd を絶対パスに正規化（~ 展開、resolve）."""
        if v is None:
            return None
        path = Path(v).expanduser()
        return path.resolve(strict=False)

    @field_validator("environments")
    @classmethod
    def validate_environments(cls, v: dict[str, str]) -> dict[str, str]:
        """環境変数名の最小バリデーション."""
        for key in v:
            if not key:
                raise ValueError("environment variable name cannot be empty")
            if not key.replace("_", "").isalnum():
                raise ValueError(
                    f'environment variable name "{key}" contains invalid characters'
                )
        return v

    @model_serializer(mode="wrap")
    def _serialize(self, serializer: Any) -> dict[str, Any]:
        """空の environments は JSON 出力から除外（後方互換）."""
        data = serializer(self)
        if not data.get("environments"):
            data.pop("environments", None)
        return data

    @field_validator("tmux_windows")
    @classmethod
    def validate_unique_windows(
        cls, v: list[WindowConfig]
    ) -> list[WindowConfig]:
        """ウィンドウ名の重複チェック."""
        names = [w.name for w in v]
        if len(names) != len(set(names)):
            raise ValueError("window names must be unique")
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
