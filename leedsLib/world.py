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
# • https://web.archive.org/web/20180729202923/http://gtamodding.ru/wiki/WRLD (Russian - not the best resource but info is scarce)
# • https://web.archive.org/web/20180729204205/http://gtamodding.ru/wiki/CHK (Russian - WRLD textures)
# • https://github.com/aap/librwgta/blob/master/tools/storiesview/worldstream.cpp
# • https://web-archive-org.translate.goog/web/20180810183857/http://gtamodding.ru/wiki/LVZ?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (English)
# • https://web-archive-org.translate.goog/web/20180807031320/http://www.gtamodding.ru/wiki/IMG?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (ditto)
# • https://web-archive-org.translate.goog/web/20180729204205/http://gtamodding.ru/wiki/CHK?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (ditto - WRLD textures)
# - Mod resources/cool stuff:
# • https://gtaforums.com/topic/285544-gtavcslcs-modding/ (includes unimg.exe for Stories)
# • https://github.com/electronicarts/RenderWare3Docs/blob/master/whitepapers/worlds.pdf (Leeds Worlds are based on RW Worlds)
# • https://lcsteam.net/community/forum/index.php/topic,337.msg9335.html#msg9335 (RW 3.7/4.0, .MDL's, .WRLD's, .BSP's... )
# • https://vk.com/video143954957_456239416 (Russian - Leeds Worlds explained)


#######################################################
# Helpers
#######################################################
def read_u32_le(buf, off):
    return struct.unpack_from("<I", buf, off)[0]
#######################################################
def read_u16_le(buf, off):
    return struct.unpack_from("<H", buf, off)[0]
#######################################################
def read_fourcc(buf, off):
    return buf[off:off+4].decode("ascii", errors="ignore")
#######################################################
def looks_like_zlib(buf):
    return len(buf) >= 2 and buf[0] == 0x78 and buf[1] in (0x01, 0x9C, 0xDA)
#######################################################
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

#######################################################
# WRLD header parsing
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
# Slave WRLD groups directory + technical sector
#######################################################
def parse_slave_group_directory(buf, start_off=0x24, safety_pairs=4096):
    
    off = start_off
    dir_begin = off
    entries = []

    for _ in range(safety_pairs):
        if off + 4 > len(buf):
            raise ValueError("unexpected end while peeking directory dword")

        peek = read_u32_le(buf, off)

        # zero dword → likely end of address list in some builds
        if peek == 0:
            off += 4
            break

        # If upper 16 bits are zero, treat this as start of u16 count/reserved.
        if (peek & 0xFFFF0000) == 0:
            break

        if off + 8 > len(buf):
            raise ValueError("unexpected end while reading a directory pair")

        addr = peek
        x_shift = read_u32_le(buf, off + 4)
        entries.append((addr, x_shift))
        off += 8

    # Read the u16 count + u16 reserved
    if off + 4 > len(buf):
        raise ValueError("missing u16 count + u16 reserved after directory")

    count_off = off
    count_u16 = read_u16_le(buf, off)
    reserved_off = off + 2
    reserved_u16 = read_u16_le(buf, reserved_off)
    off += 4

    # Technical mirror block length equals bytes used by (directory + count/reserved)
    dir_and_count_len = off - dir_begin
    tech_len = dir_and_count_len

    pad_start = off
    actual_len = min(tech_len, len(buf) - off)
    padding_bytes = buf[pad_start:pad_start + actual_len]
    off += actual_len

    return {
        "entries": entries,
        "count_u16": count_u16,
        "count_off": count_off,
        "reserved_u16": reserved_u16,
        "reserved_off": reserved_off,
        "pad_start": pad_start,
        "padding_bytes": padding_bytes,
        "next_block_offset": off,
        "start_offset": start_off,
        "dir_bytes": (count_off - dir_begin),
        "dir_plus_count_bytes": dir_and_count_len,
        "tech_block_bytes": actual_len,
    }

#######################################################
# Post-technical
#######################################################
def parse_post_padding_block(buf, off):

    need = off + 8 * 4
    if need > len(buf):
        raise ValueError("not enough bytes for post-padding 8 dwords")
    vals = [read_u32_le(buf, off + i * 4) for i in range(8)]
    offs = [off + i * 4 for i in range(8)]
    return {
        "base_off": off,
        "time_rows": vals[0],   "time_rows_off": offs[0],
        "time_addr": vals[1],   "time_addr_off": offs[1],
        "fx_rows":   vals[2],   "fx_rows_off":   offs[2],
        "fx_addr":   vals[3],   "fx_addr_off":   offs[3],
        "int_rows":  vals[4],   "int_rows_off":  offs[4],
        "int_addr":  vals[5],   "int_addr_off":  offs[5],
        "radar_rows":vals[6],   "radar_rows_off":offs[6],
        "radar_addr":vals[7],   "radar_addr_off":offs[7],
    }

#######################################################
# Resource ID table
#######################################################
def parse_resource_id_table(buf, table_off, group_count_u16, max_pairs=None):

    pair_count = int(group_count_u16) * 2
    if max_pairs is not None:
        pair_count = min(pair_count, max_pairs)

    out = []
    off = table_off
    need = off + pair_count * 8
    if need > len(buf):
        raise ValueError(
            f"resource table overruns file: need up to 0x{need:X}, size 0x{len(buf):X}"
        )

    for i in range(pair_count):
        idv  = read_u32_le(buf, off + 0)
        aux  = read_u32_le(buf, off + 4)
        out.append({
            "index": i,
            "off_id": off + 0,
            "id": idv,
            "off_aux": off + 4,
            "aux": aux,
            "empty": (idv == 0),
        })
        off += 8

    return out

#######################################################
# Printing helpers
#######################################################
def hx(v): 
    return f"0x{v:08X}"
#######################################################
def hxb(b): 
    return " ".join(f"{x:02X}" for x in b)
#######################################################
def print_block_as_dwords(block_name, start_off, data_bytes, start_index=0):
    n = len(data_bytes)
    print(f"\n{block_name}")
    print(f"  bytes: {n} (start @ {hx(start_off)})")
    if n == 0:
        print("  (empty)")
        return

    word_count = n // 4
    if word_count:
        print("  index |        dword")
        for i in range(word_count):
            s = i * 4
            word = int.from_bytes(data_bytes[s:s+4], "little", signed=False)
            print(f"  {start_index + i:5d} | {hx(word)}")

    tail = n % 4
    if tail:
        tb = data_bytes[-tail:]
        idx = start_index + word_count
        print(f"  {idx:5d} | tail bytes ({tail}): {hxb(tb)}")
#######################################################
def print_post_block(block):
    print("\nPost-technical tables (8 dwords right after technical block)")
    print(f"  start @ {hx(block['base_off'])}")
    def line(name, val, off_note, note=""):
        print(f"  {name:<28} @ {hx(off_note)} : {hx(val)} ({val}){note}")
    line("timeobjects rows", block["time_rows"], block["time_rows_off"], "  (1 row = 4 bytes)")
    line("timeobjects addr", block["time_addr"], block["time_addr_off"])
    line("2dfx rows",        block["fx_rows"],   block["fx_rows_off"],   "  (1 row = 48 bytes)")
    line("2dfx addr",        block["fx_addr"],   block["fx_addr_off"])
    line("interiors count",  block["int_rows"],  block["int_rows_off"],  "  (1 row = 6 bytes)")
    line("interiors table",  block["int_addr"],  block["int_addr_off"])
    line("radar tex count",  block["radar_rows"],block["radar_rows_off"],"  (LCS only)")
    line("radar starts addr",block["radar_addr"],block["radar_addr_off"],"  (LCS only)")
#######################################################
def print_resource_table(entries, title="Resource Identity Table (group_count * 2 pairs)"):
    nz = sum(1 for e in entries if not e["empty"])
    print(f"\n{title}")
    print(f"  entries parsed : {len(entries)}")
    print(f"  non-empty IDs  : {nz}")
    if not entries:
        return
    print("\n  index |   off(id)  |        id |  off(aux)  |       aux | note")
    for e in entries:
        note = "EMPTY" if e["empty"] else ""
        print(f"  {e['index']:5d} | {hx(e['off_id'])} | {hx(e['id'])} | {hx(e['off_aux'])} | {hx(e['aux'])} | {note}")
#######################################################
def print_wrld_report(lvz_path_str, img_path_str, hdr, dir_info=None, post_block=None, res_entries=None):
    print(f"\n===== Leeds LVZ/IMG Inspector =====")
    print(f"Selected LVZ/BIN: {lvz_path_str}")
    print(f"Associated IMG:   {img_path_str}\n")

    print("WRLD Master Header (global)")
    print(f"  0x00 fourCC                : {hdr['fourcc']!r}")
    print(f"  0x04 shrink                : {hx(hdr['shrink'])} ({hdr['shrink']})")
    print(f"  0x08 file size             : {hx(hdr['file_size'])} ({hdr['file_size']})")
    print(f"  0x0C global section addr   : {hx(hdr['global_addr_0'])}")
    print(f"  0x10 global section addr   : {hx(hdr['global_addr_1'])} (repeat)")
    print(f"  0x14 global offsets count  : {hx(hdr['global_count'])} ({hdr['global_count']})")
    print(f"  0x18 slave continuation IMG: {hx(hdr['slave_continuation'])}")
    print(f"  0x1C reserved              : {hx(hdr['reserved'])}")
    print()
    print("Resource Identity Table pointer")
    print(f"  0x20 resource id table     : {hx(hdr['resource_id_table'])}")

    if dir_info is not None:
        print("\nSlave WRLD Groups Directory (LVZ-local addresses)")
        print(f"  directory start @ {hx(dir_info['start_offset'])}")
        print(f"  entries: {len(dir_info['entries'])}")
        if dir_info['entries']:
            print("\n  index | LVZ offset | X shift")
            for i, (addr, xshift) in enumerate(dir_info['entries']):
                print(f"  {i:5d} | {hx(addr)} | {hx(xshift)}")

        print("\nGroup count (u16) and reserved")
        print(f"  count    @ {hx(dir_info['count_off'])} : {dir_info['count_u16']} (0x{dir_info['count_u16']:04X})")
        print(f"  reserved @ {hx(dir_info['reserved_off'])} : {dir_info['reserved_u16']} (0x{dir_info['reserved_u16']:04X})")

        print(f"\nDirectory/tech sizing")
        print(f"  directory bytes            : {dir_info['dir_bytes']}")
        print(f"  dir + count bytes          : {dir_info['dir_plus_count_bytes']}")
        print(f"  technical block bytes      : {dir_info['tech_block_bytes']} (mirrored)")

        print_block_as_dwords(
            "Technical mirror block (same length as directory+count)",
            dir_info['pad_start'],
            dir_info['padding_bytes'],
            start_index=len(dir_info['entries'])
        )

    if post_block is not None:
        print_post_block(post_block)

    if res_entries is not None:
        print_resource_table(res_entries)

#######################################################
class LeedsImportWRLD(Operator, ImportHelper):
    """R* Leeds WRLD LVZ/BIN inspector (header, groups, technical block, tables, resource IDs)"""
    bl_idname = "import_scene.leeds_wrld_lvz"
    bl_label = "R* Leeds: WRLD LVZ/BIN (.lvz/.bin)"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".lvz"
    filter_glob: StringProperty(
        name="File Filter",
        default="*.lvz;*.LVZ;*.bin;*.BIN",
        options={'HIDDEN'},
    )
    #######################################################
    def execute(self, context):
        lvz_path = Path(self.filepath)
        img_path = lvz_path.with_suffix(".img")  # Associated IMG: same folder + stem

        try:
            raw = lvz_path.read_bytes()
        except Exception as e:
            self.report({'ERROR'}, f"failed to read file: {e}")
            return {'CANCELLED'}

        data = ensure_wrld_bytes(raw)
        if data[:4] != b"DLRW":
            self.report({'ERROR'}, "DLRW not found (not a WRLD header after optional zlib).")
            return {'CANCELLED'}

        try:
            hdr = parse_wrld_header(data)
            dir_info = parse_slave_group_directory(data, start_off=0x24)
            post_block = parse_post_padding_block(data, dir_info["next_block_offset"])
            res_entries = parse_resource_id_table(
                data,
                hdr["resource_id_table"],
                dir_info["count_u16"]
            )
        except Exception as e:
            self.report({'ERROR'}, f"parse error: {e}")
            return {'CANCELLED'}

        print_wrld_report(str(lvz_path), str(img_path), hdr, dir_info, post_block, res_entries)
        self.report({'INFO'}, "LVZ parsed. See console for details.")
        return {'FINISHED'}
#######################################################
def menu_func_import(self, context):
    self.layout.operator(LeedsImportWRLD.bl_idname, text=LeedsImportWRLD.bl_label)

def register():
    bpy.utils.register_class(LeedsImportWRLD)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.utils.unregister_class(LeedsImportWRLD)

if __name__ == "__main__":
    register()
