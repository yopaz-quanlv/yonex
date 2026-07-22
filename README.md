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
Homebrew automatically. Press F1 in the launcher to open FCEUX and configure
the keyboard or game controller from its Config menu.

The included macOS keyboard profile uses:

- Arrow keys: D-pad
- Q: Select; W: Start
- A: NES A; S: NES B
- Z: Turbo A; X: Turbo B

Reinstall the recommended profile at any time with:

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
