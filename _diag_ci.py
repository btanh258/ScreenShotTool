"""Run only on CI: dump what the Escape test actually sees.

Temporary diagnostic. Prints the state the failing test observes so the fix is
based on the runner's real behaviour instead of a guess. Deleted once the
difference is understood.
"""
import sys
import time
import tkinter as tk
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

import importlib.util

spec = importlib.util.spec_from_file_location("app", REPO / "ScreenShotTool.pyw")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

from PIL import Image

root = tk.Tk()
root.withdraw()
root.geometry("1280x800+30+30")

editor = app.ImageEditor(root, Image.new("RGB", (600, 400), "white"))
editor.top.state("normal")
editor.top.update_idletasks()
editor.top.geometry("1100x700+10+10")
for _ in range(8):
    root.update()

print("DIAG top width      :", editor.top.winfo_width())
print("DIAG inspector mapped:", editor.inspector.winfo_ismapped())
print("DIAG overlay flag    :", getattr(editor, "_inspector_overlay", None))
print("DIAG last_layout_w   :", getattr(editor, "_last_layout_width", None))
print("DIAG manager         :", editor.inspector.winfo_manager())
print("DIAG focus_get       :", root.focus_get())

# what bind_all is registered on
print("DIAG bind_all Escape :", repr(root.bind_all("<Escape>")))

# fire it the way the test does
editor._inspector_overlay_before = getattr(editor, "_inspector_overlay", None)
editor.top.focus_set()
root.update()
print("DIAG focus after set :", root.focus_get())
editor.top.event_generate("<Escape>", when="tail")
root.update()
print("DIAG after generate  : mapped=%s overlay=%s"
      % (editor.inspector.winfo_ismapped(),
         getattr(editor, "_inspector_overlay", None)))

# fire it directly to prove the handler works here
editor._on_escape()
root.update()
print("DIAG after direct    : mapped=%s" % editor.inspector.winfo_ismapped())

editor.top.destroy()
root.destroy()
