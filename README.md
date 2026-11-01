# tgTransloader

Telegram bot that transloads, converts, extracts, and manages files, with a
pluggable per-site downloader system.

## Install (with `uv`)

```bash
uv sync
cp .env.sample .env   # fill in API_ID, API_HASH, BOT_TOKEN, BASE_DIR
uv run tgtransloader
```

Node.js is required for the bundled gofile plugin
(it runs `plugins/gofile_wt.mjs` under `node`).

### `thumb-gen` fix

The upstream `thumb-gen` package needs a small compatibility patch:

```bash
sed -i 's/from cv2        import cv2/import cv2/' $(uv run python -c "import thumb_gen,os;print(os.path.dirname(thumb_gen.__file__))")/application.py
sed -i 's#font\.getsize(\(.*\))\[0\]#font.getbbox(\1)[2]-font.getbbox(\1)[0]#' $(uv run python -c "import thumb_gen,os;print(os.path.dirname(thumb_gen.__file__))")/application.py
sed -i 's#font\.getsize(\(.*\))\[1\]#font.getbbox(\1)[3]-font.getbbox(\1)[1]#' $(uv run python -c "import thumb_gen,os;print(os.path.dirname(thumb_gen.__file__))")/application.py
```

## Project layout

```
src/tgtransloader/
    app.py              TransloaderBot (composition root) + main()
    config.py           Config (env -> dataclass)
    db.py               KeyValueStore (sqlite)
    downloader.py       Downloader (default + plugin dispatch)
    extractor.py        Extractor (zip/rar/7z/split-7z)
    ffmpeg_runner.py    FFmpegRunner (background ffmpeg + log tail)
    converter_runner.py Subprocess target for ffmpeg
    media.py            is_video / ThumbnailGenerator
    uploader.py         Uploader (Telegram upload + thumbnail)
    ui.py               UIBuilder, keyboards, URL parsing
    handlers.py         Handlers (Telethon event -> methods)
    vconvert.py         ServerConverter (video-converter.com)
    plugin_api/         BasePlugin, PluginContext, PluginManager
plugins/                Drop-in plugin folder (auto-discovered)
    gofile.py           Built-in gofile plugin
    gofile_wt.mjs       Website-token generator used by gofile.py
```

## Bot commands

| Command     | What it does                                   |
|-------------|------------------------------------------------|
| any URL     | downloads via a matching plugin or default dl  |
| any file    | saves the attached file into `BASE_DIR`        |
| `/files`    | opens the file browser                         |
| `/ex HASH`  | extracts an archive (optional password arg)    |
| `/rn OLD NEW` | renames a file                               |
| `/plugins`  | enable / disable / reload plugins              |

## Plugins

A plugin is any `.py` file in `plugins/` (configurable via
`PLUGINS_DIR`) that defines a subclass of `BasePlugin`:

```python
from tgtransloader.plugin_api import BasePlugin, PluginContext

class ExamplePlugin(BasePlugin):
    name = "example"
    description = "Downloads from example.com"
    url_patterns = [r"https?://(?:www\.)?example\.com/.+"]

    async def download(self, url: str, event, ctx: PluginContext) -> str:
        # ctx.config, ctx.download_dir
        # await event.edit("downloading...") to report progress
        ...
        return "/absolute/path/to/downloaded/file"
```

Rules the loader enforces:

- Filename must not start with `_`.
- Each `BasePlugin` subclass is instantiated with no args.
- `name` must be non-empty; it's the key for enable/disable state.
- Enable state persists in `database.db` (`plugin:<name>:enabled`).

When a URL is sent to the bot, the first *enabled* plugin whose
`url_patterns` match handles the download; otherwise the default
downloader is used.

The `/plugins` menu lets you toggle plugins and hot-reload the
folder without restarting the bot.
