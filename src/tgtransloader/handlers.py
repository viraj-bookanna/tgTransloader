from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from telethon import Button, events

from tgtransloader import fasttelethon
from tgtransloader.media import is_video
from tgtransloader.ui import MAIN_KEYBTN, find_all_urls, goto
from tgtransloader.uploader import FAST_TRANSFER_THRESHOLD
from tgtransloader.utils import (
    TimeKeeper,
    dir_files,
    dir_tree,
    file_name_hash,
    gen_hash_list,
    guess_icon,
    humanify,
    progress_bar,
)
from tgtransloader.vconvert import ServerConverter

if TYPE_CHECKING:
    from tgtransloader.app import TransloaderBot


class Handlers:
    """Telethon event handlers; owns all top-level bot behavior."""

    def __init__(self, app: "TransloaderBot"):
        self.app = app

    # ------------------------------------------------------------------ setup

    def register(self) -> None:
        bot = self.app.bot
        bot.add_event_handler(self.on_media, events.NewMessage(outgoing=False))
        bot.add_event_handler(self.on_link, events.NewMessage(pattern="^[^/]"))
        bot.add_event_handler(self.on_extract_cmd, events.NewMessage(pattern="/ex"))
        bot.add_event_handler(self.on_rename_cmd, events.NewMessage(pattern="/rn"))
        bot.add_event_handler(self.on_files_cmd, events.NewMessage(pattern="/files"))
        bot.add_event_handler(self.on_plugins_cmd, events.NewMessage(pattern="/plugins"))
        bot.add_event_handler(self.on_callback, events.CallbackQuery())

    # ---------------------------------------------------------------- helpers

    @property
    def base_dir(self) -> Path:
        return self.app.config.base_dir

    def _ensure_dirs(self) -> None:
        for d in (self.base_dir, self.app.config.temp_dir):
            os.makedirs(d, exist_ok=True)

    # ----------------------------------------------------------- message hooks

    async def on_media(self, event):
        self._ensure_dirs()
        if not event.message.file:
            return
        tk = TimeKeeper()
        msg = await event.respond("wait..")
        fname = event.message.file.name or "file"
        file_size = event.message.file.size or 0
        document = getattr(event.message, "document", None)
        use_fast = document is not None and file_size > FAST_TRANSFER_THRESHOLD
        label = "Downloading (fast)" if use_fast else "Downloading"

        async def on_progress(current, total):
            if total:
                pct = current / total * 100
                if tk.should_edit(pct):
                    await msg.edit(
                        f"**{label}**: {progress_bar(pct)}\n"
                        f"**File Name**: {fname}\n"
                        f"**Size**: {humanify(total)}\n"
                        f"**Downloaded**: {humanify(current)}"
                    )

        if use_fast:
            dest = os.path.join(str(self.app.config.temp_dir), fname)
            with open(dest, "wb") as out:
                await fasttelethon.download_file(
                    self.app.bot, document, out, progress_callback=on_progress
                )
            file = dest
        else:
            file = await event.message.download_media(
                str(self.app.config.temp_dir), progress_callback=on_progress
            )
        filename = os.path.basename(file)
        shutil.move(file, os.path.join(str(self.base_dir), filename))
        await msg.edit(
            "file download complete \u2705",
            buttons=[goto("file", filename), MAIN_KEYBTN],
        )
        raise events.StopPropagation

    async def on_link(self, event):
        try:
            urls = find_all_urls(event.message)
            if not urls:
                return
            msg = await event.respond("wait...")
            for url in urls:
                clean = url.replace("_____", "")
                resumable = not (
                    event.message.text.startswith(".d") or "_____" in url
                )
                dest = await self.app.downloader.dispatch(
                    clean, msg, resumable=resumable, download_dir=self.base_dir
                )
                fname = os.path.basename(dest)
                await msg.edit(
                    f"file {fname} downloaded successful!",
                    buttons=[goto("file", fname), MAIN_KEYBTN],
                )
        except Exception as e:
            await event.respond(f"Error: {e}")
        raise events.StopPropagation

    async def on_extract_cmd(self, event):
        files = dir_files(str(self.base_dir))
        try:
            msg = await event.respond("extracting..")
            cmd = event.message.text.split(" ", 2)
            if cmd[1] not in files:
                await msg.edit("\U0001f643 unrecognized command")
                return
            sel_file_path = os.path.join(str(self.base_dir), files[cmd[1]])
            if not os.path.isfile(sel_file_path):
                await msg.edit("\U0001f50d target file doesn't exist")
                return
            expath = os.path.join(str(self.base_dir), cmd[1])
            self.app.db.put(cmd[1], files[cmd[1]].rsplit(".", 1)[0])
            if os.path.isdir(expath):
                await msg.edit(
                    "destination already exists",
                    buttons=[goto("dirpage", cmd[1], "switch to folder \U0001f501"), MAIN_KEYBTN],
                )
                return
            os.makedirs(expath)
            password = None if len(cmd) == 2 else cmd[2]
            await asyncio.to_thread(
                self.app.extractor.extract, sel_file_path, expath, password
            )
            await self.app.ui.dir_buttons(event, cmd[1], 1, False)
            await msg.delete()
        except Exception as e:
            await event.respond(f"Error: {e}")

    async def on_rename_cmd(self, event):
        try:
            cmd = event.message.text.split(" ", 2)
            cmd2 = cmd[1].split("-")
            if len(cmd2) == 2:
                tree = dir_tree(os.path.join(str(self.base_dir), cmd2[0]))
                target = tree[cmd2[1]][1]
                dest = os.path.join(os.path.dirname(target), cmd[2])
                keyboard = [
                    goto("dirfile", f"{cmd2[0]}-{file_name_hash(dest)}", "Go to file"),
                    goto("dirpage", cmd2[0], f"\u25c0\ufe0f Back to {self.app.db.get(cmd2[0])}"),
                    MAIN_KEYBTN,
                ]
            else:
                files = dir_files(str(self.base_dir))
                target = os.path.join(str(self.base_dir), files[cmd[1]])
                dest = os.path.join(str(self.base_dir), cmd[2])
                keyboard = [goto("file", cmd[2]), MAIN_KEYBTN]
            os.rename(target, dest)
            await event.respond(
                f"file renamed from: {os.path.basename(target)} to: {cmd[2]}",
                buttons=keyboard,
            )
        except Exception as e:
            await event.respond(f"Error: {e}")

    async def on_files_cmd(self, event):
        try:
            await self.app.ui.main_page(self.base_dir, event, 1, False)
        except Exception as e:
            await event.respond(f"Error: {e}")

    async def on_plugins_cmd(self, event):
        try:
            await event.respond(
                "\U0001f50c **Plugins** - tap to enable / disable",
                buttons=self.app.ui.plugins_menu(),
            )
        except Exception as e:
            await event.respond(f"Error: {e}")

    # -------------------------------------------------------------- callbacks

    async def on_callback(self, event):
        try:
            data = event.data.decode("utf-8").split(":", 1)
            action = data[0]
            if action == "noop":
                return
            if action in ("plugintoggle", "pluginreload"):
                return await self._handle_plugin_callback(event, action, data[1])
            await self._handle_file_callback(event, data)
        except Exception as e:
            await event.respond(f"Error: {e}")

    async def _handle_plugin_callback(self, event, action: str, payload: str):
        if action == "plugintoggle":
            new_state = self.app.plugins.toggle(payload)
            marker = "\u2705 enabled" if new_state else "\u274c disabled"
            await event.edit(
                f"\U0001f50c **Plugins** - tap to enable / disable\n`{payload}` {marker}",
                buttons=self.app.ui.plugins_menu(),
            )
        elif action == "pluginreload":
            self.app.plugins.reload()
            await event.edit(
                "\U0001f504 **Plugins** reloaded - tap to enable / disable",
                buttons=self.app.ui.plugins_menu(),
            )

    async def _handle_file_callback(self, event, data: list[str]):
        self._ensure_dirs()
        files = dir_files(str(self.base_dir))
        keyboard = None
        text: str | None = None
        as_new = False

        data2 = data[1].split("-")
        sel_dir = os.path.join(str(self.base_dir), data2[0])
        sel_dir_filename: str
        sel_dir_filepath: str
        if len(data2) > 1 and os.path.isdir(sel_dir):
            tree = dir_tree(sel_dir)
            if data2[1] in tree and os.path.isfile(tree[data2[1]][1]):
                sel_dir_filename = tree[data2[1]][0]
                sel_dir_filepath = tree[data2[1]][1]
            else:
                sel_dir_filename = data2[0]
                sel_dir_filepath = os.path.join(str(self.base_dir), sel_dir_filename)
        elif data2[0] in files:
            sel_dir_filename = files[data2[0]]
            sel_dir_filepath = os.path.join(str(self.base_dir), sel_dir_filename)
        else:
            sel_dir_filename = data2[0]
            sel_dir_filepath = os.path.join(str(self.base_dir), sel_dir_filename)

        action = data[0]

        if action in ("mainpage", "delmainfilepage"):
            if action.startswith("del"):
                sfile = os.path.join(str(self.base_dir), dir_files(str(self.base_dir)).get(data2[0], ""))
                if os.path.isfile(sfile):
                    os.remove(sfile)
                elif os.path.isdir(sfile):
                    await asyncio.to_thread(shutil.rmtree, sfile)
                data2[0] = data2[1]
            await self.app.ui.main_page(self.base_dir, event, data2[0])
            return

        if action in ("dirpage", "deldirfilepage"):
            if action.startswith("del") and os.path.isfile(sel_dir_filepath):
                os.remove(sel_dir_filepath)
                data2[1] = data2[2]
            await self.app.ui.dir_buttons(event, data2[0], data2[1])
            return

        if action == "mvdirfile":
            if os.path.isfile(sel_dir_filepath):
                shutil.move(sel_dir_filepath, str(self.base_dir))
            keyboard = [goto("file", sel_dir_filename)]
            text = f"file: {self.app.ui.unugly_path(sel_dir_filepath)} moved to main"

        elif action in ("filetomp4", "dirfiletomp4"):
            keyboard = [
                [Button.inline("\U0001f40c Normal convert (slow)", data=f"{action}c:{data[1]}")],
                [Button.inline("\u26a1 Codec copy (fast)", data=f"{action}copy:{data[1]}")],
                [Button.inline("\u2601\ufe0f Server convert (fast)", data=f"{action}srv:{data[1]}")],
            ]
            if "dirfile" in action:
                keyboard.append(goto("dirfile", data[1], "\u25c0\ufe0f Back"))
            else:
                keyboard.append(goto("file", sel_dir_filename, "\u25c0\ufe0f Back"))
            text = f"file: {sel_dir_filename}\n\nconversion options:"

        elif action.startswith(("filetomp4", "dirfiletomp4")):
            await event.edit("wait..")
            if action.endswith("srv"):
                sconv = ServerConverter(sel_dir_filepath)
                tk1 = TimeKeeper()
                tk2 = TimeKeeper()

                async def ucb(c, t):
                    if t and tk1.should_edit(c / t * 100):
                        await event.edit(
                            f"**Upload**: {progress_bar(c / t * 100)}\n"
                            f"**File**: {sel_dir_filepath}\n"
                            f"**Size**: {humanify(t)}\n**Up**: {humanify(c)}"
                        )

                async def ccb(c, t):
                    if t and tk2.should_edit(c / t * 100):
                        await event.edit(
                            f"**Convert**: {progress_bar(c / t * 100)}\n"
                            f"**File**: {sel_dir_filepath}"
                        )

                link = await sconv.convert_in_server(ucb, ccb)
                await self.app.downloader.dispatch(
                    link,
                    event,
                    resumable=False,
                    custom_filename=f"{os.path.basename(sel_dir_filepath)}.mp4",
                    download_dir=Path(os.path.dirname(sel_dir_filepath)),
                )
            else:
                await self.app.ffmpeg.convert(
                    sel_dir_filepath,
                    f"{sel_dir_filepath}.mp4",
                    event,
                    "copy" in action,
                )
            os.remove(sel_dir_filepath)
            keyboard = []
            text = f"conversion complete!\noutput file: {sel_dir_filename}.mp4"

        elif action in ("uploadfile", "uploadfiledoc", "uploaddirfile", "uploaddirfiledoc"):
            await event.edit("wait..")
            await self.app.uploader.send_file(
                event.chat,
                event,
                sel_dir_filepath,
                sel_dir_filepath,
                self.app.ui.unugly_path(sel_dir_filename),
                "doc" in action,
            )
            keyboard = []
            text = f"file {sel_dir_filename} uploaded \u2705"

        elif action in ("renamefile", "renamedirfile"):
            keyboard = []
            if "dirfile" in action:
                keyboard.append(goto("dirfile", data[1], "\u25c0\ufe0f Back"))
            else:
                keyboard.append(goto("file", sel_dir_filename, "\u25c0\ufe0f Back"))
            text = (
                f"file: `{sel_dir_filename}`\n"
                f"use following command to rename\n\n`/rn {data[1]} new_name`"
            )

        elif action == "extract":
            keyboard = [goto("file", sel_dir_filename, "\u25c0\ufe0f Back")]
            text = (
                f"file: `{sel_dir_filename}`\n"
                f"use following command to extract\n\n"
                f"without password:`/ex {data[1]}`\n"
                f"with password:`/ex {data[1]} passwd`"
            )

        elif action in ("delfile", "deldirfile"):
            kind = "file"
            if os.path.isdir(sel_dir_filepath):
                await asyncio.to_thread(shutil.rmtree, sel_dir_filepath)
                kind = "folder"
                sel_dir_filename = self.app.db.get(sel_dir_filename) or sel_dir_filename
            elif os.path.isfile(sel_dir_filepath):
                os.remove(sel_dir_filepath)
            keyboard = []
            text = f"{kind}: {self.app.ui.unugly_path(sel_dir_filepath)} deleted"

        elif action in ("filegenthumbs", "dirfilegenthumbs"):
            await event.edit("wait..")
            thumb = await asyncio.to_thread(
                self.app.thumb_gen.composite, sel_dir_filepath
            )
            await event.respond(sel_dir_filename, file=thumb)
            as_new = True
            keyboard = []
            text = "thumbnail generated successfully"

        elif action in ("file", "dirfile"):
            keyboard = [
                [Button.inline("Upload \U0001f4e4", data=f"upload{action}:{data[1]}")],
            ]
            if is_video(sel_dir_filepath, False):
                if sel_dir_filepath.lower().endswith((".mp4", ".mkv")):
                    keyboard.append(
                        [Button.inline("Generate thumbnails \U0001f3a9", data=f"{action}genthumbs:{data[1]}")]
                    )
                else:
                    keyboard.append(
                        [Button.inline("Convert to .mp4 \u267b\ufe0f", data=f"{action}tomp4:{data[1]}")]
                    )
                keyboard.append(
                    [Button.inline("Upload as document \U0001f4ce", data=f"upload{action}doc:{data[1]}")]
                )
            if action == "file" and sel_dir_filename.lower().endswith(
                (".zip", ".rar", ".7z", ".7z.001", ".7z.0001")
            ):
                keyboard.append([Button.inline("Extract \U0001f510", data=f"extract:{data[1]}")])
            keyboard.append([Button.inline("rename \u270d\ufe0f", data=f"rename{action}:{data[1]}")])
            keyboard.append([Button.inline("delete \u274c", data=f"del{action}:{data[1]}")])
            if action == "dirfile":
                keyboard.append([Button.inline("move to main \U0001f4d1", data=f"mvdirfile:{data[1]}")])
            text = (
                f"{guess_icon(sel_dir_filepath)} file: "
                f"{self.app.ui.unugly_path(sel_dir_filepath)}\n"
                f"size: {humanify(os.path.getsize(sel_dir_filepath))}"
            )

        elif action == "deleteall":
            keyboard = [
                [
                    Button.inline("\u2705 Yes", data=b"deleteallyes:deleteallyes"),
                    Button.inline("\u274c No", data=b"main:main"),
                ]
            ]
            text = "\u26a0\ufe0f ARE YOU SURE?"

        elif action == "deleteallyes":
            await asyncio.to_thread(shutil.rmtree, str(self.base_dir))
            text = "\U0001f6ab ALL FILES DELETED!"

        elif "uploadall" in action:
            await event.edit("wait..")
            if action == "uploadall":
                tree = gen_hash_list(
                    {
                        item.name: os.path.join(str(self.base_dir), item.name)
                        for item in os.scandir(str(self.base_dir))
                        if item.is_file()
                    }
                )
            elif action == "uploadalldir":
                tree = dir_tree(sel_dir_filepath)
            else:
                tree = dir_tree(str(self.base_dir))
            total = len(tree)
            current = 0
            for entry in tree.values():
                current += 1
                pbar_total = "**Total**: " + progress_bar(current / total * 100)
                await self.app.uploader.send_file(
                    event.chat,
                    event,
                    entry[1],
                    entry[1],
                    self.app.ui.unugly_path(entry[0]),
                    False,
                    pbar_total,
                )
            as_new = True
            text = "all files uploaded \u2705"

        if text is None:
            return
        if keyboard is not None:
            if "dirfile" in action:
                keyboard.append(goto("dirpage", data2[0], f"\u25c0\ufe0f Back to {self.app.db.get(data2[0])}"))
            keyboard.append(MAIN_KEYBTN)
        if as_new:
            await event.delete()
            await event.respond(text, buttons=keyboard)
        else:
            await event.edit(text, buttons=keyboard)
