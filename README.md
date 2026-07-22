# Yonex NES Game Library

A fullscreen GTK 4 retro game library for macOS and Linux. It discovers paged
NES games inside `./games/Page N` plus GBA and Nintendo DS games in
`~/Downloads`, displays cached Libretro artwork and metadata, and launches NES
games through FCEUX on macOS or games through RetroArch on Linux.

## Features

- Home menu for NES, GBA, NDS, and controller settings
- Folder-based NES pages controlled with Left/Right
- Alphabetical GBA/NDS listings with automatic ROM ZIP detection
- Keyboard and gamepad navigation (D-pad/analog, A to select, B to go back)
- Box art and gameplay screenshots from Libretro Thumbnails
- Separate NES, GBA, and NDS keyboard/gamepad mapping screens
- Configurable Save State and Load State controls (F2/F4 by default)
- Fullscreen RetroArch launching

## macOS

1. Install [Homebrew](https://brew.sh), then install the GTK runtime:

   ```bash
   brew install gtk4 pygobject3
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
- `NES_FCEUX`
- `NES_RETROARCH`
- `NES_LIBRETRO_CORE`
- `NES_RETROARCH_CONFIG`
