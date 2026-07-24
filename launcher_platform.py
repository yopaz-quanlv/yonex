"""Platform-specific paths used by the NES launcher.

This module deliberately has no GTK dependency so path discovery can be tested on
machines that do not have the graphical runtime installed yet.
"""

import os
import platform
import shutil
from pathlib import Path


def _first_file(candidates):
    return next((path for path in candidates if path.is_file()), None)


def game_root(app_dir):
    override = os.environ.get("NES_GAME_DIR")
    return Path(override).expanduser() if override else Path(app_dir) / "games"


def fceux_executable():
    override = os.environ.get("NES_FCEUX")
    if override:
        return Path(override).expanduser()

    command = shutil.which("fceux")
    if command:
        return Path(command)
    return _first_file((Path("/opt/homebrew/bin/fceux"), Path("/usr/local/bin/fceux")))


def fceux_environment():
    """Return an environment that finds Homebrew's versioned Qt plugins."""
    environment = os.environ.copy()
    for prefix in (Path("/opt/homebrew"), Path("/usr/local")):
        plugins = prefix / "opt/qtbase/share/qt/plugins"
        if plugins.is_dir():
            environment["QT_PLUGIN_PATH"] = str(plugins)
            break
    return environment


def retroarch_executable(system=None, home=None):
    override = os.environ.get("NES_RETROARCH")
    if override:
        return Path(override).expanduser()

    command = shutil.which("retroarch")
    if command:
        return Path(command)

    system = system or platform.system()
    home = Path(home or Path.home())
    if system == "Darwin":
        return _first_file(
            (
                Path("/Applications/RetroArch.app/Contents/MacOS/RetroArch"),
                home / "Applications/RetroArch.app/Contents/MacOS/RetroArch",
            )
        )
    return _first_file((Path("/usr/bin/retroarch"), Path("/usr/local/bin/retroarch")))


def libretro_core(system=None, home=None, console="NES"):
    console = console.upper()
    override = os.environ.get(f"{console}_LIBRETRO_CORE")
    if override:
        return Path(override).expanduser()

    system = system or platform.system()
    home = Path(home or Path.home())
    core_names = {
        "NES": ("nestopia_libretro", "fceumm_libretro"),
        "GBA": ("mgba_libretro",),
        "NDS": ("desmume_libretro", "melonds_libretro"),
    }
    names = core_names.get(console, ())
    if system == "Darwin":
        support = home / "Library/Application Support/RetroArch"
        directories = (
            support / "cores",
            Path("/Applications/RetroArch.app/Contents/Resources/cores"),
            home / "Applications/RetroArch.app/Contents/Resources/cores",
        )
        return _first_file(
            directory / f"{name}.dylib" for directory in directories for name in names
        )

    directories = (
        Path("/usr/lib/x86_64-linux-gnu/libretro"),
        Path("/usr/lib/aarch64-linux-gnu/libretro"),
        Path("/usr/lib/libretro"),
        home / ".config/retroarch/cores",
    )
    return _first_file(
        directory / f"{name}.so" for directory in directories for name in names
    )


def retroarch_config(system=None, home=None):
    override = os.environ.get("NES_RETROARCH_CONFIG")
    if override:
        return Path(override).expanduser()

    system = system or platform.system()
    home = Path(home or Path.home())
    if system == "Darwin":
        return home / "Library/Application Support/RetroArch/config/retroarch.cfg"
    return home / ".config/retroarch/retroarch.cfg"


def platform_help(system=None, console="NES"):
    if (system or platform.system()) == "Darwin" and console.upper() == "NES":
        return "Install FCEUX with: brew install fceux"
    return f"Install RetroArch and a {console.upper()} libretro core"


def emulator_command(game, system=None, console="NES", append_configs=(), home=None):
    system = system or platform.system()
    console = console.upper()
    if system == "Darwin" and console == "NES":
        executable = fceux_executable()
        return [str(executable), "--fullscreen", "1", str(game)] if executable else None

    executable = retroarch_executable(system=system, home=home)
    core = libretro_core(system=system, home=home, console=console)
    if not executable or not core:
        return None
    command = [str(executable), "--fullscreen"]
    if append_configs:
        command.append(f"--appendconfig={'|'.join(map(str, append_configs))}")
    command.extend(("-L", str(core), str(game)))
    return command
