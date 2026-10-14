"""Decoder for Darkest Dungeon's binary save format (DSON).

Format reference: docs/dson.md. Field types are not stored in the file, so they
are inferred from the field name and the size of the field data.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAGIC = b"\x01\xb1\x00\x00"
HEADER_SIZE = 64

# Field types cannot be inferred from the data alone, so the ambiguous ones are
# identified by name.
FLOAT_ARRAY_FIELDS = frozenset({"bounds", "mappos", "sidepos"})
INT_VECTOR_FIELDS = frozenset(
    {
        "additional_mash_disabled_infestation_monster_class_ids",
        "camping_skills",
        "combat_skills",
        "dispatched_events",
        "dungeon_history",
        "dungeons_unlocked",
        "heroes",
        "last_party_guids",
        "narration_audio_event_queue_tags",
        "played_video_list",
        "read_page_indexes",
        "result_event_history",
    }
)
STRING_VECTOR_FIELDS = frozenset({"goal_ids"})
FLOAT_FIELDS = frozenset(
    {
        "chance",
        "chance_of_loot",
        "current_hp",
        "heirloom_gain_multiplier",
        "percent",
        "roster.timestamp",
        "start_elapsed_time",
        "stress",
        "time_stamp",
        "torchlight",
        "totalelapsed",
        "value",
    }
)
TWO_BOOL_FIELDS = frozenset(
    {
        "corpses",
        "curio_tracker",
        "dd_mode",
        "deaths_door_recovery_debuffs",
        "deck_based_stage_coach",
        "multiplied_enemy_crits",
        "provision_warnings",
        "quest_select_warnings",
        "retreats_can_fail",
        "stall_penalty",
    }
)


class DsonError(ValueError):
    """Raised when a buffer is not a valid DSON file."""


def string_hash(value: str) -> int:
    """Hash used by the game for class ids, upgrade trees, etc. (signed 32-bit)."""
    h = 0
    for byte in value.encode("utf-8"):
        h = (h * 53 + byte) & 0xFFFFFFFF
    return h - (1 << 32) if h & 0x80000000 else h


@dataclass(frozen=True)
class _Meta1:
    parent: int
    meta2_index: int
    direct_children: int
    all_children: int


@dataclass(frozen=True)
class _Meta2:
    name_hash: int
    offset: int
    is_object: bool
    name_length: int
    meta1_index: int


def _align4(value: int) -> int:
    return (value + 3) & ~3


def loads(data: bytes) -> dict[str, Any]:
    """Decode DSON bytes into nested dicts. Embedded files are decoded too."""
    if len(data) < HEADER_SIZE or data[:4] != MAGIC:
        raise DsonError("not a DSON file (bad magic number)")

    (
        _revision,
        header_length,
        _zero,
        _meta1_size,
        meta1_count,
        meta1_offset,
        _zero2,
        _zero3,
        meta2_count,
        meta2_offset,
        _zero4,
        data_length,
        data_offset,
    ) = struct.unpack_from("<4xIIIIIIqqIIIII", data, 0)
    if header_length != HEADER_SIZE:
        raise DsonError(f"unexpected header length {header_length}")
    if data_offset + data_length > len(data):
        raise DsonError("file is truncated")

    meta1 = [
        _Meta1(*struct.unpack_from("<iiii", data, meta1_offset + 16 * i))
        for i in range(meta1_count)
    ]
    meta2 = []
    for i in range(meta2_count):
        name_hash, offset, info = struct.unpack_from("<iiI", data, meta2_offset + 12 * i)
        meta2.append(
            _Meta2(
                name_hash=name_hash,
                offset=offset,
                is_object=bool(info & 1),
                name_length=(info & 0b11111111100) >> 2,
                meta1_index=(info & 0b1111111111111111111100000000000) >> 11,
            )
        )
    if not meta1 or not meta2:
        raise DsonError("file contains no objects")

    # A field's size is not stored; it runs up to the next larger offset.
    boundaries = sorted({m.offset for m in meta2} | {data_length})
    next_offset = {a: b for a, b in zip(boundaries, boundaries[1:])}

    def read_name(entry: _Meta2) -> str:
        start = data_offset + entry.offset
        # Some names (e.g. in map files) carry arbitrary bytes as a unique suffix.
        return data[start : start + entry.name_length - 1].decode("latin-1")

    def read_object(index: int) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        info = meta1[index]
        cursor = info.meta2_index + 1
        for _ in range(info.direct_children):
            entry = meta2[cursor]
            name = read_name(entry)
            if entry.is_object:
                obj[name] = read_object(entry.meta1_index)
                cursor += 1 + meta1[entry.meta1_index].all_children
            else:
                start = data_offset + entry.offset + entry.name_length
                end = data_offset + next_offset[entry.offset]
                obj[name] = _decode_value(data, name, start, end)
                cursor += 1
        return obj

    return read_object(0)


def load(path: str | Path) -> dict[str, Any]:
    """Decode a DSON file from disk."""
    return loads(Path(path).read_bytes())


def _decode_value(data: bytes, name: str, start: int, end: int) -> Any:
    if end - start == 1:
        return bool(data[start]) if data[start] in (0, 1) else chr(data[start])

    unaligned_start = start
    start = _align4(start)
    size = end - start
    if size < 0:
        return bytes(data[unaligned_start:end])

    if name in FLOAT_ARRAY_FIELDS:
        return list(struct.unpack_from(f"<{size // 4}f", data, start))
    if name in INT_VECTOR_FIELDS:
        (count,) = struct.unpack_from("<i", data, start)
        return list(struct.unpack_from(f"<{count}i", data, start + 4))
    if name in STRING_VECTOR_FIELDS:
        return _read_string_vector(data, start)
    if name in FLOAT_FIELDS and size == 4:
        return struct.unpack_from("<f", data, start)[0]
    if name in TWO_BOOL_FIELDS and size == 8:
        return [bool(v) for v in struct.unpack_from("<ii", data, start)]

    if size == 4:
        return struct.unpack_from("<i", data, start)[0]

    if size >= 5:
        (length,) = struct.unpack_from("<i", data, start)
        if length == size - 4 and _looks_like_string(data, start + 4, length):
            raw = data[start + 4 : start + 4 + length]
            if raw[:4] == MAGIC:
                return loads(bytes(raw))
            return raw[:-1].decode("utf-8", errors="replace")
        items = _try_string_vector(data, start, end)
        if items is not None:
            return items

    if size == 8:
        return list(struct.unpack_from("<ii", data, start))

    return bytes(data[start:end])


def _looks_like_string(data: bytes, start: int, length: int) -> bool:
    raw = data[start : start + length]
    if raw[:4] == MAGIC:
        return True
    return raw.endswith(b"\x00") and b"\x00" not in raw[:-1]


def _try_string_vector(data: bytes, start: int, end: int) -> list[str] | None:
    """Parse a string vector, or return None if the bytes don't fit exactly."""
    (count,) = struct.unpack_from("<i", data, start)
    if count <= 0:
        return None
    pos = start + 4
    items = []
    for _ in range(count):
        if pos + 4 > end:
            return None
        (length,) = struct.unpack_from("<i", data, pos)
        pos += 4
        if length < 1 or pos + length > end or not _looks_like_string(data, pos, length):
            return None
        items.append(data[pos : pos + length - 1].decode("utf-8", errors="replace"))
        pos += length
    return items if pos == end else None


def _read_string_vector(data: bytes, start: int) -> list[str]:
    (count,) = struct.unpack_from("<i", data, start)
    pos = start + 4
    items = []
    for _ in range(count):
        (length,) = struct.unpack_from("<i", data, pos)
        pos += 4
        items.append(data[pos : pos + length - 1].decode("utf-8", errors="replace"))
        pos += length
    return items
