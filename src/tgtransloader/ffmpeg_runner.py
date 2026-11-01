from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from tgtransloader.config import Config
from tgtransloader.utils import (
    file_name_hash,
    human_time_to_seconds,
    progress_bar,
    seconds_to_human_time,
    shell_quote,
)


def _parse_status(log_file: str) -> str:
    try:
        with open(log_file, "r") as f:
            content = f.read()
        duration_match = re.search(r"Duration: (.*?), start:", content)
        if duration_match is None:
            return ""
        raw_duration = duration_match.group(1)
        time_matches = re.findall(r"time=(.*?) bitrate", content)
        raw_time = time_matches[-1]
        fraction = human_time_to_seconds(raw_time) / human_time_to_seconds(raw_duration)
        status = (
            f"**Converting**: {progress_bar(fraction * 100)}\n"
            f"**Duration**: {raw_duration}\n**CurrentTime**: {raw_time}"
        )
        return status
    except Exception as e:
        print(repr(e))
        return ""


class FFmpegRunner:
    """Runs ``converter.py`` as a background process and tails its log file."""

    def __init__(self, config: Config, unugly_path):
        self.config = config
        self.unugly_path = unugly_path

    async def convert(self, input_path: str, output_path: str, msg, codec_copy: bool) -> None:
        os.makedirs(self.config.log_dir, exist_ok=True)
        os.makedirs(self.config.temp_dir, exist_ok=True)
        filename = os.path.basename(input_path)
        logfile = os.path.join(
            self.config.log_dir, filename + file_name_hash(input_path) + ".log"
        )
        tmp_output_path = os.path.join(self.config.temp_dir, os.path.basename(output_path))

        converter_cmd = [
            "python" if self.config.is_windows else "python3",
            "-m",
            "tgtransloader.converter_runner",
            shell_quote(input_path),
            shell_quote(tmp_output_path),
            shell_quote(logfile),
            "1" if codec_copy else "0",
        ]
        if self.config.is_windows:
            subprocess.Popen(
                converter_cmd, shell=True, stdin=None, stdout=None, stderr=None, close_fds=True
            )
        else:
            os.system(" ".join(converter_cmd) + " 1> /dev/null 2>&1 & ")

        await asyncio.sleep(10)
        start_time = time.time()
        last = ""
        last_edit_time = 0.0
        while os.path.isfile(logfile):
            status = _parse_status(logfile)
            now = time.time()
            if last_edit_time + 5 < now and last != status:
                elapsed = seconds_to_human_time(now - start_time)
                await msg.edit(
                    f"**File Name**: {self.unugly_path(input_path)}\n"
                    f"{status}\n**Elapsed**: {elapsed}"
                )
                last = status
                last_edit_time = now
            await asyncio.sleep(2)
        shutil.move(tmp_output_path, output_path)
