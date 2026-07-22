#!/usr/bin/env python3
import os
import subprocess
import re
import hashlib
import platform
import threading
import urllib.parse
import urllib.request
import zipfile
import glob
import struct
import time
from pathlib import Path

from launcher_platform import (
    emulator_command,
    fceux_environment,
    fceux_executable,
    game_root,
    platform_help,
)

try:
    import gi
except ImportError as error:
    raise SystemExit(
        "GTK 4 Python bindings are required.\n"
        "On macOS with Homebrew, run: brew install gtk4 pygobject3"
    ) from error

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk


ROM_EXTENSIONS = {".nes"}
PAGE_DIRECTORY = re.compile(r"^Page\s+(\d+)$", re.IGNORECASE)
APP_DIR = Path(__file__).resolve().parent
GAME_ROOT = game_root(APP_DIR)
SPLASH_IMAGE = APP_DIR / "assets" / "logo_slogan_2.png"
SPLASH_DURATION_MS = 2000
DOWNLOADS = Path.home() / "Downloads"
RETROARCH = "/usr/bin/retroarch"
NES_CORE = "/usr/lib/x86_64-linux-gnu/libretro/nestopia_libretro.so"
GBA_CORE = "/usr/lib/x86_64-linux-gnu/libretro/mgba_libretro.so"
NDS_CORE = "/usr/lib/x86_64-linux-gnu/libretro/desmume_libretro.so"
CONTROL_DIR = Path.home() / ".config" / "yones" / "controls"
ART_CACHE = (
    Path.home() / "Library" / "Caches" / "nes-game-library"
    if platform.system() == "Darwin"
    else Path.home() / ".cache" / "nes-game-library"
)
THUMBNAIL_ROOTS = {
    "NES": "https://thumbnails.libretro.com/Nintendo%20-%20Nintendo%20Entertainment%20System",
    "GBA": "https://thumbnails.libretro.com/Nintendo%20-%20Game%20Boy%20Advance",
    "NDS": "https://thumbnails.libretro.com/Nintendo%20-%20Nintendo%20DS",
}
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

    def do_activate(self):
        if self.window:
            self.window.present()
            return

        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("NES Game Library")
        self.window.fullscreen()

        css = Gtk.CssProvider()
        css.load_from_data(b"""
            window { background: #090b12; color: #f7f7fb; }
            label { color: #f7f7fb; }
            button {
                color: #111827;
                background-image: none;
                background-color: #f3f4f6;
                border: 1px solid #9ca3af;
            }
            button label { color: #111827; }
            button:hover { background-color: #ffffff; }
            button:hover label { color: #111827; }
            button:active { background-color: #d1d5db; }
            .hero { font-size: 42px; font-weight: 900; color: #ffdf5d; }
            .subtitle { font-size: 16px; color: #9da6ba; }
            list { background: transparent; }
            row { border-radius: 14px; margin: 5px 0; padding: 5px; }
            row:selected { background: #5846e8; }
            row:selected label { color: #ffffff; }
            .game-title { font-size: 25px; font-weight: 700; color: #f7f7fb; }
            .game-path { font-size: 13px; color: #aeb6c8; }
            .hint { font-size: 14px; color: #aeb6c8; }
            .status { font-size: 15px; color: #6ee7b7; }
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
        hint_text = "↑ ↓ Select    ← → Page    Enter Play    F5 Refresh    Esc Back"
        if platform.system() == "Darwin":
            hint_text += "    •    Game: Arrows Move  Q Select  W Start  A=A  S=B  Z/X Turbo A/B"
        hint = Gtk.Label(label=hint_text, xalign=0)
        hint.add_css_class("hint")
        hint.set_hexpand(True)
        self.status = Gtk.Label(xalign=1)
        self.status.add_css_class("status")
        footer.append(hint)
        footer.append(self.status)
        outer.append(footer)
        if platform.system() == "Darwin":
            settings = Gtk.Button(label="Open FCEUX Settings  [F1]")
            settings.connect("clicked", lambda _button: self.open_fceux_settings())
        else:
            settings = Gtk.Button(label="Controller Setup  [F1]")
            settings.connect("clicked", lambda _button: self.show_settings_menu())
        footer.append(settings)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(180)
        self.stack.add_named(self.build_splash_page(), "splash")
        self.stack.add_named(self.build_home_page(), "home")
        self.stack.add_named(outer, "games")
        self.stack.add_named(self.build_settings_menu(), "settings_menu")
        self.stack.add_named(self.build_setup_page(), "setup")
        self.window.set_child(self.stack)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.on_key)
        self.window.add_controller(keys)
        self.refresh()
        self.stack.set_visible_child_name("splash")
        self.window.present()
        self.start_gamepad_monitor()
        GLib.timeout_add(SPLASH_DURATION_MS, self.finish_splash)

    def build_splash_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page.set_halign(Gtk.Align.FILL)
        page.set_valign(Gtk.Align.FILL)
        page.set_hexpand(True)
        page.set_vexpand(True)

        monitors = Gdk.Display.get_default().get_monitors()
        monitor = monitors.get_item(0) if monitors.get_n_items() else None
        screen_width = monitor.get_geometry().width if monitor else 1440
        logo_width = max(480, round(screen_width * 0.5))
        logo_height = round(logo_width * 512 / 1788)
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            str(SPLASH_IMAGE), logo_width, logo_height, True
        )
        logo = Gtk.Picture.new_for_pixbuf(pixbuf)
        logo.set_content_fit(Gtk.ContentFit.CONTAIN)
        logo.set_can_shrink(True)
        logo.set_size_request(logo_width, logo_height)
        logo.set_halign(Gtk.Align.CENTER)
        logo.set_valign(Gtk.Align.CENTER)
        page.append(logo)
        return page

    def finish_splash(self):
        if self.stack.get_visible_child_name() == "splash":
            self.stack.set_visible_child_name("home")
            self.window.present()
            GLib.idle_add(self.focus_home)
        return False

    def focus_home(self):
        self.home_listbox.grab_focus()
        return False

    def start_gamepad_monitor(self):
        if self.gamepad_monitor_started:
            return
        self.gamepad_monitor_started = True
        threading.Thread(target=self.monitor_gamepad, daemon=True).start()

    def monitor_gamepad(self):
        """Hot-plug monitor for common USB/Bluetooth controllers via joydev."""
        while True:
            devices = sorted(glob.glob("/dev/input/js*"))
            if not devices:
                time.sleep(1)
                continue
            try:
                fd = os.open(devices[0], os.O_RDONLY | os.O_NONBLOCK)
                axis_active = {}
                try:
                    while devices[0] in glob.glob("/dev/input/js*"):
                        try:
                            data = os.read(fd, 8)
                        except BlockingIOError:
                            time.sleep(0.02)
                            continue
                        if len(data) != 8:
                            break
                        _stamp, value, event_type, number = struct.unpack("<IhBB", data)
                        if event_type & 0x80:
                            continue
                        event_type &= 0x7F
                        action = None
                        if event_type == 1 and value:
                            action = {0: "accept", 1: "back", 7: "accept"}.get(number)
                        elif event_type == 2:
                            direction = 1 if value > 16000 else -1 if value < -16000 else 0
                            previous = axis_active.get(number, 0)
                            axis_active[number] = direction
                            if direction and direction != previous:
                                if number in (0, 6):
                                    action = "right" if direction > 0 else "left"
                                elif number in (1, 7):
                                    action = "down" if direction > 0 else "up"
                        if action:
                            GLib.idle_add(self.handle_gamepad_navigation, action)
                finally:
                    os.close(fd)
            except OSError:
                pass
            time.sleep(1)

    def handle_gamepad_navigation(self, action):
        if self.game_running or self.capture_kind == "gamepad":
            return False
        screen = self.stack.get_visible_child_name()
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
                    self.launch_game(row.game_path)
            return False
        if action == "back":
            if screen == "games" or screen == "settings_menu":
                self.show_home()
            elif screen == "setup":
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
        source = GAME_ROOT if system == "NES" else DOWNLOADS
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
        for system in ("NES", "GBA", "NDS"):
            row = Gtk.ListBoxRow()
            label = Gtk.Label(label=f"{system} Controls", xalign=0)
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
        self.show_setup(getattr(row, "control_system", "NES"))

    def build_details_panel(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        panel.set_margin_start(28)
        panel.set_margin_top(8)
        panel.set_size_request(390, -1)
        self.detail_title = Gtk.Label(label="Select a game", xalign=0)
        self.detail_title.add_css_class("game-title")
        self.detail_title.set_wrap(True)
        self.boxart = Gtk.Picture()
        self.boxart.set_size_request(260, 300)
        self.boxart.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.screenshot = Gtk.Picture()
        self.screenshot.set_size_request(320, 180)
        self.screenshot.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.detail_meta = Gtk.Label(xalign=0, yalign=0)
        self.detail_meta.add_css_class("subtitle")
        self.detail_meta.set_wrap(True)
        panel.append(self.detail_title)
        panel.append(self.boxart)
        panel.append(self.screenshot)
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
        GLib.idle_add(self.focus_mapping_button, "up", "keyboard")

    def focus_mapping_button(self, action, kind="keyboard"):
        buttons = self.mapping_buttons if kind == "keyboard" else self.gamepad_mapping_buttons
        button = buttons.get(action)
        if button:
            button.grab_focus()
        return False

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

    def open_fceux_settings(self):
        executable = fceux_executable()
        if not executable:
            self.status.set_text(platform_help())
            return
        try:
            subprocess.Popen([str(executable)], env=fceux_environment())
            self.status.set_text("FCEUX opened — configure input from its Config menu")
        except OSError as error:
            self.status.set_text(f"Could not start FCEUX: {error}")

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
        direction_names = {
            "up": "Up",
            "down": "Down",
            "left": "Left",
            "right": "Right",
        }
        for action, _label in CONTROL_BUTTONS[self.current_control_system]:
            raw = mapping.get(action, "")
            keyval = Gdk.keyval_from_name(self.retro_to_gdk_name(raw)) if raw else 0
            key_name = direction_names.get(raw.casefold())
            if not key_name:
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
            devices = sorted(glob.glob("/dev/input/js*"))
            if not devices:
                self.capture_action = None
                self.capture_kind = None
                button.set_label("Connect gamepad")
                button.grab_focus()
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
        self.focus_mapping_button(action, "gamepad")
        return False

    def cancel_gamepad_capture(self, token):
        if token == self.capture_token:
            action = self.capture_action
            self.capture_action = None
            self.capture_kind = None
            self.refresh_mapping_labels()
            if action:
                self.focus_mapping_button(action, "gamepad")
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
        for action, _label in CONTROL_BUTTONS[self.current_control_system]:
            config_key = self.retroarch_config_key(action)
            lines.append(f'{config_key} = "{mapping[action]}"')
            binding = gamepad_mapping.get(action)
            if binding:
                kind, value = binding
                lines.append(f'{config_key}_{kind} = "{value}"')
        lines.append('input_player1_joypad_index = "0"')
        self.control_config_path(self.current_control_system).write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    @staticmethod
    def ensure_control_config(system):
        path = GameLauncher.control_config_path(system)
        if not path.exists():
            CONTROL_DIR.mkdir(parents=True, exist_ok=True)
            lines = []
            for action, _label in CONTROL_BUTTONS[system]:
                config_key = GameLauncher.retroarch_config_key(action)
                lines.append(f'{config_key} = "{RECOMMENDED_KEYS[system][action]}"')
            lines.append('input_player1_joypad_index = "0"')
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        else:
            text = path.read_text(encoding="utf-8")
            additions = []
            for action in HOTKEY_ACTIONS:
                config_key = GameLauncher.retroarch_config_key(action)
                if not re.search(rf'^{config_key}\s*=', text, re.MULTILINE):
                    additions.append(f'{config_key} = "{RECOMMENDED_KEYS[system][action]}"')
            if not re.search(r'^input_player1_joypad_index\s*=', text, re.MULTILINE):
                additions.append('input_player1_joypad_index = "0"')
            if additions:
                path.write_text(text.rstrip() + "\n" + "\n".join(additions) + "\n", encoding="utf-8")
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
        self.boxart.set_filename(None)
        self.screenshot.set_filename(None)
        year, genre, publisher, players = GAME_METADATA.get(
            title.casefold(), ("Unknown", f"{self.current_system} game", "Unknown", "Unknown")
        )
        self.detail_meta.set_text(
            f"Year: {year}\nGenre: {genre}\nPublisher: {publisher}\nPlayers: {players}\n\n{game.name}"
        )
        threading.Thread(
            target=self.fetch_artwork, args=(game, title, self.current_system), daemon=True
        ).start()

    def fetch_artwork(self, game, title, system):
        ART_CACHE.mkdir(parents=True, exist_ok=True)
        identity = hashlib.sha1(str(game).encode()).hexdigest()[:12]
        results = {}
        for kind, folder in (("boxart", "Named_Boxarts"), ("screenshot", "Named_Snaps")):
            target = ART_CACHE / f"{identity}-{kind}.png"
            if not target.exists():
                for candidate in (f"{title} (USA)", f"{title} (USA, Europe)", title):
                    filename = urllib.parse.quote(f"{candidate}.png", safe="()',")
                    url = f"{THUMBNAIL_ROOTS[system]}/{folder}/{filename}"
                    try:
                        request = urllib.request.Request(
                            url, headers={"User-Agent": "NES-Game-Library/1.0"}
                        )
                        with urllib.request.urlopen(request, timeout=8) as response:
                            data = response.read()
                        if data.startswith(b"\x89PNG"):
                            target.write_bytes(data)
                            break
                    except Exception:
                        continue
            if target.exists():
                results[kind] = str(target)
        GLib.idle_add(self.show_artwork, game, results)

    def show_artwork(self, game, results):
        row = self.listbox.get_selected_row()
        if not row or getattr(row, "game_path", None) != game:
            return False
        if results.get("boxart"):
            self.boxart.set_filename(results["boxart"])
        if results.get("screenshot"):
            self.screenshot.set_filename(results["screenshot"])
        return False

    def refresh(self):
        if self.current_system in ("GBA", "NDS"):
            extension = ".gba" if self.current_system == "GBA" else ".nds"
            direct_games = [p for p in DOWNLOADS.rglob(f"*{extension}") if p.is_file()]
            archives = [
                p for p in DOWNLOADS.rglob("*.zip")
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
            root = GAME_ROOT if self.current_system == "NES" else DOWNLOADS
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
        use_fceux = platform.system() == "Darwin" and self.current_system == "NES"
        if use_fceux:
            command = emulator_command(game)
        else:
            core = {"NES": NES_CORE, "GBA": GBA_CORE, "NDS": NDS_CORE}[self.current_system]
            controls = self.ensure_control_config(self.current_system)
            command = [
                RETROARCH,
                "--fullscreen",
                f"--appendconfig={controls}",
                "-L",
                core,
                str(game),
            ]
        if not command:
            self.status.set_text(platform_help())
            return
        self.status.set_text(f"Launching {self.pretty_name(game)}…")
        try:
            process = subprocess.Popen(
                command,
                env=fceux_environment() if use_fceux else None,
            )
            self.game_running = True
        except OSError as error:
            self.window.present()
            self.status.set_text(f"Could not start RetroArch: {error}")
            return
        threading_source = GLib.child_watch_add(process.pid, self.game_finished)
        self._watch = threading_source

    def game_finished(self, _pid, _status):
        self.game_running = False
        page_number, page_games = self.pages[self.current_page]
        if self.current_system == "NES":
            self.status.set_text(
                f"Page {page_number}  •  {len(page_games)} game(s)  •  {len(self.games)} total"
            )
        else:
            self.status.set_text(f"{len(page_games)} {self.current_system} game(s)  •  A–Z")
        self.window.present()

    def on_key(self, _controller, keyval, _keycode, _state):
        if self.stack.get_visible_child_name() == "splash":
            return True
        if (_state & Gdk.ModifierType.CONTROL_MASK) and keyval in (Gdk.KEY_c, Gdk.KEY_C):
            self.quit()
            return True
        if self.capture_action and self.capture_kind == "keyboard":
            if keyval == Gdk.KEY_Escape:
                action = self.capture_action
                self.capture_action = None
                self.capture_kind = None
                self.refresh_mapping_labels()
                self.focus_mapping_button(action)
                return True
            action = self.capture_action
            self.capture_action = None
            self.capture_kind = None
            self.save_key(action, keyval)
            self.refresh_mapping_labels()
            self.focus_mapping_button(action)
            return True
        if self.capture_action and self.capture_kind == "gamepad" and keyval == Gdk.KEY_Escape:
            action = self.capture_action
            self.capture_token += 1
            self.capture_action = None
            self.capture_kind = None
            self.refresh_mapping_labels()
            self.focus_mapping_button(action, "gamepad")
            return True
        if self.stack.get_visible_child_name() == "setup":
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
            if platform.system() == "Darwin":
                self.open_fceux_settings()
            else:
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
