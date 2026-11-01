from __future__ import annotations

import os
from pathlib import Path

from telethon import Button
from telethon.tl.types import MessageEntityUrl

from tgtransloader.db import KeyValueStore
from tgtransloader.plugin_api import PluginManager
from tgtransloader.utils import (
    btn_text,
    dir_files,
    dir_tree,
    file_name_hash,
    guess_icon,
)

MAIN_KEYBTN = [Button.inline("\U0001f519 Back to files", data=b"mainpage:1")]


def find_all_urls(message) -> list[str]:
    out: list[str] = []
    if message.entities is None:
        return out
    for entity in message.entities:
        if type(entity) is MessageEntityUrl:
            url = message.text[entity.offset : entity.offset + entity.length]
            if url.startswith(("http://", "https://")):
                out.append(url)
            else:
                out.append("http://" + url)
    return out


def goto(file_or_dir: str, name: str, text: str = "") -> list:
    text = text or f"Go to {file_or_dir}"
    if file_or_dir == "file":
        name = file_name_hash(name)
    elif file_or_dir == "dirpage":
        name = f"{name}-1"
    return [Button.inline(text, data=f"{file_or_dir}:{name}")]


def make_pages(buttons, prefix: str, curr_page: str | int = "1", page_size: int = 6):
    curr_page = int(curr_page)
    pages = [buttons[i : i + page_size] for i in range(0, len(buttons), page_size)]
    if len(pages) < curr_page:
        curr_page = len(pages)
    keyboard = pages[curr_page - 1] if pages else []
    prev_nxt = []
    if curr_page > 1:
        prev_nxt.append(Button.inline("\u23ea prev", data=f"{prefix}{curr_page - 1}"))
    if curr_page < len(pages):
        prev_nxt.append(Button.inline("next \u23e9", data=f"{prefix}{curr_page + 1}"))
    if prev_nxt:
        keyboard.append(prev_nxt)
    return keyboard


class UIBuilder:
    """Builds keyboards and page views for the bot."""

    def __init__(self, db: KeyValueStore, base_dir: Path, plugins: PluginManager):
        self.db = db
        self.base_dir = base_dir
        self.plugins = plugins

    def unugly_path(self, path: str) -> str:
        dirhash = path.replace(str(self.base_dir), "").strip(os.sep).split(os.sep)[0]
        if dirhash:
            return path.replace(dirhash, self.db.get(dirhash, dirhash))
        return path

    async def main_page(self, scan_path, event, page: int | str = 1, edit: bool = True, page_size: int = 6):
        files = dir_files(str(scan_path))
        if not files:
            if edit:
                await event.edit("no files")
            else:
                await event.respond("no files")
            return
        buttons = []
        for fh, fname in files.items():
            fpath = os.path.join(str(self.base_dir), fname)
            text = f"{guess_icon(fpath)} {btn_text(self.db.get(fname, fname))}"
            buttons.append(
                [
                    goto("dirpage" if os.path.isdir(fpath) else "file", fname, text)[0],
                    Button.inline("\u274c", data=f"delmainfilepage:{fh}-{page}"),
                ]
            )
        keyboard = make_pages(buttons, "mainpage:", page)
        keyboard.append([Button.inline("\U0001f4e4 Upload all files \U0001f4e4", data=b"uploadall:uploadall")])
        keyboard.append([Button.inline("\U0001f4e4 Upload all files (subdirs) \U0001f4e4", data=b"uploadallsubdirs:uploadallsubdirs")])
        keyboard.append([Button.inline("\U0001f6ab Delete all \U0001f6ab", data=b"deleteall:deleteall")])
        if edit:
            await event.edit("Select a file:", buttons=keyboard)
        else:
            await event.respond("Select a file:", buttons=keyboard)

    async def dir_buttons(self, event, dirname: str, page: int | str = 1, edit: bool = True):
        tree = dir_tree(os.path.join(str(self.base_dir), dirname))
        buttons = [
            [
                Button.inline(
                    btn_text(guess_icon(entry[1]) + " " + entry[0]),
                    data=f"dirfile:{dirname}-{fh}",
                ),
                Button.inline("\u274c", data=f"deldirfilepage:{dirname}-{fh}-{page}"),
            ]
            for fh, entry in tree.items()
        ]
        keyboard = make_pages(buttons, f"dirpage:{dirname}-", page) if tree else []
        dirhash = file_name_hash(dirname)
        keyboard.append([Button.inline("upload all \U0001f4e4", data=f"uploadalldir:{dirhash}")])
        keyboard.append([Button.inline("delete this folder \U0001f5d1", data=f"delfile:{dirhash}")])
        keyboard.append(MAIN_KEYBTN)
        text = (
            f"\U0001f5c2 folder: {self.db.get(dirname, dirname)}\n"
            f"\U0001f522 file count: {len(tree)}"
        )
        if edit:
            await event.edit(text, buttons=keyboard)
        else:
            await event.respond(text, buttons=keyboard)

    def plugins_menu(self):
        plugins = sorted(self.plugins.all_plugins(), key=lambda p: p.name)
        if not plugins:
            return [
                [Button.inline("\U0001f50c (no plugins loaded)", data=b"noop:noop")],
                [Button.inline("\U0001f504 Reload plugins", data=b"pluginreload:1")],
                MAIN_KEYBTN,
            ]
        buttons = []
        for p in plugins:
            enabled = self.plugins.is_enabled(p.name)
            marker = "\u2705" if enabled else "\u274c"
            label = f"{marker} \U0001f50c {btn_text(p.name)}"
            buttons.append([Button.inline(label, data=f"plugintoggle:{p.name}")])
        buttons.append([Button.inline("\U0001f504 Reload plugins", data=b"pluginreload:1")])
        buttons.append(MAIN_KEYBTN)
        return buttons
