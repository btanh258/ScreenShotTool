"""Export and clipboard behaviour for the image editor.

These four methods were the most self-contained group inside ``ImageEditor``:
they talk to the filesystem and the clipboard and to nothing else in the class
except ``render_final_image``, ``commit_text`` and the Copy button. Pulling them
out here keeps the editor module focused on canvas interaction while leaving the
drawing and transform logic exactly where it was.

``EditorExportMixin`` is mixed into ``ImageEditor``; the methods are unchanged,
only relocated. Anything added here must not reach into canvas or shape state
beyond what these already touch, or the separation stops being worth having.
"""
import logging

import tkinter as tk
from tkinter import filedialog, messagebox

from PIL import Image

log = logging.getLogger(__name__)

# The button's idle caption. A module constant so the confirmation timer restores
# a known string rather than whatever the button currently shows.
_COPY_LABEL = "Copy"


class EditorExportMixin:
    """Copy to clipboard and save to disk.

    The clipboard writer is looked up on ``self`` each call rather than captured
    at construction: the application module owns ``send_to_clipboard`` and tests
    replace it there, so holding a bound reference here would freeze the original
    and make the indirection untestable.
    """

    def _clipboard_writer(self):
        writer = getattr(self, "send_to_clipboard", None)
        if writer is None:
            raise AttributeError("the editor needs a send_to_clipboard callable")
        return writer

    def save_clipboard(self):
        """Render the current image and publish it to the clipboard."""
        if self.text_entry:
            self.commit_text()
        copied = self._clipboard_writer()(self.render_final_image())
        # The idle label is a constant, not "whatever is on the button now":
        # a second click inside the 2 s confirmation window used to capture the
        # confirmation text itself and restore to the confirmation forever.
        if self._copy_reset_id is not None:
            self.top.after_cancel(self._copy_reset_id)
        self.btn_copy.config(text="✔ Copy!" if copied else "✖ Lỗi")
        self._copy_reset_id = self.top.after(2000, self._restore_copy_label)
        return copied

    def _restore_copy_label(self):
        self._copy_reset_id = None
        self.btn_copy.config(text=_COPY_LABEL)

    def _cancel_copy_reset(self, _event=None):
        # A pending confirmation timer must not outlive its button: Tk keeps the
        # "after" script queued in the interpreter and reports
        # "invalid command name ..._restore_copy_label" once the window is gone.
        if self._copy_reset_id is not None:
            try:
                self.top.after_cancel(self._copy_reset_id)
            except tk.TclError:
                pass
            self._copy_reset_id = None

    def save_file(self):
        """Ask for a path and write the rendered image there."""
        if self.text_entry:
            self.commit_text()
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")],
            parent=self.top)
        if not path:
            return None
        try:
            img = self.render_final_image()
            if path.lower().endswith((".jpg", ".jpeg")):
                # JPEG has no alpha: flatten onto white instead of writing a
                # black background where the image was transparent.
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            img.save(path)
        except (OSError, ValueError) as exc:
            log.exception("Could not save image to %s", path)
            messagebox.showerror("Không lưu được file",
                                 "Không ghi được file:\n%s\n\n%s" % (path, exc),
                                 parent=self.top)
            return None
        if not messagebox.askyesno(
                "Thành công",
                "Đã lưu file tại:\n%s\n\nBạn có muốn tiếp tục chỉnh sửa không?" % path,
                parent=self.top):
            self.top.destroy()
        return path
