#!/usr/bin/env python3
"""Install the Yonex keyboard profile for FCEUX on macOS."""

import shutil
from pathlib import Path


PROFILE_NAME = "yonex-mac-keyboard"
PROFILE_TEXT = """\
keyboard,yonex-mac-keyboard,config:0,a:kA,b:kS,back:kQ,start:kW,dpup:kUp,dpdown:kDown,dpleft:kLeft,dpright:kRight,turboA:kZ,turboB:kX,
"""
SETTINGS = {
    "SDL.Input.GamePad.0.DeviceType": "Keyboard",
    "SDL.Input.GamePad.0.DeviceGUID": "",
    "SDL.Input.GamePad.0.Profile": PROFILE_NAME,
    # Q is Select in the profile, so it must not also trigger this default hotkey.
    "SDL.Hotkeys.ToggleMovieRW": "",
}


def update_setting(text, name, value):
    replacement = f"{name} = {value}"
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(f"{name} ="):
            lines[index] = replacement
            break
    else:
        lines.append(replacement)
    return "\n".join(lines) + "\n"


def install_profile(config_path, profile_root):
    config_path = Path(config_path)
    profile_root = Path(profile_root)
    if not config_path.exists():
        raise FileNotFoundError("Run FCEUX once before installing its keyboard profile")

    backup_path = config_path.with_suffix(".cfg.before-yonex")
    if not backup_path.exists():
        shutil.copy2(config_path, backup_path)

    text = config_path.read_text(encoding="utf-8")
    for name, value in SETTINGS.items():
        text = update_setting(text, name, value)
    config_path.write_text(text, encoding="utf-8")

    profile_dir = profile_root / "keyboard"
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_path = profile_dir / f"{PROFILE_NAME}.txt"
    profile_path.write_text(PROFILE_TEXT, encoding="utf-8")
    return profile_path, backup_path


if __name__ == "__main__":
    base = Path.home() / ".fceux"
    profile, backup = install_profile(base / "fceux.cfg", base / "input")
    print(f"Installed: {profile}")
    print(f"Backup:    {backup}")
