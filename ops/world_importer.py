# BLeeds - Scripts for working with R* Leeds (GTA Stories, Manhunt 2, etc) formats in Blender
# Author: spicybung
# Years: 2025 -

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

import bpy
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple

from ..leedsLib import world


def image_from_rgba_uint8(rgba: np.ndarray, name: str, w: int, h: int) -> bpy.types.Image:

    img = bpy.data.images.new(name=name, width=w, height=h, alpha=True, float_buffer=False)
    flat = (rgba.astype(np.float32) / 255.0).reshape(-1, 4)
    img.pixels = flat.flatten().tolist()
    img.alpha_mode = 'STRAIGHT'
    img.pack()
    return img


def create_material_from_image(img: bpy.types.Image, mat_name: str) -> bpy.types.Material:

    mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    nt = mat.node_tree
    for node in list(nt.nodes):
        nt.nodes.remove(node)
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (300, 0)
    principled = nt.nodes.new("ShaderNodeBsdfPrincipled"); principled.location = (0, 0)
    tex = nt.nodes.new("ShaderNodeTexImage"); tex.location = (-300, 0); tex.image = img
    nt.links.new(tex.outputs["Color"], principled.inputs["Base Color"])
    if img.has_data and "Alpha" in tex.outputs and "Alpha" in principled.inputs:
        nt.links.new(tex.outputs["Alpha"], principled.inputs["Alpha"])
        mat.blend_method = 'BLEND'
    nt.links.new(principled.outputs["BSDF"], out.inputs["Surface"])
    return mat


def get_or_create_collection(name: str) -> bpy.types.Collection:
    """Return an existing collection or create one under the scene root."""
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


def classify_entries(entries: list) -> None:
    """Label resource entries as ``TEX_REF`` or ``MDL`` according to heuristics."""
    for e in entries:
        if e.b16 == 0 and e.a16 != 0:
            e.kind = "TEX_REF"
            e.ref_addr = e.a32
            e.note = "tex_ref"
        else:
            e.kind = "MDL"
            e.note = "mdl_or_other"
            e.mdl_info = None


def decode_textures_for_entries(data: bytes, header: world.WorldHeader, entries: list, stem: str) -> None:

    n = len(data)
    tex_entries = [e for e in entries if e.kind == "TEX_REF" and 0 < getattr(e, 'ref_addr', 0) < n]
    if not tex_entries:
        return
    uniq = []
    seen = set()
    for e in sorted(tex_entries, key=lambda e: e.ref_addr):
        if e.ref_addr not in seen:
            uniq.append(e.ref_addr)
            seen.add(e.ref_addr)
    decoded: Dict[int, Tuple[bpy.types.Image, bpy.types.Material, Tuple[int, int]]] = {}
    for idx, addr in enumerate(uniq):
        start = addr
        if idx + 1 < len(uniq):
            next_start = uniq[idx + 1]
        else:
            if 0 < header.global0 < n and header.global0 > start:
                next_start = header.global0
            else:
                next_start = n
        if next_start <= start or next_start - start < 64:
            continue
        blob = data[start:next_start]
        index = blob[:-64]
        palette = blob[-64:]
        pal = [tuple(palette[i:i + 4]) for i in range(0, 64, 4)]
        try:
            w, h = world.choose_single_size_for_4bpp(len(index))
        except Exception:
            continue
        expanded = world.expand_nibbles_lo_first(index)
        need = w * h
        if len(expanded) < need:
            continue
        slab = expanded[:need]
        slab = world.unswizzle8_ps2_linearized(slab, w, h)
        idx2d = slab.reshape(h, w)
        w2 = world.nearest_pow2(w)
        h2 = world.nearest_pow2(h)
        if (w2, h2) != (w, h):
            idx2d = world.resize_indices_to_dims(idx2d, w2, h2)
            w, h = w2, h2
        idx2d = np.flipud(idx2d)
        pal_arr = np.asarray(pal, dtype=np.uint8)
        pal_arr = world.apply_ps2_alpha_scale(pal_arr, do_scale=True)
        rgba = pal_arr[np.clip(idx2d, 0, pal_arr.shape[0] - 1)]
        name = f"{stem}_tex_{addr:08X}"
        img = image_from_rgba_uint8(rgba, name, w, h)
        mat = create_material_from_image(img, name)
        decoded[addr] = (img, mat, (w, h))
    for e in tex_entries:
        res = decoded.get(e.ref_addr)
        if res:
            e.image, e.material, e.tex_size = res
            e.note += f"|decoded {e.tex_size}"
        else:
            e.note += "|decode_fail"


def build_mdl_objects(entries: list, resources: list, stem: str, collection: bpy.types.Collection = None, max_pairs_per_mdl: int = 4) -> None:

    res_map = {e.res_id: e for e in resources}
    if collection is None:
        collection = get_or_create_collection(f"WRLD_MDL_{stem}")
    total = 0
    for e in entries:
        if e.kind != "MDL":
            continue
        info = getattr(e, 'mdl_info', None)
        if not info or not info.get('pairs'):
            continue
        parent_name = f"{stem}_mdl{e.res_id:04d}"
        parent = bpy.data.objects.new(parent_name, None)
        parent.empty_display_type = 'ARROWS'
        parent.empty_display_size = 0.5
        parent["wrld_res_id"] = int(e.res_id)
        parent["wrld_a16"] = int(e.a16)
        parent["wrld_b16"] = int(e.b16)
        parent["wrld_a32"] = int(e.a32)
        parent["wrld_b32"] = int(e.b32)
        collection.objects.link(parent)
        total += 1
        for idx, (tex_id, unknown) in enumerate(info['pairs'][:max_pairs_per_mdl]):
            child_name = f"{parent_name}_tex{tex_id:04d}_{idx}"
            child = bpy.data.objects.new(child_name, None)
            child.empty_display_type = 'PLAIN_AXES'
            child.empty_display_size = 0.2
            child["tex_res_id"] = int(tex_id)
            child["tex_unknown"] = int(unknown)
            ref = res_map.get(tex_id)
            if ref and getattr(ref, 'material', None) is not None:
                child["wrld_tex_material"] = ref.material.name
            child.parent = parent
            collection.objects.link(child)
            total += 1
    world.dbg(f"[mdl] created {total} objects in collection '{collection.name}'")


def build_mdl_geometry(entries: list, data: bytes, stem: str, collection: bpy.types.Collection = None) -> None:
    """Parse MDL blobs into meshes and link them into a collection.

    Each MDL entry is decompressed and parsed using ``world.MDLParser``.
    Materials are assigned via ``parser.material_by_res_index``.  The
    resulting mesh object is linked into ``collection`` (or
    ``WRLD_GEO_<stem>`` if not provided), and statistics are saved
    into the entry's ``mdl_info`` for logging.
    """
    if collection is None:
        collection = get_or_create_collection(f"WRLD_GEO_{stem}")
    mat_map: Dict[int, bpy.types.Material] = {e.res_id: e.material for e in entries if getattr(e, 'material', None) is not None}
    total = 0
    for e in entries:
        if e.kind != "MDL":
            continue
        start = e.offset
        end = e.offset + e.length
        if start < 0 or end > len(data) or start >= end:
            continue
        blob = data[start:end]
        parser = world.MDLParser(blob, stem, use_swizzle=True, debug_print=False)
        parser.material_by_res_index = mat_map
        try:
            mlist = parser.parse_mdl_material_list(0)
        except Exception as ex:
            e.note += f"|mdl_material_error {ex}"
            continue
        groups, after = parser.parse_mdl_stream_after_list(mlist.next_off)
        parser.assign_materials_by_strip_bytes(mlist, groups)
        obj, face_ranges = parser.build_mesh_from_groups(e.res_id, groups)
        unpack_count, mscal_count = parser.count_vif_commands()
        mdl_stat = {
            "materials_declared": mlist.count,
            "materials_used": len({m.texture_id for m in mlist.materials}),
            "unpack_count": unpack_count,
            "mscal_count": mscal_count,
            "groups": len(groups),
            "verts": 0,
            "faces": 0,
        }
        if obj is not None:
            collection.objects.link(obj)
            total += 1
            mdl_stat["verts"] = len(obj.data.vertices)
            mdl_stat["faces"] = len(obj.data.polygons)
            obj["wrld_res_id"] = int(e.res_id)
            obj["wrld_unpacks"] = int(unpack_count)
            obj["wrld_mscals"] = int(mscal_count)
            obj["wrld_materials"] = mlist.count
            obj["wrld_tri_strip_groups"] = len(groups)
        if e.mdl_info is None:
            e.mdl_info = {}
        e.mdl_info.update(mdl_stat)
    if total > 0:
        world.dbg(f"[mdl] built {total} geometry objects in collection '{collection.name}'")


def analyze_mdl_entries(data: bytes, entries: list, max_pairs: int = 8) -> None:
    """Extract hexdumps and initial texture pairs from MDL entries."""
    n = len(data)
    for e in entries:
        if e.kind != "MDL":
            continue
        start = e.offset
        end = e.offset + e.length
        if start < 0 or start >= n:
            continue
        slice_end = min(start + 64, n)
        hexd = world.hexdump_bytes(data[start:slice_end], max_len=slice_end - start)
        count = 0
        if e.b16 and e.b16 % 4 == 0:
            count = e.b16 // 4
        elif e.a16 and e.a16 % 4 == 0:
            count = e.a16 // 4
        if count <= 0:
            count = max_pairs
        count = min(count, max_pairs)
        pairs: List[Tuple[int, int]] = []
        for i in range(count):
            pos = start + 4 + i * 4
            if pos + 4 > n or pos + 4 > end:
                break
            p0 = world.read_u16(data, pos)
            p1 = world.read_u16(data, pos + 2)
            pairs.append((p0, p1))
        e.mdl_info = {
            "a16": e.a16,
            "b16": e.b16,
            "a32": e.a32,
            "b32": e.b32,
            "hexdump": hexd,
            "pairs": pairs,
        }


def log_and_import(path: str, decode_textures: bool = True, write_log: bool = True, build_models: bool = True) -> None:
    data = Path(path).read_bytes()
    header = world.parse_world_header(data)
    ext = world.parse_extended_header(data)
    entries = world.parse_resource_table(data, header, ext)
    classify_entries(entries)
    stem = Path(path).stem
    if decode_textures:
        decode_textures_for_entries(data, header, entries, stem)
    analyze_mdl_entries(data, entries)
    if build_models:
        try:
            build_mdl_geometry(entries, data, stem)
        except Exception as ex:
            world.dbg(f"[mdl] error while building MDL geometry: {ex}")
    lines: List[str] = []
    lines.append(f"[wrld] loading '{path}' ({len(data)} bytes)")
    lines.append(
        f"[wrld] magic={header.magic} type={header.wrld_type} size={header.total_size} "
        f"g0=0x{header.global0:08X} g1=0x{header.global1:08X} gcnt={header.global_count} "
        f"cont=0x{header.continuation:08X} resv=0x{header.reserved:08X}"
    )
    lines.append(
        f"[wrld] res_table=0x{ext.res_table_addr:08X} rows={ext.res_count} unk={ext.unknown_count}"
    )
    lines.append("[wrld] sky_offsets=" + ", ".join(f"0x{off:08X}" for off in ext.sky_offsets))
    lines.append(f"[res] parsed {len(entries)} raw entries from table")
    for e in entries:
        lines.append(
            f"[res] idx={e.table_index:02d} id={e.res_id} off=0x{e.offset:08X} len={e.length} "
            f"kind={e.kind}"
        )
    for e in entries:
        if e.kind == "TEX_REF":
            detail = (
                f"[res] idx={e.table_index:02d} id={e.res_id} TEX_REF "
                f"a16={e.a16} b16={e.b16} a32=0x{e.a32:08X} b32=0x{e.b32:08X} "
                f"ref=0x{e.ref_addr:08X}"
            )
            if getattr(e, 'tex_size', None):
                detail += f" size={e.tex_size}"
            detail += f" note={e.note}"
            lines.append(detail)
        else:
            lines.append(
                f"[res] idx={e.table_index:02d} id={e.res_id} MDL "
                f"a16={e.a16} b16={e.b16} a32=0x{e.a32:08X} b32=0x{e.b32:08X}"
            )
            info = e.mdl_info or {}
            hd = info.get('hexdump')
            if hd:
                lines.append(
                    f"[mdl] idx={e.table_index:02d} id={e.res_id} hexdump={hd}"
                )
            pairs = info.get('pairs')
            if pairs:
                pair_str = ", ".join(f"({p0},{p1})" for p0, p1 in pairs)
                lines.append(
                    f"[mdl] idx={e.table_index:02d} id={e.res_id} pairs={pair_str}"
                )
            mats_decl = info.get('materials_declared')
            unpacks = info.get('unpack_count')
            mscals = info.get('mscal_count')
            verts = info.get('verts')
            faces = info.get('faces')
            if mats_decl is not None:
                lines.append(
                    f"[mdl] idx={e.table_index:02d} id={e.res_id} materials={mats_decl} unpacks={unpacks} mscals={mscals} verts={verts} faces={faces}"
                )
    for line in lines:
        print(line)
    if write_log:
        out_path = Path(path).with_suffix(".wrld_full_log.txt")
        try:
            out_path.write_text("\n".join(lines), encoding="utf-8")
        except Exception as exc:
            print(f"[log] failed to write '{out_path}': {exc}")