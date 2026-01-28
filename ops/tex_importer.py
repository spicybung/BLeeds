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

import os
from typing import List, Dict, Tuple, Optional

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
)


def decode_chk_to_blender_images(
    input_path: str,
    platform: str = 'auto',
    prefix: str = '',
) -> List[bpy.types.Image]:
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file '{input_path}' does not exist")
    with open(input_path, 'rb') as f:
        data = f.read()
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
    visited: set[int] = set()
    textures: List[Tuple[str, int, object]] = []
    base = slot_base_from_slot_ptr(first_slot)
    last_base = slot_base_from_slot_ptr(last_slot) if last_slot else None
    while True:
        if base in visited:
            break
        visited.add(base)
        cinfo = parse_container(data, base)
        if not cinfo:
            break
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
    for i in range(len(offsets)):
        start = offsets[i]
        if i + 1 < len(offsets):
            end = offsets[i + 1]
        else:
            glob_candidates = [hdr['glob1'], hdr['glob2'], hdr['coll_size'], len(data)]
            end_candidates = [ec for ec in glob_candidates if ec > start]
            end = min(end_candidates) if end_candidates else len(data)
        block_sizes.append(max(0, end - start))
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
        img.pixels = pixels
        blender_images.append(img)
    return blender_images


###############################################################################
# Blender import operator and add‑on registration
###############################################################################


