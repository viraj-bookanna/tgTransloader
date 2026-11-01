from __future__ import annotations

import hashlib
import mimetypes
import os
import platform
import shlex
import time
from dataclasses import dataclass, field
from datetime import datetime

try:
    import mslex
except ImportError:
    mslex = None

IS_WIN = platform.system() == "Windows"


def shell_quote(string: str) -> str:
    return mslex.quote(string) if (IS_WIN and mslex) else shlex.quote(string)


def human_time_to_seconds(human_time: str) -> float:
    return (
        datetime.strptime(human_time, "%H:%M:%S.%f") - datetime(1900, 1, 1)
    ).total_seconds()


def seconds_to_human_time(sec: float) -> str:
    sec = int(sec)
    hrs = sec // 3600
    sec %= 3600
    mins = sec // 60
    sec %= 60
    return "%02d:%02d:%02d" % (hrs, mins, sec)


def humanify(byte_size: float | None) -> str:
    if byte_size is None:
        return "?"
    units = ["B", "KB", "MB", "GB", "TB"]
    for i, unit in enumerate(units):
        div = 1024 ** i
        if byte_size / div < 1024 or i == len(units) - 1:
            return f"{byte_size / div:.2f} {unit}"
    return f"{byte_size} B"


def progress_bar(percentage: float, length: int = 10) -> str:
    fill_char = "\u2588"
    empty_char = "\u2592"
    fill = round(length * percentage / 100)
    return f"{fill_char * fill}{empty_char * (length - fill)} {percentage:.2f}%"


def file_name_hash(file_name: str) -> str:
    return hashlib.md5(file_name.encode()).hexdigest()[:16]


def guess_icon(full_path: str) -> str:
    if os.path.isdir(full_path):
        return "\U0001f5c2"  # card index dividers
    lower = full_path.lower()
    if lower.endswith((".zip", ".rar", ".7z", ".7z.001", ".7z.0001")):
        return "\U0001f5dc"  # compression
    mime_type, _ = mimetypes.guess_type(full_path)
    if not mime_type:
        return "\U0001f5c4"  # file cabinet
    if "video/" in mime_type and lower.endswith((".mp4", ".mkv")):
        return "\U0001f39e\u25b6\ufe0f"
    if "video/" in mime_type or lower.endswith(".3gp"):
        return "\U0001f39e"
    if "audio/" in mime_type:
        return "\U0001f3a7"
    if "image/" in mime_type:
        return "\U0001f5bc"
    return "\U0001f5c4"


def btn_text(txt: str, maxlen: int = 30) -> str:
    return txt if len(txt) < maxlen else txt[: maxlen - 4] + "..."


def gen_hash_list(list_or_dict):
    if isinstance(list_or_dict, list):
        return {file_name_hash(k): k for k in list_or_dict}
    if isinstance(list_or_dict, dict):
        return {
            file_name_hash(list_or_dict[k]): [k, list_or_dict[k]]
            for k in list_or_dict
        }
    raise TypeError(type(list_or_dict))


def dir_files(dir_path: str) -> dict:
    return gen_hash_list(os.listdir(dir_path))


def dir_tree(dir_path: str) -> dict:
    tree = {}
    for root, _dirs, files in os.walk(dir_path):
        for file in files:
            tree[file] = os.path.join(root, file)
    return gen_hash_list(tree)


@dataclass
class TimeKeeper:
    """Rate-limits progress updates to every ~5 s / 2 pct."""

    last_percentage: float = 0.0
    last_edited_time: float = 0.0

    def should_edit(self, percentage: float, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        if self.last_percentage + 2 < percentage and self.last_edited_time + 5 < now:
            self.last_percentage = percentage
            self.last_edited_time = now
            return True
        return False
