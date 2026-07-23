# Yonex NES Game Library

A fullscreen GTK 4 retro game library for Ubuntu. It discovers paged NES games
inside `./games/Page N` plus GBA and Nintendo DS games in `~/Downloads`, displays
cached Libretro artwork and metadata, and launches games through RetroArch.

## Features

- Home menu for NES, GBA, NDS, and controller settings
- Folder-based NES pages controlled with Left/Right
- Alphabetical GBA/NDS listings with automatic ROM ZIP detection
- Keyboard and gamepad navigation (D-pad/analog, A to select, B to go back)
- Box art and gameplay screenshots from Libretro Thumbnails
- Separate NES, GBA, and NDS keyboard/gamepad mapping screens
- Two-player mapped control test and raw physical button/axis test screens
- Configurable Save State and Load State controls (F2/F4 by default)
- Fullscreen RetroArch launching

## Requirements

- Python 3 with GTK 4 GObject bindings
- RetroArch
- Nestopia, mGBA, and DeSmuME libretro cores

Run the launcher with:

```bash
python3 game_launcher.py
```
