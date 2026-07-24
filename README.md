# Yonex NES Game Library

A fullscreen GTK 4 retro game library for macOS and Linux. It discovers paged
NES games inside `./games/Page N`, GBA games in `./games/GBA`, and Nintendo DS
games in `~/Downloads`. It displays bundled gameplay artwork and metadata, and
launches NES games through FCEUX on macOS or games through RetroArch on Linux.

## Features

- Home menu for NES, GBA, NDS, and controller settings
- Folder-based NES pages controlled with Left/Right
- Alphabetical GBA/NDS listings with automatic ROM ZIP detection
- Keyboard and gamepad navigation (D-pad/analog, A to select, B to go back)
- Locally captured gameplay artwork with a blurred, darkened game background
- If a game has no artwork, its first Start press captures a thumbnail
- Separate NES, GBA, and NDS keyboard/gamepad mapping screens
- Two-player mapped control test and raw physical button/axis test screens
- Configurable Save State and Load State controls (F2/F4 by default)
- Fullscreen RetroArch launching
- Guided raw controller mapping with RetroArch autoconfig output

## Guided controller mapper

List detected controllers:

```bash
python3 controller_mapper.py --list
```

Run the guided test for one controller:

```bash
python3 controller_mapper.py --device /dev/input/js1
```

The mapper asks for every physical button, direction, stick, and trigger in
sequence. By default it only prints the generated RetroArch configuration.
Pass `--apply` to save it under `autoconfig/udev` after reviewing the captured
bindings.

## Controller Home launcher

`controller_launcher_daemon.py` watches MACHENIKE controllers and activates the
fullscreen launcher when raw Button 8 (Home) is pressed. It deliberately ignores
Home while RetroArch is running so the game's own menu hotkey remains available.

The user service template is stored at
`systemd/yones-controller-launcher.service`. Install and enable it with:

```bash
install -Dm644 systemd/yones-controller-launcher.service \
  ~/.config/systemd/user/yones-controller-launcher.service
systemctl --user daemon-reload
systemctl --user enable --now yones-controller-launcher.service
```

Check detection and service logs with:

```bash
python3 controller_launcher_daemon.py --check
systemctl --user status yones-controller-launcher.service
journalctl --user -u yones-controller-launcher.service
```

## macOS

1. Install [Homebrew](https://brew.sh), then install the GTK runtime:

   ```bash
   brew install gtk4 pygobject3 pillow
   ```

2. Install FCEUX:

   ```bash
   brew install fceux
   ```

3. Double-click `run-macos.command` in Finder, or run it from Terminal:

   ```bash
   ./run-macos.command
   ```

The launcher supports both Intel and Apple Silicon Macs and finds FCEUX from
Homebrew automatically. Open **Settings** from the Home menu to configure
separate keyboard controls for NES Player 1 and Player 2. Press F1 to open the
native FCEUX settings.

GBA and NDS games use RetroArch. Install the RetroArch app and download the
mGBA and DeSmuME (or melonDS) cores from its Online Updater before launching
those systems.

The recommended macOS keyboard profiles avoid FCEUX's number-key save slots:

- Player 1: Arrow keys; E Select; R Start; A/S; Z/X turbo
- Player 2: T/F/G/H directions; Y Select; U Start; J/K; N/M turbo

Reinstall both recommended profiles at any time with:

```bash
python3 configure_fceux_macos.py
```

## Linux requirements

- Python 3 with GTK 4 GObject bindings
- RetroArch
- Nestopia, mGBA, and DeSmuME libretro cores

Run the launcher with:

```bash
python3 game_launcher.py
```

## Custom paths

The bundled `games` directory is used by default. These optional environment
variables can override detected paths:

- `NES_GAME_DIR`
- `GBA_GAME_DIR`
- `NES_ART_DIR`
- `NES_FCEUX`
- `NES_RETROARCH`
- `NES_LIBRETRO_CORE`
- `GBA_LIBRETRO_CORE`
- `NDS_LIBRETRO_CORE`
- `NES_RETROARCH_CONFIG`

## Capture missing screenshots

Generate missing screenshots locally by starting each game, waiting five
emulated seconds, and capturing its video output:

```bash
python3 capture_game_screenshots.py
```

Existing screenshots are skipped, so the command is safe to resume. Use
`--system NES` to process only one system, `--wait 8` for games with longer
loading screens, or `--overwrite` to recapture every screenshot. It captures
10 games concurrently by default; use `--jobs 4` to reduce GPU and memory use.
Generated images are stored in `artwork/` so they can be committed with the
library; the launcher uses these bundled images before its download cache.
