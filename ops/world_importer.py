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

import bpy
import math
import numpy as np
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .. import get_or_create_corner_color_layer, set_mesh_auto_smooth, stamp_bleeds_entity_type
from ..leedsLib import bsp, world

def image_from_rgba_uint8(rgba: np.ndarray, name: str, w: int, h: int) -> bpy.types.Image:

    img = bpy.data.images.new(name=name, width=w, height=h, alpha=True, float_buffer=False)
    flat = np.ascontiguousarray(rgba.reshape(-1, 4), dtype=np.float32)
    flat *= (1.0 / 255.0)
    try:
        img.pixels.foreach_set(flat.reshape(-1))
    except Exception:
        img.pixels = flat.reshape(-1).tolist()
    img.update()
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
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll

def classify_entries(entries: list) -> None:
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


def _source_stem(path: str) -> str:
    """Use a stable source name without browser-copy suffixes such as '(1)'."""
    stem = Path(path).stem.strip()
    cleaned = re.sub(r"\s*\(\d+\)$", "", stem).strip()
    return cleaned or stem or "WorldLevel"


def _remove_collection_recursive(collection: bpy.types.Collection) -> None:
    if collection is None:
        return
    for child in list(collection.children):
        _remove_collection_recursive(child)
    for obj in list(collection.objects):
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
        except Exception:
            try:
                collection.objects.unlink(obj)
            except Exception:
                pass
    try:
        bpy.data.collections.remove(collection)
    except Exception:
        pass


def _new_world_level_collections(stem: str, collision_only: bool = False):
    root_name = f"{stem} [World Level]"
    existing = bpy.data.collections.get(root_name)
    if existing is not None:
        _remove_collection_recursive(existing)

    root = bpy.data.collections.new(root_name)
    bpy.context.scene.collection.children.link(root)

    objects = bpy.data.collections.new(f"{stem} Objects")
    root.children.link(objects)

    collision = bpy.data.collections.new(f"{stem} Collision")
    root.children.link(collision)
    return root, objects, collision


def _set_material_base_color(material, rgba) -> None:
    color = tuple(float(v) / 255.0 for v in rgba)
    try:
        material.diffuse_color = color
    except Exception:
        pass
    if not getattr(material, "use_nodes", False):
        return
    try:
        node = material.node_tree.nodes.get("Principled BSDF")
        if node is not None and "Base Color" in node.inputs:
            node.inputs["Base Color"].default_value = color
    except Exception:
        pass


def _create_bsp_material(
    stem: str,
    record: bsp.BSPMaterialRecord,
    image: Optional[bpy.types.Image],
) -> bpy.types.Material:
    source_name = record.name.strip() or f"Untextured Material {record.index + 1:02d}"
    material = bpy.data.materials.new(f"{source_name} [{stem}]")
    material.use_nodes = True
    _set_material_base_color(material, record.color_rgba)
    material["blds_kind"] = "PSP_BSP_MATERIAL"
    material["blds_bsp_material_index"] = int(record.index)
    material["blds_bsp_material_name"] = str(record.name)
    material["blds_bsp_material_flags"] = int(record.flags)

    if image is None:
        return material

    try:
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        output = next((node for node in nodes if node.type == "OUTPUT_MATERIAL"), None)
        principled = next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
        if output is None:
            output = nodes.new("ShaderNodeOutputMaterial")
        if principled is None:
            principled = nodes.new("ShaderNodeBsdfPrincipled")
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = image
        texture.label = record.name or image.name
        links.new(texture.outputs["Color"], principled.inputs["Base Color"])
        uses_alpha = _image_uses_cutout_alpha(image)
        if uses_alpha and "Alpha" in texture.outputs and "Alpha" in principled.inputs:
            links.new(texture.outputs["Alpha"], principled.inputs["Alpha"])
            try:
                material.blend_method = "HASHED"
            except Exception:
                pass
        else:
            try:
                principled.inputs["Alpha"].default_value = 1.0
                material.blend_method = "OPAQUE"
            except Exception:
                pass
        material["blds_bsp_uses_texture_alpha"] = bool(uses_alpha)
        if not principled.outputs["BSDF"].is_linked:
            links.new(principled.outputs["BSDF"], output.inputs["Surface"])
    except Exception:
        pass
    return material


def _image_uses_cutout_alpha(image: bpy.types.Image) -> bool:
    if image is None:
        return False
    try:
        if "blds_has_cutout_alpha" in image:
            return bool(image.get("blds_has_cutout_alpha", False))
    except Exception:
        pass
    transparent = False
    opaque = False
    try:
        pixels = image.pixels
        for offset in range(3, len(pixels), 4):
            if float(pixels[offset]) < 0.5:
                transparent = True
            else:
                opaque = True
            if transparent and opaque:
                break
    except Exception:
        return False
    result = bool(transparent and opaque)
    try:
        image["blds_has_cutout_alpha"] = result
    except Exception:
        pass
    return result


def _decode_bsp_txd(txd_path: Optional[Path], stem: str, lines: List[str]):
    images_by_name: Dict[str, bpy.types.Image] = {}
    images_by_index: Dict[int, bpy.types.Image] = {}
    if txd_path is None:
        lines.append("[bsp-txd] no matching TCDT texture dictionary found beside the BSP")
        return images_by_name, images_by_index

    try:
        dictionary = bsp.parse_tcdt(str(txd_path))
    except Exception as exc:
        lines.append(f"[bsp-txd] failed to parse '{txd_path}': {exc}")
        return images_by_name, images_by_index

    lines.append(
        f"[bsp-txd] source='{txd_path}' textures={len(dictionary.textures)} "
        f"wrapped_z2hm={dictionary.header.wrapped_z2hm}"
    )
    for texture in dictionary.textures:
        try:
            rgba = bsp.decode_tcdt_texture(dictionary, texture)
            image_name = texture.name.strip() or f"Texture_{texture.index:03d}"
            image = image_from_rgba_uint8(
                rgba,
                f"{stem}_{image_name}",
                int(texture.width),
                int(texture.height),
            )
            image["blds_kind"] = "PSP_TCDT_TEXTURE"
            image["blds_tcdt_index"] = int(texture.index)
            image["blds_tcdt_name"] = str(texture.name)
            image["blds_tcdt_source"] = str(txd_path)
            images_by_index[int(texture.index)] = image
            normalized = bsp.normalize_asset_name(texture.name)
            if normalized:
                images_by_name[normalized] = image
            lines.append(
                f"[bsp-txd] index={texture.index} name='{texture.name}' "
                f"size={texture.width}x{texture.height} bpp={texture.bits_per_pixel} decoded=yes"
            )
        except Exception as exc:
            lines.append(
                f"[bsp-txd] index={texture.index} name='{texture.name}' decoded=no error={exc}"
            )
    return images_by_name, images_by_index


def _assign_corner_colors(mesh, block: bsp.BSPGeometryBlock) -> None:
    layer = get_or_create_corner_color_layer(mesh, "Color")
    if layer is None:
        return
    try:
        data = layer.data
        for loop_index, loop in enumerate(mesh.loops):
            rgba = block.vertices[int(loop.vertex_index)].color
            color = tuple(float(value) / 255.0 for value in rgba)
            data[loop_index].color = color
    except Exception:
        pass


def _build_bsp_mesh_object(
    stem: str,
    source_path: str,
    block_index: int,
    block: bsp.BSPGeometryBlock,
    materials: List[bpy.types.Material],
    collection: bpy.types.Collection,
    txd_path: Optional[Path],
):
    faces, face_materials = bsp.triangle_strip_faces(block)
    if not faces:
        return None, 0

    from collections import Counter

    material_face_counts = Counter(
        int(index) for index in face_materials
        if 0 <= int(index) < len(materials)
    )
    dominant_material_index = material_face_counts.most_common(1)[0][0] if material_face_counts else 0
    dominant_material_name = "Untextured"
    if 0 <= dominant_material_index < len(materials):
        try:
            dominant_material_name = str(
                materials[dominant_material_index].get(
                    "blds_bsp_material_name",
                    materials[dominant_material_index].name,
                ) or "Untextured"
            ).strip()
        except Exception:
            dominant_material_name = str(materials[dominant_material_index].name)
    dominant_material_name = dominant_material_name or "Untextured"
    object_name = f"{stem} Part {block_index + 1:03d} - {dominant_material_name}"
    mesh = bpy.data.meshes.new(object_name)
    mesh.from_pydata([vertex.position for vertex in block.vertices], [], faces)
    mesh.update()

    used_material_indices = sorted(material_face_counts)
    if not used_material_indices and materials:
        used_material_indices = [0]
    local_material_indices = {}
    for source_index in used_material_indices:
        local_material_indices[int(source_index)] = len(mesh.materials)
        mesh.materials.append(materials[int(source_index)])
    for polygon_index, polygon in enumerate(mesh.polygons):
        source_index = face_materials[polygon_index] if polygon_index < len(face_materials) else 0
        polygon.material_index = int(local_material_indices.get(int(source_index), 0))
        try:
            polygon.use_smooth = True
        except Exception:
            pass

    try:
        uv_layer = mesh.uv_layers.new(name="UVMap")
        for loop_index, loop in enumerate(mesh.loops):
            uv_layer.data[loop_index].uv = block.vertices[int(loop.vertex_index)].uv
    except Exception:
        pass
    _assign_corner_colors(mesh, block)
    set_mesh_auto_smooth(mesh, True)
    try:
        mesh.auto_smooth_angle = math.radians(60.0)
    except Exception:
        pass

    obj = bpy.data.objects.new(object_name, mesh)
    collection.objects.link(obj)
    stamp_bleeds_entity_type(obj, "OBJECT")
    obj["blds_kind"] = "PSP_BSP_WORLD"
    obj["blds_source"] = str(source_path)
    obj["blds_bsp_block_index"] = int(block_index)
    obj["blds_bsp_block_offset"] = int(block.file_offset)
    obj["blds_bsp_block_size"] = int(block.size)
    obj["blds_bsp_flags"] = int(block.flags)
    obj["blds_bsp_strip_count"] = int(block.strip_count)
    obj["blds_bsp_vertex_count"] = int(block.vertex_count)
    obj["blds_bsp_face_count"] = int(len(faces))
    obj["blds_bsp_display_name"] = str(object_name)
    obj["blds_bsp_dominant_material_index"] = int(dominant_material_index)
    obj["blds_bsp_dominant_material_name"] = str(dominant_material_name)
    obj["blds_bsp_material_indices"] = [int(index) for index in used_material_indices]
    obj["blds_bsp_material_names"] = [
        str(materials[index].get("blds_bsp_material_name", materials[index].name) or materials[index].name)
        for index in used_material_indices
    ]
    obj["blds_bsp_bounds_center"] = [float(value) for value in block.bounds[:3]]
    obj["blds_bsp_bounds_radius"] = float(block.bounds[3])
    obj["blds_bsp_decode_summary"] = "{} vertices; {} faces; {} strips; {} used materials".format(
        int(block.vertex_count), int(len(faces)), int(block.strip_count), int(len(used_material_indices))
    )
    obj["blds_platform"] = "PSP"
    try:
        if 0 <= dominant_material_index < len(materials):
            color = tuple(materials[dominant_material_index].diffuse_color)
            obj.color = color
    except Exception:
        pass
    if txd_path is not None:
        obj["blds_txd_source"] = str(txd_path)
    return obj, len(faces)


def _discover_psp_bsp_scene_set(path: str):
    selected = Path(path)
    clean_stem = _source_stem(path)
    match = re.match(r"^(.*?)(\d+)$", clean_stem, re.IGNORECASE)
    scene_stem = match.group(1).rstrip(" _-.") if match else clean_stem
    if not scene_stem:
        scene_stem = clean_stem

    candidates = []
    if match:
        prefix = match.group(1)
        for sibling in selected.parent.iterdir():
            if not sibling.is_file() or sibling.suffix.lower() != ".bsp":
                continue
            sibling_stem = re.sub(r"\s*\(\d+\)$", "", sibling.stem).strip()
            sibling_match = re.match(r"^(.*?)(\d+)$", sibling_stem, re.IGNORECASE)
            if sibling_match and sibling_match.group(1).lower() == prefix.lower():
                candidates.append((int(sibling_match.group(2)), sibling.name.lower(), sibling))
    if not candidates:
        candidates.append((0, selected.name.lower(), selected))

    ordered = []
    seen = set()
    for _number, _name, candidate in sorted(candidates):
        resolved = str(candidate.resolve()).lower()
        if resolved in seen:
            continue
        seen.add(resolved)
        ordered.append(candidate)
    return scene_stem, ordered


def import_psp_bsp(
    path: str,
    decode_textures: bool = True,
    write_log: bool = True,
    build_models: bool = True,
) -> None:
    selected_path = Path(path)
    scene_stem, bsp_paths = _discover_psp_bsp_scene_set(path)

    parsed_files = []
    material_names = []
    for bsp_path in bsp_paths:
        parsed = bsp.parse_psp_bsp(str(bsp_path))
        parsed_files.append((bsp_path, parsed))
        material_names.extend(item.name for item in parsed.materials)

    txd_path = bsp.find_best_companion_txd(str(selected_path), material_names) if decode_textures else None
    root, objects_collection, collision_collection = _new_world_level_collections(scene_stem, collision_only=True)
    root["blds_kind"] = "PSP_BSP_WORLD_LEVEL"
    root["blds_source"] = str(selected_path)
    root["blds_platform"] = "PSP"
    root["blds_world_level_format"] = "BSP"
    root["blds_bsp_scene_files"] = "|".join(str(item[0]) for item in parsed_files)

    lines: List[str] = []
    lines.append("===== R* Leeds BSP World Level Import =====")
    lines.append(f"[bsp-set] selected='{selected_path}' scene='{scene_stem}' files={len(parsed_files)}")
    for bsp_path, parsed in parsed_files:
        lines.append(
            f"[bsp] source='{bsp_path}' packed={parsed.header.packed_size} "
            f"unpacked={parsed.header.unpacked_size} wrapped_z2hm={parsed.header.wrapped_z2hm} "
            f"magic={parsed.header.magic} version={parsed.header.version} "
            f"relocations={parsed.header.relocation_count} root=0x{parsed.root_offset:08X} "
            f"materials={len(parsed.materials)} render_blocks={len(parsed.geometry)}"
        )

    images_by_name: Dict[str, bpy.types.Image] = {}
    images_by_index: Dict[int, bpy.types.Image] = {}
    if decode_textures:
        images_by_name, images_by_index = _decode_bsp_txd(txd_path, scene_stem, lines)

    material_cache = {}
    object_count = 0
    vertex_count = 0
    face_count = 0
    collision_sources = 0

    for bsp_path, parsed in parsed_files:
        file_stem = _source_stem(str(bsp_path))
        if parsed.geometry:
            source_collection = bpy.data.collections.new(f"{file_stem} - Render Geometry")
            objects_collection.children.link(source_collection)
        else:
            source_collection = bpy.data.collections.new(f"{file_stem} - Collision Data")
            collision_collection.children.link(source_collection)
        source_collection["blds_kind"] = "BSP_RENDER_SOURCE" if parsed.geometry else "BSP_COLLISION_SOURCE"
        source_collection["blds_bsp_source"] = str(bsp_path)
        source_collection["blds_bsp_material_count"] = int(len(parsed.materials))
        source_collection["blds_bsp_render_block_count"] = int(len(parsed.geometry))
        source_collection["blds_bsp_collision_only"] = bool(parsed.collision_only)
        source_collection["blds_bsp_readable_summary"] = (
            "{} render parts; {} materials".format(len(parsed.geometry), len(parsed.materials))
            if parsed.geometry else
            "Collision-side BSP; no render geometry blocks"
        )
        materials: List[bpy.types.Material] = []
        for record in parsed.materials:
            normalized = bsp.normalize_asset_name(record.name)
            cache_key = (normalized, int(record.flags), tuple(record.color_rgba))
            material = material_cache.get(cache_key)
            if material is None:
                image = images_by_name.get(normalized) if normalized else images_by_index.get(int(record.index))
                material = _create_bsp_material(scene_stem, record, image)
                material_cache[cache_key] = material
                lines.append(
                    f"[bsp-material] source='{bsp_path.name}' index={record.index} "
                    f"name='{record.name}' flags=0x{record.flags:08X} "
                    f"texture={'yes' if image is not None else 'no'}"
                )
            materials.append(material)

        if build_models and parsed.geometry:
            for block_index, block in enumerate(parsed.geometry):
                obj, block_faces = _build_bsp_mesh_object(
                    file_stem,
                    str(bsp_path),
                    block_index,
                    block,
                    materials,
                    source_collection,
                    txd_path,
                )
                if obj is None:
                    lines.append(
                        f"[bsp-geometry] source='{bsp_path.name}' block={block_index} "
                        f"offset=0x{block.file_offset:08X} vertices={block.vertex_count} "
                        "faces=0 skipped=degenerate"
                    )
                    continue
                object_count += 1
                vertex_count += int(block.vertex_count)
                face_count += int(block_faces)
                lines.append(
                    f"[bsp-geometry] source='{bsp_path.name}' block={block_index} "
                    f"offset=0x{block.file_offset:08X} strips={block.strip_count} "
                    f"vertices={block.vertex_count} faces={block_faces} object='{obj.name}'"
                )
        elif not parsed.geometry:
            collision_sources += 1
            lines.append(
                f"[bsp-collision] source='{bsp_path.name}' contains no render blocks; "
                "kept as a collision source for scene-set decoding, with no fake placeholder object"
            )

    lines.append(
        f"[summary] collection='{root.name}' bsp_files={len(parsed_files)} "
        f"objects={object_count} vertices={vertex_count} faces={face_count} "
        f"collision_sources={collision_sources} textures={len(images_by_index)}"
    )
    if object_count == 0:
        lines.append(
            "[warning] no render geometry was decoded from any BSP in the discovered scene set; "
            "the importer did not create an empty cube or claim a successful mesh import"
        )

    for line in lines:
        print(line)
    if write_log:
        output = selected_path.with_suffix(".bsp_full_log.txt")
        try:
            output.write_text("\n".join(lines), encoding="utf-8")
        except Exception as exc:
            print(f"[log] failed to write '{output}': {exc}")

def _import_wrld(path: str, decode_textures: bool = True, write_log: bool = True, build_models: bool = True) -> None:
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



def log_and_import(
    path: str,
    decode_textures: bool = True,
    write_log: bool = True,
    build_models: bool = True,
) -> None:
    source = Path(path)
    suffix = source.suffix.lower()
    magic = source.read_bytes()[:4]
    if suffix == ".bsp" or magic == bsp.Z2HM_MAGIC:
        # Z2HM can wrap more than one Leeds resource type. Confirm the
        # decompressed payload before routing it to the BSP reader.
        if suffix == ".bsp":
            return import_psp_bsp(path, decode_textures, write_log, build_models)
        try:
            payload, _wrapped, _size = bsp.load_resource_file(path)
        except Exception:
            payload = b""
        if payload[:4] == bsp.DLRW_MAGIC:
            return import_psp_bsp(path, decode_textures, write_log, build_models)
    return _import_wrld(path, decode_textures, write_log, build_models)
