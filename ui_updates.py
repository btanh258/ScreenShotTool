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
    release, _reason = fetch_latest_release_detailed(timeout)
    return release


def fetch_latest_release_detailed(timeout=TIMEOUT_SECONDS):
    """Like :func:`fetch_latest_release`, but also says *why* it failed.

    Returns ``(release_or_None, reason)``, where reason is one of "ok",
    "not-found", "rate-limited", "offline" or "error". The caller needs the
    distinction to avoid telling the user to check their network when the real
    cause is a private repository or a missing release.
    """
    request = urllib.request.Request(
        RELEASES_API,
        headers={"User-Agent": USER_AGENT,
                 "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # 404 is what GitHub returns for a private repository when the request
        # carries no token, and for a repository that has no release yet.
        if exc.code == 404:
            log.info("Update check: no public release found (404)")
            return None, "not-found"
        if exc.code in (403, 429):
            log.info("Update check rate limited (%s)", exc.code)
            return None, "rate-limited"
        log.info("Update check failed: %s", exc)
        return None, "error"
    except (urllib.error.URLError, OSError) as exc:
        log.info("Update check failed: %s", exc)
        return None, "offline"
    except (ValueError, json.JSONDecodeError) as exc:
        log.info("Update check returned unusable data: %s", exc)
        return None, "error"
    if not isinstance(payload, dict):
        return None, "error"
    return {
        "tag": payload.get("tag_name") or "",
        "url": payload.get("html_url") or "",
        "notes": payload.get("body") or "",
        "name": payload.get("name") or "",
    }, "ok"


def check_async(current_version, callback):
    """Run the check on a worker thread and hand the result to ``callback``.

    ``callback`` receives (release_or_None, current_version) and is expected to
    marshal itself back onto the UI thread. Callbacks that also accept a
    ``reason`` argument get the failure cause ("not-found", "offline",
    "rate-limited", "error") as a third positional argument, so the UI can say
    something truer than "check your network".
    """
    def run():
        release, reason = fetch_latest_release_detailed()
        try:
            try:
                callback(release, current_version, reason)
            except TypeError:
                # Older single-purpose callbacks take two arguments.
                callback(release, current_version)
        except Exception:
            log.exception("Update check callback failed")

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    return worker
