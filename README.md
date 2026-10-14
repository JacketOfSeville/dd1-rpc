# Darkest Dungeon Discord Rich Presence Companion

A standalone Python app that provides Rich Presence on Discord.
Does so by tracking the player's save state.

## Pre-built usage

A pre-built .exe is avaiable [here for download](https://github.com/JacketOfSeville/dd1-rpc/releases/tag/release) with a pre-baked Discord activity with the needed resources for out-of-the-box usage.

## Compiling and using

1. Create an application at the [Discord Developer Portal](https://discord.com/developers/applications) and copy it's Client ID.
2. Upload Rich Presence art assets (1024×1024 PNG) with these keys:
   - Large image: `hamlet`, `weald`, `warrens`, `ruins`, `cove`, `courtyard`, `darkest_dungeon`, `farmstead`, `logo`
   - Small image (campaign mode): `mode_darkest`, `mode_radiant`, `mode_stygian`, `mode_bloodmoon`
3. Install and run (Discord must be open on the same machine):

   ```powershell
   pip install -e .
   dd1-rpc --client-id <CLIENT_ID>   # or set CLIENT_ID in a .env file
   ```

The Steam save folder (`...\Steam\userdata\<id>\262060\remote`) is auto-detected; override it with `--save-dir`.
The presence appears while `Darkest.exe` is running and is cleared when it closes.

Run the tests with `$env:PYTHONPATH="src"; python -m unittest discover -s tests`.

## Tray app and .exe

`python -m dd1_rpc.tray` runs the app as a system tray icon (menu: status, Open save folder, Quit). It reads `CLIENT_ID` from a `.env` next to the executable and logs to `dd1-rpc.log` there.

Build a single-file executable with your client ID baked in (needs `pip install pystray pillow pyinstaller`):

```
python build.py
```

`build.py` reads `CLIENT_ID` from the environment or `.env`, compiles it into the `.exe` via a temporary git-ignored module, and writes `dist\dd1-rpc.exe`. A `.env` next to the `.exe` (or the `CLIENT_ID` environment variable) still overrides the baked-in value.

## References

- Official Darkest Dungeon modding guide on [Steam](https://steamcommunity.com/sharedfiles/filedetails/?id=819597757)
- `dson.md` documentation about the save structure by **robojumper**. Sourced from [DarkestDungeonSaveEditor](https://github.com/robojumper/DarkestDungeonSaveEditor/blob/master/docs/dson.md?plain=1)