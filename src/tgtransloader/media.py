from __future__ import annotations

import mimetypes
import os
import subprocess

from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from thumb_gen import Generator

from tgtransloader.utils import seconds_to_human_time


def is_video(file_path: str, use_hachoir: bool = True) -> bool:
    if not use_hachoir:
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is not None:
            return "video/" in mime_type or file_path.lower().endswith(".3gp")
    parser = createParser(file_path)
    if parser:
        metadata = extractMetadata(parser)
        if metadata and "MIME type: video" in str(metadata):
            return True
    return False


class ThumbnailGenerator:
    """Wraps ffmpeg + thumb-gen for single-frame and composite thumbnails."""

    def __init__(self, ffmpeg_path: str, thumb_dir: str):
        self.ffmpeg_path = ffmpeg_path
        self.thumb_dir = thumb_dir

    def single_frame(self, video_path: str, thumbnail_path: str, time_sec: int = 1) -> None:
        subprocess.run(
            [
                self.ffmpeg_path,
                "-ss", seconds_to_human_time(time_sec),
                "-i", video_path,
                "-vframes", "1",
                "-y",
                thumbnail_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

    def composite(self, video_path: str) -> str:
        os.makedirs(self.thumb_dir, exist_ok=True)
        Generator(video_path, output_path=self.thumb_dir, imgCount=16, columns=4).run()
        name = os.path.basename(video_path).rsplit(".", 1)[0] + ".jpg"
        return os.path.join(self.thumb_dir, name)
