import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dd1_rpc import dson, saves


def touch(path: Path, mtime_ns: int | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    if mtime_ns is not None:
        os.utime(path, ns=(mtime_ns, mtime_ns))
    return path


class ProfileTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_picks_most_recent_profile_with_a_game_save(self):
        touch(self.root / "profile_0" / saves.GAME_FILE, 1_000_000_000)
        touch(self.root / "profile_1" / saves.GAME_FILE, 2_000_000_000)
        touch(self.root / "profile_9" / "persist.circus_estate.json", 3_000_000_000)
        self.assertEqual(saves.active_profile(self.root).name, "profile_1")

    def test_no_profile(self):
        self.assertIsNone(saves.active_profile(self.root))

    def test_raid_path_prefers_profile_root(self):
        profile = self.root / "profile_0"
        touch(profile / saves.RAID_FILE)
        touch(profile / "plot_x" / saves.RAID_FILE)
        self.assertEqual(saves.raid_path(profile, {"raid_save": "plot_x"}), profile / saves.RAID_FILE)

    def test_raid_path_uses_raid_save_folder(self):
        profile = self.root / "profile_0"
        touch(profile / "plot_x" / saves.RAID_FILE)
        self.assertEqual(
            saves.raid_path(profile, {"raid_save": "plot_x"}), profile / "plot_x" / saves.RAID_FILE
        )

    def test_raid_path_rejects_path_traversal(self):
        profile = self.root / "profile_0"
        touch(self.root / saves.RAID_FILE)
        self.assertIsNone(saves.raid_path(profile, {"raid_save": ".."}))

    def test_raid_path_missing(self):
        self.assertIsNone(saves.raid_path(self.root, {"raid_save": ""}))


class ReaderTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.profile = self.root / "profile_0"
        for name in (saves.GAME_FILE, saves.CAMPAIGN_LOG_FILE, saves.RAID_FILE):
            touch(self.profile / name)
        self.reader = saves.SaveReader(self.root)

    def fake_load(self, game):
        def load(path):
            return {
                saves.GAME_FILE: game,
                saves.CAMPAIGN_LOG_FILE: {"total_weeks": 3},
                saves.RAID_FILE: {"raid_instance": {}},
            }[Path(path).name]

        return mock.patch.object(dson, "load", side_effect=load)

    def test_hamlet_reads_campaign_log_only(self):
        with self.fake_load({"inraid": False, "raiddungeon": "none"}):
            snap = self.reader.read()
        self.assertEqual(snap.campaign_log, {"total_weeks": 3})
        self.assertIsNone(snap.raid)

    def test_raid_reads_raid_only(self):
        with self.fake_load({"inraid": True, "raiddungeon": "weald", "raid_save": ""}):
            snap = self.reader.read()
        self.assertEqual(snap.raid, {"raid_instance": {}})
        self.assertIsNone(snap.campaign_log)

    def test_unchanged_files_are_not_reparsed(self):
        with self.fake_load({"inraid": False, "raiddungeon": "none"}) as load:
            self.reader.read()
            calls = load.call_count
            self.reader.read()
        self.assertEqual(load.call_count, calls)

    def test_partial_write_keeps_last_good_copy(self):
        with self.fake_load({"inraid": False, "raiddungeon": "none"}):
            self.reader.read()
        (self.profile / saves.GAME_FILE).write_bytes(b"xx")  # changes the signature
        with mock.patch.object(dson, "load", side_effect=dson.DsonError("truncated")):
            snap = self.reader.read()
        self.assertEqual(snap.game, {"inraid": False, "raiddungeon": "none"})

    def test_unreadable_game_file_returns_none(self):
        with mock.patch.object(dson, "load", side_effect=dson.DsonError("bad")):
            self.assertIsNone(self.reader.read())


if __name__ == "__main__":
    unittest.main()
