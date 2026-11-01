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


def _hachoir_metadata(file_path: str):
    try:
        parser = createParser(file_path)
    except Exception:
        return None
    if parser is None:
        return None
    try:
        return extractMetadata(parser)
    except Exception:
        return None


def _safe_get(metadata, key, cast=int, default=0):
    try:
        if metadata.has(key):
            value = metadata.get(key)
            if hasattr(value, "total_seconds"):
                return int(value.total_seconds())
            return cast(value)
    except Exception:
        pass
    return default


def probe_video(file_path: str) -> dict | None:
    """Return ``{duration, width, height}`` for videos; None otherwise."""
    metadata = _hachoir_metadata(file_path)
    if metadata is None or "MIME type: video" not in str(metadata):
        return None
    return {
        "duration": _safe_get(metadata, "duration"),
        "width": _safe_get(metadata, "width"),
        "height": _safe_get(metadata, "height"),
    }


def probe_audio(file_path: str) -> dict | None:
    """Return ``{duration, title, performer}`` for audio; None otherwise."""
    metadata = _hachoir_metadata(file_path)
    if metadata is None or "MIME type: audio" not in str(metadata):
        return None
    return {
        "duration": _safe_get(metadata, "duration"),
        "title": _safe_get(metadata, "title", cast=str, default=""),
        "performer": _safe_get(metadata, "author", cast=str, default=""),
    }


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
