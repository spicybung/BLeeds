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
import bmesh

from bpy.types import Operator
from bpy.props import StringProperty
from bpy_extras.io_utils import ImportHelper

#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
#   This script is for .mdl/.wbls - formats for models in GTA:CW Mobile/PSP/DS      #
#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
# - Script resources:
# • https://gtamods.com/wiki/Leeds_Engine (some assets point to CW being made in Unity?)
# • https://gtamods.com/wiki/MDL (TODO: update stub to include Chinatown Wars documentation)
# • https://web.archive.org/web/20221108130633/http://gtamodding.ru/wiki/GAME.PAK_(Chinatown_Wars)#.D0.9C.D0.BE.D0.B4.D0.B5.D0.BB.D0.B8 (*Russian*)
# • https://web.archive.org/web/20221108130633/http://gtamodding.ru/wiki/GAME.PAK_(Chinatown_Wars)?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (*English*)
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
def read_vec3_int4096(data, offset):
    # Read three signed int32s, divide each by 4096
    x = struct.unpack_from('<i', data, offset)[0] / 4096.0
    y = struct.unpack_from('<i', data, offset + 4)[0] / 4096.0
    z = struct.unpack_from('<i', data, offset + 8)[0] / 4096.0
    return (x, y, z)
#######################################################
def read_leeds_cw_transform(data, offset):
    # Diagonal: 32-bit int
    RightX = struct.unpack_from('<i', data, offset)[0] / 4096.0
    # Off-diagonal: 16-bit int
    RightY = struct.unpack_from('<h', data, offset+4)[0] / 4096.0
    RightZ = struct.unpack_from('<h', data, offset+6)[0] / 4096.0
    TopX   = struct.unpack_from('<h', data, offset+8)[0] / 4096.0
    # Diagonal: 32-bit int
    TopY   = struct.unpack_from('<i', data, offset+0x0A)[0] / 4096.0
    TopZ   = struct.unpack_from('<h', data, offset+0x0E)[0] / 4096.0
    AtX    = struct.unpack_from('<h', data, offset+0x10)[0] / 4096.0
    AtY    = struct.unpack_from('<h', data, offset+0x12)[0] / 4096.0
    # Diagonal: 32-bit int
    AtZ    = struct.unpack_from('<i', data, offset+0x14)[0] / 4096.0
    # Padding: 32-bit int
    Padding = struct.unpack_from('<i', data, offset+0x18)[0]
    # Position (translation): 32-bit ints
    PosnX = struct.unpack_from('<i', data, offset+0x1C)[0] / 4096.0
    PosnY = struct.unpack_from('<i', data, offset+0x20)[0] / 4096.0
    PosnZ = struct.unpack_from('<i', data, offset+0x24)[0] / 4096.0

    print("    -Transform")
    print(f"      RightX {RightX:.6f}")
    print(f"      RightY {RightY:.6f}")
    print(f"      RightZ {RightZ:.6f}")
    print(f"      TopX   {TopX:.6f}")
    print(f"      TopY   {TopY:.6f}")
    print(f"      TopZ   {TopZ:.6f}")
    print(f"      AtX    {AtX:.6f}")
    print(f"      AtY    {AtY:.6f}")
    print(f"      AtZ    {AtZ:.6f}")
    print(f"      Padding {Padding}")
    print(f"      PosnX  {PosnX:.6f}")
    print(f"      PosnY  {PosnY:.6f}")
    print(f"      PosnZ  {PosnZ:.6f}")

    # Return as a dictionary
    return {
        "Right": (RightX, RightY, RightZ),
        "Top":   (TopX, TopY, TopZ),
        "At":    (AtX, AtY, AtZ),
        "Pos":   (PosnX, PosnY, PosnZ),
        "Padding": Padding
    }
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
            print("==== .WBL TRANSFORM HEADER (0x00 - 0x27) ====")
            header_transform = read_leeds_cw_transform(file_bytes, 0x00)
            PosnX, PosnY, PosnZ = header_transform["Pos"]

            # --- Sectors A to D: Each sector is 12 bytes, start at 0x28
            sector_ofs = 0x28
            mesh_offsets_found = set()
            for sector_idx in range(4):
                # --- Read sector header (12 bytes) ---
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
                print(f"[0x{sector_ofs:02X}] Bool1: {Bool1} (byte value: {sec[0]:02X})")
                print(f"[0x{sector_ofs+1:02X}] Bool2: {Bool2} (byte value: {sec[1]:02X})")
                print(f"[0x{sector_ofs+2:02X}] NumInstances (int16): {NumInstances}")
                print(f"[0x{sector_ofs+4:02X}] NumShadows   (int16): {NumShadows}")
                print(f"[0x{sector_ofs+6:02X}] NumLevels    (int16): {NumLevels}")
                print(f"[0x{sector_ofs+8:02X}] NumLights    (int16): {NumLights}")
                print(f"[0x{sector_ofs+10:02X}] NumTextures  (int16): {NumTextures}")
                print(f"Levels:\n")

                # --- Read all levels (each 16 bytes) ---
                level_ofs = sector_ofs + 12
                for level_idx in range(NumLevels):
                    X_raw = struct.unpack_from("<i", file_bytes, level_ofs)[0]
                    Y_raw = struct.unpack_from("<i", file_bytes, level_ofs + 4)[0]
                    Z_raw = struct.unpack_from("<i", file_bytes, level_ofs + 8)[0]
                    NumInstances_lvl = struct.unpack_from("<h", file_bytes, level_ofs + 12)[0]
                    Flags_lvl = struct.unpack_from("<h", file_bytes, level_ofs + 14)[0]
                    X = X_raw / 4096.0
                    Y = Y_raw / 4096.0
                    Z = Z_raw / 4096.0
                    print(f"    Level {level_idx}:")
                    print(f"      [0x{level_ofs:02X}] X (int32/4096): {X}")
                    print(f"      [0x{level_ofs+4:02X}] Y (int32/4096): {Y}")
                    print(f"      [0x{level_ofs+8:02X}] Z (int32/4096): {Z}")
                    print(f"      [0x{level_ofs+12:02X}] NumInstances (int16): {NumInstances_lvl}")
                    print(f"      [0x{level_ofs+14:02X}] Flags (int16): {Flags_lvl}")
                    level_ofs += 16

                # --- Read all instances (each 16 bytes) ---
                print(f"Instances:\n")
                for instance_idx in range(NumInstances):
                    inst_base = level_ofs + instance_idx * 16
                    ID = struct.unpack_from('<h', file_bytes, inst_base)[0]
                    Instances = struct.unpack_from('<b', file_bytes, inst_base+2)[0]
                    BuildingSwap = struct.unpack_from('<b', file_bytes, inst_base+3)[0]
                    ResourceID = struct.unpack_from('<I', file_bytes, inst_base+4)[0]
                    MeshOffset = struct.unpack_from('<I', file_bytes, inst_base+8)[0]
                    Pointer = struct.unpack_from('<I', file_bytes, inst_base+12)[0]
                    print(f"  Instance {instance_idx}:")
                    print(f"    [0x{inst_base:02X}] ID (int16): {ID}")
                    print(f"    [0x{inst_base+2:02X}] Instances (int8): {Instances}")
                    print(f"    [0x{inst_base+3:02X}] BuildingSwap (int8): {BuildingSwap}")
                    print(f"    [0x{inst_base+4:02X}] ResourceID (uint32): 0x{ResourceID:08X} ({ResourceID})")
                    print(f"    [0x{inst_base+8:02X}] MeshOffset (uint32): 0x{MeshOffset:08X} ({MeshOffset})")
                    print(f"    [0x{inst_base+12:02X}] Pointer (uint32): 0x{Pointer:08X} ({Pointer})")
                    if MeshOffset != 0:
                        mesh_offsets_found.add(MeshOffset)
                level_ofs += 16 * NumInstances

                # --- Read two material slots (4 bytes) ONLY if there are instances ---
                if NumInstances > 0:
                    material_slot_offset = level_ofs
                    material_slot_1 = struct.unpack_from('<H', file_bytes, material_slot_offset)[0]
                    material_slot_2 = struct.unpack_from('<H', file_bytes, material_slot_offset + 2)[0]
                    print(f"    Material Slot 1 (uint16): {material_slot_1}  [0x{material_slot_offset:06X}]")
                    print(f"    Material Slot 2 (uint16): {material_slot_2}  [0x{material_slot_offset+2:06X}]")
                    sector_size = 12 + (NumLevels * 16) + (NumInstances * 16) + 4
                else:
                    sector_size = 12 + (NumLevels * 16) + (NumInstances * 16)

                sector_ofs += sector_size



            # ---- Parse all MeshOffsets ----
            # After sector reading loop comes Geometry Model headers:
            print("\n==== MESH HEADERS FROM ALL INSTANCES ====")

            for MeshOffset in sorted(mesh_offsets_found):
                if MeshOffset < 0 or MeshOffset > len(file_bytes) - 48:
                    print(f"  [0x{MeshOffset:02X}] MeshOffset out of file bounds")
                    continue
                mdl_ident = file_bytes[MeshOffset:MeshOffset+4]
                ident_str = ' '.join(f'{b:02X}' for b in mdl_ident)
                try:
                    mdl_ascii = mdl_ident.decode('ascii', errors='replace')
                except Exception:
                    mdl_ascii = '??'

                unknown = struct.unpack_from('<b', file_bytes, MeshOffset+4)[0]
                numMaterials = struct.unpack_from('<b', file_bytes, MeshOffset+5)[0]
                numVertices = struct.unpack_from('<h', file_bytes, MeshOffset+6)[0]
                field8 = struct.unpack_from('<I', file_bytes, MeshOffset+8)[0]
                fieldC = struct.unpack_from('<I', file_bytes, MeshOffset+12)[0]
                boundmin = read_vec3_int4096(file_bytes, MeshOffset+16)
                boundmax = read_vec3_int4096(file_bytes, MeshOffset+28)
                scaleFactor = struct.unpack_from('<f', file_bytes, MeshOffset+40)[0] # scaling factor to multiply divided XYZ with
                divFactor = struct.unpack_from('<f', file_bytes, MeshOffset+44)[0] # number to divide vert XYZ (usually 64.0)
                print(f"  [0x{MeshOffset:02X}] MDL Identifier: {ident_str} ('{mdl_ascii}')")
                print(f"    [0x{MeshOffset+4:02X}] Unknown (int8): {unknown}")
                print(f"    [0x{MeshOffset+5:02X}] numMaterials (int8): {numMaterials}")
                print(f"    [0x{MeshOffset+6:02X}] numVertices (int16): {numVertices}")
                print(f"    [0x{MeshOffset+8:02X}] Field 8 (uint32): 0x{field8:08X} ({field8})")
                print(f"    [0x{MeshOffset+12:02X}] Field C (uint32): 0x{fieldC:08X} ({fieldC})")
                print(f"    [0x{MeshOffset+16:02X}] BoundMin (3 floats): ({boundmin[0]}, {boundmin[1]}, {boundmin[2]})")
                print(f"    [0x{MeshOffset+28:02X}] BoundMax (3 floats): ({boundmax[0]}, {boundmax[1]}, {boundmax[2]})")
                print(f"    [0x{MeshOffset+40:02X}] Scale Factor: {scaleFactor}")
                print(f"    [0x{MeshOffset+44:02X}] Division Factor: {divFactor}")

                # Read vertex buffer for this mesh
                stride = 16
                vertex_base = MeshOffset + 48
                print(f"    [0x{vertex_base:02X}] Vertex Buffer ({numVertices} entries, stride {stride}):")
                verts = []
                faces = []

                for vi in range(numVertices):
                    v_off = vertex_base + vi * stride
                    x_raw = struct.unpack_from('<h', file_bytes, v_off + 0)[0]
                    y_raw = struct.unpack_from('<i', file_bytes, v_off + 2)[0]
                    z_raw = struct.unpack_from('<i', file_bytes, v_off + 4)[0]
                    x = x_raw / divFactor * scaleFactor + 2371.0
                    y = y_raw / divFactor
                    z = z_raw / divFactor
                    # Any floats above 100.0 are double-divided
                    if abs(x) > 100.0: x = x_raw / 128.0
                    if abs(y) > 100.0: y = y_raw / 128.0
                    if abs(z) > 100.0: z = z_raw / 128.0
                    verts.append((x, y, z))
                    # TODO: Normals and UVs

                flip = False
                for i in range(len(verts) - 2):
                    if flip:
                        faces.append((i, i+2, i+1))
                    else:
                        faces.append((i, i+1, i+2))
                    flip = not flip

                mesh = bpy.data.meshes.new(f"CW_Model_{MeshOffset:06X}")
                mesh.from_pydata(verts, [], faces)
                mesh.update()
                obj = bpy.data.objects.new(mesh.name, mesh)
                bpy.context.collection.objects.link(obj)


                

        except Exception as e:
            tb_str = traceback.format_exc()
            self.report({'ERROR'}, f"Import error: {e}\n{tb_str}")
            print(tb_str)
            return {'CANCELLED'}

        return {'FINISHED'}
    
#######################################################
def menu_func_import(self, context):
    self.layout.operator(ImportWBLPSPSectorOperator.bl_idname, text="R* Leeds Chinatown Wars Worldblock/Model(.wbl/.mdl)")

def register():
    bpy.utils.register_class(ImportWBLPSPSectorOperator)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.utils.unregister_class(ImportWBLPSPSectorOperator)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

if __name__ == "__main__":
    register()
