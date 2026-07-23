# Yonex NES Game Library

A fullscreen GTK 4 retro game library for Ubuntu. It discovers paged NES games
inside `./games/Page N` plus GBA and Nintendo DS games in `~/Downloads`, displays
bundled gameplay artwork and metadata, and launches games through RetroArch.

## Features

- Home menu for NES, GBA, NDS, and controller settings
- Folder-based NES pages controlled with Left/Right
- Alphabetical GBA/NDS listings with automatic ROM ZIP detection
- Keyboard and gamepad navigation (D-pad/analog, A to select, B to go back)
- Locally captured gameplay artwork with a blurred, darkened game background
- Pressing Start in a game captures that moment as the game's next thumbnail
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
