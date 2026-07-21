# Yonex NES Game Library

A fullscreen GTK 4 NES library for Ubuntu. It discovers `.nes` games inside
`~/Downloads/Page N`, displays cached Libretro artwork and metadata, and launches
games through RetroArch with the Nestopia libretro core.

## Features

- Folder-based pages controlled with Left/Right
- Keyboard game selection with Up/Down and Enter
- Box art and gameplay screenshots from Libretro Thumbnails
- Built-in keyboard mapping screen
- Fullscreen RetroArch launching

## Requirements

- Python 3 with GTK 4 GObject bindings
- RetroArch
- Nestopia libretro core

Run the launcher with:

```bash
python3 game_launcher.py
```
