"""Recent-capture history and the floating "pinned" image window.

Two small self-contained features that would otherwise have been bolted onto the
editor or the tray module, where they would have to reach into the other's state:

* :class:`CaptureHistory` - keeps the last N captures on disk so a screenshot
  taken by mistake can be recovered after the editor is closed.
* :class:`PinnedImage` - a frameless always-on-top window holding one image, for
  comparing a reference shot against live work.

Nothing here imports the application module; both are driven through callbacks
so the dependency arrow stays one-way.
"""
import logging
import os
import time

import tkinter as tk

import ui_theme as T

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover - Pillow is a hard requirement
    raise

log = logging.getLogger(__name__)

# Keep the footprint small: a screenshot PNG is typically 100 KB - 2 MB, so 20
# entries stay in the tens of megabytes at worst.
DEFAULT_MAX_ENTRIES = 20


class CaptureHistory:
    """A bounded folder of the most recent captures.

    Files are named ``YYYYmmdd-HHMMSS-micro.png`` so lexical order is
    chronological, which means pruning needs no metadata file and no state that
    could desynchronise from the directory.
    """

    def __init__(self, directory, max_entries=DEFAULT_MAX_ENTRIES):
        self.directory = directory
        self.max_entries = max_entries

    def ensure_dir(self):
        try:
            os.makedirs(self.directory, exist_ok=True)
            return True
        except OSError:
            log.warning("Could not create the capture history folder", exc_info=True)
            return False

    def save(self, image):
        """Store one capture and prune the oldest. Returns the path or None."""
        if not self.ensure_dir():
            return None
        path = self._unique_path()
        try:
            # Opaque background: history is for recovery, not for later editing,
            # so the transparent regions a crop can leave must not turn black.
            if image.mode in ("RGBA", "LA", "P"):
                image = image.convert("RGBA")
                background = Image.new("RGB", image.size, (255, 255, 255))
                background.paste(image, mask=image.split()[-1])
                image = background
            image.save(path, "PNG")
        except (OSError, ValueError):
            log.warning("Could not write capture history entry", exc_info=True)
            return None
        self.prune()
        return path

    def _unique_path(self):
        """A timestamped filename that no existing entry already uses.

        Two captures can land in the same millisecond - the second one used to
        overwrite the first, silently losing a screenshot from the history.
        """
        while True:
            stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
            self._counter = (getattr(self, "_counter", 0) + 1) % 1000
            micro = "%03d" % self._counter
            candidate = os.path.join(self.directory, "%s-%s.png" % (stamp, micro))
            if not os.path.exists(candidate):
                return candidate

    def entries(self):
        """Newest-first list of stored history paths."""
        try:
            names = [name for name in os.listdir(self.directory)
                     if name.lower().endswith(".png")]
        except OSError:
            return []
        names.sort(reverse=True)
        return [os.path.join(self.directory, name) for name in names]

    def prune(self):
        """Delete everything beyond the newest ``max_entries`` files."""
        for stale in self.entries()[self.max_entries:]:
            try:
                os.remove(stale)
            except OSError:
                log.debug("Could not prune %s", stale, exc_info=True)

    def clear(self):
        removed = 0
        for path in self.entries():
            try:
                os.remove(path)
                removed += 1
            except OSError:
                log.debug("Could not remove %s", path, exc_info=True)
        return removed


class PinnedImage:
    """A frameless, always-on-top copy of an image.

    Deliberately minimal: drag to move, wheel to fade, double-click or Esc to
    close. It is a reference view, not an editor, so it has no toolbar.
    """

    MIN_ALPHA = 0.25
    ALPHA_STEP = 0.08
    BORDER = 2

    def __init__(self, root, image, at=None):
        self.root = root
        self.image = image if image.mode in ("RGB", "RGBA") else image.convert("RGBA")
        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        try:
            self.window.attributes("-topmost", True)
        except tk.TclError:
            log.debug("Could not set topmost on the pinned window", exc_info=True)
        self.alpha = 1.0
        self._drag_origin = None

        self.photo = ImageTk.PhotoImage(self.image)
        width, height = self.image.width, self.image.height
        self.canvas = tk.Canvas(
            self.window, width=width, height=height, highlightthickness=self.BORDER,
            highlightbackground=T.COLORS.accent, bd=0, cursor="fleur")
        self.canvas.pack()
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)

        if at is None:
            at = (self.window.winfo_pointerx() + 24, self.window.winfo_pointery() + 24)
        # Keep the whole window on screen: pinning near the bottom-right corner
        # would otherwise place most of it off the desktop where it cannot be
        # grabbed or closed.
        x = max(0, min(int(at[0]), self.window.winfo_screenwidth() - width - 8))
        y = max(0, min(int(at[1]), self.window.winfo_screenheight() - height - 8))
        self.window.geometry("%dx%d+%d+%d" % (width + 2 * self.BORDER,
                                              height + 2 * self.BORDER, x, y))

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<Double-Button-1>", lambda _e: self.close())
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.window.bind("<Escape>", lambda _e: self.close())
        self.window.bind("<Button-3>", lambda _e: self.close())
        try:
            self.window.focus_force()
        except tk.TclError:
            pass

    def _on_press(self, event):
        self._drag_origin = (event.x_root - self.window.winfo_x(),
                             event.y_root - self.window.winfo_y())

    def _on_drag(self, event):
        if self._drag_origin is None:
            return
        x = event.x_root - self._drag_origin[0]
        y = event.y_root - self._drag_origin[1]
        self.window.geometry("+%d+%d" % (x, y))

    def _on_wheel(self, event):
        delta = getattr(event, "delta", 0)
        step = self.ALPHA_STEP if delta > 0 else -self.ALPHA_STEP
        self.set_alpha(self.alpha + step)
        return "break"

    def set_alpha(self, value):
        self.alpha = max(self.MIN_ALPHA, min(1.0, value))
        try:
            self.window.attributes("-alpha", self.alpha)
        except tk.TclError:
            log.debug("Alpha not supported on this window", exc_info=True)
        return self.alpha

    def close(self):
        try:
            self.window.destroy()
        except tk.TclError:
            pass
