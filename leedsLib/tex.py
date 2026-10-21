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
import struct
import zlib
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Sequence

import numpy as np


def read_u32(data: bytes, offset: int) -> int:

    return struct.unpack_from('<I', data, offset)[0]

def read_cstr(data: bytes, offset: int, length: int) -> str:

    s = data[offset:offset + length]
    end = s.find(b'\0')
    if end == -1:
        end = len(s)
    return s[:end].decode('ascii', 'replace')

@dataclass
class Mh2TexEntry:
    name: str
    descriptor_offset: int
    width: int
    height: int
    bits_per_pixel: int
    pitch_or_linear_size: int
    flags: int
    mipmap_count: int
    data_offset: int
    data_size: int
    uses_cutout_alpha: bool
    dds_data: bytes


def decompress_mh2_tex_container(data: bytes) -> bytes:
    if data[:4] == b"TCDT":
        return data
    if data[:4] != b"Z2HM":
        raise ValueError("Not a Manhunt 2 TEX container")
    if len(data) < 9:
        raise ValueError("Truncated Manhunt 2 Z2HM TEX container")
    decoded = zlib.decompress(data[8:])
    if decoded[:4] != b"TCDT":
        raise ValueError("Z2HM data did not decode to a TCDT texture container")
    return decoded


def is_mh2_tex_data(data: bytes) -> bool:
    if not data:
        return False
    if data[:4] == b"TCDT":
        return True
    if data[:4] != b"Z2HM":
        return False
    try:
        return decompress_mh2_tex_container(data)[:4] == b"TCDT"
    except Exception:
        return False


def dxt1_uses_cutout_alpha(dds_data: bytes) -> bool:
    if len(dds_data) < 0x80 or dds_data[:4] != b"DDS ":
        return False
    if dds_data[0x54:0x58] != b"DXT1":
        return False

    payload = memoryview(dds_data)[0x80:]
    for block_offset in range(0, len(payload) - 7, 8):
        color0, color1, indices = struct.unpack_from("<HHI", payload, block_offset)
        if color0 > color1:
            continue
        for pixel_index in range(16):
            if ((indices >> (pixel_index * 2)) & 0x03) == 0x03:
                return True
    return False


def parse_mh2_tex_entries(data: bytes) -> List[Mh2TexEntry]:
    decoded = decompress_mh2_tex_container(data)
    if len(decoded) < 0x30:
        raise ValueError("Manhunt 2 TEX header is truncated")

    signature, const_number, file_size, index_table_offset, index_table_offset2, num_index, zero1, zero2, texture_count, first_texture_offset, last_texture_offset, zero3 = struct.unpack_from(
        "<4s11I", decoded, 0
    )
    if signature != b"TCDT":
        raise ValueError("Unsupported Manhunt 2 TEX signature")
    if const_number != 1:
        raise ValueError("Unsupported Manhunt 2 TEX header version")
    if texture_count > 65536:
        raise ValueError("Unreasonable Manhunt 2 TEX texture count")

    entries: List[Mh2TexEntry] = []
    normalized_names = set()
    current_offset = int(first_texture_offset)
    visited = set()

    for texture_index in range(int(texture_count)):
        if current_offset in visited:
            break
        visited.add(current_offset)
        if current_offset < 0 or current_offset + 0x70 > len(decoded):
            raise ValueError("Manhunt 2 TEX entry offset is outside the decoded file")

        next_offset = read_u32(decoded, current_offset + 0x00)
        name = read_cstr(decoded, current_offset + 0x08, 0x20).strip()
        descriptor_width = read_u32(decoded, current_offset + 0x48)
        descriptor_height = read_u32(decoded, current_offset + 0x4C)
        bits_per_pixel = read_u32(decoded, current_offset + 0x50)
        descriptor_pitch_or_linear_size = read_u32(decoded, current_offset + 0x54)
        flags = struct.unpack_from("<H", decoded, current_offset + 0x58)[0]
        mipmap_count = decoded[current_offset + 0x5C]
        data_offset = read_u32(decoded, current_offset + 0x60)
        data_size = read_u32(decoded, current_offset + 0x68)

        if not name:
            name = "MH2_Texture_{:03d}".format(texture_index)
        if data_size <= 0 or data_offset < 0 or data_offset + data_size > len(decoded):
            raise ValueError("Invalid Manhunt 2 TEX DDS range for {!r}".format(name))

        dds_data = decoded[data_offset:data_offset + data_size]
        if dds_data[:4] != b"DDS ":
            raise ValueError("Manhunt 2 TEX entry {!r} does not contain a DDS payload".format(name))
        if len(dds_data) < 0x80 or read_u32(dds_data, 0x04) != 124:
            raise ValueError("Manhunt 2 TEX entry {!r} has a truncated DDS header".format(name))

        height = read_u32(dds_data, 0x0C)
        width = read_u32(dds_data, 0x10)
        pitch_or_linear_size = read_u32(dds_data, 0x14)
        dds_mipmap_count = read_u32(dds_data, 0x1C)
        if width <= 0 or height <= 0 or width > 16384 or height > 16384:
            raise ValueError("Invalid Manhunt 2 TEX DDS dimensions for {!r}".format(name))
        if descriptor_width and descriptor_width != width:
            descriptor_width = width
        if descriptor_height and descriptor_height != height:
            descriptor_height = height
        if descriptor_pitch_or_linear_size and descriptor_pitch_or_linear_size != pitch_or_linear_size:
            descriptor_pitch_or_linear_size = pitch_or_linear_size
        if dds_mipmap_count:
            mipmap_count = int(dds_mipmap_count)

        normalized_name = os.path.splitext(os.path.basename(name.replace("\\", "/")))[0].casefold()
        if normalized_name in normalized_names:
            raise ValueError("Manhunt 2 TEX contains duplicate texture name {!r}".format(name))
        normalized_names.add(normalized_name)

        entries.append(Mh2TexEntry(
            name=name,
            descriptor_offset=int(current_offset),
            width=int(width),
            height=int(height),
            bits_per_pixel=int(bits_per_pixel),
            pitch_or_linear_size=int(pitch_or_linear_size),
            flags=int(flags),
            mipmap_count=int(mipmap_count),
            data_offset=int(data_offset),
            data_size=int(data_size),
            uses_cutout_alpha=dxt1_uses_cutout_alpha(dds_data),
            dds_data=bytes(dds_data),
        ))

        if texture_index + 1 >= int(texture_count):
            break
        if next_offset == 0 or next_offset == current_offset:
            break
        if next_offset < 0x30 or next_offset + 0x70 > len(decoded):
            raise ValueError("Manhunt 2 TEX descriptor chain points outside the decoded file")
        current_offset = int(next_offset)

    if len(entries) != int(texture_count):
        raise ValueError(
            "Manhunt 2 TEX declared {} textures but {} entries were readable".format(
                int(texture_count), len(entries)
            )
        )
    return entries

def unswizzlePspRows(source: bytes, row_stride: int, height: int) -> bytes:
    if row_stride <= 0 or row_stride % 16 or height <= 0:
        raise ValueError("Invalid PSP texture row size")
    columns = np.arange(row_stride, dtype=np.int64)
    rows = np.arange(height, dtype=np.int64)[:, None]
    addresses = ((rows // 8) * (row_stride // 16) + columns // 16) * 128
    addresses += (rows % 8) * 16 + columns % 16
    if int(addresses.max()) >= len(source):
        raise ValueError("PSP texture pixels are truncated")
    pixels = np.frombuffer(source, dtype=np.uint8)
    return pixels[addresses].tobytes()


def unswizzle_psp_4bit(src: bytes, w: int, h: int, buffer_stride: int = 0) -> bytes:
    row_size = (int(w) + 1) // 2
    row_stride = max(16, row_size, int(buffer_stride))
    pixels = unswizzlePspRows(src, row_stride, int(h))
    return np.frombuffer(pixels, dtype=np.uint8).reshape(h, row_stride)[:, :row_size].tobytes()


def unswizzle_psp_8bit(src: bytes, w: int, h: int, buffer_stride: int = 0) -> bytes:
    row_stride = max(16, int(w), int(buffer_stride))
    pixels = unswizzlePspRows(src, row_stride, int(h))
    return np.frombuffer(pixels, dtype=np.uint8).reshape(h, row_stride)[:, :w].tobytes()


def unswizzle_psp_32bit(src: bytes, w: int, h: int, buffer_stride: int = 0) -> bytes:
    row_size = int(w) * 4
    row_stride = max(16, row_size, int(buffer_stride))
    pixels = unswizzlePspRows(src, row_stride, int(h))
    return np.frombuffer(pixels, dtype=np.uint8).reshape(h, row_stride)[:, :row_size].tobytes()


def expand_nibbles_lo_first(data: bytes) -> np.ndarray:

    out = np.empty(len(data) * 2, dtype=np.uint8)
    for i, value in enumerate(data):
        out[2 * i] = value & 0x0F
        out[2 * i + 1] = (value >> 4) & 0x0F
    return out

def swizzle_ps2(x: int, y: int, logw: int) -> int:

    nx = (x & 7) ^ (((y >> 1) ^ (y >> 2)) << 2)
    nx = (nx & 7) | ((x >> 1) & ~7)
    ny = (y & 1) | ((y >> 1) & ~1)
    n = ((y >> 1) & 1) | (((x >> 3) & 1) << 1)
    return n | (nx << 2) | (ny << (logw - 1 + 2))

def unswizzle_ps2_indices(idx: np.ndarray, w: int, h: int) -> np.ndarray:

    total = w * h
    dst = np.empty(total, dtype=np.uint8)

    logw = 0
    tmp = 1
    while tmp < w:
        tmp <<= 1
        logw += 1
    for y in range(h):
        for x in range(w):
            dst[y * w + x] = idx[swizzle_ps2(x, y, logw) % len(idx)]
    return dst

def convert_clut_ps2(data: np.ndarray) -> None:

    mapping = [0x00, 0x10, 0x08, 0x18]
    for i in range(len(data)):
        v = int(data[i])
        data[i] = (v & ~0x18) | mapping[(v & 0x18) >> 3]

@dataclass
class PspTexHeader:

    unknown0: int
    raster_offset: int
    swizzle_width: int
    width_pow2: int
    height_pow2: int
    bpp: int
    mip_count: int
    tail: int

    @property
    def width(self) -> int:
        return 1 << self.width_pow2 if self.width_pow2 < 32 else 0

    @property
    def height(self) -> int:
        return 1 << self.height_pow2 if self.height_pow2 < 32 else 0

@dataclass
class Ps2TexHeader:

    reserved0: int
    reserved1: int
    raster_offset: int
    flags: int

    @property
    def swizzle_mask(self) -> int:
        return self.flags & 0xFF

    @property
    def mip_count(self) -> int:
        return (self.flags >> 8) & 0xF

    @property
    def bpp(self) -> int:
        return (self.flags >> 14) & 0x3F

    @property
    def width_pow2(self) -> int:
        return (self.flags >> 26) & 0x3F

    @property
    def height_pow2(self) -> int:
        return (self.flags >> 20) & 0x3F

    @property
    def width(self) -> int:
        return 1 << self.width_pow2 if self.width_pow2 < 32 else 0

    @property
    def height(self) -> int:
        return 1 << self.height_pow2 if self.height_pow2 < 32 else 0

def decode_ps2_runtime_flags(flags: int) -> Optional[Tuple[int, int, int, int, int, int]]:
    width_pow2 = int(flags) & 0x3F
    height_pow2 = (int(flags) >> 6) & 0x3F
    bpp = (int(flags) >> 12) & 0x3F
    unknown_bits = (int(flags) >> 18) & 0x03
    mip_count = (int(flags) >> 20) & 0x0F
    swizzle_mask = (int(flags) >> 24) & 0xFF
    if width_pow2 >= 13 or height_pow2 >= 13 or bpp not in (4, 8, 16, 32):
        return None
    width = 1 << width_pow2
    height = 1 << height_pow2
    if width <= 0 or height <= 0 or width > 4096 or height > 4096:
        return None
    return width, height, bpp, mip_count, swizzle_mask, unknown_bits


def validate_ps2_stories_runtime_container(data: bytes) -> Tuple[bool, List[str]]:
    messages: List[str] = []
    if len(data) < 0x24 or data[:3] != b"xet":
        return True, messages
    if read_u32(data, 0x20) not in (0x8606, 0xCC06):
        return True, messages
    if len(data) < 0x4C:
        return False, ["PS2 texture dictionary is missing its collection header or relocations"]

    logical_end = read_u32(data, 0x08)
    relocation_offset = read_u32(data, 0x0C)
    relocation_count = read_u32(data, 0x14)
    relocation_end = relocation_offset + relocation_count * 4
    if relocation_count < 2 or relocation_offset < 0x44 or relocation_end > len(data):
        return False, ["PS2 texture relocation table is invalid"]
    if logical_end != relocation_end or read_u32(data, 0x10) != relocation_offset:
        messages.append("PS2 texture logical end or relocation pointer is inconsistent")
    if len(data) % 2048:
        messages.append("PS2 texture dictionary is not padded to a 2048-byte sector")
    relocations = [read_u32(data, relocation_offset + index * 4) for index in range(relocation_count)]
    if relocations[:2] != [0x28, 0x2C]:
        messages.append("PS2 relocation table must start with the tail/head fields")

    current_slot = read_u32(data, 0x2C)
    previous_slot = 0x28
    visited = set()
    nodes = []
    headers = []
    raster_offsets = []
    expected_relocations = [0x28, 0x2C]
    while current_slot != 0x28:
        if current_slot in visited or len(visited) >= 4096:
            messages.append("PS2 texture list has a cycle or too many entries")
            break
        visited.add(current_slot)
        base = current_slot - 8
        if base < 0x50 or base + 0x60 > relocation_offset:
            messages.append("PS2 texture node is outside the object range")
            break
        if read_u32(data, base + 8) != previous_slot:
            messages.append("PS2 texture previous link is inconsistent")
        if read_u32(data, base + 4) != 0x20:
            messages.append("PS2 texture collection back-pointer must be 0x20")
        header = read_u32(data, base)
        if header < 0x50 or header + 16 > relocation_offset:
            messages.append("PS2 texture raster header is invalid")
            break
        fields = decode_ps2_runtime_flags(read_u32(data, header + 12))
        if fields is None:
            messages.append("PS2 texture flags do not use the runtime bit layout")
        else:
            width, height, depth, mip_count, swizzle_mask, unknown_bits = fields
            expected_transfer = (0x450000 | (width // 2)) if depth == 4 else (0x250000 | width) if depth == 8 else 0
            transfer = read_u32(data, header + 4)


            valid_runtime_bits = (transfer >> 28) in (0, 0xC)
            if depth in (4, 8) and (transfer & 0x00FFFFFF != expected_transfer or not valid_runtime_bits):
                messages.append("PS2 indexed texture transfer word is inconsistent")
        raster = read_u32(data, header + 8)
        if raster < 0x50 or raster >= base:
            messages.append("PS2 texture raster overlaps or follows the nodes")
        nodes.append(base)
        headers.append(header)
        raster_offsets.append(raster)
        expected_relocations.extend((base, base + 4, base + 8, base + 12))
        previous_slot = current_slot
        current_slot = read_u32(data, base + 12)
    if read_u32(data, 0x28) != previous_slot:
        messages.append("PS2 texture collection tail is inconsistent")
    expected_relocations.extend(header + 8 for header in headers)
    if relocations != expected_relocations:
        messages.append("PS2 texture relocation fields do not match the runtime pointers")
    if nodes and (max(raster_offsets) >= min(nodes) or max(node + 0x60 for node in nodes) > min(headers)):
        messages.append("PS2 texture objects do not follow raster/node/header order")
    return not messages, messages


def parse_psp_header(data: bytes, offset: int) -> Optional[PspTexHeader]:

    if offset <= 0 or offset + 16 > len(data):
        return None
    hdr = data[offset:offset + 16]
    if len(hdr) < 16:
        return None
    unknown0 = read_u32(hdr, 0)
    raster_offset = read_u32(hdr, 4)
    swizzle_width = struct.unpack_from('<H', hdr, 8)[0]
    width_pow2 = hdr[10]
    height_pow2 = hdr[11]
    bpp = hdr[12]
    mip_count = hdr[13]
    tail = struct.unpack_from('<H', hdr, 14)[0]
    width = 1 << width_pow2 if width_pow2 < 32 else 0
    height = 1 << height_pow2 if height_pow2 < 32 else 0
    if width == 0 or height == 0 or width > 4096 or height > 4096:
        return None
    if bpp not in (4, 8, 16, 32) or mip_count > 8:
        return None
    if raster_offset <= 0 or raster_offset >= len(data):
        return None
    row_size = (width * bpp + 7) // 8
    if swizzle_width and (swizzle_width < row_size or max(16, swizzle_width) % 16):
        return None
    return PspTexHeader(
        unknown0=unknown0,
        raster_offset=raster_offset,
        swizzle_width=swizzle_width,
        width_pow2=width_pow2,
        height_pow2=height_pow2,
        bpp=bpp,
        mip_count=mip_count,
        tail=tail,
    )

def parse_ps2_header(data: bytes, offset: int) -> Optional[Ps2TexHeader]:

    if offset <= 0 or offset + 16 > len(data):
        return None
    hdr = data[offset:offset + 16]
    if len(hdr) < 16:
        return None
    reserved0 = read_u32(hdr, 0)
    reserved1 = read_u32(hdr, 4)
    raster_offset = read_u32(hdr, 8)
    flags = read_u32(hdr, 12)

    w_pow2_std = (flags >> 26) & 0x3F
    h_pow2_std = (flags >> 20) & 0x3F
    bpp_std = (flags >> 14) & 0x3F
    width_std = 1 << w_pow2_std if w_pow2_std < 32 else 0
    height_std = 1 << h_pow2_std if h_pow2_std < 32 else 0

    use_alt = False

    w_pow2_alt = flags & 0x3F
    h_pow2_alt = (flags >> 6) & 0x3F
    bpp_alt = (flags >> 12) & 0x3F
    alt_unknown = (flags >> 18) & 0x3
    mip_alt = (flags >> 20) & 0xF
    swizzle_alt = (flags >> 24) & 0xFF
    width_alt = 1 << w_pow2_alt if w_pow2_alt < 32 else 0
    height_alt = 1 << h_pow2_alt if h_pow2_alt < 32 else 0

    std_invalid = (width_std == 0 or height_std == 0 or width_std > 4096 or height_std > 4096)
    alt_valid_dims = (width_alt > 0 and height_alt > 0 and width_alt <= 4096 and height_alt <= 4096)
    alt_bpp_reasonable = bpp_alt in (4, 8, 16, 32)

    if (
        std_invalid or
        (width_std <= 8 and height_std <= 8) or
        (bpp_std not in (4, 8, 16, 32))
    ) and alt_valid_dims and alt_bpp_reasonable:
        use_alt = True
    if use_alt:

        canonical_flags = (
            (swizzle_alt & 0xFF)
            | ((mip_alt & 0xF) << 8)
            | ((alt_unknown & 0x3) << 12)
            | ((bpp_alt & 0x3F) << 14)
            | ((h_pow2_alt & 0x3F) << 20)
            | ((w_pow2_alt & 0x3F) << 26)
        )
        flags = canonical_flags
        width_std = width_alt
        height_std = height_alt

    if width_std == 0 or height_std == 0 or width_std > 4096 or height_std > 4096:
        return None
    return Ps2TexHeader(
        reserved0=reserved0,
        reserved1=reserved1,
        raster_offset=raster_offset,
        flags=flags,
    )

def slot_base_from_slot_ptr(slot_ptr: int) -> int:
    if slot_ptr <= 0:
        return 0
    return max(0, slot_ptr - 8)

def parse_container(data: bytes, base: int) -> Optional[Dict[str, int]]:

    if base < 0 or base + 80 > len(data):
        return None
    tex_off = read_u32(data, base + 0x00)
    coll_off = read_u32(data, base + 0x04)
    next_slot = read_u32(data, base + 0x08)
    prev_slot = read_u32(data, base + 0x0C)
    name = read_cstr(data, base + 0x10, 64)
    return {
        'base': base,
        'tex_off': tex_off,
        'coll_off': coll_off,
        'next_slot': next_slot,
        'prev_slot': prev_slot,
        'name': name,
    }

def getPspRasterLayout(header: PspTexHeader) -> Dict[str, object]:
    if header.bpp not in (4, 8, 16, 32):
        raise ValueError("Unsupported PSP texture depth: %d" % header.bpp)
    if not 0 <= header.mip_count <= 8:
        raise ValueError("Invalid PSP mipmap count: %d" % header.mip_count)
    levels = []
    width = header.width
    height = header.height
    offset = int(header.raster_offset)
    buffer_stride = int(header.swizzle_width)
    for level in range(max(1, header.mip_count)):
        row_size = (width * header.bpp + 7) // 8
        if buffer_stride:
            row_stride = max(16, row_size, buffer_stride >> level)
            if row_stride % 16:
                raise ValueError("Invalid PSP texture row size: %d" % row_stride)
        else:
            row_stride = row_size
        size = row_stride * height
        levels.append({'offset': offset, 'size': size, 'width': width,
                       'height': height, 'row_stride': row_stride})
        offset += size
        width = max(1, width // 2)
        height = max(1, height // 2)
    palette_size = (1 << header.bpp) * 4 if header.bpp in (4, 8) else 0
    if palette_size and not buffer_stride:
        offset = (offset + 15) & ~15
    return {'levels': levels, 'palette_offset': offset,
            'palette_size': palette_size,
            'size': offset + palette_size - header.raster_offset}


def decodePspDirectColor(pixels: np.ndarray, header: PspTexHeader) -> np.ndarray:
    if header.bpp == 32:
        return pixels.reshape(header.height, header.width, 4).copy()
    values = np.frombuffer(pixels.tobytes(), dtype='<u2').reshape(header.height, header.width)
    color_format = header.tail & 0x0F00
    rgba = np.empty((header.height, header.width, 4), dtype=np.uint8)
    if color_format == 0x0200:
        rgba[:, :, 0] = (values & 31) * 255 // 31
        rgba[:, :, 1] = ((values >> 5) & 63) * 255 // 63
        rgba[:, :, 2] = ((values >> 11) & 31) * 255 // 31
        rgba[:, :, 3] = 255
    elif color_format in (0x0100, 0x0A00):
        rgba[:, :, 0] = (values & 31) * 255 // 31
        rgba[:, :, 1] = ((values >> 5) & 31) * 255 // 31
        rgba[:, :, 2] = ((values >> 10) & 31) * 255 // 31
        rgba[:, :, 3] = np.where(values & 0x8000, 255, 0) if color_format == 0x0100 else 255
    elif color_format == 0x0300:
        for channel in range(4):
            rgba[:, :, channel] = ((values >> (channel * 4)) & 15) * 17
    else:
        raise ValueError("Unsupported PSP 16-bit colour format: 0x%04X" % header.tail)
    return rgba


def decode_psp_texture(
    data: bytes,
    thdr: PspTexHeader,
    block_size: int,
    palette_override: Optional[Sequence[Tuple[int, int, int, int]]] = None,
    mip_level: int = 0,
) -> Optional[np.ndarray]:
    layout = getPspRasterLayout(thdr)
    levels = layout['levels']
    if not 0 <= mip_level < len(levels):
        raise ValueError("PSP mipmap level is out of range")
    level = levels[mip_level]
    block_end = min(len(data), thdr.raster_offset + int(block_size))
    last_level = levels[-1]
    pixel_end = int(last_level['offset']) + int(last_level['size'])
    required_end = (int(layout['palette_offset']) + int(layout['palette_size'])
                    if palette_override is None else pixel_end)
    if block_size <= 0 or thdr.raster_offset <= 0 or required_end > block_end:
        raise ValueError("PSP texture pixels or palette are truncated")
    width = int(level['width'])
    height = int(level['height'])
    row_stride = int(level['row_stride'])
    offset = int(level['offset'])
    raw = data[offset:offset + int(level['size'])]
    if thdr.swizzle_width:
        raw = unswizzlePspRows(raw, row_stride, height)
    rows = np.frombuffer(raw, dtype=np.uint8).reshape(height, row_stride)
    if thdr.bpp in (16, 32):
        row_size = width * thdr.bpp // 8
        level_header = PspTexHeader(thdr.unknown0, offset, 0,
                                   width.bit_length() - 1, height.bit_length() - 1,
                                   thdr.bpp, 1, thdr.tail)
        return decodePspDirectColor(rows[:, :row_size].copy(), level_header)
    if thdr.bpp == 4:
        indices = np.empty((height, row_stride * 2), dtype=np.uint8)
        indices[:, 0::2] = rows & 15
        indices[:, 1::2] = rows >> 4
        indices = indices[:, :width]
    else:
        indices = rows[:, :width]
    if palette_override is None:
        palette_start = int(layout['palette_offset'])
        palette_end = palette_start + int(layout['palette_size'])
        palette = np.frombuffer(data[palette_start:palette_end], dtype=np.uint8).reshape(-1, 4)
    else:
        palette = np.asarray(palette_override, dtype=np.uint8)
        if palette.ndim != 2 or palette.shape[1] != 4:
            raise ValueError("PSP palette must contain RGBA colours")
    if len(palette) <= int(indices.max()):
        raise ValueError("PSP texture uses a missing palette colour")
    return palette[indices].copy()


def decode_ps2_texture(
    data: bytes,
    thdr: Ps2TexHeader,
    block_size: int,
    palette_override: Optional[Sequence[Tuple[int, int, int, int]]] = None,
) -> Optional[np.ndarray]:
    w = thdr.width
    h = thdr.height
    bpp = thdr.bpp
    offset = thdr.raster_offset
    if w <= 0 or h <= 0 or offset <= 0:
        return None
    pixel_count = w * h
    if bpp == 4:
        base_bytes = (pixel_count + 1) // 2
    elif bpp == 8:
        base_bytes = pixel_count
    elif bpp == 16:
        base_bytes = pixel_count * 2
    elif bpp == 32:
        base_bytes = pixel_count * 4
    else:
        return None
    if offset + base_bytes > len(data):
        return None
    raw = data[offset:offset + base_bytes]
    pal = palette_override
    if bpp in (4, 8) and pal is None:
        pal_len = 16 if bpp == 4 else 256
        pal_bytes_len = pal_len * 4
        pal_start = offset + block_size - pal_bytes_len
        pal_end = pal_start + pal_bytes_len
        if 0 <= pal_start < pal_end <= len(data):
            pal_bytes = data[pal_start:pal_end]
            pal = []
            for i in range(0, len(pal_bytes), 4):
                r = pal_bytes[i]
                g = pal_bytes[i + 1]
                b = pal_bytes[i + 2]
                a = pal_bytes[i + 3]
                a = int(a * 255 / 128)
                if a > 255:
                    a = 255
                pal.append((r, g, b, a))
        else:
            pal = None
    if bpp == 4:
        idx = np.empty(pixel_count, dtype=np.uint8)
        for i in range(pixel_count // 2):
            byte = raw[i]
            idx[i * 2] = byte & 0x0F
            idx[i * 2 + 1] = byte >> 4
        if pixel_count % 2:
            idx[-1] = raw[pixel_count // 2] & 0x0F
        if thdr.swizzle_mask & 1:
            idx = unswizzle_ps2_indices(idx, w, h)
    elif bpp == 8:

        idx = np.frombuffer(raw, dtype=np.uint8).copy()
        if thdr.swizzle_mask & 1:
            idx = unswizzle_ps2_indices(idx, w, h)
        convert_clut_ps2(idx)
    elif bpp == 32:
        if thdr.swizzle_mask & 1:
            unswizzled = unswizzle_psp_32bit(raw, w, h)
        else:
            unswizzled = raw
        rgba = np.frombuffer(unswizzled, dtype=np.uint8).reshape((h, w, 4)).copy()
        alpha = rgba[:, :, 3].astype(np.int32) * 255 // 128
        alpha = np.clip(alpha, 0, 255).astype(np.uint8)
        rgba[:, :, 3] = alpha
        return rgba
    else:
        return None
    rgba = np.empty((h, w, 4), dtype=np.uint8)
    if pal:
        for i in range(pixel_count):
            y = i // w
            x = i % w
            col = pal[int(idx[i]) % len(pal)]
            rgba[y, x] = col
    else:
        max_idx = int(idx.max()) if len(idx) > 0 else 0
        scale = 255.0 / max_idx if max_idx > 0 else 0.0
        for i in range(pixel_count):
            y = i // w
            x = i % w
            val = int(idx[i] * scale + 0.5)
            rgba[y, x] = (val, val, val, 255)
    return rgba
