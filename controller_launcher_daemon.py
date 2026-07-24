#!/usr/bin/env python3
"""Open the Yonex launcher when a controller Home button is pressed."""

import argparse
import glob
import os
import struct
import subprocess
import sys
import time
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent
LAUNCHER = APP_ROOT / "game_launcher.py"
EVENT_SIZE = 8
BUTTON_EVENT = 0x01
INITIAL_EVENT = 0x80
DEFAULT_HOME_BUTTON = 8
DEFAULT_DEVICE_MATCH = "machenike"
POLL_INTERVAL = 0.05
RECONNECT_INTERVAL = 1.0
DEBOUNCE_SECONDS = 1.0


def log(message):
    print(message, flush=True)


def device_name(device):
    name_path = Path("/sys/class/input") / Path(device).name / "device" / "name"
    try:
        return name_path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def matching_devices(name_match):
    result = []
    for device in sorted(glob.glob("/dev/input/js*")):
        if name_match.casefold() in device_name(device).casefold():
            result.append(device)
    return result


def process_running(executable_name):
    for comm_path in Path("/proc").glob("[0-9]*/comm"):
        try:
            if comm_path.read_text(encoding="utf-8").strip() == executable_name:
                return True
        except OSError:
            continue
    return False


def open_launcher():
    if process_running("retroarch"):
        log("Home ignored: RetroArch is running")
        return
    if not LAUNCHER.exists():
        log(f"Launcher not found: {LAUNCHER}")
        return
    subprocess.Popen(
        [sys.executable, str(LAUNCHER)],
        cwd=APP_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    log("Home pressed: launcher activation requested")


def monitor(home_button, name_match):
    open_devices = {}
    last_scan = 0.0
    last_activation = 0.0
    log(
        f"Watching {name_match!r} controllers for Home button {home_button}; "
        "RetroArch sessions are left undisturbed"
    )
    while True:
        now = time.monotonic()
        if now - last_scan >= RECONNECT_INTERVAL:
            detected = matching_devices(name_match)
            for device in list(open_devices):
                if device not in detected:
                    os.close(open_devices.pop(device))
                    log(f"Disconnected: {device}")
            for device in detected:
                if device in open_devices:
                    continue
                try:
                    open_devices[device] = os.open(
                        device, os.O_RDONLY | os.O_NONBLOCK
                    )
                    log(f"Connected: {device} — {device_name(device)}")
                except OSError as error:
                    log(f"Cannot open {device}: {error}")
            last_scan = now

        for device, descriptor in list(open_devices.items()):
            try:
                while True:
                    data = os.read(descriptor, EVENT_SIZE)
                    if len(data) != EVENT_SIZE:
                        raise OSError("short controller read")
                    _stamp, value, event_type, number = struct.unpack("<IhBB", data)
                    if event_type & INITIAL_EVENT:
                        continue
                    if (
                        event_type == BUTTON_EVENT
                        and number == home_button
                        and value
                        and now - last_activation >= DEBOUNCE_SECONDS
                    ):
                        last_activation = now
                        open_launcher()
            except BlockingIOError:
                pass
            except OSError as error:
                os.close(open_devices.pop(device))
                log(f"Read failed for {device}: {error}")
        time.sleep(POLL_INTERVAL)


def main():
    parser = argparse.ArgumentParser(
        description="Open the Yonex game launcher from a controller Home button."
    )
    parser.add_argument(
        "--home-button",
        type=int,
        default=DEFAULT_HOME_BUTTON,
        help=f"raw joydev Home button number (default: {DEFAULT_HOME_BUTTON})",
    )
    parser.add_argument(
        "--device-match",
        default=DEFAULT_DEVICE_MATCH,
        help=f"case-insensitive device-name filter (default: {DEFAULT_DEVICE_MATCH})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="show matching controllers and exit",
    )
    args = parser.parse_args()
    if args.check:
        found = matching_devices(args.device_match)
        for device in found:
            print(f"{device}\t{device_name(device)}")
        if not found:
            print("No matching controller currently connected.")
        return
    monitor(args.home_button, args.device_match)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(0)
