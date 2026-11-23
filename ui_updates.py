"""Check GitHub for a newer release, and install it.

Kept separate from the application module so it can be tested without Tk, and so
the network call is a single, easy-to-stub function. The app itself is a tray
utility that may run for days, which is why this is opt-in from the menu rather
than a request at startup: a silent outbound connection on every launch is
something a local screenshot tool should not do without being asked.
"""
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile

log = logging.getLogger(__name__)

RELEASES_API = "https://api.github.com/repos/btanh258/ScreenShotTool/releases/latest"
TIMEOUT_SECONDS = 8
# A release binary is ~70 MB, so the download gets its own, much longer budget:
# TIMEOUT_SECONDS is per socket operation and would abort a slow but healthy
# transfer when the user is on a poor connection.
DOWNLOAD_TIMEOUT_SECONDS = 60
USER_AGENT = "ScreenShotTool-update-check"

# Name of the packaged binary inside a release.
UPDATE_ASSET_NAME = "ScreenShotTool.exe"
# Onedir builds ship as a zip named ScreenShotTool-<version>.zip.
UPDATE_ZIP_SUFFIX = ".zip"


def is_onefile_build():
    """True when the running build is the single-file exe.

    A onefile build extracts its libraries to a %TEMP%\\_MEI* folder on every
    launch, so its own folder never holds an ``_internal`` directory; an
    onedir build always has one next to the exe. Running from source counts
    as not-onefile: there is nothing frozen to replace either way.
    """
    if not getattr(sys, "frozen", False):
        return False
    app_dir = os.path.dirname(os.path.abspath(sys.executable))
    return not os.path.isdir(os.path.join(app_dir, "_internal"))


def pick_update_asset(release):
    """Download URL of the update payload for this build, or None.

    Onedir builds take the zip (the whole app folder); onefile builds take
    the exe, which is also the bridge that lets an old onefile install reach
    a release that only ships the zip. Falls back to any asset ending in
    .exe so a renamed binary still updates, and never raises: an unusable
    release just means no in-app update.
    """
    if not is_onefile_build():
        zip_url = pick_update_zip(release)
        if zip_url:
            return zip_url
    if not isinstance(release, dict):
        return None
    fallback = None
    for asset in release.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        url = asset.get("url") or ""
        if not url:
            continue
        name = (asset.get("name") or "").lower()
        if name == UPDATE_ASSET_NAME.lower():
            return url
        if fallback is None and name.endswith(".exe"):
            fallback = url
    # A onefile build on a release that ships only the zip can still install
    # it (it swaps to the onedir layout); it just prefers the exe bridge.
    return fallback or pick_update_zip(release)


def pick_update_zip(release):
    """Download URL of the onedir zip inside ``release``, or None."""
    if not isinstance(release, dict):
        return None
    for asset in release.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        url = asset.get("url") or ""
        name = (asset.get("name") or "").lower()
        if url and name.endswith(UPDATE_ZIP_SUFFIX) and "screenshottool" in name:
            return url
    return None


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
        # Kept so the caller can install the update without a second request.
        "assets": [
            {
                "name": asset.get("name") or "",
                "url": asset.get("browser_download_url") or "",
                "size": asset.get("size") or 0,
            }
            for asset in (payload.get("assets") or [])
            if isinstance(asset, dict)
        ],
    }, "ok"


def can_self_update():
    """Replacing the running binary only makes sense for the packaged build.

    Running from source, there is nothing to swap: the "program" is the
    interpreter, so the caller falls back to opening the release page.
    """
    return bool(getattr(sys, "frozen", False))


def download_asset(url, destination, timeout=DOWNLOAD_TIMEOUT_SECONDS,
                   progress=None, chunk_size=256 * 1024):
    """Download ``url`` to ``destination``; the path, or None on failure.

    Writes to a temporary sibling and renames on success, so an interrupted
    download can never leave a truncated exe behind that a later run would
    happily install.
    """
    if not url:
        return None
    # Accept a Path as well as a str: string concatenation below would blow up
    # on anything but a plain path string.
    destination = os.fspath(destination)
    try:
        os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
    except OSError:
        log.exception("Could not create the download directory")
        return None

    partial = destination + ".part"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            total = int(response.headers.get("Content-Length") or 0)
            written = 0
            with open(partial, "wb") as handle:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    handle.write(chunk)
                    written += len(chunk)
                    if progress is not None:
                        try:
                            progress(written, total)
                        except Exception:
                            log.debug("Download progress callback failed",
                                      exc_info=True)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log.info("Download failed: %s", exc)
        _quiet_remove(partial)
        return None

    if total > 0 and written != total:
        # Mạng đứt giữa chừng: file .part thiếu bytes nhưng vẫn ghi xuống đĩa.
        # Trước đây chỉ kiểm tra size > 0 nên file cụt vẫn được đổi tên thành
        # exe rồi swap vào, restart lên là hỏng. README hứa "tải thất bại thì
        # bản đang chạy vẫn nguyên" — chỉ đúng khi so đủ Content-Length.
        log.info("Download truncated: got %d of %d bytes", written, total)
        _quiet_remove(partial)
        return None
    if os.path.getsize(partial) <= 0:
        log.info("Download produced an empty file")
        _quiet_remove(partial)
        return None
    try:
        os.replace(partial, destination)
    except OSError:
        log.exception("Could not move the download into place")
        _quiet_remove(partial)
        return None
    return destination


def _quiet_remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


# Windows refuses to overwrite a running executable, so the swap has to happen
# after this process exits. The helper retries the move instead of polling for
# the pid: the move failing is the exact condition it needs to wait for, and it
# keeps retrying only until the process lets go of the file.
_UPDATE_SCRIPT = r"""@echo off
setlocal
set "OLD={old}"
set "NEW={new}"
set /a tries=0
:retry
set /a tries+=1
move /y "%NEW%" "%OLD%" >nul 2>&1
if not errorlevel 1 goto swapped
if %tries% GEQ 120 goto failed
ping -n 2 127.0.0.1 >nul
goto retry
:failed
start "" "%OLD%"
del "%~f0" >nul 2>&1
exit /b 1
:swapped
del "%NEW%" >nul 2>&1
start "" "%OLD%"
del "%~f0" >nul 2>&1
exit /b 0
"""


def apply_update(new_path, current_exe, relaunch=True):
    """Replace the running build with ``new_path`` and start it, via a helper.

    ``new_path`` is the downloaded payload: an .exe swaps just the file (the
    old onefile behaviour), a .zip swaps the whole app folder (onedir). Returns
    the path of the helper script that was launched, or None. The caller is
    expected to exit immediately afterwards: the helper waits for this process
    to release its files, then swaps them in.
    """
    new_path = os.path.abspath(new_path)
    current_exe = os.path.abspath(current_exe)
    if not os.path.isfile(new_path):
        log.info("Update payload is missing: %s", new_path)
        return None
    if new_path.lower().endswith(UPDATE_ZIP_SUFFIX):
        return _apply_dir_update(new_path, current_exe, relaunch)
    return _apply_exe_update(new_path, current_exe, relaunch)


def _launch_helper(script, helper_name):
    """Write ``script`` to a .bat in %TEMP% and launch it hidden, or None."""
    helper = os.path.join(tempfile.gettempdir(), helper_name)
    try:
        with open(helper, "w", encoding="utf-8", newline="\r\n") as handle:
            handle.write(script)
    except OSError:
        log.exception("Could not write the update helper")
        return None

    flags = 0
    for name in ("CREATE_NO_WINDOW", "CREATE_NEW_PROCESS_GROUP"):
        flags |= getattr(subprocess, name, 0)
    try:
        subprocess.Popen(
            ["cmd", "/c", helper],
            creationflags=flags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except OSError:
        log.exception("Could not launch the update helper")
        return None
    return helper


def _apply_exe_update(new_exe, current_exe, relaunch=True):
    """Onefile path: swap the exe file once this process has exited."""
    script = _UPDATE_SCRIPT.format(old=current_exe, new=new_exe)
    if not relaunch:
        script = script.replace('start "" "%OLD%"', "rem no relaunch")
    helper = _launch_helper(script, "screenshotool_update.bat")
    if helper:
        log.info("Update helper launched to replace %s", current_exe)
    return helper


# Directory swap for onedir updates. Renaming the app folder fails while the
# running exe inside it is still locked, so the helper retries the rename
# (which is also how it waits for the old process to exit), then moves the
# staged folder into place. The old folder is kept as <dir>.old so a failed
# swap can still be recovered by hand; the new build deletes it on startup.
_UPDATE_DIR_SCRIPT = r"""@echo off
setlocal
set "TARGET={target}"
set "STAGING={staging}"
set "EXE={exe}"
set /a tries=0
:retry
set /a tries+=1
if exist "%TARGET%" (
  rd /s /q "%TARGET%.old" >nul 2>&1
  move /y "%TARGET%" "%TARGET%.old" >nul 2>&1
  if errorlevel 1 goto wait
)
move /y "%STAGING%" "%TARGET%" >nul 2>&1
if errorlevel 1 goto wait
start "" "%TARGET%\%EXE%"
del "%~f0" >nul 2>&1
exit /b 0
:wait
if %tries% GEQ 120 goto failed
ping -n 2 127.0.0.1 >nul
goto retry
:failed
if exist "%TARGET%\%EXE%" start "" "%TARGET%\%EXE%"
del "%~f0" >nul 2>&1
exit /b 1
"""


def _extract_update_zip(zip_path):
    """Extract the onedir zip to a staging dir; return the app folder or None.

    The zip holds one top folder with ScreenShotTool.exe inside. Extraction
    happens while the old build is still running, which is the whole point:
    Defender gets the download+extract time to scan the DLLs before the new
    exe is ever launched, instead of meeting them for the first time at launch.
    """
    staging_root = os.path.join(tempfile.gettempdir(), "ScreenShotTool-update")
    shutil.rmtree(staging_root, ignore_errors=True)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(staging_root)
    except (OSError, zipfile.BadZipFile):
        log.exception("Could not extract the update zip")
        return None
    for root, _dirs, files in os.walk(staging_root):
        if "ScreenShotTool.exe" in files:
            return root
    log.info("Update zip has no ScreenShotTool.exe inside")
    return None


def _onedir_target_dir(current_exe):
    """Where the onedir build should live.

    A onefile exe usually sits in Downloads or on the Desktop — swapping that
    whole folder would be wrong — so the first onedir install goes to a
    dedicated folder under %LOCALAPPDATA%. An onedir build just replaces its
    own folder in place.
    """
    if is_onefile_build():
        local_appdata = os.environ.get("LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Local")
        return os.path.join(local_appdata, "ScreenShotTool")
    return os.path.dirname(os.path.abspath(current_exe))


def _apply_dir_update(zip_path, current_exe, relaunch=True):
    """Onedir path: stage the zip, then swap the whole app folder."""
    app_dir = _extract_update_zip(zip_path)
    if app_dir is None:
        return None
    target = _onedir_target_dir(current_exe)
    script = _UPDATE_DIR_SCRIPT.format(
        target=target, staging=app_dir, exe="ScreenShotTool.exe")
    if not relaunch:
        script = script.replace('start "" "%TARGET%\\%EXE%"', "rem no relaunch")
    helper = _launch_helper(script, "screenshotool_update_dir.bat")
    if helper:
        log.info("Update helper launched to replace %s", target)
    return helper


def cleanup_old_app_dir():
    """Delete the <appdir>.old folder left behind by a directory swap.

    Called at startup by the new build, once it is running fine: the old
    folder is only garbage once the new one has proven it can start.
    """
    if not getattr(sys, "frozen", False):
        return
    app_dir = os.path.dirname(os.path.abspath(sys.executable))
    old_dir = app_dir + ".old"
    if os.path.isdir(old_dir):
        shutil.rmtree(old_dir, ignore_errors=True)
        log.info("Removed the previous app folder %s", old_dir)


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
