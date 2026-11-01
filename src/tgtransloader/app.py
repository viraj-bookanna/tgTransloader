from __future__ import annotations

import logging
import os
from pathlib import Path

from telethon import TelegramClient

from tgtransloader.config import Config
from tgtransloader.db import KeyValueStore
from tgtransloader.downloader import Downloader
from tgtransloader.extractor import Extractor
from tgtransloader.ffmpeg_runner import FFmpegRunner
from tgtransloader.handlers import Handlers
from tgtransloader.media import ThumbnailGenerator
from tgtransloader.plugin_api import PluginManager
from tgtransloader.ui import UIBuilder
from tgtransloader.uploader import Uploader


class TransloaderBot:
    """Composition root for the Telegram transloader bot."""

    def __init__(self, config: Config):
        self.config = config
        self.bot = TelegramClient(
            "bot", config.api_id, config.api_hash
        ).start(bot_token=config.bot_token)

        self.db = KeyValueStore(config.db_path)
        self.plugins = PluginManager(config.plugins_dir, self.db)
        self.plugins.load()

        self.extractor = Extractor(config.unrar_path)
        self.thumb_gen = ThumbnailGenerator(config.ffmpeg_path, str(config.thumb_dir))
        self.downloader = Downloader(config, self.plugins)
        self.ui = UIBuilder(self.db, config.base_dir, self.plugins)
        self.uploader = Uploader(self.bot, config, self.thumb_gen)
        self.ffmpeg = FFmpegRunner(config, self.ui.unugly_path)

        self.handlers = Handlers(self)
        self.handlers.register()

    def run(self) -> None:
        for d in (self.config.base_dir, self.config.temp_dir, self.config.log_dir, self.config.thumb_dir):
            os.makedirs(d, exist_ok=True)
        with self.bot:
            self.bot.run_until_disconnected()


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOGLEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    project_root = Path(os.getcwd())
    config = Config.from_env(project_root)
    TransloaderBot(config).run()


if __name__ == "__main__":
    main()
