# BLeeds - Scripts for working with R* Leeds (GTA Stories, Chinatown Wars, Manhunt 2, etc) formats in Blender
# Author: spicybung
# Years: 2025 - 2026

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import struct
import time
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import bpy
from mathutils import Matrix

from ..compat import setMeshAutoSmooth
from ..leedsLib import lvz_img as LVZ

UNPACK_BYTES = struct.pack("<I", LVZ.read_lvz.UNPACK)
IMG_MDL_SCAN_LIMIT = 0x240
IMG_MDL_MAX_IMPORT = 4096
IMPORT_IMG_MDL_PAYLOADS_BY_DEFAULT = False

def read_img_next_to_lvz(lvz_path: str) -> Tuple[Optional[bytes], Optional[str]]:
    lvz_p = Path(lvz_path)
    candidates = [
        lvz_p.with_suffix(".IMG"),
        lvz_p.with_suffix(".img"),
        lvz_p.with_suffix(".IMG.zip"),
        lvz_p.with_suffix(".img.zip"),
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        if candidate.suffix.lower() == ".zip":
            with zipfile.ZipFile(candidate, "r") as zf:
                member_name = None
                for name in zf.namelist():
                    if name.lower().endswith(".img"):
                        member_name = name
                        break
                if member_name is None and zf.namelist():
                    member_name = zf.namelist()[0]
                if member_name is None:
                    return None, None
                return zf.read(member_name), candidate.name
        return candidate.read_bytes(), candidate.name
    return None, None

def detect_lvz_img_platform(lvz_reader: LVZ.read_lvz, img_reader: Optional[LVZ.read_img]) -> str:
    if img_reader is not None:
        try:
            return img_reader.detect_platform_from_lvz_groups()
        except Exception:
            pass
    try:
        groups, _, _ = lvz_reader.parse_slave_groups_and_rescount()
        group_types = set()
        for group in groups:
            note = str(getattr(group, "note", ""))
            marker = "group_type=0x"
            if marker in note:
                part = note.split(marker, 1)[1].split()[0].strip(";,)")
                group_types.add(int(part, 16))
        nonzero = [value for value in group_types if value != 0]
        if any(value >= 0x0D for value in nonzero):
            return "PS2"
        if any(value in (0x02, 0x03) for value in nonzero):
            return "PSP"
    except Exception:
        pass
    return "PS2"

def platform_uses_ps2_swizzle(platform: str) -> bool:
    return str(platform).upper() == "PS2"

def detect_platform_from_resource_dialects(lvz_reader: LVZ.read_lvz, rows: List[Dict], fallback_platform: str) -> Tuple[str, Dict[str, int]]:
    counts: Dict[str, int] = {}
    for row in rows:
        if row.get("kind") != "MDL":
            continue
        try:
            material_list = lvz_reader.parse_mdl_material_list(
                int(row.get("res_addr", 0)),
                max_end=int(row.get("res_end", len(lvz_reader.decomp)) or len(lvz_reader.decomp)),
            )
        except Exception:
            continue
        tag = str(getattr(material_list, "format_tag", "unknown"))
        counts[tag] = counts.get(tag, 0) + 1

    psp_count = sum(value for key, value in counts.items() if key.startswith("psp_wrld"))
    ps2_count = sum(value for key, value in counts.items() if key.startswith("ps2_"))
    if psp_count > ps2_count and psp_count > 0:
        return "PSP", counts
    if ps2_count > 0:
        return "PS2", counts
    return fallback_platform, counts

def matrix_from_img_detail(detail) -> Matrix:
    origin = None
    if len(detail) > 18:
        origin = detail[18]
    return LVZ.matrix_from_16_floats_row_major_values_with_origin(detail[12], origin)

def build_mesh_from_mdl_groups(stem: str, res_index: int, groups: List[LVZ.MDLStripGroup]):
    if not groups:
        return None, []

    vertices: List[Tuple[float, float, float]] = []
    uvs: List[Tuple[float, float]] = []
    faces: List[Tuple[int, int, int]] = []
    face_ranges: List[Tuple[int, int, int]] = []

    for group in groups:
        for strip in group.strips:
            count = min(len(strip.verts), len(strip.uvs), int(strip.count))
            if count < 3:
                continue
            base = len(vertices)
            vertices.extend(strip.verts[:count])
            uvs.extend(strip.uvs[:count])
            poly_start = len(faces)
            for i in range(count - 2):
                if i & 1:
                    faces.append((base + i + 1, base + i, base + i + 2))
                else:
                    faces.append((base + i, base + i + 1, base + i + 2))
            face_ranges.append((poly_start, count - 2, strip.material_res_index))

    if not vertices or not faces:
        return None, []

    mesh_name = f"{stem}{res_index}"
    mesh = bpy.data.meshes.new(mesh_name)
    mesh.from_pydata(vertices, [], faces)
    setMeshAutoSmooth(mesh, True)
    mesh.validate(clean_customdata=False)
    mesh.update()

    if uvs:
        uv_layer = mesh.uv_layers.new(name="UVMap")
        uv_data = uv_layer.data
        for poly in mesh.polygons:
            loop_start = poly.loop_start
            for loop_index, vertex_index in enumerate(poly.vertices):
                if vertex_index < len(uvs):
                    uv_data[loop_start + loop_index].uv = uvs[vertex_index]

    obj = bpy.data.objects.new(mesh_name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj["blds_kind"] = "MDL"
    obj["blds_res_index"] = int(res_index)
    obj["blds_groups"] = len(groups)
    obj["blds_faces"] = len(faces)
    obj["blds_verts"] = len(vertices)
    return obj, face_ranges

def get_or_create_missing_lvz_material(texture_id: int):
    name = f"lvz_texres_{int(texture_id)}_missing_image"
    material = bpy.data.materials.get(name)
    if material is not None:
        return material
    material = bpy.data.materials.new(name)
    material["blds_kind"] = "TEX_PLACEHOLDER"
    material["blds_texture_res_index"] = int(texture_id)
    material["blds_missing_texture_image"] = True
    seed = (int(texture_id) * 1103515245 + 12345) & 0xFFFFFFFF
    r = 0.25 + (((seed >> 0) & 0xFF) / 255.0) * 0.55
    g = 0.25 + (((seed >> 8) & 0xFF) / 255.0) * 0.55
    b = 0.25 + (((seed >> 16) & 0xFF) / 255.0) * 0.55
    material.diffuse_color = (r, g, b, 1.0)
    return material

def add_material_slots(obj, material_by_res_index: Dict[int, bpy.types.Material], material_list: LVZ.MDLMaterialList, face_ranges):
    resid_to_slot: Dict[int, int] = {}
    slots_added = 0
    if material_list.materials:
        for material_record in material_list.materials:
            texture_id = int(material_record.texture_id)
            material = material_by_res_index.get(texture_id)
            if material is None:
                material = get_or_create_missing_lvz_material(texture_id)
            existing_slot = None
            for slot_index, existing_material in enumerate(obj.data.materials):
                if existing_material and existing_material.name == material.name:
                    existing_slot = slot_index
                    break
            if existing_slot is None:
                obj.data.materials.append(material)
                existing_slot = len(obj.data.materials) - 1
                slots_added += 1
            resid_to_slot[texture_id] = existing_slot

    if face_ranges:
        polygons = obj.data.polygons
        for poly_start, poly_count, mat_resid in face_ranges:
            if mat_resid is None or mat_resid < 0:
                continue
            slot = resid_to_slot.get(int(mat_resid))
            if slot is None:
                continue
            for poly_index in range(poly_start, poly_start + poly_count):
                if 0 <= poly_index < len(polygons):
                    polygons[poly_index].material_index = slot
    return slots_added

def img_chunk_end(img_bytes: bytes, ordered_conts: List[int], cont: int) -> int:
    img_len = len(img_bytes)
    end = img_len
    try:
        index = ordered_conts.index(cont)
        if index + 1 < len(ordered_conts):
            end = min(end, int(ordered_conts[index + 1]))
    except ValueError:
        pass
    if 0 <= cont + 4 <= img_len:
        declared = LVZ.read_u32(img_bytes, cont)
        if 0x20 <= declared <= 0x04000000:
            end = min(end, cont + declared)
    return max(cont, min(end, img_len))

def looks_like_img_mdl_payload(img_bytes: bytes, base: int, end: int) -> bool:
    if base < 0 or base + 4 > end:
        return False
    count = LVZ.read_u16(img_bytes, base + 0)
    size_bytes = LVZ.read_u16(img_bytes, base + 2)
    if count <= 0 or count > 256:
        return False
    if size_bytes < count * 22 or size_bytes > 0x4000:
        return False
    if base + 4 + size_bytes > end:
        return False

    for stream_guess in (base + 4 + (count * 22), base + 4 + size_bytes):
        cursor = stream_guess
        while cursor < end and img_bytes[cursor] == 0xAA and cursor - base < 0x1000:
            cursor += 1
        cursor = LVZ.align_down4(cursor)
        if img_bytes.find(UNPACK_BYTES, max(base, cursor - 0x10), min(end, cursor + 0x80)) >= 0:
            return True
    return False

def find_img_mdl_payload_start(img_bytes: bytes, cont: int, end: int) -> Optional[int]:
    scan_start = cont + 0x20
    scan_end = min(end, cont + IMG_MDL_SCAN_LIMIT)
    for base in range(LVZ.align_up4(scan_start), LVZ.align_down4(scan_end), 4):
        if looks_like_img_mdl_payload(img_bytes, base, end):
            return base
    return None

def collect_img_mdl_candidates(img_reader: LVZ.read_img) -> List[Dict[str, int]]:
    records = img_reader.find_top_level_container_records_from_lvz()
    img_bytes = img_reader.img_bytes
    ordered_conts = sorted(set(
        int(record["cont"]) for record in records
        if 0 <= int(record["cont"]) < len(img_bytes)
    ))

    candidates_by_cont: Dict[int, Dict[str, int]] = {}
    first_record_by_cont: Dict[int, Dict[str, int]] = {}
    for record in records:
        cont = int(record.get("cont", -1))
        if 0 <= cont < len(img_bytes) and cont not in first_record_by_cont:
            first_record_by_cont[cont] = record

    for cont in ordered_conts:
        end = img_chunk_end(img_bytes, ordered_conts, cont)
        base = find_img_mdl_payload_start(img_bytes, cont, end)
        if base is None:
            continue
        record = first_record_by_cont.get(cont, {})
        candidates_by_cont[cont] = {
            "cont": int(cont),
            "payload": int(base),
            "end": int(end),
            "group_type": int(record.get("group_type", 0)),
            "group_index": int(record.get("group_index", -1)),
            "child_index": int(record.get("child_index", -1)),
            "lvz_addr": int(record.get("lvz_addr", 0)),
            "declared_total": int(record.get("total", 0)),
        }
    return [candidates_by_cont[key] for key in sorted(candidates_by_cont)]

def build_lvz_resource_mdl_objects(lvz_reader: LVZ.read_lvz, rows: List[Dict]) -> Dict[int, bpy.types.Object]:
    mdl_rows = [row for row in rows if row.get("kind") == "MDL"]
    built_by_res: Dict[int, bpy.types.Object] = {}
    if not mdl_rows:
        LVZ.dbg("— LVZ Resource MDLs — none found")
        return built_by_res

    LVZ.dbg("— LVZ Resource MDLs —")
    for row in mdl_rows:
        res_index = int(row["index"])
        res_addr = int(row["res_addr"])
        res_end = int(row.get("res_end", len(lvz_reader.decomp)) or len(lvz_reader.decomp))
        try:
            material_list = lvz_reader.parse_mdl_material_list(res_addr, max_end=res_end)
            LVZ.dbg(
                f"[mdl {res_index}] list: format={material_list.format_tag} row_len={material_list.row_len} "
                f"count={material_list.count} size_bytes={material_list.size_bytes} "
                f"bytes_read={material_list.bytes_read} aa_tail={len(material_list.aa_tail)} "
                f"next=0x{material_list.next_off:08X} end=0x{res_end:08X}"
            )
            for material_index, material_record in enumerate(material_list.materials):
                LVZ.dbg(
                    f"  mat[{material_index:02d}] texRES={material_record.texture_id} "
                    f"strip_size={material_record.tri_strip_size} cull={int(material_record.backface_cull)} "
                    f"us={material_record.u_scale:.4f} vs={material_record.v_scale:.4f} "
                    f"flags2=0x{material_record.flags2:04X} bbox={material_record.bbox6_i16}"
                )
            groups, after = lvz_reader.parse_mdl_geometry_after_list(material_list, max_end=res_end)
            LVZ.dbg(f"[mdl {res_index}] batches={len(groups)} stream_end=0x{after:08X} bounded_end=0x{res_end:08X}")
            lvz_reader.assign_materials_by_strip_bytes(material_list, groups)
        except Exception as exc:
            LVZ.dbg(f"[mdl {res_index}] parse failed at 0x{res_addr:08X}: {exc}")
            continue

        obj, face_ranges = build_mesh_from_mdl_groups(lvz_reader.stem, res_index, groups)
        if obj is None:
            LVZ.dbg(f"[mdl {res_index}] no faces/verts, skipped object creation")
            continue
        slots_added = add_material_slots(obj, lvz_reader.material_by_res_index, material_list, face_ranges)
        built_by_res[res_index] = obj
        LVZ.dbg(f"[mdl {res_index}] → created object '{obj.name}' (added {slots_added} material slots)")

    LVZ.dbg(f"[done] total LVZ resource MDL objects created: {len(built_by_res)}")
    return built_by_res

def build_img_mdl_objects(stem: str, img_bytes: bytes, img_reader: LVZ.read_img, material_by_res_index: Dict[int, bpy.types.Material], source_lvz_path: str, img_name: Optional[str]) -> Dict[int, bpy.types.Object]:
    candidates = collect_img_mdl_candidates(img_reader)
    parser = LVZ.read_lvz(
        decomp_bytes=img_bytes,
        stem=stem,
        use_swizzle=False,
        debug_print=False,
    )
    parser.material_by_res_index = material_by_res_index

    built_by_cont: Dict[int, bpy.types.Object] = {}
    LVZ.dbg("— IMG MDL Containers —")
    LVZ.dbg(f"[img-mdl] payload candidates: {len(candidates)}")

    for import_index, candidate in enumerate(candidates[:IMG_MDL_MAX_IMPORT]):
        cont = int(candidate["cont"])
        payload = int(candidate["payload"])
        end = int(candidate["end"])
        try:
            material_list = parser.parse_mdl_material_list(payload, max_end=end)
            groups, after = parser.parse_mdl_geometry_after_list(material_list, max_end=end)
            parser.assign_materials_by_strip_bytes(material_list, groups)
        except Exception as exc:
            LVZ.dbg(f"[img-mdl 0x{cont:08X}] parse failed at payload=0x{payload:08X}: {exc}")
            continue

        obj, face_ranges = build_mesh_from_mdl_groups(stem, import_index, groups)
        if obj is None:
            LVZ.dbg(
                f"[img-mdl 0x{cont:08X}] no faces/verts payload=0x{payload:08X} "
                f"batches={len(groups)} end=0x{end:08X}"
            )
            continue

        slots_added = add_material_slots(obj, material_by_res_index, material_list, face_ranges)
        obj.name = f"{stem}_img_{import_index:04d}"
        obj.data.name = obj.name
        obj["blds_kind"] = "IMG_MDL"
        obj["blds_res_index"] = int(import_index)
        obj["blds_img_cont"] = cont
        obj["blds_img_payload"] = payload
        obj["blds_img_end"] = end
        obj["blds_img_group_type"] = int(candidate.get("group_type", 0))
        obj["blds_img_group_index"] = int(candidate.get("group_index", -1))
        obj["blds_img_child_index"] = int(candidate.get("child_index", -1))
        obj["blds_source_lvz_path"] = str(source_lvz_path)
        if img_name:
            obj["blds_source_img_path"] = str(Path(source_lvz_path).with_name(img_name))
        built_by_cont[cont] = obj
        LVZ.dbg(
            f"[img-mdl {import_index:04d}] cont=0x{cont:08X} payload=0x{payload:08X} "
            f"groups={len(groups)} verts={obj.get('blds_verts', 0)} faces={obj.get('blds_faces', 0)} "
            f"materials={slots_added}"
        )

    if len(candidates) > IMG_MDL_MAX_IMPORT:
        LVZ.dbg(f"[img-mdl] stopped at safety cap {IMG_MDL_MAX_IMPORT}; candidates={len(candidates)}")
    LVZ.dbg(f"[img-mdl] total IMG MDL objects created: {len(built_by_cont)}")
    return built_by_cont

def build_sector_overlay_mdl_objects(stem: str, img_bytes: bytes, lvz_reader: LVZ.read_lvz, img_reader: LVZ.read_img, sector_records: List[Dict[str, int]], max_resource_id: int, source_lvz_path: str, img_name: Optional[str], needed_sector_res_keys=None) -> Dict[Tuple[int, int], bpy.types.Object]:
    parser = LVZ.read_lvz(
        decomp_bytes=img_bytes,
        stem=stem,
        use_swizzle=bool(lvz_reader.use_swizzle),
        debug_print=False,
    )
    parser.material_by_res_index = lvz_reader.material_by_res_index

    overlay_rows = img_reader.collect_sector_overlay_resources(sector_records, max_resource_id=max_resource_id)
    if needed_sector_res_keys is not None:
        needed_sector_res_keys = set(needed_sector_res_keys)
        overlay_rows = [row for row in overlay_rows if (int(row.get("sector_index", -1)), int(row.get("res_id", -1))) in needed_sector_res_keys]
    overlay_by_sector_res: Dict[Tuple[int, int], bpy.types.Object] = {}
    parsed = 0
    skipped_duplicate = 0
    skipped_non_geometry = 0
    LVZ.dbg("— IMG Sector Overlay Resource MDLs —")
    LVZ.dbg(f"[sector-mdl] overlay resource rows: {len(overlay_rows)}")

    for overlay in overlay_rows:
        sector_index = int(overlay["sector_index"])
        res_id = int(overlay["res_id"])
        key = (sector_index, res_id)
        if key in overlay_by_sector_res:
            skipped_duplicate += 1
            continue

        raw_off = int(overlay["raw_off"])
        sector_end = int(overlay["sector_end"])
        try:
            material_list = parser.parse_mdl_material_list(raw_off, max_end=sector_end)
            groups, after = parser.parse_mdl_geometry_after_list(material_list, max_end=sector_end)
            parser.assign_materials_by_strip_bytes(material_list, groups)
        except Exception:
            skipped_non_geometry += 1
            continue

        obj, face_ranges = build_mesh_from_mdl_groups(f"{stem}_sec{sector_index:04d}_res", res_id, groups)
        if obj is None:
            skipped_non_geometry += 1
            continue

        obj.name = f"{stem}_sec{sector_index:04d}_res{res_id}"
        obj.data.name = obj.name
        slots_added = add_material_slots(obj, parser.material_by_res_index, material_list, face_ranges)
        obj["blds_kind"] = "IMG_SECTOR_MDL"
        obj["blds_res_index"] = res_id
        obj["blds_img_sector_index"] = sector_index
        obj["blds_img_sector_x"] = int(overlay.get("sector_x", 0))
        obj["blds_img_sector_y"] = int(overlay.get("sector_y", 0))
        obj["blds_img_overlay_resource"] = True
        obj["blds_img_overlay_raw_off"] = raw_off
        obj["blds_img_overlay_raw_ptr"] = int(overlay.get("raw_ptr", 0))
        obj["blds_source_lvz_path"] = str(source_lvz_path)
        if img_name:
            obj["blds_source_img_path"] = str(Path(source_lvz_path).with_name(img_name))
        overlay_by_sector_res[key] = obj
        parsed += 1
        if parsed <= 64:
            LVZ.dbg(
                f"[sector-mdl] sector={sector_index} res={res_id} raw=0x{raw_off:08X} "
                f"format={material_list.format_tag} groups={len(groups)} materials={slots_added}"
            )

    LVZ.dbg(
        f"[sector-mdl] created={len(overlay_by_sector_res)} skipped_non_geometry={skipped_non_geometry} "
        f"skipped_duplicate={skipped_duplicate}"
    )
    return overlay_by_sector_res

def stamp_source_paths(objects_by_res: Dict[int, bpy.types.Object], lvz_path: str, img_name: Optional[str]):
    for _, obj in objects_by_res.items():
        try:
            obj["blds_source_lvz_path"] = str(lvz_path)
            if img_name:
                obj["blds_source_img_path"] = str(Path(lvz_path).with_name(img_name))
        except Exception:
            pass

def stamp_img_detail_on_object(obj: bpy.types.Object, detail, instance_index: int):
    obj["blds_img_cont"] = int(detail[1])
    obj["blds_img_rel_off"] = int(detail[2])
    obj["blds_img_ipl_raw"] = int(detail[3])
    obj["blds_img_ipl_id"] = int(detail[4])
    obj["blds_img_instance_index"] = int(instance_index)
    if len(detail) > 18:
        obj["blds_img_pass_index"] = int(detail[13])
        obj["blds_img_pass_name"] = str(detail[14])
        obj["blds_img_sector_index"] = int(detail[15])
        obj["blds_img_sector_x"] = int(detail[16])
        obj["blds_img_sector_y"] = int(detail[17])
        origin = detail[18]
        obj["blds_img_sector_origin_x"] = float(origin[0])
        obj["blds_img_sector_origin_y"] = float(origin[1])
        obj["blds_img_sector_origin_z"] = float(origin[2])

def remove_unplaced_base_objects(candidate_objects, used_object_ids) -> int:
    removed = 0
    for obj in list(candidate_objects):
        if obj is None:
            continue
        if id(obj) in used_object_ids:
            continue
        try:
            mesh = obj.data if getattr(obj, "type", None) == 'MESH' else None
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
            removed += 1
        except Exception:
            try:
                obj.hide_viewport = True
                obj.hide_render = True
            except Exception:
                pass
    return removed

def apply_img_instance_transforms(built_by_res: Dict[int, bpy.types.Object], details, overlay_by_sector_res: Optional[Dict[Tuple[int, int], bpy.types.Object]] = None) -> Tuple[int, int, int]:
    if not details:
        return 0, 0, 0

    overlay_by_sector_res = overlay_by_sector_res or {}
    object_use_count: Dict[int, int] = {}
    used_object_ids = set()
    seen_instance_keys = set()
    applied = 0
    linked = 0
    skipped_missing = 0
    skipped_duplicate = 0

    for detail in details:
        res_id = int(detail[0])
        ipl_id = int(detail[4])
        sector_index = int(detail[15]) if len(detail) > 15 else -1
        pass_name = str(detail[14]) if len(detail) > 14 else "UNKNOWN"
        if pass_name in LVZ.IMG_LOD_PASS_NAMES:
            continue

        instance_key = (ipl_id, res_id)
        if instance_key in seen_instance_keys:
            skipped_duplicate += 1
            continue
        seen_instance_keys.add(instance_key)

        base_obj = overlay_by_sector_res.get((sector_index, res_id))
        if base_obj is None:
            base_obj = built_by_res.get(res_id)
        if base_obj is None:
            skipped_missing += 1
            continue

        base_id = id(base_obj)
        instance_index = object_use_count.get(base_id, 0)
        matrix = matrix_from_img_detail(detail)

        if instance_index == 0:
            obj = base_obj
        else:
            obj = base_obj.copy()
            obj.data = base_obj.data
            obj.animation_data_clear()
            obj.name = f"{base_obj.name}_ipl{ipl_id:04d}_{instance_index:03d}"
            try:
                bpy.context.scene.collection.objects.link(obj)
            except Exception:
                bpy.context.collection.objects.link(obj)
            linked += 1

        obj.matrix_world = matrix
        stamp_img_detail_on_object(obj, detail, instance_index)
        object_use_count[base_id] = instance_index + 1
        used_object_ids.add(base_id)
        applied += 1

        if instance_index == 0:
            LVZ.dbg(
                f"[apply] RES={res_id} sector={sector_index} pass={pass_name} IPL={ipl_id} "
                f"→ object '{obj.name}' matrix_world set."
            )

    base_candidates = list(built_by_res.values()) + list(overlay_by_sector_res.values())
    removed = remove_unplaced_base_objects(base_candidates, used_object_ids)
    LVZ.dbg(f"[apply] skipped missing mesh/resource rows: {skipped_missing}")
    LVZ.dbg(f"[apply] skipped duplicate IPL/resource rows: {skipped_duplicate}")
    LVZ.dbg(f"[apply] removed unplaced base resource objects: {removed}")
    return applied, linked, removed

def import_lvz_img_archive(operator, context, lvz_path: str, csv_dedup_res_ids: bool = True, apply_img_transforms: bool = True, debug_print: bool = True, write_debug_log: bool = True):
    if not lvz_path:
        operator.report({'ERROR'}, "No LVZ selected.")
        return {'CANCELLED'}

    stem = Path(lvz_path).stem
    log_path = str(Path(lvz_path).with_suffix("")) + "_blds_import.log" if write_debug_log else None
    LVZ.DEBUG = LVZ.DebugOut(debug_print, write_debug_log, log_path)

    t0 = time.time()
    lvz_bytes_in = Path(lvz_path).read_bytes()
    decomp, was_cmp = LVZ.safe_decompress(lvz_bytes_in)

    LVZ.dbg("===== LVZ Walk + IMG Match/Apply =====")
    LVZ.dbg("Patch: LVZ_IMG_SECTOR_DIRECTORY_VISIBLE_PASS_OVERLAY_FIX_V9")
    LVZ.dbg(f"LVZ: {lvz_path}")
    LVZ.dbg(f"[io] LVZ bytes in: {len(lvz_bytes_in)}  decomp: {len(decomp)} ({'compressed' if was_cmp else 'raw'})")
    LVZ.dbg("")

    lvz = LVZ.read_lvz(
        decomp_bytes=decomp,
        stem=stem,
        use_swizzle=True,
        debug_print=debug_print,
    )

    try:
        master = lvz.parse_master_header()
        groups_hdr, res_count, _ = lvz.parse_slave_groups_and_rescount()
    except Exception as exc:
        operator.report({'ERROR'}, f"Failed to parse LVZ: {exc}")
        if LVZ.DEBUG is not None:
            LVZ.DEBUG.flush()
        return {'CANCELLED'}

    img_bytes, img_name = None, None
    try:
        img_bytes, img_name = read_img_next_to_lvz(lvz_path)
        if img_bytes:
            LVZ.dbg(f"— IMG Read — source: {img_name} bytes={len(img_bytes)}")
        else:
            LVZ.dbg("[img] IMG not found next to LVZ; IMG-based features will be skipped")
    except Exception as exc:
        LVZ.dbg(f"[img] failed to read IMG: {exc}")

    img = LVZ.read_img(img_bytes=img_bytes, lvz_bytes=decomp) if img_bytes else None
    platform = detect_lvz_img_platform(lvz, img)
    use_swizzle = platform_uses_ps2_swizzle(platform)
    lvz.use_swizzle = use_swizzle
    LVZ.dbg(f"[platform] auto-detected {platform}; texture swizzle={'PS2' if use_swizzle else 'PSP/no-PS2-swizzle'}")
    LVZ.dbg("")

    LVZ.dbg("— Slave Group Table —")
    LVZ.dbg(f"  groups: {len(groups_hdr)}")
    for group in groups_hdr:
        LVZ.dbg(
            f"  [sg {group.index:03d}] LVZ+0x{group.addr:08X} tag='{group.tag}' "
            f"size={group.total} gcnt={group.gcnt} contIMG=0x{group.cont:08X} — {group.note}"
        )
    LVZ.dbg(f"  resource count: {res_count}")
    if img is not None:
        parent_records = img.find_parent_container_records_from_lvz()
        nested_records = img.find_nested_container_records_from_lvz()
        LVZ.dbg(f"  parent IMG container records: {len(parent_records)}")
        LVZ.dbg(f"  nested DLRW preface records: {len(nested_records)} (diagnostic, not used as IMG row roots)")
        LVZ.dbg(f"  unique parent IMG container bases: {len(set(record['cont'] for record in parent_records))}")
    LVZ.dbg("")

    rows = lvz.walk_master_resource_table(master.res_table_addr, res_count)
    platform_from_resources, resource_dialects = detect_platform_from_resource_dialects(lvz, rows, platform)
    if platform_from_resources != platform or resource_dialects:
        platform = platform_from_resources
        use_swizzle = platform_uses_ps2_swizzle(platform)
        lvz.use_swizzle = use_swizzle
        dialect_text = ", ".join(f"{key}:{value}" for key, value in sorted(resource_dialects.items())) if resource_dialects else "none"
        LVZ.dbg(f"[platform] resource dialects: {dialect_text}; final platform={platform}; texture swizzle={'PS2' if use_swizzle else 'PSP/no-PS2-swizzle'}")
        LVZ.dbg("")
    LVZ.dbg("— Master Resource Table (first 300) —")
    for row in rows[:min(len(rows), 300)]:
        a16, b16 = row["peek_u16"]
        a32, b32 = row["peek_u32"]
        extra = []
        if row["kind"] == "UNK_FAC0" and "unk_fac0" in row:
            extra.append(f"unk_fac0={row['unk_fac0']}")
        if row["kind"] == "EMPTY" and "empty_reason" in row:
            extra.append(f"reason={row['empty_reason']}")
        if row["kind"] == "TEX_REF":
            extra.append(f"ref_addr=0x{row['ref_addr']:08X}")
            extra.append(f"RES(index)={row['index']}")
            if "embedded_res_id" in row and row["embedded_res_id"] is not None:
                extra.append(f"embedded=0x{row['embedded_res_id']:08X}")
        LVZ.dbg(
            f"[res {row['index']:5d}] table@0x{row['table_off']:08X} → res@0x{row['res_addr']:08X} "
            f"kind={row['kind']} u16,u16=({a16},{b16}) "
            f"u32,u32=(0x{(a32 if a32 is not None else 0):08X},0x{(b32 if b32 is not None else 0):08X}) "
            f"{' '.join(extra)}"
        )
    LVZ.dbg("")

    lvz.decode_textures(rows)

    transforms_by_res: Dict[int, Matrix] = {}
    details = []
    sector_records = []
    if img is not None:
        sector_records = img.find_sector_container_records_from_lvz()
        LVZ.dbg(f"[img] sector row directories: {len(img.find_sector_row_directories_from_lvz())}")
        LVZ.dbg(f"[img] concrete sector headers: {len(sector_records)}")
        details = img.enumerate_sector_details(max_resource_id=res_count, include_lod=False, dedupe_visible=True)
        stats = getattr(img, "last_sector_walk_stats", {}) or {}
        LVZ.dbg(
            f"[img] sector rows candidate={stats.get('candidate_rows', 0)} valid={stats.get('valid_rows', 0)} "
            f"kept_visible={stats.get('kept_rows', 0)} skipped_lod={stats.get('skipped_lod_rows', 0)} "
            f"skipped_dupes={stats.get('skipped_duplicate_rows', 0)}"
        )
        transforms_by_res = img.build_sector_transforms_map_and_log(details, enable_unique_log=csv_dedup_res_ids)
        all_rows = img.write_sector_csvs(lvz_path, details, enable_unique=csv_dedup_res_ids)
        LVZ.dbg(f"[img] visible non-LOD IMG placement rows kept: {len(all_rows)}")
        LVZ.dbg("— FILTERED VISIBLE RESOURCE IDs (IMG walk order) —")
        for i, (cont, rel_off, ipl_raw, ipl_id, res_id) in enumerate(all_rows[:2000]):
            LVZ.dbg(f"{i:04d}: {res_id}")
        if len(all_rows) > 2000:
            LVZ.dbg(f"[img] resource-id log truncated at 2000 / {len(all_rows)} rows")
    else:
        LVZ.dbg("[img] IMG rows not enumerated because IMG is missing")

    built_by_res = build_lvz_resource_mdl_objects(lvz, rows)
    stamp_source_paths(built_by_res, lvz_path, img_name)

    built_by_cont: Dict[int, bpy.types.Object] = {}
    if img is not None and IMPORT_IMG_MDL_PAYLOADS_BY_DEFAULT:
        built_by_cont = build_img_mdl_objects(stem, img_bytes, img, lvz.material_by_res_index, lvz_path, img_name)
    elif img is not None:
        LVZ.dbg("[img-mdl] direct IMG payload scan skipped by default; using LVZ resource MDLs for PS2/PSP LVZ+IMG world batches")

    overlay_by_sector_res: Dict[Tuple[int, int], bpy.types.Object] = {}
    if img is not None and sector_records:
        needed_sector_res_keys = {(int(detail[15]), int(detail[0])) for detail in details if len(detail) > 15}
        overlay_by_sector_res = build_sector_overlay_mdl_objects(
            stem,
            img_bytes,
            lvz,
            img,
            sector_records,
            int(res_count),
            lvz_path,
            img_name,
            needed_sector_res_keys=needed_sector_res_keys,
        )

    linked_instances = 0
    removed_unplaced = 0
    if apply_img_transforms and details:
        try:
            applied, linked_instances, removed_unplaced = apply_img_instance_transforms(built_by_res, details, overlay_by_sector_res)
            LVZ.dbg(f"[apply] IMG placement rows applied: {applied}")
            LVZ.dbg(f"[apply] linked duplicate placement objects created: {linked_instances}")
        except Exception as exc:
            LVZ.dbg(f"[apply] IMG placement transform pass failed: {exc}")
    elif apply_img_transforms:
        LVZ.dbg("[apply] no IMG transforms available to apply")

    elapsed = time.time() - t0
    LVZ.dbg(f"[summary] LVZ-table MDL resource objects parsed: {len(built_by_res)}")
    LVZ.dbg(f"[summary] IMG sector overlay MDL objects parsed: {len(overlay_by_sector_res)}")
    LVZ.dbg(f"[summary] removed unplaced resource objects: {removed_unplaced}")
    LVZ.dbg(f"[summary] linked IMG placement duplicates: {linked_instances}")
    LVZ.dbg(f"[summary] IMG-container MDL objects: {len(built_by_cont)}")
    LVZ.dbg(f"[total] finished in {elapsed:.3f} seconds")

    if LVZ.DEBUG is not None:
        LVZ.DEBUG.flush()
    operator.report({'INFO'}, f"Imported LVZ+IMG: {len(details)} visible placements, {linked_instances} linked duplicates, {len(overlay_by_sector_res)} sector MDLs, {removed_unplaced} unplaced resources removed ({platform}).")
    return {'FINISHED'}
