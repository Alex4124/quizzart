from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from django.conf import settings


def _latest_static_mtime() -> str:
    newest = 0.0
    for directory in getattr(settings, "STATICFILES_DIRS", []):
        for path in Path(directory).rglob("*"):
            if path.suffix in {".css", ".js"}:
                newest = max(newest, path.stat().st_mtime)
    return str(int(newest))


_cached_static_mtime = lru_cache(maxsize=1)(_latest_static_mtime)


def asset_version(request):
    """Cache-busting suffix for CSS/JS: changes whenever a deploy touches a stylesheet or script."""
    configured = getattr(settings, "ASSET_VERSION", "")
    if configured:
        version = configured
    elif settings.DEBUG:
        version = _latest_static_mtime()
    else:
        version = _cached_static_mtime()
    return {"asset_version": version}
