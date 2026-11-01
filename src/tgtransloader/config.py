from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    api_id: int
    api_hash: str
    bot_token: str
    base_dir: Path
    temp_dir: Path
    log_dir: Path
    thumb_dir: Path
    plugins_dir: Path
    db_path: Path
    download_timeout_minutes: int
    ffmpeg_path: str
    unrar_path: str
    is_windows: bool

    @classmethod
    def from_env(cls, project_root: Path | None = None) -> "Config":
        load_dotenv(override=True)
        root = project_root or Path.cwd()
        base_dir = Path(os.environ["BASE_DIR"])
        plugins_dir = Path(os.getenv("PLUGINS_DIR") or (root / "plugins"))
        return cls(
            api_id=int(os.environ["API_ID"]),
            api_hash=os.environ["API_HASH"],
            bot_token=os.environ["BOT_TOKEN"],
            base_dir=base_dir,
            temp_dir=root / "temp",
            log_dir=root / "logs",
            thumb_dir=root / "thumbs",
            plugins_dir=plugins_dir,
            db_path=root / "database.db",
            download_timeout_minutes=int(os.getenv("DOWNLOAD_TIMEOUT_MINUTES", "60")),
            ffmpeg_path=os.getenv("FFMPEG_PATH", "ffmpeg"),
            unrar_path=os.getenv("UNRAR_PATH", ""),
            is_windows=platform.system() == "Windows",
        )
