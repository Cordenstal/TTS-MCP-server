"""Small, dependency-free Windows GUI primitives for the TTS save menu.

TTS uses a Unity-rendered interface rather than standard Windows controls, so
there is no stable UI Automation tree to address. Coordinates are therefore
explicit inputs and are always relative to the detected TTS window.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class WindowsGuiError(RuntimeError):
    """Raised when the guarded TTS GUI workflow cannot proceed."""


@dataclass(frozen=True)
class Window:
    handle: int
    title: str
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


def _user32() -> Any:
    if os.name != "nt":
        raise WindowsGuiError("Windows GUI automation is only available on Windows")
    return ctypes.windll.user32


def find_tts_window(title_contains: str = "Tabletop Simulator") -> Window:
    user32 = _user32()
    handles: list[Window] = []
    enum_windows = user32.EnumWindows
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    enum_windows.argtypes = [callback_type, ctypes.c_void_p]
    enum_windows.restype = ctypes.c_bool

    def visit(handle: int, _unused: int) -> bool:
        if not user32.IsWindowVisible(handle):
            return True
        length = user32.GetWindowTextLengthW(handle)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(handle, buffer, length + 1)
        title = buffer.value
        if title_contains.lower() not in title.lower():
            return True
        rect = ctypes.wintypes.RECT()
        if not user32.GetWindowRect(handle, ctypes.byref(rect)):
            return True
        handles.append(Window(handle, title, rect.left, rect.top, rect.right, rect.bottom))
        return True

    enum_windows(callback_type(visit), 0)
    if not handles:
        raise WindowsGuiError(f"No visible window contains {title_contains!r} in its title")
    if len(handles) > 1:
        exact = [window for window in handles if window.title.lower() == title_contains.lower()]
        if len(exact) == 1:
            return exact[0]
        raise WindowsGuiError(
            "Multiple visible windows match Tabletop Simulator; close duplicates or use a narrower title"
        )
    return handles[0]


def _focus(window: Window) -> None:
    user32 = _user32()
    user32.ShowWindow(window.handle, 9)  # SW_RESTORE
    if not user32.SetForegroundWindow(window.handle):
        raise WindowsGuiError("Could not bring the Tabletop Simulator window to the foreground")
    time.sleep(0.25)


def _click(window: Window, x: int, y: int) -> None:
    if not (0 <= x <= window.width and 0 <= y <= window.height):
        raise WindowsGuiError(f"GUI coordinate ({x}, {y}) is outside the TTS window")
    user32 = _user32()
    user32.SetCursorPos(window.left + x, window.top + y)
    time.sleep(0.08)
    user32.mouse_event(0x0002, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTDOWN
    user32.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP


def _key(vk: int, *, down: bool) -> None:
    user32 = _user32()
    user32.keybd_event(vk, 0, 0 if down else 0x0002, 0)


def press_key(vk: int) -> None:
    _key(vk, down=True)
    _key(vk, down=False)


def hotkey(*keys: int) -> None:
    for key in keys:
        _key(key, down=True)
    for key in reversed(keys):
        _key(key, down=False)


def type_text(value: str) -> None:
    user32 = _user32()
    for character in value:
        code = ord(character)
        if code > 0xFFFF:
            raise WindowsGuiError("save name contains unsupported non-BMP characters")
        user32.keybd_event(0, code, 0x0004, 0)
        user32.keybd_event(0, code, 0x0004 | 0x0002, 0)


def load_save_via_gui(
    path: Path,
    *,
    games_button: tuple[int, int],
    save_load_button: tuple[int, int],
    search_box: tuple[int, int],
    result_row: tuple[int, int],
    confirm_button: tuple[int, int] | None = None,
    title_contains: str = "Tabletop Simulator",
    settle_seconds: float = 8.0,
) -> dict[str, Any]:
    """Load one numbered save using configured coordinates in the TTS window."""
    if not path.is_file():
        raise WindowsGuiError(f"save file does not exist: {path}")
    window = find_tts_window(title_contains)
    _focus(window)

    # Escape closes an already-open TTS overlay without changing the scene.
    press_key(0x1B)
    time.sleep(0.2)
    _click(window, *games_button)
    time.sleep(0.8)
    _click(window, *save_load_button)
    time.sleep(1.2)
    _click(window, *search_box)
    hotkey(0x11, 0x41)  # Ctrl+A
    type_text(path.stem)
    time.sleep(1.0)
    _click(window, *result_row)
    time.sleep(1.0)
    if confirm_button is None:
        press_key(0x0D)  # Enter on the TTS confirmation dialog
    else:
        _click(window, *confirm_button)
    time.sleep(max(1.0, min(float(settle_seconds), 60.0)))
    return {
        "window_title": window.title,
        "window_rect": {
            "left": window.left,
            "top": window.top,
            "right": window.right,
            "bottom": window.bottom,
        },
        "path": str(path),
        "search_text": path.stem,
        "settle_seconds": max(1.0, min(float(settle_seconds), 60.0)),
        "coordinates_relative_to_window": {
            "games_button": games_button,
            "save_load_button": save_load_button,
            "search_box": search_box,
            "result_row": result_row,
            "confirm_button": confirm_button,
        },
        "load_requested": True,
    }
