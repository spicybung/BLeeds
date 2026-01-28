# BLeeds - Scripts for working with R* Leeds (GTA Stories, Chinatown Wars, Manhunt 2, etc) formats in Blender
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

import struct
import math

from dataclasses import dataclass

import numpy as np

import bpy
from mathutils import Matrix

from pathlib import Path 

import zlib
from typing import List, Tuple, Dict, Optional

#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
#   This script is for .wrld's - the file format for GTA Stories world sectors      #
#   TODO: .BSP worlds maybe?                                                        # 
#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
# - Script resources:
# • https://gtamods.com/wiki/IMG_archive
# • https://web.archive.org/web/20180402031926/http://gtamodding.ru/wiki/IMG
# • https://web.archive.org/web/20180406213309/http://gtamodding.ru/wiki/LVZ
# • https://web.archive.org/web/20180729202923/http://gtamodding.ru/wiki/WRLD (*Russian*)
# • https://web.archive.org/web/20180729204205/http://gtamodding.ru/wiki/CHK (*Russian* - WRLD textures)
# • https://github.com/aap/librwgta/blob/master/tools/storiesview/worldstream.cpp
# • https://web-archive-org.translate.goog/web/20180810183857/http://gtamodding.ru/wiki/LVZ?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (*English*)
# • https://web-archive-org.translate.goog/web/20180807031320/http://www.gtamodding.ru/wiki/IMG?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (ditto)
# • https://web-archive-org.translate.goog/web/20180729204205/http://gtamodding.ru/wiki/CHK?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (ditto - WRLD textures)
# - Mod resources/cool stuff:
# • https://gtaforums.com/topic/285544-gtavcslcs-modding/ (includes unimg.exe for Stories)
# • https://github.com/electronicarts/RenderWare3Docs/blob/master/whitepapers/worlds.pdf (Leeds Worlds are based on RW Worlds)
# • https://lcsteam.net/community/forum/index.php/topic,337.msg9335.html#msg9335 (RW 3.7/4.0, .MDL's, .WRLD's, .BSP's... )
# • https://vk.com/video143954957_456239416 (Russian - Leeds Worlds explained)


#######################################################
def dbg(msg: str) -> None:

    try:
        print(msg)
    except Exception:
        pass


def safe_decompress(data: bytes) -> bytes:

    if not data:
        return data
    if len(data) >= 2 and data[0] == 0x78 and data[1] in (0x01, 0x9C, 0xDA):
        try:
            return zlib.decompress(data)
        except Exception:
            pass
    for wbits in (16 + zlib.MAX_WBITS, -zlib.MAX_WBITS):
        try:
            return zlib.decompress(data, wbits)
        except Exception:
            continue
    return data

@dataclass
class MDLMaterial:
    texture_id: int
    tri_strip_size: int
    backface_cull: bool
    u_scale: float
    v_scale: float
    flags2: int
    bbox6_i16: Tuple[int, int, int, int, int, int]

@dataclass
class MDLMaterialList:
    count: int
    size_bytes: int
    materials: List[MDLMaterial]
    bytes_read: int
    aa_tail: bytes
    next_off: int

@dataclass
class TriStrip:
    count: int
    verts: List[Tuple[float, float, float]]
    uvs: List[Tuple[float, float]]
    cols_raw_u16: List[int]
    cols_rgba4444: List[Tuple[int, int, int, int]]
    material_res_index: int = -1
    u_scale: float = 1.0
    v_scale: float = 1.0

@dataclass
class MDLStripGroup:
    strips: List[TriStrip]
    bytes_read: int
    start_off: int
    end_off: int

class MDLParser:

    # VIF
    UNPACK = 0x6C018000
    STMASK = 0x20000000
    STROW  = 0x30000000
    MSCAL  = 0x14000006

    def __init__(self, mdl_bytes: bytes, stem: str, use_swizzle: bool = True, debug_print: bool = True):
        self.decomp = safe_decompress(mdl_bytes)
        self.stem = stem
        self.use_swizzle = use_swizzle
        self.debug_print = debug_print
        self.material_by_res_index: Dict[int, bpy.types.Material] = {}

    def read_vec3_i16_norm(self, buf: bytes, off: int) -> Tuple[float, float, float]:
        x = read_i16(buf, off + 0)
        y = read_i16(buf, off + 2)
        z = read_i16(buf, off + 4)
        return (x / 32767.5, y / 32767.5, z / 32767.5)

    def read_uv_u8_div128(self, buf: bytes, off: int) -> Tuple[float, float]:
        u = buf[off + 0]
        v = buf[off + 1]
        return (u / 128.0, v / 128.0)

    def decode_rgba4444(self, v16: int) -> Tuple[int, int, int, int]:
        r = ((v16 >> 12) & 0xF) * 17
        g = ((v16 >> 8) & 0xF) * 17
        b = ((v16 >> 4) & 0xF) * 17
        a = (v16 & 0xF) * 17
        return (r, g, b, a)

    def find_unpack_near(self, buf: bytes, off: int, window: int = 8) -> int:
        n = len(buf)
        start = max(0, off - window)
        end = min(n, off + window + 4)
        for p in range(start, end):
            if (p & 3) == 0 and p + 4 <= n and read_u32(buf, p) == self.UNPACK:
                return p
        raise ValueError(f"UNPACK header not found near 0x{off:08X}")

    def scan_aa_tail(self, off: int) -> Tuple[bytes, int]:
        lvz = self.decomp
        n = len(lvz)
        i = off
        while i < n and lvz[i] == 0xAA:
            i += 1
        return (lvz[off:i], i)

    def parse_mdl_material_list(self, base: int) -> MDLMaterialList:
        lvz = self.decomp
        n = len(lvz)
        if base + 4 > n:
            raise ValueError("MDL material list header out of range.")
        count = read_u16(lvz, base + 0)
        size_bytes = read_u16(lvz, base + 2)
        off = base + 4
        materials: List[MDLMaterial] = []
        limit = min(n, base + 4 + size_bytes)
        for mi in range(count):
            need = off + 22
            if need > n:
                break
            if off >= limit:
                break
            texture_id = read_u16(lvz, off + 0)
            tri_raw    = read_u16(lvz, off + 2)
            u_half     = read_u16(lvz, off + 4)
            v_half     = read_u16(lvz, off + 6)
            flags2     = read_u16(lvz, off + 8)
            b0 = read_i16(lvz, off + 10)
            b1 = read_i16(lvz, off + 12)
            b2 = read_i16(lvz, off + 14)
            b3 = read_i16(lvz, off + 16)
            b4 = read_i16(lvz, off + 18)
            b5 = read_i16(lvz, off + 20)
            tri_strip_size = (tri_raw & 0x7FFF)
            backface_cull  = (tri_raw & 0x8000) != 0
            u_scale = half_to_float(u_half)
            v_scale = half_to_float(v_half)
            materials.append(MDLMaterial(
                texture_id=texture_id,
                tri_strip_size=tri_strip_size,
                backface_cull=backface_cull,
                u_scale=u_scale,
                v_scale=v_scale,
                flags2=flags2,
                bbox6_i16=(b0, b1, b2, b3, b4, b5),
            ))
            off += 22

        aa_tail, new_off = self.scan_aa_tail(off)
        next_guess = (new_off & ~3)
        return MDLMaterialList(
            count=count,
            size_bytes=size_bytes,
            materials=materials,
            bytes_read=off - base,
            aa_tail=aa_tail,
            next_off=next_guess,
        )

    def parse_one_batch(self, buf: bytes, pos: int) -> Tuple[TriStrip, int]:

        n = len(buf)

        pos = self.find_unpack_near(buf, (pos & ~3))
        if pos + 20 > n:
            raise ValueError("VIF batch header truncated.")

        nvert_all = read_u32(buf, pos + 16) & 0x7FFF
        if nvert_all == 0:
            raise ValueError("Zero‑length VIF batch.")
        w = pos + 20
        if read_u32(buf, w) != self.STMASK:
            raise ValueError(f"Expected STMASK before positions at 0x{w:08X}")
        w += 8
        if read_u32(buf, w) != self.STROW:
            raise ValueError(f"Expected STROW before positions at 0x{w:08X}")
        w += 20
        header_pos = read_u32(buf, w)

        if (header_pos & 0xFF004000) != 0x79000000:
            raise ValueError(f"Unexpected positions header 0x{header_pos:08X} at 0x{w:08X}")
        w += 4
        need_bytes_pos = nvert_all * 6
        if w + need_bytes_pos > n:
            raise ValueError("Position payload truncated.")
        verts: List[Tuple[float, float, float]] = []

        for i in range(nvert_all):
            off = w + i * 6
            verts.append(self.read_vec3_i16_norm(buf, off))
        w += need_bytes_pos
        w = (w + 3) & ~3
        if read_u32(buf, w) != self.STMASK:
            raise ValueError(f"Expected STMASK before texcoords at 0x{w:08X}")
        w += 8
        if read_u32(buf, w) != self.STROW:
            raise ValueError(f"Expected STROW before texcoords at 0x{w:08X}")
        w += 20
        h_uv = read_u32(buf, w)
        if (h_uv & 0xFF004000) != 0x76004000:
            raise ValueError(f"Unexpected UV header 0x{h_uv:08X} at 0x{w:08X}")
        w += 4
        need_bytes_uv = nvert_all * 2
        if w + need_bytes_uv > n:
            raise ValueError("UV payload truncated.")
        uvs: List[Tuple[float, float]] = []
        for i in range(nvert_all):
            off = w + i * 2
            uvs.append(self.read_uv_u8_div128(buf, off))
        w += need_bytes_uv
        w = (w + 3) & ~3
        h_col = read_u32(buf, w)
        if (h_col & 0xFF004000) != 0x6F000000:
            raise ValueError(f"Unexpected colour header 0x{h_col:08X} at 0x{w:08X}")
        w += 4
        need_bytes_col = nvert_all * 2
        if w + need_bytes_col > n:
            raise ValueError("Colour payload truncated.")
        cols_raw_u16: List[int] = []
        cols_rgba4444: List[Tuple[int, int, int, int]] = []
        for i in range(nvert_all):
            c16 = read_u16(buf, w + i * 2)
            cols_raw_u16.append(c16)
            cols_rgba4444.append(self.decode_rgba4444(c16))
        w += need_bytes_col
        w = (w + 3) & ~3
        if read_u32(buf, w) != self.MSCAL:
            if w + 4 <= n and read_u32(buf, w + 4) == self.MSCAL:
                w += 4
            else:
                raise ValueError(f"MSCAL 0x14000006 missing around 0x{w:08X}")
        w += 4
        while w + 4 <= n and read_u32(buf, w) == 0:
            w += 4
        strip = TriStrip(
            count=nvert_all,
            verts=verts,
            uvs=uvs,
            cols_raw_u16=cols_raw_u16,
            cols_rgba4444=cols_rgba4444,
        )
        return strip, w

    def parse_mdl_stream_after_list(self, start_off: int, max_groups: int = 4096) -> Tuple[List[MDLStripGroup], int]:

        buf = self.decomp
        groups: List[MDLStripGroup] = []
        n = len(buf)
        try:
            off = self.find_unpack_near(buf, start_off)
        except Exception:
            return groups, start_off
        for _ in range(max_groups):
            if off >= n:
                break
            try:
                strip, next_off = self.parse_one_batch(buf, off)
            except Exception:
                break
            groups.append(MDLStripGroup(strips=[strip], bytes_read=(next_off - off), start_off=off, end_off=next_off))
            try:
                off = self.find_unpack_near(buf, next_off)
            except Exception:
                off = next_off
                break
        return groups, off

    def assign_materials_by_strip_bytes(self, mlist: MDLMaterialList, groups: List[MDLStripGroup]) -> None:

        if not mlist.materials or not groups:
            return
        flat: List[Tuple[TriStrip, int, int]] = []
        gstart = min(g.start_off for g in groups)
        for g in groups:
            for s in g.strips:
                rel_start = g.start_off - gstart
                rel_end = g.end_off - gstart
                flat.append((s, rel_start, rel_end))
        flat.sort(key=lambda item: item[1])
        m_idx = 0
        m = mlist.materials[m_idx]
        m_window = m.tri_strip_size
        acc_len = 0
        for s, rel_start, rel_end in flat:
            batch_len = rel_end - rel_start
            if batch_len <= 0:
                continue
            while m_idx < len(mlist.materials) and acc_len >= m_window and m_window > 0:
                m_idx += 1
                if m_idx < len(mlist.materials):
                    m = mlist.materials[m_idx]
                    m_window = m.tri_strip_size
                    acc_len = 0
            if m_idx >= len(mlist.materials):
                break
            s.material_res_index = m.texture_id
            s.u_scale = m.u_scale if m.u_scale != 0.0 else 1.0
            s.v_scale = m.v_scale if m.v_scale != 0.0 else 1.0
            if s.uvs:
                s.uvs = [(u * s.u_scale, v * s.v_scale) for (u, v) in s.uvs]
            acc_len += batch_len

    def triangulate_strip_indices(self, local_count: int) -> List[Tuple[int, int, int]]:

        tris: List[Tuple[int, int, int]] = []
        for i in range(local_count - 2):
            if i & 1:
                tris.append((i + 1, i, i + 2))
            else:
                tris.append((i, i + 1, i + 2))
        return tris

    def build_mesh_from_groups(self, res_index: int, groups: List[MDLStripGroup]) -> Tuple[Optional[bpy.types.Object], List[Tuple[int, int, int]]]:

        if not groups:
            return None, []
        vertices: List[Tuple[float, float, float]] = []
        uvs_list: List[Tuple[float, float]] = []
        faces: List[Tuple[int, int, int]] = []
        face_ranges: List[Tuple[int, int, int]] = []
        for g in groups:
            for s in g.strips:
                k = min(len(s.verts), len(s.uvs), s.count)
                if k < 3:
                    continue
                base = len(vertices)
                vertices.extend(s.verts[:k])
                uvs_list.extend(s.uvs[:k])
                tri_list = self.triangulate_strip_indices(k)
                poly_start = len(faces)
                for a, b, c in tri_list:
                    faces.append((base + a, base + b, base + c))
                poly_count = len(tri_list)
                face_ranges.append((poly_start, poly_count, s.material_res_index))
        if not faces or not vertices:
            return None, []
        mesh_name = f"{self.stem}_mdl{res_index}"
        me = bpy.data.meshes.new(mesh_name)
        me.from_pydata(vertices, [], faces)
        me.use_auto_smooth = True
        me.validate(clean_customdata=False)
        me.update()
        if uvs_list:
            uv_layer = me.uv_layers.new(name="UVMap")
            uv_data = uv_layer.data
            for poly in me.polygons:
                li = poly.loop_start
                for j, vi in enumerate(poly.vertices):
                    if vi < len(uvs_list):
                        u, v = uvs_list[vi]
                        uv_data[li + j].uv = (u, v)
        obj = bpy.data.objects.new(mesh_name, me)
        resid_to_slot: Dict[int, int] = {}
        for fr in face_ranges:
            mat_resid = fr[2]
            if mat_resid not in resid_to_slot:
                mat = self.material_by_res_index.get(mat_resid)
                if mat is not None:
                    obj.data.materials.append(mat)
                    resid_to_slot[mat_resid] = len(obj.data.materials) - 1
        if face_ranges:
            polys = obj.data.polygons
            for (pstart, pcount, mat_resid) in face_ranges:
                slot = resid_to_slot.get(mat_resid)
                if slot is not None:
                    for pi in range(pstart, pstart + pcount):
                        if 0 <= pi < len(polys):
                            polys[pi].material_index = slot
        return obj, face_ranges

    def count_vif_commands(self) -> Tuple[int, int]:

        buf = self.decomp
        n = len(buf)
        unpack_count = 0
        mscal_count = 0
        for i in range(0, n - 4, 4):
            cmd = read_u32(buf, i)
            if cmd == self.UNPACK:
                unpack_count += 1
            elif cmd == self.MSCAL:
                mscal_count += 1
        return unpack_count, mscal_count

# -----------------------------------------------------------------------------
# Helper functions for reading binary data
# -----------------------------------------------------------------------------

def read_u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def read_i16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<h", data, offset)[0]


def read_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def read_f32(data: bytes, offset: int) -> float:
    return struct.unpack_from("<f", data, offset)[0]


def half_to_float(h: int) -> float:
    """Convert a 16‑bit half precision float into a Python float."""
    return float(np.frombuffer(struct.pack("<H", h & 0xFFFF), dtype=np.float16)[0])


def hexdump_bytes(b: bytes, max_len: int = 32) -> str:
    """Return a string of hex bytes for logging."""
    n = min(len(b), max_len)
    return " ".join(f"{x:02X}" for x in b[:n])


# -----------------------------------------------------------------------------
# Image decoding
# -----------------------------------------------------------------------------
def expand_nibbles_lo_first(b: bytes) -> np.ndarray:
    """Expand 4bpp (low nibble first) into 8bpp index array."""
    arr = np.frombuffer(b, dtype=np.uint8)
    lo = arr & 0x0F
    hi = arr >> 4
    return np.vstack([lo, hi]).T.reshape(-1)


def log2_pow2(n: int) -> int:
    l = 0
    v = max(1, n)
    while (1 << l) < v:
        l += 1
    return l


def swizzle_ps2_addr(x: int, y: int, logw: int) -> int:

    X3 = (x >> 3) & 1
    Y1 = (y >> 1) & 1
    Y2 = (y >> 2) & 1
    x ^= ((Y1 ^ Y2) << 2)
    nx = (x & 7) | ((x >> 1) & ~7)
    ny = (y & 1) | ((y >> 1) & ~1)
    n = (Y1) | (X3 << 1)
    return (n | (nx << 2) | (ny << (logw - 1 + 2)))


def unswizzle8_ps2_linearized(src: np.ndarray, w: int, h: int) -> np.ndarray:

    dst = np.empty(w * h, dtype=np.uint8)
    logw = log2_pow2(w)
    for y in range(h):
        for x in range(w):
            s = swizzle_ps2_addr(x, y, logw)
            dst[y * w + x] = src[s % src.size]
    return dst


def apply_ps2_alpha_scale(palette_rgba: np.ndarray, do_scale: bool) -> np.ndarray:
    if not do_scale:
        return palette_rgba
    pal = palette_rgba.copy()
    a = pal[:, 3].astype(np.uint16)
    a = (a * 255 + 64) // 128
    pal[:, 3] = np.clip(a, 0, 255).astype(np.uint8)
    return pal


def nearest_pow2(n: int) -> int:

    if n <= 1:
        return 1
    if (n & (n - 1)) == 0:
        return n
    lower = 1 << (n.bit_length() - 1)
    upper = lower << 1
    return upper if (n - lower) > (upper - n) else lower


def resize_indices_to_dims(idx2d: np.ndarray, new_w: int, new_h: int) -> np.ndarray:

    h, w = idx2d.shape
    if new_h < h:
        idx2d = idx2d[:new_h, :]
        h = new_h
    if new_w < w:
        idx2d = idx2d[:, :new_w]
        w = new_w
    if new_h > h:
        pad_h = new_h - h
        idx2d = np.pad(idx2d, ((0, pad_h), (0, 0)), mode='edge')
        h = new_h
    if new_w > w:
        pad_w = new_w - w
        idx2d = np.pad(idx2d, ((0, 0), (0, pad_w)), mode='edge')
    return idx2d


def choose_single_size_for_4bpp(index_len_bytes: int) -> tuple:

    total_pixels = index_len_bytes * 2
    if total_pixels <= 0:
        raise ValueError("Index length is zero; cannot choose size.")
    dim_pool = [16, 32, 64, 128, 256, 512, 1024]
    candidates = []
    for w in dim_pool:
        if total_pixels % w != 0:
            continue
        h = total_pixels // w
        if h in dim_pool:
            candidates.append((w, h))
    if not candidates:
        for w in dim_pool:
            if total_pixels % w == 0:
                h = total_pixels // w
                if h > 0:
                    candidates.append((w, h))
    if not candidates:
        raise ValueError(f"No dimension pair matches pixel count {total_pixels}.")
    squares = [(w, h) for (w, h) in candidates if w == h]
    if squares:
        squares.sort(key=lambda wh: abs(wh[0] - int(math.sqrt(total_pixels))))
        return squares[0]
    candidates.sort(key=lambda wh: (abs(wh[0] - wh[1]), -wh[0]))
    return candidates[0]


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
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (300, 0)
    principled = nt.nodes.new("ShaderNodeBsdfPrincipled"); principled.location = (0, 0)
    tex = nt.nodes.new("ShaderNodeTexImage"); tex.location = (-300, 0); tex.image = img
    nt.links.new(tex.outputs["Color"], principled.inputs["Base Color"])
    if img.has_data and "Alpha" in tex.outputs and "Alpha" in principled.inputs:
        nt.links.new(tex.outputs["Alpha"], principled.inputs["Alpha"])
        mat.blend_method = 'BLEND'
    nt.links.new(principled.outputs["BSDF"], out.inputs["Surface"])
    return mat


# -----------------------------------------------------------------------------
# Data classes for WRLD parsing
# -----------------------------------------------------------------------------

@dataclass
class WorldHeader:
    magic: bytes
    wrld_type: int
    total_size: int
    global0: int
    global1: int
    global_count: int
    continuation: int
    reserved: int


@dataclass
class ExtendedHeader:
    res_table_addr: int
    res_count: int
    unknown_count: int
    sky_offsets: list


@dataclass
class ResourceEntry:
    res_id: int
    table_index: int
    offset: int
    length: int
    a16: int
    b16: int
    a32: int
    b32: int
    kind: str = ""
    ref_addr: int = -1
    image: bpy.types.Image | None = None
    material: bpy.types.Material | None = None
    tex_size: tuple | None = None
    note: str = ""
    mdl_info: dict | None = None


def parse_world_header(data: bytes) -> WorldHeader:
    return WorldHeader(
        magic=data[0:4],
        wrld_type=read_u32(data, 4),
        total_size=read_u32(data, 8),
        global0=read_u32(data, 12),
        global1=read_u32(data, 16),
        global_count=read_u32(data, 20),
        continuation=read_u32(data, 24),
        reserved=read_u32(data, 28),
    )


def parse_extended_header(data: bytes) -> ExtendedHeader:
    res_table_addr = read_u32(data, 0x20)
    res_count = read_u16(data, 0x24)
    unknown_count = read_u16(data, 0x26)
    sky_offsets = [read_u32(data, 0x28 + i * 4) for i in range(8)]
    return ExtendedHeader(res_table_addr, res_count, unknown_count, sky_offsets)


def parse_resource_table(data: bytes, header: WorldHeader, ext: ExtendedHeader) -> list:

    n = len(data)
    base = ext.res_table_addr
    rows = ext.res_count
    raw = []
    for i in range(rows):
        off = base + i * 8
        if off + 8 > n:
            break
        res_id = read_u32(data, off)
        res_off = read_u32(data, off + 4)
        raw.append((i, res_id, res_off))
    valid = [r for r in raw if 0 < r[2] < n]
    sorted_offs = sorted(valid, key=lambda r: r[2])
    entries = []
    for idx, (table_idx, res_id, res_off) in enumerate(sorted_offs):
        if idx + 1 < len(sorted_offs):
            next_off = sorted_offs[idx + 1][2]
        else:
            if 0 < header.global0 < n and header.global0 > res_off:
                next_off = header.global0
            else:
                next_off = n
        length = max(0, min(next_off, n) - res_off)
        if res_off + 8 <= n:
            a16 = read_u16(data, res_off)
            b16 = read_u16(data, res_off + 2)
            a32 = read_u32(data, res_off)
            b32 = read_u32(data, res_off + 4)
        else:
            a16 = b16 = a32 = b32 = 0
        entries.append(
            ResourceEntry(
                res_id=res_id,
                table_index=table_idx,
                offset=res_off,
                length=length,
                a16=a16,
                b16=b16,
                a32=a32,
                b32=b32,
            )
        )
    return entries


def classify_entries(entries: list) -> None:
    """Classify each entry as MDL or TEX_REF according to heuristics."""
    for e in entries:
        if e.b16 == 0 and e.a16 != 0:
            e.kind = "TEX_REF"
            e.ref_addr = e.a32
            e.note = "tex_ref"
        else:
            e.kind = "MDL"
            e.note = "mdl_or_other"
            e.mdl_info = None


def decode_textures_for_entries(data: bytes, header: WorldHeader, entries: list, stem: str) -> None:

    return None

def get_or_create_collection(name: str) -> bpy.types.Collection:

    dbg(f"[world] get_or_create_collection called for '{name}', but this function is now in world_importer")
    return None

# -----------------------------------------------------------------------------
# MDL object builder
# -----------------------------------------------------------------------------

def build_mdl_objects(entries: list, resources: list, stem: str, collection: bpy.types.Collection = None, max_pairs_per_mdl: int = 4) -> None:

    dbg("[world] build_mdl_objects stub invoked; use world_importer for object creation")
    return None


# -----------------------------------------------------------------------------
# MDL geometry builder
# -----------------------------------------------------------------------------

def build_mdl_geometry(entries: list, data: bytes, stem: str, collection: bpy.types.Collection = None) -> None:

    dbg("[world] build_mdl_geometry stub invoked; use world_importer for mesh construction")
    return None

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
        hexd = hexdump_bytes(data[start:slice_end], max_len=slice_end - start)

        count = 0
        if e.b16 and e.b16 % 4 == 0:
            count = e.b16 // 4
        elif e.a16 and e.a16 % 4 == 0:
            count = e.a16 // 4

        if count <= 0:
            count = max_pairs
        count = min(count, max_pairs)
        pairs = []
 
        for i in range(count):
            pos = start + 4 + i * 4
            if pos + 4 > n or pos + 4 > end:
                break
            p0 = read_u16(data, pos)
            p1 = read_u16(data, pos + 2)
            pairs.append((p0, p1))
        e.mdl_info = {
            "a16": e.a16,
            "b16": e.b16,
            "a32": e.a32,
            "b32": e.b32,
            "hexdump": hexd,
            "pairs": pairs,
        }

#######################################################
def log_and_import(path: str, decode_textures: bool = True, write_log: bool = True, build_models: bool = True) -> None:

    data = Path(path).read_bytes()
    header = parse_world_header(data)
    ext = parse_extended_header(data)
    entries = parse_resource_table(data, header, ext)
    classify_entries(entries)
    stem = Path(path).stem

    if decode_textures:
        decode_textures_for_entries(data, header, entries, stem)

    analyze_mdl_entries(data, entries)
    if build_models:
        try:
            build_mdl_geometry(entries, data, stem)
        except Exception as ex:
            dbg(f"[mdl] error while building MDL geometry: {ex}")

    lines = []
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
            if e.tex_size:
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
