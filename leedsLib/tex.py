
# BLeeds - Scripts for working with R* Leeds (GTA Stories, Chinatown Wars, Manhunt 2, etc) formats in Blender
# Author: spicybung
# Years: 2025 -
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import os
import io
import bpy

from bpy.types import Operator
from bpy.props import StringProperty, IntProperty
from bpy_extras.io_utils import ImportHelper
from bpy.types import TOPBAR_MT_file_import

#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
#   This script is for .CHK/.XTX/.TEX - dictionaries for LCS/VCS/CW/MH2 textures    #
#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
# - Script resources:
# • https://gtamods.com/wiki/Relocatable_chunk (pre-process)
# • https://web.archive.org/web/20180729204205/http://gtamodding.ru/wiki/CHK (... .xtx, .tex)
# - Mod resources/cool stuff:
# • https://libertycity.net/files/gta-liberty-city-stories/48612-yet-another-img-editor.html (extract textures)
# • https://gtaforums.com/topic/518948-rel-gta-stories-texture-explorer-20/ (view/explore textures)
# • https://www.dixmor-hospital.com/mhs/index.php (Manhunt 2)


#######################################################
def u8(b: bytes, off: int) -> int:
    return b[off]
#######################################################
def u24(b: bytes, off: int) -> int:
    return b[off] | (b[off + 1] << 8) | (b[off + 2] << 16)
#######################################################
def u32(b: bytes, off: int) -> int:
    return int.from_bytes(b[off:off+4], byteorder="little", signed=False)
#######################################################
def cstr64(b: bytes) -> str:
    n = b.find(0)
    if n == -1:
        n = len(b)
    return b[:n].decode("ascii", "replace")
#######################################################
def read_block(fp: io.BufferedReader, offset: int, size: int):
    here = fp.tell()
    try:
        fp.seek(offset, os.SEEK_SET)
        data = fp.read(size)
        if not data or len(data) < size:
            return (None, 0 if not data else len(data))
        return (data, len(data))
    finally:
        fp.seek(here, os.SEEK_SET)

#######################################################
def parse_collection_header(fp):
    head, fsz = read_block(fp, 0, 0x30)
    if head is None:
        raise RuntimeError("file too small")
    return {
        "sig": head[0:4].decode("ascii","replace"),
        "plat": u32(head,0x04),
        "fsz": fsz,
        "coll_size": u32(head,0x08),
        "glob1": u32(head,0x0C),
        "glob2": u32(head,0x10),
        "glob_count": u32(head,0x14),
        "cont_byte": u8(head,0x20),
        "flags24": u24(head,0x21),
        "first_slot": u32(head,0x28),
        "last_slot":  u32(head,0x2C),
    }

#######################################################
def parse_container_from_current(fp):
  
    base = fp.tell()
    block, fsz = read_block(fp, base, 16 + 64)  # 80 bytes total
    if block is None:
        return None
    tex_off   = u32(block, 0x00)
    coll      = u32(block, 0x04)
    next_slot = u32(block, 0x08)
    prev_slot = u32(block, 0x0C)
    name      = cstr64(block[0x10:0x10+64])
    return {
        "base": base,
        "tex_off": tex_off,
        "coll": coll,
        "prev_slot": prev_slot,
        "next_slot": next_slot,
        "name": name,
        "fsz": fsz,
    }

#######################################################
def hex_dump_around(fp, center_pos: int, span: int = 16) -> str:
    keep = fp.tell()
    try:
        fp.seek(center_pos, os.SEEK_SET)
        data = fp.read(span) or b""
    finally:
        fp.seek(keep, os.SEEK_SET)
    return " ".join(f"{b:02X}" for b in data)
#######################################################
def read_rasterinfo(fp: io.BufferedReader, offset: int, file_size: int) -> dict:
    """
    Read the 16-byte rasterinfo structure at 'offset':
      +0x00 u32 reserved0
      +0x04 u16 count_a
      +0x06 u16 count_b
      +0x08 u32 image_info
      +0x0C u32 flags
    """
    here = fp.tell()
    try:
        if offset <= 0 or offset + 16 > file_size:
            return {"present": False, "reason": f"rasterinfo out of bounds (off=0x{offset:08X})"}
        fp.seek(offset, os.SEEK_SET)
        data = fp.read(16)
        if not data or len(data) < 16:
            return {"present": False, "reason": "short read for rasterinfo"}

        reserved0 = u32(data, 0x00)
        count_a   = int.from_bytes(data[0x04:0x06], "little", signed=False)
        count_b   = int.from_bytes(data[0x06:0x08], "little", signed=False)
        image_info= u32(data, 0x08)
        flags     = u32(data, 0x0C)

        return {
            "present": True,
            "reserved0": reserved0,
            "count_a": count_a,
            "count_b": count_b,
            "image_info": image_info,
            "flags": flags,
            "raw_hex": " ".join(f"{b:02X}" for b in data),
        }
    finally:
        fp.seek(here, os.SEEK_SET)

#######################################################
def print_rasterinfo_info(rinfo: dict, idx: int):
    """
    Console dump for the rasterinfo block of a slot.
    """
    print(f"rasterinfo (slot {idx}):")
    if not rinfo.get("present", False):
        print(f"  present    : False ({rinfo.get('reason', 'unknown reason')})")
        print("==============================================================")
        return
    print("  present    : True")
    print(f"  reserved0  : 0x{rinfo['reserved0']:08X}")
    print(f"  count_a    : {rinfo['count_a']} (0x{rinfo['count_a']:04X})")
    print(f"  count_b    : {rinfo['count_b']} (0x{rinfo['count_b']:04X})")
    print(f"  image_info : 0x{rinfo['image_info']:08X} ({rinfo['image_info']})")
    print(f"  flags      : 0x{rinfo['flags']:08X}")
    print(f"  raw(16)    : {rinfo['raw_hex']}")
    print("==============================================================")

#######################################################
def print_header_info(hdr: dict, file_size: int):
    print("==============================================================")
    print("Collection Header")
    print("--------------------------------------------------------------")
    print(f"sig         : {hdr['sig']!r}")
    print(f"plat        : 0x{hdr['plat']:08X}")
    print(f"fsz(read)   : 0x{hdr['fsz']:X} ({hdr['fsz']})")
    print(f"file_size   : 0x{file_size:X} ({file_size})")
    print(f"coll_size   : 0x{hdr['coll_size']:X} ({hdr['coll_size']})")
    print(f"glob1       : 0x{hdr['glob1']:08X}")
    print(f"glob2       : 0x{hdr['glob2']:08X}")
    print(f"glob_count  : {hdr['glob_count']}")
    print(f"cont_byte   : 0x{hdr['cont_byte']:02X}")
    print(f"flags24     : 0x{hdr['flags24']:06X}")
    print(f"first_slot  : 0x{hdr['first_slot']:08X} ({hdr['first_slot']})")
    print(f"last_slot   : 0x{hdr['last_slot']:08X} ({hdr['last_slot']})")
    print("==============================================================")

#######################################################
def print_container_info(cinfo: dict, idx: int = None):
    if idx is not None:
        print(f"# Slot {idx}")
    print("Container summary (parsed from current position)")
    print("--------------------------------------------------------------")
    print(f"container base        : 0x{cinfo['base']:08X} ({cinfo['base']})")
    print(f"texture offset: 0x{cinfo['tex_off']:08X} ({cinfo['tex_off']})")
    print(f"collection header: 0x{cinfo['coll']:08X} ({cinfo['coll']})")
    print(f"previous slot: 0x{cinfo['prev_slot']:08X} ({cinfo['prev_slot']})")
    print(f"next slot: 0x{cinfo['next_slot']:08X} ({cinfo['next_slot']})")
    print(f"texture name: {cinfo['name']!r}")
    print(f"blocksize(read): {cinfo['fsz']}")
    print("==============================================================")

#######################################################
def _slot_base_from_slot_ptr(slot_ptr: int) -> int:
    return max(0, slot_ptr - 0x08)

#######################################################
def iterate_slots(fp, first_slot: int, last_slot: int, file_size: int, expected_count: int):

    if first_slot <= 0 or first_slot >= file_size:
        print(f"[warn] first_slot 0x{first_slot:08X} is out of file bounds, aborting iteration.")
        return

    visited = set()
    idx = 0

    # Seek to the first container base
    first_base = _slot_base_from_slot_ptr(first_slot)
    fp.seek(first_base, os.SEEK_SET)

    while True:
        here = fp.tell()
        if here in visited:
            print(f"[stop] container base 0x{here:08X} has already been visited (cycle detected).")
            break
        visited.add(here)

        # Read and print this container
        cinfo = parse_container_from_current(fp)
        if cinfo is None:
            print(f"[stop] could not read container at base 0x{here:08X}.")
            break

        print_container_info(cinfo, idx=idx)

        rinfo = read_rasterinfo(fp, cinfo["tex_off"], file_size)
        print_rasterinfo_info(rinfo, idx=idx)

        idx += 1
        if expected_count and idx >= expected_count:
            print(f"[stop] reached expected slot count ({expected_count}).")
            break

        # Decide where to go next
        nxt = cinfo["next_slot"]
        if nxt == 0:
            print("[stop] next_slot == 0 (null).")
            break
        if nxt >= file_size:
            print(f"[stop] next_slot 0x{nxt:08X} is out of bounds (>= file size).")
            break

        # Compute next container base from slot pointer and seek
        nxt_base = _slot_base_from_slot_ptr(nxt)
        fp.seek(nxt_base, os.SEEK_SET)

        # As a safety, also stop if we arrived at the last slot's base and its next
        # would circle oddly. This gives us a bound when header exposes last_slot.
        if last_slot and _slot_base_from_slot_ptr(last_slot) == nxt_base:
            # We'll still parse it in next loop round; after that, whichever pointer it has will decide.
            pass

#######################################################
class IMPORT_OT_collection_header(Operator, ImportHelper):
    bl_idname = "import_scene.collection_header_leeds_cw"
    bl_label = "Import TXD (Iterate Slots)"
    bl_options = {"REGISTER", "UNDO"}
    filename_ext = ".xtx"
    filter_glob: StringProperty(default="*.xtx;*.chk;*.tex;*.XTX;*.CHK;*.TEX", options={'HIDDEN'})

    #######################################################
    def execute(self, context):
        path = self.filepath
        if not path or not os.path.isfile(path):
            self.report({'ERROR'}, "No file selected or path is invalid")
            return {'CANCELLED'}

        try:
            with open(path, "rb") as fp:
                # File size
                fp.seek(0, os.SEEK_END)
                file_size = fp.tell()
                fp.seek(0, os.SEEK_SET)

                # Read header and print
                hdr = parse_collection_header(fp)
                print_header_info(hdr, file_size)

                # ========== Phase A: Show the seek report for the first slot (as before) ==========
                first_slot = hdr["first_slot"]
                last_slot  = hdr["last_slot"]
                if first_slot >= file_size:
                    self.report({'WARNING'}, f"first_slot (0x{first_slot:08X}) beyond EOF")
                    return {'CANCELLED'}

                fp.seek(first_slot, os.SEEK_SET)
                pos_after_first = fp.tell()
                back_by = 8
                new_pos = max(0, pos_after_first - back_by)
                fp.seek(new_pos, os.SEEK_SET)

                print("---- Seek report --------------------------------------------")
                print(f"Seeked to first_slot:  0x{first_slot:08X} ({first_slot})")
                print(f"Then jumped back 0x{back_by:X} ({back_by}) bytes")
                print(f"Current position:      0x{fp.tell():08X} ({fp.tell()})")
                print(f"Hex @ current pos (16 bytes): {hex_dump_around(fp, fp.tell(), 16)}")
                print("--------------------------------------------------------------")

                # Parse and print the very first container at this base (for continuity)
                cinfo = parse_container_from_current(fp)
                if cinfo is None:
                    self.report({'ERROR'}, "Container parse failed at current position")
                    return {'CANCELLED'}
                print_container_info(cinfo, idx=0)

                rinfo0 = read_rasterinfo(fp, cinfo["tex_off"], file_size)
                print_rasterinfo_info(rinfo0, idx=0)

                # ========== Phase B: Iterate forward through the slot chain, 80 bytes each ==========
                print("=============== Iterating through slot chain (80 bytes each) ===============")
                # We already printed idx 0 above; start the loop from the next one.
                # iterate_slots() itself will print starting again from idx 0, so to avoid a duplicate
                # we move the file pointer to the *next* container before calling it.
                nxt = cinfo["next_slot"]
                if nxt and nxt < file_size:
                    fp.seek(max(0, nxt - 8), os.SEEK_SET)
                    # We pass glob_count as an upper bound if reasonable (>0)
                    exp_cnt = hdr["glob_count"] if hdr["glob_count"] > 0 else 0
                    # We printed 1 already, so if using expected count, subtract one so we end exactly.
                    exp_cnt = max(0, exp_cnt - 1) if exp_cnt else 0
                    iterate_slots(fp, nxt, last_slot, file_size, exp_cnt)
                else:
                    print("[info] next_slot of the first container is null or out-of-bounds; no iteration performed.")
                print("=============================================================================")

        except Exception as e:
            self.report({'ERROR'}, f"Error: {e}")
            raise

        self.report({'INFO'}, "Done. See system console for detailed output.")
        return {'FINISHED'}

#######################################################
def menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_collection_header.bl_idname,
                         text="R* Leeds: Texture Dictionary (.chk/.xtx/.tex)")

def register():
    bpy.utils.register_class(IMPORT_OT_collection_header)
    TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.utils.unregister_class(IMPORT_OT_collection_header)

if __name__ == "__main__":
    register()
