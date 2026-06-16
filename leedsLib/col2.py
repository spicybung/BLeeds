# BLeeds - Scripts for working with R* Leeds (GTA Stories, Manhunt 2, etc) formats in Blender
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

import struct
from pathlib import Path

#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
#   This script is for .COL2 - the file format for GTA Stories collisions           #
#   NOTE: Leeds Engine Collision 2 differs from Rockstars Renderware Col2 format    #
#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
# - Script resources:
# • https://gtamods.com/wiki/Relocatable_chunk (pre-process)
# •
# - Mod resources/cool stuff:
# •

HEADER_SIZE = 0x20
COLMODEL_HEADER_SIZE = 0x60
COLBOX_SIZE = 0x30
COL2_SIGNATURE = b"2loc"

def align_value(value: int, alignment: int = 0x10) -> int:
    if alignment <= 0:
        return int(value)
    return (int(value) + alignment - 1) & ~(alignment - 1)

def pad_bytes(data: bytearray, alignment: int = 0x10, fill: int = 0) -> None:
    target = align_value(len(data), alignment)
    if target > len(data):
        data.extend(bytes([fill & 0xFF]) * (target - len(data)))

def is_finite_vec(values) -> bool:
    for value in values:
        if value != value:
            return False
        if value in (float("inf"), float("-inf")):
            return False
    return True

def clean_aabb(aabb_min, aabb_max):
    min_x, min_y, min_z = float(aabb_min[0]), float(aabb_min[1]), float(aabb_min[2])
    max_x, max_y, max_z = float(aabb_max[0]), float(aabb_max[1]), float(aabb_max[2])
    return (
        (min(min_x, max_x), min(min_y, max_y), min(min_z, max_z), 0.0),
        (max(min_x, max_x), max(min_y, max_y), max(min_z, max_z), 0.0),
    )

def hex32(value: int) -> str:
    return f"0x{value:08X}"

def read_exact(file, size: int) -> bytes:
    data = file.read(size)
    if len(data) != size:
        raise EOFError(f"Tried to read {size} bytes, got {len(data)} bytes")
    return data

def read_u32(file) -> int:
    return struct.unpack("<I", read_exact(file, 4))[0]

def hexdump_block(data: bytes, base_off: int = 0, width: int = 16) -> str:
    lines = []
    for i in range(0, len(data), width):
        chunk = data[i : i + width]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        asc_part = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        lines.append(f"{base_off + i:08X}  {hex_part:<{width * 3}}  {asc_part}")
    return "\n".join(lines)

def ascii_preview(sig_bytes: bytes) -> str:
    out = []
    for b in sig_bytes:
        out.append(chr(b) if 32 <= b <= 126 else ".")
    return "".join(out)

def parse_col2_header(file, path: str):
    file.seek(0)
    header_bytes = read_exact(file, HEADER_SIZE)

    sig_bytes, unk04, file_size, mirror1, mirror2, entry_hint, unk18, unk1C = struct.unpack(
        "<4sIIIIIII", header_bytes
    )

    sig_ascii = ascii_preview(sig_bytes)

    if file_size == 0:
        file_size = Path(path).stat().st_size

    if 0 < mirror1 <= file_size:
        data_end = mirror1
    else:
        data_end = file_size

    report_lines = []
    report_lines.append("=== COL2 Header ===")
    report_lines.append(f"Signature        : {sig_bytes!r} ({sig_ascii})")
    report_lines.append(f"Unknown @0x04    : {unk04} ({hex32(unk04)})")
    report_lines.append(f"File size        : {file_size} ({hex32(file_size)})")
    report_lines.append(f"Mirror dir off 1 : {mirror1} ({hex32(mirror1)})")
    report_lines.append(f"Mirror dir off 2 : {mirror2} ({hex32(mirror2)})")
    report_lines.append(f"Entry hint @0x14 : {entry_hint} (dec)")
    report_lines.append(f"Reserved @0x18   : {unk18} ({hex32(unk18)})")
    report_lines.append(f"Reserved @0x1C   : {unk1C} ({hex32(unk1C)})")
    report_lines.append(f"Resource table   : starts at {hex32(HEADER_SIZE)}")
    report_lines.append(
        f"Collision data   : assumed within [0x{HEADER_SIZE:04X}, {hex32(data_end)})"
    )

    return {
        "raw": header_bytes,
        "sig": sig_bytes,
        "sig_ascii": sig_ascii,
        "file_size": file_size,
        "mirror_dir_off": mirror1,
        "mirror_dir_off2": mirror2,
        "entry_hint": entry_hint,
        "data_end": data_end,
        "report": "\n".join(report_lines),
    }

def scan_primary_resource_table(file, header, log):
    file_size = header["file_size"]
    entry_hint = header["entry_hint"]

    start_off = HEADER_SIZE
    file.seek(start_off)

    entries = []
    lines = []
    index = 0

    lines.append("=== Primary resource table ===")
    lines.append(f"Start offset     : {hex32(start_off)}")
    lines.append(f"Entry hint       : {entry_hint} (dec)")
    lines.append("Format           : u32 resourceId, u32 resourceOffset")
    lines.append("Stop condition   : (id==0xFFFFFFFF && off==0) OR (id==0 && off==0) OR EOF")

    while True:
        position = file.tell()
        if position + 8 > file_size:
            lines.append(f"Reached file end at {hex32(position)}; stop.")
            break

        raw = file.read(8)
        if len(raw) < 8:
            lines.append("Short read; stop.")
            break

        resource_id, resource_offset = struct.unpack("<II", raw)

        if resource_id == 0xFFFFFFFF and resource_offset == 0:
            lines.append(f"[{index:04d}] sentinel (FFFFFFFF,0) at {hex32(position)}; table end.")
            break

        if resource_id == 0 and resource_offset == 0:
            lines.append(f"[{index:04d}] sentinel (0,0) at {hex32(position)}; table end.")
            break

        offset_note = ""
        if resource_offset >= file_size:
            offset_note = "  [warn: offset >= file size]"

        lines.append(
            f"[{index:04d}] id={hex32(resource_id)} off={hex32(resource_offset)}{offset_note}"
        )
        entries.append((resource_id, resource_offset))
        index += 1

        if entry_hint and index > entry_hint + 64:
            log(f"[WARN] Resource table has more than hint ({entry_hint}) + 64 entries; odd.")
            break

    return entries, "\n".join(lines)

def read_colmodel_header(file, base_offset: int, data_end: int):
    if base_offset < HEADER_SIZE or base_offset + 0x60 > data_end:
        return None

    file.seek(base_offset)
    data = read_exact(file, 0x60)

    center_x, center_y, center_z, radius = struct.unpack_from("<4f", data, 0x00)

    if not (0.0 <= abs(radius) <= 100000.0):
        return None

    min_x, min_y, min_z, min_w = struct.unpack_from("<4f", data, 0x10)
    max_x, max_y, max_z, max_w = struct.unpack_from("<4f", data, 0x20)
    if not (min_x <= max_x and min_y <= max_y and min_z <= max_z):
        return None

    num_spheres, num_boxes, num_tris = struct.unpack_from("<hhh", data, 0x30)
    num_lines = data[0x36]
    num_tri_sections = data[0x37]
    col_store_id = data[0x38]
    field_39 = data[0x39]
    field_3A = data[0x3A]
    field_3B = data[0x3B]

    for val in (num_spheres, num_boxes, num_tris):
        if val < 0 or val > 20000:
            return None

    spheres_off = struct.unpack_from("<I", data, 0x3C)[0]
    lines_off = struct.unpack_from("<I", data, 0x40)[0]
    boxes_off = struct.unpack_from("<I", data, 0x44)[0]
    tri_sec_off = struct.unpack_from("<I", data, 0x48)[0]
    verts_off = struct.unpack_from("<I", data, 0x4C)[0]
    tris_off = struct.unpack_from("<I", data, 0x50)[0]
    unk0 = struct.unpack_from("<I", data, 0x54)[0]
    pad0_0 = struct.unpack_from("<I", data, 0x58)[0]
    pad0_1 = struct.unpack_from("<I", data, 0x5C)[0]

    def in_data(off: int) -> bool:
        return HEADER_SIZE <= off < data_end

    if num_tris > 0:
        if not (in_data(verts_off) and in_data(tris_off)):
            return None

    if num_boxes > 0 and boxes_off != 0 and not in_data(boxes_off):
        return None
    if num_spheres > 0 and spheres_off != 0 and not in_data(spheres_off):
        return None

    return {
        "base_off": base_offset,
        "center": (center_x, center_y, center_z),
        "radius": radius,
        "aabb_min": (min_x, min_y, min_z, min_w),
        "aabb_max": (max_x, max_y, max_z, max_w),
        "numSpheres": num_spheres,
        "numBoxes": num_boxes,
        "numTris": num_tris,
        "numLines": num_lines,
        "numTriSections": num_tri_sections,
        "colStoreId": col_store_id,
        "field_39": field_39,
        "field_3A": field_3A,
        "field_3B": field_3B,
        "spheres_off": spheres_off,
        "lines_off": lines_off,
        "boxes_off": boxes_off,
        "triSec_off": tri_sec_off,
        "verts_off": verts_off,
        "tris_off": tris_off,
        "unk0": unk0,
        "pad0_0": pad0_0,
        "pad0_1": pad0_1,
    }

def decompress_compressed_vector(x_int: int, y_int: int, z_int: int):
    return (x_int / 128.0, y_int / 128.0, z_int / 128.0)

def read_colmodel_triangles(file, tris_off: int, num_tris: int, data_end: int, log):
    if num_tris <= 0:
        return [], -1

    if tris_off >= data_end:
        log(f"[WARN] Triangle pointer {hex32(tris_off)} outside data_end {hex32(data_end)}.")
        return [], -1

    file.seek(tris_off)
    max_possible = (data_end - tris_off) // 8
    count = min(num_tris, max_possible)
    if count <= 0:
        log(
            f"[WARN] Triangle list @ {hex32(tris_off)} has zero usable entries "
            f"(max_possible={max_possible})."
        )
        return [], -1

    raw = read_exact(file, count * 8)
    tris = []
    max_index = 0

    for index in range(count):
        a_raw, b_raw, c_raw, surf, pad = struct.unpack_from("<hhhBB", raw, index * 8)

        if a_raw < 0 or b_raw < 0 or c_raw < 0:
            continue

        a = a_raw // 6
        b = b_raw // 6
        c = c_raw // 6

        if (a_raw % 6) or (b_raw % 6) or (c_raw % 6):
            log(
                f"[WARN] Triangle #{index} at {hex32(tris_off + index*8)} "
                f"has non-multiple-of-6 offsets: a={a_raw}, b={b_raw}, c={c_raw}"
            )

        max_index = max(max_index, a, b, c)
        tris.append((a, b, c))

    if not tris:
        log(f"[WARN] No valid triangles decoded from {hex32(tris_off)}.")
        return [], -1

    return tris, max_index

def read_colmodel_vertices(file, verts_off: int, required_vertices: int, data_end: int, log):
    if required_vertices <= 0:
        log(f"[WARN] Requested 0 vertices at {hex32(verts_off)}.")
        return []

    if verts_off >= data_end:
        log(f"[WARN] Vertex pointer {hex32(verts_off)} outside data_end {hex32(data_end)}.")
        return []

    max_possible = (data_end - verts_off) // 6
    if max_possible <= 0:
        log(f"[WARN] Vertex buffer @ {hex32(verts_off)} has no room inside {hex32(data_end)}.")
        return []

    count = min(required_vertices, max_possible)

    file.seek(verts_off)
    raw = read_exact(file, count * 6)
    verts = []

    for index in range(count):
        xi, yi, zi = struct.unpack_from("<hhh", raw, index * 6)
        verts.append(decompress_compressed_vector(xi, yi, zi))

    if count < required_vertices:
        log(
            f"[WARN] Vertex buffer @ {hex32(verts_off)} ran out of room: "
            f"needed {required_vertices}, used {count}."
        )

    return verts

def read_colmodel_boxes(file, boxes_off: int, num_boxes: int, data_end: int, log):
    if num_boxes <= 0 or boxes_off == 0:
        return []
    if boxes_off < HEADER_SIZE or boxes_off >= data_end:
        log(f"[WARN] CBox pointer {hex32(boxes_off)} outside data range ending {hex32(data_end)}.")
        return []

    max_possible = max(0, (data_end - boxes_off) // COLBOX_SIZE)
    count = min(int(num_boxes), max_possible)
    if count <= 0:
        return []

    boxes = []
    file.seek(boxes_off)

    for index in range(count):
        off = boxes_off + index * COLBOX_SIZE
        raw = file.read(COLBOX_SIZE)
        if len(raw) != COLBOX_SIZE:
            break

        min_x, min_y, min_z, min_w = struct.unpack_from("<4f", raw, 0x00)
        max_x, max_y, max_z, max_w = struct.unpack_from("<4f", raw, 0x10)
        values = (min_x, min_y, min_z, min_w, max_x, max_y, max_z, max_w)

        if not is_finite_vec(values):
            log(f"[WARN] CBox #{index} at {hex32(off)} stopped: non-finite values.")
            break
        if min_x > max_x or min_y > max_y or min_z > max_z:
            log(f"[WARN] CBox #{index} at {hex32(off)} stopped: min > max, likely next structure.")
            break
        if max(abs(v) for v in values[:3] + values[4:7]) > 1000000.0:
            log(f"[WARN] CBox #{index} at {hex32(off)} stopped: unreasonable coordinate size.")
            break

        boxes.append({
            "index": index,
            "offset": off,
            "aabb_min": (min_x, min_y, min_z, min_w),
            "aabb_max": (max_x, max_y, max_z, max_w),
            "trailer": raw[0x20:0x30],
            "raw": raw,
        })

    if len(boxes) != int(num_boxes):
        log(
            f"[INFO] CBox table @ {hex32(boxes_off)} requested {num_boxes} entries, "
            f"read {len(boxes)} sane 0x30-byte AABB records."
        )
    return boxes

def compute_aabb_from_points(points):
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    zs = [float(p[2]) for p in points]
    if not xs:
        return ((0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0))
    return ((min(xs), min(ys), min(zs), 0.0), (max(xs), max(ys), max(zs), 0.0))

def compute_sphere_from_aabb(aabb_min, aabb_max):
    min_x, min_y, min_z, _ = aabb_min
    max_x, max_y, max_z, _ = aabb_max
    cx = (float(min_x) + float(max_x)) * 0.5
    cy = (float(min_y) + float(max_y)) * 0.5
    cz = (float(min_z) + float(max_z)) * 0.5
    dx = float(max_x) - cx
    dy = float(max_y) - cy
    dz = float(max_z) - cz
    radius = (dx * dx + dy * dy + dz * dz) ** 0.5
    return (cx, cy, cz, radius)

def encode_compressed_vector(value):
    x, y, z = value
    def clamp_i16(v):
        iv = int(round(float(v) * 128.0))
        return max(-32768, min(32767, iv))
    return clamp_i16(x), clamp_i16(y), clamp_i16(z)

def pack_colbox(aabb_min, aabb_max, trailer: bytes = None) -> bytes:
    aabb_min, aabb_max = clean_aabb(aabb_min, aabb_max)
    if trailer is None:
        trailer = b"\x00" * 16
    trailer = bytes(trailer[:16]).ljust(16, b"\x00")
    return struct.pack("<4f4f", *aabb_min, *aabb_max) + trailer

def triangulate_face_indices(indices):
    indices = list(indices)
    if len(indices) < 3:
        return []
    if len(indices) == 3:
        return [tuple(indices)]
    triangles = []
    anchor = indices[0]
    for i in range(1, len(indices) - 1):
        triangles.append((anchor, indices[i], indices[i + 1]))
    return triangles

def write_col2_archive(path: str, models, pad_to_sector: bool = True) -> dict:
    if not models:
        raise ValueError("No COL2 models were supplied for export.")

    clean_models = []
    next_resource_id = 0x1000
    for model in models:
        resource_id = int(model.get("resource_id", 0) or 0)
        if resource_id <= 0 or resource_id == 0xFFFFFFFF:
            resource_id = next_resource_id
            next_resource_id += 1

        vertices = [tuple(float(c) for c in v[:3]) for v in model.get("vertices", [])]
        faces = []
        for face in model.get("faces", []):
            faces.extend(triangulate_face_indices(face))

        boxes = []
        for box in model.get("boxes", []):
            mn = box.get("aabb_min", (0.0, 0.0, 0.0, 0.0))
            mx = box.get("aabb_max", (0.0, 0.0, 0.0, 0.0))
            trailer = box.get("trailer", None)
            mn, mx = clean_aabb(mn, mx)
            boxes.append({"aabb_min": mn, "aabb_max": mx, "trailer": trailer})

        if vertices:
            aabb_min, aabb_max = compute_aabb_from_points(vertices)
        elif boxes:
            corners = []
            for box in boxes:
                mn = box["aabb_min"]
                mx = box["aabb_max"]
                corners.append((mn[0], mn[1], mn[2]))
                corners.append((mx[0], mx[1], mx[2]))
            aabb_min, aabb_max = compute_aabb_from_points(corners)
        else:
            aabb_min, aabb_max = clean_aabb(
                model.get("aabb_min", (0.0, 0.0, 0.0, 0.0)),
                model.get("aabb_max", (0.0, 0.0, 0.0, 0.0)),
            )
            boxes.append({"aabb_min": aabb_min, "aabb_max": aabb_max, "trailer": None})

        clean_models.append({
            "resource_id": resource_id,
            "name": str(model.get("name", f"col_{resource_id:04X}")),
            "vertices": vertices,
            "faces": faces,
            "boxes": boxes,
            "aabb_min": aabb_min,
            "aabb_max": aabb_max,
        })

    data = bytearray(b"\x00" * HEADER_SIZE)
    relocation_offsets = []

    resource_table_start = len(data)
    for _model in clean_models:
        data.extend(b"\x00" * 8)
    data.extend(struct.pack("<II", 0xFFFFFFFF, 0))
    pad_bytes(data, 0x10)

    model_records = []

    for model in clean_models:
        pad_bytes(data, 0x10)
        header_off = len(data)
        data.extend(b"\x00" * COLMODEL_HEADER_SIZE)

        boxes_off = 0
        if model["boxes"]:
            pad_bytes(data, 0x10)
            boxes_off = len(data)
            for box in model["boxes"]:
                data.extend(pack_colbox(box["aabb_min"], box["aabb_max"], box.get("trailer")))

        verts_off = 0
        if model["vertices"]:
            pad_bytes(data, 0x02)
            verts_off = len(data)
            for vertex in model["vertices"]:
                data.extend(struct.pack("<hhh", *encode_compressed_vector(vertex)))

        tris_off = 0
        if model["faces"]:
            pad_bytes(data, 0x02)
            tris_off = len(data)
            for a, b, c in model["faces"]:
                for index in (a, b, c):
                    if int(index) < 0 or int(index) >= len(model["vertices"]):
                        raise ValueError(
                            f"Model {model['name']} has triangle index {index} outside "
                            f"0..{len(model['vertices']) - 1}."
                        )
                a_raw = int(a) * 6
                b_raw = int(b) * 6
                c_raw = int(c) * 6
                if max(a_raw, b_raw, c_raw) > 32767:
                    raise ValueError(
                        f"Model {model['name']} has too many vertices for COL2 int16 triangle offsets."
                    )
                data.extend(struct.pack("<hhhBB", a_raw, b_raw, c_raw, 0, 0))

        model_records.append({
            "resource_id": model["resource_id"],
            "header_off": header_off,
            "boxes_off": boxes_off,
            "verts_off": verts_off,
            "tris_off": tris_off,
            "model": model,
        })

    for record in model_records:
        model = record["model"]
        header_off = record["header_off"]
        aabb_min, aabb_max = clean_aabb(model["aabb_min"], model["aabb_max"])
        sphere = compute_sphere_from_aabb(aabb_min, aabb_max)

        struct.pack_into("<4f", data, header_off + 0x00, *sphere)
        struct.pack_into("<4f", data, header_off + 0x10, *aabb_min)
        struct.pack_into("<4f", data, header_off + 0x20, *aabb_max)
        struct.pack_into(
            "<hhhBBBB",
            data,
            header_off + 0x30,
            0,
            len(model["boxes"]),
            len(model["faces"]),
            0,
            0,
            4,
            0,
        )
        struct.pack_into("<I", data, header_off + 0x3C, 0)
        struct.pack_into("<I", data, header_off + 0x40, 0)
        struct.pack_into("<I", data, header_off + 0x44, record["boxes_off"])
        struct.pack_into("<I", data, header_off + 0x48, 0)
        struct.pack_into("<I", data, header_off + 0x4C, record["verts_off"])
        struct.pack_into("<I", data, header_off + 0x50, record["tris_off"])
        struct.pack_into("<I", data, header_off + 0x54, 0)
        struct.pack_into("<I", data, header_off + 0x58, 0)
        struct.pack_into("<I", data, header_off + 0x5C, 0)

        for ptr_field in (0x44, 0x4C, 0x50):
            if struct.unpack_from("<I", data, header_off + ptr_field)[0] != 0:
                relocation_offsets.append(header_off + ptr_field)

    for index, record in enumerate(model_records):
        entry_off = resource_table_start + index * 8
        struct.pack_into("<II", data, entry_off, record["resource_id"], record["header_off"])
        relocation_offsets.append(entry_off + 4)

    pad_bytes(data, 0x04)
    reloc_off = len(data)
    relocation_offsets = sorted(set(relocation_offsets))
    for off in relocation_offsets:
        data.extend(struct.pack("<I", off))

    logical_size = len(data)
    struct.pack_into(
        "<4sIIIIIII",
        data,
        0,
        COL2_SIGNATURE,
        0,
        logical_size,
        reloc_off,
        reloc_off,
        len(relocation_offsets),
        0,
        0,
    )

    if pad_to_sector:
        pad_bytes(data, 0x800)

    Path(path).write_bytes(bytes(data))
    return {
        "path": str(path),
        "model_count": len(clean_models),
        "logical_size": logical_size,
        "physical_size": len(data),
        "reloc_off": reloc_off,
        "reloc_count": len(relocation_offsets),
        "resource_ids": [m["resource_id"] for m in clean_models],
    }

def find_colmodels_from_entries(file, header, entries, report_lines, log):
    data_end = header["data_end"]
    colmodels = {}

    report_lines.append("=== CColModel discovery (single-level table) ===")
    report_lines.append(f"Data end        : {hex32(data_end)}")
    report_lines.append(f"Resource entries: {len(entries)}")

    for index, (resource_id, resource_offset) in enumerate(entries):
        if resource_offset < HEADER_SIZE or resource_offset >= data_end:
            report_lines.append(
                f"[{index:04d}] id={hex32(resource_id)} "
                f"off={hex32(resource_offset)} skipped (outside [HEADER,data_end))."
            )
            continue

        header_candidate = read_colmodel_header(file, resource_offset, data_end)
        if header_candidate is None:
            report_lines.append(
                f"[{index:04d}] id={hex32(resource_id)} off={hex32(resource_offset)} "
                f"not recognised as CColModel."
            )
            continue

        entry = colmodels.get(resource_offset)
        if entry is None:
            entry = {"header": header_candidate, "refs": []}
            colmodels[resource_offset] = entry
        entry["refs"].append(resource_id)

        report_lines.append(
            f"[{index:04d}] id={hex32(resource_id)} off={hex32(resource_offset)} -> CColModel "
            f"tris={header_candidate['numTris']} boxes={header_candidate['numBoxes']} "
            f"spheres={header_candidate['numSpheres']}"
        )

    report_lines.append(f"Total CColModels accepted: {len(colmodels)}")
    if not colmodels:
        report_lines.append("No CColModel headers passed sanity; nothing to import.")
    return colmodels
