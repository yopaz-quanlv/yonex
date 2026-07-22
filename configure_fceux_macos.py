#!/usr/bin/env python3
"""Install and edit Yonex keyboard profiles for FCEUX on macOS."""

import shutil
from pathlib import Path


PROFILE_NAMES = {
    1: "yonex-mac-keyboard-p1",
    2: "yonex-mac-keyboard-p2",
}
PROFILE_NAME = PROFILE_NAMES[1]
FCEUX_ACTION_FIELDS = (
    ("a", "a"),
    ("b", "b"),
    ("select", "back"),
    ("start", "start"),
    ("up", "dpup"),
    ("down", "dpdown"),
    ("left", "dpleft"),
    ("right", "dpright"),
    ("turboa", "turboA"),
    ("turbob", "turboB"),
)
RECOMMENDED_PLAYER_KEYS = {
    1: {
        "up": "Up", "down": "Down", "left": "Left", "right": "Right",
        "select": "E", "start": "R", "a": "A", "b": "S",
        "turboa": "Z", "turbob": "X",
    },
    2: {
        "up": "T", "down": "G", "left": "F", "right": "H",
        "select": "Y", "start": "U", "a": "J", "b": "K",
        "turboa": "N", "turbob": "M",
    },
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


def player_settings(player):
    index = player - 1
    prefix = f"SDL.Input.GamePad.{index}"
    return {
        f"SDL.Input.{index}": f"GamePad.{index}",
        f"{prefix}.DeviceType": "Keyboard",
        f"{prefix}.DeviceGUID": "keyboard",
        f"{prefix}.Profile": PROFILE_NAMES[player],
    }


def escape_profile_key(key):
    return str(key).replace("\\", "\\\\").replace(",", "\\,")


def build_profile(player, mapping):
    fields = ["keyboard", PROFILE_NAMES[player], "config:0"]
    fields.extend(
        f"{field}:k{escape_profile_key(mapping[action])}"
        for action, field in FCEUX_ACTION_FIELDS
    )
    return ",".join(fields) + ",\n"


def parse_profile(text):
    values = {}
    field_to_action = {field: action for action, field in FCEUX_ACTION_FIELDS}
    lines = text.splitlines()
    line = lines[0] if lines else ""
    token = ""
    tokens = []
    escaped = False
    for character in line:
        if escaped:
            token += character
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == ",":
            tokens.append(token)
            token = ""
        else:
            token += character
    for token in tokens:
        if ":" not in token:
            continue
        field, value = token.split(":", 1)
        action = field_to_action.get(field)
        if action and value.startswith("k"):
            values[action] = value[1:]
    return values


def profile_path(profile_root, player):
    return Path(profile_root) / "keyboard" / f"{PROFILE_NAMES[player]}.txt"


def read_player_mapping(profile_root, player):
    path = profile_path(profile_root, player)
    mapping = dict(RECOMMENDED_PLAYER_KEYS[player])
    if path.exists():
        mapping.update(parse_profile(path.read_text(encoding="utf-8")))
    return mapping


def prepare_config(config_path):
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = config_path.with_suffix(".cfg.before-yonex")
    if config_path.exists() and not backup_path.exists():
        shutil.copy2(config_path, backup_path)
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    return text, backup_path


def save_player_mapping(config_path, profile_root, player, mapping):
    if player not in PROFILE_NAMES:
        raise ValueError(f"Unsupported player: {player}")
    config_path = Path(config_path)
    text, backup_path = prepare_config(config_path)
    for name, value in player_settings(player).items():
        text = update_setting(text, name, value)
    config_path.write_text(text, encoding="utf-8")

    path = profile_path(profile_root, player)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_profile(player, mapping), encoding="utf-8")
    return path, backup_path


def ensure_profiles(config_path, profile_root):
    config_path = Path(config_path)
    text, backup_path = prepare_config(config_path)
    for player in PROFILE_NAMES:
        for name, value in player_settings(player).items():
            text = update_setting(text, name, value)
        path = profile_path(profile_root, player)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                build_profile(player, RECOMMENDED_PLAYER_KEYS[player]), encoding="utf-8"
            )
    config_path.write_text(text, encoding="utf-8")
    return [profile_path(profile_root, player) for player in PROFILE_NAMES], backup_path


def install_profiles(config_path, profile_root):
    config_path = Path(config_path)
    text, backup_path = prepare_config(config_path)
    for player in PROFILE_NAMES:
        for name, value in player_settings(player).items():
            text = update_setting(text, name, value)
        path = profile_path(profile_root, player)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            build_profile(player, RECOMMENDED_PLAYER_KEYS[player]), encoding="utf-8"
        )
    config_path.write_text(text, encoding="utf-8")
    return [profile_path(profile_root, player) for player in PROFILE_NAMES], backup_path


def install_profile(config_path, profile_root):
    """Backward-compatible installer returning the Player 1 profile."""
    profiles, backup_path = install_profiles(config_path, profile_root)
    return profiles[0], backup_path


if __name__ == "__main__":
    base = Path.home() / ".fceux"
    profiles, backup = install_profiles(base / "fceux.cfg", base / "input")
    for profile in profiles:
        print(f"Installed: {profile}")
    print(f"Backup:    {backup}")
