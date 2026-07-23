#!/usr/bin/env python3
"""Capture missing game artwork by running each ROM in RetroArch."""

import argparse
import concurrent.futures
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from game_launcher import (
    BUNDLED_ART,
    DOWNLOADS,
    GAME_ROOT,
    GBA_CORE,
    NDS_CORE,
    NES_CORE,
    RETROARCH,
    GameLauncher,
)


SYSTEMS = {
    "NES": (".nes", NES_CORE),
    "GBA": (".gba", GBA_CORE),
    "NDS": (".nds", NDS_CORE),
}


def screenshot_path(game):
    identity = hashlib.sha1(str(game).encode()).hexdigest()[:12]
    return BUNDLED_ART / f"{identity}-screenshot.png"


def find_games(system):
    extension, _core = SYSTEMS[system]
    root = GAME_ROOT if system == "NES" else DOWNLOADS
    direct = [path for path in root.rglob(f"*{extension}") if path.is_file()]
    if system == "NES":
        return sorted(direct, key=GameLauncher.game_sort_key)
    archives = [
        path
        for path in root.rglob("*.zip")
        if GameLauncher.is_archive_with_extension(path, extension)
    ]
    return sorted(direct + archives, key=lambda path: path.stem.casefold())


def capture(game, core, seconds):
    target = screenshot_path(game)
    target.parent.mkdir(parents=True, exist_ok=True)
    frames = max(1, round(seconds * 60))

    with tempfile.TemporaryDirectory(prefix="yones-capture-") as temporary:
        temporary_path = Path(temporary)
        raw_screenshot = temporary_path / "screenshot.png"
        config = temporary_path / "capture.cfg"
        config.write_text(
            'audio_enable = "false"\n'
            'video_fullscreen = "false"\n'
            'video_windowed_fullscreen = "false"\n',
            encoding="utf-8",
        )
        command = [
            RETROARCH,
            f"--appendconfig={config}",
            "-L",
            core,
            f"--max-frames={frames}",
            "--max-frames-ss",
            f"--max-frames-ss-path={raw_screenshot}",
            str(game),
        ]
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0 or not raw_screenshot.exists():
            detail = result.stderr.strip().splitlines()
            return False, detail[-1] if detail else f"RetroArch exited with {result.returncode}"
        # /tmp and ~/.cache can be mounted on different filesystems, where
        # Path.replace() raises EXDEV. Copy to the destination filesystem first,
        # then atomically publish the completed image.
        with tempfile.NamedTemporaryFile(
            dir=target.parent,
            prefix=f".{target.stem}-",
            suffix=".tmp",
            delete=False,
        ) as staged:
            staged_path = Path(staged.name)
            with raw_screenshot.open("rb") as source:
                shutil.copyfileobj(source, staged)
        try:
            os.replace(staged_path, target)
        finally:
            staged_path.unlink(missing_ok=True)
    return True, str(target)


def main():
    parser = argparse.ArgumentParser(
        description="Run games briefly and capture screenshots missing from the launcher cache."
    )
    parser.add_argument(
        "--system",
        choices=("NES", "GBA", "NDS", "all"),
        default="all",
        help="system to scan (default: all)",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=5.0,
        metavar="SECONDS",
        help="emulated loading time before capture (default: 5)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace screenshots that already exist",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=10,
        metavar="COUNT",
        help="number of games to capture concurrently (default: 10)",
    )
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be at least 1")

    selected = SYSTEMS if args.system == "all" else (args.system,)
    queue = []
    skipped = 0
    for system in selected:
        _extension, core = SYSTEMS[system]
        for game in find_games(system):
            if screenshot_path(game).exists() and not args.overwrite:
                skipped += 1
            else:
                queue.append((system, game, core))

    print(f"{len(queue)} game(s) to capture; {skipped} existing screenshot(s) skipped.")
    failures = []
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
        pending = {
            executor.submit(capture, game, core, args.wait): (system, game)
            for system, game, core in queue
        }
        for future in concurrent.futures.as_completed(pending):
            system, game = pending[future]
            completed += 1
            try:
                ok, detail = future.result()
            except Exception as error:
                ok, detail = False, str(error)
            status = "captured" if ok else f"failed: {detail}"
            print(
                f"[{completed}/{len(queue)}] {system}: "
                f"{GameLauncher.pretty_name(game)} — {status}",
                flush=True,
            )
            if not ok:
                failures.append((game, detail))

    print(f"Finished: {len(queue) - len(failures)} captured, {len(failures)} failed.")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
