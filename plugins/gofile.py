"""GoFile download plugin.

Matches ``https://gofile.io/d/<contentId>`` style URLs, obtains a guest
account token, generates the website token by running the bundled
``gofile_wt.mjs`` with Node, then streams each child file asynchronously
into ``ctx.download_dir`` under its *original filename*.

Set the environment variable ``GOFILE_TOKEN`` to use an owner token
instead of a disposable guest account.
"""
from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path

import aiofiles
import aiohttp

from tgtransloader.plugin_api import BasePlugin, PluginContext
from tgtransloader.utils import (
    TimeKeeper,
    humanify,
    progress_bar,
    seconds_to_human_time,
)

API = "https://api.gofile.io"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
WT_SCRIPT = Path(__file__).with_name("gofile_wt.mjs")


class GofilePlugin(BasePlugin):
    name = "gofile"
    description = "Downloads files from gofile.io, preserving original filenames."
    url_patterns = [
        r"https?://(?:www\.)?gofile\.io/d/(?P<content_id>[A-Za-z0-9]+)",
        r"https?://(?:www\.)?gofile\.io/\?c=(?P<content_id2>[A-Za-z0-9]+)",
    ]

    _ID_RE = re.compile(r"gofile\.io/(?:d/|\?c=)(?P<content_id>[A-Za-z0-9]+)")

    def _extract_content_id(self, url: str) -> str:
        m = self._ID_RE.search(url)
        if not m:
            raise ValueError(f"not a gofile url: {url}")
        return m.group("content_id")

    async def _generate_wt(self, token: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "node", str(WT_SCRIPT), token,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"gofile_wt.mjs failed ({proc.returncode}): {err.decode(errors='replace')}"
            )
        return out.decode().strip()

    async def _get_guest_token(self, session: aiohttp.ClientSession) -> str:
        async with session.post(f"{API}/accounts", json={}) as r:
            body = await r.json()
        token = body.get("data", {}).get("token")
        if not token:
            raise RuntimeError(f"gofile: unable to obtain guest token: {body}")
        return token

    async def _fetch_contents(
        self,
        session: aiohttp.ClientSession,
        content_id: str,
        token: str,
        wt: str,
    ) -> list[dict]:
        async with session.get(
            f"{API}/contents/{content_id}?pageSize=100",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Website-Token": wt,
                "X-BL": "en-US",
            },
            timeout=aiohttp.ClientTimeout(total=60),
        ) as r:
            body = await r.json()
        if body.get("status") != "ok":
            raise RuntimeError(f"gofile api error: {body}")
        children = body["data"].get("children", {})
        items = list(children.values()) if isinstance(children, dict) else list(children)
        if not items:
            raise RuntimeError(f"gofile: no files in content {content_id}")
        return items

    async def _stream_item(
        self,
        session: aiohttp.ClientSession,
        item: dict,
        token: str,
        event,
        dest: Path,
    ) -> None:
        link = item.get("link") or item.get("directLink")
        if not link:
            raise RuntimeError(f"gofile: no direct link on item {item.get('name')}")
        name = dest.name
        total = int(item.get("size") or 0) or None
        tk = TimeKeeper()
        start_time = time.time()
        current = 0
        headers = {"Cookie": f"accountToken={token}"}
        timeout = aiohttp.ClientTimeout(total=60 * 60)
        async with session.get(link, headers=headers, timeout=timeout) as resp:
            ctype = resp.headers.get("Content-Type", "")
            if "text/html" in ctype:
                raise RuntimeError(f"gofile: download blocked (HTML) for {name}")
            async with aiofiles.open(dest, "wb") as f:
                async for chunk in resp.content.iter_chunked(1024 * 1024):
                    await f.write(chunk)
                    current += len(chunk)
                    if total:
                        pct = current / total * 100
                        if tk.should_edit(pct):
                            await event.edit(
                                f"**Downloading** (gofile): {progress_bar(pct)}\n"
                                f"**File Name**: {name}\n"
                                f"**Size**: {humanify(total)}\n"
                                f"**Downloaded**: {humanify(current)}\n"
                                f"**Elapsed Time**: "
                                f"{seconds_to_human_time(time.time() - start_time)}"
                            )

    async def download(self, url: str, event, ctx: PluginContext) -> str:
        content_id = self._extract_content_id(url)
        owner_token = os.environ.get("GOFILE_TOKEN")
        os.makedirs(ctx.download_dir, exist_ok=True)

        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(
            connector=connector, headers={"User-Agent": UA}
        ) as session:
            token = owner_token or await self._get_guest_token(session)
            wt = await self._generate_wt(token)
            items = await self._fetch_contents(session, content_id, token, wt)

            saved_paths: list[Path] = []
            for item in items:
                name = item.get("name") or f"gofile_{content_id}"
                dest = ctx.download_dir / name
                await self._stream_item(session, item, token, event, dest)
                saved_paths.append(dest)

        if not saved_paths:
            raise RuntimeError(f"gofile: nothing downloaded from {url}")
        return str(saved_paths[0])
