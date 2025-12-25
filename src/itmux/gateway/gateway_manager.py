"""Gateway情報の永続化管理."""

import json
from pathlib import Path
from typing import Optional


class GatewayManager:
    """tmux Control Mode接続のGateway情報を管理するクラス.

    Gateway情報（connection_id、session_name等）をJSON形式で永続化します。
    """

    def __init__(self, gateway_path: Optional[Path] = None):
        """Initialize GatewayManager.

        Args:
            gateway_path: Gateway情報ファイルのパス（デフォルト: ~/.itmux/gateway.json）
        """
        self.gateway_path = gateway_path or (Path.home() / ".itmux" / "gateway.json")

    def load(self, project_name: str) -> Optional[dict]:
        """プロジェクトのGateway情報を読み込み.

        Args:
            project_name: プロジェクト名

        Returns:
            Gateway情報の辞書、存在しない場合はNone
        """
        if not self.gateway_path.exists():
            return None

        data = json.loads(self.gateway_path.read_text())
        projects = data.get("projects", {})
        return projects.get(project_name)

    def save(self, project_name: str, info: dict) -> None:
        """プロジェクトのGateway情報を保存.

        Args:
            project_name: プロジェクト名
            info: 保存するGateway情報
        """
        self.gateway_path.parent.mkdir(parents=True, exist_ok=True)

        # 既存データを読み込み
        if self.gateway_path.exists():
            data = json.loads(self.gateway_path.read_text())
        else:
            data = {"projects": {}}

        # プロジェクト情報を更新
        if "projects" not in data:
            data["projects"] = {}
        data["projects"][project_name] = info

        self.gateway_path.write_text(json.dumps(data, indent=2) + "\n")

    def clear(self, project_name: str) -> None:
        """プロジェクトのGateway情報をクリア.

        Args:
            project_name: プロジェクト名
        """
        if not self.gateway_path.exists():
            return

        data = json.loads(self.gateway_path.read_text())
        if "projects" in data and project_name in data["projects"]:
            del data["projects"][project_name]
            self.gateway_path.write_text(json.dumps(data, indent=2) + "\n")
