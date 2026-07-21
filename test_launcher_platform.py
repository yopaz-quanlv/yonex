import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import launcher_platform
from configure_fceux_macos import PROFILE_NAME, install_profile


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

    def test_environment_overrides(self):
        values = {
            "NES_GAME_DIR": "~/roms",
            "NES_FCEUX": "~/fceux",
            "NES_RETROARCH": "~/RetroArch",
            "NES_LIBRETRO_CORE": "~/nestopia.dylib",
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

    def test_installs_fceux_keyboard_profile_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            config = base / "fceux.cfg"
            config.write_text(
                "SDL.Input.GamePad.0.Profile = \nSDL.Hotkeys.ToggleMovieRW = Q\n",
                encoding="utf-8",
            )

            profile, backup = install_profile(config, base / "input")

            updated = config.read_text(encoding="utf-8")
            self.assertIn(f"SDL.Input.GamePad.0.Profile = {PROFILE_NAME}", updated)
            self.assertIn("SDL.Hotkeys.ToggleMovieRW = \n", updated)
            mapping = profile.read_text(encoding="utf-8")
            self.assertIn("a:kA,b:kS,back:kQ,start:kW", mapping)
            self.assertIn("turboA:kZ,turboB:kX", mapping)
            self.assertTrue(backup.exists())


if __name__ == "__main__":
    unittest.main()
