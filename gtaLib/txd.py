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

import os
import io
import bpy

from bpy.types import Operator
from bpy.props import StringProperty, IntProperty
from bpy_extras.io_utils import ImportHelper
from bpy.types import TOPBAR_MT_file_import


#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
#   This script is for .CHK/XTX/TEX - dictionaries for LCS/VCS/CW/MH2 textures      #
#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
# - Script resources:
# • https://gtamods.com/wiki/Relocatable_chunk (pre-process)
# • https://web.archive.org/web/20180729204205/http://gtamodding.ru/wiki/CHK (.xtx, .tex)
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
    block, fsz = read_block(fp, base, 16 + 64)
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
def print_container_info(cinfo: dict):
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
class IMPORT_OT_collection_header(Operator, ImportHelper):
    bl_idname = "import_scene.collection_header_leeds_cw"
    bl_label = "Import TXD"
    bl_options = {"REGISTER", "UNDO"}
    filename_ext = ".xtx"
    filter_glob: StringProperty(default="*.xtx;*.chk;*.XTX;*.CHK", options={'HIDDEN'})

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

                # Read header
                hdr = parse_collection_header(fp)
                print_header_info(hdr, file_size)

                # Seek to first_slot, then back 8 bytes
                first_slot = hdr["first_slot"]
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

                # Parse container from CURRENT POSITION
                cinfo = parse_container_from_current(fp)
                if cinfo is None:
                    self.report({'ERROR'}, "Container parse failed at current position")
                    return {'CANCELLED'}

                print_container_info(cinfo)

        except Exception as e:
            self.report({'ERROR'}, f"Error: {e}")
            raise

        self.report({'INFO'}, "Done. See system console for output.")
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
