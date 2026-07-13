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

import math
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import tex as leeds_tex

#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
# - Script resources:
# •
# - Mod resources/cool stuff:
# •


Z2HM_MAGIC = b"Z2HM"
DLRW_MAGIC = b"DLRW"
TCDT_MAGIC = b"TCDT"
PSP_RENDER_FLAGS = 0x115


def read_u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def read_i16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<h", data, offset)[0]


def read_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def read_f32(data: bytes, offset: int) -> float:
    return struct.unpack_from("<f", data, offset)[0]


def read_cstr(data: bytes, offset: int, max_length: int = 256) -> str:
    if offset < 0 or offset >= len(data):
        return ""
    end_limit = min(len(data), offset + max(1, int(max_length)))
    end = data.find(b"\0", offset, end_limit)
    if end < 0:
        end = end_limit
    return data[offset:end].decode("ascii", "replace")


def unwrap_z2hm(data: bytes) -> Tuple[bytes, bool, int]:
    """Return decompressed data, wrapper flag, and declared unpacked size."""
    if len(data) < 8 or data[:4] != Z2HM_MAGIC:
        return data, False, len(data)
    declared_size = read_u32(data, 4)
    payload = zlib.decompress(data[8:])
    if declared_size and len(payload) != declared_size:
        raise ValueError(
            "Z2HM size mismatch: declared %d bytes, decoded %d bytes"
            % (declared_size, len(payload))
        )
    return payload, True, declared_size


def load_resource_file(path: str) -> Tuple[bytes, bool, int]:
    return unwrap_z2hm(Path(path).read_bytes())


@dataclass
class RelocatableHeader:
    magic: str
    version: int
    total_size: int
    relocation_offset: int
    relocation_count: int
    wrapped_z2hm: bool = False
    packed_size: int = 0
    unpacked_size: int = 0


@dataclass
class BSPMaterialRecord:
    index: int
    name: str
    name_offset: int
    color_rgba: Tuple[int, int, int, int]
    flags: int


@dataclass
class BSPStripDescriptor:
    index: int
    vertex_start: int
    vertex_count: int
    material_index: int
    uv_scale_u: float
    uv_scale_v: float
    bbox_i16: Tuple[int, int, int, int, int, int, int, int]
    unknown_tail: Tuple[int, int]


@dataclass
class BSPVertex:
    position: Tuple[float, float, float]
    uv: Tuple[float, float]
    color: Tuple[int, int, int, int]
    raw_position: Tuple[int, int, int]
    raw_uv: Tuple[int, int]
    raw_color: int


@dataclass
class BSPGeometryBlock:
    file_offset: int
    size: int
    flags: int
    strip_count: int
    vertex_count: int
    bounds: Tuple[float, float, float, float]
    scale: Tuple[float, float, float]
    position: Tuple[float, float, float]
    vertex_buffer_offset: int
    unknown0: int
    unknown1: int
    unknown2: float
    strips: List[BSPStripDescriptor] = field(default_factory=list)
    vertices: List[BSPVertex] = field(default_factory=list)


@dataclass
class BSPWorld:
    header: RelocatableHeader
    root_offset: int
    material_table_offset: int
    materials: List[BSPMaterialRecord]
    geometry: List[BSPGeometryBlock]
    data: bytes
    collision_only: bool = False


@dataclass
class TCDTTextureRecord:
    index: int
    header_offset: int
    next_offset: int
    previous_offset: int
    name: str
    width: int
    height: int
    bits_per_pixel: int
    raster_format: int
    pixel_format: int
    mip_levels: int
    swizzle_mask: int
    p_pixel: int
    render_pass: int
    data_offset: int
    palette_offset: int
    unknown0: int
    unknown1: int


@dataclass
class TCDTDictionary:
    header: RelocatableHeader
    textures: List[TCDTTextureRecord]
    data: bytes


def parse_relocatable_header(
    data: bytes,
    expected_magic: bytes,
    wrapped_z2hm: bool = False,
    packed_size: int = 0,
) -> RelocatableHeader:
    if len(data) < 0x18:
        raise ValueError("Relocatable file is too small")
    if data[:4] != expected_magic:
        raise ValueError(
            "Unexpected magic %r; expected %r" % (data[:4], expected_magic)
        )
    version = read_u32(data, 4)
    total_size = read_u32(data, 8)
    relocation_offset = read_u32(data, 0x10)
    relocation_count = read_u32(data, 0x14)
    if total_size <= 0 or total_size > len(data):
        total_size = len(data)
    if relocation_offset < 0 or relocation_offset > len(data):
        raise ValueError("Relocation table offset is outside the file")
    if relocation_offset + relocation_count * 4 > len(data):
        raise ValueError("Relocation table is truncated")
    return RelocatableHeader(
        magic=expected_magic.decode("ascii", "replace"),
        version=version,
        total_size=total_size,
        relocation_offset=relocation_offset,
        relocation_count=relocation_count,
        wrapped_z2hm=bool(wrapped_z2hm),
        packed_size=int(packed_size),
        unpacked_size=len(data),
    )


def parse_bsp_materials(data: bytes) -> Tuple[int, List[BSPMaterialRecord]]:
    if len(data) < 0x5C:
        return 0, []
    table_offset = read_u32(data, 0x50)
    count = read_u32(data, 0x54)
    if count > 0x10000:
        raise ValueError("Unreasonable BSP material count: %d" % count)
    if table_offset <= 0 or table_offset + count * 12 > len(data):
        return table_offset, []
    materials: List[BSPMaterialRecord] = []
    for index in range(count):
        offset = table_offset + index * 12
        name_offset = read_u32(data, offset)
        color = tuple(int(v) for v in data[offset + 4:offset + 8])
        flags = read_u32(data, offset + 8)
        materials.append(
            BSPMaterialRecord(
                index=index,
                name=read_cstr(data, name_offset, 256),
                name_offset=name_offset,
                color_rgba=(color[1], color[2], color[3], color[0] if color[0] else 255),
                flags=flags,
            )
        )
    return table_offset, materials


def decode_rgba5551(value: int) -> Tuple[int, int, int, int]:
    r = (value & 0x1F) * 255 // 31
    g = ((value >> 5) & 0x1F) * 255 // 31
    b = ((value >> 10) & 0x1F) * 255 // 31
    a = 255 if (value & 0x8000) else 0
    return int(r), int(g), int(b), int(a)


def _geometry_header_at(data: bytes, offset: int) -> Optional[BSPGeometryBlock]:
    if offset < 0 or offset + 0x48 > len(data):
        return None
    values = struct.unpack_from("<4I4f3fi3fiIf", data, offset)
    size, flags, strip_count, unknown0 = values[:4]
    bounds = tuple(float(v) for v in values[4:8])
    scale = tuple(float(v) for v in values[8:11])
    vertex_count = int(values[11])
    position = tuple(float(v) for v in values[12:15])
    unknown1 = int(values[15])
    vertex_buffer_offset = int(values[16])
    unknown2 = float(values[17])

    if flags != PSP_RENDER_FLAGS:
        return None
    if strip_count <= 0 or strip_count > 4096:
        return None
    if vertex_count <= 0 or vertex_count > 10000000:
        return None
    expected_vertex_offset = 0x50 + strip_count * 0x20
    if vertex_buffer_offset != expected_vertex_offset:
        return None
    expected_size = vertex_buffer_offset + vertex_count * 10
    if size != expected_size or offset + size > len(data):
        return None
    if not all(math.isfinite(v) for v in bounds + scale + position + (unknown2,)):
        return None

    strips: List[BSPStripDescriptor] = []
    vertex_cursor = 0
    for strip_index in range(strip_count):
        descriptor_offset = offset + 0x50 + strip_index * 0x20
        if descriptor_offset + 0x20 > offset + vertex_buffer_offset:
            return None
        bbox_i16 = struct.unpack_from("<8h", data, descriptor_offset)
        vertex_count_for_strip = read_u16(data, descriptor_offset + 0x10)
        material_index = read_u16(data, descriptor_offset + 0x12)
        uv_scale_u = read_f32(data, descriptor_offset + 0x14)
        uv_scale_v = read_f32(data, descriptor_offset + 0x18)
        tail0 = read_u32(data, descriptor_offset + 0x1C)
        if vertex_count_for_strip <= 0:
            return None
        if not math.isfinite(uv_scale_u):
            return None
        # The beta PSP files use one encoded UV scale.  A zero second value
        # means the same scale is used for both axes.
        if not math.isfinite(uv_scale_v) or abs(uv_scale_v) < 1.0e-30:
            uv_scale_v = uv_scale_u
        strips.append(
            BSPStripDescriptor(
                index=strip_index,
                vertex_start=vertex_cursor,
                vertex_count=vertex_count_for_strip,
                material_index=material_index,
                uv_scale_u=uv_scale_u if abs(uv_scale_u) > 1.0e-30 else 1.0,
                uv_scale_v=uv_scale_v if abs(uv_scale_v) > 1.0e-30 else 1.0,
                bbox_i16=tuple(int(v) for v in bbox_i16),
                unknown_tail=(int(tail0), 0),
            )
        )
        vertex_cursor += vertex_count_for_strip
    if vertex_cursor != vertex_count:
        return None

    vertices: List[BSPVertex] = []
    vertex_buffer_absolute = offset + vertex_buffer_offset
    strip_index = 0
    active_strip = strips[0]
    for vertex_index in range(vertex_count):
        while (
            strip_index + 1 < len(strips)
            and vertex_index >= active_strip.vertex_start + active_strip.vertex_count
        ):
            strip_index += 1
            active_strip = strips[strip_index]
        vertex_offset = vertex_buffer_absolute + vertex_index * 10
        raw_u = int(data[vertex_offset])
        raw_v = int(data[vertex_offset + 1])
        raw_color = read_u16(data, vertex_offset + 2)
        raw_x = read_i16(data, vertex_offset + 4)
        raw_y = read_i16(data, vertex_offset + 6)
        raw_z = read_i16(data, vertex_offset + 8)
        x = raw_x / 32768.0 * scale[0] + position[0]
        y = raw_y / 32768.0 * scale[1] + position[1]
        z = raw_z / 32768.0 * scale[2] + position[2]
        u = raw_u / 128.0 * active_strip.uv_scale_u
        v = raw_v / 128.0 * active_strip.uv_scale_v
        vertices.append(
            BSPVertex(
                position=(x, y, z),
                uv=(u, v),
                color=decode_rgba5551(raw_color),
                raw_position=(raw_x, raw_y, raw_z),
                raw_uv=(raw_u, raw_v),
                raw_color=raw_color,
            )
        )

    return BSPGeometryBlock(
        file_offset=offset,
        size=size,
        flags=flags,
        strip_count=strip_count,
        vertex_count=vertex_count,
        bounds=bounds,
        scale=scale,
        position=position,
        vertex_buffer_offset=vertex_buffer_offset,
        unknown0=unknown0,
        unknown1=unknown1,
        unknown2=unknown2,
        strips=strips,
        vertices=vertices,
    )


def scan_psp_render_geometry(data: bytes) -> List[BSPGeometryBlock]:
    geometry: List[BSPGeometryBlock] = []
    seen_ranges: List[Tuple[int, int]] = []
    # Headers are four-byte aligned in the supplied PSP beta files.  The
    # strict size/strip/vertex validation makes this scan deterministic.
    for offset in range(0x20, max(0x20, len(data) - 0x48 + 1), 4):
        block = _geometry_header_at(data, offset)
        if block is None:
            continue
        block_end = block.file_offset + block.size
        overlaps = False
        for start, end in seen_ranges:
            if block.file_offset < end and block_end > start:
                overlaps = True
                break
        if overlaps:
            continue
        geometry.append(block)
        seen_ranges.append((block.file_offset, block_end))
    geometry.sort(key=lambda item: item.file_offset)
    return geometry


def parse_psp_bsp(path: str) -> BSPWorld:
    packed = Path(path).read_bytes()
    data, wrapped, _declared = unwrap_z2hm(packed)
    header = parse_relocatable_header(
        data,
        DLRW_MAGIC,
        wrapped_z2hm=wrapped,
        packed_size=len(packed),
    )
    material_table_offset, materials = parse_bsp_materials(data)
    root_offset = read_u32(data, 0x58) if len(data) >= 0x5C else 0
    geometry = scan_psp_render_geometry(data)
    return BSPWorld(
        header=header,
        root_offset=root_offset,
        material_table_offset=material_table_offset,
        materials=materials,
        geometry=geometry,
        data=data,
        collision_only=(len(geometry) == 0),
    )


def parse_tcdt(path: str) -> TCDTDictionary:
    packed = Path(path).read_bytes()
    data, wrapped, _declared = unwrap_z2hm(packed)
    header = parse_relocatable_header(
        data,
        TCDT_MAGIC,
        wrapped_z2hm=wrapped,
        packed_size=len(packed),
    )
    if len(data) < 0x30:
        raise ValueError("TCDT header is truncated")
    texture_count = read_u32(data, 0x20)
    current_offset = read_u32(data, 0x24)
    if texture_count > 0x10000:
        raise ValueError("Unreasonable TCDT texture count: %d" % texture_count)
    textures: List[TCDTTextureRecord] = []
    seen = set()
    for index in range(texture_count):
        if current_offset in seen:
            raise ValueError("TCDT texture linked list loops at 0x%X" % current_offset)
        if current_offset <= 0 or current_offset + 0x70 > len(data):
            raise ValueError("TCDT texture header %d is outside the file" % index)
        seen.add(current_offset)
        next_offset = read_u32(data, current_offset)
        previous_offset = read_u32(data, current_offset + 4)
        name = read_cstr(data, current_offset + 8, 64)
        width, height, bits_per_pixel, raster_format, pixel_format = struct.unpack_from(
            "<5I", data, current_offset + 0x48
        )
        mip_levels, swizzle_mask, p_pixel, render_pass = struct.unpack_from(
            "<4B", data, current_offset + 0x5C
        )
        data_offset = read_u32(data, current_offset + 0x60)
        palette_offset = read_u32(data, current_offset + 0x64)
        unknown0 = read_u32(data, current_offset + 0x68)
        unknown1 = read_u32(data, current_offset + 0x6C)
        if width <= 0 or height <= 0 or width > 8192 or height > 8192:
            raise ValueError("Invalid TCDT texture dimensions for %r" % name)
        textures.append(
            TCDTTextureRecord(
                index=index,
                header_offset=current_offset,
                next_offset=next_offset,
                previous_offset=previous_offset,
                name=name,
                width=width,
                height=height,
                bits_per_pixel=bits_per_pixel,
                raster_format=raster_format,
                pixel_format=pixel_format,
                mip_levels=mip_levels,
                swizzle_mask=swizzle_mask,
                p_pixel=p_pixel,
                render_pass=render_pass,
                data_offset=data_offset,
                palette_offset=palette_offset,
                unknown0=unknown0,
                unknown1=unknown1,
            )
        )
        current_offset = next_offset
    return TCDTDictionary(header=header, textures=textures, data=data)


def _read_palette_rgba(data: bytes, offset: int, color_count: int) -> np.ndarray:
    byte_count = color_count * 4
    if offset <= 0 or offset + byte_count > len(data):
        raise ValueError("TCDT palette is outside the file")
    return np.frombuffer(data[offset:offset + byte_count], dtype=np.uint8).reshape(color_count, 4).copy()


def decode_tcdt_texture(dictionary: TCDTDictionary, texture: TCDTTextureRecord) -> np.ndarray:
    data = dictionary.data
    width = texture.width
    height = texture.height
    bits_per_pixel = texture.bits_per_pixel
    padded_height = ((height + 7) // 8) * 8
    if bits_per_pixel == 4:
        byte_count = (max(width, 32) // 2) * padded_height
        if texture.data_offset <= 0 or texture.data_offset + byte_count > len(data):
            raise ValueError("TCDT 4-bit pixel data is outside the file")
        raw = data[texture.data_offset:texture.data_offset + byte_count]
        # The PSP TCDT raster is stored in 16x8 swizzled blocks.  The first
        # beta header contains stale non-zero flag bytes, so format identity
        # is more reliable than treating swizzle_mask as a boolean.
        raw = leeds_tex.unswizzle_psp_4bit(raw, width, height)
        packed = np.frombuffer(raw, dtype=np.uint8)
        indices = np.empty(width * height, dtype=np.uint8)
        indices[0::2] = packed & 0x0F
        indices[1::2] = packed >> 4
        palette = _read_palette_rgba(data, texture.palette_offset, 16)
        rgba = palette[indices.reshape(height, width)]
    elif bits_per_pixel == 8:
        byte_count = max(width, 16) * padded_height
        if texture.data_offset <= 0 or texture.data_offset + byte_count > len(data):
            raise ValueError("TCDT 8-bit pixel data is outside the file")
        raw = data[texture.data_offset:texture.data_offset + byte_count]
        raw = leeds_tex.unswizzle_psp_8bit(raw, width, height)
        indices = np.frombuffer(raw, dtype=np.uint8).reshape(height, width)
        palette = _read_palette_rgba(data, texture.palette_offset, 256)
        rgba = palette[indices]
    elif bits_per_pixel == 32:
        byte_count = max(width, 4) * 4 * padded_height
        if texture.data_offset <= 0 or texture.data_offset + byte_count > len(data):
            raise ValueError("TCDT 32-bit pixel data is outside the file")
        raw = data[texture.data_offset:texture.data_offset + byte_count]
        raw = leeds_tex.unswizzle_psp_32bit(raw, width, height)
        rgba = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 4).copy()
    else:
        raise ValueError(
            "Unsupported TCDT bit depth %d for texture %r"
            % (bits_per_pixel, texture.name)
        )
    return np.flipud(np.asarray(rgba, dtype=np.uint8).copy())


def normalize_asset_name(name: str) -> str:
    value = str(name or "").strip().replace("\\", "/")
    value = value.rsplit("/", 1)[-1]
    value = value.rsplit(".", 1)[0]
    return "".join(ch.lower() for ch in value if ch.isalnum() or ch == "_")


def find_companion_txd(bsp_path: str) -> Optional[Path]:
    path = Path(bsp_path)
    directory = path.parent
    wanted = path.stem.lower()
    exact = directory / (path.stem + ".TXD")
    if exact.is_file():
        return exact
    exact_lower = directory / (path.stem + ".txd")
    if exact_lower.is_file():
        return exact_lower
    candidates = []
    try:
        for item in directory.iterdir():
            if not item.is_file() or item.suffix.lower() != ".txd":
                continue
            stem_lower = item.stem.lower()
            if stem_lower == wanted:
                return item
            if stem_lower.startswith(wanted + "(") or stem_lower.startswith(wanted + " ("):
                candidates.append(item)
    except Exception:
        return None
    if candidates:
        candidates.sort(key=lambda item: (len(item.name), item.name.lower()))
        return candidates[0]
    return None


def find_best_companion_txd(
    bsp_path: str,
    material_names: List[str],
) -> Optional[Path]:
    """Find a PSP TCDT silently, preferring exact stem then material overlap."""
    exact = find_companion_txd(bsp_path)
    if exact is not None:
        return exact

    path = Path(bsp_path)
    wanted = {normalize_asset_name(name) for name in material_names}
    wanted.discard("")
    best_path: Optional[Path] = None
    best_score = 0
    try:
        candidates = sorted(
            (item for item in path.parent.iterdir() if item.is_file() and item.suffix.lower() == ".txd"),
            key=lambda item: item.name.lower(),
        )
    except Exception:
        return None
    for candidate in candidates:
        try:
            dictionary = parse_tcdt(str(candidate))
        except Exception:
            continue
        available = {normalize_asset_name(texture.name) for texture in dictionary.textures}
        available.discard("")
        score = len(wanted.intersection(available))
        if score > best_score:
            best_score = score
            best_path = candidate
    return best_path if best_score > 0 else None


def triangle_strip_faces(
    block: BSPGeometryBlock,
    epsilon: float = 1.0e-30,
) -> Tuple[List[Tuple[int, int, int]], List[int]]:
    faces: List[Tuple[int, int, int]] = []
    material_indices: List[int] = []
    positions = [vertex.position for vertex in block.vertices]
    for strip in block.strips:
        start = strip.vertex_start
        end = start + strip.vertex_count
        for local_index in range(2, strip.vertex_count):
            a = start + local_index - 2
            b = start + local_index - 1
            c = start + local_index
            if local_index & 1:
                a, b = b, a
            if a < start or c >= end:
                continue
            pa = positions[a]
            pb = positions[b]
            pc = positions[c]
            if pa == pb or pb == pc or pa == pc:
                continue
            ab = (pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2])
            ac = (pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2])
            cross = (
                ab[1] * ac[2] - ab[2] * ac[1],
                ab[2] * ac[0] - ab[0] * ac[2],
                ab[0] * ac[1] - ab[1] * ac[0],
            )
            area_squared = cross[0] * cross[0] + cross[1] * cross[1] + cross[2] * cross[2]
            if area_squared <= epsilon:
                continue
            faces.append((a, b, c))
            material_indices.append(int(strip.material_index))
    return faces, material_indices
