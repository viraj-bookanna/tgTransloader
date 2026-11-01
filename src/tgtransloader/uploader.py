from __future__ import annotations

import os

from telethon import TelegramClient

from tgtransloader import fasttelethon
from tgtransloader.config import Config
from tgtransloader.media import ThumbnailGenerator, is_video
from tgtransloader.utils import TimeKeeper, humanify, progress_bar

FAST_TRANSFER_THRESHOLD = 10 * 1024 * 1024


class Uploader:
    """Uploads a local file via a TelegramClient with progress reporting."""

    def __init__(self, bot: TelegramClient, config: Config, thumb_gen: ThumbnailGenerator):
        self.bot = bot
        self.config = config
        self.thumb_gen = thumb_gen

    async def send_file(
        self,
        chat,
        msg,
        upload_file_path: str,
        upload_file_name: str,
        caption: str,
        force_document: bool = False,
        title: str = "",
    ) -> None:
        os.makedirs(self.config.temp_dir, exist_ok=True)
        tk = TimeKeeper()
        file_size = os.path.getsize(upload_file_path)
        use_fast = file_size > FAST_TRANSFER_THRESHOLD
        label = "Uploading (fast)" if use_fast else "Uploading"

        async def on_progress(current, total):
            if total:
                pct = current / total * 100
                if tk.should_edit(pct):
                    await msg.edit(
                        f"{title}\n**{label}**: {progress_bar(pct)}\n"
                        f"**File Name**: {upload_file_name}\n"
                        f"**Size**: {humanify(total)}\n"
                        f"**Uploaded**: {humanify(current)}"
                    )

        if use_fast:
            with open(upload_file_path, "rb") as fh:
                file = await fasttelethon.upload_file(
                    self.bot, fh, progress_callback=on_progress
                )
        else:
            file = await self.bot.upload_file(
                upload_file_path, progress_callback=on_progress
            )

        thumb_path = ""
        try:
            if is_video(upload_file_path):
                thumb_path = os.path.join(
                    self.config.temp_dir,
                    os.path.basename(upload_file_path) + ".jpg",
                )
                self.thumb_gen.single_frame(upload_file_path, thumb_path)
        except Exception as e:
            print(repr(e))

        try:
            if force_document:
                await self.bot.send_file(
                    chat,
                    file=file,
                    caption=caption,
                    force_document=True,
                    link_preview=False,
                )
            else:
                await self.bot.send_file(
                    chat,
                    file=file,
                    thumb=thumb_path if os.path.isfile(thumb_path) else None,
                    caption=caption,
                    supports_streaming=True,
                    link_preview=False,
                )
        finally:
            if thumb_path and os.path.isfile(thumb_path):
                os.unlink(thumb_path)
