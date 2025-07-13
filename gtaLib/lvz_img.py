# BLeeds - Scripts for working with R* Leeds (GTA Stories, Manhunt 2, etc) formats in Blender
# Author: SpicyBung
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
import bpy
import zlib
import struct

from bpy.props import StringProperty
from bpy_extras.io_utils import ImportHelper

#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
#   This script is for .LVZ & .IMG respectively - formats for Stories file archives
#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
# - Script resources:
# • https://gtamods.com/wiki/IMG_archive
# • https://web.archive.org/web/20180729202923/http://gtamodding.ru/wiki/WRLD (Russian)
# • https://web.archive.org/web/20180729204205/http://gtamodding.ru/wiki/CHK (Russian - WRLD textures)
# • https://web-archive-org.translate.goog/web/20180810183857/http://gtamodding.ru/wiki/LVZ?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (English)
# • https://web-archive-org.translate.goog/web/20180807031320/http://www.gtamodding.ru/wiki/IMG?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (ditto)
# • https://web-archive-org.translate.goog/web/20180729204205/http://gtamodding.ru/wiki/CHK?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (ditto - WRLD textures)

#######################################################
def padhex(n, w=8):
    return "0x{:0{}X}".format(n, w)
def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]
def u16(b, o):
    return struct.unpack_from("<H", b, o)[0]
def read_cstr(b, o, maxlen=64):
    s = b[o:o+maxlen]
    i = s.find(b'\x00')
    return s[:i].decode('ascii', errors='replace') if i >= 0 else s.decode('ascii', errors='replace')

class LeedsFullLVZIMGInspector(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.leeds_full_lvz_img"
    bl_label = "Leeds Full LVZ/IMG Inspector"
    bl_description = "Fully parse and analyze a Rockstar Leeds LVZ/BIN + IMG, print all sector WRLD info, follow all pointers (no brevity)"
    filename_ext = ".lvz;.bin"
    filter_glob: bpy.props.StringProperty(default="*.lvz;*.bin", options={'HIDDEN'})

    def execute(self, context):
        lvz_path = self.filepath
        base, ext = os.path.splitext(lvz_path)
        # Find matching IMG file in same folder
        img_path = base + ".img"
        if not os.path.isfile(img_path):
            folder = os.path.dirname(lvz_path)
            imgs = [f for f in os.listdir(folder) if f.lower().endswith(".img")]
            if imgs:
                img_path = os.path.join(folder, imgs[0])
            else:
                self.report({'ERROR'}, "No matching IMG file found in folder!")
                return {'CANCELLED'}

        print(f"\n===== Leeds LVZ/IMG Inspector =====")
        print(f"Selected LVZ/BIN: {lvz_path}")
        print(f"Associated IMG:   {img_path}")

        # Load and decompress LVZ
        try:
            with open(lvz_path, "rb") as f:
                lvz_data = f.read()
            is_zlib = lvz_data[:2] in (b'\x78\x9C', b'\x78\xDA', b'\x78\x01')
            if is_zlib:
                decompressed = zlib.decompress(lvz_data)
                print(f"[INFO] Decompressed LVZ. Original size: {len(lvz_data)}, Decompressed size: {len(decompressed)} bytes.")
            else:
                decompressed = lvz_data
                print(f"[INFO] LVZ was not compressed. Size: {len(decompressed)} bytes.")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to open/decompress LVZ: {e}")
            return {'CANCELLED'}

        lvz_size = len(decompressed)

        # Open IMG file for later
        try:
            img_file = open(img_path, "rb")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to open IMG: {e}")
            return {'CANCELLED'}

        # Parse Master WRLD Header at offset 0
        hdr = decompressed[:0x800]
        print("\n--- Master WRLD Header (LVZ offset 0x0) ---")
        signature = hdr[:4]
        wrld_type = u32(hdr, 0x04)
        wrld_size = u32(hdr, 0x08)
        global_tab_1 = u32(hdr, 0x0C)
        global_tab_2 = u32(hdr, 0x10)
        global_tab_count = u32(hdr, 0x14)
        img_cont_addr = u32(hdr, 0x18)
        unused_1C = u32(hdr, 0x1C)
        res_id_table_addr = u32(hdr, 0x20)

        print(f"Signature (should be DLRW): {signature} ({signature.decode(errors='replace')})")
        print(f"WRLD Type: {wrld_type} ({'Master' if wrld_type==1 else 'Slave' if wrld_type==0 else 'Unknown'})")
        print(f"WRLD Size: {wrld_size}")
        print(f"Global Section Address #1: {padhex(global_tab_1)}")
        print(f"Global Section Address #2: {padhex(global_tab_2)}")
        print(f"Global Section Offset Count: {global_tab_count}")
        print(f"IMG Continuation Address: {padhex(img_cont_addr)}")
        print(f"Unused (always 0): {padhex(unused_1C)}")
        print(f"Resource ID Table Address: {padhex(res_id_table_addr)}")

        # Parse Slave WRLD group array after 0x24
        print("\n--- Slave WRLD Group Array (after 0x24) ---")
        offset = 0x24
        slave_groups = []
        while True:
            if offset + 8 > 0x320:
                break
            addr = u32(hdr, offset)
            x_offset = u32(hdr, offset+4)
            if addr == 0 and x_offset == 0:
                break
            # Decide LVZ or IMG
            source = "LVZ" if addr < lvz_size else "IMG"
            print(f"Entry @ {padhex(offset)}: address={padhex(addr)}, x_offset={padhex(x_offset)} [{source}]")
            slave_groups.append((addr, x_offset, source))
            offset += 8
        total_resources = u32(hdr, offset)
        print(f"Total resources in level (after Slave WRLD group array): {total_resources}")

        # Extended tables (Timeobjects, 2dfx, Interiors, Radar, etc.)
        timeobj_count = u32(hdr, 0x320)
        timeobj_table_addr = u32(hdr, 0x324)
        fx_count = u32(hdr, 0x328)
        fx_table_addr = u32(hdr, 0x32C)
        interior_count = u32(hdr, 0x330)
        interior_table_addr = u32(hdr, 0x334)
        radar_tex_count = u32(hdr, 0x338)
        radar_table_addr = u32(hdr, 0x33C)

        print("\n--- Extended Tables ---")
        print(f"Timeobject rows: {timeobj_count} @ {padhex(timeobj_table_addr)}")
        print(f"2dfx effect rows: {fx_count} @ {padhex(fx_table_addr)}")
        print(f"Slave WRLDs with interiors: {interior_count} @ {padhex(interior_table_addr)}")
        print(f"Radar-attached textures: {radar_tex_count} @ {padhex(radar_table_addr)}")

        # Parse each Slave WRLD header referenced
        print("\n--- Parsing all referenced Slave WRLDs ---")
        for i, (addr, x_offset, source) in enumerate(slave_groups):
            if source == "LVZ":
                if addr + 32 > lvz_size:
                    print(f"  [{i}] [LVZ] Address {padhex(addr)} out of LVZ bounds.")
                    continue
                wrld_hdr = decompressed[addr:addr+32]
            else:
                img_file.seek(addr)
                wrld_hdr = img_file.read(32)
            sig = wrld_hdr[:4]
            if sig != b'DLRW':
                print(f"  [{i}] [{source}] Not a WRLD signature at {padhex(addr)}: {sig}")
                continue
            sw_type = u32(wrld_hdr, 0x04)
            sw_size = u32(wrld_hdr, 0x08)
            sw_gsect_addr1 = u32(wrld_hdr, 0x0C)
            sw_gsect_addr2 = u32(wrld_hdr, 0x10)
            sw_gsect_count = u32(wrld_hdr, 0x14)
            sw_img_cont_addr = u32(wrld_hdr, 0x18)
            print(f"\n  Slave WRLD [{i}] @ {padhex(addr)} ({source}):")
            print(f"    Signature: {sig.decode(errors='replace')}")
            print(f"    Type: {sw_type} ({'Master' if sw_type==1 else 'Slave' if sw_type==0 else 'Unknown'})")
            print(f"    WRLD Size: {sw_size}")
            print(f"    Global Section Address: {padhex(sw_gsect_addr1)} (repeat: {padhex(sw_gsect_addr2)})")
            print(f"    Global Section Offset Count: {sw_gsect_count}")
            print(f"    IMG Continuation Address: {padhex(sw_img_cont_addr)}")
            # If this WRLD has an IMG continuation, show what would be loaded
            if sw_img_cont_addr != 0:
                print(f"      [!] This Slave WRLD continues in IMG at {padhex(sw_img_cont_addr)}.")
                img_file.seek(sw_img_cont_addr)
                img_wrld = img_file.read(32)
                img_sig = img_wrld[:4]
                img_type = u32(img_wrld, 0x04)
                img_size = u32(img_wrld, 0x08)
                print(f"      --> IMG WRLD Header: Signature={img_sig}, Type={img_type}, Size={img_size}")

        img_file.close()
        self.report({'INFO'}, "Full parse complete. See system console for detailed output.")
        return {'FINISHED'}

def menu_func_import(self, context):
    self.layout.operator(LeedsFullLVZIMGInspector.bl_idname, text="Full Leeds LVZ/IMG Inspector (No Brevity)")

def register():
    bpy.utils.register_class(LeedsFullLVZIMGInspector)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.utils.unregister_class(LeedsFullLVZIMGInspector)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

if __name__ == "__main__":
    register()
