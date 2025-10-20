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

import bpy
import struct
import zlib
import datetime
import os
import sys
import traceback

from pathlib import Path
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty
from bpy.types import Operator

#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
#   This script is for .IMG & .LVZ - file formats for Stories/MH2 worlds            #
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
# Little helpers
#######################################################
def read_u32_le(buf, off):
    return struct.unpack_from("<I", buf, off)[0]

def read_u16_le(buf, off):
    return struct.unpack_from("<H", buf, off)[0]

def read_fourcc(buf, off):
    return buf[off:off+4].decode("ascii", errors="ignore")

def looks_like_zlib(buf):
    return len(buf) >= 2 and buf[0] == 0x78 and buf[1] in (0x01, 0x9C, 0xDA)

def ensure_wrld_bytes(raw_bytes):
    if len(raw_bytes) >= 4 and raw_bytes[:4] == b"DLRW":
        return raw_bytes
    if looks_like_zlib(raw_bytes):
        try:
            data = zlib.decompress(raw_bytes)
            if len(data) >= 4 and data[:4] == b"DLRW":
                return data
        except zlib.error:
            pass
    return raw_bytes

def hx32(v):
    return f"0x{v:08X}"

def hx16(v):
    return f"0x{v:04X}"

#######################################################
# Debug logger 
#######################################################
class DebugLog:
    """
    Simple log sink:
      - Collects lines in memory
      - Prints to console immediately
      - Writes the entire session to a file at the end
    The file name is "<lvz_stem>_import_log" (no extension).
    """
    def __init__(self, requested_path: Path):
        self.lines = []
        self.log_path = self._resolve_log_path(requested_path)
        now = datetime.datetime.now()
        self.log(f"===== LVZ+IMG Import Session =====")
        self.log(f"Time: {now.isoformat(sep=' ', timespec='seconds')}")
        self.log(f"Log file: {self.log_path}")
        self.log("")

    def _resolve_log_path(self, requested_path: Path) -> Path:
        """
        Try to place the log next to the LVZ as "<stem>_import_log".
        If not writable, fall back to Blender temp dir, then home dir.
        """
        candidate = requested_path
        try:
            with open(candidate, "w", encoding="utf-8") as _:
                pass
            return candidate
        except Exception:
            pass

        tempdir = getattr(bpy.app, "tempdir", None) or ""
        if tempdir:
            try:
                p = Path(tempdir) / requested_path.name
                with open(p, "w", encoding="utf-8") as _:
                    pass
                return p
            except Exception:
                pass

        try:
            home = Path.home()
            p = home / requested_path.name
            with open(p, "w", encoding="utf-8") as _:
                pass
            return p
        except Exception:
            return Path(os.getcwd()) / requested_path.name

    def log(self, s: str):
        self.lines.append(s)
        print(s)

    def __call__(self, s: str):
        self.log(s)

    def write_out(self):
        try:
            with open(self.log_path, "w", encoding="utf-8") as f:
                for line in self.lines:
                    f.write(line)
                    if not line.endswith("\n"):
                        f.write("\n")
        except Exception as e:
            print(f"[WARN] Failed to write log to {self.log_path}: {e}")

#######################################################
# WRLD master header (top of LVZ)
#######################################################
def parse_wrld_header(buf):
    if len(buf) < 0x24:
        raise ValueError("buffer too small for WRLD header")
    return {
        "fourcc":             read_fourcc(buf, 0x00),
        "shrink":             read_u32_le(buf, 0x04),
        "file_size":          read_u32_le(buf, 0x08),
        "global_addr_0":      read_u32_le(buf, 0x0C),
        "global_addr_1":      read_u32_le(buf, 0x10),
        "global_count":       read_u32_le(buf, 0x14),
        "slave_continuation": read_u32_le(buf, 0x18),
        "reserved":           read_u32_le(buf, 0x1C),
        "resource_id_table":  read_u32_le(buf, 0x20),
    }

#######################################################
# Directory + technical mirror
#######################################################
def parse_group_directory_and_tech(buf, start_off=0x24, safety_pairs=65535):
    off = start_off
    dir_begin = off
    entries = []

    for _ in range(safety_pairs):
        if off + 4 > len(buf):
            raise ValueError("unexpected end while peeking directory")
        peek = read_u32_le(buf, off)

        if peek == 0:
            off += 4
            break

        if (peek & 0xFFFF0000) == 0:
            break

        if off + 8 > len(buf):
            raise ValueError("truncated pair in directory")
        addr = peek
        x_shift = read_u32_le(buf, off + 4)
        entries.append((addr, x_shift))
        off += 8

    if off + 4 > len(buf):
        raise ValueError("missing u16 group_count + u16 reserved")
    count_off = off
    group_count = read_u16_le(buf, off)
    reserved = read_u16_le(buf, off + 2)
    off += 4

    dir_plus_count_len = off - dir_begin
    tech_len = dir_plus_count_len
    pad_start = off
    pad_end = min(off + tech_len, len(buf))
    padding_bytes = buf[pad_start:pad_end]
    off = pad_end

    return {
        "entries": entries,
        "count_u16": group_count,
        "reserved_u16": reserved,
        "count_off": count_off,
        "dir_bytes": (count_off - dir_begin),
        "dir_plus_count_bytes": dir_plus_count_len,
        "pad_start": pad_start,
        "pad_bytes": padding_bytes,
        "next_offset": off,
    }

#######################################################
# Count 32-byte Slave WRLD headers per group (LVZ-only)
#######################################################
def count_headers_in_groups(lvz_bytes, group_entries):
    groups = sorted(group_entries, key=lambda t: t[0])
    addrs = [g[0] for g in groups]

    results = []
    for i, (addr, xshift) in enumerate(groups):
        start = max(0, min(addr, len(lvz_bytes)))
        if i + 1 < len(groups):
            end_limit = max(start, min(addrs[i+1], len(lvz_bytes)))
            last = False
        else:
            end_limit = len(lvz_bytes)
            last = True

        ptr = start
        members = 0

        if not last:
            while ptr + 32 <= end_limit:
                if lvz_bytes[ptr:ptr+4] != b"DLRW":
                    break
                members += 1
                ptr += 32
            window_end = end_limit
        else:
            while ptr + 32 <= len(lvz_bytes) and lvz_bytes[ptr:ptr+4] == b"DLRW":
                members += 1
                ptr += 32
            window_end = ptr

        group_bytes = members * 32
        trailing = max(0, window_end - start - group_bytes)
        results.append({
            "addr": addr,
            "xshift": xshift,
            "members": members,
            "total_bytes": group_bytes,
            "window_start": start,
            "window_end": window_end,
            "trailing_bytes": trailing,
        })
    return results

#######################################################
# Resource Address Table 
#######################################################
def parse_resource_address_table(buf, start_off, group_count_u16, max_pairs_cap=10_000_000):
    expected_pairs = int(group_count_u16)
    expected_pairs = min(expected_pairs, max_pairs_cap)

    pairs = []
    off = start_off
    for _ in range(expected_pairs):
        if off + 8 > len(buf):
            break
        rid = read_u32_le(buf, off)
        filler = read_u32_le(buf, off + 4)
        pairs.append((rid, filler))
        off += 8

    nonzero = [rid for (rid, filler) in pairs if rid != 0]
    bytes_consumed = len(pairs) * 8
    return {
        "pairs": pairs,
        "nonzero_ids": nonzero,
        "bytes_consumed": bytes_consumed,
        "start_off": start_off,
        "expected_pairs": expected_pairs,
        "actual_pairs": len(pairs),
        "end_off": start_off + bytes_consumed
    }

#######################################################
# LVZ: Read a single 32-byte Slave WRLD header
#######################################################
def parse_slave_wrld_header(buf, off):
    if off + 32 > len(buf):
        raise ValueError(f"not enough bytes to read 32-byte WRLD header at {hx32(off)}")

    fourcc = read_fourcc(buf, off + 0x00)
    wrld_type = read_u32_le(buf, off + 0x04)
    size      = read_u32_le(buf, off + 0x08)
    glob0     = read_u32_le(buf, off + 0x0C)
    glob1     = read_u32_le(buf, off + 0x10)
    globcnt   = read_u32_le(buf, off + 0x14)
    cont_img  = read_u32_le(buf, off + 0x18)
    reserved  = read_u32_le(buf, off + 0x1C)

    return {
        "offset": off,
        "fourcc": fourcc,
        "type": wrld_type,
        "size": size,
        "global_addr_0": glob0,
        "global_addr_1": glob1,
        "global_count": globcnt,
        "slave_continuation": cont_img,
        "reserved": reserved
    }

def print_single_slave_header(h, log):
    log(f"    @ {hx32(h['offset'])}")
    log(f"      0x00 fourCC                 : {h['fourcc']!r}")
    log(f"      0x04 type                   : {hx32(h['type'])} ({'Master' if h['type']==1 else 'Slave' if h['type']==0 else 'Unknown'})")
    log(f"      0x08 size                   : {hx32(h['size'])} ({h['size']})")
    log(f"      0x0C global section addr    : {hx32(h['global_addr_0'])}")
    log(f"      0x10 global section addr    : {hx32(h['global_addr_1'])} (repeat)")
    log(f"      0x14 global offsets count   : {hx32(h['global_count'])} ({h['global_count']})")
    log(f"      0x18 slave continuation IMG : {hx32(h['slave_continuation'])}")
    log(f"      0x1C reserved               : {hx32(h['reserved'])}")

#######################################################
# Pretty printing blocks and tables (mirrored to log)
#######################################################
def print_block_as_dwords(block_name, start_off, data_bytes, log, start_index=0):
    n = len(data_bytes)
    log(f"\n{block_name}")
    log(f"  bytes: {n} (start @ {hx32(start_off)})")
    if n == 0:
        log("  (empty)")
        return

    word_count = n // 4
    if word_count:
        log("  index |        dword")
        for i in range(word_count):
            s = i * 4
            word = int.from_bytes(data_bytes[s:s+4], "little", signed=False)
            log(f"  {start_index + i:5d} | {hx32(word)}")

    tail = n % 4
    if tail:
        tb = data_bytes[-tail:]
        idx = start_index + word_count
        hex_tail = " ".join(f"{x:02X}" for x in tb)
        log(f"  {idx:5d} | tail bytes ({tail}): {hex_tail}")

def print_groups_table(groups_info, log):
    log("\nSlave WRLD groups (walked BEFORE resource ID table)")
    log(f"  entries: {len(groups_info)}\n")
    log("  idx |  LVZ group addr | X shift     | members | total bytes | trailing")
    for i, g in enumerate(groups_info):
        log(f"  {i:3d} | {hx32(g['addr'])}      | {hx32(g['xshift'])} | {g['members']:7d} | {g['total_bytes']:11d} | {g['trailing_bytes']:8d}")

def print_resource_addr_table(rtab, log):
    log("\nResource Address Table (parsed AFTER groups)")
    log(f"  start @ {hx32(rtab['start_off'])}")
    log(f"  expected pairs (count*2): {rtab['expected_pairs']}")
    log(f"  actual pairs read       : {rtab['actual_pairs']}")
    log(f"  bytes consumed          : {rtab['bytes_consumed']}")
    log(f"  end @ {hx32(rtab['end_off'])}")
    nz = len(rtab['nonzero_ids'])
    log(f"  non-zero resource IDs   : {nz}")

    if rtab['actual_pairs']:
        log("\n  idx |     res_id | filler (should be 0)")
        for i, (rid, fil) in enumerate(rtab["pairs"]):
            log(f"  {i:4d} | {hx32(rid)} | {hx32(fil)}")

#######################################################
# Walk and print each group's Slave WRLD 32-byte headers (LVZ)
#######################################################
def print_group_slave_headers(lvz_bytes, groups_info, log):
    log("\nPer-group Slave WRLD 32-byte headers (LVZ-only)")
    if not groups_info:
        log("  (no groups)")
        return

    for gi, g in enumerate(groups_info):
        addr = g["addr"]
        members = g["members"]
        log(f"\nGroup {gi} @ {hx32(addr)}  (members: {members})")
        if members == 0:
            log("  (no headers detected in this group window)")
            continue

        ptr = addr
        for mi in range(members):
            if ptr + 32 > len(lvz_bytes):
                log(f"  member {mi}: stop (would overrun EOF at {hx32(ptr)})")
                break
            if lvz_bytes[ptr:ptr+4] != b"DLRW":
                log(f"  member {mi}: stop (fourCC not 'DLRW' at {hx32(ptr)})")
                break

            try:
                h = parse_slave_wrld_header(lvz_bytes, ptr)
            except Exception as e:
                log(f"  member {mi}: parse error at {hx32(ptr)}: {e}")
                break

            log(f"  member {mi}:")
            print_single_slave_header(h, log)
            ptr += 32

#######################################################
# Collect all
#######################################################
def collect_slave_continuations(lvz_bytes, groups_info):
    continuations = []  # list of dicts
    for gi, g in enumerate(groups_info):
        addr = g["addr"]
        members = g["members"]
        ptr = addr
        for mi in range(members):
            if ptr + 32 > len(lvz_bytes):
                break
            if lvz_bytes[ptr:ptr+4] != b"DLRW":
                break
            h = parse_slave_wrld_header(lvz_bytes, ptr)
            cont = h["slave_continuation"]
            continuations.append({
                "group_index": gi,
                "member_index": mi,
                "lvz_header_offset": ptr,
                "img_cont_offset": cont
            })
            ptr += 32
    return continuations

#######################################################
# Parse IMG Slave WRLD header 
#######################################################
def parse_img_slave_header(img_bytes, off):
    """
    Base layout (48 bytes):
      0x00 u32  res_id_table_addr
      0x04 u16  res_count
      0x06 u16  unk_06 (often 0x12)
      0x08 [8]*u32 ipl_addrs
      0x28 u16  triggered_count
      0x2A u16  flag_2A (often 0x12)
    Optional:
      0x4C u32  triggered_table_addr (print when present)
    """
    need = off + 0x30  # 48 bytes minimum
    if need > len(img_bytes):
        raise ValueError(f"IMG EOF before 48-byte Slave WRLD header at {hx32(off)}")

    res_id_table = read_u32_le(img_bytes, off + 0x00)
    res_count    = read_u16_le(img_bytes, off + 0x04)
    unk_06       = read_u16_le(img_bytes, off + 0x06)
    ipl_addrs = []
    ipl_base = off + 0x08
    for i in range(8):
        ipl_addrs.append(read_u32_le(img_bytes, ipl_base + 4*i))
    triggered_count = read_u16_le(img_bytes, off + 0x28)
    flag_2A         = read_u16_le(img_bytes, off + 0x2A)

    # 0x4C field 
    triggered_table_addr = None
    if off + 0x50 <= len(img_bytes):
        triggered_table_addr = read_u32_le(img_bytes, off + 0x4C)

    return {
        "offset": off,
        "res_id_table_addr": res_id_table,
        "res_count": res_count,
        "unk_06": unk_06,
        "ipl_addrs": ipl_addrs,
        "triggered_count": triggered_count,
        "flag_2A": flag_2A,
        "triggered_table_addr": triggered_table_addr
    }

def print_img_slave_header(h, log):
    log(f"    @ {hx32(h['offset'])}")
    log(f"      0x00 res_id_table_addr     : {hx32(h['res_id_table_addr'])}")
    log(f"      0x04 res_count             : {hx16(h['res_count'])} ({h['res_count']})")
    log(f"      0x06 unk_06                : {hx16(h['unk_06'])}")
    for i, a in enumerate(h["ipl_addrs"]):
        log(f"      0x08+{i*4:02X} IPL[{i}] addr        : {hx32(a)}")
    log(f"      0x28 triggered_count       : {hx16(h['triggered_count'])} ({h['triggered_count']})")
    log(f"      0x2A flag_2A               : {hx16(h['flag_2A'])}")
    if h["triggered_table_addr"] is not None:
        log(f"      0x4C triggered_table_addr  : {hx32(h['triggered_table_addr'])}")
    else:
        log(f"      0x4C triggered_table_addr  : (not present in 48-byte header)")

#######################################################
# Drive the IMG crawl 
#######################################################
def crawl_img_slave_headers(img_path: Path, lvz_bytes: bytes, groups_info, log):
    log("\n===== IMG Slave WRLD headers (by LVZ group/member) =====")
    if not img_path.exists():
        log(f"[WARN] IMG file not found: {img_path}")
        return

    try:
        img_bytes = img_path.read_bytes()
        log(f"Read IMG bytes: {len(img_bytes)}")
    except Exception as e:
        log(f"[ERROR] failed to read IMG: {e}")
        return

    conts = collect_slave_continuations(lvz_bytes, groups_info)
    if not conts:
        log("No Slave WRLD continuations collected from LVZ.")
        return

    last_group = -1
    for entry in conts:
        gi = entry["group_index"]
        mi = entry["member_index"]
        img_off = entry["img_cont_offset"]

        if gi != last_group:
            log(f"\nGroup {gi} (from LVZ) — IMG continuations:")
            last_group = gi

        if img_off == 0:
            log(f"  member {mi}: IMG continuation is 0x00000000 (none)")
            continue
        if img_off >= len(img_bytes):
            log(f"  member {mi}: IMG continuation {hx32(img_off)} beyond IMG EOF ({len(img_bytes)} bytes)")
            continue

        log(f"  member {mi}: IMG header @ {hx32(img_off)}")
        try:
            h = parse_img_slave_header(img_bytes, img_off)
        except Exception as e:
            log(f"    parse error at {hx32(img_off)}: {e}")
            continue

        print_img_slave_header(h, log)

#######################################################
def print_wrld_report(lvz_path_str, img_path_str, hdr, dir_info, groups_info, rtab, log):
    log(f"\n===== Leeds LVZ/IMG Inspector =====")
    log(f"Selected LVZ/BIN: {lvz_path_str}")
    log(f"Associated IMG:   {img_path_str}\n")

    log("WRLD Master Header (global)")
    log(f"  0x00 fourCC                : {hdr['fourcc']!r}")
    log(f"  0x04 shrink                : {hx32(hdr['shrink'])} ({hdr['shrink']})")
    log(f"  0x08 file size             : {hx32(hdr['file_size'])} ({hdr['file_size']})")
    log(f"  0x0C global section addr   : {hx32(hdr['global_addr_0'])}")
    log(f"  0x10 global section addr   : {hx32(hdr['global_addr_1'])} (repeat)")
    log(f"  0x14 global offsets count  : {hx32(hdr['global_count'])} ({hdr['global_count']})")
    log(f"  0x18 slave continuation IMG: {hx32(hdr['slave_continuation'])}")
    log(f"  0x1C reserved              : {hx32(hdr['reserved'])}")
    log("")
    log("Resource Identity Table pointer")
    log(f"  0x20 resource id table     : {hx32(hdr['resource_id_table'])}")

    log("\nSlave WRLD groups directory (LVZ-local addresses)")
    log(f"  directory start @ {hx32(0x24)}")
    log(f"  entries: {len(dir_info['entries'])}")
    if dir_info['entries']:
        log("\n  index | LVZ offset | X shift")
        for i, (addr, xshift) in enumerate(dir_info['entries']):
            log(f"  {i:5d} | {hx32(addr)} | {hx32(xshift)}")

    log("\nGroup count (u16) and reserved")
    log(f"  count    @ {hx32(dir_info['count_off'])} : {dir_info['count_u16']} ({hx16(dir_info['count_u16'])})")
    log(f"  reserved @ {hx32(dir_info['count_off']+2)} : {dir_info['reserved_u16']} ({hx16(dir_info['reserved_u16'])})")

    log(f"\nDirectory/technical sizing")
    log(f"  directory bytes            : {dir_info['dir_bytes']}")
    log(f"  dir + count bytes          : {dir_info['dir_plus_count_bytes']}")
    log(f"  technical block bytes      : {len(dir_info['pad_bytes'])} (mirrored)")

    print_block_as_dwords(
        "Technical mirror block (same length as directory+count)",
        dir_info['pad_start'],
        dir_info['pad_bytes'],
        log,
        start_index=len(dir_info['entries'])
    )

    print_groups_table(groups_info, log)

    print_group_slave_headers(lvz_bytes=data_global_bytes_cache, groups_info=groups_info, log=log)

    print_resource_addr_table(rtab, log)

#######################################################
# Operator
#######################################################
data_global_bytes_cache = b""

class LeedsImportLVZGroups(Operator, ImportHelper):
    bl_idname = "import_scene.leeds_lvz_groups"
    bl_label = "R* Leeds: LVZ groups (.lvz/.bin)"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".lvz"
    filter_glob: StringProperty(
        name="File Filter",
        default="*.lvz;*.LVZ;*.bin;*.BIN",
        options={'HIDDEN'},
    )

    def execute(self, context):
        global data_global_bytes_cache

        lvz_path = Path(self.filepath)
        img_path = lvz_path.with_suffix(".img")

        desired_log_name = f"{lvz_path.stem}_import_log"
        desired_log_path = lvz_path.with_name(desired_log_name)

        log = DebugLog(desired_log_path)
        log.log(f"LVZ path: {lvz_path}")
        log.log(f"IMG path: {img_path}")
        log.log("")

        try:
            try:
                raw = lvz_path.read_bytes()
                log.log(f"Read LVZ bytes: {len(raw)}")
            except Exception as e:
                log.log(f"[ERROR] failed to read LVZ: {e}")
                log.write_out()
                self.report({'ERROR'}, f"failed to read file: {e}")
                return {'CANCELLED'}

            data = ensure_wrld_bytes(raw)
            if data[:4] != b"DLRW":
                msg = "DLRW not found (not a WRLD header after optional zlib)."
                log.log(f"[ERROR] {msg}")
                log.write_out()
                self.report({'ERROR'}, msg)
                return {'CANCELLED'}

            data_global_bytes_cache = data
            log.log("Confirmed WRLD magic 'DLRW' at 0x00")
            log.log(f"Decompressed/Raw size in memory: {len(data)}")
            log.log("")

            try:
                hdr = parse_wrld_header(data)
                dir_info = parse_group_directory_and_tech(data, start_off=0x24)
                groups_info = count_headers_in_groups(data, dir_info["entries"])

                res_tab_off = hdr["resource_id_table"]
                if res_tab_off >= len(data):
                    raise ValueError(f"resource address table offset {hx32(res_tab_off)} beyond EOF ({len(data)} bytes)")

                rtab = parse_resource_address_table(
                    data,
                    start_off=res_tab_off,
                    group_count_u16=dir_info["count_u16"]
                )
            except Exception as e:
                log.log(f"[ERROR] parse error: {e}")
                log.log("Traceback:")
                tb = traceback.format_exc()
                for line in tb.rstrip().splitlines():
                    log.log(line)
                log.write_out()
                self.report({'ERROR'}, f"parse error: {e}")
                return {'CANCELLED'}

            print_wrld_report(str(lvz_path), str(img_path), hdr, dir_info, groups_info, rtab, log)
            log.log(f"\n[summary] resource address table bytes (count): {dir_info['count_u16']}")

            crawl_img_slave_headers(img_path, data_global_bytes_cache, groups_info, log)

            self.report({'INFO'}, "LVZ groups + per-group headers + resource address table + IMG headers parsed. See console and log.")

        finally:
            log.write_out()

        return {'FINISHED'}

#######################################################
def menu_func_import(self, context):
    self.layout.operator(LeedsImportLVZGroups.bl_idname, text=LeedsImportLVZGroups.bl_label)

def register():
    bpy.utils.register_class(LeedsImportLVZGroups)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.utils.unregister_class(LeedsImportLVZGroups)

if __name__ == "__main__":
    register()
