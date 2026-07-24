#!/usr/bin/env python3
import os
import subprocess
import re
import hashlib
import shutil
import threading
import zipfile
import glob
import struct
import time
from pathlib import Path

import gi
from PIL import Image, ImageFilter, UnidentifiedImageError

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk


ROM_EXTENSIONS = {".nes"}
PAGE_DIRECTORY = re.compile(r"^Page\s+(\d+)$", re.IGNORECASE)
APP_ROOT = Path(__file__).resolve().parent
GAME_ROOT = Path(os.environ.get("NES_GAME_DIR", APP_ROOT / "games")).expanduser()
GBA_ROOT = Path(os.environ.get("GBA_GAME_DIR", GAME_ROOT / "GBA"))
DOWNLOADS = Path.home() / "Downloads"
RETROARCH = "/usr/bin/retroarch"
NES_CORE = "/usr/lib/x86_64-linux-gnu/libretro/nestopia_libretro.so"
GBA_CORE = "/usr/lib/x86_64-linux-gnu/libretro/mgba_libretro.so"
NDS_CORE = "/usr/lib/x86_64-linux-gnu/libretro/desmume_libretro.so"
CONTROL_DIR = Path.home() / ".config" / "yones" / "controls"
ART_CACHE = Path.home() / ".cache" / "nes-game-library"
BUNDLED_ART = Path(os.environ.get("NES_ART_DIR", GAME_ROOT.parent / "artwork"))
GAME_METADATA = {
    "contra": ("1988", "Run and gun", "Konami", "1–2 players"),
    "super mario bros. 3": ("1990", "Platform", "Nintendo", "1–2 players"),
    "mega man 2": ("1989", "Action platform", "Capcom", "1 player"),
    "the legend of zelda": ("1987", "Action adventure", "Nintendo", "1 player"),
    "battle city": ("1985", "Action", "Namco", "1–2 players"),
    "tetris": ("1989", "Puzzle", "Nintendo", "1–2 players"),
}
RETROARCH_ACTIONS = {
    "up": "up", "down": "down", "left": "left", "right": "right",
    "select": "select", "start": "start", "a": "a", "b": "b",
    "turboa": "x", "turbob": "y", "l": "l", "r": "r",
    "save_state": "save_state", "load_state": "load_state",
}
HOTKEY_ACTIONS = {"save_state", "load_state"}
CONTROL_BUTTONS = {
    "NES": (
    ("up", "D-pad Up"), ("down", "D-pad Down"),
    ("left", "D-pad Left"), ("right", "D-pad Right"),
    ("select", "Select"), ("start", "Start"),
    ("a", "A"), ("b", "B"),
    ("turboa", "Turbo A"), ("turbob", "Turbo B"),
    ("save_state", "Save State"), ("load_state", "Load State"),
    ),
    "GBA": (
        ("up", "D-pad Up"), ("down", "D-pad Down"),
        ("left", "D-pad Left"), ("right", "D-pad Right"),
        ("select", "Select"), ("start", "Start"),
        ("a", "A"), ("b", "B"), ("l", "L"), ("r", "R"),
        ("save_state", "Save State"), ("load_state", "Load State"),
    ),
    "NDS": (
        ("up", "D-pad Up"), ("down", "D-pad Down"),
        ("left", "D-pad Left"), ("right", "D-pad Right"),
        ("select", "Select"), ("start", "Start"),
        ("a", "A"), ("b", "B"), ("turboa", "X"), ("turbob", "Y"),
        ("l", "L"), ("r", "R"),
        ("save_state", "Save State"), ("load_state", "Load State"),
    ),
}
RECOMMENDED_KEYS = {
    "NES": {"up": "up", "down": "down", "left": "left", "right": "right",
            "select": "num1", "start": "num2", "a": "s", "b": "a",
            "turboa": "x", "turbob": "z", "save_state": "f2", "load_state": "f4"},
    "GBA": {"up": "up", "down": "down", "left": "left", "right": "right",
            "select": "num1", "start": "num2", "a": "s", "b": "a",
            "l": "q", "r": "w", "save_state": "f2", "load_state": "f4"},
    "NDS": {"up": "up", "down": "down", "left": "left", "right": "right",
            "select": "num1", "start": "num2", "a": "s", "b": "a",
            "turboa": "x", "turbob": "z", "l": "q", "r": "w",
            "save_state": "f2", "load_state": "f4"},
}
DEFAULT_GAMEPAD_BINDINGS = {
    "NES": {
        "up": ("axis", "-7"), "down": ("axis", "+7"),
        "left": ("axis", "-6"), "right": ("axis", "+6"),
        "select": ("btn", "6"), "start": ("btn", "7"),
        "a": ("btn", "0"), "b": ("btn", "1"),
        "turboa": ("btn", "2"), "turbob": ("btn", "3"),
    },
    "GBA": {
        "up": ("axis", "-7"), "down": ("axis", "+7"),
        "left": ("axis", "-6"), "right": ("axis", "+6"),
        "select": ("btn", "6"), "start": ("btn", "7"),
        "a": ("btn", "0"), "b": ("btn", "1"),
        "l": ("btn", "4"), "r": ("btn", "5"),
    },
    "NDS": {
        "up": ("axis", "-7"), "down": ("axis", "+7"),
        "left": ("axis", "-6"), "right": ("axis", "+6"),
        "select": ("btn", "6"), "start": ("btn", "7"),
        "a": ("btn", "0"), "b": ("btn", "1"),
        "turboa": ("btn", "2"), "turbob": ("btn", "3"),
        "l": ("btn", "4"), "r": ("btn", "5"),
    },
}


class GameLauncher(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="local.yones.GameLauncher")
        self.window = None
        self.listbox = None
        self.status = None
        self.games = []
        self.pages = []
        self.current_page = 0
        self.capture_action = None
        self.capture_kind = None
        self.capture_token = 0
        self.mapping_buttons = {}
        self.gamepad_mapping_buttons = {}
        self.current_system = "NES"
        self.current_control_system = "NES"
        self.home_listbox = None
        self.settings_listbox = None
        self.gamepad_monitor_started = False
        self.game_running = False
        self.running_game = None
        self.live_capture_token = 0
        self.controller_test_cards = {}
        self.controller_test_state = {}
        self.physical_test_cards = {}
        self.physical_test_values = {}

    def do_activate(self):
        if self.window:
            self.window.present()
            return

        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("NES Game Library")
        self.window.fullscreen()

        css = Gtk.CssProvider()
        css.load_from_data(b"""
            window, label { color: #f7f7fb; }
            window { background: #090b12; }
            .hero { font-size: 42px; font-weight: 900; color: #ffdf5d; }
            .subtitle { font-size: 16px; color: #9da6ba; }
            list { background: transparent; }
            row, row label { color: #f7f7fb; }
            row { border-radius: 14px; margin: 5px 0; padding: 5px; }
            row:hover { background: #24293a; }
            row:selected, row:selected label {
                background: #5846e8;
                color: #ffffff;
            }
            button, button label {
                background: #24293a;
                color: #f7f7fb;
            }
            button:hover, button:hover label,
            button:focus, button:focus label,
            button:checked, button:checked label {
                background: #5846e8;
                color: #ffffff;
            }
            .game-title { font-size: 25px; font-weight: 700; color: #f7f7fb; }
            .game-path { font-size: 13px; color: #aeb6c8; }
            .hint { font-size: 14px; color: #aeb6c8; }
            .status { font-size: 15px; color: #6ee7b7; }
            .test-active { background: #16a36a; color: white; border-radius: 10px; }
            .game-background-shade { background: rgba(9, 11, 18, 0.80); }
            .controller-shell {
                background: rgba(35, 40, 55, 0.92);
                border: 2px solid #687086;
                border-radius: 34px;
                padding: 20px;
            }
            .controller-button {
                background: #171b27;
                color: #f7f7fb;
                border: 1px solid #7d879d;
                border-radius: 22px;
                padding: 8px;
                font-size: 16px;
                font-weight: 700;
            }
            .controller-shoulder {
                background: #171b27;
                color: #f7f7fb;
                border: 1px solid #7d879d;
                border-radius: 10px;
                padding: 8px 20px;
                font-weight: 700;
            }
            .controller-button.test-active,
            .controller-shoulder.test-active {
                background: #16a36a;
                color: white;
            }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_margin_top(42)
        outer.set_margin_bottom(28)
        outer.set_margin_start(70)
        outer.set_margin_end(70)

        self.library_title = Gtk.Label(label="NES GAME LIBRARY", xalign=0)
        self.library_title.add_css_class("hero")
        self.library_subtitle = Gtk.Label(label=f"Games found in {GAME_ROOT}", xalign=0)
        self.library_subtitle.add_css_class("subtitle")
        outer.append(self.library_title)
        outer.append(self.library_subtitle)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.set_activate_on_single_click(False)
        self.listbox.connect("row-activated", self.launch_row)
        self.listbox.connect("row-selected", self.on_game_selected)
        scroll.set_child(self.listbox)
        library = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        library.set_wide_handle(True)
        library.set_start_child(scroll)
        library.set_end_child(self.build_details_panel())
        library.set_position(760)
        library.set_vexpand(True)
        outer.append(library)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        hint = Gtk.Label(
            label="↑ ↓ Select    ← → Page    Enter Play    F5 Refresh    Esc Back", xalign=0
        )
        hint.add_css_class("hint")
        hint.set_hexpand(True)
        self.status = Gtk.Label(xalign=1)
        self.status.add_css_class("status")
        footer.append(hint)
        footer.append(self.status)
        outer.append(footer)
        settings = Gtk.Button(label="Controller Setup  [F1]")
        settings.connect("clicked", lambda _button: self.show_settings_menu())
        footer.append(settings)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(180)
        self.stack.add_named(self.build_home_page(), "home")
        games_overlay = Gtk.Overlay()
        self.game_background = Gtk.Picture()
        self.game_background.set_content_fit(Gtk.ContentFit.COVER)
        self.game_background.set_hexpand(True)
        self.game_background.set_vexpand(True)
        self.game_background.set_can_target(False)
        games_overlay.set_child(self.game_background)
        shade = Gtk.Box()
        shade.add_css_class("game-background-shade")
        shade.set_hexpand(True)
        shade.set_vexpand(True)
        shade.set_can_target(False)
        games_overlay.add_overlay(shade)
        games_overlay.add_overlay(outer)
        self.stack.add_named(games_overlay, "games")
        self.stack.add_named(self.build_settings_menu(), "settings_menu")
        self.stack.add_named(self.build_setup_page(), "setup")
        self.stack.add_named(self.build_controller_test_page(), "controller_test")
        self.stack.add_named(self.build_physical_test_page(), "physical_test")
        self.window.set_child(self.stack)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.on_key)
        self.window.add_controller(keys)
        self.refresh()
        self.stack.set_visible_child_name("home")
        self.window.present()
        self.start_gamepad_monitor()

    def start_gamepad_monitor(self):
        if self.gamepad_monitor_started:
            return
        self.gamepad_monitor_started = True
        threading.Thread(target=self.monitor_gamepad, daemon=True).start()

    @staticmethod
    def gamepad_devices():
        """Return joydev nodes, preferring real controllers over keyboard extras."""
        devices = sorted(glob.glob("/dev/input/js*"))
        preferred = []
        controller_words = (
            "controller", "gamepad", "joystick", "xbox", "dualshock",
            "dualsense", "microsoft", "sony", "nintendo", "8bitdo",
            "machenike",
        )
        non_controller_words = ("keyboard", "mouse", "keychron link")
        for device in devices:
            name_path = Path("/sys/class/input") / Path(device).name / "device" / "name"
            try:
                name = name_path.read_text(encoding="utf-8").strip().casefold()
            except OSError:
                name = ""
            if any(word in name for word in controller_words):
                preferred.append(device)
            elif any(word in name for word in non_controller_words):
                continue
        # Keep compatibility with generic USB pads whose device name does not
        # contain a recognizable controller word.
        return preferred or devices

    def monitor_gamepad(self):
        """Hot-plug monitor for common USB/Bluetooth controllers via joydev."""
        open_devices = {}
        axis_active = {}
        while True:
            devices = self.gamepad_devices()
            for device in list(open_devices):
                if device not in devices:
                    os.close(open_devices.pop(device))
                    axis_active.pop(device, None)
                    GLib.idle_add(self.controller_disconnected, device)
            for device in devices:
                if device in open_devices:
                    continue
                try:
                    open_devices[device] = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
                    axis_active[device] = {}
                    GLib.idle_add(self.controller_connected, device)
                except OSError:
                    continue
            for device, fd in list(open_devices.items()):
                try:
                    while True:
                        data = os.read(fd, 8)
                        if len(data) != 8:
                            break
                        _stamp, value, event_type, number = struct.unpack("<IhBB", data)
                        if event_type & 0x80:
                            continue
                        event_type &= 0x7F
                        GLib.idle_add(
                            self.handle_controller_test_event,
                            device, event_type, number, value,
                        )
                        action = None
                        if event_type == 1 and value:
                            action = {0: "accept", 1: "back", 7: "accept"}.get(number)
                        elif event_type == 2:
                            direction = 1 if value > 16000 else -1 if value < -16000 else 0
                            previous = axis_active[device].get(number, 0)
                            axis_active[device][number] = direction
                            if direction and direction != previous:
                                if number in (0, 6):
                                    action = "right" if direction > 0 else "left"
                                elif number in (1, 7):
                                    action = "down" if direction > 0 else "up"
                        if action and device == devices[0]:
                            GLib.idle_add(self.handle_gamepad_navigation, action)
                except BlockingIOError:
                    pass
                except OSError:
                    os.close(open_devices.pop(device))
                    axis_active.pop(device, None)
                    GLib.idle_add(self.controller_disconnected, device)
            time.sleep(0.02)

    def handle_gamepad_navigation(self, action):
        if self.game_running or self.capture_kind == "gamepad":
            return False
        screen = self.stack.get_visible_child_name()
        if screen in ("controller_test", "physical_test"):
            return False
        listbox = self.home_listbox if screen == "home" else (
            self.settings_listbox if screen == "settings_menu" else self.listbox
        )
        if action in ("up", "down") and screen != "setup":
            row = listbox.get_selected_row()
            index = row.get_index() if row else 0
            index += -1 if action == "up" else 1
            target = listbox.get_row_at_index(max(0, index))
            if target:
                listbox.select_row(target)
                target.grab_focus()
            return False
        if action in ("left", "right") and screen == "games":
            self.change_page(-1 if action == "left" else 1)
            return False
        if action == "accept":
            if screen == "home":
                row = self.home_listbox.get_selected_row()
                if row:
                    self.activate_home_row(self.home_listbox, row)
            elif screen == "settings_menu":
                row = self.settings_listbox.get_selected_row()
                if row:
                    self.activate_settings_row(self.settings_listbox, row)
            elif screen == "games":
                row = self.listbox.get_selected_row()
                if row and hasattr(row, "game_path"):
                    self.launch_row(self.listbox, row)
            return False
        if action == "back":
            if screen == "games" or screen == "settings_menu":
                self.show_home()
            elif screen in ("setup", "controller_test", "physical_test"):
                self.show_settings_menu()
        return False

    def build_home_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        page.set_margin_top(90)
        page.set_margin_bottom(70)
        page.set_margin_start(180)
        page.set_margin_end(180)
        title = Gtk.Label(label="GAME LIBRARY")
        title.add_css_class("hero")
        subtitle = Gtk.Label(label="Choose a system")
        subtitle.add_css_class("subtitle")
        page.append(title)
        page.append(subtitle)
        self.home_listbox = Gtk.ListBox()
        self.home_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.home_listbox.set_activate_on_single_click(False)
        self.home_listbox.connect("row-activated", self.activate_home_row)
        for system, description in (
            ("NES", "Nintendo Entertainment System"),
            ("GBA", "Game Boy Advance"),
            ("NDS", "Nintendo DS"),
            ("Settings", "Controller mapping"),
        ):
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            box.set_margin_top(20)
            box.set_margin_bottom(20)
            box.set_margin_start(28)
            box.set_margin_end(28)
            name = Gtk.Label(label=system, xalign=0)
            name.add_css_class("game-title")
            detail = Gtk.Label(label=description, xalign=0)
            detail.add_css_class("subtitle")
            box.append(name)
            box.append(detail)
            row.set_child(box)
            row.menu_action = system
            self.home_listbox.append(row)
        self.home_listbox.select_row(self.home_listbox.get_row_at_index(0))
        self.home_listbox.set_vexpand(True)
        page.append(self.home_listbox)
        hint = Gtk.Label(label="↑ ↓ Select    Enter Open    Esc Exit")
        hint.add_css_class("hint")
        page.append(hint)
        return page

    def activate_home_row(self, _listbox, row):
        action = getattr(row, "menu_action", "")
        if action == "Settings":
            self.show_settings_menu()
        elif action in ("NES", "GBA", "NDS"):
            self.show_library(action)

    def show_library(self, system):
        self.current_system = system
        self.current_page = 0
        self.library_title.set_text(f"{system} GAME LIBRARY")
        source = {
            "NES": GAME_ROOT,
            "GBA": GBA_ROOT,
            "NDS": DOWNLOADS,
        }[system]
        self.library_subtitle.set_text(f"Games found in {source}")
        self.refresh()
        self.stack.set_visible_child_name("games")

    def show_home(self):
        self.capture_action = None
        self.capture_kind = None
        self.capture_token += 1
        self.stack.set_visible_child_name("home")
        self.home_listbox.grab_focus()

    def build_settings_menu(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        page.set_margin_top(90)
        page.set_margin_bottom(70)
        page.set_margin_start(180)
        page.set_margin_end(180)
        title = Gtk.Label(label="CONTROLLER SETTINGS")
        title.add_css_class("hero")
        page.append(title)
        self.settings_listbox = Gtk.ListBox()
        self.settings_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.settings_listbox.set_activate_on_single_click(False)
        self.settings_listbox.connect("row-activated", self.activate_settings_row)
        for system in (
            "NES", "GBA", "NDS", "Test Mapped Controls", "Test Physical Inputs"
        ):
            row = Gtk.ListBoxRow()
            label_text = (
                f"{system} Controls"
                if system in ("NES", "GBA", "NDS")
                else system
            )
            label = Gtk.Label(label=label_text, xalign=0)
            label.add_css_class("game-title")
            label.set_margin_top(26)
            label.set_margin_bottom(26)
            label.set_margin_start(28)
            label.set_margin_end(28)
            row.set_child(label)
            row.control_system = system
            self.settings_listbox.append(row)
        self.settings_listbox.select_row(self.settings_listbox.get_row_at_index(0))
        self.settings_listbox.set_vexpand(True)
        page.append(self.settings_listbox)
        hint = Gtk.Label(label="↑ ↓ Select    Enter Open    Esc Back")
        hint.add_css_class("hint")
        page.append(hint)
        return page

    def show_settings_menu(self):
        self.capture_action = None
        self.capture_kind = None
        self.capture_token += 1
        self.stack.set_visible_child_name("settings_menu")
        self.settings_listbox.grab_focus()

    def activate_settings_row(self, _listbox, row):
        system = getattr(row, "control_system", "NES")
        if system == "Test Mapped Controls":
            self.show_controller_test()
        elif system == "Test Physical Inputs":
            self.show_physical_test()
        else:
            self.show_setup(system)

    def build_controller_test_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        page.set_margin_top(48)
        page.set_margin_bottom(36)
        page.set_margin_start(90)
        page.set_margin_end(90)
        title = Gtk.Label(label="TEST MAPPED CONTROLS", xalign=0)
        title.add_css_class("hero")
        subtitle = Gtk.Label(
            label="Press a direction or button. Green labels are currently active.",
            xalign=0,
        )
        subtitle.add_css_class("subtitle")
        self.controller_test_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=18
        )
        self.controller_test_box.set_vexpand(True)
        self.controller_test_empty = Gtk.Label(
            label="No controller detected — connect a USB or Bluetooth controller."
        )
        self.controller_test_empty.add_css_class("game-title")
        self.controller_test_box.append(self.controller_test_empty)
        self.controller_test_raw = Gtk.Label(label="Waiting for input…", xalign=0)
        self.controller_test_raw.add_css_class("status")
        back = Gtk.Button(label="Back to Settings  [Esc]")
        back.connect("clicked", lambda _button: self.show_settings_menu())
        page.append(title)
        page.append(subtitle)
        page.append(self.controller_test_box)
        page.append(self.controller_test_raw)
        page.append(back)
        return page

    def show_controller_test(self):
        self.stack.set_visible_child_name("controller_test")
        for device in self.gamepad_devices():
            self.controller_connected(device)

    def build_physical_test_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        page.set_margin_top(42)
        page.set_margin_bottom(30)
        page.set_margin_start(70)
        page.set_margin_end(70)
        title = Gtk.Label(label="TEST PHYSICAL INPUTS", xalign=0)
        title.add_css_class("hero")
        subtitle = Gtk.Label(
            label="Raw Linux joydev input — buttons and axes are shown without mapping.",
            xalign=0,
        )
        subtitle.add_css_class("subtitle")
        self.physical_test_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=16
        )
        self.physical_test_empty = Gtk.Label(
            label="No controller detected — connect a USB or Bluetooth controller."
        )
        self.physical_test_empty.add_css_class("game-title")
        self.physical_test_box.append(self.physical_test_empty)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self.physical_test_box)
        back = Gtk.Button(label="Back to Settings  [Esc]")
        back.connect("clicked", lambda _button: self.show_settings_menu())
        page.append(title)
        page.append(subtitle)
        page.append(scroll)
        page.append(back)
        devices = self.gamepad_devices()
        slots = devices[:2] if devices else ["/dev/input/js1", "/dev/input/js2"]
        for device in slots:
            self.physical_controller_connected(device)
        return page

    def show_physical_test(self):
        self.stack.set_visible_child_name("physical_test")
        for device in self.gamepad_devices():
            self.physical_controller_connected(device)

    def physical_controller_connected(self, device):
        devices = self.gamepad_devices()
        player = devices.index(device) + 1 if device in devices else (
            1 if Path(device).name == "js1" else 2
        )
        if device in self.physical_test_cards:
            card = self.physical_test_cards[device]
            connected = Path(device).exists()
            card["frame"].set_label(
                f"Player {player}  •  {device}" if connected
                else f"Player {player}  •  Not connected"
            )
            card["waiting"].set_text(
                "Press or move any control to discover its input."
                if connected else "Connect a controller to this player slot."
            )
            card["waiting"].set_visible(True)
            return False
        if self.physical_test_empty.get_parent():
            self.physical_test_box.remove(self.physical_test_empty)
        connected = Path(device).exists()
        frame = Gtk.Frame(
            label=f"Player {player}  •  {device}" if connected
            else f"Player {player}  •  Not connected"
        )
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(16)
        content.set_margin_end(16)
        layout = Gtk.Grid(column_spacing=10, row_spacing=10)
        layout.set_column_homogeneous(True)
        layout.add_css_class("controller-shell")
        layout.set_hexpand(True)
        button_visuals = {}

        def add_control(number, text, column, row, width=1, css_class="controller-button"):
            suffix = f"\nB{number}" if number is not None else ""
            label = Gtk.Label(label=f"{text}{suffix}")
            label.set_justify(Gtk.Justification.CENTER)
            label.set_size_request(72 * width, 54)
            label.add_css_class(css_class)
            layout.attach(label, column, row, width, 1)
            if number is not None:
                button_visuals[number] = label
            return label

        left_trigger = add_control(None, "LT\nAxis 2", 0, 0, 2, "controller-shoulder")
        add_control(4, "LB", 2, 0, 2, "controller-shoulder")
        add_control(5, "RB", 7, 0, 2, "controller-shoulder")
        right_trigger = add_control(None, "RT\nAxis 5", 9, 0, 2, "controller-shoulder")
        dpad = {
            "up": add_control(None, "↑", 1, 2),
            "left": add_control(None, "←", 0, 3),
            "down": add_control(None, "↓", 1, 4),
            "right": add_control(None, "→", 2, 3),
        }
        add_control(6, "BACK", 4, 2, 2)
        add_control(8, "HOME", 6, 2)
        add_control(7, "START", 7, 2, 2)
        add_control(11, "FN / TURBO", 5, 4, 2)
        add_control(2, "X", 9, 2)
        add_control(3, "Y", 8, 3)
        add_control(0, "A", 10, 3)
        add_control(1, "B", 9, 4)
        add_control(9, "L3", 3, 6, 2)
        add_control(10, "R3", 7, 6, 2)
        left_stick = Gtk.Label(label="LEFT STICK\nX +0  Y +0")
        left_stick.set_justify(Gtk.Justification.CENTER)
        left_stick.add_css_class("controller-button")
        layout.attach(left_stick, 0, 6, 3, 1)
        right_stick = Gtk.Label(label="RIGHT STICK\nX +0  Y +0")
        right_stick.set_justify(Gtk.Justification.CENTER)
        right_stick.add_css_class("controller-button")
        layout.attach(right_stick, 9, 6, 2, 1)
        buttons_title = Gtk.Label(label="BUTTONS", xalign=0)
        buttons_title.add_css_class("subtitle")
        buttons = Gtk.FlowBox()
        buttons.set_selection_mode(Gtk.SelectionMode.NONE)
        buttons.set_max_children_per_line(8)
        axes_title = Gtk.Label(label="AXES", xalign=0)
        axes_title.add_css_class("subtitle")
        axes = Gtk.FlowBox()
        axes.set_selection_mode(Gtk.SelectionMode.NONE)
        axes.set_max_children_per_line(4)
        waiting = Gtk.Label(
            label="Press or move any control to discover its input."
            if connected else "Connect a controller to this player slot.",
            xalign=0,
        )
        waiting.add_css_class("status")
        content.append(layout)
        content.append(buttons_title)
        content.append(buttons)
        content.append(axes_title)
        content.append(axes)
        content.append(waiting)
        frame.set_child(content)
        self.physical_test_box.append(frame)
        self.physical_test_cards[device] = {
            "frame": frame, "buttons_box": buttons, "axes_box": axes,
            "buttons": {}, "axes": {}, "waiting": waiting,
            "button_visuals": button_visuals,
            "left_stick": left_stick, "right_stick": right_stick,
            "dpad": dpad,
            "left_trigger": left_trigger, "right_trigger": right_trigger,
        }
        self.physical_test_values[device] = {}
        return False

    def update_physical_test_event(self, device, event_type, number, value):
        if device not in self.physical_test_cards:
            self.physical_controller_connected(device)
        card = self.physical_test_cards[device]
        card["waiting"].set_visible(False)
        if event_type == 1:
            visual = card["button_visuals"].get(number)
            if visual:
                if value:
                    visual.add_css_class("test-active")
                else:
                    visual.remove_css_class("test-active")
            label = card["buttons"].get(number)
            if label is None:
                label = Gtk.Label(label=f"Button {number}")
                label.set_size_request(112, 48)
                label.add_css_class("game-title")
                card["buttons_box"].append(label)
                card["buttons"][number] = label
            if value:
                label.add_css_class("test-active")
                label.set_text(f"Button {number}  ●")
            else:
                label.remove_css_class("test-active")
                label.set_text(f"Button {number}")
        elif event_type == 2:
            values = self.physical_test_values.setdefault(device, {})
            values[number] = value
            if number == 6:
                directions = ("left", "right")
            elif number == 7:
                directions = ("up", "down")
            else:
                directions = ()
            if directions:
                negative, positive = directions
                for direction, active in (
                    (negative, value < -16000),
                    (positive, value > 16000),
                ):
                    if active:
                        card["dpad"][direction].add_css_class("test-active")
                    else:
                        card["dpad"][direction].remove_css_class("test-active")
            if number in (0, 1):
                stick = card["left_stick"]
                stick.set_text(
                    f"LEFT STICK\nX {values.get(0, 0):+6d}  Y {values.get(1, 0):+6d}"
                )
                stick_active = any(abs(values.get(axis, 0)) > 8000 for axis in (0, 1))
            elif number in (3, 4):
                stick = card["right_stick"]
                stick.set_text(
                    f"RIGHT STICK\nX {values.get(3, 0):+6d}  Y {values.get(4, 0):+6d}"
                )
                stick_active = any(abs(values.get(axis, 0)) > 8000 for axis in (3, 4))
            else:
                stick = None
                stick_active = False
            if stick:
                if stick_active:
                    stick.add_css_class("test-active")
                else:
                    stick.remove_css_class("test-active")
            trigger = card["left_trigger"] if number == 2 else (
                card["right_trigger"] if number == 5 else None
            )
            if trigger:
                name = "LT" if number == 2 else "RT"
                trigger.set_text(f"{name}\nAxis {number}: {value:+6d}")
                if value > -16000:
                    trigger.add_css_class("test-active")
                else:
                    trigger.remove_css_class("test-active")
            label = card["axes"].get(number)
            if label is None:
                label = Gtk.Label()
                label.set_size_request(190, 48)
                label.add_css_class("game-title")
                card["axes_box"].append(label)
                card["axes"][number] = label
            label.set_text(f"Axis {number}: {value:+6d}")
            active = value > -16000 if number in (2, 5) else abs(value) > 16000
            if active:
                label.add_css_class("test-active")
            else:
                label.remove_css_class("test-active")
        return False

    def controller_connected(self, device):
        self.physical_controller_connected(device)
        if device in self.controller_test_cards:
            return False
        if self.controller_test_empty.get_parent():
            self.controller_test_box.remove(self.controller_test_empty)
        player = int(Path(device).name[2:]) + 1
        frame = Gtk.Frame(label=f"Player {player}  •  {device}")
        grid = Gtk.Grid(column_spacing=12, row_spacing=12)
        grid.set_margin_top(18)
        grid.set_margin_bottom(18)
        grid.set_margin_start(18)
        grid.set_margin_end(18)
        labels = {}
        actions = (
            ("up", "UP"), ("down", "DOWN"), ("left", "LEFT"), ("right", "RIGHT"),
            ("a", "A"), ("b", "B"), ("turboa", "TURBO A"),
            ("turbob", "TURBO B"), ("select", "SELECT"), ("start", "START"),
        )
        for index, (action, text) in enumerate(actions):
            label = Gtk.Label(label=text)
            label.set_size_request(130, 54)
            label.add_css_class("game-title")
            grid.attach(label, index % 5, index // 5, 1, 1)
            labels[action] = label
        frame.set_child(grid)
        self.controller_test_box.append(frame)
        self.controller_test_cards[device] = (frame, labels)
        self.controller_test_state[device] = set()
        return False

    def controller_disconnected(self, device):
        physical = self.physical_test_cards.get(device)
        self.physical_test_values.pop(device, None)
        if physical:
            player = int(Path(device).name[2:]) + 1
            if player <= 2:
                physical["frame"].set_label(f"Player {player}  •  Not connected")
                physical["waiting"].set_text("Connect a controller to this player slot.")
                physical["waiting"].set_visible(True)
                for visual in physical["button_visuals"].values():
                    visual.remove_css_class("test-active")
                for visual in (
                    physical["left_stick"],
                    physical["right_stick"],
                    physical["left_trigger"],
                    physical["right_trigger"],
                    *physical["dpad"].values(),
                ):
                    visual.remove_css_class("test-active")
                physical["left_stick"].set_text("LEFT STICK\nX +0  Y +0")
                physical["right_stick"].set_text("RIGHT STICK\nX +0  Y +0")
                physical["left_trigger"].set_text("LT\nAxis 2")
                physical["right_trigger"].set_text("RT\nAxis 5")
                for label in physical["buttons"].values():
                    label.remove_css_class("test-active")
                for label in physical["axes"].values():
                    label.remove_css_class("test-active")
            else:
                self.physical_test_cards.pop(device, None)
                self.physical_test_box.remove(physical["frame"])
        if not self.physical_test_cards and not self.physical_test_empty.get_parent():
            self.physical_test_box.append(self.physical_test_empty)
        card = self.controller_test_cards.pop(device, None)
        self.controller_test_state.pop(device, None)
        if card:
            self.controller_test_box.remove(card[0])
        if not self.controller_test_cards and not self.controller_test_empty.get_parent():
            self.controller_test_box.append(self.controller_test_empty)
        return False

    def handle_controller_test_event(self, device, event_type, number, value):
        self.update_physical_test_event(device, event_type, number, value)
        if device not in self.controller_test_cards:
            self.controller_connected(device)
        _frame, labels = self.controller_test_cards[device]
        state = self.controller_test_state[device]
        affected = set()
        if event_type == 1:
            action = {
                0: "a", 1: "b", 2: "turboa", 3: "turbob",
                6: "select", 7: "start",
            }.get(number)
            if action:
                affected.add(action)
                (state.add if value else state.discard)(action)
            detail = f"{Path(device).name}: Button {number} {'pressed' if value else 'released'}"
        elif event_type == 2:
            axis_actions = {
                0: ("left", "right"), 1: ("up", "down"),
                6: ("left", "right"), 7: ("up", "down"),
            }.get(number)
            if axis_actions:
                negative, positive = axis_actions
                affected.update(axis_actions)
                state.discard(negative)
                state.discard(positive)
                if value < -16000:
                    state.add(negative)
                elif value > 16000:
                    state.add(positive)
            detail = f"{Path(device).name}: Axis {number} = {value}"
        else:
            return False
        for action in affected:
            if action in state:
                labels[action].add_css_class("test-active")
            else:
                labels[action].remove_css_class("test-active")
        if self.stack.get_visible_child_name() == "controller_test":
            self.controller_test_raw.set_text(detail)
        return False

    def build_details_panel(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        panel.set_margin_start(28)
        panel.set_margin_top(8)
        panel.set_size_request(390, -1)
        self.detail_title = Gtk.Label(label="Select a game", xalign=0)
        self.detail_title.add_css_class("game-title")
        self.detail_title.set_wrap(True)
        self.artwork = Gtk.Picture()
        self.artwork.set_size_request(360, 270)
        self.artwork.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.detail_meta = Gtk.Label(xalign=0, yalign=0)
        self.detail_meta.add_css_class("subtitle")
        self.detail_meta.set_wrap(True)
        panel.append(self.detail_title)
        panel.append(self.artwork)
        panel.append(self.detail_meta)
        return panel

    def build_setup_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        page.set_margin_top(42)
        page.set_margin_bottom(32)
        page.set_margin_start(100)
        page.set_margin_end(100)

        self.setup_title = Gtk.Label(label="NES CONTROLS", xalign=0)
        self.setup_title.add_css_class("hero")
        subtitle = Gtk.Label(
            label="Choose a controller button, then press the keyboard key you want to use.", xalign=0
        )
        subtitle.add_css_class("subtitle")
        page.append(self.setup_title)
        page.append(subtitle)

        self.setup_grid = Gtk.Grid(column_spacing=18, row_spacing=12)
        self.setup_grid.set_valign(Gtk.Align.CENTER)
        setup_scroll = Gtk.ScrolledWindow()
        setup_scroll.set_vexpand(True)
        setup_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        setup_scroll.set_child(self.setup_grid)
        page.append(setup_scroll)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        back = Gtk.Button(label="Back to Settings  [Esc]")
        back.connect("clicked", lambda _button: self.show_settings_menu())
        reset = Gtk.Button(label="Use Recommended Keys")
        reset.connect("clicked", self.set_recommended_keys)
        controls.append(back)
        controls.append(reset)
        page.append(controls)
        return page

    def show_setup(self, system="NES"):
        self.current_control_system = system
        self.capture_action = None
        self.capture_kind = None
        self.capture_token += 1
        self.setup_title.set_text(f"{system} CONTROLS")
        self.populate_mapping_buttons()
        self.refresh_mapping_labels()
        self.stack.set_visible_child_name("setup")

    def populate_mapping_buttons(self):
        while child := self.setup_grid.get_first_child():
            self.setup_grid.remove(child)
        self.mapping_buttons = {}
        self.gamepad_mapping_buttons = {}
        keyboard_header = Gtk.Label(label="Keyboard")
        keyboard_header.add_css_class("subtitle")
        gamepad_header = Gtk.Label(label="Gamepad")
        gamepad_header.add_css_class("subtitle")
        self.setup_grid.attach(keyboard_header, 1, 0, 1, 1)
        self.setup_grid.attach(gamepad_header, 2, 0, 1, 1)
        for index, (action, label) in enumerate(CONTROL_BUTTONS[self.current_control_system]):
            name = Gtk.Label(label=label, xalign=0)
            name.add_css_class("game-title")
            keyboard_button = Gtk.Button()
            keyboard_button.set_size_request(190, 42)
            keyboard_button.connect("clicked", self.begin_capture, action, "keyboard")
            gamepad_button = Gtk.Button()
            gamepad_button.set_size_request(190, 42)
            gamepad_button.connect("clicked", self.begin_capture, action, "gamepad")
            self.mapping_buttons[action] = keyboard_button
            self.gamepad_mapping_buttons[action] = gamepad_button
            row = index + 1
            self.setup_grid.attach(name, 0, row, 1, 1)
            self.setup_grid.attach(keyboard_button, 1, row, 1, 1)
            self.setup_grid.attach(gamepad_button, 2, row, 1, 1)

    def read_mapping(self):
        path = self.control_config_path(self.current_control_system)
        if not path.exists():
            return dict(RECOMMENDED_KEYS[self.current_control_system])
        text = path.read_text(encoding="utf-8")
        mapping = dict(RECOMMENDED_KEYS[self.current_control_system])
        for action, _label in CONTROL_BUTTONS[self.current_control_system]:
            config_key = self.retroarch_config_key(action)
            match = re.search(
                rf'^{config_key}\s*=\s*"([^"]*)"', text, re.MULTILINE
            )
            if match:
                mapping[action] = match.group(1)
        return mapping

    def read_gamepad_mapping(self):
        path = self.control_config_path(self.current_control_system)
        if not path.exists():
            return {}
        text = path.read_text(encoding="utf-8")
        mapping = {}
        for action, _label in CONTROL_BUTTONS[self.current_control_system]:
            config_key = self.retroarch_config_key(action)
            button = re.search(
                rf'^{config_key}_btn\s*=\s*"(\d+)"', text, re.MULTILINE
            )
            axis = re.search(
                rf'^{config_key}_axis\s*=\s*"([+-]\d+)"', text, re.MULTILINE
            )
            if button:
                mapping[action] = ("btn", button.group(1))
            elif axis:
                mapping[action] = ("axis", axis.group(1))
        return mapping

    @staticmethod
    def control_config_path(system):
        return CONTROL_DIR / f"{system.casefold()}.cfg"

    @staticmethod
    def retroarch_config_key(action):
        prefix = "input_" if action in HOTKEY_ACTIONS else "input_player1_"
        return f"{prefix}{RETROARCH_ACTIONS[action]}"

    def refresh_mapping_labels(self):
        mapping = self.read_mapping()
        gamepad_mapping = self.read_gamepad_mapping()
        for action, _label in CONTROL_BUTTONS[self.current_control_system]:
            raw = mapping.get(action, "")
            keyval = Gdk.keyval_from_name(self.retro_to_gdk_name(raw)) if raw else 0
            key_name = Gdk.keyval_name(keyval) if keyval else None
            self.mapping_buttons[action].set_label(key_name or "Not set")
            binding = gamepad_mapping.get(action)
            self.gamepad_mapping_buttons[action].set_label(
                self.gamepad_binding_label(binding) if binding else "Not set"
            )

    def begin_capture(self, button, action, kind):
        if self.capture_action and self.capture_action in self.mapping_buttons:
            self.refresh_mapping_labels()
        self.capture_action = action
        self.capture_kind = kind
        self.capture_token += 1
        if kind == "keyboard":
            button.set_label("Press a key…")
            self.window.grab_focus()
        else:
            devices = self.gamepad_devices()
            if not devices:
                self.capture_action = None
                self.capture_kind = None
                button.set_label("Connect gamepad")
                return
            button.set_label("Press a button…")
            token = self.capture_token
            threading.Thread(
                target=self.capture_gamepad_event,
                args=(devices[0], action, token),
                daemon=True,
            ).start()

    def save_key(self, action, keyval):
        self.write_retroarch_settings({action: self.gdk_to_retro_name(keyval)})

    def capture_gamepad_event(self, device, action, token):
        try:
            with open(device, "rb", buffering=0) as gamepad:
                while token == self.capture_token:
                    data = gamepad.read(8)
                    if len(data) != 8:
                        break
                    _time, value, event_type, number = struct.unpack("<IhBB", data)
                    if event_type & 0x80:
                        continue
                    event_type &= 0x7F
                    if event_type == 1 and value:
                        GLib.idle_add(
                            self.complete_gamepad_capture, action, ("btn", str(number)), token
                        )
                        return
                    if event_type == 2 and abs(value) > 16000:
                        direction = "+" if value > 0 else "-"
                        GLib.idle_add(
                            self.complete_gamepad_capture,
                            action,
                            ("axis", f"{direction}{number}"),
                            token,
                        )
                        return
        except OSError:
            GLib.idle_add(self.cancel_gamepad_capture, token)

    def complete_gamepad_capture(self, action, binding, token):
        if token != self.capture_token:
            return False
        keyboard = self.read_mapping()
        gamepad = self.read_gamepad_mapping()
        gamepad[action] = binding
        self.write_control_config(keyboard, gamepad)
        self.capture_action = None
        self.capture_kind = None
        self.refresh_mapping_labels()
        return False

    def cancel_gamepad_capture(self, token):
        if token == self.capture_token:
            self.capture_action = None
            self.capture_kind = None
            self.refresh_mapping_labels()
        return False

    @staticmethod
    def gamepad_binding_label(binding):
        kind, value = binding
        if kind == "btn":
            return f"Button {value}"
        direction = "+" if value.startswith("+") else "−"
        return f"Axis {value[1:]} {direction}"

    @staticmethod
    def gdk_to_retro_name(keyval):
        name = (Gdk.keyval_name(keyval) or "").lower()
        aliases = {"return": "enter", "shift_l": "lshift", "shift_r": "rshift",
                   "control_l": "lctrl", "control_r": "rctrl",
                   **{str(number): f"num{number}" for number in range(10)}}
        return aliases.get(name, name)

    @staticmethod
    def retro_to_gdk_name(name):
        aliases = {"enter": "Return", "lshift": "Shift_L", "rshift": "Shift_R",
                   "lctrl": "Control_L", "rctrl": "Control_R",
                   **{f"num{number}": str(number) for number in range(10)}}
        return aliases.get(name, name)

    def write_retroarch_settings(self, settings):
        mapping = self.read_mapping()
        mapping.update(settings)
        self.write_control_config(mapping, self.read_gamepad_mapping())

    def write_control_config(self, mapping, gamepad_mapping):
        CONTROL_DIR.mkdir(parents=True, exist_ok=True)
        lines = []
        defaults = DEFAULT_GAMEPAD_BINDINGS[self.current_control_system]
        for action, _label in CONTROL_BUTTONS[self.current_control_system]:
            config_key = self.retroarch_config_key(action)
            lines.append(f'{config_key} = "{mapping[action]}"')
            binding = gamepad_mapping.get(action, defaults.get(action))
            if binding:
                kind, value = binding
                lines.append(f'{config_key}_{kind} = "{value}"')
            if action not in HOTKEY_ACTIONS and action in defaults:
                kind, value = defaults[action]
                player2_key = config_key.replace("input_player1_", "input_player2_", 1)
                lines.append(f'{player2_key}_{kind} = "{value}"')
        lines.extend((
            'input_player1_joypad_index = "1"',
            'input_player2_joypad_index = "2"',
        ))
        self.control_config_path(self.current_control_system).write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    @staticmethod
    def ensure_control_config(system):
        path = GameLauncher.control_config_path(system)
        defaults = DEFAULT_GAMEPAD_BINDINGS[system]
        if not path.exists():
            CONTROL_DIR.mkdir(parents=True, exist_ok=True)
            lines = []
            for action, _label in CONTROL_BUTTONS[system]:
                config_key = GameLauncher.retroarch_config_key(action)
                lines.append(f'{config_key} = "{RECOMMENDED_KEYS[system][action]}"')
                binding = defaults.get(action)
                if binding:
                    kind, value = binding
                    lines.append(f'{config_key}_{kind} = "{value}"')
                    player2_key = config_key.replace("input_player1_", "input_player2_", 1)
                    lines.append(f'{player2_key}_{kind} = "{value}"')
            lines.extend((
                'input_player1_joypad_index = "1"',
                'input_player2_joypad_index = "2"',
            ))
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        else:
            text = path.read_text(encoding="utf-8")
            additions = []
            text = re.sub(
                r'^input_player1_joypad_index\s*=.*$',
                'input_player1_joypad_index = "1"',
                text,
                flags=re.MULTILINE,
            )
            text = re.sub(
                r'^input_player2_joypad_index\s*=.*$',
                'input_player2_joypad_index = "2"',
                text,
                flags=re.MULTILINE,
            )
            for action in HOTKEY_ACTIONS:
                config_key = GameLauncher.retroarch_config_key(action)
                if not re.search(rf'^{config_key}\s*=', text, re.MULTILINE):
                    additions.append(f'{config_key} = "{RECOMMENDED_KEYS[system][action]}"')
            if not re.search(r'^input_player1_joypad_index\s*=', text, re.MULTILINE):
                additions.append('input_player1_joypad_index = "1"')
            if not re.search(r'^input_player2_joypad_index\s*=', text, re.MULTILINE):
                additions.append('input_player2_joypad_index = "2"')
            for action, (kind, value) in defaults.items():
                config_key = GameLauncher.retroarch_config_key(action)
                if not re.search(rf'^{config_key}_(?:btn|axis)\s*=', text, re.MULTILINE):
                    additions.append(f'{config_key}_{kind} = "{value}"')
                player2_key = config_key.replace("input_player1_", "input_player2_", 1)
                if not re.search(rf'^{player2_key}_(?:btn|axis)\s*=', text, re.MULTILINE):
                    additions.append(f'{player2_key}_{kind} = "{value}"')
            path.write_text(
                text.rstrip() + ("\n" + "\n".join(additions) if additions else "") + "\n",
                encoding="utf-8",
            )
        return path

    def set_recommended_keys(self, _button):
        self.write_retroarch_settings(RECOMMENDED_KEYS[self.current_control_system])
        self.refresh_mapping_labels()

    def on_game_selected(self, _listbox, row):
        game = getattr(row, "game_path", None) if row else None
        if not game:
            return
        title = self.pretty_name(game)
        self.detail_title.set_text(title)
        self.artwork.set_filename(None)
        self.game_background.set_filename(None)
        year, genre, publisher, players = GAME_METADATA.get(
            title.casefold(), ("Unknown", f"{self.current_system} game", "Unknown", "Unknown")
        )
        self.detail_meta.set_text(
            f"Year: {year}\nGenre: {genre}\nPublisher: {publisher}\nPlayers: {players}\n\n{game.name}"
        )
        threading.Thread(
            target=self.fetch_artwork, args=(game,), daemon=True
        ).start()

    def fetch_artwork(self, game):
        identity = hashlib.sha1(str(game).encode()).hexdigest()[:12]
        screenshot = BUNDLED_ART / f"{identity}-screenshot.png"
        if not screenshot.exists():
            GLib.idle_add(self.show_artwork, game, None, None)
            return

        blur_directory = ART_CACHE / "blurred"
        blur_directory.mkdir(parents=True, exist_ok=True)
        blurred = blur_directory / f"{identity}.png"
        if not blurred.exists() or blurred.stat().st_mtime < screenshot.stat().st_mtime:
            temporary = blur_directory / f".{identity}-{threading.get_ident()}.png"
            try:
                try:
                    with Image.open(screenshot) as image:
                        image.load()
                        image.convert("RGB").filter(ImageFilter.GaussianBlur(24)).save(
                            temporary, "PNG"
                        )
                except (OSError, UnidentifiedImageError):
                    GLib.idle_add(self.show_artwork, game, None, None)
                    return
                os.replace(temporary, blurred)
            finally:
                temporary.unlink(missing_ok=True)
        GLib.idle_add(self.show_artwork, game, str(screenshot), str(blurred))

    def show_artwork(self, game, screenshot, blurred):
        row = self.listbox.get_selected_row()
        if not row or getattr(row, "game_path", None) != game:
            return False
        if screenshot:
            self.artwork.set_filename(screenshot)
        if blurred:
            self.game_background.set_filename(blurred)
        return False

    def refresh(self):
        if self.current_system in ("GBA", "NDS"):
            extension = ".gba" if self.current_system == "GBA" else ".nds"
            root = GBA_ROOT if self.current_system == "GBA" else DOWNLOADS
            direct_games = [p for p in root.rglob(f"*{extension}") if p.is_file()]
            archives = [
                p for p in root.rglob("*.zip")
                if self.is_archive_with_extension(p, extension)
            ]
            games = sorted(direct_games + archives, key=lambda path: path.stem.casefold())
            self.pages = [(0, games)]
            self.games = games
            self.current_page = 0
            self.render_page()
            return
        page_dirs = []
        if GAME_ROOT.exists():
            for path in GAME_ROOT.iterdir():
                if path.is_dir() and (match := PAGE_DIRECTORY.match(path.name)):
                    page_dirs.append((int(match.group(1)), path))
        page_dirs.sort(key=lambda item: item[0])
        self.pages = []
        for page_number, directory in page_dirs:
            games = sorted(
                (p for p in directory.rglob("*.nes") if p.is_file()),
                key=self.game_sort_key,
            )
            self.pages.append((page_number, games))
        if not self.pages:
            games = sorted(
                (p for p in GAME_ROOT.rglob("*.nes") if p.is_file()),
                key=self.game_sort_key,
            )
            self.pages = [(0, games)]
        self.games = [game for _page, games in self.pages for game in games]
        self.current_page = min(self.current_page, len(self.pages) - 1)
        self.render_page()

    def render_page(self):
        while child := self.listbox.get_first_child():
            self.listbox.remove(child)
        page_number, page_games = self.pages[self.current_page]
        for game in page_games:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            box.set_margin_top(10)
            box.set_margin_bottom(10)
            box.set_margin_start(18)
            box.set_margin_end(18)
            name = Gtk.Label(label=self.pretty_name(game), xalign=0)
            name.add_css_class("game-title")
            root = {
                "NES": GAME_ROOT,
                "GBA": GBA_ROOT,
                "NDS": DOWNLOADS,
            }[self.current_system]
            path = Gtk.Label(label=str(game.relative_to(root)), xalign=0)
            path.add_css_class("game-path")
            box.append(name)
            box.append(path)
            row.set_child(box)
            row.game_path = game
            self.listbox.append(row)
        if page_games:
            self.listbox.select_row(self.listbox.get_row_at_index(0))
            if self.current_system == "NES":
                self.status.set_text(
                    f"Page {page_number}  •  {len(page_games)} game(s)  •  {len(self.games)} total"
                )
            else:
                self.status.set_text(f"{len(page_games)} {self.current_system} game(s)  •  A–Z")
        else:
            empty = Gtk.Label(label=f"No {self.current_system} games found", xalign=0)
            empty.add_css_class("game-title")
            empty.set_margin_top(30)
            self.listbox.append(empty)
            self.status.set_text("0 games")

    def change_page(self, offset):
        if self.current_system != "NES" or not self.pages:
            return
        new_page = max(0, min(self.current_page + offset, len(self.pages) - 1))
        if new_page != self.current_page:
            self.current_page = new_page
            self.render_page()

    @staticmethod
    def is_archive_with_extension(path, extension):
        try:
            with zipfile.ZipFile(path) as archive:
                return any(name.casefold().endswith(extension) for name in archive.namelist())
        except (OSError, zipfile.BadZipFile):
            return False

    @staticmethod
    def game_sort_key(path):
        match = re.match(r"^\s*(\d+)", path.stem)
        return (int(match.group(1)) if match else 10**9, path.name.casefold())

    @staticmethod
    def pretty_name(path):
        name = path.stem.replace("_", " ").replace("-", " ")
        name = re.sub(r"^\s*\d+\s+", "", name)
        return " ".join(name.split())

    def launch_row(self, _listbox, row):
        game = getattr(row, "game_path", None)
        if not game:
            return
        self.status.set_text(f"Launching {self.pretty_name(game)}…")
        try:
            core = {"NES": NES_CORE, "GBA": GBA_CORE, "NDS": NDS_CORE}[self.current_system]
            controls = self.ensure_control_config(self.current_system)
            identity = hashlib.sha1(str(game).encode()).hexdigest()[:12]
            thumbnail = BUNDLED_ART / f"{identity}-screenshot.png"
            capture = None
            append_configs = [str(controls)]
            if not self.thumbnail_is_usable(thumbnail, self.current_system):
                capture = self.start_thumbnail_capture(game, controls)
                append_configs.append(str(capture[0]))
            process = subprocess.Popen(
                [
                    RETROARCH,
                    "--fullscreen",
                    f"--appendconfig={'|'.join(append_configs)}",
                    "-L",
                    core,
                    str(game),
                ]
            )
            self.game_running = True
            self.running_game = game
            self.live_capture_token += 1
            token = self.live_capture_token
            if capture:
                _capture_config, capture_directory = capture
                threading.Thread(
                    target=self.watch_thumbnail_capture,
                    args=(game, capture_directory, token),
                    daemon=True,
                ).start()
        except OSError as error:
            self.window.present()
            self.status.set_text(f"Could not start RetroArch: {error}")
            return
        threading_source = GLib.child_watch_add(process.pid, self.game_finished)
        self._watch = threading_source

    def game_finished(self, _pid, _status):
        self.game_running = False
        self.running_game = None
        page_number, page_games = self.pages[self.current_page]
        if self.current_system == "NES":
            self.status.set_text(
                f"Page {page_number}  •  {len(page_games)} game(s)  •  {len(self.games)} total"
            )
        else:
            self.status.set_text(f"{len(page_games)} {self.current_system} game(s)  •  A–Z")
        self.window.present()

    @staticmethod
    def thumbnail_is_usable(path, system):
        if not path.exists():
            return False
        try:
            with Image.open(path) as image:
                image.verify()
            if system == "GBA":
                with Image.open(path) as image:
                    # Reject near-empty mGBA frames (for example a white screen
                    # with only the pause indicator) so Start can recapture them.
                    if image.convert("L").entropy() < 0.5:
                        return False
        except (OSError, UnidentifiedImageError):
            return False
        return True

    @staticmethod
    def start_thumbnail_capture(game, controls):
        identity = hashlib.sha1(str(game).encode()).hexdigest()[:12]
        capture_directory = ART_CACHE / "start-captures" / identity
        capture_directory.mkdir(parents=True, exist_ok=True)
        for old_capture in capture_directory.glob("*.png"):
            old_capture.unlink(missing_ok=True)

        text = controls.read_text(encoding="utf-8")
        lines = [
            f'screenshot_directory = "{capture_directory}"',
            'auto_screenshot_filename = "true"',
        ]
        mappings = {
            match.group(1): match.group(2)
            for match in re.finditer(
                r'^input_player1_start(?:_(btn|axis))?\s*=\s*"([^"]*)"',
                text,
                re.MULTILINE,
            )
        }
        keyboard = mappings.get(None)
        if keyboard and keyboard != "nul":
            lines.append(f'input_screenshot = "{keyboard}"')
        for kind in ("btn", "axis"):
            value = mappings.get(kind)
            if value and value != "nul":
                lines.append(f'input_screenshot_{kind} = "{value}"')

        capture_config = capture_directory / "capture.cfg"
        capture_config.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return capture_config, capture_directory

    def watch_thumbnail_capture(self, game, capture_directory, token):
        screenshot = None
        previous_size = -1
        stable_checks = 0
        while token == self.live_capture_token:
            captures = sorted(
                capture_directory.glob("*.png"),
                key=lambda path: path.stat().st_mtime,
            )
            if captures:
                candidate = captures[0]
                size = candidate.stat().st_size
                if size > 0 and size == previous_size:
                    stable_checks += 1
                else:
                    previous_size = size
                    stable_checks = 0
                if stable_checks >= 2:
                    try:
                        with Image.open(candidate) as image:
                            image.verify()
                        screenshot = candidate
                        break
                    except (OSError, UnidentifiedImageError):
                        stable_checks = 0
            if not self.game_running or self.running_game != game:
                break
            time.sleep(0.1)
        if not screenshot:
            return

        identity = hashlib.sha1(str(game).encode()).hexdigest()[:12]
        target = BUNDLED_ART / f"{identity}-screenshot.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.parent / f".{identity}-{threading.get_ident()}.png"
        try:
            with screenshot.open("rb") as source, temporary.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            with Image.open(temporary) as image:
                image.verify()
            os.replace(temporary, target)
        except (OSError, UnidentifiedImageError):
            return
        finally:
            temporary.unlink(missing_ok=True)
        GLib.idle_add(self.thumbnail_captured, game)

    def thumbnail_captured(self, game):
        row = self.listbox.get_selected_row()
        if row and getattr(row, "game_path", None) == game:
            self.fetch_artwork(game)
        return False

    def on_key(self, _controller, keyval, _keycode, _state):
        if (_state & Gdk.ModifierType.CONTROL_MASK) and keyval in (Gdk.KEY_c, Gdk.KEY_C):
            self.quit()
            return True
        if self.capture_action and self.capture_kind == "keyboard":
            if keyval == Gdk.KEY_Escape:
                self.capture_action = None
                self.capture_kind = None
                self.refresh_mapping_labels()
                return True
            action = self.capture_action
            self.capture_action = None
            self.capture_kind = None
            self.save_key(action, keyval)
            self.refresh_mapping_labels()
            return True
        if self.capture_action and self.capture_kind == "gamepad" and keyval == Gdk.KEY_Escape:
            self.capture_token += 1
            self.capture_action = None
            self.capture_kind = None
            self.refresh_mapping_labels()
            return True
        if self.stack.get_visible_child_name() in (
            "setup", "controller_test", "physical_test"
        ):
            if keyval == Gdk.KEY_Escape:
                self.show_settings_menu()
                return True
            return False
        if self.stack.get_visible_child_name() == "settings_menu":
            if keyval == Gdk.KEY_Escape:
                self.show_home()
                return True
            if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                row = self.settings_listbox.get_selected_row()
                if row:
                    self.activate_settings_row(self.settings_listbox, row)
                return True
            return False
        if self.stack.get_visible_child_name() == "home":
            if keyval == Gdk.KEY_Escape:
                self.quit()
                return True
            if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                row = self.home_listbox.get_selected_row()
                if row:
                    self.activate_home_row(self.home_listbox, row)
                return True
            return False
        if keyval == Gdk.KEY_Escape:
            self.show_home()
            return True
        if keyval == Gdk.KEY_F1:
            self.show_settings_menu()
            return True
        if keyval == Gdk.KEY_F5:
            self.refresh()
            return True
        if keyval == Gdk.KEY_Left:
            self.change_page(-1)
            return True
        if keyval == Gdk.KEY_Right:
            self.change_page(1)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            row = self.listbox.get_selected_row()
            if row:
                self.launch_row(self.listbox, row)
            return True
        return False


if __name__ == "__main__":
    try:
        exit_code = GameLauncher().run()
    except KeyboardInterrupt:
        exit_code = 0
    raise SystemExit(exit_code)
