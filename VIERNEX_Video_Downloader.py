import os
import sys
import re
import json
import time
import uuid
import ctypes
import queue
import shutil
import threading
import subprocess
import socket
import urllib.request
from pathlib import Path
from urllib.parse import urlparse, parse_qs, parse_qsl, urlencode, urlunparse, unquote

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageDraw

try:
    import yt_dlp
    from yt_dlp.utils import download_range_func
except Exception:
    yt_dlp = None
    download_range_func = None

try:
    import imageio_ffmpeg
except Exception:
    imageio_ffmpeg = None

try:
    import pystray
except Exception:
    pystray = None

try:
    from winotify import Notification, audio
except Exception:
    Notification = None
    audio = None

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except Exception:
    DND_FILES = None
    TkinterDnD = None
    DND_AVAILABLE = False

try:
    import comtypes
    from comtypes import GUID, IUnknown, COMMETHOD, HRESULT
    from comtypes.client import CreateObject
    from ctypes import wintypes, c_ulonglong
    COMTYPES_AVAILABLE = True
except Exception:
    COMTYPES_AVAILABLE = False


APP_NAME = "VIER-NEX Video Downloader"
APP_VERSION = "0.1.0"
APP_CREATOR = "Bryant Brugal"
APP_BRAND = "VIER-NEX"
APP_ID = "VIERNEX.VideoDownloader.4"

WHATSAPP_TARGET_MB = 170
DEFAULT_CUSTOM_TARGET_MB = 100

ROOT_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
USER_DATA = Path.home() / "AppData" / "Local" / "VIER-NEX Video Downloader"
DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads" / "VIER-NEX Videos"
HISTORY_FILE = USER_DATA / "history.json"
SETTINGS_FILE = USER_DATA / "settings.json"
QUEUE_FILE = USER_DATA / "queue.json"
LOG_FILE = USER_DATA / "viernex.log"
BACKGROUND_NOTICE_SENTINEL = USER_DATA / ".background_notice_shown"

APP_HOST = "127.0.0.1"
APP_PORT = 43661
ICON_ICO = ROOT_DIR / "VIERNEX_icon.ico"
ICON_PNG = ROOT_DIR / "VIERNEX_icon.png"

APP_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
MANUAL_PDF = APP_DIR / "VIER-NEX_Manual_de_Usuario.pdf"

BG = "#07101f"
HEADER = "#081525"
PANEL = "#0b1728"
PANEL_2 = "#0e1d31"
CARD = "#102239"
BORDER = "#1c3a57"
TEXT = "#f4f7fb"
MUTED = "#8ba3ba"
CYAN = "#20dfff"
BLUE = "#2b85ff"
PURPLE = "#8b55ff"
GREEN = "#2dd978"
YELLOW = "#ffcc3a"
RED = "#ff5d69"
ORANGE = "#ff9f43"

# Resize rendering strategy:
# The native Tk host follows Windows immediately. The expensive CustomTkinter
# workspace is resized at a capped cadence instead of once per WM_SIZE event.
BODY_RESIZE_FRAME_MS = 48
BODY_RESIZE_IDLE_MS = 150
BODY_MAX_WIDTH = 1540

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Native vector icon font included with Windows 10/11.
ICON_FONT = "Segoe MDL2 Assets"

ICONS = {
    "link": "\uE71B",
    "info": "\uE946",
    "clock": "\uE823",
    "download": "\uE896",
    "settings": "\uE713",
    "folder": "\uE8B7",
    "play": "\uE768",
    "up": "\uE70E",
    "display": "\uE7F4",
    "audio": "\uE767",
    "chat": "\uE8BD",
    "list": "\uE8FD",
    "progress": "\uE895",
}


# ---------------- Windows taskbar progress ----------------
if COMTYPES_AVAILABLE:
    try:
        class ITaskbarList(IUnknown):
            _iid_ = GUID("{56FDF342-FD6D-11D0-958A-006097C9A090}")
            _methods_ = [
                COMMETHOD([], HRESULT, "HrInit"),
                COMMETHOD([], HRESULT, "AddTab", (["in"], wintypes.HWND, "hwnd")),
                COMMETHOD([], HRESULT, "DeleteTab", (["in"], wintypes.HWND, "hwnd")),
                COMMETHOD([], HRESULT, "ActivateTab", (["in"], wintypes.HWND, "hwnd")),
                COMMETHOD([], HRESULT, "SetActiveAlt", (["in"], wintypes.HWND, "hwnd")),
            ]

        class ITaskbarList2(ITaskbarList):
            _iid_ = GUID("{602D4995-B13A-429B-A66E-1935E44F4317}")
            _methods_ = [
                COMMETHOD([], HRESULT, "MarkFullscreenWindow",
                          (["in"], wintypes.HWND, "hwnd"),
                          (["in"], wintypes.BOOL, "fFullscreen")),
            ]

        class ITaskbarList3(ITaskbarList2):
            _iid_ = GUID("{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}")
            _methods_ = [
                COMMETHOD([], HRESULT, "SetProgressValue",
                          (["in"], wintypes.HWND, "hwnd"),
                          (["in"], c_ulonglong, "ullCompleted"),
                          (["in"], c_ulonglong, "ullTotal")),
                COMMETHOD([], HRESULT, "SetProgressState",
                          (["in"], wintypes.HWND, "hwnd"),
                          (["in"], ctypes.c_int, "tbpFlags")),
            ]
    except Exception:
        COMTYPES_AVAILABLE = False

TBPF_NOPROGRESS = 0
TBPF_INDETERMINATE = 1
TBPF_NORMAL = 2
TBPF_ERROR = 4
TBPF_PAUSED = 8


class TaskbarProgress:
    def __init__(self, window):
        self.window = window
        self.obj = None
        if COMTYPES_AVAILABLE and os.name == "nt":
            try:
                clsid = GUID("{56FDF344-FD6D-11D0-958A-006097C9A090}")
                self.obj = CreateObject(clsid, interface=ITaskbarList3)
                self.obj.HrInit()
            except Exception:
                self.obj = None

    @property
    def hwnd(self):
        try:
            return int(self.window.winfo_id())
        except Exception:
            return 0

    def set(self, pct, state=TBPF_NORMAL):
        if not self.obj:
            return
        try:
            self.obj.SetProgressState(self.hwnd, state)
            self.obj.SetProgressValue(self.hwnd, int(max(0, min(100, pct))), 100)
        except Exception:
            pass

    def clear(self):
        if not self.obj:
            return
        try:
            self.obj.SetProgressState(self.hwnd, TBPF_NOPROGRESS)
        except Exception:
            pass


# ---------------- Helpers ----------------
def set_windows_app_id():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass


def safe_json_load(path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def safe_json_save(path, data):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def detect_platform(url: str) -> str:
    u = (url or "").lower().strip()
    mapping = [
        (("x.com", "twitter.com"), "Twitter / X"),
        (("tiktok.com",), "TikTok"),
        (("instagram.com",), "Instagram"),
        (("facebook.com", "fb.watch"), "Facebook"),
        (("reddit.com", "redd.it"), "Reddit"),
        (("youtube.com", "youtu.be"), "YouTube"),
        (("twitch.tv",), "Twitch"),
        (("vimeo.com",), "Vimeo"),
    ]
    for domains, name in mapping:
        if any(d in u for d in domains):
            return name
    try:
        host = urlparse(u).netloc.replace("www.", "")
        return host or "Sitio compatible"
    except Exception:
        return "Sitio compatible"



def is_facebook_url(url: str) -> bool:
    u = (url or "").lower()
    return "facebook.com" in u or "fb.watch" in u


def normalize_facebook_url(url: str) -> str:
    """Normalize Facebook hosts conservatively without changing the video id.

    - m/mobile/mbasic/web.facebook.com -> www.facebook.com
    - l.facebook.com/l.php?u=<real> extracts and decodes the real URL
    - fb.watch is preserved as-is (no invented canonical URL)
    - Only known tracking params (mibextid, s, ref) are removed;
      functional params (v, id, story_fbid, ...) are preserved.
    """
    value = (url or "").strip()
    if not value:
        return value
    try:
        parsed = urlparse(value)
    except Exception:
        return value
    if not parsed.scheme or not parsed.netloc:
        return value
    host = (parsed.hostname or "").lower()
    if not host:
        return value

    # l.facebook.com/l.php?u=<real-url>: unwrap once.
    if host == "l.facebook.com":
        try:
            qs = parse_qs(parsed.query)
            nested = (qs.get("u") or [""])[0]
            if nested:
                nested = unquote(nested).strip()
                if nested.startswith(("http://", "https://")):
                    return normalize_facebook_url(nested)
        except Exception:
            pass
        return value

    # fb.watch short links: preserve, do not invent a canonical URL.
    if host == "fb.watch" or host.endswith(".fb.watch"):
        return value

    new_host = None
    if host in ("m.facebook.com", "mobile.facebook.com", "mbasic.facebook.com",
                "web.facebook.com"):
        # Preserve possible port, rebuild netloc with www host.
        new_host = "www.facebook.com"
        if parsed.port:
            new_host = f"{new_host}:{parsed.port}"
        try:
            netloc = new_host
            # Preserve userinfo if present.
            if "@" in parsed.netloc:
                userinfo = parsed.netloc.rsplit("@", 1)[0]
                netloc = f"{userinfo}@{netloc}"
            parsed = parsed._replace(netloc=netloc)
            host = "www.facebook.com"
        except Exception:
            pass

    # Strip only known tracking params on facebook.com hosts.
    if host == "facebook.com" or host.endswith(".facebook.com"):
        try:
            pairs = parse_qsl(parsed.query, keep_blank_values=True)
            tracking = {"mibextid", "s", "ref"}
            kept = [(k, v) for k, v in pairs if k not in tracking]
            if len(kept) != len(pairs):
                new_query = urlencode(kept, doseq=True)
                parsed = parsed._replace(query=new_query)
        except Exception:
            pass
        try:
            return urlunparse(parsed)
        except Exception:
            return value
    try:
        return urlunparse(parsed)
    except Exception:
        return value


def _short_error(exc, limit: int = 180) -> str:
    """One-line error summary for logs/UI. Never includes cookies/tokens."""
    try:
        text = str(exc) if not isinstance(exc, str) else exc
    except Exception:
        text = "Error desconocido"
    text = " ".join((text or "").split())
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text or "Error desconocido"


def is_facebook_auth_error(message) -> bool:
    """True only for errors compatible with login/cookies/auth.

    Uses literal substrings plus word-boundary regex for log-in variants.
    Explicitly excludes errors that are clearly non-auth (invalid URL,
    unsupported extractor, network timeout, disk/write, FFmpeg) so those
    never trigger an automatic cookie retry.
    """
    try:
        text = str(message or "").lower()
    except Exception:
        return False
    if not text:
        return False

    non_auth_markers = (
        "unsupported url", "unsupported extractor", "no suitable extractor",
        "no video formats found",
        "not a valid url", "is not a valid url", "invalid url",
        "timed out", "timeout", "timedout", "network unreachable",
        "failed to resolve", "name resolution", "temporary failure",
        "connection reset", "connection aborted", "connection refused",
        "no space left", "disk full", "permission denied", "unable to write",
        "could not write", "could not open for writing",
        "ffmpeg", "ffprobe", "postprocessor", "post-processing",
        "no such file or directory",
    )
    # If the failure is clearly infrastructural, do not treat as auth
    # unless there is also an explicit login/cookie signal. Even then,
    # infrastructural causes win: cookies would not fix them.
    has_infra_marker = any(m in text for m in non_auth_markers)

    auth_substrings = (
        "login required",
        "login is required",
        "cookies required",
        "cookies needed",
        "need cookies",
        "pass cookies",
        "no cookies",
        "cookies were not",
        "authentication required",
        "authentication is required",
        "authorization required",
        "must be logged in",
        "you must log in",
        "please log in",
        "please login",
        "requires login",
        "require login",
        "logged-in",
        "not logged in",
    )
    has_auth_literal = any(m in text for m in auth_substrings)

    auth_regexes = (
        r"\blog\s*in\b",
        r"\bsign\s*in\b",
        r"\bsigned\s*in\b",
    )
    has_auth_regex = False
    try:
        for pattern in auth_regexes:
            if re.search(pattern, text):
                has_auth_regex = True
                break
    except Exception:
        has_auth_regex = False

    if not (has_auth_literal or has_auth_regex):
        return False
    if has_infra_marker:
        return False
    return True


def is_auth_error(message) -> bool:
    """Spec-required alias: same policy as is_facebook_auth_error."""
    return is_facebook_auth_error(message)


def is_facebook_private_error(message) -> bool:
    """True for private/removed/no-access content (no automatic cookie retry)."""
    try:
        text = str(message or "").lower()
    except Exception:
        return False
    if not text:
        return False
    # Technical format-selector failures are NOT private content.
    # e.g. "Requested format is not available" contains "not available"
    # but must fall through to UNSUPPORTED, never PRIVATE.
    format_markers = (
        "requested format",
        "requesting format",
        "format is not available",
        "format not available",
        "no suitable format",
        "no video formats found",
    )
    if any(m in text for m in format_markers):
        return False
    markers = (
        "this video is private",
        "video is private",
        "is private",
        "friends only",
        "only friends",
        "only me",
        "followers only",
        "has been removed",
        "has been deleted",
        "was removed",
        "was deleted",
        "no longer available",
        "not available",
        "isn't available",
        "isnt available",
        "unavailable",
        "content not found",
        "video unavailable",
        "no tienes acceso",
        "no esta disponible",
        "no está disponible",
        "contenido no disponible",
        "eliminado",
        "privado",
    )
    return any(m in text for m in markers)


def _classify_facebook_error(detail) -> str:
    """Classify final Facebook failure: 'auth' | 'private' | 'unsupported'."""
    if is_facebook_auth_error(detail):
        return "auth"
    if is_facebook_private_error(detail):
        return "private"
    return "unsupported"


def resolve_facebook_share_url(url: str, timeout: float = 8.0, log=None) -> str:
    """
    Resolve fb.watch / Facebook share redirects to the final URL.
    Never raises: on any failure the normalized original URL is returned
    so yt-dlp can still try it. Optional log(msg) callback records whether
    the URL was resolved, unchanged, or failed to resolve.
    """
    value = normalize_facebook_url(url)
    if not value:
        return value

    def _emit(msg: str):
        try:
            if log is not None:
                log(msg)
        except Exception:
            pass

    try:
        req = urllib.request.Request(
            value,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/152.0.0.0 Safari/537.36"
                )
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            resolved = response.geturl()
        normalized = normalize_facebook_url(resolved or value)
        if normalized and normalized != value:
            _emit(f"Facebook: enlace resuelto a {normalized[:120]}")
            return normalized
        _emit("Facebook: el enlace no requirió resolución adicional.")
        return value
    except Exception as exc:
        _emit(
            "Facebook: no se pudo resolver la redirección, "
            f"se usará el enlace original. Detalle: {_short_error(exc)}"
        )
        return value


def prepare_facebook_url(url: str, timeout: float = 8.0, log=None) -> str:
    """Single URL pipeline shared by Analizar and Descargar.

    Non-Facebook URLs are returned stripped and untouched.
    """
    raw = (url or "").strip()
    if not raw:
        return raw
    if not is_facebook_url(raw):
        return raw
    return resolve_facebook_share_url(raw, timeout=timeout, log=log)


def format_mb(value):
    if value is None:
        return "Desconocido"
    try:
        return f"{float(value):.1f} MB"
    except Exception:
        return "Desconocido"


def bytes_to_mb(value):
    try:
        return value / (1024 * 1024)
    except Exception:
        return None


def human_duration(seconds):
    try:
        seconds = int(seconds)
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"
    except Exception:
        return "Desconocida"


def open_path(path):
    try:
        os.startfile(str(path))
        return True
    except Exception:
        return False


def copy_to_clipboard(root, text):
    try:
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        return True
    except Exception:
        return False


def is_url(text):
    return isinstance(text, str) and text.strip().startswith(("http://", "https://"))


def ui_logo_image(size=(44, 44), crop_ratio=0.18):
    """
    Reuse the existing VIERNEX_icon.png for internal UI branding,
    but crop away most of the outer neon frame so it reads like a logo
    instead of a large Windows app tile.
    No additional image file is created.
    """
    try:
        im = Image.open(ICON_PNG).convert("RGBA")
        w, h = im.size
        cx = int(w * crop_ratio)
        cy = int(h * crop_ratio)
        cropped = im.crop((cx, cy, w - cx, h - cy))
        return ctk.CTkImage(cropped, size=size)
    except Exception:
        return None


def current_ytdlp_version():
    try:
        from yt_dlp.version import __version__
        return __version__
    except Exception:
        return "No disponible"


def latest_ytdlp_version(timeout=4):
    try:
        req = urllib.request.Request(
            "https://pypi.org/pypi/yt-dlp/json",
            headers={"User-Agent": APP_NAME}
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data["info"]["version"]
    except Exception:
        return None


# ---------------- Optional DnD root ----------------
if DND_AVAILABLE:
    class BaseRoot(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            ctk.CTk.__init__(self, *args, **kwargs)
            try:
                self.TkdndVersion = TkinterDnD._require(self)
            except Exception:
                pass
else:
    class BaseRoot(ctk.CTk):
        pass


def make_clickable_cursor(widget):
    """Use the Windows hand cursor on clickable CustomTkinter cards/labels."""
    try:
        widget.configure(cursor="hand2")
    except Exception:
        pass

    # CustomTkinter widgets may render through internal tkinter canvases/labels.
    for attr in ("_canvas", "_text_label", "_label"):
        try:
            child = getattr(widget, attr, None)
            if child is not None:
                child.configure(cursor="hand2")
        except Exception:
            pass


class DurationCard(ctk.CTkFrame):
    def __init__(self, master, icon, title, key, callback, accent):
        super().__init__(
            master,
            fg_color="#142c42",
            corner_radius=12,
            border_width=0,
            height=66
        )
        self.key = key
        self.callback = callback
        self.accent = accent
        self._selected = False
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)

        self.icon_label = ctk.CTkLabel(
            self,
            text=icon,
            text_color=accent,
            font=ctk.CTkFont(family=ICON_FONT, size=21)
        )
        self.icon_label.grid(row=0, column=0, pady=(9, 1))

        self.title_label = ctk.CTkLabel(
            self,
            text=title,
            text_color=TEXT,
            font=ctk.CTkFont(size=15, weight="bold")
        )
        self.title_label.grid(row=1, column=0, pady=(0, 8))

        for widget in (self, self.icon_label, self.title_label):
            make_clickable_cursor(widget)
            widget.bind("<Button-1>", lambda e: self.callback(self.key))
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

    def _on_enter(self, _event=None):
        if self._selected:
            self.configure(fg_color="#117989")
        else:
            self.configure(fg_color="#1c405a")
        self.icon_label.configure(text_color="#ffffff")
        self.title_label.configure(text_color="#ffffff")

    def _on_leave(self, _event=None):
        self.select(self._selected)

    def select(self, active):
        self._selected = active
        self.configure(fg_color="#0b6674" if active else "#142c42")
        self.icon_label.configure(text_color="#ffffff" if active else self.accent)
        self.title_label.configure(text_color=TEXT)


class ModeCard(ctk.CTkFrame):
    def __init__(self, master, title, subtitle, icon, key, callback, accent):
        super().__init__(
            master,
            fg_color="#142c42",
            corner_radius=12,
            border_width=0,
            height=98
        )
        self.key = key
        self.callback = callback
        self.accent = accent
        self._selected = False
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)

        self.icon_label = ctk.CTkLabel(
            self,
            text=icon,
            text_color=accent,
            font=ctk.CTkFont(family=ICON_FONT, size=22)
        )
        self.icon_label.grid(row=0, column=0, pady=(9, 0))

        self.title_label = ctk.CTkLabel(
            self,
            text=title,
            text_color=TEXT,
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.title_label.grid(row=1, column=0, pady=(0, 1))

        self.subtitle_label = ctk.CTkLabel(
            self,
            text=subtitle,
            text_color=MUTED,
            font=ctk.CTkFont(size=11),
            wraplength=190,
            justify="center"
        )
        self.subtitle_label.grid(row=2, column=0, sticky="n", padx=8, pady=(2, 10))

        for widget in (self, self.icon_label, self.title_label, self.subtitle_label):
            make_clickable_cursor(widget)
            widget.bind("<Button-1>", lambda e: self.callback(self.key))
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)

    def _on_enter(self, _event=None):
        if self._selected:
            self.configure(fg_color="#117989")
        else:
            self.configure(fg_color="#1c405a")
        self.icon_label.configure(text_color="#ffffff")
        self.title_label.configure(text_color="#ffffff")
        self.subtitle_label.configure(text_color="#dcecff")

    def _on_leave(self, _event=None):
        self.select(self._selected)

    def select(self, active):
        self._selected = active
        self.configure(fg_color="#0b6371" if active else "#142c42")
        self.icon_label.configure(text_color="#ffffff" if active else self.accent)
        self.title_label.configure(text_color=TEXT)
        self.subtitle_label.configure(text_color=MUTED)


class VierNexApp(BaseRoot):
    def __init__(self):
        super().__init__()
        set_windows_app_id()
        USER_DATA.mkdir(parents=True, exist_ok=True)
        DEFAULT_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

        self.settings_data = safe_json_load(SETTINGS_FILE, {})
        self.history = safe_json_load(HISTORY_FILE, [])
        self.jobs = safe_json_load(QUEUE_FILE, [])
        # Never revive jobs as actively downloading after restart.
        for job in self.jobs:
            if job.get("status") in ("downloading", "analyzing", "compressing"):
                job["status"] = "queued"

        self.uiq = queue.Queue()
        self.worker_thread = None
        self.stop_worker = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.cancel_current = False
        self.current_job_id = None

        # UI performance throttling.
        # Rebuilding CustomTkinter panels on every progress callback makes
        # window resizing/maximizing noticeably heavier.
        self._last_queue_refresh = 0.0
        self._queue_refresh_pending = False
        self._last_progress_ui_update = 0.0
        self._resize_in_progress = False
        self._resize_after_id = None
        self._body_resize_job = None
        self._body_resize_target = None
        self._body_current_size = None
        self.body_host = None
        self.body = None

        self.tray_icon = None
        self.tray_thread = None
        self.about_win = None
        self.clipboard_stop = threading.Event()
        self.clipboard_thread = None
        self.last_clipboard_url = ""

        self.mode_var = ctk.StringVar(value=self.settings_data.get("mode", "whatsapp"))
        self.clip_duration_var = ctk.StringVar(value=self.settings_data.get("clip_duration", "full"))
        self.custom_target_var = ctk.StringVar(value=str(self.settings_data.get("custom_target_mb", DEFAULT_CUSTOM_TARGET_MB)))
        self.url_var = ctk.StringVar()
        self.platform_var = ctk.StringVar(value="Esperando enlace...")
        self.folder_var = ctk.StringVar(value=self.settings_data.get("folder", str(DEFAULT_DOWNLOAD_DIR)))
        self.cookies_var = ctk.BooleanVar(value=self.settings_data.get("cookies", False))
        self.open_folder_var = ctk.BooleanVar(value=self.settings_data.get("open_folder", True))
        self.clip_monitor_var = ctk.BooleanVar(value=self.settings_data.get("clip_monitor", True))
        self.clip_notify_var = ctk.BooleanVar(value=self.settings_data.get("clip_notify", True))
        self.start_windows_var = ctk.BooleanVar(value=self.settings_data.get("start_windows", False))

        # The background notice must be truly one-time across launches/versions.
        # Use both settings.json and a dedicated sentinel file for robustness.
        self.background_notice_shown = bool(
            self.settings_data.get("background_notice_shown", False)
            or BACKGROUND_NOTICE_SENTINEL.exists()
        )

        self._restoring_from_tray = False
        self._tray_saved_geometry = None
        self._tray_saved_state = "normal"
        self._instance_server = None
        self._instance_thread = None
        self.status_var = ctk.StringVar(value="Listo")

        self.analysis_title = ctk.StringVar(value="Sin analizar")
        self.analysis_meta = ctk.StringVar(value="Pega un enlace y pulsa Analizar.")
        self.analysis_size = ctk.StringVar(value="Tamaño estimado: —")
        self.analysis_output = ctk.StringVar(value="Salida estimada: —")

        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1220x760")
        self.minsize(1080, 700)
        self.configure(fg_color=BG)

        try:
            self.iconbitmap(str(ICON_ICO))
        except Exception:
            pass

        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

        self._build_ui()
        self.taskbar = TaskbarProgress(self)
        self._select_mode(self.mode_var.get())
        self._refresh_queue()
        self._refresh_recent()
        self._init_drag_drop()
        self._try_clipboard_once()
        self._start_instance_listener()

        self.after(125, self._poll_uiq)
        self.after(600, self._start_tray)
        self.after(900, self._start_clipboard_monitor)
        self.after(1200, self._ensure_worker)

    def _schedule_body_layout(self, event):
        # Compatibility alias. Resize events now come only from the lightweight
        # native body host instead of the CTk root and all heavy descendants.
        self._on_body_host_configure(event)

    def _on_body_host_configure(self, event):
        if self.body is None or self._restoring_from_tray:
            return
        if event.width < 100 or event.height < 100:
            return

        self._resize_in_progress = True
        self._body_resize_target = (int(event.width), int(event.height))

        # Coalesce a stream of WM_SIZE events. Never cancel the frame callback:
        # it will consume the latest target size at a stable cadence.
        if self._body_resize_job is None:
            self._body_resize_job = self.after(
                BODY_RESIZE_FRAME_MS,
                self._apply_coalesced_body_resize
            )

        # Separate idle detector: only this timer is reset on every event.
        if self._resize_after_id is not None:
            try:
                self.after_cancel(self._resize_after_id)
            except Exception:
                pass

        self._resize_after_id = self.after(
            BODY_RESIZE_IDLE_MS,
            self._finish_resize
        )

    def _apply_coalesced_body_resize(self, force=False):
        self._body_resize_job = None
        if self.body is None or self._body_resize_target is None:
            return

        host_w, host_h = self._body_resize_target
        content_w = min(host_w, BODY_MAX_WIDTH)
        content_h = host_h
        x = max(0, (host_w - content_w) // 2)

        target = (content_w, content_h, x)
        if force or target != self._body_current_size:
            # Important: CTk width/height belong in configure(), never in
            # place()/place_configure().
            self.body.configure(width=content_w, height=content_h)
            self.body.place_configure(x=x, y=0)
            self._body_current_size = target

        # If Windows produced a newer target while CTk was repainting, schedule
        # exactly one more frame. This bounds repaint frequency.
        if self._resize_in_progress and self.body_host is not None:
            current = (
                int(self.body_host.winfo_width()),
                int(self.body_host.winfo_height())
            )
            if current != self._body_resize_target and current[0] >= 100 and current[1] >= 100:
                self._body_resize_target = current
                self._body_resize_job = self.after(
                    BODY_RESIZE_FRAME_MS,
                    self._apply_coalesced_body_resize
                )

    def _finish_resize(self):
        self._resize_after_id = None

        # Snap once to the exact final native-host size.
        if self.body_host is not None:
            final_w = int(self.body_host.winfo_width())
            final_h = int(self.body_host.winfo_height())
            if final_w >= 100 and final_h >= 100:
                self._body_resize_target = (final_w, final_h)

        self._apply_coalesced_body_resize(force=True)
        self._resize_in_progress = False

        try:
            self._schedule_queue_refresh(min_interval=0.08)
        except Exception:
            pass

    def _prime_body_layout(self):
        if self.body_host is None:
            return
        self.update_idletasks()
        w = int(self.body_host.winfo_width())
        h = int(self.body_host.winfo_height())
        if w >= 100 and h >= 100:
            self._body_resize_target = (w, h)
            self._apply_coalesced_body_resize(force=True)

    def _on_window_configure(self, event):
        # Kept only for backwards compatibility with older internal calls.
        if self.body_host is not None and event.widget is self.body_host:
            self._on_body_host_configure(event)


    # ---------------- Layout ----------------
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color=HEADER, height=82, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)

        icon_img = ui_logo_image(size=(46, 46), crop_ratio=0.20)
        ico = ctk.CTkLabel(header, text="", image=icon_img)
        ico.image = icon_img
        ico.grid(row=0, column=0, rowspan=2, padx=(16, 9), pady=16)

        ctk.CTkLabel(
            header, text="VIER-NEX", text_color=CYAN,
            font=ctk.CTkFont(size=24, weight="bold")
        ).grid(row=0, column=1, sticky="sw", pady=(12, 0))
        ctk.CTkLabel(
            header, text="Video Downloader", text_color=TEXT,
            font=ctk.CTkFont(size=16, weight="bold")
        ).grid(row=1, column=1, sticky="nw", pady=(0, 12))

        quick = ctk.CTkFrame(header, fg_color="transparent")
        quick.grid(row=0, column=2, rowspan=2, padx=(18, 8))
        for i, (txt, sub, color) in enumerate([
            ("⚡", "Rápido", YELLOW),
            ("✓", "Local", GREEN),
            ("◆", "Universal", PURPLE)
        ]):
            c = ctk.CTkFrame(quick, fg_color="#0b1c31", corner_radius=12, border_width=1, border_color=BORDER)
            c.grid(row=0, column=i, padx=4)
            ctk.CTkLabel(c, text=txt, text_color=color, font=ctk.CTkFont(size=14, weight="bold")).pack(padx=12, pady=(5, 0))
            ctk.CTkLabel(c, text=sub, text_color=MUTED, font=ctk.CTkFont(size=9)).pack(padx=8, pady=(0, 5))

        ctk.CTkButton(
            header,
            text="Acerca de",
            width=92,
            height=34,
            corner_radius=10,
            fg_color="#173955",
            hover_color="#214c6d",
            border_width=1,
            border_color="#285274",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._about
        ).grid(row=0, column=3, rowspan=2, padx=(0, 18), pady=22)

        # Native host follows the Windows resize loop immediately. The heavy
        # CustomTkinter workspace inside it does NOT receive every intermediate
        # pixel-size event; it is updated at a capped cadence.
        self.body_host = tk.Frame(
            self,
            bg=BG,
            bd=0,
            highlightthickness=0
        )
        self.body_host.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=18,
            pady=(0, 18)
        )
        self.body_host.bind("<Configure>", self._on_body_host_configure)

        self.body = ctk.CTkFrame(
            self.body_host,
            fg_color=BG,
            corner_radius=0,
            border_width=0,
            width=1184,
            height=660
        )
        self.body.place(x=0, y=0)
        self.body.grid_propagate(False)

        body = self.body
        body.grid_columnconfigure(0, weight=3, minsize=590)
        body.grid_columnconfigure(1, weight=2, minsize=410)
        body.grid_rowconfigure(0, weight=1)

        # First exact geometry pass after Tk has measured the native host.
        self.after_idle(self._prime_body_layout)

        left = ctk.CTkScrollableFrame(
            body,
            fg_color="transparent",
            scrollbar_button_color="#16304b"
        )
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_columnconfigure(0, weight=1)

        right = ctk.CTkFrame(body, fg_color=PANEL, corner_radius=16, border_width=1, border_color=BORDER)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(3, weight=1)

        self._build_url(left)
        self._build_analysis(left)
        self._build_clip_duration(left)
        self._build_modes(left)
        self._build_options(left)
        self._build_folder(left)
        self._build_actions(left)
        self._build_progress(left)
        self._build_log(left)

        self._build_clipboard(right)
        self._build_queue(right)
        self._build_recent(right)
        self._build_right_footer(right)

    def _section(self, parent, title, icon=None, icon_color=CYAN):
        f = ctk.CTkFrame(
            parent,
            fg_color=PANEL,
            corner_radius=12,
            border_width=1,
            border_color=BORDER
        )
        f.grid(sticky="ew", padx=2, pady=4)
        f.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(f, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 5))

        if icon:
            ctk.CTkLabel(
                header,
                text=icon,
                text_color=icon_color,
                font=ctk.CTkFont(family=ICON_FONT, size=16)
            ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            header,
            text=title,
            text_color=TEXT,
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left")

        return f


    def _build_url(self, parent):
        f = self._section(parent, "Enlace del video", ICONS["link"], CYAN)
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 6))
        row.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(
            row, textvariable=self.url_var, height=38,
            fg_color="#07111e", border_color="#294966",
            placeholder_text="Pega un enlace de una red social o sitio compatible..."
        )
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 7))
        self.url_entry.bind("<KeyRelease>", lambda e: self._update_platform())

        ctk.CTkButton(
            row, text="Pegar", width=82, height=38,
            fg_color="#0d3f4c", hover_color="#12596a",
            border_width=1, border_color=CYAN,
            command=self._paste
        ).grid(row=0, column=1, padx=3)

        ctk.CTkButton(
            row, text="Analizar", width=86, height=38,
            fg_color="#173955", hover_color="#214c6d",
            command=self._analyze_current
        ).grid(row=0, column=2, padx=(3, 0))

        meta = ctk.CTkFrame(f, fg_color="transparent")
        meta.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 8))
        ctk.CTkLabel(meta, text="Plataforma:", text_color=MUTED, font=ctk.CTkFont(size=11)).pack(side="left")
        ctk.CTkLabel(
            meta, textvariable=self.platform_var,
            fg_color="#0d2534", corner_radius=8,
            text_color=GREEN, font=ctk.CTkFont(size=11, weight="bold")
        ).pack(side="left", padx=7, ipadx=7, ipady=2)

        ctk.CTkLabel(
            meta, text="Arrastra enlaces o videos directamente a la ventana",
            text_color=MUTED, font=ctk.CTkFont(size=9)
        ).pack(side="right")

    def _build_analysis(self, parent):
        f = self._section(parent, "Información previa", ICONS["info"], BLUE)
        box = ctk.CTkFrame(f, fg_color=PANEL_2, corner_radius=11)
        box.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        box.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            box, textvariable=self.analysis_title, text_color=CYAN,
            font=ctk.CTkFont(size=14, weight="bold"), anchor="w"
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(6, 1))
        ctk.CTkLabel(
            box, textvariable=self.analysis_meta, text_color=MUTED,
            font=ctk.CTkFont(size=12), anchor="w", wraplength=620
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=2)
        ctk.CTkLabel(
            box, textvariable=self.analysis_size, text_color=TEXT,
            font=ctk.CTkFont(size=14, weight="bold"), anchor="w"
        ).grid(row=2, column=0, sticky="ew", padx=12, pady=(1, 6))
        ctk.CTkLabel(
            box, textvariable=self.analysis_output, text_color=GREEN,
            font=ctk.CTkFont(size=12, weight="bold"), anchor="e"
        ).grid(row=2, column=1, sticky="ew", padx=12, pady=(1, 6))

    def _build_clip_duration(self, parent):
        f = self._section(parent, "Duración de Video", ICONS["clock"], YELLOW)

        row = ctk.CTkFrame(f, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=10, pady=(1, 9))
        for i in range(6):
            row.grid_columnconfigure(i, weight=1, uniform="durationtiles")

        specs = [
            (ICONS["play"], "Full", "full", GREEN),
            (ICONS["clock"], "15 seg", "15", CYAN),
            (ICONS["clock"], "30 seg", "30", BLUE),
            (ICONS["clock"], "1 min", "60", PURPLE),
            (ICONS["clock"], "3 min", "180", ORANGE),
            (ICONS["clock"], "5 min", "300", RED),
        ]

        self.clip_buttons = {}
        for i, (icon, label, value, accent) in enumerate(specs):
            card = DurationCard(
                row,
                icon,
                label,
                value,
                self._select_clip_duration,
                accent
            )
            card.grid(row=0, column=i, sticky="nsew", padx=3)
            self.clip_buttons[value] = card

        self._refresh_clip_buttons()


    def _select_clip_duration(self, value):
        self.clip_duration_var.set(value)
        self._refresh_clip_buttons()
        self._save_settings()
        self._refresh_analysis_output_estimate()

    def _refresh_clip_buttons(self):
        selected = self.clip_duration_var.get()
        for value, card in getattr(self, "clip_buttons", {}).items():
            card.select(value == selected)


    def _clip_seconds(self, value=None):
        value = value if value is not None else self.clip_duration_var.get()
        if value in (None, "", "full"):
            return None
        try:
            return max(1, int(value))
        except Exception:
            return None

    def _clip_label(self, value=None):
        seconds = self._clip_seconds(value)
        if seconds is None:
            return "Full"
        labels = {
            15: "15 seg",
            30: "30 seg",
            60: "1 min",
            180: "3 min",
            300: "5 min",
        }
        return labels.get(seconds, f"{seconds} seg")

    def _build_modes(self, parent):
        f = self._section(parent, "Modo de descarga", ICONS["download"], CYAN)

        grid = ctk.CTkFrame(f, fg_color="transparent")
        grid.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))
        for i in range(3):
            grid.grid_columnconfigure(i, weight=1, uniform="modecards")

        specs = [
            ("WhatsApp", "~170 MB", ICONS["chat"], "whatsapp", GREEN),
            ("Auto", "Calidad inteligente", ICONS["settings"], "smart", CYAN),
            ("Máxima", "Mejor disponible", ICONS["up"], "max", BLUE),
            ("1080p", "Full HD", ICONS["display"], "1080", CYAN),
            ("720p", "HD", ICONS["display"], "720", YELLOW),
            ("MP3", "Solo audio", ICONS["audio"], "mp3", PURPLE),
        ]

        self.mode_cards = {}
        for i, spec in enumerate(specs):
            card = ModeCard(
                grid,
                spec[0], spec[1], spec[2], spec[3],
                self._select_mode, spec[4]
            )
            card.grid(
                row=i // 3,
                column=i % 3,
                sticky="nsew",
                padx=4,
                pady=4
            )
            self.mode_cards[spec[3]] = card

        custom = ctk.CTkFrame(f, fg_color="transparent")
        custom.grid(row=2, column=0, sticky="ew", padx=12, pady=(1, 8))

        ctk.CTkLabel(
            custom,
            text=ICONS["settings"],
            text_color=PURPLE,
            font=ctk.CTkFont(family=ICON_FONT, size=15)
        ).pack(side="left", padx=(2, 5))

        ctk.CTkButton(
            custom,
            text="Tamaño personalizado",
            width=160,
            height=30,
            corner_radius=9,
            fg_color="#4d2d8d",
            hover_color="#6741b1",
            border_width=0,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=lambda: self._select_mode("custom")
        ).pack(side="left")

        self.custom_entry = ctk.CTkEntry(
            custom,
            textvariable=self.custom_target_var,
            width=70,
            height=30,
            fg_color="#07111e",
            border_color="#6045a5",
            font=ctk.CTkFont(size=11)
        )
        self.custom_entry.pack(side="left", padx=(7, 3))

        ctk.CTkLabel(
            custom, text="MB", text_color=MUTED,
            font=ctk.CTkFont(size=11)
        ).pack(side="left")

        ctk.CTkLabel(
            custom, text="50 · 100 · 250 · 500",
            text_color=MUTED,
            font=ctk.CTkFont(size=9)
        ).pack(side="left", padx=10)


    def _build_options(self, parent):
        f = self._section(parent, "Opciones", ICONS["settings"], PURPLE)
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkSwitch(
            row, text="Usar sesión del navegador", variable=self.cookies_var,
            font=ctk.CTkFont(size=12),
            progress_color=CYAN, command=self._save_settings
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkSwitch(
            row, text="Abrir carpeta al terminar", variable=self.open_folder_var,
            font=ctk.CTkFont(size=12),
            progress_color=CYAN, command=self._save_settings
        ).grid(row=0, column=1, sticky="w")

    def _build_folder(self, parent):
        f = self._section(parent, "Carpeta de salida", ICONS["folder"], YELLOW)
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(
            row, textvariable=self.folder_var, height=36,
            fg_color="#07111e", border_color="#294966"
        ).grid(row=0, column=0, sticky="ew", padx=(0, 7))
        ctk.CTkButton(row, text="Cambiar", width=74, height=36, fg_color="#173955", command=self._choose_folder).grid(row=0, column=1, padx=3)
        ctk.CTkButton(row, text="Abrir", width=68, height=36, fg_color="#173955", command=self._open_folder).grid(row=0, column=2, padx=(3, 0))

    def _build_actions(self, parent):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(sticky="ew", padx=2, pady=5)
        f.grid_columnconfigure(0, weight=3)
        f.grid_columnconfigure((1, 2), weight=1)

        self.download_btn = ctk.CTkButton(
            f, text="↓  DESCARGAR / AÑADIR A COLA", height=42,
            fg_color=BLUE, hover_color="#1c6fe4",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._enqueue_current
        )
        self.download_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(
            f, text="Lote", height=42, fg_color="#4d2d8d",
            hover_color="#6741b1", command=self._batch_dialog
        ).grid(row=0, column=1, sticky="ew", padx=4)
        ctk.CTkButton(
            f, text="Comprimir", height=42, fg_color="#4d2d8d",
            hover_color="#6741b1", command=self._compress_existing
        ).grid(row=0, column=2, sticky="ew", padx=(4, 0))

    def _build_progress(self, parent):
        f = self._section(parent, "◉  Progreso actual")
        self.progress = ctk.CTkProgressBar(
            f, height=10, progress_color=PURPLE, fg_color="#07111e"
        )
        self.progress.grid(row=1, column=0, sticky="ew", padx=14, pady=(1, 6))
        self.progress.set(0)

        actions = ctk.CTkFrame(f, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 4))
        actions.grid_columnconfigure(0, weight=1)

        self.progress_label = ctk.CTkLabel(
            actions, text="0%", text_color=CYAN,
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.progress_label.grid(row=0, column=0, sticky="w")

        self.pause_btn = ctk.CTkButton(
            actions, text="Pausar", width=70, height=28,
            fg_color="#564b20", hover_color="#74672b",
            command=self._toggle_pause
        )
        self.pause_btn.grid(row=0, column=1, padx=4)

        ctk.CTkButton(
            actions, text="Cancelar", width=70, height=28,
            fg_color="#5a2630", hover_color="#74313d",
            command=self._cancel
        ).grid(row=0, column=2, padx=(4, 0))

        ctk.CTkLabel(
            f, textvariable=self.status_var, text_color=MUTED, anchor="w"
        ).grid(row=3, column=0, sticky="ew", padx=14, pady=(1, 10))

    def _build_log(self, parent):
        f = self._section(parent, "≡  Actividad / Log")
        self.log_box = ctk.CTkTextbox(
            f, height=105, fg_color="#07111e",
            border_width=1, border_color="#183550",
            text_color="#a9c3d9", font=("Consolas", 10)
        )
        self.log_box.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
        self._log(f"VIER-NEX v{APP_VERSION} listo.")

    def _build_clipboard(self, right):
        head = ctk.CTkFrame(right, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 5))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            head, text="Panel rápido", text_color=CYAN,
            font=ctk.CTkFont(size=20, weight="bold")
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            head, text="⚙", width=34, height=28, fg_color="#173955",
            command=self._settings
        ).grid(row=0, column=1)

        f = ctk.CTkFrame(right, fg_color=PANEL_2, corner_radius=12, border_width=1, border_color=BORDER)
        f.grid(row=1, column=0, sticky="ew", padx=14, pady=6)
        f.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            f, text="Portapapeles inteligente", text_color=TEXT,
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=11, pady=(10, 2))
        ctk.CTkSwitch(
            f, text="", variable=self.clip_monitor_var,
            width=40, progress_color=CYAN,
            command=self._save_settings
        ).grid(row=0, column=1, padx=10, pady=(10, 2))

        self.clip_label = ctk.CTkLabel(
            f, text="Sin enlace detectado", text_color=MUTED,
            anchor="w", justify="left", wraplength=430,
            font=ctk.CTkFont(size=12)
        )
        self.clip_label.grid(row=1, column=0, columnspan=2, sticky="ew", padx=11, pady=5)

        buttons = ctk.CTkFrame(f, fg_color="transparent")
        buttons.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(3, 10))
        for i in range(3):
            buttons.grid_columnconfigure(i, weight=1)
        ctk.CTkButton(
            buttons, text="Descargar", height=34, fg_color=BLUE,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._enqueue_clipboard(False)
        ).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ctk.CTkButton(
            buttons, text="WhatsApp", height=34, fg_color="#176d42",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._enqueue_clipboard(True)
        ).grid(row=0, column=1, sticky="ew", padx=3)
        ctk.CTkButton(
            buttons, text="Ignorar", height=34, fg_color="#27394d",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._ignore_clipboard
        ).grid(row=0, column=2, sticky="ew", padx=(3, 0))

    def _build_queue(self, right):
        f = ctk.CTkFrame(right, fg_color=PANEL_2, corner_radius=12, border_width=1, border_color=BORDER)
        f.grid(row=2, column=0, sticky="ew", padx=14, pady=6)
        f.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            f, text="Cola de descargas", text_color=TEXT,
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=11, pady=(9, 3))
        ctk.CTkButton(
            f, text="Limpiar terminadas", width=120, height=30,
            font=ctk.CTkFont(size=11),
            fg_color="#27394d", command=self._clear_finished
        ).grid(row=0, column=1, padx=10, pady=(9, 3))

        self.queue_frame = ctk.CTkScrollableFrame(f, fg_color="transparent", height=180)
        self.queue_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=7, pady=(0, 8))
        self.queue_frame.grid_columnconfigure(0, weight=1)

    def _build_recent(self, right):
        f = ctk.CTkFrame(right, fg_color=PANEL_2, corner_radius=12, border_width=1, border_color=BORDER)
        f.grid(row=3, column=0, sticky="nsew", padx=14, pady=6)
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            f, text="Descargas recientes", text_color=TEXT,
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=11, pady=(9, 3))
        ctk.CTkButton(
            f, text="Historial", width=76, height=30,
            font=ctk.CTkFont(size=11),
            fg_color="#173955", command=self._history_window
        ).grid(row=0, column=1, padx=10, pady=(9, 3))

        self.recent_frame = ctk.CTkScrollableFrame(f, fg_color="transparent")
        self.recent_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=7, pady=(0, 8))
        self.recent_frame.grid_columnconfigure(0, weight=1)

    def _build_right_footer(self, right):
        f = ctk.CTkFrame(right, fg_color="#091a2a", corner_radius=12, border_width=1, border_color="#25506f")
        f.grid(row=4, column=0, sticky="ew", padx=14, pady=(6, 14))
        ctk.CTkLabel(
            f, text="Bandeja + Windows", text_color=CYAN,
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=11, pady=(8, 1))
        ctk.CTkLabel(
            f,
            text="Cerrar = minimizar a bandeja · doble clic = abrir\nNotificaciones + progreso en barra de tareas cuando Windows lo permite.",
            text_color=MUTED, justify="left", font=ctk.CTkFont(size=10)
        ).pack(anchor="w", padx=11, pady=(0, 8))

    # ---------------- Settings / persistence ----------------
    def _save_settings(self):
        safe_json_save(SETTINGS_FILE, {
            "mode": self.mode_var.get(),
            "clip_duration": self.clip_duration_var.get(),
            "custom_target_mb": self._target_mb(),
            "folder": self.folder_var.get(),
            "cookies": bool(self.cookies_var.get()),
            "open_folder": bool(self.open_folder_var.get()),
            "clip_monitor": bool(self.clip_monitor_var.get()),
            "clip_notify": bool(self.clip_notify_var.get()),
            "start_windows": bool(self.start_windows_var.get()),
            "background_notice_shown": bool(self.background_notice_shown),
        })

        if self.background_notice_shown:
            try:
                USER_DATA.mkdir(parents=True, exist_ok=True)
                if not BACKGROUND_NOTICE_SENTINEL.exists():
                    BACKGROUND_NOTICE_SENTINEL.write_text(
                        "VIER-NEX background notice shown.\n",
                        encoding="utf-8"
                    )
            except Exception:
                pass

    def _save_queue(self):
        safe_json_save(QUEUE_FILE, self.jobs)

    def _target_mb(self, mode=None):
        mode = mode or self.mode_var.get()
        if mode == "whatsapp":
            return WHATSAPP_TARGET_MB
        if mode == "custom":
            try:
                return max(10, int(float(self.custom_target_var.get().strip())))
            except Exception:
                return DEFAULT_CUSTOM_TARGET_MB
        return None

    def _select_mode(self, key):
        self.mode_var.set(key)
        for k, card in self.mode_cards.items():
            card.select(k == key)
        if key == "custom":
            self.custom_entry.configure(border_color=PURPLE)
        else:
            self.custom_entry.configure(border_color="#6045a5")
        self._save_settings()
        self._refresh_analysis_output_estimate()

    # ---------------- User interactions ----------------
    def _update_platform(self):
        u = self.url_var.get().strip()
        self.platform_var.set(detect_platform(u) if u else "Esperando enlace...")

    def _paste(self):
        try:
            u = self.clipboard_get().strip()
            self.url_var.set(u)
            self._update_platform()
        except Exception:
            pass

    def _choose_folder(self):
        d = filedialog.askdirectory(initialdir=self.folder_var.get() or str(DEFAULT_DOWNLOAD_DIR))
        if d:
            self.folder_var.set(d)
            self._save_settings()

    def _open_folder(self):
        p = Path(self.folder_var.get().strip() or DEFAULT_DOWNLOAD_DIR)
        p.mkdir(parents=True, exist_ok=True)
        open_path(p)

    def _log(self, text):
        stamp = time.strftime("%H:%M:%S")
        line = f"[{stamp}] {text}"
        try:
            self.log_box.insert("end", line + "\n")
            self.log_box.see("end")
        except Exception:
            pass
        try:
            USER_DATA.mkdir(parents=True, exist_ok=True)
            with LOG_FILE.open("a", encoding="utf-8") as fp:
                fp.write(line + "\n")
        except Exception:
            pass

    # ---------------- Analyze ----------------
    def _analyze_current(self):
        u = self.url_var.get().strip()
        if not is_url(u):
            messagebox.showwarning(APP_NAME, "Pega un enlace válido primero.")
            return
        self.analysis_title.set("Analizando...")
        self.analysis_meta.set("Consultando información del video.")
        self.analysis_size.set("Tamaño estimado: —")
        self.analysis_output.set("Salida estimada: —")
        threading.Thread(target=self._analyze_worker, args=(u,), daemon=True).start()

    def _analyze_worker(self, url):
        if yt_dlp is None:
            self.uiq.put(("analysis_error", "yt-dlp no está disponible."))
            return
        try:
            raw = (url or "").strip()
            fb = is_facebook_url(raw)
            if fb:
                target_url = prepare_facebook_url(
                    raw, log=lambda m: self.uiq.put(("log", m))
                )
            else:
                target_url = raw
            use_cookies = bool(self.cookies_var.get())

            def _run_analyze(target, browser):
                aopts = {
                    "quiet": True,
                    "skip_download": True,
                    "noplaylist": True,
                }
                if browser:
                    aopts["cookiesfrombrowser"] = (browser,)
                with yt_dlp.YoutubeDL(aopts) as ydl:
                    return ydl.extract_info(target, download=False)

            info = None
            if fb and use_cookies:
                errors = []
                for browser in ("chrome", "edge"):
                    try:
                        info = _run_analyze(target_url, browser)
                        break
                    except Exception as exc:
                        errors.append(str(exc))
                        self.uiq.put(
                            ("log", f"Facebook {browser} analyze failed: {_short_error(exc)}")
                        )
                if info is None:
                    detail = errors[-1] if errors else "Facebook rechazó el enlace."
                    kind = _classify_facebook_error(detail)
                    if kind == "auth":
                        raise RuntimeError(
                            "Facebook requiere una sesión válida. "
                            "Inicia sesión en Facebook en Chrome o Edge y vuelve a intentarlo. "
                            f"Detalle: {detail}"
                        )
                    if kind == "private":
                        raise RuntimeError(
                            "El video de Facebook es privado, fue eliminado o tu cuenta no tiene acceso. "
                            f"Detalle: {detail}"
                        )
                    raise RuntimeError(
                        "Facebook no permitió descargar este enlace. "
                        "Actualiza el motor yt-dlp o prueba con el enlace directo del video. "
                        f"Detalle: {detail}"
                    )
            elif fb and not use_cookies:
                try:
                    info = _run_analyze(target_url, None)
                except Exception as first_exc:
                    first_err = str(first_exc)
                    if not is_facebook_auth_error(first_err):
                        kind = _classify_facebook_error(first_err)
                        if kind == "private":
                            raise RuntimeError(
                                "El video de Facebook es privado, fue eliminado o tu cuenta no tiene acceso. "
                                f"Detalle: {first_err}"
                            )
                        raise RuntimeError(
                            "Facebook no permitió descargar este enlace. "
                            "Actualiza el motor yt-dlp o prueba con el enlace directo del video. "
                            f"Detalle: {first_err}"
                        )
                    self.uiq.put(("log", "Facebook authentication required; retrying with Chrome"))
                    try:
                        info = _run_analyze(target_url, "chrome")
                    except Exception as chrome_exc:
                        self.uiq.put(
                            ("log", f"Facebook Chrome attempt failed: {_short_error(chrome_exc)}")
                        )
                        self.uiq.put(("log", "Facebook retrying with Edge"))
                        try:
                            info = _run_analyze(target_url, "edge")
                        except Exception as edge_exc:
                            detail = str(edge_exc)
                            kind = _classify_facebook_error(detail)
                            if kind == "auth":
                                raise RuntimeError(
                                    "Facebook requiere una sesión válida. "
                                    "Inicia sesión en Facebook en Chrome o Edge y vuelve a intentarlo. "
                                    f"Detalle: {detail}"
                                )
                            if kind == "private":
                                raise RuntimeError(
                                    "El video de Facebook es privado, fue eliminado o tu cuenta no tiene acceso. "
                                    f"Detalle: {detail}"
                                )
                            raise RuntimeError(
                                "Facebook no permitió descargar este enlace. "
                                "Actualiza el motor yt-dlp o prueba con el enlace directo del video. "
                                f"Detalle: {detail}"
                            )
            else:
                opts = {
                    "quiet": True,
                    "skip_download": True,
                    "noplaylist": True,
                }
                if use_cookies:
                    opts["cookiesfrombrowser"] = ("chrome",)
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(target_url, download=False)

            title = info.get("title") or "Video"
            duration = info.get("duration")
            width = info.get("width")
            height = info.get("height")
            resolution = f"{width}×{height}" if width and height else (info.get("resolution") or "Resolución variable")
            size = info.get("filesize") or info.get("filesize_approx")
            size_mb = bytes_to_mb(size)
            if size_mb is None:
                # Estimate from bitrate when possible.
                tbr = info.get("tbr")
                if tbr and duration:
                    size_mb = (float(tbr) * 1000 / 8 * float(duration)) / (1024 * 1024)

            data = {
                "title": title,
                "duration": duration,
                "resolution": resolution,
                "size_mb": size_mb,
                "platform": detect_platform(url),
            }
            self.uiq.put(("analysis", data))
        except Exception as e:
            self.uiq.put(("analysis_error", str(e)))

    def _refresh_analysis_output_estimate(self):
        target = self._target_mb()
        clip = self._clip_label()
        if target:
            self.analysis_output.set(f"Clip: {clip} · Salida objetivo: ~{target} MB")
        else:
            self.analysis_output.set(f"Clip: {clip} · Salida según calidad")

    def _schedule_queue_refresh(self, min_interval=0.50):
        """
        Avoid destroying/recreating the whole queue panel for every yt-dlp
        progress callback. During a window resize, defer the refresh until the
        resize watcher marks the window idle again.
        """
        if self._resize_in_progress:
            if not self._queue_refresh_pending:
                self._queue_refresh_pending = True
                self.after(180, self._run_scheduled_queue_refresh)
            return

        now = time.monotonic()
        elapsed = now - self._last_queue_refresh

        if elapsed >= min_interval:
            self._last_queue_refresh = now
            self._queue_refresh_pending = False
            self._refresh_queue()
            return

        if not self._queue_refresh_pending:
            self._queue_refresh_pending = True
            delay_ms = max(40, int((min_interval - elapsed) * 1000))
            self.after(delay_ms, self._run_scheduled_queue_refresh)

    def _run_scheduled_queue_refresh(self):
        if self._resize_in_progress:
            self.after(200, self._run_scheduled_queue_refresh)
            return
        self._queue_refresh_pending = False
        self._last_queue_refresh = time.monotonic()
        self._refresh_queue()

    # ---------------- Queue ----------------
    def _job_from_url(self, url, mode=None):
        return {
            "id": uuid.uuid4().hex[:10],
            "url": url.strip(),
            "platform": detect_platform(url),
            "mode": mode or self.mode_var.get(),
            "clip_duration": self.clip_duration_var.get(),
            "clip_seconds": self._clip_seconds(),
            "target_mb": self._target_mb(mode or self.mode_var.get()),
            "folder": self.folder_var.get().strip() or str(DEFAULT_DOWNLOAD_DIR),
            "cookies": bool(self.cookies_var.get()),
            "status": "queued",
            "progress": 0,
            "name": "",
            "error": "",
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _enqueue_current(self):
        u = self.url_var.get().strip()
        if not is_url(u):
            messagebox.showwarning(APP_NAME, "Pega un enlace válido.")
            return
        self.jobs.append(self._job_from_url(u))
        self._save_queue()
        self._refresh_queue()
        self._log(f"Añadido a cola: {detect_platform(u)}")
        self._ensure_worker()

    def _batch_dialog(self):
        win = ctk.CTkToplevel(self)
        win.title("Descargas por lote")
        win.geometry("680x480")
        win.configure(fg_color=BG)
        try:
            win.iconbitmap(str(ICON_ICO))
        except Exception:
            pass
        ctk.CTkLabel(
            win, text="Descargas por lote", text_color=CYAN,
            font=ctk.CTkFont(size=21, weight="bold")
        ).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(
            win, text="Pega un enlace por línea. Todos usarán el modo seleccionado actualmente.",
            text_color=MUTED
        ).pack(anchor="w", padx=18, pady=(0, 8))
        tb = ctk.CTkTextbox(win, fg_color="#07111e", border_width=1, border_color=BORDER)
        tb.pack(fill="both", expand=True, padx=18, pady=8)

        def add():
            lines = [x.strip() for x in tb.get("1.0", "end").splitlines() if is_url(x.strip())]
            for u in lines:
                self.jobs.append(self._job_from_url(u))
            self._save_queue()
            self._refresh_queue()
            self._ensure_worker()
            win.destroy()
            self._log(f"Lote añadido: {len(lines)} enlace(s).")

        ctk.CTkButton(win, text="Añadir a cola", fg_color=BLUE, command=add).pack(fill="x", padx=18, pady=(4, 16))

    def _ensure_worker(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        if not any(j.get("status") in ("queued", "retry") for j in self.jobs):
            return
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

    def _worker_loop(self):
        while not self.stop_worker.is_set():
            job = next((j for j in self.jobs if j.get("status") in ("queued", "retry")), None)
            if not job:
                break
            self.current_job_id = job["id"]
            self.cancel_current = False
            self.pause_event.set()
            job["status"] = "downloading"
            job["progress"] = 0
            self._save_queue()
            self.uiq.put(("queue_refresh",))
            self.uiq.put(("job_start", job))
            try:
                record = self._download_job(job)
                job["status"] = "done"
                job["progress"] = 100
                self.history.insert(0, record)
                self.history = self.history[:200]
                safe_json_save(HISTORY_FILE, self.history)
                self.uiq.put(("job_done", job, record))
            except Exception as e:
                if self.cancel_current:
                    job["status"] = "cancelled"
                    job["error"] = "Cancelado por el usuario."
                    self.uiq.put(("job_cancelled", job))
                else:
                    job["status"] = "error"
                    job["error"] = str(e)
                    self.uiq.put(("job_error", job, str(e)))
            finally:
                self._save_queue()
                self.uiq.put(("queue_refresh",))
                self.current_job_id = None
                self.cancel_current = False
                self.pause_event.set()

    def _download_job(self, job):
        if yt_dlp is None or imageio_ffmpeg is None:
            raise RuntimeError("Faltan yt-dlp o FFmpeg.")

        folder = Path(job["folder"])
        folder.mkdir(parents=True, exist_ok=True)
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        mode = job["mode"]
        clip_seconds = job.get("clip_seconds")

        def hook(data):
            while not self.pause_event.is_set():
                if self.cancel_current:
                    raise yt_dlp.utils.DownloadCancelled("Cancelado")
                time.sleep(0.15)
            if self.cancel_current:
                raise yt_dlp.utils.DownloadCancelled("Cancelado")
            status = data.get("status")
            if status == "downloading":
                raw = re.sub(r"\x1b\[[0-9;]*m", "", data.get("_percent_str", "") or "")
                try:
                    pct = float(raw.replace("%", "").strip())
                except Exception:
                    pct = 0
                job["progress"] = pct
                speed = re.sub(r"\x1b\[[0-9;]*m", "", data.get("_speed_str", "") or "")
                eta = re.sub(r"\x1b\[[0-9;]*m", "", data.get("_eta_str", "") or "")
                self.uiq.put(("progress", job["id"], pct, f"{speed} · ETA {eta}".strip(" ·")))
            elif status == "finished":
                self.uiq.put(("status", "Procesando archivo..."))

        fmt = self._format_for_mode(mode)
        clip_suffix = ""
        if clip_seconds:
            clip_suffix = f" - Clip {self._clip_label(str(clip_seconds))}"

        opts = {
            "outtmpl": str(folder / f"%(title)s [%(id)s]{clip_suffix}.%(ext)s"),
            "format": fmt,
            "windowsfilenames": True,
            "noplaylist": True,
            "progress_hooks": [hook],
            "quiet": True,
            "ffmpeg_location": ffmpeg,
        }

        if clip_seconds:
            if download_range_func is None:
                raise RuntimeError("La versión instalada de yt-dlp no soporta descarga por rango.")
            opts["download_ranges"] = download_range_func(None, [(0, float(clip_seconds))])
            opts["force_keyframes_at_cuts"] = True

        if mode == "mp3":
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        else:
            opts["merge_output_format"] = "mp4"

        original_url = (job.get("url") or "").strip()
        fb = is_facebook_url(original_url)
        if fb:
            self.uiq.put(("status", "Preparando enlace de Facebook..."))
            download_url = prepare_facebook_url(
                original_url, log=lambda m: self.uiq.put(("log", m))
            )
        else:
            download_url = original_url

        def run_ytdlp_attempt(target_url, browser=None):
            attempt_opts = dict(opts)
            if browser:
                attempt_opts["cookiesfrombrowser"] = (browser,)
            elif "cookiesfrombrowser" in attempt_opts:
                attempt_opts.pop("cookiesfrombrowser", None)

            with yt_dlp.YoutubeDL(attempt_opts) as ydl:
                attempt_info = ydl.extract_info(target_url, download=True)
                attempt_prepared = Path(ydl.prepare_filename(attempt_info))
            return attempt_info, attempt_prepared

        def _facebook_final_error(detail: str):
            kind = _classify_facebook_error(detail)
            if kind == "auth":
                return RuntimeError(
                    "Facebook requiere una sesión válida. "
                    "Inicia sesión en Facebook en Chrome o Edge y vuelve a intentarlo. "
                    f"Detalle: {detail}"
                )
            if kind == "private":
                return RuntimeError(
                    "El video de Facebook es privado, fue eliminado o tu cuenta no tiene acceso. "
                    f"Detalle: {detail}"
                )
            return RuntimeError(
                "Facebook no permitió descargar este enlace. "
                "Actualiza el motor yt-dlp o prueba con el enlace directo del video. "
                f"Detalle: {detail}"
            )

        info = None
        prepared = None
        errors = []

        if not fb:
            # Non-Facebook behavior unchanged.
            if job.get("cookies"):
                attempts = [(download_url, "chrome")]
            else:
                attempts = [(download_url, None)]
            for attempt_url, browser in attempts:
                try:
                    info, prepared = run_ytdlp_attempt(attempt_url, browser)
                    break
                except Exception as exc:
                    errors.append(str(exc))
                    continue
            if info is None or prepared is None:
                raise RuntimeError(errors[-1] if errors else "No se pudo descargar el video.")
        elif job.get("cookies"):
            # Facebook + session ON: Chrome, Edge fallback.
            for idx, browser in enumerate(("chrome", "edge"), start=1):
                try:
                    self.uiq.put(("log", f"Facebook attempt {idx}/2: {browser}"))
                    self.uiq.put(("status", f"Facebook: descargando con sesión de {browser.title()}..."))
                    info, prepared = run_ytdlp_attempt(download_url, browser)
                    break
                except Exception as exc:
                    errors.append(str(exc))
                    self.uiq.put(("log", f"Facebook {browser.title()} attempt failed: {_short_error(exc)}"))
                    if browser == "chrome":
                        self.uiq.put(("log", "Facebook retrying with Edge"))
                    continue
            if info is None or prepared is None:
                detail = errors[-1] if errors else "Facebook rechazó el enlace."
                raise _facebook_final_error(detail)
        else:
            # Facebook + session OFF: public first, cookies only on auth error.
            self.uiq.put(("log", "Facebook attempt 1/3: public"))
            try:
                info, prepared = run_ytdlp_attempt(download_url, None)
            except Exception as first_exc:
                first_err = str(first_exc)
                errors.append(first_err)
                self.uiq.put(("log", f"Facebook public attempt failed: {_short_error(first_err)}"))
                if not is_facebook_auth_error(first_err):
                    raise _facebook_final_error(first_err)
                self.uiq.put(("log", "Facebook authentication required; retrying with Chrome"))
                self.uiq.put(("status", "Facebook: reintentando con sesión de Chrome..."))
                try:
                    self.uiq.put(("log", "Facebook attempt 2/3: chrome"))
                    info, prepared = run_ytdlp_attempt(download_url, "chrome")
                except Exception as chrome_exc:
                    chrome_err = str(chrome_exc)
                    errors.append(chrome_err)
                    self.uiq.put(("log", f"Facebook Chrome attempt failed: {_short_error(chrome_err)}"))
                    self.uiq.put(("log", "Facebook retrying with Edge"))
                    self.uiq.put(("status", "Facebook: reintentando con sesión de Edge..."))
                    try:
                        self.uiq.put(("log", "Facebook attempt 3/3: edge"))
                        info, prepared = run_ytdlp_attempt(download_url, "edge")
                    except Exception as edge_exc:
                        edge_err = str(edge_exc)
                        errors.append(edge_err)
                        self.uiq.put(("log", f"Facebook Edge attempt failed: {_short_error(edge_err)}"))
                        raise _facebook_final_error(edge_err)

        duration = float(info.get("duration") or 0)

        candidates = [prepared]
        for ext in (".mp4", ".mkv", ".webm", ".mov", ".mp3"):
            candidates.append(prepared.with_suffix(ext))
        candidates = [p for p in candidates if p.exists()]
        if not candidates:
            raise RuntimeError("No pude localizar el archivo descargado.")
        src = max(candidates, key=lambda p: p.stat().st_mtime)

        final = src
        target = job.get("target_mb")
        if mode in ("whatsapp", "custom") and src.suffix.lower() != ".mp3":
            job["status"] = "compressing"
            self.uiq.put(("queue_refresh",))
            self.uiq.put(("status", f"Comprimiendo a ~{target} MB..."))
            final = self._compress_to_target(src, duration, ffmpeg, folder, int(target))

        return {
            "id": uuid.uuid4().hex[:10],
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "platform": job["platform"],
            "url": job["url"],
            "file": str(final),
            "name": final.name,
            "size_mb": round(final.stat().st_size / (1024 * 1024), 1),
            "mode": mode,
            "clip_duration": job.get("clip_duration", "full"),
            "clip_seconds": clip_seconds,
        }

    def _format_for_mode(self, mode):
        if mode == "smart":
            return "bestvideo[width<=1920][height<=1920]+bestaudio/best[width<=1920][height<=1920]/best"
        if mode == "1080":
            return "bestvideo[width<=1920][height<=1920]+bestaudio/best[width<=1920][height<=1920]/best"
        if mode == "720":
            return "bestvideo[width<=1280][height<=1280]+bestaudio/best[width<=1280][height<=1280]/best"
        if mode == "mp3":
            return "ba/b"
        if mode in ("whatsapp", "custom"):
            return "bestvideo[width<=1920][height<=1920]+bestaudio/best[width<=1920][height<=1920]/best"
        return "bv*+ba/b"

    def _compress_to_target(self, src, duration, ffmpeg, folder, target_mb):
        current_mb = src.stat().st_size / (1024 * 1024)
        self.uiq.put(("log", f"Tamaño original: {current_mb:.1f} MB"))
        if current_mb <= target_mb and src.suffix.lower() == ".mp4":
            self.uiq.put(("log", "El archivo ya cumple el tamaño objetivo."))
            return src
        if duration <= 0:
            duration = self._probe_duration(src, ffmpeg)
        if duration <= 0:
            raise RuntimeError("No pude obtener la duración del video.")

        safe_target = max(10, target_mb) * 0.94
        target_bits = safe_target * 1024 * 1024 * 8
        audio_kbps = 128 if target_mb >= 80 else 96
        video_kbps = max(180, int((target_bits / duration) / 1000 - audio_kbps))

        suffix = "WhatsApp" if target_mb == WHATSAPP_TARGET_MB else f"{target_mb}MB"
        out = folder / f"{src.stem} - {suffix}.mp4"
        temp = folder / f"{src.stem} - {suffix}.temp.mp4"

        cmd = [
            ffmpeg, "-y", "-i", str(src),
            "-vf", "scale='min(1280,iw)':-2",
            "-c:v", "libx264", "-preset", "medium",
            "-b:v", f"{video_kbps}k",
            "-maxrate", f"{int(video_kbps * 1.10)}k",
            "-bufsize", f"{int(video_kbps * 2)}k",
            "-c:a", "aac", "-b:a", f"{audio_kbps}k",
            "-movflags", "+faststart",
            str(temp)
        ]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        p = subprocess.run(cmd, capture_output=True, text=True, creationflags=flags)
        if p.returncode != 0 or not temp.exists():
            raise RuntimeError("FFmpeg no pudo comprimir el video.")
        if out.exists():
            out.unlink()
        temp.replace(out)

        final_mb = out.stat().st_size / (1024 * 1024)
        if final_mb > target_mb * 1.02:
            # One corrective pass.
            ratio = (target_mb * 0.94) / final_mb
            adjusted = max(160, int(video_kbps * ratio))
            temp2 = folder / f"{src.stem} - {suffix}.pass2.mp4"
            cmd2 = [
                ffmpeg, "-y", "-i", str(out),
                "-vf", "scale='min(1280,iw)':-2",
                "-c:v", "libx264", "-preset", "medium",
                "-b:v", f"{adjusted}k",
                "-maxrate", f"{int(adjusted * 1.08)}k",
                "-bufsize", f"{int(adjusted * 2)}k",
                "-c:a", "aac", "-b:a", f"{max(80, audio_kbps - 16)}k",
                "-movflags", "+faststart",
                str(temp2)
            ]
            p2 = subprocess.run(cmd2, capture_output=True, text=True, creationflags=flags)
            if p2.returncode == 0 and temp2.exists():
                out.unlink(missing_ok=True)
                temp2.replace(out)

        self.uiq.put(("log", f"Archivo final: {out.stat().st_size/(1024*1024):.1f} MB"))
        return out

    def _probe_duration(self, src, ffmpeg):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        p = subprocess.run([ffmpeg, "-i", str(src)], capture_output=True, text=True, creationflags=flags)
        m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", p.stderr or "")
        if not m:
            return 0
        return int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))

    def _toggle_pause(self):
        if not self.current_job_id:
            return
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_btn.configure(text="Continuar")
            self.status_var.set("Pausado")
            self.taskbar.set(50, TBPF_PAUSED)
        else:
            self.pause_event.set()
            self.pause_btn.configure(text="Pausar")
            self.status_var.set("Continuando...")

    def _cancel(self):
        if self.current_job_id:
            self.cancel_current = True
            self.pause_event.set()
            self.status_var.set("Cancelando...")

    def _retry_job(self, job_id):
        for j in self.jobs:
            if j["id"] == job_id:
                j["status"] = "retry"
                j["error"] = ""
                j["progress"] = 0
        self._save_queue()
        self._refresh_queue()
        self._ensure_worker()

    def _remove_job(self, job_id):
        if job_id == self.current_job_id:
            messagebox.showinfo(APP_NAME, "Cancela la descarga actual antes de eliminarla.")
            return
        self.jobs = [j for j in self.jobs if j["id"] != job_id]
        self._save_queue()
        self._refresh_queue()

    def _clear_finished(self):
        self.jobs = [j for j in self.jobs if j.get("status") not in ("done", "cancelled")]
        self._save_queue()
        self._refresh_queue()

    # ---------------- Existing file / DnD ----------------
    def _compress_existing(self, path=None):
        if imageio_ffmpeg is None:
            messagebox.showerror(APP_NAME, "FFmpeg no está disponible.")
            return
        if not path:
            path = filedialog.askopenfilename(
                title="Selecciona un video",
                filetypes=[("Videos", "*.mp4 *.mkv *.webm *.mov *.avi"), ("Todos", "*.*")]
            )
        if not path:
            return
        target = self._target_mb()
        if not target:
            target = WHATSAPP_TARGET_MB
        threading.Thread(target=self._compress_existing_worker, args=(Path(path), int(target)), daemon=True).start()

    def _compress_existing_worker(self, src, target):
        try:
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            duration = self._probe_duration(src, ffmpeg)
            self.uiq.put(("status", f"Comprimiendo archivo local a ~{target} MB..."))
            final = self._compress_to_target(src, duration, ffmpeg, src.parent, target)
            rec = {
                "id": uuid.uuid4().hex[:10],
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "platform": "Archivo local",
                "url": "",
                "file": str(final),
                "name": final.name,
                "size_mb": round(final.stat().st_size/(1024*1024), 1),
                "mode": "custom" if target != WHATSAPP_TARGET_MB else "whatsapp",
            }
            self.history.insert(0, rec)
            self.history = self.history[:200]
            safe_json_save(HISTORY_FILE, self.history)
            self.uiq.put(("local_done", rec))
        except Exception as e:
            self.uiq.put(("local_error", str(e)))

    def _init_drag_drop(self):
        if not DND_AVAILABLE:
            return
        try:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass

    def _on_drop(self, event):
        try:
            items = list(self.tk.splitlist(event.data))
        except Exception:
            items = [event.data]
        urls = []
        local_files = []
        for raw in items:
            item = raw.strip().strip("{}")
            if is_url(item):
                urls.append(item)
            elif Path(item).exists():
                local_files.append(item)
        for u in urls:
            self.jobs.append(self._job_from_url(u))
        for f in local_files:
            suffix = Path(f).suffix.lower()
            if suffix in (".mp4", ".mkv", ".webm", ".mov", ".avi"):
                self._compress_existing(f)
        if urls:
            self._save_queue()
            self._refresh_queue()
            self._ensure_worker()
            self._log(f"Drag & Drop: {len(urls)} enlace(s) añadido(s).")

    # ---------------- Clipboard ----------------
    def _start_clipboard_monitor(self):
        if self.clipboard_thread and self.clipboard_thread.is_alive():
            return
        self.clipboard_thread = threading.Thread(target=self._clipboard_loop, daemon=True)
        self.clipboard_thread.start()

    def _clipboard_loop(self):
        while not self.clipboard_stop.is_set():
            try:
                if self.clip_monitor_var.get():
                    text = self.clipboard_get().strip()
                    if is_url(text) and text != self.last_clipboard_url:
                        self.last_clipboard_url = text
                        self.uiq.put(("clipboard", text))
            except Exception:
                pass
            time.sleep(1.0)

    def _try_clipboard_once(self):
        try:
            text = self.clipboard_get().strip()
            if is_url(text):
                self.last_clipboard_url = text
                self.url_var.set(text)
                self._update_platform()
                self.clip_label.configure(text=text[:150])
        except Exception:
            pass

    def _enqueue_clipboard(self, whatsapp=False):
        u = self.last_clipboard_url
        if not is_url(u):
            self._try_clipboard_once()
            u = self.last_clipboard_url
        if not is_url(u):
            return
        mode = "whatsapp" if whatsapp else self.mode_var.get()
        self.jobs.append(self._job_from_url(u, mode=mode))
        self._save_queue()
        self._refresh_queue()
        self._ensure_worker()

    def _ignore_clipboard(self):
        self.clip_label.configure(text="Enlace ignorado.")
        self.last_clipboard_url = ""

    # ---------------- History UI ----------------
    def _refresh_recent(self):
        for w in self.recent_frame.winfo_children():
            w.destroy()
        if not self.history:
            ctk.CTkLabel(self.recent_frame, text="Aún no hay descargas.", text_color=MUTED).grid(row=0, column=0, sticky="w", padx=4, pady=7)
            return
        for i, rec in enumerate(self.history[:6]):
            row = ctk.CTkFrame(self.recent_frame, fg_color="#0a1828", corner_radius=9)
            row.grid(row=i, column=0, sticky="ew", pady=3)
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                row, text=(rec.get("name", "Archivo")[:58] + ("…" if len(rec.get("name", "Archivo")) > 58 else "")), text_color=TEXT,
                anchor="w", font=ctk.CTkFont(size=12, weight="bold")
            ).grid(row=0, column=0, sticky="ew", padx=9, pady=(6, 0))
            ctk.CTkLabel(
                row, text=f'{rec.get("platform","")} · {rec.get("size_mb","?")} MB · {self._clip_label(rec.get("clip_duration","full"))}',
                text_color=MUTED, anchor="w", font=ctk.CTkFont(size=10)
            ).grid(row=1, column=0, sticky="ew", padx=9, pady=(0, 6))
            ctk.CTkButton(
                row, text="Abrir", width=58, height=28, fg_color="#173955",
                font=ctk.CTkFont(size=11),
                command=lambda p=rec.get("file", ""): open_path(Path(p)) if p else None
            ).grid(row=0, column=1, rowspan=2, padx=7)

    def _history_window(self):
        win = ctk.CTkToplevel(self)
        win.title("Historial")
        win.geometry("920x580")
        win.configure(fg_color=BG)
        try:
            win.iconbitmap(str(ICON_ICO))
        except Exception:
            pass
        ctk.CTkLabel(
            win, text="Historial de descargas", text_color=CYAN,
            font=ctk.CTkFont(size=21, weight="bold")
        ).pack(anchor="w", padx=18, pady=(15, 6))
        scroll = ctk.CTkScrollableFrame(win, fg_color=PANEL)
        scroll.pack(fill="both", expand=True, padx=18, pady=(0, 18))

        def redraw():
            for child in scroll.winfo_children():
                child.destroy()
            for rec in self.history:
                row = ctk.CTkFrame(scroll, fg_color=PANEL_2, corner_radius=10)
                row.pack(fill="x", pady=4)
                left = ctk.CTkFrame(row, fg_color="transparent")
                left.pack(side="left", fill="x", expand=True, padx=10, pady=8)
                ctk.CTkLabel(
                    left, text=rec.get("name", ""), text_color=TEXT,
                    anchor="w", font=ctk.CTkFont(size=11, weight="bold")
                ).pack(fill="x")
                ctk.CTkLabel(
                    left,
                    text=f'{rec.get("platform","")} · {rec.get("size_mb","?")} MB · {self._clip_label(rec.get("clip_duration","full"))} · {rec.get("time","")}',
                    text_color=MUTED, anchor="w", font=ctk.CTkFont(size=9)
                ).pack(fill="x")

                ctk.CTkButton(row, text="Abrir", width=56, command=lambda r=rec: open_path(Path(r.get("file","")))).pack(side="left", padx=3)
                ctk.CTkButton(row, text="Carpeta", width=60, fg_color="#173955",
                              command=lambda r=rec: open_path(Path(r.get("file","")).parent)).pack(side="left", padx=3)
                if rec.get("url"):
                    ctk.CTkButton(row, text="Copiar URL", width=72, fg_color="#4d2d8d",
                                  command=lambda r=rec: copy_to_clipboard(self, r.get("url",""))).pack(side="left", padx=3)
                    ctk.CTkButton(row, text="Repetir", width=58, fg_color="#176d42",
                                  command=lambda r=rec: self._redownload_record(r)).pack(side="left", padx=3)
                ctk.CTkButton(row, text="Quitar", width=55, fg_color="#5a2630",
                              command=lambda r=rec: self._remove_history_record(r, redraw)).pack(side="left", padx=(3, 8))

        redraw()

    def _redownload_record(self, rec):
        if rec.get("url"):
            job = self._job_from_url(rec["url"], mode=rec.get("mode") or "max")
            job["clip_duration"] = rec.get("clip_duration", "full")
            job["clip_seconds"] = rec.get("clip_seconds")
            self.jobs.append(job)
            self._save_queue()
            self._refresh_queue()
            self._ensure_worker()

    def _remove_history_record(self, rec, redraw=None):
        rid = rec.get("id")
        self.history = [x for x in self.history if x.get("id") != rid]
        safe_json_save(HISTORY_FILE, self.history)
        self._refresh_recent()
        if redraw:
            redraw()

    # ---------------- Queue UI ----------------
    def _refresh_queue(self):
        for w in self.queue_frame.winfo_children():
            w.destroy()
        visible = self.jobs[-8:]
        if not visible:
            ctk.CTkLabel(self.queue_frame, text="Cola vacía.", text_color=MUTED).grid(row=0, column=0, sticky="w", padx=4, pady=7)
            return
        status_colors = {
            "queued": MUTED, "downloading": CYAN, "compressing": PURPLE,
            "done": GREEN, "error": RED, "cancelled": ORANGE, "retry": YELLOW
        }
        for i, job in enumerate(visible):
            row = ctk.CTkFrame(self.queue_frame, fg_color="#0a1828", corner_radius=6)
            row.grid(row=i, column=0, sticky="ew", pady=3)
            row.grid_columnconfigure(0, weight=1)
            clip_text = self._clip_label(job.get("clip_duration", "full"))
            title = job.get("name") or f'{job.get("platform","")} · {job.get("mode","")} · {clip_text}'
            ctk.CTkLabel(
                row, text=title, text_color=TEXT, anchor="w",
                font=ctk.CTkFont(size=12, weight="bold")
            ).grid(row=0, column=0, sticky="ew", padx=10, pady=(9, 2))
            status = job.get("status", "queued")
            ctk.CTkLabel(
                row, text=f'{status.upper()} · {job.get("progress",0):.0f}%',
                text_color=status_colors.get(status, MUTED),
                font=ctk.CTkFont(size=10, weight="bold")
            ).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 9))
            if status in ("error", "cancelled"):
                ctk.CTkButton(
                    row, text="↻", width=32, height=28, fg_color="#564b20",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    command=lambda jid=job["id"]: self._retry_job(jid)
                ).grid(row=0, column=1, rowspan=2, padx=2)
            if job["id"] != self.current_job_id:
                ctk.CTkButton(
                    row, text="×", width=32, height=28, fg_color="#5a2630",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    command=lambda jid=job["id"]: self._remove_job(jid)
                ).grid(row=0, column=2, rowspan=2, padx=(2, 6))

    # ---------------- Single instance / IPC ----------------
    def _start_instance_listener(self):
        if self._instance_server is not None:
            return
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((APP_HOST, APP_PORT))
            server.listen(5)
            self._instance_server = server
        except OSError:
            self._instance_server = None
            return

        self._instance_thread = threading.Thread(
            target=self._instance_server_loop,
            daemon=True
        )
        self._instance_thread.start()

    def _instance_server_loop(self):
        while not self.stop_worker.is_set():
            try:
                self._instance_server.settimeout(1.0)
                conn, _addr = self._instance_server.accept()
            except socket.timeout:
                continue
            except Exception:
                break

            try:
                with conn:
                    msg = conn.recv(1024).decode("utf-8", errors="ignore").strip().upper()
            except Exception:
                msg = ""

            if msg == "SHOW":
                self.after(0, self._show_existing_instance)

    def _show_existing_instance(self):
        try:
            if self.state() == "withdrawn":
                self.show_from_tray()
                return
        except Exception:
            pass

        try:
            self.deiconify()
        except Exception:
            pass
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    # ---------------- Notifications / tray ----------------
    def _notify(self, title, message, folder=None):
        sent = False
        if Notification is not None and os.name == "nt":
            try:
                toast = Notification(
                    app_id=APP_NAME,
                    title=title,
                    msg=message,
                    duration="short",
                    icon=str(ICON_PNG)
                )
                if folder:
                    try:
                        launch = Path(folder).resolve().as_uri()
                        toast.add_actions(label="Abrir carpeta", launch=launch)
                    except Exception:
                        pass
                try:
                    if audio:
                        toast.set_audio(audio.Default, loop=False)
                except Exception:
                    pass
                toast.show()
                sent = True
            except Exception:
                sent = False
        if not sent and self.tray_icon:
            try:
                self.tray_icon.notify(message, title)
            except Exception:
                pass

    def _tray_image(self):
        try:
            return Image.open(ICON_PNG).convert("RGBA")
        except Exception:
            img = Image.new("RGBA", (64,64), (7,16,31,255))
            d = ImageDraw.Draw(img)
            d.polygon([(16,18),(28,18),(32,31),(36,18),(48,18),(32,49)], fill=(32,223,255,255))
            return img

    def _start_tray(self):
        if pystray is None or self.tray_icon is not None:
            return
        menu = pystray.Menu(
            pystray.MenuItem("Abrir VIER-NEX", lambda icon,item: self.after(0, self.show_from_tray), default=True),
            pystray.MenuItem("Pegar y descargar", lambda icon,item: self.after(0, lambda: self._enqueue_clipboard(False))),
            pystray.MenuItem("Descargar para WhatsApp", lambda icon,item: self.after(0, lambda: self._enqueue_clipboard(True))),
            pystray.MenuItem("Comprimir archivo", lambda icon,item: self.after(0, self._compress_existing)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Historial", lambda icon,item: self.after(0, self._history_window)),
            pystray.MenuItem("Abrir carpeta", lambda icon,item: self.after(0, self._open_folder)),
            pystray.MenuItem("Ajustes", lambda icon,item: self.after(0, self._settings)),
            pystray.MenuItem("Acerca de", lambda icon,item: self.after(0, self._about)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", lambda icon,item: self.after(0, self.exit_app)),
        )
        self.tray_icon = pystray.Icon("VIERNEXVideoDownloader", self._tray_image(), APP_NAME, menu)
        self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self.tray_thread.start()

    def hide_to_tray(self):
        try:
            self._tray_saved_state = self.state()
        except Exception:
            self._tray_saved_state = "normal"

        try:
            if self._tray_saved_state != "zoomed":
                self._tray_saved_geometry = self.geometry()
        except Exception:
            self._tray_saved_geometry = None

        self.withdraw()

        if not self.background_notice_shown:
            self.background_notice_shown = True
            try:
                USER_DATA.mkdir(parents=True, exist_ok=True)
                BACKGROUND_NOTICE_SENTINEL.write_text(
                    "VIER-NEX background notice shown.\n",
                    encoding="utf-8"
                )
            except Exception:
                pass

            self._save_settings()
            self._notify(
                APP_NAME,
                "VIER-NEX continúa ejecutándose en segundo plano desde la bandeja del sistema."
            )

    def show_from_tray(self):
        if self._restoring_from_tray:
            return

        self._restoring_from_tray = True

        try:
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
        except Exception:
            screen_w, screen_h = 1920, 1080

        # Paint outside the visible desktop first.
        try:
            self.state("normal")
        except Exception:
            pass

        try:
            self.geometry(f"1220x760+{screen_w + 120}+{max(0, screen_h // 8)}")
        except Exception:
            pass

        self.deiconify()

        try:
            self.update_idletasks()
        except Exception:
            pass

        self.after(70, self._finish_show_from_tray)

    def _finish_show_from_tray(self):
        try:
            self.update_idletasks()
        except Exception:
            pass

        try:
            if self._tray_saved_state == "zoomed":
                self.state("zoomed")
            elif self._tray_saved_geometry:
                self.geometry(self._tray_saved_geometry)
            else:
                self.geometry("1220x760")
        except Exception:
            pass

        try:
            self.update_idletasks()
        except Exception:
            pass

        self.lift()
        self.focus_force()
        self._restoring_from_tray = False


    # ---------------- Settings / About / updates ----------------
    def _settings(self):
        win = ctk.CTkToplevel(self)
        win.title("Ajustes")
        win.geometry("610x500")
        win.configure(fg_color=BG)
        try:
            win.iconbitmap(str(ICON_ICO))
        except Exception:
            pass

        ctk.CTkLabel(
            win, text="Ajustes", text_color=CYAN,
            font=ctk.CTkFont(size=25, weight="bold")
        ).pack(anchor="w", padx=20, pady=(17, 8))

        box = ctk.CTkFrame(win, fg_color=PANEL, corner_radius=14)
        box.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        ctk.CTkSwitch(
            box, text="Notificar cuando se detecte un enlace",
            variable=self.clip_notify_var, progress_color=CYAN,
            command=self._save_settings
        ).pack(anchor="w", padx=16, pady=(16, 7))

        ctk.CTkSwitch(
            box, text="Iniciar VIER-NEX con Windows",
            variable=self.start_windows_var, progress_color=CYAN,
            command=self._toggle_start_windows
        ).pack(anchor="w", padx=16, pady=7)

        version = current_ytdlp_version()
        self.engine_label = ctk.CTkLabel(
            box, text=f"Motor yt-dlp: {version}",
            text_color=TEXT, font=ctk.CTkFont(size=11, weight="bold")
        )
        self.engine_label.pack(anchor="w", padx=16, pady=(17, 3))

        ctk.CTkButton(
            box, text="Buscar actualización de yt-dlp",
            fg_color="#4d2d8d", command=self._check_engine_update
        ).pack(fill="x", padx=16, pady=6)

        ctk.CTkButton(
            box, text="Actualizar yt-dlp (modo Python)",
            fg_color="#173955", command=self._update_ytdlp
        ).pack(fill="x", padx=16, pady=6)

        ctk.CTkLabel(
            box,
            text="Privacidad: VIER-NEX procesa las descargas localmente y no envía tu historial ni añade telemetría.",
            text_color=GREEN, justify="left", wraplength=540, font=ctk.CTkFont(size=10)
        ).pack(anchor="w", padx=16, pady=(16, 6))

        ctk.CTkLabel(
            box,
            text="Nota: si usas el EXE compilado, una actualización interna de yt-dlp requiere una nueva compilación de la app.",
            text_color=MUTED, justify="left", wraplength=540, font=ctk.CTkFont(size=9)
        ).pack(anchor="w", padx=16, pady=(0, 12))

    def _toggle_start_windows(self):
        if os.name != "nt":
            return
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                if self.start_windows_var.get():
                    exe = sys.executable
                    if getattr(sys, "frozen", False):
                        cmd = f'"{exe}"'
                    else:
                        script = str(Path(__file__).resolve())
                        pyw = Path(sys.executable).with_name("pythonw.exe")
                        cmd = f'"{pyw}" "{script}"'
                    winreg.SetValueEx(key, "VIER-NEX Video Downloader", 0, winreg.REG_SZ, cmd)
                else:
                    try:
                        winreg.DeleteValue(key, "VIER-NEX Video Downloader")
                    except FileNotFoundError:
                        pass
            self._save_settings()
        except Exception as e:
            messagebox.showerror(APP_NAME, f"No se pudo cambiar el inicio con Windows:\n{e}")

    def _check_engine_update(self):
        threading.Thread(target=self._check_engine_worker, daemon=True).start()

    def _check_engine_worker(self):
        cur = current_ytdlp_version()
        latest = latest_ytdlp_version()
        if not latest:
            self.uiq.put(("notify_message", "Actualización", "No pude consultar la versión más reciente."))
        elif latest == cur:
            self.uiq.put(("notify_message", "Actualización", f"yt-dlp está actualizado ({cur})."))
        else:
            self.uiq.put(("notify_message", "Actualización", f"Disponible: {latest}\nInstalada: {cur}"))

    def _update_ytdlp(self):
        if getattr(sys, "frozen", False):
            messagebox.showinfo(
                APP_NAME,
                "El EXE usa yt-dlp integrado. Para actualizar ese motor hay que generar una versión nueva del EXE.\n\n"
                "En la versión Python sí puede actualizarse automáticamente."
            )
            return
        threading.Thread(target=self._update_ytdlp_worker, daemon=True).start()

    def _update_ytdlp_worker(self):
        try:
            self.uiq.put(("status", "Actualizando yt-dlp..."))
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            p = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
                capture_output=True, text=True, creationflags=flags
            )
            if p.returncode == 0:
                self.uiq.put(("notify_message", "Actualización", "yt-dlp actualizado. Reinicia la aplicación."))
            else:
                self.uiq.put(("notify_message", "Actualización", "No se pudo actualizar yt-dlp."))
        except Exception as e:
            self.uiq.put(("notify_message", "Actualización", str(e)))

    def _open_user_manual(self):
        if MANUAL_PDF.exists():
            if not open_path(MANUAL_PDF):
                messagebox.showerror(
                    APP_NAME,
                    "Windows no pudo abrir el Manual de Usuario en PDF."
                )
            return

        messagebox.showerror(
            APP_NAME,
            "No se encontró el Manual de Usuario.\n\n"
            f"Ruta esperada:\n{MANUAL_PDF}"
        )

    def _about(self):
        if self.about_win is not None and self.about_win.winfo_exists():
            try:
                self.about_win.deiconify()
                self.about_win.lift()
                self.about_win.focus_force()
            except Exception:
                pass
            return

        win = ctk.CTkToplevel(self)
        self.about_win = win
        win.title("Acerca de")
        win.geometry("780x760")
        win.resizable(False, False)
        win.transient(self)

        try:
            if ICON_ICO.exists():
                win.after(120, lambda: win.iconbitmap(str(ICON_ICO)))
        except Exception:
            pass

        def close_about():
            self.about_win = None
            try:
                win.destroy()
            except Exception:
                pass

        win.protocol("WM_DELETE_WINDOW", close_about)

        # Windows: keep only close button where possible.
        try:
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
            GWL_STYLE = -16
            WS_MINIMIZEBOX = 0x00020000
            WS_MAXIMIZEBOX = 0x00010000
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
            style &= ~WS_MINIMIZEBOX
            style &= ~WS_MAXIMIZEBOX
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)
        except Exception:
            pass

        root = ctk.CTkFrame(win, fg_color="#071525", corner_radius=0)
        root.pack(fill="both", expand=True)

        scroll = ctk.CTkScrollableFrame(
            root,
            fg_color="transparent",
            scrollbar_button_color="#173955",
            scrollbar_button_hover_color="#235477"
        )
        scroll.pack(fill="both", expand=True, padx=18, pady=18)
        scroll.grid_columnconfigure(0, weight=1)

        # Branding
        if ICON_PNG.exists():
            try:
                raw = Image.open(ICON_PNG).convert("RGBA")
                about_img = ctk.CTkImage(light_image=raw, dark_image=raw, size=(68, 68))
                ctk.CTkLabel(scroll, text="", image=about_img).grid(
                    row=0, column=0, pady=(2, 4)
                )
                win._about_img = about_img
            except Exception:
                pass

        ctk.CTkLabel(
            scroll,
            text="VIER-NEX Video Downloader",
            text_color=CYAN,
            font=ctk.CTkFont(size=22, weight="bold")
        ).grid(row=1, column=0, pady=(0, 2))

        ctk.CTkLabel(
            scroll,
            text=f"Versión {APP_VERSION}  ·  Creado por {APP_CREATOR}",
            text_color=MUTED,
            font=ctk.CTkFont(size=13)
        ).grid(row=2, column=0, pady=(0, 12))

        intro = ctk.CTkFrame(
            scroll,
            fg_color="#0d1d31",
            corner_radius=12,
            border_width=1,
            border_color=BORDER
        )
        intro.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        intro.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            intro,
            text="¿Qué es VIER-NEX Video Downloader?",
            text_color=TEXT,
            anchor="w",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(13, 5))

        ctk.CTkLabel(
            intro,
            text=(
                "Aplicación de Windows para descargar, recortar, convertir y optimizar "
                "videos y audio desde múltiples plataformas, con cola de descargas, "
                "historial, compresión por tamaño y procesamiento local."
            ),
            text_color="#b9cce0",
            justify="left",
            anchor="w",
            wraplength=690,
            font=ctk.CTkFont(size=13)
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 13))

        info = ctk.CTkFrame(
            scroll,
            fg_color="#0d1d31",
            corner_radius=12,
            border_width=1,
            border_color=BORDER
        )
        info.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        info.grid_columnconfigure(0, weight=1)
        info.grid_columnconfigure(1, weight=1)

        def info_section(parent, row, col, title, body, accent):
            box = ctk.CTkFrame(parent, fg_color="#0a192a", corner_radius=10)
            box.grid(row=row, column=col, sticky="nsew", padx=7, pady=7)
            ctk.CTkLabel(
                box,
                text=title,
                text_color=accent,
                anchor="w",
                font=ctk.CTkFont(size=12, weight="bold")
            ).pack(fill="x", padx=12, pady=(10, 4))
            ctk.CTkLabel(
                box,
                text=body,
                text_color="#b7c8d9",
                justify="left",
                anchor="nw",
                wraplength=315,
                font=ctk.CTkFont(size=12)
            ).pack(fill="both", expand=True, padx=12, pady=(0, 11))

        info_section(
            info, 0, 0,
            "Funciones principales",
            "• Descargas individuales y múltiples\n"
            "• Clips: Full, 15 s, 30 s, 1, 3 y 5 min\n"
            "• Modos Auto, Máxima, 1080p y 720p\n"
            "• MP3 y compresión por tamaño\n"
            "• Cola, reintentos e historial",
            CYAN
        )
        info_section(
            info, 0, 1,
            "Plataformas",
            "Twitter / X\n"
            "TikTok\n"
            "Instagram\n"
            "Facebook / fb.watch\n"
            "YouTube\n"
            "Reddit, Vimeo, Twitch y otros sitios compatibles con yt-dlp",
            PURPLE
        )
        info_section(
            info, 1, 0,
            "Procesamiento y privacidad",
            "Las descargas, recortes, conversiones, compresión, cola e historial "
            "se gestionan localmente en tu PC. VIER-NEX no incorpora telemetría propia.",
            GREEN
        )
        info_section(
            info, 1, 1,
            "Tecnologías",
            f"Python\n"
            f"yt-dlp {current_ytdlp_version()}\n"
            "FFmpeg\n"
            "CustomTkinter\n\n"
            "Diseñado para Windows 10/11 x64.",
            BLUE
        )

        manual_box = ctk.CTkFrame(
            scroll,
            fg_color="#0d1d31",
            corner_radius=12,
            border_width=1,
            border_color=BORDER
        )
        manual_box.grid(row=5, column=0, sticky="ew", pady=(0, 10))
        manual_box.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            manual_box,
            text="Ayuda y documentación",
            text_color=TEXT,
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 3))

        ctk.CTkLabel(
            manual_box,
            text=(
                "El Manual de Usuario explica paso a paso cómo funcionan los enlaces, "
                "modos de descarga, Lote, WhatsApp, tamaño personalizado, Facebook, "
                "cola, historial, bandeja de Windows y solución de problemas."
            ),
            text_color="#a9bfd3",
            justify="left",
            anchor="w",
            wraplength=690,
            font=ctk.CTkFont(size=12)
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))

        ctk.CTkButton(
            manual_box,
            text="Abrir Manual de Usuario (PDF)",
            height=36,
            fg_color="#0d6578",
            hover_color="#10839a",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._open_user_manual
        ).grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 13))

        actions = ctk.CTkFrame(scroll, fg_color="transparent")
        actions.grid(row=6, column=0, sticky="ew", pady=(0, 4))
        actions.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            actions,
            text="Copiar información de versión",
            height=38,
            fg_color="#173955",
            hover_color="#214c6d",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: copy_to_clipboard(
                self,
                f"{APP_NAME}\n"
                f"Versión {APP_VERSION}\n"
                f"Creado por {APP_CREATOR}\n"
                f"yt-dlp {current_ytdlp_version()}\n"
                "Python · FFmpeg · CustomTkinter"
            )
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5))

        ctk.CTkButton(
            actions,
            text="Buscar actualización de yt-dlp",
            height=38,
            fg_color="#4d2d8d",
            hover_color="#6741b1",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._check_engine_update
        ).grid(row=0, column=1, sticky="ew", padx=(5, 0))

        ctk.CTkLabel(
            scroll,
            text=(
                "Usa VIER-NEX respetando los derechos de autor, la privacidad "
                "y las condiciones de servicio de cada plataforma."
            ),
            text_color=MUTED,
            wraplength=690,
            justify="center",
            font=ctk.CTkFont(size=10.5)
        ).grid(row=7, column=0, pady=(8, 4))


    def exit_app(self):
        self.stop_worker.set()
        self.clipboard_stop.set()
        self.pause_event.set()
        self.taskbar.clear()
        if self._instance_server:
            try:
                self._instance_server.close()
            except Exception:
                pass
            self._instance_server = None
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.destroy()

    # ---------------- UI queue ----------------
    def _poll_uiq(self):
        try:
            while True:
                item = self.uiq.get_nowait()
                kind = item[0]

                if kind == "analysis":
                    d = item[1]
                    self.analysis_title.set(d["title"][:95])
                    self.analysis_meta.set(
                        f'{d["platform"]} · {d["resolution"]} · Duración {human_duration(d["duration"])}'
                    )
                    self.analysis_size.set(f'Tamaño estimado: {format_mb(d["size_mb"])}')
                    self._refresh_analysis_output_estimate()

                elif kind == "analysis_error":
                    self.analysis_title.set("No se pudo analizar")
                    self.analysis_meta.set(item[1])
                    self.analysis_size.set("Tamaño estimado: —")
                    self._refresh_analysis_output_estimate()

                elif kind == "clipboard":
                    u = item[1]
                    self.clip_label.configure(text=u[:150])
                    self._log(f"Portapapeles: {detect_platform(u)} detectado.")
                    if self.clip_notify_var.get():
                        self._notify("Enlace detectado", f"{detect_platform(u)} listo para descargar.")

                elif kind == "queue_refresh":
                    self._refresh_queue()

                elif kind == "job_start":
                    job = item[1]
                    self.progress.set(0)
                    self.progress_label.configure(text="0%")
                    self.status_var.set(f'Descargando {job["platform"]}...')
                    self.taskbar.set(0, TBPF_NORMAL)
                    self._log(f'Iniciando: {job["platform"]}')

                elif kind == "progress":
                    jid, pct, detail = item[1], item[2], item[3]

                    # Throttle visual progress updates. yt-dlp can report many
                    # callbacks per second; repainting every one causes resize lag.
                    now = time.monotonic()
                    if (
                        not self._resize_in_progress
                        and ((now - self._last_progress_ui_update) >= 0.15 or pct >= 100)
                    ):
                        self._last_progress_ui_update = now
                        self.progress.set(max(0, min(100, pct))/100)
                        self.progress_label.configure(text=f"{pct:.0f}%")
                        self.status_var.set(f"Descargando · {detail}")
                        self.taskbar.set(pct, TBPF_NORMAL)

                    for j in self.jobs:
                        if j["id"] == jid:
                            j["progress"] = pct
                            break

                    self._schedule_queue_refresh()

                elif kind == "status":
                    self.status_var.set(item[1])

                elif kind == "log":
                    self._log(item[1])

                elif kind == "job_done":
                    job, rec = item[1], item[2]
                    self.progress.set(1)
                    self.progress_label.configure(text="100%")
                    self.status_var.set("Completado")
                    self.taskbar.set(100, TBPF_NORMAL)
                    self.after(1600, self.taskbar.clear)
                    self._refresh_recent()
                    self._refresh_queue()
                    self._log(f'Listo: {rec["name"]}')
                    self._notify("Video listo", f'{rec["name"]}\n{rec["size_mb"]} MB', Path(rec["file"]).parent)
                    if self.open_folder_var.get():
                        open_path(Path(rec["file"]).parent)

                elif kind == "job_error":
                    job, err = item[1], item[2]
                    self.status_var.set("Error")
                    self.progress.set(0)
                    self.progress_label.configure(text="0%")
                    self.taskbar.set(100, TBPF_ERROR)
                    self.after(2500, self.taskbar.clear)
                    self._log(f"ERROR: {err}")
                    self._notify("Error de descarga", str(err)[:180])

                elif kind == "job_cancelled":
                    self.status_var.set("Cancelado")
                    self.progress.set(0)
                    self.progress_label.configure(text="0%")
                    self.taskbar.clear()
                    self._log("Descarga cancelada.")

                elif kind == "local_done":
                    rec = item[1]
                    self.status_var.set("Compresión completada")
                    self._refresh_recent()
                    self._notify("Video comprimido", f'{rec["name"]}\n{rec["size_mb"]} MB', Path(rec["file"]).parent)

                elif kind == "local_error":
                    self.status_var.set("Error de compresión")
                    self._log("ERROR: " + item[1])
                    self._notify("Error de compresión", item[1][:180])

                elif kind == "notify_message":
                    title, msg = item[1], item[2]
                    self._notify(title, msg)
                    messagebox.showinfo(title, msg)

        except queue.Empty:
            pass
        self.after(100, self._poll_uiq)


def _notify_existing_instance_to_show():
    try:
        with socket.create_connection((APP_HOST, APP_PORT), timeout=1.0) as s:
            s.sendall(b"SHOW")
        return True
    except OSError:
        return False


def main():
    if _notify_existing_instance_to_show():
        return
    app = VierNexApp()
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        try:
            import traceback
            USER_DATA.mkdir(parents=True, exist_ok=True)
            crash = USER_DATA / "startup_error.txt"
            crash.write_text(traceback.format_exc(), encoding="utf-8")
            err_text = traceback.format_exc().splitlines()[-1] if traceback.format_exc() else "Error desconocido"
            ctypes.windll.user32.MessageBoxW(
                0,
                f"VIER-NEX no pudo iniciar.\n\n{err_text}\n\nDetalle guardado en:\n{crash}",
                APP_NAME,
                0x10
            )
        except Exception:
            raise


