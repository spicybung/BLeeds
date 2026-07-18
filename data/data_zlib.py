# BLeeds - Scripts for working with R* Leeds (GTA Stories, Chinatown Wars, Manhunt 2, etc) formats in Blender
# Author: spicybung
# Years: 2025 - 2026

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import math
import re
import struct
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple


GAME_DTZ_MAX_DECOMPRESSED_BYTES = 256 * 1024 * 1024
GAME_DTZ_2DFX_ROW_SIZE = 0x40

GAME_DTZ_2DFX_EFFECT_TYPE_NAMES = {
    0: "LIGHT",
    1: "PARTICLE",
    2: "ATTRACTOR",
    3: "PED_BEHAVIOUR",
}


def game_dtz_2dfx_effect_type_name(effect_type: int) -> str:
    return GAME_DTZ_2DFX_EFFECT_TYPE_NAMES.get(int(effect_type), "UNKNOWN")


def _decompress_limited(data: bytes, wbits: int, max_output: int) -> bytes:
    decoder = zlib.decompressobj(wbits)
    output = decoder.decompress(data, max_output + 1)
    if len(output) > max_output or decoder.unconsumed_tail:
        raise ValueError("GAME.DTZ decompressed size exceeds safety limit")
    output += decoder.flush(max_output + 1 - len(output))
    if len(output) > max_output:
        raise ValueError("GAME.DTZ decompressed size exceeds safety limit")
    return output


def decompress_game_dtz(data: bytes, max_output: int = GAME_DTZ_MAX_DECOMPRESSED_BYTES) -> Tuple[bytes, bool]:
    """Return a raw GATG/GTAG resource image and whether zlib was used."""
    raw = bytes(data or b"")
    if raw[:4] in (b"GATG", b"GTAG"):
        return raw, False
    errors = []
    for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS, zlib.MAX_WBITS | 32):
        try:
            decoded = _decompress_limited(raw, wbits, int(max_output))
            if decoded[:4] not in (b"GATG", b"GTAG"):
                raise ValueError("decompressed GAME.DTZ has no GATG/GTAG signature")
            return decoded, True
        except Exception as exc:
            errors.append(str(exc))
    raise ValueError("unable to decompress GAME.DTZ: " + "; ".join(errors[:3]))


def _u32(data: bytes, off: int, default: int = 0) -> int:
    try:
        return struct.unpack_from("<I", data, int(off))[0] if 0 <= int(off) <= len(data) - 4 else default
    except Exception:
        return default


def _i16(data: bytes, off: int, default: int = -1) -> int:
    try:
        return struct.unpack_from("<h", data, int(off))[0] if 0 <= int(off) <= len(data) - 2 else default
    except Exception:
        return default


def _resolve_offset(data: bytes, raw_offset: int, min_size: int = 1) -> int:
    raw_offset = int(raw_offset)
    min_size = max(1, int(min_size))
    return raw_offset if 0 <= raw_offset and raw_offset + min_size <= len(data) else -1


def decode_game_dtz_2dfx_entry(data: bytes, off: int, index: int, table_abs: int) -> Optional[Dict[str, object]]:
    """Decode one exact 64-byte Stories C2dEffect record."""
    try:
        if off < 0 or off + GAME_DTZ_2DFX_ROW_SIZE > len(data):
            return None
        raw = bytes(data[off:off + GAME_DTZ_2DFX_ROW_SIZE])
        x, y, z, pos_w = struct.unpack_from("<4f", raw, 0x00)
        if not all(math.isfinite(float(v)) and abs(float(v)) < 1000000.0 for v in (x, y, z, pos_w)):
            return None
        effect_type = int(raw[0x14])
        if effect_type not in GAME_DTZ_2DFX_EFFECT_TYPE_NAMES:
            return None
        entry: Dict[str, object] = {
            "index": int(index), "global_index": int(index),
            "entry_off": int(off), "table_abs": int(table_abs),
            "x": float(x), "y": float(y), "z": float(z), "position_w": float(pos_w),
            "r": int(raw[0x10]), "g": int(raw[0x11]), "b": int(raw[0x12]), "a": int(raw[0x13]),
            "effect_type": effect_type,
            "effect_type_name": game_dtz_2dfx_effect_type_name(effect_type),
            "raw_hex": raw.hex(), "payload_hex": raw[0x18:].hex(),
        }
        if effect_type == 0:
            distance, outer_range, size, inner_range = struct.unpack_from("<4f", raw, 0x18)
            entry.update({
                "light_distance": float(distance), "light_outer_range": float(outer_range),
                "light_size": float(size), "light_inner_range": float(inner_range),
                "light_flash": int(raw[0x28]), "light_wet": int(raw[0x29]),
                "light_flare": int(raw[0x2A]), "light_shadow_intensity": int(raw[0x2B]),
                "light_flags": int(raw[0x2C]),
                "light_corona_texture_ptr": int(struct.unpack_from("<I", raw, 0x30)[0]),
                "light_shadow_texture_ptr": int(struct.unpack_from("<I", raw, 0x34)[0]),
            })
        elif effect_type == 1:
            dx, dy, dz = struct.unpack_from("<3f", raw, 0x1C)
            entry.update({
                "particle_subtype": int(struct.unpack_from("<i", raw, 0x18)[0]),
                "direction_x": float(dx), "direction_y": float(dy), "direction_z": float(dz),
                "particle_scale": float(struct.unpack_from("<f", raw, 0x28)[0]),
            })
        elif effect_type == 2:
            dx, dy, dz = struct.unpack_from("<3f", raw, 0x18)
            entry.update({
                "attractor_direction_x": float(dx), "attractor_direction_y": float(dy),
                "attractor_direction_z": float(dz), "attractor_subtype": int(raw[0x24]),
                "attractor_probability": int(raw[0x25]),
            })
        else:
            dx, dy, dz = struct.unpack_from("<3f", raw, 0x18)
            rx, ry, rz = struct.unpack_from("<3f", raw, 0x24)
            entry.update({
                "ped_direction_x": float(dx), "ped_direction_y": float(dy), "ped_direction_z": float(dz),
                "ped_rotation_x": float(rx), "ped_rotation_y": float(ry), "ped_rotation_z": float(rz),
                "ped_subtype": int(raw[0x30]),
            })
        return entry
    except Exception:
        return None


def parse_game_dtz_entity_pools(data: bytes, model_effects: Dict[int, List[Dict[str, object]]], ide_count: int):
    pools = (("BUILDING", 0x24), ("TREADABLE", 0x28), ("DUMMY", 0x2C))
    entities, pool_stats = [], {}
    for pool_name, header_off in pools:
        pool_ptr = int(_u32(data, header_off, 0))
        pool_abs = _resolve_offset(data, pool_ptr, 0x20)
        stats = {"pool_pointer": pool_ptr, "size": 0, "allocated": 0, "with_effects": 0, "effect_rows": 0}
        pool_stats[pool_name] = stats
        if pool_abs < 0:
            continue
        try:
            items_ptr, flags_ptr = struct.unpack_from("<II", data, pool_abs)
            size = int(struct.unpack_from("<i", data, pool_abs + 0x08)[0])
        except Exception:
            continue
        stats["size"] = size
        if not 0 <= size <= 200000:
            continue
        items_abs = _resolve_offset(data, int(items_ptr), max(1, size * 0x60))
        flags_abs = _resolve_offset(data, int(flags_ptr), max(1, size))
        if items_abs < 0 or flags_abs < 0:
            continue
        for entity_index in range(size):
            try:
                pool_flag = int(data[flags_abs + entity_index])
                if pool_flag & 0x80:
                    continue
                stats["allocated"] += 1
                entity_off = items_abs + entity_index * 0x60
                model_id = int(struct.unpack_from("<h", data, entity_off + 0x56)[0])
                model_id2 = int(struct.unpack_from("<h", data, entity_off + 0x58)[0])
                entries = model_effects.get(model_id, []) if 0 <= model_id < int(ide_count) else []
                if not entries:
                    continue
                values = struct.unpack_from("<16f", data, entity_off)
                right, up = tuple(map(float, values[0:3])), tuple(map(float, values[4:7]))
                at, position = tuple(map(float, values[8:11])), tuple(map(float, values[12:15]))
                if not all(math.isfinite(v) for v in right + up + at + position):
                    continue
                stats["with_effects"] += 1
                stats["effect_rows"] += len(entries)
                entities.append({
                    "pool_name": pool_name, "pool_index": int(entity_index), "pool_flag": pool_flag,
                    "entity_abs": int(entity_off), "model_id": model_id, "model_id2": model_id2,
                    "level": int(data[entity_off + 0x5A]), "area": int(data[entity_off + 0x5B]),
                    "right": right, "up": up, "at": at, "position": position,
                    "effect_count": len(entries),
                })
            except Exception:
                continue
    return entities, pool_stats


def parse_game_dtz_2dfx_bytes(data: bytes, wanted_model_ids=None) -> Tuple[Dict[int, List[Dict[str, object]]], Dict[str, object]]:
    summary: Dict[str, object] = {
        "status": "unparsed", "ide_count": 0, "effect_count": 0,
        "models_with_effects": 0, "entries_available": 0, "rejected_model_refs": 0,
        "malformed_effect_rows": 0, "effect_type_counts": {0: 0, 1: 0, 2: 0, 3: 0},
        "effects_imported": 0, "instances_with_effects": 0, "model_meta_by_id": {},
    }
    mapping: Dict[int, List[Dict[str, object]]] = {}
    if not data or len(data) < 0x5C:
        summary["status"] = "header_too_small"
        return mapping, summary
    signature = bytes(data[:4])
    if signature not in (b"GATG", b"GTAG"):
        summary.update({"status": "bad_signature", "signature_hex": signature.hex()})
        return mapping, summary

    ide_count, ide_ptr_raw = int(_u32(data, 0x38)), int(_u32(data, 0x3C))
    effect_count, effect_ptr_raw = int(_u32(data, 0x54)), int(_u32(data, 0x58))
    summary.update({
        "signature": signature.decode("ascii", errors="replace"), "ide_count": ide_count,
        "ide_pointer_raw": ide_ptr_raw, "effect_count": effect_count,
        "effect_pointer_raw": effect_ptr_raw,
    })
    if not 0 < ide_count <= 200000:
        summary["status"] = "ide_count_out_of_range"
        return mapping, summary
    if not 0 <= effect_count <= 100000:
        summary["status"] = "effect_count_out_of_range"
        return mapping, summary

    ide_table = _resolve_offset(data, ide_ptr_raw, ide_count * 4)
    effect_table = _resolve_offset(data, effect_ptr_raw, max(1, effect_count * GAME_DTZ_2DFX_ROW_SIZE)) if effect_count else -1
    summary.update({"ide_table_abs": ide_table, "effect_table_abs": effect_table})
    if ide_table < 0 or (effect_count and effect_table < 0):
        summary["status"] = "ide_pointer_out_of_bounds" if ide_table < 0 else "effect_pointer_out_of_bounds"
        return mapping, summary

    effects = [
        decode_game_dtz_2dfx_entry(data, effect_table + i * GAME_DTZ_2DFX_ROW_SIZE, i, effect_table)
        for i in range(effect_count)
    ]
    summary["malformed_effect_rows"] = sum(entry is None for entry in effects)
    for entry in effects:
        if entry is not None:
            effect_type = int(entry["effect_type"])
            summary["effect_type_counts"][effect_type] += 1

    if wanted_model_ids is None:
        model_ids = range(ide_count)
    else:
        model_ids = sorted({int(v) for v in wanted_model_ids if 0 <= int(v) < ide_count})
    rejected, entry_total, model_meta_by_id = 0, 0, {}
    for model_id in model_ids:
        model_ptr_raw = int(_u32(data, ide_table + int(model_id) * 4, 0))
        if not model_ptr_raw:
            continue
        model_info = _resolve_offset(data, model_ptr_raw, 0x20)
        if model_info < 0:
            rejected += 1
            continue
        model_hash = int(_u32(data, model_info + 0x08, 0))
        model_type, num_effects = int(data[model_info + 0x10]), int(data[model_info + 0x11])
        effect_index = int(_i16(data, model_info + 0x18, -1))
        model_meta_by_id[int(model_id)] = {
            "model_id": int(model_id), "model_hash": model_hash,
            "model_hash_hex": "0x{:08X}".format(model_hash),
            "model_pointer_raw": model_ptr_raw, "model_info_abs": model_info,
            "model_type": model_type, "num_effects": num_effects, "effect_index": effect_index,
            "raw_0x20": bytes(data[model_info:model_info + 0x20]).hex(),
        }
        if num_effects <= 0 or effect_index < 0:
            continue
        if effect_index + num_effects > effect_count:
            rejected += 1
            continue
        model_entries = []
        for global_index in range(effect_index, effect_index + num_effects):
            entry = effects[global_index]
            if entry is None:
                continue
            copied = dict(entry)
            copied.update({
                "model_id": int(model_id), "model_hash": model_hash,
                "model_hash_hex": "0x{:08X}".format(model_hash), "model_type": model_type,
                "model_info_abs": model_info, "model_effect_index": global_index - effect_index,
            })
            model_entries.append(copied)
        if model_entries:
            mapping[int(model_id)] = model_entries
            entry_total += len(model_entries)

    summary.update({
        "models_with_effects": len(mapping), "entries_available": entry_total,
        "model_meta_by_id": model_meta_by_id, "rejected_model_refs": rejected,
    })
    entities, pool_stats = parse_game_dtz_entity_pools(data, mapping, ide_count)
    summary.update({
        "effect_entities": entities, "entity_pool_stats": pool_stats,
        "entity_instances_with_effects": len(entities),
        "entity_effect_rows": sum(int(entity.get("effect_count", 0)) for entity in entities),
        "status": "ok",
    })
    return mapping, summary


def _normalized_copy_stem(stem: str) -> str:
    value = str(stem or "").strip()
    value = re.sub(r"\s*\(\d+\)$", "", value)
    value = re.sub(r"\s+-\s+copy(?:\s+\d+)?$", "", value, flags=re.IGNORECASE)
    return value


def find_game_dtz(lvz_path: str, explicit_path: str = "") -> str:
    candidates = []
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())
    parent = Path(lvz_path).expanduser().resolve().parent
    try:
        children = sorted((child for child in parent.iterdir() if child.is_file()), key=lambda child: child.name.lower())
    except Exception:
        children = []
    candidates.extend(child for child in children if child.name.lower() == "game.dtz")
    candidates.extend(
        child for child in children
        if child.suffix.lower() == ".dtz" and _normalized_copy_stem(child.stem).lower() == "game"
    )
    seen = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve()).lower()
            if key not in seen and candidate.is_file():
                return str(candidate)
            seen.add(key)
        except Exception:
            continue
    return ""


def parse_game_dtz_2dfx(lvz_path: str, explicit_path: str = "", wanted_model_ids=None):
    source_path = find_game_dtz(lvz_path, explicit_path)
    if not source_path:
        return {}, {
            "status": "not_found", "source_path": "", "compressed": False,
            "ide_count": 0, "effect_count": 0, "models_with_effects": 0,
            "entries_available": 0, "rejected_model_refs": 0, "malformed_effect_rows": 0,
            "effect_type_counts": {0: 0, 1: 0, 2: 0, 3: 0},
            "effects_imported": 0, "instances_with_effects": 0,
        }
    try:
        raw = Path(source_path).read_bytes()
        data, compressed = decompress_game_dtz(raw)
        mapping, summary = parse_game_dtz_2dfx_bytes(data, wanted_model_ids=wanted_model_ids)
        summary.update({
            "source_path": source_path, "compressed": bool(compressed),
            "input_bytes": len(raw), "decompressed_bytes": len(data),
        })
        return mapping, summary
    except Exception as exc:
        return {}, {
            "status": "read_failed", "source_path": source_path, "error": str(exc),
            "compressed": False, "ide_count": 0, "effect_count": 0,
            "models_with_effects": 0, "entries_available": 0, "rejected_model_refs": 0,
            "malformed_effect_rows": 0, "effect_type_counts": {0: 0, 1: 0, 2: 0, 3: 0},
            "effects_imported": 0, "instances_with_effects": 0,
        }
