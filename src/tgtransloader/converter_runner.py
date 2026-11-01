"""Subprocess entry point used by :class:`FFmpegRunner`.

Runs ffmpeg, logs stderr to a file, then removes the file to signal completion.
Executed as ``python -m tgtransloader.converter_runner``.
"""
from __future__ import annotations

import os
import platform
import shlex
import sys
import time

from dotenv import load_dotenv


def main() -> None:
    load_dotenv(override=True)
    ffmpeg = os.getenv("FFMPEG_PATH", "ffmpeg")
    in_path = sys.argv[1]
    out_path = sys.argv[2]
    log_path = sys.argv[3]
    codec = " -c copy" if sys.argv[4] == "1" else ""

    redir_fmt = "1>NUL 2>{}" if platform.system() == "Windows" else "1> {} 2>&1"
    redir = redir_fmt.format(shlex.quote(log_path))
    cmd = f"{ffmpeg} -i {shlex.quote(in_path)}{codec} {shlex.quote(out_path)} {redir}"
    os.system(cmd)
    time.sleep(3)
    try:
        os.remove(log_path)
    except FileNotFoundError:
        pass


if __name__ == "__main__":
    main()
