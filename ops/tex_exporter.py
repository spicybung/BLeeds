import math
import os
import struct
from typing import Iterable, List, Tuple

import bpy


def align(value: int, alignment: int) -> int:
    return (int(value) + int(alignment) - 1) & ~(int(alignment) - 1)


def power_of_two_log2(value: int) -> int:
    value = int(value)
    if value <= 0 or (value & (value - 1)) != 0:
        raise ValueError("Leeds texture dimensions must be powers of two")
    return int(math.log2(value))


def clean_texture_name(name: str) -> str:
    value = os.path.splitext(str(name or "texture"))[0]
    value = value.encode("ascii", "replace").decode("ascii").replace("?", "_")
    value = value[:63]
    return value or "texture"


def image_to_rgba8(image: bpy.types.Image, platform: str) -> Tuple[int, int, bytes]:
    width = int(image.size[0])
    height = int(image.size[1])
    power_of_two_log2(width)
    power_of_two_log2(height)

    if width > 4096 or height > 4096:
        raise ValueError(f"Texture '{image.name}' exceeds 4096x4096")

    pixel_count = width * height
    pixels = [0.0] * (pixel_count * 4)
    image.pixels.foreach_get(pixels)

    output = bytearray(pixel_count * 4)
    target = 0
    ps2 = str(platform).upper() == "PS2"

    # Blender image buffers are bottom-up. Leeds raster rows are top-down.
    for y in range(height - 1, -1, -1):
        row_start = y * width * 4
        for x in range(width):
            source = row_start + x * 4
            red = max(0, min(255, int(round(float(pixels[source + 0]) * 255.0))))
            green = max(0, min(255, int(round(float(pixels[source + 1]) * 255.0))))
            blue = max(0, min(255, int(round(float(pixels[source + 2]) * 255.0))))
            alpha_255 = max(0, min(255, int(round(float(pixels[source + 3]) * 255.0))))
            alpha = max(0, min(128, int(round(alpha_255 * 128.0 / 255.0)))) if ps2 else alpha_255
            output[target:target + 4] = bytes((red, green, blue, alpha))
            target += 4

    return width, height, bytes(output)


def collect_images_from_context(context: bpy.types.Context) -> List[bpy.types.Image]:
    found: List[bpy.types.Image] = []
    seen = set()

    objects = list(getattr(context, "selected_objects", []) or [])
    active = getattr(context, "active_object", None)
    if active is not None and active not in objects:
        objects.insert(0, active)

    for obj in objects:
        for slot in list(getattr(obj, "material_slots", []) or []):
            material = getattr(slot, "material", None)
            if material is None or not getattr(material, "use_nodes", False) or material.node_tree is None:
                continue
            for node in material.node_tree.nodes:
                if getattr(node, "type", "") != "TEX_IMAGE":
                    continue
                image = getattr(node, "image", None)
                if image is None or image.name in seen:
                    continue
                seen.add(image.name)
                found.append(image)

    if not found:
        area = getattr(context, "area", None)
        space = getattr(area, "spaces", None)
        active_space = getattr(space, "active", None) if space is not None else None
        image = getattr(active_space, "image", None)
        if image is not None:
            found.append(image)

    return found


def resolve_texture_depth(image, bit_depth):
    value = bit_depth
    if str(value).upper() == "AUTO":
        value = image.get("bleeds_texture_bpp", 8)
    try:
        return 4 if int(value) <= 4 else 8
    except (TypeError, ValueError):
        return 8


def quantize_texture_rgba(rgba: bytes, bit_depth: int, platform: str) -> bytes:
    from collections import Counter

    color_limit = 1 << bit_depth
    colors = Counter(tuple(rgba[offset:offset + 4]) for offset in range(0, len(rgba), 4))
    if len(colors) <= color_limit:
        palette = list(colors)
        indices_by_color = {color: index for index, color in enumerate(palette)}
    else:
        boxes = [list(colors)]
        while len(boxes) < color_limit:
            candidates = []
            for index, box in enumerate(boxes):
                if len(box) < 2:
                    continue
                ranges = [max(color[channel] for color in box) - min(color[channel] for color in box) for channel in range(4)]
                channel = max(range(4), key=lambda item: ranges[item])
                score = ranges[channel] * sum(colors[color] for color in box)
                candidates.append((score, index, channel))
            if not candidates:
                break
            score, index, channel = max(candidates)
            box = sorted(boxes.pop(index), key=lambda color: color[channel])
            half_weight = sum(colors[color] for color in box) / 2
            weight = 0
            split = 1
            for position, color in enumerate(box[:-1], 1):
                weight += colors[color]
                split = position
                if weight >= half_weight:
                    break
            boxes.extend((box[:split], box[split:]))
        palette = []
        indices_by_color = {}
        for index, box in enumerate(boxes):
            total = sum(colors[color] for color in box)
            representative = tuple(round(sum(color[channel] * colors[color] for color in box) / total) for channel in range(4))
            palette.append(representative)
            for color in box:
                indices_by_color[color] = index

    indices = bytearray(indices_by_color[tuple(rgba[offset:offset + 4])] for offset in range(0, len(rgba), 4))
    if bit_depth == 4:
        raster = bytearray((len(indices) + 1) // 2)
        for index, value in enumerate(indices):
            raster[index // 2] |= value << ((index % 2) * 4)
    else:
        raster = indices
        if platform == "PS2":
            for index, value in enumerate(raster):
                raster[index] = (value & ~0x18) | ((value & 0x08) << 1) | ((value & 0x10) >> 1)

    palette_bytes = b"".join(bytes(color) for color in palette)
    palette_bytes += bytes((color_limit - len(palette)) * 4)
    padding = bytes(align(len(raster), 16) - len(raster))
    return bytes(raster) + padding + palette_bytes


def build_ps2_texture_container(texture_records, texture_format="XTX") -> bytes:
    if len(texture_records) > 4096:
        raise ValueError("Too many textures for a Leeds texture dictionary")
    data = bytearray(0x44)
    data[:4] = b"xet\0"
    if str(texture_format).upper() == "XTX":
        struct.pack_into("<I", data, 0x20, 0xCC06)
        struct.pack_into("<IIIII", data, 0x30, 0xCCCCCCCC, 0xCCCCCCCC, 0, 0x001D3B1C, 0x07070040)
    else:
        struct.pack_into("<I", data, 0x20, 0x8606)
        struct.pack_into("<IIII", data, 0x30, 1, 0x0012FD70, 0x3B5, 0x0012FDB8)
    struct.pack_into("<II", data, 0x28, 0x28, 0x28)

    raster_offsets = []
    for name, width, height, raster, depth in texture_records:
        data.extend(bytes(align(len(data), 16) - len(data)))
        raster_offsets.append(len(data))
        data.extend(raster)

    node_offsets = []
    for record in texture_records:
        data.extend(bytes(align(len(data), 16) - len(data)))
        node_offsets.append(len(data))
        data.extend(bytes(0x60))

    header_offsets = []
    for index, (name, width, height, raster, depth) in enumerate(texture_records):
        data.extend(bytes(align(len(data), 16) - len(data)))
        header_offsets.append(len(data))
        transfer = (0x00450000 | (width // 2)) if depth == 4 else (0x00250000 | width)
        flags = power_of_two_log2(width) | (power_of_two_log2(height) << 6) | (depth << 12) | (1 << 20)
        data.extend(struct.pack("<IIII", 0, transfer, raster_offsets[index], flags))

    relocations = [0x28, 0x2C]
    if texture_records:
        struct.pack_into("<II", data, 0x28, node_offsets[-1] + 8, node_offsets[0] + 8)
    for index, (name, width, height, raster, depth) in enumerate(texture_records):
        base = node_offsets[index]
        previous_slot = node_offsets[index - 1] + 8 if index else 0x28
        next_slot = node_offsets[index + 1] + 8 if index + 1 < len(node_offsets) else 0x28
        struct.pack_into("<IIII", data, base, header_offsets[index], 0x20, previous_slot, next_slot)
        encoded_name = name.encode("ascii", "replace")[:63]
        data[base + 0x10:base + 0x10 + len(encoded_name)] = encoded_name
        relocations.extend((base, base + 4, base + 8, base + 12))
    relocations.extend(offset + 8 for offset in header_offsets)
    if texture_records:
        data.extend(bytes(align(len(data), 16) - len(data)))
    relocation_offset = len(data)
    for field_offset in relocations:
        data.extend(struct.pack("<I", field_offset))
    logical_end = len(data)
    struct.pack_into("<IIIII", data, 0x08, logical_end, relocation_offset, relocation_offset, len(relocations), 0)
    data.extend(bytes(align(logical_end, 2048) - logical_end))
    return bytes(data)


def build_leeds_texture_container(images: Iterable[bpy.types.Image], platform: str = "PS2", bit_depth="AUTO", texture_format="XTX") -> bytes:
    platform = str(platform or "PS2").upper().strip()
    if platform not in {"PS2", "PSP"}:
        platform = "PS2"

    texture_records = []
    for image in images:
        width, height, rgba = image_to_rgba8(image, platform)
        depth = resolve_texture_depth(image, bit_depth)
        raster = quantize_texture_rgba(rgba, depth, platform)
        texture_records.append((clean_texture_name(image.name), width, height, raster, depth))

    if platform == "PS2":
        return build_ps2_texture_container(texture_records, texture_format)

    if not texture_records:
        raise ValueError("No image textures are available to export")

    header_size = 0x50
    cursor = header_size
    raster_offsets = []
    for _name, _width, _height, rgba, _depth in texture_records:
        cursor = align(cursor, 16)
        raster_offsets.append(cursor)
        cursor += len(rgba)

    cursor = align(cursor, 16)
    node_offsets = []
    for _record in texture_records:
        node_offsets.append(cursor)
        cursor += 0x50

    cursor = align(cursor, 16)
    texture_header_offsets = []
    for _record in texture_records:
        texture_header_offsets.append(cursor)
        cursor += 0x10

    data = bytearray(cursor)
    data[0:4] = b"xet\0"
    struct.pack_into("<I", data, 0x04, 2 if platform == "PS2" else 1)
    struct.pack_into("<I", data, 0x08, len(data))
    struct.pack_into("<I", data, 0x0C, 0)
    struct.pack_into("<I", data, 0x10, 0)
    struct.pack_into("<I", data, 0x14, 0)
    struct.pack_into("<I", data, 0x20, 0x00008606 if platform == "PS2" else 0)

    if platform == "PS2":
        for index, value in enumerate((0x00000001, 0x0012FD70, 0x000003B5, 0x0012FDB8)):
            struct.pack_into("<I", data, 0x30 + index * 4, value)

    first_slot = node_offsets[0] + 8
    last_slot = node_offsets[-1] + 8
    struct.pack_into("<I", data, 0x28, first_slot)
    struct.pack_into("<I", data, 0x2C, last_slot)

    for index, (name, width, height, rgba, depth) in enumerate(texture_records):
        raster_offset = raster_offsets[index]
        node_offset = node_offsets[index]
        texture_header_offset = texture_header_offsets[index]
        data[raster_offset:raster_offset + len(rgba)] = rgba

        previous_slot = node_offsets[index - 1] + 8 if index > 0 else 0
        if index + 1 < len(texture_records):
            next_slot = node_offsets[index + 1] + 8
        else:
            next_slot = 0x28 if platform == "PS2" else 0

        struct.pack_into("<IIII", data, node_offset, texture_header_offset, 0, next_slot, previous_slot)
        encoded_name = name.encode("ascii", "replace")[:63]
        data[node_offset + 0x10:node_offset + 0x10 + len(encoded_name)] = encoded_name
        data[node_offset + 0x10 + len(encoded_name)] = 0

        width_pow2 = power_of_two_log2(width)
        height_pow2 = power_of_two_log2(height)
        if platform == "PS2":
            flags = (
                (width_pow2 & 0x3F)
                | ((height_pow2 & 0x3F) << 6)
                | ((depth & 0x3F) << 12)
                | ((1 & 0x0F) << 20)
            )
            struct.pack_into("<IIII", data, texture_header_offset, 0, 0, raster_offset, flags)
        else:
            struct.pack_into(
                "<IIHBBBBH",
                data,
                texture_header_offset,
                0,
                raster_offset,
                0,
                width_pow2,
                height_pow2,
                depth,
                1,
                0,
            )

    return bytes(data)


def export_leeds_texture_container(filepath: str, images: Iterable[bpy.types.Image], platform: str = "PS2", bit_depth="AUTO") -> int:
    image_list = list(images)
    texture_format = os.path.splitext(filepath)[1].lstrip(".").upper() or "XTX"
    payload = build_leeds_texture_container(image_list, platform=platform, bit_depth=bit_depth, texture_format=texture_format)
    with open(filepath, "wb") as output_file:
        output_file.write(payload)
    return len(image_list)
