#!/usr/bin/env python3
"""
Image Splicer — multi-region crop utility
  • Open via button or Ctrl+O
  • Drag & drop an image file onto the window
  • When loading a new image while selections exist, you're asked whether to keep them
    (selections that fall outside the new image are removed regardless)
  • Draw rectangle selections, resize/move them, delete individually or clear all
  • One-time save-location setting — remembered between sessions
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json, os, sys, threading
from pathlib import Path

try:
    from PIL import Image, ImageTk
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "Pillow", "--break-system-packages", "-q"])
    from PIL import Image, ImageTk

CONFIG_FILE = Path.home() / ".image_splicer_config.json"
DEBUG = "--debug" in sys.argv

def dlog(*args):
    if DEBUG:
        print("[dnd]", *args)

# ── palette ──────────────────────────────────────────────────────────────────
BG       = "#1a1a2e"
PANEL    = "#16213e"
ACCENT   = "#e94560"
ACCENT2  = "#0f3460"
GREEN    = "#27ae60"
DIMGREY  = "#444466"
TEXT     = "#eaeaea"
TEXTDIM  = "#8888aa"
SEL_NORM = "#e94560"
SEL_ACT  = "#ff6b6b"
HANDLE   = "#ffd700"
FUI      = ("Consolas", 10)
FSM      = ("Consolas", 9)
FLG      = ("Consolas", 13, "bold")


def load_cfg():
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text())
    except Exception:
        pass
    return {}

def save_cfg(cfg):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass


# ── data class ────────────────────────────────────────────────────────────────
class Sel:
    """One rectangular selection (canvas coordinates)."""
    def __init__(self, rid, lid, x1, y1, x2, y2):
        self.rid = rid
        self.lid = lid
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.handles = []

    def norm(self):
        return (min(self.x1, self.x2), min(self.y1, self.y2),
                max(self.x1, self.x2), max(self.y1, self.y2))

    def img_coords(self, scale, ox, oy):
        x1, y1, x2, y2 = self.norm()
        return (int((x1-ox)/scale), int((y1-oy)/scale),
                int((x2-ox)/scale), int((y2-oy)/scale))


# ── main window ───────────────────────────────────────────────────────────────
class App(tk.Tk):
    HR = 6  # handle half-size in pixels

    def __init__(self):
        super().__init__()
        self.title("Image Splicer")
        self.configure(bg=BG)
        self.minsize(920, 640)

        self.cfg        = load_cfg()
        self.pil_img    = None
        self.tk_img     = None
        self.scale      = 1.0
        self.offset     = (0, 0)
        self.sels       = []
        self.active     = None
        self.drag       = None
        self._resize_id = None

        self._build()
        self._setup_bindings()
        self._status("Open an image to get started  —  or drag & drop a file onto the window.")

    # ── build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        # toolbar
        tb = tk.Frame(self, bg=PANEL, height=50)
        tb.pack(fill=tk.X)
        tb.pack_propagate(False)

        self._btn(tb, "⊞  Open Image",    self._open_file,  ACCENT ).pack(side=tk.LEFT, padx=(10,4), pady=10)
        self._btn(tb, "⌂  Save Location", self._set_save,   ACCENT2).pack(side=tk.LEFT, padx=4, pady=10)
        self._btn(tb, "✦  Save Crops",    self._save_crops, GREEN  ).pack(side=tk.LEFT, padx=4, pady=10)
        tk.Frame(tb, bg=ACCENT, width=2, height=30).pack(side=tk.LEFT, padx=10, pady=10)
        self._btn(tb, "⌫  Delete Sel",    self._del_sel,    DIMGREY).pack(side=tk.LEFT, padx=4, pady=10)
        self._btn(tb, "✕  Clear All",     self._clear_all,  DIMGREY).pack(side=tk.LEFT, padx=4, pady=10)

        # Keep-selections checkbox
        tk.Frame(tb, bg=ACCENT, width=2, height=30).pack(side=tk.LEFT, padx=10, pady=10)
        self.keep_var = tk.BooleanVar(value=self.cfg.get("keep_sels", True))
        tk.Checkbutton(tb, text="Keep selections", variable=self.keep_var,
                       bg=PANEL, fg=TEXT, selectcolor=ACCENT2,
                       activebackground=PANEL, activeforeground=TEXT,
                       font=FSM, bd=0, cursor="hand2",
                       command=self._on_keep_toggle).pack(side=tk.LEFT, padx=(0,4))

        self.savedir_lbl = tk.StringVar(value=self.cfg.get("save_dir", "(no save location set)"))
        tk.Label(tb, textvariable=self.savedir_lbl, bg=PANEL, fg=TEXTDIM,
                 font=FSM).pack(side=tk.LEFT, padx=14)

        self._btn(tb, "−", self._zoom_out, ACCENT2, w=3).pack(side=tk.RIGHT, padx=(4,10), pady=10)
        self._btn(tb, "+", self._zoom_in,  ACCENT2, w=3).pack(side=tk.RIGHT, padx=4,     pady=10)
        self.zoom_lbl = tk.StringVar(value="100%")
        tk.Label(tb, textvariable=self.zoom_lbl, bg=PANEL, fg=TEXT,
                 font=FSM, width=6).pack(side=tk.RIGHT)
        tk.Label(tb, text="Zoom:", bg=PANEL, fg=TEXTDIM, font=FSM).pack(side=tk.RIGHT, padx=4)

        # main area
        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True)

        # canvas
        cf = tk.Frame(body, bg=BG)
        cf.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        self.hbar = tk.Scrollbar(cf, orient=tk.HORIZONTAL, bg=PANEL)
        self.vbar = tk.Scrollbar(cf, orient=tk.VERTICAL,   bg=PANEL)
        self.canvas = tk.Canvas(cf, bg="#0d0d1a", highlightthickness=0,
                                cursor="crosshair",
                                xscrollcommand=self.hbar.set,
                                yscrollcommand=self.vbar.set)
        self.hbar.config(command=self.canvas.xview)
        self.vbar.config(command=self.canvas.yview)
        self.hbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.vbar.pack(side=tk.RIGHT,  fill=tk.Y)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # side panel
        side = tk.Frame(body, bg=PANEL, width=210)
        side.pack(fill=tk.Y, side=tk.RIGHT)
        side.pack_propagate(False)

        tk.Label(side, text="SELECTIONS", bg=PANEL, fg=ACCENT,
                 font=FLG).pack(pady=(14, 4))
        tk.Frame(side, bg=ACCENT, height=1).pack(fill=tk.X, padx=10)

        lf_outer = tk.Frame(side, bg=PANEL)
        lf_outer.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.list_canvas = tk.Canvas(lf_outer, bg=PANEL, highlightthickness=0)
        lsb = tk.Scrollbar(lf_outer, orient=tk.VERTICAL,
                           command=self.list_canvas.yview, bg=PANEL)
        self.list_canvas.configure(yscrollcommand=lsb.set)
        lsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.list_canvas.pack(fill=tk.BOTH, expand=True)
        self.list_frame = tk.Frame(self.list_canvas, bg=PANEL)
        self._lf_win = self.list_canvas.create_window(0, 0, anchor="nw",
                                                       window=self.list_frame)
        self.list_frame.bind("<Configure>", self._on_list_resize)

        bp = tk.Frame(side, bg=PANEL)
        bp.pack(fill=tk.X, padx=10, pady=(0, 12))
        tk.Label(bp, text="Filename prefix:", bg=PANEL, fg=TEXTDIM,
                 font=FSM).pack(anchor="w")
        self.prefix_var = tk.StringVar(value=self.cfg.get("prefix", "crop"))
        tk.Entry(bp, textvariable=self.prefix_var, bg=ACCENT2, fg=TEXT,
                 font=FSM, insertbackground=TEXT,
                 relief=tk.FLAT, bd=4).pack(fill=tk.X, pady=(2, 8))
        self.prefix_var.trace_add("write", lambda *_: self._persist("prefix", self.prefix_var.get()))

        tk.Label(bp, text="Format:", bg=PANEL, fg=TEXTDIM, font=FSM).pack(anchor="w")
        self.fmt_var = tk.StringVar(value=self.cfg.get("format", "PNG"))
        ttk.Combobox(bp, textvariable=self.fmt_var,
                     values=["PNG", "JPEG", "WEBP", "BMP", "TIFF"],
                     state="readonly", font=FSM).pack(fill=tk.X, pady=(2, 0))
        self.fmt_var.trace_add("write", lambda *_: self._persist("format", self.fmt_var.get()))

        # status bar
        sb = tk.Frame(self, bg=PANEL, height=24)
        sb.pack(fill=tk.X, side=tk.BOTTOM)
        sb.pack_propagate(False)
        self.status_var = tk.StringVar()
        self.coord_var  = tk.StringVar()
        tk.Label(sb, textvariable=self.status_var, bg=PANEL, fg=TEXTDIM,
                 font=FSM, anchor="w").pack(side=tk.LEFT,  padx=10)
        tk.Label(sb, textvariable=self.coord_var,  bg=PANEL, fg=TEXTDIM,
                 font=FSM, anchor="e").pack(side=tk.RIGHT, padx=10)

    def _btn(self, parent, text, cmd, color, w=None):
        # Use Label instead of Button so macOS Tk honours bg/fg colours.
        kw = dict(text=text, bg=color, fg=TEXT, font=FUI,
                  cursor="hand2", padx=10, pady=5,
                  relief=tk.FLAT, bd=0)
        if w:
            kw["width"] = w
        b = tk.Label(parent, **kw)
        b.bind("<Enter>",          lambda e, b=b, c=color: b.configure(bg=self._lighten(c)))
        b.bind("<Leave>",          lambda e, b=b, c=color: b.configure(bg=c))
        b.bind("<ButtonPress-1>",  lambda e, b=b, c=color: b.configure(bg=self._darken(c)))
        b.bind("<ButtonRelease-1>",lambda e, b=b, c=color, f=cmd: (b.configure(bg=self._lighten(c)), f()))
        return b

    @staticmethod
    def _lighten(h):
        r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
        return f"#{min(255,r+40):02x}{min(255,g+40):02x}{min(255,b+40):02x}"

    @staticmethod
    def _darken(h):
        r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
        return f"#{max(0,r-30):02x}{max(0,g-30):02x}{max(0,b-30):02x}"

    def _on_list_resize(self, e):
        self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all"))
        self.list_canvas.itemconfig(self._lf_win,
                                    width=self.list_canvas.winfo_width())

    # ── event binding ─────────────────────────────────────────────────────────

    def _on_keep_toggle(self):
        self._persist("keep_sels", self.keep_var.get())

    def _setup_bindings(self):
        # Strategy 1: tkdnd (cross-platform, optional)
        self._dnd_ok = False
        try:
            self.tk.call("package", "require", "tkdnd")
            self.drop_target_register("DND_Files")
            self.dnd_bind("<<Drop>>", self._on_dnd_tkdnd)
            self._dnd_ok = True
        except Exception:
            pass

        # Strategy 2: Windows — hook WM_DROPFILES via ctypes directly.
        # No extra packages needed; works by subclassing the HWND and
        # intercepting the drop message before tkinter sees it.
        if not self._dnd_ok:
            try:
                self._setup_win32_dnd()
            except Exception:
                pass

        # Strategy 3: macOS native tk::mac::OpenDocument
        # This fires when files are dragged onto the window on macOS.
        # We must use tk.eval (not tk.call) so that $args is treated as a
        # literal Tcl variable reference in the proc body, not expanded now.
        if not self._dnd_ok:
            try:
                _cb = self.register(self._on_mac_drop)
                self.tk.eval(
                    f'proc ::tk::mac::OpenDocument {{args}} {{ {_cb} $args }}'
                )
                self._dnd_ok = True
            except Exception as e:
                dlog("Mac DnD setup error:", e)

        self.canvas.bind("<ButtonPress-1>",   self._press)
        self.canvas.bind("<B1-Motion>",        self._move)
        self.canvas.bind("<ButtonRelease-1>",  self._release)
        self.canvas.bind("<Motion>",           self._hover)
        self.canvas.bind("<Delete>",           lambda e: self._del_sel())
        self.canvas.bind("<BackSpace>",        lambda e: self._del_sel())
        self.canvas.bind("<Escape>",           lambda e: self._cancel_drag())

        # Support both Ctrl (Win/Linux) and Cmd (macOS)
        for mod in ("<Control-z>", "<Command-z>"):
            try: self.canvas.bind(mod, lambda e: self._del_last())
            except Exception: pass

        self.canvas.bind("<Control-MouseWheel>",
                         lambda e: self._zoom_in() if e.delta > 0 else self._zoom_out())
        self.canvas.bind("<Command-MouseWheel>",
                         lambda e: self._zoom_in() if e.delta > 0 else self._zoom_out())
        self.canvas.bind("<Control-Button-4>",  lambda e: self._zoom_in())
        self.canvas.bind("<Control-Button-5>",  lambda e: self._zoom_out())

        for mod in ("<Control-o>", "<Command-o>"):
            try: self.bind(mod, lambda e: self._open_file())
            except Exception: pass
        for mod in ("<Control-s>", "<Command-s>"):
            try: self.bind(mod, lambda e: self._save_crops())
            except Exception: pass

        self.bind("<Configure>", self._on_win_resize)
        self.canvas.focus_set()

    def _on_dnd_tkdnd(self, event):
        path = event.data.strip()
        if path.startswith("{") and path.endswith("}"):
            path = path[1:-1]
        path = path.split("} {")[0]
        self._try_load(path.strip())

    def _setup_win32_dnd(self):
        """Schedule Win32 DnD setup after mainloop starts so tkinter's
        own wndproc is installed first — we then subclass on top of it."""
        self.after(100, self._install_win32_dnd)
        self._dnd_ok = True

    def _install_win32_dnd(self):
        import ctypes, ctypes.wintypes
        user32  = ctypes.windll.user32
        shell32 = ctypes.windll.shell32

        self.update_idletasks()

        # Use the canvas HWND — tkinter's wndproc lives there and that's
        # the widget the user actually drops onto.
        hwnd = self.canvas.winfo_id()
        dlog(f"installing on canvas hwnd={hwnd:#x}")

        WM_DROPFILES     = 0x0233
        WM_COPYGLOBALDATA = 0x0049
        MSGFLT_ALLOW     = 1
        GWL_WNDPROC      = -4

        # Allow drops through UIPI filter
        try:
            user32.ChangeWindowMessageFilterEx(hwnd, WM_DROPFILES,     MSGFLT_ALLOW, None)
            user32.ChangeWindowMessageFilterEx(hwnd, WM_COPYGLOBALDATA, MSGFLT_ALLOW, None)
        except Exception as e:
            dlog("ChangeWindowMessageFilterEx error:", e)

        shell32.DragAcceptFiles(hwnd, True)
        dlog(f"DragAcceptFiles done on {hwnd:#x}")

        # Correct 64-bit-safe types
        user32.GetWindowLongPtrW.restype  = ctypes.c_size_t
        user32.GetWindowLongPtrW.argtypes = [
            ctypes.wintypes.HWND, ctypes.c_int]
        user32.SetWindowLongPtrW.restype  = ctypes.c_size_t
        user32.SetWindowLongPtrW.argtypes = [
            ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_size_t]
        user32.CallWindowProcW.restype    = ctypes.c_ssize_t
        user32.CallWindowProcW.argtypes   = [
            ctypes.c_size_t,          # lpPrevWndFunc (stored as unsigned)
            ctypes.wintypes.HWND,
            ctypes.wintypes.UINT,
            ctypes.wintypes.WPARAM,
            ctypes.wintypes.LPARAM]

        WNDPROCTYPE = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            ctypes.wintypes.HWND,
            ctypes.wintypes.UINT,
            ctypes.wintypes.WPARAM,
            ctypes.wintypes.LPARAM,
        )

        original_proc = user32.GetWindowLongPtrW(hwnd, GWL_WNDPROC)
        dlog(f"original_proc={original_proc:#x}")

        shell32.DragQueryFileW.restype  = ctypes.wintypes.UINT
        shell32.DragQueryFileW.argtypes = [
            ctypes.c_size_t, ctypes.wintypes.UINT,
            ctypes.c_wchar_p, ctypes.wintypes.UINT]
        shell32.DragFinish.argtypes = [ctypes.c_size_t]

        # We must acquire the GIL before touching Python objects because
        # Windows may invoke the wndproc from a thread that doesn't hold it.
        # Use pythonapi.PyGILState_Ensure/Release to bracket all Python calls.
        PyGILState_Ensure  = ctypes.pythonapi.PyGILState_Ensure
        PyGILState_Release = ctypes.pythonapi.PyGILState_Release
        PyGILState_Ensure.restype  = ctypes.c_int
        PyGILState_Release.argtypes = [ctypes.c_int]

        # Shared buffer: wndproc writes path here, poll loop reads it.
        # This avoids calling ANY Python code inside the wndproc itself.
        import array
        _pending = [None]  # list so closure can rebind

        def wnd_proc(h, msg, wparam, lparam):
            if msg == WM_DROPFILES:
                gstate = PyGILState_Ensure()
                try:
                    hdrop = ctypes.c_size_t(wparam).value
                    n = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
                    if n > 0:
                        buf = ctypes.create_unicode_buffer(4096)
                        shell32.DragQueryFileW(hdrop, 0, buf, 4096)
                        _pending[0] = buf.value
                    shell32.DragFinish(hdrop)
                finally:
                    PyGILState_Release(gstate)
                return 0
            return user32.CallWindowProcW(original_proc, h, msg, wparam, lparam)

        self._wnd_proc_ref = WNDPROCTYPE(wnd_proc)
        proc_ptr = ctypes.cast(self._wnd_proc_ref, ctypes.c_void_p).value
        result = user32.SetWindowLongPtrW(hwnd, GWL_WNDPROC, proc_ptr)
        dlog(f"SetWindowLongPtrW result={result:#x}")

        # Poll every 50 ms for a dropped path and load it on the main thread
        def poll_drop():
            if _pending[0] is not None:
                path, _pending[0] = _pending[0], None
                self._try_load(path)
            self.after(50, poll_drop)
        self.after(50, poll_drop)

    def _on_mac_drop(self, *args):
        # Tcl may pass args as one space-joined string or multiple tokens
        if len(args) == 1 and isinstance(args[0], str):
            parts = args[0].split()
        else:
            parts = [str(a) for a in args]
        if parts:
            self._try_load(parts[0].strip())

    def _on_win_resize(self, e):
        if self._resize_id:
            self.after_cancel(self._resize_id)
        self._resize_id = self.after(120, self._redraw_image)

    # ── hit testing ───────────────────────────────────────────────────────────

    _EDGE = 8

    def _hit(self, cx, cy):
        E = self._EDGE
        for i in reversed(range(len(self.sels))):
            x1, y1, x2, y2 = self.sels[i].norm()
            if not (x1-E <= cx <= x2+E and y1-E <= cy <= y2+E):
                continue
            oL = abs(cx-x1) <= E;  oR = abs(cx-x2) <= E
            oT = abs(cy-y1) <= E;  oB = abs(cy-y2) <= E
            if oL and oT: return i, "TL"
            if oR and oT: return i, "TR"
            if oL and oB: return i, "BL"
            if oR and oB: return i, "BR"
            if oL: return i, "L"
            if oR: return i, "R"
            if oT: return i, "T"
            if oB: return i, "B"
            return i, "move"
        return None

    _CURSORS = {
        "move": "fleur",
        "TL": "top_left_corner",  "TR": "top_right_corner",
        "BL": "bottom_left_corner", "BR": "bottom_right_corner",
        "L": "left_side", "R": "right_side",
        "T": "top_side",  "B": "bottom_side",
    }

    # ── mouse handlers ────────────────────────────────────────────────────────

    def _cv(self, event):
        return self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

    def _hover(self, event):
        if not self.pil_img:
            return
        cx, cy = self._cv(event)
        ix, iy = self._to_img(cx, cy)
        if 0 <= ix <= self.pil_img.width and 0 <= iy <= self.pil_img.height:
            self.coord_var.set(f"x:{ix}  y:{iy}")
        else:
            self.coord_var.set("")
        if self.drag:
            return
        h = self._hit(cx, cy)
        self.canvas.configure(cursor=self._CURSORS.get(h[1], "fleur") if h else "crosshair")

    def _press(self, event):
        self.canvas.focus_set()
        if not self.pil_img:
            return
        cx, cy = self._cv(event)
        h = self._hit(cx, cy)
        if h:
            idx, part = h
            self._activate(idx)
            self.drag = {"mode": part, "idx": idx,
                         "ox": cx, "oy": cy,
                         "orig": self.sels[idx].norm()}
        else:
            self._deactivate()
            self.drag = {"mode": "new", "ox": cx, "oy": cy, "tmp": None, "tlbl": None}

    def _move(self, event):
        if not self.drag:
            return
        cx, cy = self._cv(event)
        d = self.drag

        if d["mode"] == "new":
            if d["tmp"]:  self.canvas.delete(d["tmp"])
            if d["tlbl"]: self.canvas.delete(d["tlbl"])
            d["tmp"]  = self.canvas.create_rectangle(
                d["ox"], d["oy"], cx, cy,
                outline=SEL_ACT, width=2, dash=(4, 3))
            d["tlbl"] = self.canvas.create_text(
                min(d["ox"], cx)+4, min(d["oy"], cy)+4,
                text=f"#{len(self.sels)+1}", fill=SEL_ACT,
                anchor="nw", font=FSM)
            return

        s = self.sels[d["idx"]]
        dx, dy = cx - d["ox"], cy - d["oy"]
        x1o, y1o, x2o, y2o = d["orig"]
        p = d["mode"]
        if   p == "move": s.x1,s.y1,s.x2,s.y2 = x1o+dx,y1o+dy,x2o+dx,y2o+dy
        elif p == "TL":   s.x1,s.y1 = x1o+dx, y1o+dy
        elif p == "TR":   s.x2,s.y1 = x2o+dx, y1o+dy
        elif p == "BL":   s.x1,s.y2 = x1o+dx, y2o+dy
        elif p == "BR":   s.x2,s.y2 = x2o+dx, y2o+dy
        elif p == "L":    s.x1 = x1o+dx
        elif p == "R":    s.x2 = x2o+dx
        elif p == "T":    s.y1 = y1o+dy
        elif p == "B":    s.y2 = y2o+dy
        self._redraw_sel(d["idx"])
        self._refresh_list()

    def _release(self, event):
        if not self.drag:
            return
        cx, cy = self._cv(event)
        d = self.drag
        if d["mode"] == "new":
            if d["tmp"]:  self.canvas.delete(d["tmp"])
            if d["tlbl"]: self.canvas.delete(d["tlbl"])
            w, h = abs(cx - d["ox"]), abs(cy - d["oy"])
            if w > 4 and h > 4:
                self._add_sel(d["ox"], d["oy"], cx, cy)
        self.drag = None

    def _cancel_drag(self):
        if not self.drag:
            return
        d = self.drag
        if d["mode"] == "new":
            if d["tmp"]:  self.canvas.delete(d["tmp"])
            if d["tlbl"]: self.canvas.delete(d["tlbl"])
        self.drag = None

    # ── selection management ──────────────────────────────────────────────────

    def _add_sel(self, x1, y1, x2, y2):
        n   = len(self.sels) + 1
        rid = self.canvas.create_rectangle(x1, y1, x2, y2,
                                           outline=SEL_NORM, width=2, tags="sel")
        lid = self.canvas.create_text(
            min(x1,x2)+4, min(y1,y2)+4,
            text=f"#{n}", fill=SEL_NORM, anchor="nw", font=FSM, tags="sel")
        s = Sel(rid, lid, x1, y1, x2, y2)
        self.sels.append(s)
        self._draw_handles(len(self.sels)-1)
        self._activate(len(self.sels)-1)
        self._refresh_list()
        iw = abs(int((x2-x1)/self.scale))
        ih = abs(int((y2-y1)/self.scale))
        self._status(f"Selection #{n} — {iw}×{ih}px   |   {len(self.sels)} total")

    def _draw_handles(self, idx):
        s = self.sels[idx]
        for h in s.handles:
            self.canvas.delete(h)
        s.handles.clear()
        x1, y1, x2, y2 = s.norm()
        r = self.HR
        for hx, hy in [(x1,y1),(x2,y1),(x1,y2),(x2,y2)]:
            hid = self.canvas.create_rectangle(
                hx-r, hy-r, hx+r, hy+r,
                fill=HANDLE, outline=BG, width=1, tags="handle")
            s.handles.append(hid)

    def _redraw_sel(self, idx):
        s = self.sels[idx]
        self.canvas.coords(s.rid, s.x1, s.y1, s.x2, s.y2)
        self.canvas.coords(s.lid, min(s.x1,s.x2)+4, min(s.y1,s.y2)+4)
        self._draw_handles(idx)

    def _activate(self, idx):
        self._deactivate()
        self.active = idx
        s = self.sels[idx]
        self.canvas.itemconfig(s.rid, outline=SEL_ACT, width=2)
        self._draw_handles(idx)
        self._refresh_list()

    def _deactivate(self):
        if self.active is not None and self.active < len(self.sels):
            s = self.sels[self.active]
            self.canvas.itemconfig(s.rid, outline=SEL_NORM, width=2)
            for h in s.handles:
                self.canvas.delete(h)
            s.handles.clear()
        self.active = None

    def _del_sel(self):
        if self.active is None:
            return
        self._remove_idx(self.active)

    def _del_last(self):
        if self.sels:
            self._activate(len(self.sels)-1)
            self._del_sel()

    def _remove_idx(self, idx):
        s = self.sels.pop(idx)
        self.canvas.delete(s.rid)
        self.canvas.delete(s.lid)
        for h in s.handles:
            self.canvas.delete(h)
        self.active = None
        self._renumber()
        self._refresh_list()
        self._status(f"{len(self.sels)} selection(s) remaining.")

    def _clear_all(self, silent=False):
        for s in self.sels:
            self.canvas.delete(s.rid)
            self.canvas.delete(s.lid)
            for h in s.handles:
                self.canvas.delete(h)
        self.sels.clear()
        self.active = None
        self._refresh_list()
        if not silent:
            self._status("All selections cleared.")

    def _renumber(self):
        for i, s in enumerate(self.sels):
            self.canvas.itemconfig(s.lid, text=f"#{i+1}")

    # ── side-panel list ───────────────────────────────────────────────────────

    def _refresh_list(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        if not self.sels:
            tk.Label(self.list_frame, text="No selections yet.",
                     bg=PANEL, fg=TEXTDIM, font=FSM).pack(pady=10)
            return
        for i, s in enumerate(self.sels):
            x1, y1, x2, y2 = s.img_coords(self.scale, *self.offset)
            w  = abs(x2-x1);  h = abs(y2-y1)
            bg = ACCENT2 if i == self.active else PANEL
            row = tk.Frame(self.list_frame, bg=bg, pady=4)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text=f"#{i+1}", bg=bg, fg=ACCENT,
                     font=("Consolas", 9, "bold"), width=3).pack(side=tk.LEFT, padx=(6,0))
            tk.Label(row, text=f"{w}×{h}px", bg=bg, fg=TEXT,
                     font=FSM).pack(side=tk.LEFT, padx=4)
            def _d(idx=i):
                self._activate(idx)
                self._del_sel()
            tk.Button(row, text="✕", bg=bg, fg=ACCENT, font=FSM,
                      relief=tk.FLAT, bd=0, cursor="hand2",
                      command=_d).pack(side=tk.RIGHT, padx=6)
            row.bind("<Button-1>", lambda e, idx=i: self._activate(idx))

    # ── image loading ─────────────────────────────────────────────────────────

    def _open_file(self):
        p = filedialog.askopenfilename(
            title="Open Image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp *.gif"),
                       ("All", "*.*")])
        if p:
            self._try_load(p)

    def _try_load(self, path):
        """Load image at path, offering to keep valid existing selections."""
        path = path.strip()
        if not os.path.isfile(path):
            messagebox.showerror("Error", f"File not found:\n{path}")
            return
        try:
            new_img = Image.open(path)
            new_img.load()
        except Exception as e:
            messagebox.showerror("Error", f"Could not open image:\n{e}")
            return

        # --- decide what to do with existing selections ---
        restore_img = []   # list of (ix1,iy1,ix2,iy2) to restore
        if self.sels and self.pil_img and self.keep_var.get():
            for s in self.sels:
                ix1, iy1, ix2, iy2 = s.img_coords(self.scale, *self.offset)
                ix1, iy1 = min(ix1,ix2), min(iy1,iy2)
                ix2, iy2 = max(ix1,ix2), max(iy1,iy2)
                if (ix1 >= 0 and iy1 >= 0 and
                        ix2 <= new_img.width and iy2 <= new_img.height):
                    restore_img.append((ix1, iy1, ix2, iy2))

        # --- swap image ---
        self._clear_all(silent=True)
        self.pil_img = new_img
        self.scale   = 1.0
        self._fit_image()

        # --- re-apply kept selections in new canvas coordinates ---
        for (ix1, iy1, ix2, iy2) in restore_img:
            ox, oy = self.offset
            self._add_sel(
                ox + ix1*self.scale, oy + iy1*self.scale,
                ox + ix2*self.scale, oy + iy2*self.scale)
        self._deactivate()
        self._refresh_list()

        self.title(f"Image Splicer — {Path(path).name}")
        extra = f"  — kept {len(restore_img)} selection(s)" if restore_img else ""
        self._status(
            f"Loaded: {Path(path).name}  ({new_img.width}×{new_img.height}px){extra}")

    def _fit_image(self):
        if not self.pil_img:
            return
        self.update_idletasks()
        cw = self.canvas.winfo_width()  or 800
        ch = self.canvas.winfo_height() or 600
        self.scale = min(cw/self.pil_img.width, ch/self.pil_img.height, 1.0)
        self._redraw_image()

    def _redraw_image(self):
        if not self.pil_img:
            return
        iw = max(1, int(self.pil_img.width  * self.scale))
        ih = max(1, int(self.pil_img.height * self.scale))
        resized = self.pil_img.resize((iw, ih), Image.LANCZOS)
        self.tk_img = ImageTk.PhotoImage(resized)
        self.canvas.delete("bg_img")
        ox = max(0, (self.canvas.winfo_width()  - iw) // 2)
        oy = max(0, (self.canvas.winfo_height() - ih) // 2)
        self.offset = (ox, oy)
        self.canvas.create_image(ox, oy, anchor="nw",
                                 image=self.tk_img, tags="bg_img")
        self.canvas.tag_lower("bg_img")
        self.canvas.configure(scrollregion=(
            0, 0,
            max(iw+ox*2, self.canvas.winfo_width()),
            max(ih+oy*2, self.canvas.winfo_height())))
        self.zoom_lbl.set(f"{int(self.scale*100)}%")

    # ── zoom ──────────────────────────────────────────────────────────────────

    def _zoom_in(self):  self._set_zoom(min(self.scale*1.25, 8.0))
    def _zoom_out(self): self._set_zoom(max(self.scale/1.25, 0.05))

    def _set_zoom(self, ns):
        if not self.pil_img:
            return
        ratio = ns / self.scale
        self.scale = ns
        ox, oy = self.offset
        for s in self.sels:
            s.x1 = ox + (s.x1-ox)*ratio;  s.y1 = oy + (s.y1-oy)*ratio
            s.x2 = ox + (s.x2-ox)*ratio;  s.y2 = oy + (s.y2-oy)*ratio
        self._redraw_image()
        for i in range(len(self.sels)):
            self._redraw_sel(i)
        self._refresh_list()

    # ── coordinate helpers ────────────────────────────────────────────────────

    def _to_img(self, cx, cy):
        ox, oy = self.offset
        return int((cx-ox)/self.scale), int((cy-oy)/self.scale)

    # ── save ──────────────────────────────────────────────────────────────────

    def _set_save(self):
        d = filedialog.askdirectory(title="Choose save folder")
        if d:
            self.cfg["save_dir"] = d
            self.savedir_lbl.set(d)
            save_cfg(self.cfg)
            self._status(f"Save location: {d}")

    def _persist(self, key, val):
        self.cfg[key] = val
        save_cfg(self.cfg)

    def _save_crops(self):
        if not self.pil_img:
            messagebox.showwarning("No Image", "Open an image first.")
            return
        if not self.sels:
            messagebox.showwarning("No Selections", "Draw at least one selection.")
            return
        sd = self.cfg.get("save_dir", "")
        if not sd or not os.path.isdir(sd):
            messagebox.showwarning("No Save Location",
                "Set a save location first (Save Location button).")
            return

        def worker():
            prefix = self.prefix_var.get() or "crop"
            fmt    = self.fmt_var.get()
            ext    = "jpg" if fmt == "JPEG" else fmt.lower()
            saved, errors = [], []
            for i, s in enumerate(self.sels):
                ix1, iy1, ix2, iy2 = s.img_coords(self.scale, *self.offset)
                ix1, iy1 = max(0, min(ix1,ix2)), max(0, min(iy1,iy2))
                ix2, iy2 = (min(self.pil_img.width,  max(ix1,ix2)),
                             min(self.pil_img.height, max(iy1,iy2)))
                if ix2 <= ix1 or iy2 <= iy1:
                    errors.append(f"#{i+1}: zero-size crop")
                    continue
                crop = self.pil_img.crop((ix1, iy1, ix2, iy2))
                base  = f"{prefix}_{i+1:02d}"
                fname = f"{base}.{ext}";  n = 1
                while os.path.exists(os.path.join(sd, fname)):
                    fname = f"{base}_{n}.{ext}";  n += 1
                fpath = os.path.join(sd, fname)
                try:
                    crop.save(fpath, fmt, **({"quality": 95} if fmt == "JPEG" else {}))
                    saved.append(fname)
                except Exception as e:
                    errors.append(f"#{i+1}: {e}")
            if errors:
                self.after(0, lambda e=errors: self._toast(
                    "⚠ " + "\n".join(e), color=ACCENT))
            else:
                self.after(0, lambda n=len(saved): self._toast(
                    f"✓  {n} crop{'s' if n != 1 else ''} saved", color=GREEN))
            self.after(0, lambda n=len(saved): self._status(
                f"✓ Saved {n} crops → {sd}"))

        threading.Thread(target=worker, daemon=True).start()

    # ── status & toast ────────────────────────────────────────────────────────

    def _status(self, msg):
        self.status_var.set(msg)

    def _toast(self, msg, color=GREEN, duration=2200):
        """Briefly show a non-blocking overlay message on the canvas."""
        # Remove any existing toast
        if hasattr(self, '_toast_widgets'):
            for w in self._toast_widgets:
                try: w.destroy()
                except Exception: pass

        # Build the toast label
        lbl = tk.Label(self.canvas, text=msg, bg=color, fg=TEXT,
                       font=("Consolas", 11, "bold"),
                       padx=18, pady=10, relief=tk.FLAT, bd=0,
                       justify="center")
        # Place it centred near the top of the canvas
        lbl.place(relx=0.5, rely=0.08, anchor="center")
        self._toast_widgets = [lbl]

        # Fade out then destroy
        def _fade(alpha=1.0):
            if not self._toast_widgets or lbl not in self._toast_widgets:
                return
            # Interpolate colour toward the canvas background
            def _blend(fg, bg, t):
                fr,fg_,fb = int(fg[1:3],16),int(fg[3:5],16),int(fg[5:7],16)
                br,bg_,bb = int(bg[1:3],16),int(bg[3:5],16),int(bg[5:7],16)
                r = int(fr*t + br*(1-t))
                g = int(fg_*t + bg_*(1-t))
                b = int(fb*t + bb*(1-t))
                return f"#{r:02x}{g:02x}{b:02x}"
            if alpha <= 0:
                for w in self._toast_widgets:
                    try: w.destroy()
                    except Exception: pass
                self._toast_widgets = []
                return
            try:
                lbl.configure(
                    bg=_blend(color, "#0d0d1a", alpha),
                    fg=_blend(TEXT,  "#0d0d1a", alpha))
            except Exception:
                return
            self.after(30, lambda: _fade(alpha - 0.04))

        self.after(duration, lambda: _fade(1.0))


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    style = ttk.Style(app)
    style.theme_use("default")
    style.configure("TCombobox",
                    fieldbackground=ACCENT2, background=PANEL,
                    foreground=TEXT, selectbackground=ACCENT, arrowcolor=TEXT)
    app.mainloop()
