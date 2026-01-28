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
import zlib
import time
import math
import csv
import zipfile
import numpy as np

from pathlib import Path
from dataclasses import dataclass
from typing import Tuple, List, Dict, Optional

import bpy
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, BoolProperty
from mathutils import Matrix


#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
#   This script is for .IMG & .LVZ - file formats for Stories/MH2 worlds            #  
#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
# - Script resources:
# • https://gtamods.com/wiki/Relocatable_chunk (pre-process for included formats)
# • https://gtamods.com/wiki/Relocatable_chunk#:~:text=The%20different%20file%20types%20are%3A
# • https://gtamods.com/wiki/IMG_archive
# • https://web.archive.org/web/20180402031926/http://gtamodding.ru/wiki/IMG (*Russian*)
# • https://web.archive.org/web/20180406213309/http://gtamodding.ru/wiki/LVZ (*Russian*)
# • https://web.archive.org/web/20180729202923/http://gtamodding.ru/wiki/WRLD (*Russian*)
# • https://web.archive.org/web/20180729204205/http://gtamodding.ru/wiki/CHK (*Russian* - WRLD textures)
# • https://github.com/aap/librwgta/blob/master/tools/storiesview/worldstream.cpp
# • https://web-archive-org.translate.goog/web/20180810183857/http://gtamodding.ru/wiki/LVZ?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (*English*)
# • https://web-archive-org.translate.goog/web/20180807031320/http://www.gtamodding.ru/wiki/IMG?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (ditto)
# • https://web-archive-org.translate.goog/web/20180729204205/http://gtamodding.ru/wiki/CHK?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (ditto - WRLD textures)
# - Mod resources/cool stuff:
# • https://gtaforums.com/topic/285544-gtavcslcs-modding/ (includes old unimg.exe for GTA: Stories)
# • https://github.com/electronicarts/RenderWare3Docs/blob/master/whitepapers/worlds.pdf (Leeds Worlds are based on RW Worlds, which are based on .bsp)
# • https://developer.valvesoftware.com/wiki/BSP_(Quake) (see above)
# • https://lcsteam.net/community/forum/index.php/topic,337.msg9335.html#msg9335 (RW 3.7/4.0, .MDL's, .WRLD's, .BSP's... )
# • https://vk.com/video143954957_456239416 (*Russian* - how DTZ + LVZ + IMG work together in GTA: Stories by Daniil Sayanov)
# • https://www.gtagarage.com/mods/screen.php?s=60828 (converts LVZ + IMG to RW .DFF)


#######################################################
class DebugOut:
    def __init__(self, enable_console: bool, write_file: bool, file_path: Optional[str]):
        self.enable_console = enable_console
        self.write_file = write_file
        self.file_path = file_path
        self._buf: List[str] = []

    def log(self, msg: str):
        if self.enable_console:
            print(msg)
        if self.write_file:
            self._buf.append(msg)

    def flush(self):
        if not self.write_file or not self.file_path:
            return
        try:
            Path(self.file_path).write_text("\n".join(self._buf), encoding="utf-8")
        except Exception as e:
            print(f"[log] failed to write '{self.file_path}': {e}")

DEBUG: Optional[DebugOut] = None
def dbg(msg: str):
    if DEBUG is not None:
        DEBUG.log(msg)
    else:
        print(msg)

#######################################################
# Helpers shared by LVZ and IMG
#######################################################

def read_u32(b: bytes, o: int) -> int:
    return struct.unpack_from("<I", b, o)[0]
def read_u16(b: bytes, o: int) -> int:
    return struct.unpack_from("<H", b, o)[0]
def read_i16(b: bytes, o: int) -> int:
    return struct.unpack_from("<h", b, o)[0]

def align_up4(o: int) -> int:
    return (o + 3) & ~3
def align_down4(o: int) -> int:
    return (o) & ~3

def is_zlib(data: bytes) -> bool:
    return len(data) >= 2 and data[0] == 0x78 and data[1] in (0x01, 0x9C, 0xDA)

def safe_decompress(data: bytes) -> Tuple[bytes, bool]:
    if not data:
        return data, False
    if is_zlib(data):
        try:
            return zlib.decompress(data), True
        except Exception:
            pass
    for wbits in (16 + zlib.MAX_WBITS, -zlib.MAX_WBITS):
        try:
            return zlib.decompress(data, wbits), True
        except Exception:
            continue
    return data, False

def hexdump_bytes(b: bytes, max_len: int = 32) -> str:
    n = min(len(b), max_len)
    return " ".join(f"{x:02X}" for x in b[:n])

def half_to_float(h: int) -> float:
    return float(np.frombuffer(struct.pack('<H', h), dtype=np.float16)[0])

#######################################################
# LVZ data structures
#######################################################

@dataclass
class LVZMaster:
    magic: bytes
    type: int
    g0: int
    g1: int
    g1_dup: int
    count_like: int
    res_table_addr: int

@dataclass
class SlaveGroup:
    index: int
    addr: int
    tag: str
    total: int
    gcnt: int
    cont: int
    note: str

@dataclass
class MDLMaterial:
    texture_id: int           # map LVZ RES 
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

#######################################################
# LVZ responsibilities (master/slave/RES, TEX, MDL)
#######################################################

class read_lvz:
    UNPACK = 0x6C018000
    STMASK = 0x20000000
    STROW  = 0x30000000
    MSCAL  = 0x14000006

    def __init__(self, decomp_bytes: bytes, stem: str, use_swizzle: bool, debug_print: bool):
        self.decomp = decomp_bytes
        self.stem = stem
        self.use_swizzle = use_swizzle
        self.debug_print = debug_print
        self.material_by_res_index: Dict[int, bpy.types.Material] = {}

    #######################################################
    # Master/slave/resource table
    #######################################################

    def parse_master_header(self) -> LVZMaster:
        lvz = self.decomp
        if len(lvz) < 0x24:
            raise ValueError("LVZ smaller than 0x24")
        magic = lvz[0:4]
        _type = read_u32(lvz, 0x04)
        g0 = read_u32(lvz, 0x08)
        g1 = read_u32(lvz, 0x0C)
        g1d = read_u32(lvz, 0x10)
        cnt = read_u32(lvz, 0x14)
        rtab = read_u32(lvz, 0x20)
        return LVZMaster(magic, _type, g0, g1, g1d, cnt, rtab)

    def _peek_global32(self, addr: int):
        lvz = self.decomp
        n = len(lvz)
        if addr < 0 or addr + 32 > n:
            return ("(oob)", {}, "out-of-bounds")
        blk = lvz[addr:addr+32]
        tag = blk[0:4]
        info = {}
        note = ""
        try:
            tag_str = tag.decode("ascii", errors="replace")
        except Exception:
            tag_str = tag.hex()
        if tag == b"DLRW":
            wrld_type = read_u32(blk, 0x04)
            total = read_u32(blk, 0x08)
            g0 = read_u32(blk, 0x0C)
            g1 = read_u32(blk, 0x10)
            gcnt = read_u32(blk, 0x14)
            cont = read_u32(blk, 0x18)
            info = {"wrld_type": wrld_type, "total": total, "g0": g0, "g1": g1, "gcnt": gcnt, "cont": cont}
            note = "WRLD 32B preface"
        elif tag == b"xet\x00":
            _hdrsz = read_u32(blk, 0x04)
            total = read_u32(blk, 0x08)
            g0 = read_u32(blk, 0x0C)
            g1 = read_u32(blk, 0x10)
            gcnt = read_u32(blk, 0x14)
            cont = read_u32(blk, 0x18)
            info = {"total": total, "g0": g0, "g1": g1, "gcnt": gcnt, "cont": cont, "hdrsz": _hdrsz}
            note = "TEX 32B preface"
        else:
            note = "Unknown 32B header"
            info = {"first16_hex": hexdump_bytes(blk[:16], 16)}
        return (tag_str, info, note)

    def parse_slave_groups_and_rescount(self):
        lvz = self.decomp
        n = len(lvz)
        cursor = 0x24
        groups: List[SlaveGroup] = []
        idx = 0
        while cursor + 8 <= n:
            addr = read_u32(lvz, cursor + 0)
            resv = read_u32(lvz, cursor + 4)
            plaus = (0 < addr < n and (addr & 0x3) == 0)
            plaus = plaus and (resv == 0 or (resv & 0xFFFF) == 0)
            if not plaus:
                break
            tag, info, note = self._peek_global32(addr)
            total = int(info.get("total", 0))
            gcnt  = int(info.get("gcnt", 0))
            cont  = int(info.get("cont", 0))
            groups.append(SlaveGroup(idx, addr, str(tag), total, gcnt, cont, note))
            idx += 1
            cursor += 8

        res_count = 0
        if cursor + 4 <= n:
            res_count_u32 = read_u32(lvz, cursor)
            res_count = res_count_u32 & 0xFFFF
            cursor += 4
        return (groups, res_count, cursor)

    def _classify_entry_peek(self, res_addr: int):
        lvz = self.decomp
        n = len(lvz)
        if res_addr == 0:
            info = {"reason": "ptr_is_zero"}
            if n >= 8:
                info["u16_pair"] = (read_u16(lvz, 0), read_u16(lvz, 2))
                info["u32_pair"] = (read_u32(lvz, 0), read_u32(lvz, 4))
            return ("EMPTY", info)
        if res_addr < 0 or res_addr + 8 > n:
            return ("INVALID", {"why": "out_of_range"})

        a16 = read_u16(lvz, res_addr + 0)
        b16 = read_u16(lvz, res_addr + 2)
        a32 = read_u32(lvz, res_addr + 0)
        b32 = read_u32(lvz, res_addr + 4)

        if a16 == 0:
            kind = "UNK_FAC0"
        elif a16 <= 100:
            kind = "MDL"
        else:
            kind = "TEX_REF"

        info = {"u16_pair": (a16, b16), "u32_pair": (a32, b32)}
        if kind == "UNK_FAC0":
            info["unk_fac0"] = b16
        if kind == "TEX_REF":
            info["ref_addr"] = a32
            info["embedded_res_id"] = b32  
        return (kind, info)

    def walk_master_resource_table(self, res_table_addr: int, res_count: int) -> List[Dict]:
        lvz = self.decomp
        rows: List[Dict] = []
        n = len(lvz)
        base = res_table_addr
        if base <= 0 or base + (res_count * 8) > n:
            max_rows = max(0, (n - base) // 8)
            if res_count > max_rows:
                dbg(f"[lvz] WARNING: res_count={res_count} exceeds file bounds; clamping to {max_rows}")
                res_count = max_rows
        off = base
        for i in range(res_count):
            res_addr = read_u32(lvz, off + 0)
            reserved = read_u32(lvz, off + 4)
            kind, info = self._classify_entry_peek(res_addr)
            a16, b16 = info.get("u16_pair", (None, None))
            a32, b32 = info.get("u32_pair", (None, None))
            row: Dict = {
                "index": i,                 
                "table_off": off,
                "res_addr": res_addr,
                "reserved": reserved,
                "kind": kind,
                "peek_u16": (a16, b16),
                "peek_u32": (a32, b32),
            }
            if kind == "UNK_FAC0":
                row["unk_fac0"] = info.get("unk_fac0")
            if kind == "EMPTY":
                row["empty_reason"] = info.get("reason", "unknown")
            if kind == "TEX_REF":
                row["ref_addr"] = info.get("ref_addr")
                row["res_id"] = i  
                row["embedded_res_id"] = info.get("embedded_res_id")
            rows.append(row)
            off += 8
        return rows

    #######################################################
    # ===== Image logic (kept INTACT): palette, swizzle, PoT =====
    #######################################################

    @staticmethod
    def expand_nibbles_lo_first(b: bytes) -> np.ndarray:
        arr = np.frombuffer(b, dtype=np.uint8)
        lo = arr & 0x0F
        hi = arr >> 4
        return np.vstack([lo, hi]).T.reshape(-1)

    @staticmethod
    def _log2_pow2(n: int) -> int:
        l = 0
        v = max(1, n)
        while (1 << l) < v:
            l += 1
        return l

    @staticmethod
    def swizzle_ps2_addr(x: int, y: int, logw: int) -> int:
        X3 = (x >> 3) & 1
        Y1 = (y >> 1) & 1
        Y2 = (y >> 2) & 1
        x ^= ((Y1 ^ Y2) << 2)
        nx = (x & 7) | ((x >> 1) & ~7)
        ny = (y & 1) | ((y >> 1) & ~1)
        n = (Y1) | (X3 << 1)
        return (n | (nx << 2) | (ny << (logw - 1 + 2)))

    @classmethod
    def unswizzle8_ps2_linearized(cls, src: np.ndarray, w: int, h: int) -> np.ndarray:
        dst = np.empty(w * h, dtype=np.uint8)
        logw = cls._log2_pow2(w)
        for y in range(h):
            for x in range(w):
                s = cls.swizzle_ps2_addr(x, y, logw)
                dst[y * w + x] = src[s % src.size]
        return dst

    @staticmethod
    def apply_ps2_alpha_scale(palette_rgba: np.ndarray, do_scale: bool) -> np.ndarray:
        if not do_scale:
            return palette_rgba
        pal = palette_rgba.copy()
        a = pal[:, 3].astype(np.uint16)
        a = (a * 255 + 64) // 128
        pal[:, 3] = np.clip(a, 0, 255).astype(np.uint8)
        return pal

    @staticmethod
    def image_from_rgba_uint8(rgba: np.ndarray, name: str, w: int, h: int) -> bpy.types.Image:
        img = bpy.data.images.new(name=name, width=w, height=h, alpha=True, float_buffer=False)
        flat = (rgba.astype(np.float32) / 255.0).reshape(-1, 4)
        img.pixels = flat.flatten().tolist()
        img.alpha_mode = 'STRAIGHT'
        img.pack()
        return img

    @staticmethod
    def create_material_from_image(img: bpy.types.Image, mat_name: str) -> bpy.types.Material:
        mat = bpy.data.materials.new(mat_name)
        mat.use_nodes = True
        nt = mat.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (300, 0)
        princ = nt.nodes.new("ShaderNodeBsdfPrincipled"); princ.location = (0, 0)
        tex = nt.nodes.new("ShaderNodeTexImage"); tex.location = (-300, 0); tex.image = img
        nt.links.new(tex.outputs["Color"], princ.inputs["Base Color"])
        if img.has_data and "Alpha" in tex.outputs and "Alpha" in princ.inputs:
            nt.links.new(tex.outputs["Alpha"], princ.inputs["Alpha"])
            mat.blend_method = 'BLEND'
        nt.links.new(princ.outputs["BSDF"], out.inputs["Surface"])
        return mat

    @staticmethod
    def split_index_and_palette_tail64(data: bytes) -> Tuple[bytes, List[Tuple[int,int,int,int]], int, int]:
        if len(data) < 64:
            raise ValueError("Input shorter than 64 bytes; cannot take tail-64 palette.")
        index = data[:-64]
        pal = data[-64:]
        palette = [tuple(pal[i:i+4]) for i in range(0, 64, 4)]
        return index, palette, len(data) - 64, 64

    @staticmethod
    def split_index_and_palette_explicit(data: bytes, pal_offset: int, pal_size: int) -> Tuple[bytes, List[Tuple[int,int,int,int]], int, int]:
        if pal_offset < 0 or pal_offset + pal_size > len(data):
            raise ValueError("Palette window out of range.")
        pal = data[pal_offset: pal_offset + pal_size]
        if pal_size % 4 != 0:
            raise ValueError("Palette size must be divisible by 4 (RGBA entries).")
        index = data[:pal_offset]
        palette = [tuple(pal[i:i+4]) for i in range(0, pal_size, 4)]
        return index, palette, pal_offset, pal_size

    @classmethod
    def palette_candidate_single(cls, data: bytes, mode: str, explicit_off: Optional[int], explicit_sz: Optional[int]):
        if mode == "explicit" and explicit_off is not None and explicit_sz is not None:
            i, p, off, sz = cls.split_index_and_palette_explicit(data, explicit_off, explicit_sz)
            return (i, p, off, sz, f"pal_explicit_{sz}")
        i, p, off, sz = cls.split_index_and_palette_tail64(data)
        return (i, p, off, sz, "pal_tail64")

    @staticmethod
    def nearest_pow2(n: int) -> int:
        if n <= 1:
            return 1
        if (n & (n - 1)) == 0:
            return n
        lower = 1 << (n.bit_length() - 1)
        upper = lower << 1
        return upper if (n - lower) > (upper - n) else lower

    @staticmethod
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

    @staticmethod
    def choose_single_size_for_4bpp(index_len_bytes: int, sizes_hint: Optional[str], prefer_square: bool = True) -> Tuple[int, int]:
        total_pixels = index_len_bytes * 2
        if total_pixels <= 0:
            raise ValueError("Index length is zero; cannot choose size.")
        if sizes_hint:
            hints = []
            for chunk in sizes_hint.split(","):
                chunk = chunk.strip().lower()
                if not chunk or "x" not in chunk:
                    continue
                w_str, h_str = chunk.split("x", 1)
                try:
                    w = int(w_str); h = int(h_str)
                    hints.append((w, h))
                except ValueError:
                    continue
            for (w, h) in hints:
                if w > 0 and h > 0 and (w * h) == total_pixels:
                    return (w, h)

        dim_pool = [16, 32, 64, 128, 256, 512, 1024] 
        cands: List[Tuple[int, int]] = []
        for w in dim_pool:
            if total_pixels % w != 0:
                continue
            h = total_pixels // w
            if h in dim_pool:
                cands.append((w, h))
        if not cands:
            for w in dim_pool:
                if total_pixels % w == 0:
                    h = total_pixels // w
                    if h > 0:
                        cands.append((w, h))
        if not cands:
            raise ValueError(f"No dimension pair matches pixel count {total_pixels}. Provide an explicit size.")
        squares = [(w, h) for (w, h) in cands if w == h]
        if prefer_square and squares:
            squares.sort(key=lambda wh: abs(wh[0] - int(math.sqrt(total_pixels))))
            return squares[0]
        cands.sort(key=lambda wh: (abs(wh[0] - wh[1]), -wh[0]))
        return cands[0]

    def decode_blob_4bpp_lo_single(self,
                                   blob: bytes,
                                   out_stem: str,
                                   palette_mode: str,
                                   palette_offset: Optional[int],
                                   palette_size: Optional[int],
                                   use_swizzle: bool,
                                   sizes_hint: Optional[str],
                                   alpha_scale: str,
                                   name_override: Optional[str] = None) -> Dict:
        index, palette, pal_off, pal_sz, tag = self.palette_candidate_single(blob, palette_mode, palette_offset, palette_size)
        if self.debug_print:
            dbg(f"[palette] using {tag}  index_len={len(index)}  pal_sz={pal_sz}")
        w, h = self.choose_single_size_for_4bpp(len(index), sizes_hint, prefer_square=True)
        if self.debug_print:
            dbg(f"[size] chosen (pre-round): {w}x{h} (pixels={w*h}, index_bytes={len(index)})")
        expanded = self.expand_nibbles_lo_first(index)
        need = w * h
        if len(expanded) < need:
            raise ValueError(f"Expanded indices smaller than required pixels ({len(expanded)} < {need}).")
        slab = expanded[:need]
        if use_swizzle:
            slab = self.unswizzle8_ps2_linearized(slab, w, h)
        idx2d = slab.reshape(h, w)
        w2 = self.nearest_pow2(w)
        h2 = self.nearest_pow2(h)
        if (w2, h2) != (w, h):
            if self.debug_print:
                dbg(f"[pow2] rounding to nearest per-dimension: ({w}x{h}) → ({w2}x{h2})")
            idx2d = self.resize_indices_to_dims(idx2d, w2, h2)
            w, h = w2, h2
        idx2d = np.flipud(idx2d)
        pal_arr = np.asarray(palette, dtype=np.uint8)
        pal_arr = self.apply_ps2_alpha_scale(pal_arr, do_scale=(alpha_scale == "ps2"))
        rgba = pal_arr[np.clip(idx2d, 0, pal_arr.shape[0] - 1)]
        asset_name = name_override if name_override else out_stem
        img = self.image_from_rgba_uint8(rgba, asset_name, w, h)
        mat = self.create_material_from_image(img, asset_name)
        return {"material": mat, "size": (w, h), "palette_tag": tag}

    #######################################################
    # Texture decode
    #######################################################

    def decode_textures(self, rows: List[Dict]) -> int:
        tex_rows = [r for r in rows if r["kind"] == "TEX_REF"]
        if not tex_rows:
            dbg("[tex] no TEX_REF rows")
            return 0

        dbg(f"[tex] TEX_REF rows: {len(tex_rows)}")
        tex_sorted = sorted(
            [{"i": r["index"], "ref_addr": r.get("ref_addr", -1), "res_id": r.get("res_id", -1),
              "embedded": r.get("embedded_res_id", None)} for r in tex_rows],
            key=lambda d: d["ref_addr"]
        )
        uniq = []
        last = None
        for t in tex_sorted:
            ra = t["ref_addr"]
            if ra != last and isinstance(ra, int) and 0 <= ra < len(self.decomp):
                uniq.append(t)
                last = ra

        decoded = 0
        for idx, r in enumerate(uniq):
            start = r["ref_addr"]
            end = uniq[idx+1]["ref_addr"] if idx+1 < len(uniq) else len(self.decomp)
            if end <= start or end - start < 64:
                continue
            blob = self.decomp[start:end]

            res_index = r["res_id"]  
            material_name = f"{self.stem}{res_index:0d}"
            try:
                result = self.decode_blob_4bpp_lo_single(
                    blob=blob,
                    out_stem=material_name,
                    palette_mode="tail64",
                    palette_offset=None,
                    palette_size=None,
                    use_swizzle=self.use_swizzle,
                    sizes_hint=None,
                    alpha_scale="ps2",
                    name_override=material_name
                )
                mat = result["material"]
                self.material_by_res_index[res_index] = mat
                decoded += 1
                if self.debug_print:
                    if r["embedded"] is not None:
                        dbg(f"[tex] {material_name}: material='{mat.name}' size={result['size']} RES(index)={res_index} embedded=0x{r['embedded']:08X}")
                    else:
                        dbg(f"[tex] {material_name}: material='{mat.name}' size={result['size']} RES(index)={res_index}")
            except Exception as e:
                dbg(f"[tex] {material_name}: decode error: {e}")
        dbg(f"[tex] total decoded: {decoded}")
        return decoded

    #######################################################
    # MDL parse + mesh build
    #######################################################

    def _read_vec3_i16_norm(self, buf: bytes, off: int) -> Tuple[float,float,float]:
        x = read_i16(buf, off + 0); y = read_i16(buf, off + 2); z = read_i16(buf, off + 4)
        return (x / 32767.5, y / 32767.5, z / 32767.5)

    def _read_uv_u8_div128(self, buf: bytes, off: int) -> Tuple[float,float]:
        u = buf[off + 0]; v = buf[off + 1]
        return (u / 128.0, v / 128.0)

    def _decode_rgba4444(self, v16: int) -> Tuple[int,int,int,int]:
        r = ((v16 >> 12) & 0xF) * 17
        g = ((v16 >> 8)  & 0xF) * 17
        b = ((v16 >> 4)  & 0xF) * 17
        a = ( v16        & 0xF) * 17
        return (r, g, b, a)

    def _find_unpack_near(self, buf: bytes, off: int, window: int = 8) -> int:
        n = len(buf)
        start = max(0, off - window)
        end = min(n, off + window + 4)
        for p in range(start, end):
            if (p & 3) == 0 and p + 4 <= n and read_u32(buf, p) == self.UNPACK:
                return p
        raise ValueError(f"UNPACK header not found near 0x{off:08X}")

    def parse_mdl_material_list(self, base: int) -> MDLMaterialList:
        lvz = self.decomp
        n = len(lvz)
        if base + 4 > n:
            raise ValueError("MDL material list header out of range.")
        count = read_u16(lvz, base + 0)
        size_bytes = read_u16(lvz, base + 2)
        off = base + 4
        materials: List[MDLMaterial] = []
        bytes_limit = min(n, base + 4 + size_bytes)
        for mi in range(count):
            need = off + 22
            if need > n:
                dbg(f"[mdl] material {mi}: truncated at LVZ end (need up to 0x{need:08X})")
                break
            if off >= bytes_limit:
                dbg(f"[mdl] reached declared size_bytes at material {mi}; stopping")
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
                bbox6_i16=(b0,b1,b2,b3,b4,b5)
            ))
            off += 22
        aa_tail, new_off = self._scan_aa_tail(off)
        next_guess = align_down4(new_off)
        return MDLMaterialList(
            count=count,
            size_bytes=size_bytes,
            materials=materials,
            bytes_read=off - base,
            aa_tail=aa_tail,
            next_off=next_guess
        )

    def _scan_aa_tail(self, off: int) -> Tuple[bytes, int]:
        lvz = self.decomp
        n = len(lvz); i = off
        while i < n and lvz[i] == 0xAA:
            i += 1
        return (lvz[off:i], i)

    def parse_one_batch_noskip(self, buf: bytes, pos: int) -> Tuple[TriStrip, int]:
        n = len(buf)
        pos = self._find_unpack_near(buf, align_down4(pos))
        if pos + 20 > n:
            raise ValueError("Batch header truncated.")
        nvert_all = read_u32(buf, pos + 16) & 0x7FFF
        nvert_eff = nvert_all
        w = pos + 20

        if read_u32(buf, w) != self.STMASK: raise ValueError(f"Expected STMASK before positions at 0x{w:08X}")
        w += 8
        if read_u32(buf, w) != self.STROW:  raise ValueError(f"Expected STROW before positions at 0x{w:08X}")
        w += 20
        h_pos = read_u32(buf, w)
        if (h_pos & 0xFF004000) != 0x79000000: raise ValueError(f"Unexpected positions header 0x{h_pos:08X} at 0x{w:08X}")
        w += 4
        need_bytes_pos = nvert_all * 6
        if w + need_bytes_pos > n: raise ValueError("Position payload truncated.")
        verts: List[Tuple[float,float,float]] = []
        for i in range(nvert_eff):
            off = w + i * 6
            verts.append(self._read_vec3_i16_norm(buf, off))
        w += need_bytes_pos
        w = align_up4(w)

        if read_u32(buf, w) != self.STMASK: raise ValueError(f"Expected STMASK before texcoords at 0x{w:08X}")
        w += 8
        if read_u32(buf, w) != self.STROW:  raise ValueError(f"Expected STROW before texcoords at 0x{w:08X}")
        w += 20
        h_uv = read_u32(buf, w)
        if (h_uv & 0xFF004000) != 0x76004000: raise ValueError(f"Unexpected UV header 0x{h_uv:08X} at 0x{w:08X}")
        w += 4
        need_bytes_uv = nvert_all * 2
        if w + need_bytes_uv > n: raise ValueError("UV payload truncated.")
        uvs: List[Tuple[float,float]] = []
        for i in range(nvert_eff):
            off = w + i * 2
            uvs.append(self._read_uv_u8_div128(buf, off))
        w += need_bytes_uv
        w = align_up4(w)

        h_col = read_u32(buf, w)
        if (h_col & 0xFF004000) != 0x6F000000: raise ValueError(f"Unexpected prelight header 0x{h_col:08X} at 0x{w:08X}")
        w += 4
        need_bytes_col = nvert_all * 2
        if w + need_bytes_col > n: raise ValueError("Prelight payload truncated.")
        cols_raw_u16: List[int] = []
        cols_rgba4444: List[Tuple[int,int,int,int]] = []
        for i in range(nvert_eff):
            c16 = read_u16(buf, w + i * 2)
            cols_raw_u16.append(c16)
            cols_rgba4444.append(self._decode_rgba4444(c16))
        w += need_bytes_col
        w = align_up4(w)

        if read_u32(buf, w) != self.MSCAL:
            if w + 4 <= n and read_u32(buf, w + 4) == self.MSCAL:
                w += 4
            else:
                raise ValueError(f"MSCAL 0x14000006 missing around 0x{w:08X}")
        w += 4
        while w + 4 <= n and read_u32(buf, w) == 0:
            w += 4

        strip = TriStrip(
            count=nvert_eff,
            verts=verts,
            uvs=uvs,
            cols_raw_u16=cols_raw_u16,
            cols_rgba4444=cols_rgba4444
        )
        return strip, w

    def parse_mdl_stream_after_list(self, start_off: int, max_groups: int = 4096) -> Tuple[List[MDLStripGroup], int]:
        buf = self.decomp
        groups: List[MDLStripGroup] = []
        try:
            off = self._find_unpack_near(buf, start_off)
        except Exception as e:
            dbg(f"[splits] UNPACK not found near 0x{start_off:08X}: {e}")
            return groups, start_off
        n = len(buf)
        for _ in range(max_groups):
            if off >= n:
                break
            try:
                strip, next_off = self.parse_one_batch_noskip(buf, off)
            except Exception as e:
                dbg(f"[splits] stop at 0x{off:08X}: {e}")
                break
            groups.append(MDLStripGroup(strips=[strip], bytes_read=(next_off - off), start_off=off, end_off=next_off))
            try:
                off = self._find_unpack_near(buf, next_off)
            except Exception:
                off = next_off
                break
        return groups, off

    def assign_materials_by_strip_bytes(self, mlist: MDLMaterialList, groups: List[MDLStripGroup]):

        if not mlist.materials or not groups:
            return

        flat: List[Tuple[TriStrip, int, int]] = []
        gstart = min(g.start_off for g in groups)
        for g in groups:
            for s in g.strips:
                s_start = g.start_off
                s_end = g.end_off
                flat.append((s, s_start - gstart, s_end - gstart))

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

    def _triangulate_strip_indices(self, local_count: int) -> List[Tuple[int,int,int]]:
        tris: List[Tuple[int,int,int]] = []
        for i in range(local_count - 2):
            if i & 1:
                tris.append((i + 1, i, i + 2))
            else:
                tris.append((i, i + 1, i + 2))
        return tris

    def _build_mesh_from_mdl_groups(self, res_index: int, groups: List[MDLStripGroup]):
        if not groups:
            return None, []
        vertices: List[Tuple[float,float,float]] = []
        uvs: List[Tuple[float,float]] = []
        faces: List[Tuple[int,int,int]] = []
        face_ranges: List[Tuple[int,int,int]] = []

        for g in groups:
            for s in g.strips:
                k = min(len(s.verts), len(s.uvs), s.count)
                if k < 3:
                    continue
                base = len(vertices)
                vertices.extend(s.verts[:k])
                uvs.extend(s.uvs[:k])
                tri_list = self._triangulate_strip_indices(k)
                poly_start = len(faces)
                for a,b,c in tri_list:
                    faces.append((base + a, base + b, base + c))
                poly_count = len(tri_list)
                face_ranges.append((poly_start, poly_count, s.material_res_index))

        if not faces or not vertices:
            return None, []

        mesh_name = f"{self.stem}{res_index:0d}"
        me = bpy.data.meshes.new(mesh_name)
        me.from_pydata(vertices, [], faces)
        me.use_auto_smooth = True
        me.validate(clean_customdata=False)
        me.update()

        if uvs:
            uv_layer = me.uv_layers.new(name="UVMap")
            uv_data = uv_layer.data
            for poly in me.polygons:
                li = poly.loop_start
                for j, vi in enumerate(poly.vertices):
                    if vi < len(uvs):
                        u, v = uvs[vi]
                        uv_data[li + j].uv = (u, v)

        obj = bpy.data.objects.new(mesh_name, me)
        bpy.context.scene.collection.objects.link(obj)
        obj["blds_kind"] = "MDL"
        obj["blds_res_index"] = res_index
        obj["blds_groups"] = len(groups)
        obj["blds_faces"] = len(faces)
        obj["blds_verts"] = len(vertices)
        return obj, face_ranges

    def build_mdl_objects(self, rows: List[Dict]) -> Dict[int, bpy.types.Object]:
        mdl_rows = [r for r in rows if r["kind"] == "MDL"]
        built_by_res: Dict[int, bpy.types.Object] = {}
        if not mdl_rows:
            dbg("— MDL — none found")
            return built_by_res

        dbg("— MDL Material Lists + Batches + Mesh Build (NO-SKIP) —")
        built_cnt = 0
        for row in mdl_rows:
            res_index = row["index"]
            res_addr  = row["res_addr"]
            try:
                mlist = self.parse_mdl_material_list(res_addr)
            except Exception as e:
                dbg(f"[mdl {res_index}] material list error at 0x{res_addr:08X}: {e}")
                continue

            dbg(f"[mdl {res_index}] list: count={mlist.count} size_bytes={mlist.size_bytes} bytes_read={mlist.bytes_read} aa_tail={len(mlist.aa_tail)} next=0x{mlist.next_off:08X}")
            for i, m in enumerate(mlist.materials):
                dbg(f"  mat[{i:02d}] texRES={m.texture_id} strip_size={m.tri_strip_size} cull={int(m.backface_cull)} us={m.u_scale:.4f} vs={m.v_scale:.4f} flags2=0x{m.flags2:04X} bbox={m.bbox6_i16}")

            groups, after = self.parse_mdl_stream_after_list(mlist.next_off)
            dbg(f"[mdl {res_index}] batches={len(groups)} stream_end=0x{after:08X}")

            self.assign_materials_by_strip_bytes(mlist, groups)

            for gi, g in enumerate(groups):
                for si, s in enumerate(g.strips):
                    k = s.count
                    dbg(f"[mdl {res_index}] dump: group={gi} strip={si} count={k} matRES={s.material_res_index} us={s.u_scale:.4f} vs={s.v_scale:.4f}")
                    for vi in range(k):
                        px, py, pz = s.verts[vi]
                        tu, tv     = s.uvs[vi]
                        c16        = s.cols_raw_u16[vi] if vi < len(s.cols_raw_u16) else 0
                        r,gc,b,a   = s.cols_rgba4444[vi] if vi < len(s.cols_rgba4444) else (0,0,0,0)
                        dbg(f"    v[{vi:04d}] pos=({px:.6f},{py:.6f},{pz:.6f}) uv=({tu:.6f},{tv:.6f}) col16=0x{c16:04X} rgba4444=({r},{gc},{b},{a})")

            obj, face_ranges = self._build_mesh_from_mdl_groups(res_index, groups)
            if obj is not None:
                mat_slots_added = 0
                resid_to_slot: Dict[int, int] = {}
                if mlist.materials:
                    for m in mlist.materials:
                        mat = self.material_by_res_index.get(m.texture_id)
                        if mat is not None:
                            if mat.name not in [mm.name for mm in obj.data.materials]:
                                obj.data.materials.append(mat)
                                resid_to_slot[m.texture_id] = len(obj.data.materials) - 1
                                mat_slots_added += 1
                            else:
                                for si, mm in enumerate(obj.data.materials):
                                    if mm and mm.name == mat.name:
                                        resid_to_slot[m.texture_id] = si
                                        break
                if face_ranges:
                    polys = obj.data.polygons
                    for (pstart, pcount, mat_resid) in face_ranges:
                        if mat_resid is None or mat_resid < 0:
                            continue
                        slot = resid_to_slot.get(mat_resid)
                        if slot is None:
                            continue
                        for pi in range(pstart, pstart + pcount):
                            if 0 <= pi < len(polys):
                                polys[pi].material_index = slot
                built_cnt += 1
                built_by_res[res_index] = obj
                dbg(f"[mdl {res_index}] → created object '{obj.name}' (added {mat_slots_added} material slots)")
            else:
                dbg(f"[mdl {res_index}] no faces/verts, skipped object creation")
        dbg(f"[done] total MDL objects created: {built_cnt}")
        return built_by_res

#######################################################
# read_img: IMG responsibilities only
#######################################################

class read_img:
    def __init__(self, img_bytes: bytes, lvz_bytes: bytes):
        self.img_bytes = img_bytes
        self.lvz_bytes = lvz_bytes

    def find_conts(self) -> List[int]:
        lvz = self.lvz_bytes
        conts: List[int] = []
        i = 0; n = len(lvz)
        while True:
            j = lvz.find(b"DLRW", i)
            if j < 0:
                break
            if (j & 3) == 0 and j + 32 <= n:
                conts.append(read_u32(lvz, j + 0x18))
            i = j + 1
        conts = sorted(set(conts))
        if 0 not in conts:
            conts = [0] + conts
        return conts

    def _img_sky_span(self, cont: int):
        img = self.img_bytes
        start = cont + 0x30
        if cont < 0 or start >= len(img):
            return None
        sky = [read_u32(img, cont + 0x08 + i * 4) for i in range(8)]
        nz = [v for v in sky if v]
        if not nz:
            return None
        stop = cont + max(nz)
        stop = min(stop, len(img))
        return (start, stop, sky)

    def enumerate_all_rows(self, conts: List[int]):
        rows: List[Tuple[int,int,int,int,int]] = []
        ENTRY = 0x50
        img = self.img_bytes
        for cont in conts:
            span = self._img_sky_span(cont)
            if not span:
                continue
            start, stop, sky = span
            off = start
            while off + ENTRY <= stop:
                ipl_raw = read_u16(img, off + 0x00)
                res_id  = read_u16(img, off + 0x02)
                rows.append((cont, off - cont, ipl_raw, (ipl_raw & 0x7FFF), res_id))
                off += ENTRY
        rows.sort(key=lambda t: (t[0], t[1]))
        return rows

    def enumerate_details(self, conts: List[int]):
        rows = []
        ENTRY = 0x50
        img = self.img_bytes
        for cont in conts:
            span = self._img_sky_span(cont)
            if not span:
                continue
            start, stop, sky = span
            off = start
            while off + ENTRY <= stop:
                ipl_raw = read_u16(img, off + 0x00)
                ipl_id  = (ipl_raw & 0x7FFF)
                res_id  = read_u16(img, off + 0x02)
                sx = half_to_float(read_u16(img, off + 0x04))
                sy = half_to_float(read_u16(img, off + 0x06))
                sz = half_to_float(read_u16(img, off + 0x08))
                sr = half_to_float(read_u16(img, off + 0x0A))
                m  = struct.unpack_from("<16f", img, off + 0x10)
                s0 = math.sqrt(m[0]*m[0] + m[1]*m[1] + m[2]*m[2])
                s1 = math.sqrt(m[4]*m[4] + m[5]*m[5] + m[6]*m[6])
                s2 = math.sqrt(m[8]*m[8] + m[9]*m[9] + m[10]*m[10])
                rows.append((res_id, cont, off - cont, ipl_raw, ipl_id, sx, sy, sz, sr, s0, s1, s2, m))
                off += ENTRY
        rows.sort(key=lambda t: (t[1], t[2]))
        return rows

    def write_csvs(self, lvz_path: str, all_rows, unique_rows, enable_unique: bool):
        out_csv = str(Path(lvz_path).with_suffix("")) + "_all_res_ids.csv"
        try:
            with open(out_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["index","cont_hex","off_hex","ipl_raw","ipl_id","res_id"])
                for i,(cont, rel_off, ipl_raw, ipl_id, res_id) in enumerate(all_rows):
                    w.writerow([i, f"0x{cont:08X}", f"0x{rel_off:08X}", f"0x{ipl_raw:04X}", ipl_id, res_id])
            dbg(f"[ids] wrote {len(all_rows)} rows → {out_csv}")
        except Exception as e:
            dbg(f"[ids] failed to write CSV: {e}")

        if enable_unique:
            try:
                out_csv_unique = str(Path(lvz_path).with_suffix("")) + "_all_res_ids_unique.csv"
                with open(out_csv_unique, "w", newline="", encoding="utf-8") as f2:
                    w2 = csv.writer(f2)
                    w2.writerow(["index","cont_hex","off_hex","ipl_raw","ipl_id","res_id"])
                    for i,(cont, rel_off, ipl_raw, ipl_id, res_id) in enumerate(unique_rows):
                        w2.writerow([i, f"0x{cont:08X}", f"0x{rel_off:08X}", f"0x{ipl_raw:04X}", ipl_id, res_id])
                dbg(f"[ids] wrote {len(unique_rows)} unique rows → {out_csv_unique}")
            except Exception as e:
                dbg(f"[ids] failed to write UNIQUE CSV: {e}")

    def build_transforms_map_and_log(self, details, enable_unique_log: bool) -> Dict[int, Matrix]:
        transforms_by_res: Dict[int, Matrix] = {}
        if not enable_unique_log:
            seen = set()
            for (res_id, cont, rel_off, ipl_raw, ipl_id, sx, sy, sz, sr, s0, s1, s2, m) in details:
                if res_id in seen:
                    continue
                seen.add(res_id)
                transforms_by_res[res_id] = Matrix((
                    (m[0], m[1], m[2],  m[3]),
                    (m[4], m[5], m[6],  m[7]),
                    (m[8], m[9], m[10], m[11]),
                    (m[12],m[13],m[14],m[15]),
                ))
            return transforms_by_res

        seen_res = set()
        kept = 0
        dbg("— UNIQUE RES IDs: xyzr + scales + matrix + pos —")
        for (res_id, cont, rel_off, ipl_raw, ipl_id, sx, sy, sz, sr, s0, s1, s2, m) in details:
            if res_id in seen_res:
                continue
            seen_res.add(res_id)
            kept += 1
            posx, posy, posz = (m[12], m[13], m[14])
            dbg(f"  RES={res_id} @ IMG+0x{cont:08X}+0x{rel_off:08X}  IPLraw=0x{ipl_raw:04X}  IPLid={ipl_id}")
            dbg(f"     sphere=({sx:.6f},{sy:.6f},{sz:.6f}, r={sr:.6f}) scale=({s0:.6f},{s1:.6f},{s2:.6f})")
            dbg(f"     mat=[[{m[0]:.6f},{m[1]:.6f},{m[2]:.6f},{m[3]:.6f}],")
            dbg(f"          [{m[4]:.6f},{m[5]:.6f},{m[6]:.6f},{m[7]:.6f}],")
            dbg(f"          [{m[8]:.6f},{m[9]:.6f},{m[10]:.6f},{m[11]:.6f}],")
            dbg(f"          [{m[12]:.6f},{m[13]:.6f},{m[14]:.6f},{m[15]:.6f}]]")
            dbg(f"     pos=({posx:.6f},{posy:.6f},{posz:.6f})")

            transforms_by_res[res_id] = Matrix((
                (m[0], m[1], m[2],  m[3]),
                (m[4], m[5], m[6],  m[7]),
                (m[8], m[9], m[10], m[11]),
                (m[12],m[13],m[14],m[15]),
            ))
        dbg(f"[ids] unique printed: {kept}")
        return transforms_by_res

#######################################################
class IMPORT_SCENE_OT_stories_lvz(Operator, ImportHelper):
    """Import a Rockstar Leeds LevelZlib & IMG Archive"""
    bl_idname = "import_scene.leeds_lvz_img"
    bl_label = "Import LVZ + IMG Archive"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".lvz"

    use_swizzle: BoolProperty(
        name="PS2 swizzle",
        default=True
    )
    csv_dedup_res_ids: BoolProperty(
        name="CSV unique + log detailed blocks",
        default=True
    )
    apply_img_transforms: BoolProperty(
        name="Apply IMG transforms to MDL objects",
        default=True
    )
    debug_print: BoolProperty(
        name="Debug print",
        default=True
    )
    write_debug_log: BoolProperty(
        name="Write debug log next to LVZ",
        default=True
    )

    filter_glob: StringProperty(
        default="*.lvz;*.LVZ",
        options={'HIDDEN'},
        maxlen=255,
    )

    def execute(self, context):
        lvz_path = self.filepath
        if not lvz_path:
            self.report({'ERROR'}, "No LVZ selected.")
            return {'CANCELLED'}

        stem = Path(lvz_path).stem
        log_path = str(Path(lvz_path).with_suffix("")) + "_blds_import.log" if self.write_debug_log else None
        global DEBUG
        DEBUG = DebugOut(self.debug_print, self.write_debug_log, log_path)

        t0 = time.time()
        lvz_bytes_in = Path(lvz_path).read_bytes()
        decomp, was_cmp = safe_decompress(lvz_bytes_in)

        dbg("===== LVZ Walk + IMG Match/Apply =====")
        dbg(f"LVZ: {lvz_path}")
        dbg(f"[io] LVZ bytes in: {len(lvz_bytes_in)}  decomp: {len(decomp)} ({'compressed' if was_cmp else 'raw'})")
        dbg("")

        lvz = read_lvz(
            decomp_bytes=decomp,
            stem=stem,
            use_swizzle=self.use_swizzle,
            debug_print=self.debug_print
        )
        try:
            mast = lvz.parse_master_header()
            groups_hdr, res_count, _ = lvz.parse_slave_groups_and_rescount()
        except Exception as e:
            self.report({'ERROR'}, f"Failed to parse LVZ: {e}")
            return {'CANCELLED'}

        dbg("— Slave Group Table —")
        dbg(f"  groups: {len(groups_hdr)}")
        for g in groups_hdr:
            dbg(f"  [sg {g.index:03d}] LVZ+0x{g.addr:08X} tag='{g.tag}' size={g.total} gcnt={g.gcnt} contIMG=0x{g.cont:08X} — {g.note}")
        dbg(f"  resource count: {res_count}")
        dbg("")

        rows = lvz.walk_master_resource_table(mast.res_table_addr, res_count)
        dbg("— Master Resource Table (first 300) —")
        for r in rows[:min(len(rows), 300)]:
            a16, b16 = r["peek_u16"]; a32, b32 = r["peek_u32"]
            extra = []
            if r["kind"] == "UNK_FAC0" and "unk_fac0" in r: extra.append(f"unk_fac0={r['unk_fac0']}")
            if r["kind"] == "EMPTY" and "empty_reason" in r: extra.append(f"reason={r['empty_reason']}")
            if r["kind"] == "TEX_REF":
                extra.append(f"ref_addr=0x{r['ref_addr']:08X}")
                extra.append(f"RES(index)={r['index']}")
                if "embedded_res_id" in r and r["embedded_res_id"] is not None:
                    extra.append(f"embedded=0x{r['embedded_res_id']:08X}")
            dbg(f"[res {r['index']:5d}] table@0x{r['table_off']:08X} → res@0x{r['res_addr']:08X} "
                f"kind={r['kind']} u16,u16=({a16},{b16}) u32,u32=(0x{(a32 if a32 is not None else 0):08X},0x{(b32 if b32 is not None else 0):08X}) {' '.join(extra)}")
        dbg("")

        img_bytes = None; img_name = None
        try:
            lvz_p = Path(lvz_path)
            cands = [lvz_p.with_suffix(".IMG"), lvz_p.with_suffix(".img"), lvz_p.with_suffix(".img.zip")]
            for cand in cands:
                if cand.exists():
                    if cand.suffix.lower() == ".zip":
                        with zipfile.ZipFile(cand, 'r') as zf:
                            nm = None
                            for nm0 in zf.namelist():
                                if nm0.lower().endswith(".img"):
                                    nm = nm0; break
                            if nm is None and zf.namelist():
                                nm = zf.namelist()[0]
                            img_bytes = zf.read(nm)
                            img_name = str(cand.name)
                    else:
                        img_bytes = cand.read_bytes()
                        img_name = cand.name
                    break
            if img_bytes:
                dbg(f"— IMG Read — source: {img_name} bytes={len(img_bytes)}")
            else:
                dbg("[img] IMG not found next to LVZ; IMG-based features will be skipped")
        except Exception as eimg:
            dbg(f"[img] failed to read IMG: {eimg}")

        lvz.decode_textures(rows)

        transforms_by_res: Dict[int, Matrix] = {}
        if img_bytes:
            img = read_img(img_bytes=img_bytes, lvz_bytes=decomp)
            conts = img.find_conts()
            dbg(f"[img] DLRW prefaces in LVZ → conts: {len(conts)} (includes master=0)")
            all_rows = img.enumerate_all_rows(conts)
            details  = img.enumerate_details(conts)
            transforms_by_res = img.build_transforms_map_and_log(details, enable_unique_log=self.csv_dedup_res_ids)
            dbg(f"[img] total IMG rows walked: {len(all_rows)}")
            dbg("— ALL RESOURCE IDs (IMG walk order) —")
            for i, (cont, rel_off, ipl_raw, ipl_id, res_id) in enumerate(all_rows):
                dbg(f"{i:04d}: {res_id}")

            if self.csv_dedup_res_ids:
                seen = set(); unique_rows = []
                for row in all_rows:
                    rid = row[4]
                    if rid not in seen:
                        seen.add(rid)
                        unique_rows.append(row)
            else:
                unique_rows = []
            img.write_csvs(lvz_path, all_rows, unique_rows, enable_unique=self.csv_dedup_res_ids)
        else:
            dbg("[img] IMG rows not enumerated because IMG is missing")

        built_by_res = lvz.build_mdl_objects(rows)

        if self.apply_img_transforms and transforms_by_res:
            applied = 0
            for res_id, M in transforms_by_res.items():
                obj = built_by_res.get(res_id)
                if obj is None:
                    continue
                try:
                    obj.matrix_world = M
                    applied += 1
                    dbg(f"[apply] RES={res_id} → object '{obj.name}' matrix_world set.")
                except Exception as e:
                    dbg(f"[apply] RES={res_id} apply failed: {e}")
            dbg(f"[apply] transforms applied: {applied} (of {len(transforms_by_res)})")
        elif self.apply_img_transforms:
            dbg("[apply] no IMG transforms available to apply")

        dbg(f"\n[total] finished in {time.time() - t0:.2f}s")
        if DEBUG is not None:
            DEBUG.flush()
        return {'FINISHED'}

#######################################################
classes = (IMPORT_SCENE_OT_stories_lvz,)

def menu_func_import(self, context):
    self.layout.operator(IMPORT_SCENE_OT_stories_lvz.bl_idname, text="R* Leeds: LeVelZlib IMG Archive")

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    for c in reversed(classes):
        bpy.utils.unregister_class(c)

if __name__ == "__main__":
    register()
