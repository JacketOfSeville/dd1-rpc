import unittest

from dd1_rpc.state import Activity, Kind, build_activity, dungeon_display, light_text


def raid(**overrides):
    data = {
        "raid_instance": {
            "id": "generated_3",
            "dungeon": "weald",
            "type": "explore",
            "length": 3,
            "difficulty": 3,
        },
        "torchlight": 74.6,
        "inbattle": False,
    }
    data.update(overrides)
    return data


class HamletTests(unittest.TestCase):
    def test_hamlet_with_week(self):
        game = {"inraid": False, "raiddungeon": "none", "estatename": "Santa Helena"}
        act = build_activity(game, campaign_log={"total_weeks": 34})
        self.assertEqual(act.kind, Kind.HAMLET)
        self.assertEqual(act.details, "In the Hamlet")
        self.assertEqual(act.state, "Santa Helena · Week 34")
        self.assertEqual(act.large_image, "hamlet")

    def test_hamlet_without_optional_data(self):
        act = build_activity({"inraid": False, "raiddungeon": "none"})
        self.assertEqual(act.state, "")

    def test_inraid_flag_without_dungeon_is_hamlet(self):
        self.assertEqual(
            build_activity({"inraid": True, "raiddungeon": "none"}).kind, Kind.HAMLET
        )


class GameModeTests(unittest.TestCase):
    def test_small_image_per_mode(self):
        for mode, image, text in [
            ("base", "mode_darkest", "Darkest"),
            ("radiant", "mode_radiant", "Radiant"),
            ("new_game_plus", "mode_stygian", "Stygian"),
            ("bloodmoon", "mode_bloodmoon", "Bloodmoon"),
        ]:
            act = build_activity({"inraid": False, "game_mode": mode})
            self.assertEqual((act.small_image, act.small_text), (image, text))

    def test_small_image_also_shown_in_raids(self):
        act = build_activity({"inraid": True, "raiddungeon": "weald", "game_mode": "radiant"}, raid())
        self.assertEqual(act.small_image, "mode_radiant")

    def test_unknown_mode_has_no_small_image(self):
        act = build_activity({"inraid": False, "game_mode": "something_new"})
        self.assertEqual((act.small_image, act.small_text), ("", ""))
        self.assertEqual(build_activity({"inraid": False}).small_image, "")


class RaidTests(unittest.TestCase):
    game = {"inraid": True, "raiddungeon": "weald", "estatename": "x"}

    def test_exploring(self):
        act = build_activity(self.game, raid())
        self.assertEqual(act.kind, Kind.RAID)
        self.assertEqual(act.details, "Exploring the Weald")
        self.assertEqual(act.state, "Pushing forward with a dimming light (75%)")
        self.assertEqual(act.large_image, "weald")
        self.assertEqual(act.large_text, "The Weald · Long · Veteran")
        self.assertEqual(act.key, "raid:generated_3")

    def test_in_battle(self):
        act = build_activity(self.game, raid(inbattle=True))
        self.assertEqual(act.details, "Battling in the Weald")
        self.assertEqual(act.state, "Pushing forward with a dimming light (75%)")

    def test_battle_round_and_boss(self):
        def enemy(cls, name):
            return {"data": {"monster_class": cls, "actor": {"name": name}}}

        battle = {"round": 3, "enemies": {"0": enemy("brigand_blood_A", "Bloodletter")}}
        act = build_activity(self.game, raid(inbattle=True, battle=battle))
        self.assertEqual(act.details, "Battling in the Weald (Round 3)")
        battle["enemies"]["1"] = enemy("hag_A", "The Hag")
        act = build_activity(self.game, raid(inbattle=True, battle=battle))
        self.assertEqual(act.details, "Battling The Hag in the Weald (Round 3)")

    def test_torch_tiers(self):
        for torch, expected in [
            (100, "Sweeping with radiant light (100%)"),
            (76, "Sweeping with radiant light (76%)"),
            (75.4, "Pushing forward with a dimming light (75%)"),
            (51, "Pushing forward with a dimming light (51%)"),
            (50, "Paranoid with the settling shadows (50%)"),
            (26, "Paranoid with the settling shadows (26%)"),
            (25, "Venturing into the unknown shadows (25%)"),
            (1, "Venturing into the unknown shadows (1%)"),
            (0, "In pitch darkness... black as Death (0%)"),
        ]:
            act = build_activity(self.game, raid(torchlight=torch))
            self.assertEqual(act.state, expected)

    def test_no_torch_info(self):
        self.assertEqual(light_text(None), "")
        self.assertEqual(light_text({"raid_instance": {}}), "")

    def test_bloodlight_has_no_percentage(self):
        instance = {"id": "cc", "dungeon": "courtyard", "torch_setting": "bloodlight"}
        game = {"inraid": True, "raiddungeon": "courtyard"}
        act = build_activity(game, raid(raid_instance=instance, torchlight=100))
        self.assertEqual(act.state, "The blood taints the purity of light")

    def test_farmstead_lighting(self):
        for setting, expected in [
            ("wave_farm", "Gazing upon the distorted light"),
            ("wave_transition_a", "The distortion gleams a crimson light"),
            ("wave_transition_b", "Blazing light through the Farmstead"),
            ("wave_transition_c", "Haunted by the unknown's light"),
            ("wave_transition_d", "The splendorous light lights the path"),
        ]:
            instance = {"id": "w", "dungeon": "farm", "torch_setting": "wave_farm"}
            data = raid(raid_instance=instance, wave={"torch_settings_id": setting})
            act = build_activity({"inraid": True, "raiddungeon": "farm"}, data)
            self.assertEqual(act.state, expected)

    def test_unknown_torch_setting_falls_back_to_percentage(self):
        instance = {"id": "q", "dungeon": "weald", "torch_setting": "modded_light"}
        act = build_activity(self.game, raid(raid_instance=instance))
        self.assertEqual(act.state, "Pushing forward with a dimming light (75%)")

    def test_length_and_difficulty_names(self):
        for length, difficulty, expected in [
            (1, 1, "The Weald · Short · Apprentice"),
            (2, 5, "The Weald · Medium · Champion"),
            (5, 6, "The Weald · Epic · Darkest"),
            (None, 3, "The Weald · Veteran"),
            (2, 4, "The Weald · Medium"),
        ]:
            instance = {"id": "q", "dungeon": "weald", "length": length, "difficulty": difficulty}
            act = build_activity(self.game, raid(raid_instance=instance))
            self.assertEqual(act.large_text, expected)

    def test_quest_types(self):
        for quest_type, expected in {
            "cleanse": "Cleansing the Weald",
            "kill_boss": "Hunting a boss in the Weald",
            "mystery": "Delving into the Weald",
        }.items():
            instance = {"id": "q", "dungeon": "weald", "type": quest_type}
            act = build_activity(self.game, raid(raid_instance=instance))
            self.assertEqual(act.details, expected)

    def test_raid_file_missing_falls_back_to_game_dungeon(self):
        act = build_activity({"inraid": True, "raiddungeon": "crypts"})
        self.assertEqual(act.details, "Delving into the Ruins")
        self.assertEqual(act.large_image, "ruins")
        self.assertEqual(act.large_text, "The Ruins")
        self.assertEqual(act.state, "")
        self.assertEqual(act.key, "raid:crypts")

    def test_stale_raid_file_from_another_dungeon_is_ignored(self):
        stale = raid(
            raid_instance={"id": "old", "dungeon": "crypts", "type": "explore", "length": 1, "difficulty": 1}
        )
        act = build_activity(self.game, stale)
        self.assertEqual(act.details, "Delving into the Weald")
        self.assertEqual(act.state, "")
        self.assertEqual(act.large_text, "The Weald")

    def test_modded_dungeon(self):
        self.assertEqual(dungeon_display("dark_forest"), ("Dark Forest", "logo"))


class HelperTests(unittest.TestCase):
    def test_activity_is_frozen(self):
        act = Activity(Kind.HAMLET, "k", "d", "s", "i")
        with self.assertRaises(Exception):
            act.details = "x"


if __name__ == "__main__":
    unittest.main()
