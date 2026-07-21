#!/usr/bin/env python3
import os
import subprocess
import re
import hashlib
import threading
import urllib.parse
import urllib.request
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk


ROM_EXTENSIONS = {".nes"}
PAGE_DIRECTORY = re.compile(r"^Page\s+(\d+)$", re.IGNORECASE)
GAME_ROOT = Path(os.environ.get("NES_GAME_DIR", Path.home() / "yones" / "games"))
RETROARCH = "/usr/bin/retroarch"
LIBRETRO_CORE = "/usr/lib/x86_64-linux-gnu/libretro/nestopia_libretro.so"
RETROARCH_CONFIG = Path.home() / ".config" / "retroarch" / "retroarch.cfg"
ART_CACHE = Path.home() / ".cache" / "nes-game-library"
THUMBNAIL_ROOT = "https://thumbnails.libretro.com/Nintendo%20-%20Nintendo%20Entertainment%20System"
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
    "turboa": "x", "turbob": "y",
}
NES_BUTTONS = (
    ("up", "D-pad Up"), ("down", "D-pad Down"),
    ("left", "D-pad Left"), ("right", "D-pad Right"),
    ("select", "Select"), ("start", "Start"),
    ("a", "A"), ("b", "B"),
    ("turboa", "Turbo A"), ("turbob", "Turbo B"),
)


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
        self.mapping_buttons = {}

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
            .hero { font-size: 42px; font-weight: 900; color: #ffdf5d; }
            .subtitle { font-size: 16px; color: #9da6ba; }
            list { background: transparent; }
            row { border-radius: 14px; margin: 5px 0; padding: 5px; }
            row:selected { background: #5846e8; }
            .game-title { font-size: 25px; font-weight: 700; }
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

        title = Gtk.Label(label="NES GAME LIBRARY", xalign=0)
        title.add_css_class("hero")
        subtitle = Gtk.Label(label=f"Games found in {GAME_ROOT}", xalign=0)
        subtitle.add_css_class("subtitle")
        outer.append(title)
        outer.append(subtitle)

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
            label="↑ ↓ Select    ← → Page    Enter Play    F5 Refresh    Esc Exit", xalign=0
        )
        hint.add_css_class("hint")
        hint.set_hexpand(True)
        self.status = Gtk.Label(xalign=1)
        self.status.add_css_class("status")
        footer.append(hint)
        footer.append(self.status)
        outer.append(footer)
        settings = Gtk.Button(label="Controller Setup  [F1]")
        settings.connect("clicked", lambda _button: self.show_setup())
        footer.append(settings)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(180)
        self.stack.add_named(outer, "games")
        self.stack.add_named(self.build_setup_page(), "setup")
        self.window.set_child(self.stack)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.on_key)
        self.window.add_controller(keys)
        self.refresh()
        self.window.present()

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

        title = Gtk.Label(label="CONTROLLER SETUP", xalign=0)
        title.add_css_class("hero")
        subtitle = Gtk.Label(
            label="Choose an NES button, then press the keyboard key you want to use.", xalign=0
        )
        subtitle.add_css_class("subtitle")
        page.append(title)
        page.append(subtitle)

        grid = Gtk.Grid(column_spacing=18, row_spacing=12)
        grid.set_vexpand(True)
        grid.set_valign(Gtk.Align.CENTER)
        for index, (action, label) in enumerate(NES_BUTTONS):
            name = Gtk.Label(label=label, xalign=0)
            name.add_css_class("game-title")
            button = Gtk.Button()
            button.set_size_request(240, 54)
            button.connect("clicked", self.begin_capture, action)
            self.mapping_buttons[action] = button
            column = (index % 2) * 2
            row = index // 2
            grid.attach(name, column, row, 1, 1)
            grid.attach(button, column + 1, row, 1, 1)
        page.append(grid)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        back = Gtk.Button(label="Back to Games  [Esc]")
        back.connect("clicked", lambda _button: self.show_games())
        reset = Gtk.Button(label="Use Recommended Keys")
        reset.connect("clicked", self.set_recommended_keys)
        controls.append(back)
        controls.append(reset)
        page.append(controls)
        return page

    def show_setup(self):
        self.capture_action = None
        self.refresh_mapping_labels()
        self.stack.set_visible_child_name("setup")

    def show_games(self):
        self.capture_action = None
        self.stack.set_visible_child_name("games")

    def read_mapping(self):
        text = RETROARCH_CONFIG.read_text(encoding="utf-8") if RETROARCH_CONFIG.exists() else ""
        mapping = {}
        for action, retro_action in RETROARCH_ACTIONS.items():
            match = re.search(
                rf'^input_player1_{retro_action}\s*=\s*"([^"]*)"', text, re.MULTILINE
            )
            mapping[action] = match.group(1) if match else ""
        return mapping

    def refresh_mapping_labels(self):
        mapping = self.read_mapping()
        for action, _label in NES_BUTTONS:
            raw = mapping.get(action, "")
            keyval = Gdk.keyval_from_name(self.retro_to_gdk_name(raw)) if raw else 0
            key_name = Gdk.keyval_name(keyval) if keyval else None
            self.mapping_buttons[action].set_label(key_name or "Not set")

    def begin_capture(self, button, action):
        if self.capture_action and self.capture_action in self.mapping_buttons:
            self.refresh_mapping_labels()
        self.capture_action = action
        button.set_label("Press a key…")
        self.window.grab_focus()

    def save_key(self, action, keyval):
        self.write_retroarch_settings({action: self.gdk_to_retro_name(keyval)})

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
        RETROARCH_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        text = RETROARCH_CONFIG.read_text(encoding="utf-8") if RETROARCH_CONFIG.exists() else ""
        for action, value in settings.items():
            retro_action = RETROARCH_ACTIONS[action]
            pattern = rf'^input_player1_{retro_action}\s*=.*$'
            replacement = f'input_player1_{retro_action} = "{value}"'
            if re.search(pattern, text, re.MULTILINE):
                text = re.sub(pattern, replacement, text, count=1, flags=re.MULTILINE)
            else:
                text += f"\n{replacement}\n"
        RETROARCH_CONFIG.write_text(text, encoding="utf-8")

    def set_recommended_keys(self, _button):
        recommended = {
            "up": Gdk.KEY_Up, "down": Gdk.KEY_Down,
            "left": Gdk.KEY_Left, "right": Gdk.KEY_Right,
            "select": Gdk.KEY_1, "start": Gdk.KEY_2,
            "a": Gdk.KEY_a, "b": Gdk.KEY_s,
            "turboa": Gdk.KEY_z, "turbob": Gdk.KEY_x,
        }
        self.write_retroarch_settings(
            {action: self.gdk_to_retro_name(keyval) for action, keyval in recommended.items()}
        )
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
            title.casefold(), ("Unknown", "NES game", "Unknown", "Unknown")
        )
        self.detail_meta.set_text(
            f"Year: {year}\nGenre: {genre}\nPublisher: {publisher}\nPlayers: {players}\n\n{game.name}"
        )
        threading.Thread(target=self.fetch_artwork, args=(game, title), daemon=True).start()

    def fetch_artwork(self, game, title):
        ART_CACHE.mkdir(parents=True, exist_ok=True)
        identity = hashlib.sha1(str(game).encode()).hexdigest()[:12]
        results = {}
        for kind, folder in (("boxart", "Named_Boxarts"), ("screenshot", "Named_Snaps")):
            target = ART_CACHE / f"{identity}-{kind}.png"
            if not target.exists():
                for candidate in (f"{title} (USA)", f"{title} (USA, Europe)", title):
                    filename = urllib.parse.quote(f"{candidate}.png", safe="()',")
                    url = f"{THUMBNAIL_ROOT}/{folder}/{filename}"
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
            path = Gtk.Label(label=str(game.relative_to(GAME_ROOT)), xalign=0)
            path.add_css_class("game-path")
            box.append(name)
            box.append(path)
            row.set_child(box)
            row.game_path = game
            self.listbox.append(row)
        if page_games:
            self.listbox.select_row(self.listbox.get_row_at_index(0))
            self.status.set_text(
                f"Page {page_number}  •  {len(page_games)} game(s)  •  {len(self.games)} total"
            )
        else:
            empty = Gtk.Label(label="No NES games found in Downloads", xalign=0)
            empty.add_css_class("game-title")
            empty.set_margin_top(30)
            self.listbox.append(empty)
            self.status.set_text("0 games")

    def change_page(self, offset):
        if not self.pages:
            return
        new_page = max(0, min(self.current_page + offset, len(self.pages) - 1))
        if new_page != self.current_page:
            self.current_page = new_page
            self.render_page()

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
            process = subprocess.Popen(
                [RETROARCH, "--fullscreen", "-L", LIBRETRO_CORE, str(game)]
            )
        except OSError as error:
            self.window.present()
            self.status.set_text(f"Could not start RetroArch: {error}")
            return
        threading_source = GLib.child_watch_add(process.pid, self.game_finished)
        self._watch = threading_source

    def game_finished(self, _pid, _status):
        page_number, page_games = self.pages[self.current_page]
        self.status.set_text(
            f"Page {page_number}  •  {len(page_games)} game(s)  •  {len(self.games)} total"
        )
        self.window.present()

    def on_key(self, _controller, keyval, _keycode, _state):
        if (_state & Gdk.ModifierType.CONTROL_MASK) and keyval in (Gdk.KEY_c, Gdk.KEY_C):
            self.quit()
            return True
        if self.capture_action:
            if keyval == Gdk.KEY_Escape:
                self.capture_action = None
                self.refresh_mapping_labels()
                return True
            action = self.capture_action
            self.capture_action = None
            self.save_key(action, keyval)
            self.refresh_mapping_labels()
            return True
        if self.stack.get_visible_child_name() == "setup":
            if keyval == Gdk.KEY_Escape:
                self.show_games()
                return True
            return False
        if keyval == Gdk.KEY_Escape:
            self.quit()
            return True
        if keyval == Gdk.KEY_F1:
            self.show_setup()
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
