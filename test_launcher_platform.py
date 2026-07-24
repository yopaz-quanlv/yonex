import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import launcher_platform
from configure_fceux_macos import (
    PROFILE_NAMES,
    RECOMMENDED_PLAYER_KEYS,
    ensure_profiles,
    install_profiles,
    read_player_mapping,
    save_player_mapping,
)


class LauncherPlatformTests(unittest.TestCase):
    def test_game_root_defaults_to_bundled_library(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(launcher_platform.game_root("/app"), Path("/app/games"))

    def test_mac_paths(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            home = Path(directory)
            core = home / "Library/Application Support/RetroArch/cores/nestopia_libretro.dylib"
            core.parent.mkdir(parents=True)
            core.touch()

            self.assertEqual(launcher_platform.libretro_core("Darwin", home), core)
            self.assertEqual(
                launcher_platform.retroarch_config("Darwin", home),
                home / "Library/Application Support/RetroArch/config/retroarch.cfg",
            )

    def test_mac_gba_retroarch_command(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {}, clear=True
        ):
            home = Path(directory)
            executable = home / "Applications/RetroArch.app/Contents/MacOS/RetroArch"
            core = (
                home
                / "Library/Application Support/RetroArch/cores/mgba_libretro.dylib"
            )
            executable.parent.mkdir(parents=True)
            executable.touch()
            core.parent.mkdir(parents=True)
            core.touch()

            self.assertEqual(
                launcher_platform.emulator_command(
                    "game.gba",
                    "Darwin",
                    console="GBA",
                    append_configs=("/tmp/controls.cfg",),
                    home=home,
                ),
                [
                    str(executable),
                    "--fullscreen",
                    "--appendconfig=/tmp/controls.cfg",
                    "-L",
                    str(core),
                    "game.gba",
                ],
            )

    def test_environment_overrides(self):
        values = {
            "NES_GAME_DIR": "~/roms",
            "NES_FCEUX": "~/fceux",
            "NES_RETROARCH": "~/RetroArch",
            "NES_LIBRETRO_CORE": "~/nestopia.dylib",
            "GBA_LIBRETRO_CORE": "~/mgba.dylib",
            "NES_RETROARCH_CONFIG": "~/retroarch.cfg",
        }
        with patch.dict(os.environ, values, clear=True):
            self.assertEqual(launcher_platform.game_root("/app"), Path("~/roms").expanduser())
            self.assertEqual(launcher_platform.fceux_executable(), Path("~/fceux").expanduser())
            self.assertEqual(
                launcher_platform.retroarch_executable(), Path("~/RetroArch").expanduser()
            )
            self.assertEqual(
                launcher_platform.libretro_core(), Path("~/nestopia.dylib").expanduser()
            )
            self.assertEqual(
                launcher_platform.libretro_core(console="GBA"),
                Path("~/mgba.dylib").expanduser(),
            )
            self.assertEqual(
                launcher_platform.retroarch_config(), Path("~/retroarch.cfg").expanduser()
            )

    def test_mac_uses_fceux_without_a_libretro_core(self):
        with patch.dict(os.environ, {"NES_FCEUX": "/opt/homebrew/bin/fceux"}, clear=True):
            self.assertEqual(
                launcher_platform.emulator_command("game.nes", "Darwin"),
                ["/opt/homebrew/bin/fceux", "--fullscreen", "1", "game.nes"],
            )

    def test_fceux_environment_preserves_existing_values(self):
        with patch.dict(os.environ, {"LAUNCHER_TEST": "yes"}, clear=True):
            environment = launcher_platform.fceux_environment()
            self.assertEqual(environment["LAUNCHER_TEST"], "yes")

    def test_installs_two_fceux_keyboard_profiles_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            config = base / "fceux.cfg"
            config.write_text(
                "SDL.Input.GamePad.0.Profile = \n",
                encoding="utf-8",
            )

            profiles, backup = install_profiles(config, base / "input")

            updated = config.read_text(encoding="utf-8")
            self.assertIn("SDL.Input.0 = GamePad.0", updated)
            self.assertIn("SDL.Input.1 = GamePad.1", updated)
            self.assertIn(f"SDL.Input.GamePad.0.Profile = {PROFILE_NAMES[1]}", updated)
            self.assertIn(f"SDL.Input.GamePad.1.Profile = {PROFILE_NAMES[2]}", updated)
            self.assertIn("SDL.Input.GamePad.1.DeviceType = Keyboard", updated)
            self.assertEqual(len(profiles), 2)
            player_one = profiles[0].read_text(encoding="utf-8")
            player_two = profiles[1].read_text(encoding="utf-8")
            self.assertIn("back:kE,start:kR", player_one)
            self.assertIn("dpup:kUp,dpdown:kDown", player_one)
            self.assertIn("back:kY,start:kU", player_two)
            self.assertIn("dpup:kT,dpdown:kG,dpleft:kF,dpright:kH", player_two)
            for mapping in RECOMMENDED_PLAYER_KEYS.values():
                self.assertTrue(set(mapping.values()).isdisjoint({"1", "2", "3", "4"}))
            self.assertTrue(backup.exists())

    def test_updates_and_reads_player_two_fceux_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            config = base / "fceux.cfg"
            mapping = dict(RECOMMENDED_PLAYER_KEYS[2])
            mapping["start"] = "Space"

            save_player_mapping(config, base / "input", 2, mapping)

            self.assertEqual(read_player_mapping(base / "input", 2), mapping)
            updated = config.read_text(encoding="utf-8")
            self.assertIn(f"SDL.Input.GamePad.1.Profile = {PROFILE_NAMES[2]}", updated)

    def test_launch_setup_preserves_custom_fceux_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            mapping = dict(RECOMMENDED_PLAYER_KEYS[1])
            mapping["start"] = "Space"
            save_player_mapping(base / "fceux.cfg", base / "input", 1, mapping)

            ensure_profiles(base / "fceux.cfg", base / "input")

            self.assertEqual(read_player_mapping(base / "input", 1), mapping)
            self.assertTrue(
                (base / "input" / "keyboard" / f"{PROFILE_NAMES[2]}.txt").exists()
            )


if __name__ == "__main__":
    unittest.main()
