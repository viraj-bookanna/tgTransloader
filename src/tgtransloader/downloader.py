from __future__ import annotations

import hashlib
import os
import re
import shutil
import time
import urllib.parse
from pathlib import Path

import aiofiles
import aiohttp
from bs4 import BeautifulSoup

from tgtransloader.config import Config
from tgtransloader.plugin_api import PluginContext, PluginManager
from tgtransloader.utils import (
    TimeKeeper,
    humanify,
    progress_bar,
    seconds_to_human_time,
)


def _parse_header(header: str) -> tuple[str, dict[str, str]]:
    parts = header.split(";", 1)
    if len(parts) == 1:
        return parts[0].strip(), {}
    params = [p.split("=") for p in parts[1].split(";")]
    return parts[0].strip(), {kv[0].strip(): kv[1].strip('" ') for kv in params}


class Downloader:
    """Default URL downloader with plugin dispatch and optional speeddl mirror."""

    DEFAULT_HEADERS = {
        "accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/webp,image/apng,*/*;q=0.8,"
            "application/signed-exchange;v=b3;q=0.7"
        ),
        "accept-language": "en-US,en;q=0.9",
        "sec-ch-ua": (
            '"Microsoft Edge";v="117", "Not;A=Brand";v="8", "Chromium";v="117"'
        ),
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
    }

    def __init__(self, config: Config, plugins: PluginManager):
        self.config = config
        self.plugins = plugins

    async def dispatch(
        self,
        url: str,
        event,
        *,
        resumable: bool = True,
        custom_filename: str | None = None,
        download_dir: Path | None = None,
    ) -> str:
        """Route ``url`` through a matching plugin or the default downloader."""
        target_dir = download_dir or self.config.base_dir
        os.makedirs(target_dir, exist_ok=True)
        plugin = self.plugins.find_matching(url)
        if plugin is not None:
            ctx = PluginContext(config=self.config, download_dir=Path(target_dir))
            return await plugin.download(url, event, ctx)
        return await self._default_download(
            url, event, resumable, custom_filename, Path(target_dir)
        )

    async def _default_download(
        self,
        url: str,
        event,
        resumable: bool,
        custom_filename: str | None,
        download_dir: Path,
    ) -> str:
        os.makedirs(self.config.temp_dir, exist_ok=True)
        timeout = aiohttp.ClientTimeout(total=60 * self.config.download_timeout_minutes)
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False), timeout=timeout
        ) as session:
            return await self._fetch(
                session, url, event, resumable, custom_filename, download_dir
            )

    async def _fetch(
        self,
        session: aiohttp.ClientSession,
        url: str,
        event,
        resumable: bool,
        custom_filename: str | None,
        download_dir: Path,
    ) -> str:
        if re.match(r"https?://(www\.)?upload\.ee", url):
            async with session.get(url) as r:
                html = await r.text()
            tag = BeautifulSoup(html, "html.parser").find("a", attrs={"id": "d_l"})
            if tag is None or not tag.get("href"):
                raise RuntimeError("upload.ee: download link not found")
            url = tag["href"]

        parsed = urllib.parse.urlparse(url)
        file_org_name = urllib.parse.unquote(os.path.basename(parsed.path))
        if not file_org_name:
            file_org_name = hashlib.md5(url.encode()).hexdigest()
        headers = dict(self.DEFAULT_HEADERS)
        headers["referer"] = f"{parsed.scheme}://{parsed.netloc}/"

        if resumable:
            info = await session.head(url, headers=headers)
            speed_url = (
                "https://speeddl.honar.workers.dev/?durl="
                + urllib.parse.quote(url, safe="")
            )
            speed_info = await session.head(speed_url)
            total_a = int(info.headers.get("content-length", 0)) or None
            total_b = int(speed_info.headers.get("content-length", 0)) or None
            if total_a == total_b:
                url = speed_url

        tk = TimeKeeper()
        current = 0
        start_time = time.time()
        async with session.get(url, headers=headers) as response:
            server_filename = _parse_header(
                response.headers.get("content-disposition", "")
            )[1].get("filename")
            total = int(response.headers.get("content-length", 0)) or None
            if custom_filename is not None:
                file_org_name = custom_filename
            elif server_filename:
                file_org_name = server_filename
            if len(file_org_name) > 250:
                file_org_name = hashlib.md5(file_org_name.encode()).hexdigest()

            temp_path = self.config.temp_dir / file_org_name
            async with aiofiles.open(temp_path, "wb") as f:
                async for chunk in response.content.iter_chunked(1024):
                    await f.write(chunk)
                    current += len(chunk)
                    if total:
                        pct = current / total * 100
                        if tk.should_edit(pct):
                            await event.edit(
                                f"**Downloading**: {progress_bar(pct)}\n"
                                f"**File Name**: {file_org_name}\n"
                                f"**Size**: {humanify(total)}\n"
                                f"**Downloaded**: {humanify(current)}\n"
                                f"**Elapsed Time**: "
                                f"{seconds_to_human_time(time.time() - start_time)}"
                            )

        final_path = download_dir / file_org_name
        shutil.move(str(temp_path), str(final_path))
        return str(final_path)
