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
import struct
import traceback

from bpy.types import Operator
from bpy.props import StringProperty
from bpy_extras.io_utils import ImportHelper

#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
#   This script is for .MDL/.WBLs - the format for models in Chinatown Wars PSP/DS
#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
# - Script resources:
# • https://gtamods.com/wiki/Leeds_Engine
# • https://gtamods.com/wiki/MDL (TODO: update stub to include Chinatown Wars documentation)
# • https://web.archive.org/web/20221108130633/http://gtamodding.ru/wiki/GAME.PAK_(Chinatown_Wars)#.D0.9C.D0.BE.D0.B4.D0.B5.D0.BB.D0.B8 (Russian)
# • https://web.archive.org/web/20221108130633/http://gtamodding.ru/wiki/GAME.PAK_(Chinatown_Wars)?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (English)
# - Mod resources/cool stuff:
# • https://gtaforums.com/topic/781150-relctw-chinatown-wars-mobile-resource-explorer/
# • https://web.archive.org/web/20221005045615/https://github.com/DK22Pac/ctw-gxt-tools (in case the repo goes down)

#######################################################
def print_bytes(data, start=0, end=None):
    b = data[start:end]
    hexstr = ' '.join(f"{x:02X}" for x in b)
    print(f"[0x{start:02X}] {hexstr}")
#######################################################
def padhex(n, w=8):
    return "0x{:0{}X}".format(n, w)
#######################################################
def read_u8(data, offset):
    return struct.unpack_from('<B', data, offset)[0]
#######################################################
def read_i8(data, offset):
    return struct.unpack_from('<b', data, offset)[0]
#######################################################
def read_i16(data, offset):
    return struct.unpack_from('<h', data, offset)[0]
#######################################################
def read_u16(data, offset):
    return struct.unpack_from('<H', data, offset)[0]
#######################################################
class ImportWBLPSPSectorOperator(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.wbl_psp_sector"
    bl_label = "Import WBL Sectors (.wbl, PSP float32, BLeeds style)"
    filename_ext = ".wbl"
    filter_glob: StringProperty(default="*.wbl", options={'HIDDEN'})
    #######################################################
    def execute(self, context):
        try:
            with open(self.filepath, "rb") as f:
                file_bytes = f.read()
            header = file_bytes[:0x28]
            print("==== .WBL HEADER HEX DUMP (0x00 - 0x27) ====")
            print_bytes(header, 0, len(header))
            print("==== BEGIN HEADER FIELD INTERPRETATION ====")
            offset = 0
            while offset < len(header):
                if offset + 4 <= len(header):
                    val_u32 = struct.unpack_from("<I", header, offset)[0]
                    print(f"[0x{offset:02X}] u32: {padhex(val_u32)} ({val_u32})")
                if offset + 2 <= len(header):
                    val_u16 = struct.unpack_from("<H", header, offset)[0]
                    print(f"[0x{offset:02X}] u16: {padhex(val_u16,4)} ({val_u16})")
                val_u8 = header[offset]
                print(f"[0x{offset:02X}] u8: {val_u8:02X} ({val_u8})")
                offset += 4

            print("==== 2-BYTE WORD VIEW (header) ====")
            for o in range(0, len(header), 2):
                if o + 2 <= len(header):
                    val = struct.unpack_from("<H", header, o)[0]
                    print(f"[0x{o:02X}] u16: {padhex(val,4)} ({val})")
            print("==== 1-BYTE BYTE VIEW (header) ====")
            for o in range(0, len(header)):
                val = header[o]
                print(f"[0x{o:02X}] u8: {val:02X} ({val})")
            print("==== FLOAT VIEW (header, every 4 bytes) ====")
            for o in range(0, len(header) - 3, 4):
                try:
                    val = struct.unpack_from("<f", header, o)[0]
                    print(f"[0x{o:02X}] float: {val}")
                except struct.error:
                    pass

            # --- Sectors: Each sector is 12 bytes, start at 0x28
            sector_base = 0x28
            for sector_idx in range(4):
                sector_ofs = sector_base + sector_idx * 12
                sec = file_bytes[sector_ofs:sector_ofs + 12]
                print(f"\n==== SECTOR {sector_idx} (0x{sector_ofs:02X} - 0x{sector_ofs+11:02X}) ====")
                print(f"[0x{sector_ofs:02X}] Sector raw bytes: {' '.join(f'{b:02X}' for b in sec)}")

                Bool1 = bool(sec[0])
                Bool2 = bool(sec[1])
                NumInstances = struct.unpack_from("<h", sec, 2)[0]
                NumShadows   = struct.unpack_from("<h", sec, 4)[0]
                NumLevels    = struct.unpack_from("<h", sec, 6)[0]
                NumLights    = struct.unpack_from("<h", sec, 8)[0]
                NumTextures  = struct.unpack_from("<h", sec,10)[0]

                print(f"[0x{sector_ofs:02X}]   Bool1: {Bool1} (byte value: {sec[0]:02X})")
                print(f"[0x{sector_ofs+1:02X}] Bool2: {Bool2} (byte value: {sec[1]:02X})")
                print(f"[0x{sector_ofs+2:02X}] NumInstances (int16): {NumInstances}")
                print(f"[0x{sector_ofs+4:02X}] NumShadows   (int16): {NumShadows}")
                print(f"[0x{sector_ofs+6:02X}] NumLevels    (int16): {NumLevels}")
                print(f"[0x{sector_ofs+8:02X}] NumLights    (int16): {NumLights}")
                print(f"[0x{sector_ofs+10:02X}] NumTextures  (int16): {NumTextures}")
                

                # --- If sector has levels, parse all levels after this sector
                level_ofs = sector_ofs + 12
                for level_idx in range(NumLevels):
                    X = struct.unpack_from("<i", file_bytes, level_ofs)[0] / 4096.0
                    Y = struct.unpack_from("<i", file_bytes, level_ofs + 4)[0] / 4096.0
                    Z = struct.unpack_from("<i", file_bytes, level_ofs + 8)[0] / 4096.0
                    NumInstances_lvl = struct.unpack_from("<h", file_bytes, level_ofs + 12)[0]
                    Flags_lvl        = struct.unpack_from("<h", file_bytes, level_ofs + 14)[0]
                    print(f"    Level {level_idx}:")
                    print(f"      [0x{level_ofs:02X}] X (int32/4096): {X}")
                    print(f"      [0x{level_ofs+4:02X}] Y (int32/4096): {Y}")
                    print(f"      [0x{level_ofs+8:02X}] Z (int32/4096): {Z}")
                    print(f"      [0x{level_ofs+12:02X}] NumInstances (int16): {NumInstances_lvl}")
                    print(f"      [0x{level_ofs+14:02X}] Flags (int16): {Flags_lvl}")
                    level_ofs += 16

                # After all levels, read sector-wide info
                ID          = struct.unpack_from("<h", file_bytes, level_ofs)[0]
                Instances   = struct.unpack_from("<b", file_bytes, level_ofs + 2)[0]
                BuildingSwap= struct.unpack_from("<b", file_bytes, level_ofs + 3)[0]
                ResourceID  = struct.unpack_from("<I", file_bytes, level_ofs + 4)[0]
                MeshOffset  = struct.unpack_from("<I", file_bytes, level_ofs + 8)[0]
                Pointer     = struct.unpack_from("<I", file_bytes, level_ofs + 12)[0]

                print(f"  [0x{level_ofs:02X}] ID (int16): {ID}")
                print(f"  [0x{level_ofs+2:02X}] Instances (int8): {Instances}")
                print(f"  [0x{level_ofs+3:02X}] BuildingSwap (int8): {BuildingSwap}")
                print(f"  [0x{level_ofs+4:02X}] ResourceID (uint32): 0x{ResourceID:08X} ({ResourceID})")
                print(f"  [0x{level_ofs+8:02X}] MeshOffset (uint32): 0x{MeshOffset:08X} ({MeshOffset})")
                print(f"  [0x{level_ofs+12:02X}] Pointer (uint32): 0x{Pointer:08X} ({Pointer})")
                level_ofs += 16 



        except Exception as e:
            tb_str = traceback.format_exc()
            self.report({'ERROR'}, f"Import error: {e}\n{tb_str}")
            print(tb_str)
            return {'CANCELLED'}

        return {'FINISHED'}
#######################################################
def menu_func_import(self, context):
    self.layout.operator(ImportWBLPSPSectorOperator.bl_idname, text="R* Leeds Chinatown Wars Model(.WBL/.MDL)")

def register():
    bpy.utils.register_class(ImportWBLPSPSectorOperator)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.utils.unregister_class(ImportWBLPSPSectorOperator)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

if __name__ == "__main__":
    register()
