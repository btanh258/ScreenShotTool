"""Check GitHub for a newer release.

Kept separate from the application module so it can be tested without Tk, and so
the network call is a single, easy-to-stub function. The app itself is a tray
utility that may run for days, which is why this is opt-in from the menu rather
than a request at startup: a silent outbound connection on every launch is
something a local screenshot tool should not do without being asked.
"""
import json
import logging
import threading
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

RELEASES_API = "https://api.github.com/repos/btanh258/ScreenShotTool/releases/latest"
TIMEOUT_SECONDS = 8
USER_AGENT = "ScreenShotTool-update-check"


def parse_version(text):
    """Turn "v1.2.3" or "1.2.3" into a comparable tuple; None if unparseable."""
    if not isinstance(text, str):
        return None
    cleaned = text.strip().lstrip("vV")
    if not cleaned:
        return None
    parts = []
    for chunk in cleaned.split("."):
        # Keep only the leading digits so "3-beta" still compares as 3.
        digits = ""
        for char in chunk:
            if char.isdigit():
                digits += char
            else:
                break
        if not digits:
            return None
        parts.append(int(digits))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer(latest, current):
    """True when ``latest`` is a higher version than ``current``."""
    parsed_latest = parse_version(latest)
    parsed_current = parse_version(current)
    if parsed_latest is None or parsed_current is None:
        return False
    return parsed_latest > parsed_current


def fetch_latest_release(timeout=TIMEOUT_SECONDS):
    """Return the newest release's metadata, or None when it cannot be read.

    Every failure mode (offline, rate limited, malformed JSON, a repository that
    moved) resolves to None: an update check must never be the reason the app
    shows an error or crashes.
    """
    request = urllib.request.Request(
        RELEASES_API,
        headers={"User-Agent": USER_AGENT,
                 "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError,
            ValueError, json.JSONDecodeError) as exc:
        log.info("Update check failed: %s", exc)
        return None
    if not isinstance(payload, dict):
        return None
    return {
        "tag": payload.get("tag_name") or "",
        "url": payload.get("html_url") or "",
        "notes": payload.get("body") or "",
        "name": payload.get("name") or "",
    }


def check_async(current_version, callback):
    """Run the check on a worker thread and hand the result to ``callback``.

    ``callback`` receives (release_or_None, current_version) and is expected to
    marshal itself back onto the UI thread.
    """
    def run():
        release = fetch_latest_release()
        try:
            callback(release, current_version)
        except Exception:
            log.exception("Update check callback failed")

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    return worker
