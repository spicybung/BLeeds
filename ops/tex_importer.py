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

import os
import tempfile
from typing import List, Dict, Tuple, Optional, Any, Iterable

import numpy as np
import bpy

from ..leedsLib.tex import (
    PspTexHeader,
    Ps2TexHeader,
    read_u32,
    slot_base_from_slot_ptr,
    parse_container,
    parse_psp_header,
    parse_ps2_header,
    decode_psp_texture,
    decode_ps2_texture,
    is_mh2_tex_data,
    parse_mh2_tex_entries,
)

def normalize_leeds_texture_name(name: str) -> str:
    value = str(name or "").strip().lower()
    if value.endswith(".png") or value.endswith(".tga") or value.endswith(".dds") or value.endswith(".bmp"):
        value = os.path.splitext(value)[0]
    if value.endswith(".001") or value.endswith(".002") or value.endswith(".003") or value.endswith(".004"):
        stem, suffix = value.rsplit(".", 1)
        if suffix.isdigit():
            value = stem
    return value

LEEDS_TEXTURE_SIDECAR_EXTENSIONS: Tuple[str, ...] = (".xtx", ".chk", ".tex")


def find_last_texture_raster_end(
    raster_offset: int,
    container_bases: Iterable[int],
    global_offsets: Iterable[int],
    data_size: int,
) -> int:
    start = int(raster_offset)
    candidates: List[int] = []

    for value in list(container_bases or []):
        try:
            offset = int(value)
        except Exception:
            continue
        if offset > start:
            candidates.append(offset)

    for value in list(global_offsets or []):
        try:
            offset = int(value)
        except Exception:
            continue
        if offset > start:
            candidates.append(offset)

    if int(data_size) > start:
        candidates.append(int(data_size))

    return min(candidates) if candidates else int(data_size)

def find_sidecar_texture_for_mdl(mdl_path: str) -> Optional[str]:
    if not mdl_path:
        return None

    base, _ext = os.path.splitext(os.path.abspath(mdl_path))
    candidates: List[str] = []
    for ext in LEEDS_TEXTURE_SIDECAR_EXTENSIONS:
        candidates.append(base + ext)
        candidates.append(base + ext.upper())
        candidates.append(base + ext.capitalize())

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    folder = os.path.dirname(base)
    wanted_stem = os.path.basename(base).lower()
    wanted_exts = set(LEEDS_TEXTURE_SIDECAR_EXTENSIONS)
    try:
        for entry in os.listdir(folder or "."):
            stem, ext = os.path.splitext(entry)
            if stem.lower() == wanted_stem and ext.lower() in wanted_exts:
                candidate = os.path.join(folder, entry)
                if os.path.isfile(candidate):
                    return candidate
    except Exception:
        pass

    return None

def find_sidecar_txd_for_mdl(mdl_path: str) -> Optional[str]:
    return find_sidecar_texture_for_mdl(mdl_path)


def find_mh2_sidecar_texture_for_mdl(mdl_path: str) -> Optional[str]:
    if not mdl_path:
        return None
    base, _extension = os.path.splitext(os.path.abspath(mdl_path))
    folder = os.path.dirname(base)
    wanted_stem = os.path.basename(base).casefold()
    try:
        entries = sorted(os.listdir(folder or "."))
    except Exception:
        entries = []
    for entry in entries:
        stem, extension = os.path.splitext(entry)
        if stem.casefold() != wanted_stem or extension.casefold() != ".tex":
            continue
        candidate = os.path.join(folder, entry)
        if not os.path.isfile(candidate):
            continue
        try:
            with open(candidate, "rb") as input_file:
                header_data = input_file.read()
            if is_mh2_tex_data(header_data):
                return candidate
        except Exception:
            continue
    return None

def get_image_original_texture_name(image: bpy.types.Image) -> str:
    try:
        value = image.get("bleeds_texture_name", "")
        if value:
            return str(value)
    except Exception:
        pass
    try:
        return str(image.name).split(".")[0]
    except Exception:
        return ""

def build_image_lookup(images: Iterable[bpy.types.Image]) -> Dict[str, bpy.types.Image]:
    lookup: Dict[str, bpy.types.Image] = {}
    for image in list(images or []):
        if image is None:
            continue
        names = []
        try:
            names.append(str(image.name))
        except Exception:
            pass
        try:
            original = image.get("bleeds_texture_name", "")
            if original:
                names.append(str(original))
        except Exception:
            pass
        for name in names:
            key = normalize_leeds_texture_name(name)
            if key and key not in lookup:
                lookup[key] = image
    return lookup

def find_principled_bsdf_node(material: bpy.types.Material) -> Optional[bpy.types.Node]:
    if material is None or not material.use_nodes or material.node_tree is None:
        return None
    for node in material.node_tree.nodes:
        if getattr(node, "type", "") == "BSDF_PRINCIPLED":
            return node
    return None

def find_or_create_output_node(material: bpy.types.Material) -> Optional[bpy.types.Node]:
    if material is None or material.node_tree is None:
        return None
    nodes = material.node_tree.nodes
    for node in nodes:
        if getattr(node, "type", "") == "OUTPUT_MATERIAL":
            return node
    try:
        return nodes.new(type="ShaderNodeOutputMaterial")
    except Exception:
        return None

def find_or_create_principled_bsdf_node(material: bpy.types.Material) -> Optional[bpy.types.Node]:
    if material is None:
        return None
    try:
        material.use_nodes = True
    except Exception:
        return None
    if material.node_tree is None:
        return None

    node = find_principled_bsdf_node(material)
    if node is not None:
        return node

    try:
        node = material.node_tree.nodes.new(type="ShaderNodeBsdfPrincipled")
        node.location = (0, 0)
    except Exception:
        return None

    out = find_or_create_output_node(material)
    try:
        if out is not None and "BSDF" in node.outputs and "Surface" in out.inputs:
            material.node_tree.links.new(node.outputs["BSDF"], out.inputs["Surface"])
    except Exception:
        pass
    return node

def remove_existing_bleeds_texture_links(material: bpy.types.Material, bsdf_node: bpy.types.Node) -> None:
    if material is None or material.node_tree is None or bsdf_node is None:
        return
    links = material.node_tree.links
    for socket_name in ("Base Color", "Alpha"):
        try:
            socket = bsdf_node.inputs.get(socket_name)
            if socket is None:
                continue
            for link in list(socket.links):
                links.remove(link)
        except Exception:
            pass

def image_has_meaningful_alpha(image: bpy.types.Image) -> bool:
    if image is None:
        return False

    try:
        if "bleeds_texture_has_meaningful_alpha" in image:
            return bool(image.get("bleeds_texture_has_meaningful_alpha", False))
    except Exception:
        pass

    try:
        pixels = image.pixels
        pixel_count = len(pixels) // 4
        if pixel_count <= 0:
            return False

        alpha_min = 1.0
        alpha_max = 0.0
        for pixel_index in range(pixel_count):
            alpha_value = float(pixels[(pixel_index * 4) + 3])
            if alpha_value < alpha_min:
                alpha_min = alpha_value
            if alpha_value > alpha_max:
                alpha_max = alpha_value
            if alpha_min < 0.999 and alpha_max > 0.001:
                return True
        return alpha_max > 0.001 and alpha_min < 0.999
    except Exception:
        return False


def material_allows_texture_alpha(
    material: bpy.types.Material,
    image: bpy.types.Image,
) -> bool:
    if material is None:
        return True

    image_platform = ""
    try:
        image_platform = str(image.get("bleeds_texture_platform", "") or "").strip().lower()
    except Exception:
        image_platform = ""

    if image_platform != "psp":
        return True

    try:
        if "bleeds_mdl_allow_texture_alpha" in material:
            return bool(material.get("bleeds_mdl_allow_texture_alpha", True))
    except Exception:
        pass

    return True


def psp_image_alpha_is_effectively_opaque(image: bpy.types.Image) -> bool:
    if image is None:
        return False

    image_platform = ""
    try:
        image_platform = str(image.get("bleeds_texture_platform", "") or "").strip().lower()
    except Exception:
        image_platform = ""

    if image_platform != "psp":
        return False

    try:
        alpha_min = int(image.get("bleeds_texture_alpha_min", 255))
        alpha_max = int(image.get("bleeds_texture_alpha_max", 255))
    except Exception:
        return False

    return alpha_min >= 250 and alpha_max >= 250


def configure_material_alpha_mode(
    material: bpy.types.Material,
    bsdf_node: bpy.types.Node,
    texture_node: bpy.types.Node,
    use_texture_alpha: bool,
) -> None:
    if material is None or bsdf_node is None:
        return

    alpha_input = None
    try:
        alpha_input = bsdf_node.inputs.get("Alpha")
    except Exception:
        alpha_input = None

    if use_texture_alpha and texture_node is not None and alpha_input is not None:
        try:
            alpha_output = texture_node.outputs.get("Alpha")
            if alpha_output is not None:
                material.node_tree.links.new(alpha_output, alpha_input)
        except Exception:
            pass
        try:
            material.blend_method = "HASHED"
        except Exception:
            pass
        try:
            material.shadow_method = "HASHED"
        except Exception:
            pass
        try:
            if hasattr(material, "show_transparent_back"):
                material.show_transparent_back = False
        except Exception:
            pass
    else:
        if alpha_input is not None:
            try:
                alpha_input.default_value = 1.0
            except Exception:
                pass
        try:
            material.blend_method = "OPAQUE"
        except Exception:
            pass
        try:
            material.shadow_method = "OPAQUE"
        except Exception:
            pass
        try:
            if hasattr(material, "show_transparent_back"):
                material.show_transparent_back = False
        except Exception:
            pass
        try:
            diffuse = tuple(material.diffuse_color)
            if len(diffuse) >= 4:
                material.diffuse_color = (diffuse[0], diffuse[1], diffuse[2], 1.0)
        except Exception:
            pass

    try:
        material["bleeds_texture_uses_alpha"] = bool(use_texture_alpha)
    except Exception:
        pass


def apply_image_to_material(material: bpy.types.Material, image: bpy.types.Image) -> bool:
    if material is None or image is None:
        return False

    try:
        material.use_nodes = True
    except Exception:
        return False

    if material.node_tree is None:
        return False

    bsdf = find_or_create_principled_bsdf_node(material)
    if bsdf is None:
        return False

    nodes = material.node_tree.nodes
    links = material.node_tree.links

    existing_node = None
    for node in nodes:
        try:
            if getattr(node, "type", "") == "TEX_IMAGE" and (node.get("bleeds_auto_texture_node", False) or node.get("bleeds_auto_txd_node", False)):
                existing_node = node
                break
        except Exception:
            pass

    if existing_node is None:
        try:
            existing_node = nodes.new(type="ShaderNodeTexImage")
            existing_node.location = (-350, 120)
        except Exception:
            return False

    try:
        existing_node.image = image
        existing_node.label = "BLeeds Texture"
        existing_node.name = "BLeeds_Texture_Image"
        existing_node["bleeds_auto_texture_node"] = True
        existing_node["bleeds_auto_txd_node"] = True
    except Exception:
        pass

    remove_existing_bleeds_texture_links(material, bsdf)

    try:
        if "Color" in existing_node.outputs and "Base Color" in bsdf.inputs:
            links.new(existing_node.outputs["Color"], bsdf.inputs["Base Color"])
    except Exception:
        pass

    use_texture_alpha = (
        image_has_meaningful_alpha(image)
        and material_allows_texture_alpha(material, image)
        and not psp_image_alpha_is_effectively_opaque(image)
    )
    configure_material_alpha_mode(
        material=material,
        bsdf_node=bsdf,
        texture_node=existing_node,
        use_texture_alpha=use_texture_alpha,
    )

    try:
        material.use_screen_refraction = False
    except Exception:
        pass

    try:
        material["bleeds_texture_image_name"] = str(image.name)
        material["bleeds_texture_texture_name"] = get_image_original_texture_name(image)
        material["bleeds_txd_image_name"] = str(image.name)
        material["bleeds_txd_texture_name"] = get_image_original_texture_name(image)
    except Exception:
        pass

    return True

def texture_names_for_material(material: bpy.types.Material) -> List[str]:
    names: List[str] = []
    if material is None:
        return names

    for key in (
        "bleeds_mdl_texture_name",
        "bleeds_mdl_part_texture_name",
        "bleeds_mdl_material_name",
        "bleeds_texture_texture_name",
        "bleeds_txd_texture_name",
    ):
        try:
            value = material.get(key, "")
            if value:
                names.append(str(value))
        except Exception:
            pass

    try:
        if material.name:
            names.append(str(material.name))
    except Exception:
        pass

    return names

def texture_names_for_object_material_slot(obj: bpy.types.Object, material: bpy.types.Material) -> List[str]:
    names = texture_names_for_material(material)
    if obj is None:
        return names

    for datablock in (obj, getattr(obj, "data", None)):
        if datablock is None:
            continue
        for key in (
            "bleeds_mdl_texture_name",
            "bleeds_mdl_part_texture_name",
            "bleeds_mdl_material_name",
        ):
            try:
                value = datablock.get(key, "")
                if value:
                    names.append(str(value))
            except Exception:
                pass

    return names

def apply_images_to_imported_mdl_materials(
    images: Iterable[bpy.types.Image],
    imported_objects: Iterable[bpy.types.Object],
) -> Tuple[int, int, List[str]]:
    image_lookup = build_image_lookup(images)
    matched_materials = 0
    visited_materials = set()
    missing_names: List[str] = []

    for obj in list(imported_objects or []):
        if obj is None or getattr(obj, "type", None) != "MESH":
            continue
        data = getattr(obj, "data", None)
        if data is None:
            continue
        for material in list(getattr(data, "materials", []) or []):
            if material is None:
                continue
            material_key = getattr(material, "name", str(id(material)))
            if material_key in visited_materials:
                continue

            candidate_names = texture_names_for_object_material_slot(obj, material)
            image = None
            best_name = ""
            for name in candidate_names:
                lookup_key = normalize_leeds_texture_name(name)
                if lookup_key in image_lookup:
                    image = image_lookup[lookup_key]
                    best_name = name
                    break

            if image is None:
                for name in candidate_names:
                    lookup_key = normalize_leeds_texture_name(name)
                    if lookup_key and lookup_key not in missing_names:
                        missing_names.append(lookup_key)
                continue

            if apply_image_to_material(material, image):
                matched_materials += 1
                visited_materials.add(material_key)
                try:
                    material["bleeds_texture_matched_from"] = str(best_name)
                    material["bleeds_txd_matched_from"] = str(best_name)
                except Exception:
                    pass

    return matched_materials, len(image_lookup), missing_names

def import_sidecar_texture_for_mdl(
    mdl_path: str,
    imported_objects: Iterable[bpy.types.Object],
    platform: str = "auto",
) -> Tuple[Optional[str], List[bpy.types.Image], int, List[str]]:
    texture_path = find_sidecar_texture_for_mdl(mdl_path)
    if not texture_path:
        return None, [], 0, []

    decode_platform = str(platform or "auto").strip().lower()
    if decode_platform not in {"auto", "psp", "ps2"}:
        decode_platform = "auto"

    images = decode_chk_to_blender_images(
        texture_path,
        platform=decode_platform,
        prefix="",
    )
    matched_materials, _image_count, missing_names = apply_images_to_imported_mdl_materials(
        images,
        imported_objects,
    )
    return texture_path, images, matched_materials, missing_names

def load_mh2_dds_image(entry, input_path: str, prefix: str = "") -> Optional[bpy.types.Image]:
    source_path = os.path.abspath(str(input_path))
    source_key = os.path.normcase(source_path)
    base_image_name = "{}{}".format(prefix, entry.name)
    image_name = base_image_name

    for existing_image in bpy.data.images:
        try:
            existing_source = os.path.normcase(os.path.abspath(str(existing_image.get("bleeds_texture_source_path", "") or "")))
            existing_texture_name = normalize_leeds_texture_name(existing_image.get("bleeds_texture_name", existing_image.name))
        except Exception:
            continue
        if existing_source == source_key and existing_texture_name == normalize_leeds_texture_name(entry.name):
            return existing_image

    existing = bpy.data.images.get(base_image_name)
    if existing is not None:
        source_stem = os.path.splitext(os.path.basename(source_path))[0]
        image_name = "{} [{}]".format(base_image_name, source_stem)

    temp_path = ""
    try:
        file_descriptor, temp_path = tempfile.mkstemp(prefix="bleeds_mh2_tex_", suffix=".dds")
        try:
            with os.fdopen(file_descriptor, "wb") as output_file:
                output_file.write(entry.dds_data)
        except Exception:
            try:
                os.close(file_descriptor)
            except Exception:
                pass
            raise

        image = bpy.data.images.load(temp_path, check_existing=False)
        image.name = image_name
        try:
            image.pack()
        except Exception:
            pass
        try:
            image.filepath_raw = ""
        except Exception:
            pass
        try:
            image["bleeds_texture_name"] = str(entry.name)
            image["bleeds_texture_source_path"] = source_path
            image["bleeds_texture_platform"] = "mh2_pc"
            image["bleeds_mh2_tex_width"] = int(entry.width)
            image["bleeds_mh2_tex_height"] = int(entry.height)
            image["bleeds_mh2_tex_bits_per_pixel"] = int(entry.bits_per_pixel)
            image["bleeds_mh2_tex_mipmap_count"] = int(entry.mipmap_count)
            image["bleeds_mh2_tex_dds_size"] = int(entry.data_size)
        except Exception:
            pass
        return image
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except Exception:
                pass


def decode_mh2_tex_to_blender_images(
    input_path: str,
    prefix: str = "",
) -> List[bpy.types.Image]:
    if not os.path.isfile(input_path):
        raise FileNotFoundError("Input file {!r} does not exist".format(input_path))
    with open(input_path, "rb") as input_file:
        data = input_file.read()
    entries = parse_mh2_tex_entries(data)
    images: List[bpy.types.Image] = []
    for entry in entries:
        image = load_mh2_dds_image(entry, input_path, prefix=prefix)
        if image is not None:
            images.append(image)
    return images


def decode_chk_to_blender_images(
    input_path: str,
    platform: str = 'auto',
    prefix: str = '',
) -> List[bpy.types.Image]:

    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file '{input_path}' does not exist")
    with open(input_path, 'rb') as f:
        data = f.read()

    if is_mh2_tex_data(data):
        return decode_mh2_tex_to_blender_images(input_path, prefix=prefix)

    hdr = {
        'sig': data[0:4].decode('ascii', 'replace'),
        'plat': read_u32(data, 0x04),
        'coll_size': read_u32(data, 0x08),
        'glob1': read_u32(data, 0x0C),
        'glob2': read_u32(data, 0x10),
        'glob_count': read_u32(data, 0x14),
        'cont_byte': data[0x20],
        'flags24': data[0x21] | (data[0x22] << 8) | (data[0x23] << 16),
        'first_slot': read_u32(data, 0x28),
        'last_slot': read_u32(data, 0x2C),
    }
    first_slot = hdr['first_slot']
    last_slot = hdr['last_slot']
    visited = set()

    textures: List[Tuple[str, int, object]] = []
    container_bases: List[int] = []
    base = slot_base_from_slot_ptr(first_slot)
    last_base = slot_base_from_slot_ptr(last_slot) if last_slot else None

    while True:
        if base in visited:
            break
        visited.add(base)
        cinfo = parse_container(data, base)
        if not cinfo:
            break
        try:
            container_bases.append(int(cinfo['base']))
        except Exception:
            pass
        name = cinfo['name']

        if name and all(32 <= ord(ch) < 127 for ch in name):

            tex_off = cinfo['tex_off']
            hdr_psp: Optional[PspTexHeader] = None
            hdr_ps2: Optional[Ps2TexHeader] = None
            if platform in ('auto', 'psp'):
                hdr_psp = parse_psp_header(data, tex_off)
            if platform in ('auto', 'ps2'):
                hdr_ps2 = parse_ps2_header(data, tex_off)
            header_obj: Optional[object] = None
            if platform == 'psp':
                header_obj = hdr_psp
            elif platform == 'ps2':
                header_obj = hdr_ps2
            else:

                def is_plausible_psp(h: Optional[PspTexHeader]) -> bool:
                    if not h:
                        return False

                    if h.bpp not in (4, 8, 32):
                        return False
                    if h.width < 4 or h.height < 4:
                        return False
                    return True

                def is_plausible_ps2(h: Optional[Ps2TexHeader]) -> bool:
                    if not h:
                        return False

                    if h.bpp not in (4, 8, 16, 32):
                        return False
                    if h.width < 4 or h.height < 4:
                        return False
                    return True

                has_psp = is_plausible_psp(hdr_psp)
                has_ps2 = is_plausible_ps2(hdr_ps2)
                if has_psp and not has_ps2:
                    header_obj = hdr_psp
                elif has_ps2 and not has_psp:
                    header_obj = hdr_ps2
                elif has_psp and has_ps2:

                    size_psp = hdr_psp.width * hdr_psp.height
                    size_ps2 = hdr_ps2.width * hdr_ps2.height
                    if size_psp >= size_ps2:
                        header_obj = hdr_psp
                    else:
                        header_obj = hdr_ps2
                else:

                    header_obj = hdr_psp if hdr_psp else hdr_ps2
            if header_obj:
                textures.append((name, cinfo['tex_off'], header_obj))

        next_slot = cinfo['next_slot']
        if next_slot == 0:
            break
        next_base = slot_base_from_slot_ptr(next_slot)
        if next_base == base:
            break
        base = next_base
    if not textures:
        return []

    textures_sorted = []
    for name, tex_off, header in textures:
        if isinstance(header, PspTexHeader):
            roff = header.raster_offset
        elif isinstance(header, Ps2TexHeader):
            roff = header.raster_offset
        else:
            continue
        textures_sorted.append((name, tex_off, header, roff))
    textures_sorted.sort(key=lambda x: x[3])
    offsets = [hdr_info[3] for hdr_info in textures_sorted]
    block_sizes: List[int] = []
    for texture_index, start in enumerate(offsets):
        structural_end = find_last_texture_raster_end(
            raster_offset=start,
            container_bases=container_bases,
            global_offsets=(hdr['glob1'], hdr['glob2'], hdr['coll_size']),
            data_size=len(data),
        )

        if texture_index + 1 < len(offsets):
            next_raster_offset = offsets[texture_index + 1]
            end = min(int(next_raster_offset), int(structural_end))
        else:
            end = int(structural_end)

        block_sizes.append(max(0, int(end) - int(start)))
    blender_images: List[bpy.types.Image] = []

    for ((name, tex_off, header, roff), blk_size) in zip(textures_sorted, block_sizes):
        if isinstance(header, PspTexHeader):
            rgba = decode_psp_texture(data, header, blk_size, palette_override=None)
        elif isinstance(header, Ps2TexHeader):
            rgba = decode_ps2_texture(data, header, blk_size, palette_override=None)
        else:
            rgba = None
        if rgba is None:
            continue
        h, w, _ = rgba.shape

        rgba_flat = rgba.reshape((-1, 4)).astype(np.float32) / 255.0

        pixels = rgba_flat.flatten().tolist()

        image_name = f"{prefix}{name}"

        img = bpy.data.images.new(name=image_name, width=w, height=h, alpha=True)
        alpha_values = rgba[:, :, 3]
        alpha_min = int(alpha_values.min()) if alpha_values.size else 255
        alpha_max = int(alpha_values.max()) if alpha_values.size else 255
        has_meaningful_alpha = bool(alpha_max > 0 and alpha_min < 255)

        try:
            img["bleeds_texture_name"] = str(name)
            img["bleeds_texture_source_path"] = str(input_path)
            img["bleeds_texture_platform"] = str(platform)
            img["bleeds_texture_alpha_min"] = alpha_min
            img["bleeds_texture_alpha_max"] = alpha_max
            img["bleeds_texture_has_meaningful_alpha"] = has_meaningful_alpha
        except Exception:
            pass

        img.pixels = pixels
        blender_images.append(img)
    return blender_images

def import_mh2_sidecar_texture_for_mdl(
    mdl_path: str,
    imported_objects: Optional[Iterable[bpy.types.Object]] = None,
) -> Tuple[Optional[str], List[bpy.types.Image], int, List[str]]:
    texture_path = find_mh2_sidecar_texture_for_mdl(mdl_path)
    if not texture_path:
        return None, [], 0, []
    images = decode_mh2_tex_to_blender_images(texture_path, prefix="")
    if imported_objects is None:
        return texture_path, images, 0, []
    matched_materials, _image_count, missing_names = apply_images_to_imported_mdl_materials(
        images,
        imported_objects,
    )
    return texture_path, images, matched_materials, missing_names


def import_sidecar_txd_for_mdl(mdl_path: str, imported_objects: Iterable[bpy.types.Object], platform: str = "auto") -> Tuple[Optional[str], List[bpy.types.Image], int, List[str]]:
    return import_sidecar_texture_for_mdl(mdl_path, imported_objects, platform=platform)
