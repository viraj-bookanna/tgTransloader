# Plugins

Drop a `.py` file here that defines a `BasePlugin` subclass:

```python
from tgtransloader.plugin_api import BasePlugin, PluginContext

class MyPlugin(BasePlugin):
    name = "my-plugin"
    description = "What this does"
    url_patterns = [r"https?://(?:www\.)?example\.com/.+"]

    async def download(self, url: str, event, ctx: PluginContext) -> str:
        # do the download, edit `event` with progress
        return "/path/to/downloaded/file"
```

- Files starting with `_` are ignored by the loader.
- Auxiliary non-`.py` files (such as `gofile_wt.mjs`) sit next to their
  plugin and are referenced via `Path(__file__).with_name(...)`.
- Use `/plugins` in the bot to enable, disable, or reload plugins.
