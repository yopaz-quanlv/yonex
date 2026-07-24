#!/usr/bin/env python3
"""Guided Linux joydev to RetroArch controller mapper."""

import argparse
import glob
import os
import select
import struct
import sys
from pathlib import Path


EVENT_SIZE = 8
BUTTON_EVENT = 0x01
AXIS_EVENT = 0x02
INITIAL_EVENT = 0x80
AXIS_THRESHOLD = 16000

CONTROLS = (
    ("a", "A", "button"),
    ("b", "B", "button"),
    ("x", "X", "button"),
    ("y", "Y", "button"),
    ("l", "LB", "button"),
    ("r", "RB", "button"),
    ("select", "Back / Select", "button"),
    ("start", "Start", "button"),
    ("menu_toggle", "Home / logo", "button"),
    ("turbo", "Fn / Turbo", "button"),
    ("l3", "Press left stick (L3)", "button"),
    ("r3", "Press right stick (R3)", "button"),
    ("up", "D-pad Up", "direction"),
    ("down", "D-pad Down", "direction"),
    ("left", "D-pad Left", "direction"),
    ("right", "D-pad Right", "direction"),
    ("l_x_minus", "Left stick Left", "direction"),
    ("l_x_plus", "Left stick Right", "direction"),
    ("l_y_minus", "Left stick Up", "direction"),
    ("l_y_plus", "Left stick Down", "direction"),
    ("r_x_minus", "Right stick Left", "direction"),
    ("r_x_plus", "Right stick Right", "direction"),
    ("r_y_minus", "Right stick Up", "direction"),
    ("r_y_plus", "Right stick Down", "direction"),
    ("l2", "LT", "axis"),
    ("r2", "RT", "axis"),
)


def device_name(device):
    path = Path("/sys/class/input") / Path(device).name / "device" / "name"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return "Unknown controller"


def device_id(device, field):
    path = Path("/sys/class/input") / Path(device).name / "device" / "id" / field
    try:
        return int(path.read_text(encoding="utf-8").strip(), 16)
    except (OSError, ValueError):
        return 0


def devices():
    return sorted(glob.glob("/dev/input/js*"))


def choose_device(requested):
    found = devices()
    if requested:
        if requested not in found:
            raise SystemExit(f"Controller not found: {requested}")
        return requested
    if not found:
        raise SystemExit("No /dev/input/js* controller found.")
    if len(found) == 1 or not sys.stdin.isatty():
        return found[0]
    print("Detected controllers:")
    for index, device in enumerate(found, 1):
        print(f"  {index}. {device} — {device_name(device)}")
    while True:
        answer = input("Choose controller number: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(found):
            return found[int(answer) - 1]


def read_event(stream):
    while True:
        ready, _, _ = select.select((stream,), (), (), 0.1)
        if not ready:
            continue
        data = stream.read(EVENT_SIZE)
        if len(data) != EVENT_SIZE:
            raise OSError("Controller disconnected")
        _stamp, value, event_type, number = struct.unpack("<IhBB", data)
        if event_type & INITIAL_EVENT:
            continue
        return event_type & ~INITIAL_EVENT, number, value


def neutralize(stream):
    """Discard queued events before asking for the next control."""
    while True:
        ready, _, _ = select.select((stream,), (), (), 0)
        if not ready:
            return
        if len(stream.read(EVENT_SIZE)) != EVENT_SIZE:
            raise OSError("Controller disconnected")


def capture(stream, expected):
    neutralize(stream)
    while True:
        event_type, number, value = read_event(stream)
        if expected == "button" and event_type == BUTTON_EVENT and value:
            return "btn", str(number)
        if expected in ("axis", "direction") and event_type == AXIS_EVENT:
            if abs(value) > AXIS_THRESHOLD:
                direction = "+" if value > 0 else "-"
                return "axis", f"{direction}{number}"


def binding_text(binding):
    kind, value = binding
    return f"Button {value}" if kind == "btn" else f"Axis {value}"


def map_controller(device):
    result = {}
    used = {}
    print(f"\nMapping {device}: {device_name(device)}")
    print("Press Ctrl+C to cancel. Keep sticks and triggers released between steps.\n")
    with open(device, "rb", buffering=0) as stream:
        for index, (action, label, expected) in enumerate(CONTROLS, 1):
            answer = input(
                f"[{index:02}/{len(CONTROLS)}] Enter then activate {label} "
                "(or type s to skip): "
            ).strip().casefold()
            if answer == "s":
                result[action] = None
                print("     Skipped")
                continue
            binding = capture(stream, expected)
            previous = used.get(binding)
            result[action] = binding
            used[binding] = label
            warning = f"  WARNING: also used by {previous}" if previous else ""
            print(f"     {binding_text(binding)}{warning}")
    return result


def render_config(device, mapping):
    lines = [
        f'input_device = "{device_name(device)}"',
        'input_driver = "udev"',
        f'input_vendor_id = "{device_id(device, "vendor")}"',
        f'input_product_id = "{device_id(device, "product")}"',
        "",
    ]
    for action, _label, _expected in CONTROLS:
        binding = mapping[action]
        if binding is None:
            continue
        kind, value = binding
        lines.append(f"input_{action}_{kind} = \"{value}\"")
    return "\n".join(lines) + "\n"


def default_output(device):
    safe_name = "".join(
        character if character.isalnum() or character in " ._-" else "_"
        for character in device_name(device)
    ).strip()
    return (
        Path(__file__).resolve().parent
        / "autoconfig"
        / "udev"
        / f"{safe_name or 'controller'}.cfg"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Test every controller input and generate a RetroArch udev autoconfig."
    )
    parser.add_argument("--device", help="joydev path, for example /dev/input/js1")
    parser.add_argument("--list", action="store_true", help="list detected controllers")
    parser.add_argument("--output", type=Path, help="output .cfg path")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write to this project's autoconfig/udev directory",
    )
    args = parser.parse_args()

    if args.list:
        for device in devices():
            print(
                f"{device}\t{device_name(device)}\t"
                f"{device_id(device, 'vendor'):04x}:{device_id(device, 'product'):04x}"
            )
        return

    device = choose_device(args.device)
    mapping = map_controller(device)
    config = render_config(device, mapping)
    output = args.output
    if args.apply:
        output = default_output(device)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(config, encoding="utf-8")
        print(f"\nSaved RetroArch autoconfig: {output}")
    else:
        print("\nGenerated RetroArch autoconfig:\n")
        print(config, end="")
        print("Run again with --apply to save it into the project.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit("\nCancelled.")
    except OSError as error:
        raise SystemExit(f"\nController error: {error}")
