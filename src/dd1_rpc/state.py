# Maps decoded Darkest Dungeon saves to a Discord Rich Presence activity.
# Everything here is pure: it takes the decoded save dicts (see ``dson.load``) and
# returns an :class:`Activity`, so it can be tested without the game or Discord.


from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

DISCORD_FIELD_LIMIT = 128

# Dungeon id -> (display name incl. article, Discord art asset key).
DUNGEONS: dict[str, tuple[str, str]] = {
    "weald": ("the Weald", "weald"),
    "warrens": ("the Warrens", "warrens"),
    "crypts": ("the Ruins", "ruins"),
    "cove": ("the Cove", "cove"),
    "courtyard": ("the Courtyard", "courtyard"),
    "darkestdungeon": ("the Darkest Dungeon", "darkest_dungeon"),
    "farm": ("the Farmstead", "farmstead"),
}

# Quest type -> verb phrase placed before the dungeon name.
QUEST_VERBS: dict[str, str] = {
    "explore": "Exploring",
    "cleanse": "Cleansing",
    "kill_boss": "Hunting a boss in",
    "gather": "Gathering in",
    "wave": "Defending",
    "farm_bloodcrate": "Collecting bloodcrates in",
    "inventory_activate": "Activating objects in",
}
DEFAULT_VERB = "Delving into"

# Goal id -> verb phrase, for quest types whose goal says more than the type does.
GOAL_VERBS: dict[str, str] = {
    "gather_grain": "Gathering grain in",
    "gather_holy_relic": "Retrieving a holy relic in",
    "gather_medicines": "Gathering medicines in",
    "gather_shipments": "Gathering shipments in",
    "inventory_activate_beacons": "Lighting the beacons in",
    "inventory_activate_wards": "Activating the wards in",
    "inventory_activate_animalistic_shrine": "Activating the animalistic shrine in",
    "inventory_activate_corrupted_altar": "Activating the corrupted altar in",
    "inventory_activate_infected_corpse": "Investigating the infected corpse in",
}

# Quest length (1-3 in random quests; plot quests can go higher) -> display name.
QUEST_LENGTHS: dict[int, str] = {1: "Short", 2: "Medium", 3: "Long"}
EPIC_LENGTH = "Epic"

# Quest difficulty level -> display name.
QUEST_DIFFICULTIES: dict[int, str] = {1: "Apprentice", 3: "Veteran", 5: "Champion", 6: "Darkest"}

# persist.game ``game_mode`` (the name of the game's mode folder) -> (display name, art asset key).
GAME_MODES: dict[str, tuple[str, str]] = {
    "base": ("Darkest", "mode_darkest"),
    "radiant": ("Radiant", "mode_radiant"),
    "new_game_plus": ("Stygian", "mode_stygian"),
    "bloodmoon": ("Bloodmoon", "mode_bloodmoon"),
}

HAMLET_IMAGE = "hamlet"
FALLBACK_IMAGE = "logo"

# Monster classes tagged "boss" in the game's data files.
BOSS_CLASSES = frozenset(
    """baron_B body_average_A body_average_B body_average_C body_bloated_A body_bloated_B body_bloated_C
    body_emaciated_A body_emaciated_B body_emaciated_C brigand_cannon_A brigand_cannon_B brigand_cannon_C
    brigand_fuseman_A brigand_fuseman_B brigand_fuseman_C brigand_sapper_D bulrush_A bulrush_B bulrush_C
    cattail_A cattail_B cattail_C cauldron_empty_A cauldron_empty_B cauldron_empty_C cauldron_full_A
    cauldron_full_B cauldron_full_C collector_A collector_B collector_C com_bulrush_D com_cattail_D
    com_crocodile_D countess_D countess_E countess_F crocodile_A crocodile_B crocodile_C crow_A crow_B crow_C
    crow_D curtain_A curtain_B curtain_C curtain_E curtain_F curtain_G curtain_H curtain_I curtain_J
    drowned_anchor_A drowned_anchor_B drowned_anchor_C drowned_anchored_A drowned_anchored_B drowned_anchored_C
    drowned_captain_A drowned_captain_B drowned_captain_C fanatic_A fanatic_B fanatic_C formless_guard_A
    formless_guard_B formless_guard_C formless_melee_A formless_melee_B formless_melee_C formless_ranged_A
    formless_ranged_B formless_ranged_C formless_weak_A formless_weak_B formless_weak_C galaxy_D hag_A hag_B
    hag_C miller_A miller_B miller_C necromancer_A necromancer_B necromancer_C nest_A nest_B nest_C
    pew_large_A pew_large_B pew_large_C pew_medium_A pew_medium_B pew_medium_C pew_small_A pew_small_B
    pew_small_C prophet_A prophet_B prophet_C pyre_empty_A pyre_empty_B pyre_empty_C pyre_full_A pyre_full_B
    pyre_full_C shambler_A shambler_B shambler_C shambler_E shambler_tentacle_A shambler_tentacle_B
    shambler_tentacle_C shambler_tentacle_E shuffler_D siren_A siren_B siren_C spire_D statue_hand_A
    statue_hand_B statue_hand_C statue_head_A statue_head_B statue_head_C statue_shield_A statue_shield_B
    statue_shield_C swine_piglet_A swine_piglet_B swine_piglet_C swine_prince_A swine_prince_B swine_prince_C
    thing_A thing_B thing_C viscount_C""".split()
)

# Torchlight tiers as (minimum percent, description), highest first.
TORCH_TIERS: tuple[tuple[int, str], ...] = (
    (76, "Sweeping with radiant light"),
    (51, "Pushing forward with a dimming light"),
    (26, "Paranoid with the settling shadows"),
    (1, "Venturing into the dark"),
    (0, "In pitch darkness... black as Death"),
)

# Raids with a special light source show a fixed description and no percentage.
SPECIAL_LIGHTS: dict[str, str] = {
    "bloodlight": "The blood taints the purity of light",
    "wave_farm": "Gazing upon the distorted light",
    "wave_pre_time_and_space": "Gazing upon the distorted light",
    "wave_transition_a": "The distortion gleams a crimson light",
    "wave_transition_b": "Blazing light through the Farmstead",
    "wave_transition_c": "Haunted by the unknown's light",
    "wave_transition_d": "The splendorous light lights the path",
}


class Kind(Enum):
    GENERIC = "generic"
    HAMLET = "hamlet"
    RAID = "raid"


@dataclass(frozen=True)
class Activity:
    """What to show on Discord. ``key`` changes whenever the timer should restart.

    Empty text and image fields should be omitted from the update.
    """

    kind: Kind
    key: str
    details: str
    state: str
    large_image: str
    large_text: str = ""
    small_image: str = ""
    small_text: str = ""


def generic_activity() -> Activity:
    """Shown while the game runs but its saves can't be read."""
    return Activity(
        kind=Kind.GENERIC,
        key="generic",
        details="Playing Darkest Dungeon",
        state="",
        large_image=FALLBACK_IMAGE,
    )


def build_activity(
    game: Mapping[str, Any],
    raid: Mapping[str, Any] | None = None,
    campaign_log: Mapping[str, Any] | None = None,
) -> Activity:
    """Build the activity for the current save state.

    ``game`` is persist.game; the others are optional and improve the output
    when available. A raid is only reported if persist.game says one is active.
    """
    mode_image, mode_text = game_mode_display(game.get("game_mode"))
    if game.get("inraid") and game.get("raiddungeon", "none") != "none":
        activity = _raid_activity(game, raid)
    else:
        activity = _hamlet_activity(game, campaign_log)
    return replace(activity, small_image=mode_image, small_text=mode_text)


def game_mode_display(game_mode: Any) -> tuple[str, str]:
    """Return (art asset key, display name) of the campaign mode, or empty strings if unknown."""
    name, image = GAME_MODES.get(str(game_mode), ("", ""))
    return image, name


def _hamlet_activity(game: Mapping[str, Any], campaign_log: Mapping[str, Any] | None) -> Activity:
    parts = []
    estate = game.get("estatename")
    if estate:
        parts.append(str(estate))
    weeks = (campaign_log or {}).get("total_weeks")
    if isinstance(weeks, int) and weeks > 0:
        parts.append(f"Week {weeks}")
    return Activity(
        kind=Kind.HAMLET,
        key="hamlet",
        details="In the Hamlet",
        state=_clip(" · ".join(parts)),
        large_image=HAMLET_IMAGE,
        large_text="The Hamlet",
    )


def _raid_activity(game: Mapping[str, Any], raid: Mapping[str, Any] | None) -> Activity:
    instance = (raid or {}).get("raid_instance") or {}
    if instance.get("dungeon") not in (None, game["raiddungeon"]):
        # persist.raid is from a previous raid; the game hasn't rewritten it yet.
        raid, instance = None, {}
    dungeon_id = str(instance.get("dungeon") or game["raiddungeon"])
    quest_type = str(instance.get("type") or "")
    name, image = dungeon_display(dungeon_id)

    parts = []
    light = light_text(raid)
    if light:
        parts.append(light)

    verb = QUEST_VERBS.get(quest_type, DEFAULT_VERB)
    goals = instance.get("goal_ids")
    for goal in goals if isinstance(goals, (list, tuple)) else (goals.values() if isinstance(goals, Mapping) else ()):
        if goal in GOAL_VERBS:
            verb = GOAL_VERBS[goal]
            break
    if (raid or {}).get("inbattle"):
        details = _battle_text(raid or {}, name)
    else:
        details = f"{verb} {name}"
    tooltip = [name[:1].upper() + name[1:]]
    for label in (_length_name(instance.get("length")), QUEST_DIFFICULTIES.get(instance.get("difficulty", 0))):
        if label:
            tooltip.append(label)
    return Activity(
        kind=Kind.RAID,
        key=f"raid:{instance.get('id') or dungeon_id}",
        details=_clip(details),
        state=_clip(" · ".join(parts)),
        large_image=image,
        large_text=_clip(" · ".join(tooltip)),
    )


def _battle_text(raid: Mapping[str, Any], place: str) -> str:
    """``Battling in <place>`` or ``Battling <boss> in <place>``, plus `` (Round N)`` when known."""
    battle = raid.get("battle")
    battle = battle if isinstance(battle, Mapping) else {}
    who = ""
    enemies = battle.get("enemies")
    for enemy in (enemies.values() if isinstance(enemies, Mapping) else ()):
        data = enemy.get("data") if isinstance(enemy, Mapping) else None
        if not isinstance(data, Mapping) or data.get("monster_class") not in BOSS_CLASSES:
            continue
        actor = data.get("actor")
        who = f" {(actor.get('name') if isinstance(actor, Mapping) else None) or data['monster_class']}"
        break
    text = f"Battling{who} in {place}"
    rnd = battle.get("round")
    if isinstance(rnd, int) and not isinstance(rnd, bool):
        text += f" (Round {rnd})"
    return text


def current_torch_setting(raid: Mapping[str, Any] | None) -> str:
    """The id of the active torch setting (e.g. ``bloodlight``), or an empty string for the default.

    The game switches it mid-raid in the Farmstead, so a ``torch_settings_id`` anywhere in the
    raid save wins over the quest's starting ``raid_instance.torch_setting``.
    """
    if not raid:
        return ""
    live = _find_key(raid, "torch_settings_id")
    if isinstance(live, str) and live:
        return live
    setting = (raid.get("raid_instance") or {}).get("torch_setting")
    return setting if isinstance(setting, str) else ""


def _find_key(data: Mapping[str, Any], key: str) -> Any:
    if key in data:
        return data[key]
    for value in data.values():
        if isinstance(value, Mapping):
            found = _find_key(value, key)
            if found is not None:
                return found
    return None


def light_text(raid: Mapping[str, Any] | None) -> str:
    """Describe the party's light, e.g. ``Sweeping with radiant light (82%)``."""
    special = SPECIAL_LIGHTS.get(current_torch_setting(raid))
    if special:
        return special
    torch = (raid or {}).get("torchlight")
    if not isinstance(torch, (int, float)):
        return ""
    percent = max(0, min(100, round(torch)))
    description = next(text for minimum, text in TORCH_TIERS if percent >= minimum)
    return f"{description} ({percent}%)"


def _length_name(length: Any) -> str:
    if not isinstance(length, int):
        return ""
    return QUEST_LENGTHS.get(length) or (EPIC_LENGTH if length > max(QUEST_LENGTHS) else "")


def dungeon_display(dungeon_id: str) -> tuple[str, str]:
    """Return (display name, art asset key); unknown (modded) dungeons are title-cased."""
    if dungeon_id in DUNGEONS:
        return DUNGEONS[dungeon_id]
    if not dungeon_id:
        return "the Unknown", FALLBACK_IMAGE
    return dungeon_id.replace("_", " ").title(), FALLBACK_IMAGE


def _clip(text: str) -> str:
    # Discord rejects activity strings longer than 128 characters. An empty
    # string means "omit this field" (it also rejects strings under 2 characters).
    return text[: DISCORD_FIELD_LIMIT - 1] + "…" if len(text) > DISCORD_FIELD_LIMIT else text
