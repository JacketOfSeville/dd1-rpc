# dd1-rpc documentation

A standalone companion app that shows Darkest Dungeon (Steam, App ID `262060`) as a Discord Rich Presence activity. It never touches the game: it only reads the save files and watches for the game process. Save format details are in [dson.md](./dson.md).

## Architecture

```
Darkest.exe running? ──► SaveReader ──► build_activity ──► presence_payload ──► pypresence ──► Discord
   (psutil)            (saves.py,      (state.py)          (app.py)
                        dson.py)
```

| Module | Role |
| --- | --- |
| `src/dd1_rpc/dson.py` | Decoder for the game's binary DSON saves (`load`, `loads`, `string_hash`, `DsonError`). |
| `src/dd1_rpc/saves.py` | Finds the save folder and active profile, reads the three save files with a cache (`SaveReader` → `Snapshot`). |
| `src/dd1_rpc/state.py` | Pure mapping from decoded saves to an `Activity` (text, image keys). No I/O. |
| `src/dd1_rpc/app.py` | `PresenceApp`: poll loop, timer handling, rate limiting, reconnects, `status` string. |
| `src/dd1_rpc/__main__.py` | CLI and client ID lookup (`default_client_id`). |
| `src/dd1_rpc/tray.py` | System tray front end used by the `.exe`. |
| `tray_launcher.py`, `build.py` | PyInstaller entry point and the build script that bakes in the client ID. |
| `tests/` | `unittest` suites for the decoder-independent logic (state, saves, app, client ID). |

## Running

- CLI: `python -m dd1_rpc` (flags: `--client-id`, `--save-dir`, `--interval` (default 5 s), `-v`). Run with `$env:PYTHONPATH="src"` unless installed with `pip install -e .`.
- Tray: `python -m dd1_rpc.tray`. Menu: status line, Open save folder, Quit. Logs to `dd1-rpc.log` next to the executable (or the working folder).
- Executable: `python build.py` → `dist\dd1-rpc.exe` (needs `pystray`, `pillow`, `pyinstaller`).

### Client ID resolution

1. `--client-id` (CLI only)
2. `CLIENT_ID` environment variable
3. `CLIENT_ID` in a `.env` file (current folder for the CLI; next to the `.exe` for the tray app)
4. `DD1_RPC_CLIENT_ID` (legacy name, environment or `.env`)
5. Tray app only: the ID baked in at build time by `build.py`

The client ID is the public application ID, not a secret. `.env` and the generated `src/dd1_rpc/_baked.py` are git-ignored. An invalid ID is fatal (`InvalidID`): the CLI exits with 1 and the tray app shows a message box.

## Behaviour

### Poll loop (`PresenceApp.tick`, every 5 s)

1. Look for `darkest.exe` with psutil. If it is gone, the presence is cleared and Discord disconnected; status is "Waiting for Darkest Dungeon".
2. A new game PID resets the session (timer, last payload).
3. Read the saves and call `build_activity`. If the saves are unreadable, a generic "Playing Darkest Dungeon" card with the logo is shown.
4. Send the payload only if it changed **and** at least 15 s passed since the last send (Discord's rate limit).
5. If Discord is not running, connection attempts are retried every 15 s; a failed update drops the connection and reconnects.

### Timer

The elapsed timer restarts whenever `Activity.key` changes (`raid:<raid id>` or `hamlet`). On the first Hamlet visit after attaching, it counts from the game process start time; raids count from when the app first saw them.

### Presence card

| Situation | Details (top line) | State (second line) | Large image / text | Small image |
| --- | --- | --- | --- | --- |
| Hamlet | `In the Hamlet` | `<estate name> · Week N` | `hamlet` / `The Hamlet` | game mode |
| Raid | `<verb> <dungeon>` | torch text | dungeon key / `Location · Length · Difficulty` | game mode |
| Raid, in battle | `Battling in <dungeon> (Round N)` | torch text | as raid | game mode |
| Raid, boss battle | `Battling <Boss> in <dungeon> (Round N)` | torch text | as raid | game mode |
| Saves unreadable | `Playing Darkest Dungeon` | – | `logo` | – |

Fields are clipped to 128 characters (Discord's limit). Empty fields are omitted from the update.

- **Verbs** (`QUEST_VERBS`): explore → Exploring, cleanse → Cleansing, kill_boss → Hunting a boss in, gather → Gathering in, wave → Defending, farm_bloodcrate → Collecting bloodcrates in; anything else → Delving into.
- **Length**: 1/2/3 → Short/Medium/Long; above 3 → Epic (a guess, unconfirmed).
- **Difficulty**: 1/3/5/6 → Apprentice/Veteran/Champion/Darkest.
- **Game mode** (small image, from `persist.game.json` `game_mode`): `base` → Darkest, `radiant` → Radiant, `new_game_plus` → Stygian, `bloodmoon` → Bloodmoon. Only `base` has been verified from real saves.
- **Torch text**: tiers 76-100 "Sweeping with radiant light", 51-75 "Pushing forward with a dimming light", 26-50 "Paranoid with the settling shadows", 1-25 "Venturing into the unknown shadows", 0 "In pitch darkness... black as Death", each followed by `(N%)`. Special lights show fixed text without a percentage: `bloodlight` (Courtyard) and the Farmstead `wave_*` settings (`SPECIAL_LIGHTS`).
- **Boss detection**: a battle enemy whose `monster_class` is in `BOSS_CLASSES` (every monster tagged `boss` in the game's `*.info.darkest` files, including DLC). The name shown is the in-game name stored in the save.

## Save files read

Located in `...\Steam\userdata\<user id>\262060\remote` (auto-detected from the Steam install: the `userdata\*\262060\remote` folder with the most recently modified files; override with `--save-dir`).

| File | Used for |
| --- | --- |
| `profile_N\persist.game.json` | `inraid`, `raiddungeon`, `raid_save`, `estatename`, `game_mode` |
| `profile_N\persist.campaign_log.json` | `total_weeks` (shown as the week) |
| `profile_N\persist.raid.json` (or the subfolder named by `raid_save`, e.g. `plot_crimson_court_1\`) | `raid_instance` (id, dungeon, type, difficulty, length, torch_setting), `torchlight`, `inbattle`, `battle` (round, enemies) |

- The **active profile** is the `profile_*` folder whose `persist.game.json` was written most recently. Profile 9 (Butcher's Circus) is not handled.
- `raid_path` checks the profile root first, then `raid_save`, and rejects `..` path escapes.
- A raid file whose dungeon differs from `raiddungeon` is treated as stale and ignored.
- `SaveReader` caches by mtime and size, and falls back to the last good snapshot if a read hits a half-written file.
- The files are tiny (about 10 ms to parse), so polling is used instead of a filesystem watcher.

## DSON decoder notes

Field types are not stored in the files. `dson.py` infers them from name sets (float, float array, int vector, string vector, two-bool) and size heuristics, tuned against the sample saves. Names are decoded as latin-1. Embedded files (magic `01 B1 00 00`) are decoded recursively. Unknown vectors are tried as string vectors. A negative-size field returns raw bytes. If a new game version adds fields, a wrongly inferred type usually shows up as odd values, not a crash.

## Discord application and art assets

Create an application at the Discord developer portal and upload Rich Presence art (1024×1024 PNG recommended; keys are lowercased; uploads can take minutes to appear):

- Large: `hamlet`, `weald`, `warrens`, `ruins`, `cove`, `courtyard`, `darkest_dungeon`, `farmstead`, `logo`
- Small: `mode_darkest`, `mode_radiant`, `mode_stygian`, `mode_bloodmoon`

## Development

```powershell
$env:PYTHONPATH="src"; python -m unittest discover -s tests          # tests
$env:MYPYPATH="src"; mypy src tests --ignore-missing-imports         # types
```

`state.py` is pure, so most new presence behaviour is a change there plus a test in `tests/test_state.py`. `PresenceApp` takes injectable `rpc_factory`, `find_process` and `clock`, which the app tests use.

## Known limitations and unverified assumptions

- Round number is shown as saved (`battle.round`); whether it is 1-based in every case is unconfirmed.
- Farmstead mid-raid lighting is read from a guessed `torch_settings_id` field; `wave_pre_time_and_space` mapped to the Miasma text is a guess.
- `Epic` length, and the `radiant`, `new_game_plus` and `bloodmoon` folder names, are unverified.
- `gather` and `inventory_activate` quests have no dedicated wording (the latter uses "Delving into").
- Only Windows with the Steam version and a locally running Discord client are supported.
- The unsigned `.exe` may trigger SmartScreen or antivirus warnings.
