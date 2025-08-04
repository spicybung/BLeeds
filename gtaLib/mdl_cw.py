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
import bmesh
import struct
import datetime
import traceback

from bpy.types import Operator
from bpy.props import StringProperty
from bpy_extras.io_utils import ImportHelper

#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
#   This script is for .mdl/.wbls - formats for models in GTA:CW Mobile/PSP/DS      #
#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
# - Script resources:
# • https://gtamods.com/wiki/Leeds_Engine (some assets point to CW being made in Unity? ports maybe?)
# • https://gtamods.com/wiki/MDL (TODO: update stub to include Chinatown Wars documentation)
# • https://web.archive.org/web/20221108130633/http://gtamodding.ru/wiki/GAME.PAK_(Chinatown_Wars)#.D0.9C.D0.BE.D0.B4.D0.B5.D0.BB.D0.B8 (*Russian*)
# • https://web.archive.org/web/20221108130633/http://gtamodding.ru/wiki/GAME.PAK_(Chinatown_Wars)?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (*English*)
# - Mod resources/cool stuff:
# • https://gtaforums.com/topic/781150-relctw-chinatown-wars-mobile-resource-explorer/  (*analyzes game.pak for mobile & partial support for psp*)
# • https://web.archive.org/web/20221005045615/https://github.com/DK22Pac/ctw-gxt-tools (*texture editor - in case the repo goes down*)



# ======= DEBUG CONFIGURATION =======
DEBUG_MODE = True  # set to True for debug print/log, False for silent
# ===================================

#######################################################
def get_debug_logfile(import_path):
    """Get log filename in same folder as import file"""
    basename = os.path.basename(import_path)
    modelname, _ = os.path.splitext(basename)
    dirpath = os.path.dirname(import_path)
    log_path = os.path.join(dirpath, f"{modelname}_debuglog.txt")
    return log_path

#######################################################
def debug_print(s, logf=None, do_print=True):
    """Print to console and append to file if logf provided and debug enabled"""
    if DEBUG_MODE and do_print:
        print(s)
        if logf is not None:
            try:
                logf.write(s + '\n')
                logf.flush()
            except Exception as e:
                print(f"Failed to write to log file: {e}")

#######################################################
def print_bytes(data, start=0, end=None, logf=None):
    b = data[start:end]
    hexstr = ' '.join(f"{x:02X}" for x in b)
    debug_print(f"[0x{start:02X}] {hexstr}", logf)
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
    # Unsigned integers to floats
    x = struct.unpack_from('<i', data, offset)[0] / 4096.0
    y = struct.unpack_from('<i', data, offset + 4)[0] / 4096.0
    z = struct.unpack_from('<i', data, offset + 8)[0] / 4096.0
    return (x, y, z)
#######################################################
def read_leeds_cw_transform(data, offset, logf=None):
    RightX = struct.unpack_from('<h', data, offset)[0] / 4096.0
    RightY = struct.unpack_from('<h', data, offset+2)[0] / 4096.0
    RightZ = struct.unpack_from('<h', data, offset+4)[0] / 4096.0
    TopX   = struct.unpack_from('<h', data, offset+6)[0] / 4096.0
    TopY   = struct.unpack_from('<h', data, offset+8)[0] / 4096.0
    TopZ   = struct.unpack_from('<h', data, offset+0x0A)[0] / 4096.0
    AtX    = struct.unpack_from('<h', data, offset+0x0C)[0] / 4096.0
    AtY    = struct.unpack_from('<h', data, offset+0x0E)[0] / 4096.0
    AtZ    = struct.unpack_from('<h', data, offset+0x10)[0] / 4096.0
    Padding = struct.unpack_from('<h', data, offset+0x12)[0]
    PosnX = struct.unpack_from('<i', data, offset+0x14)[0] / 4096.0
    PosnY = struct.unpack_from('<i', data, offset+0x18)[0] / 4096.0
    PosnZ = struct.unpack_from('<i', data, offset+0x1C)[0] / 4096.0
    debug_print("    -Transform", logf)
    debug_print(f"      RightX {RightX:.6f}", logf)
    debug_print(f"      RightY {RightY:.6f}", logf)
    debug_print(f"      RightZ {RightZ:.6f}", logf)
    debug_print(f"      TopX   {TopX:.6f}", logf)
    debug_print(f"      TopY   {TopY:.6f}", logf)
    debug_print(f"      TopZ   {TopZ:.6f}", logf)
    debug_print(f"      AtX    {AtX:.6f}", logf)
    debug_print(f"      AtY    {AtY:.6f}", logf)
    debug_print(f"      AtZ    {AtZ:.6f}", logf)
    debug_print(f"      Padding {Padding}", logf)
    debug_print(f"      PosnX  {PosnX:.6f}", logf)
    debug_print(f"      PosnY  {PosnY:.6f}", logf)
    debug_print(f"      PosnZ  {PosnZ:.6f}", logf)
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
        logf = None
        if DEBUG_MODE:
            logpath = get_debug_logfile(self.filepath)
            logf = open(logpath, 'w', encoding='utf-8')
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            debug_print(f"==== DEBUG LOG STARTED {now} ====", logf)

        try:
            with open(self.filepath, "rb") as f:
                file_bytes = f.read()
            debug_print("==== .WBL TRANSFORM HEADER (0x00 - 0x27) ====", logf)
            header_transform = read_leeds_cw_transform(file_bytes, 0x00, logf)
            PosnX, PosnY, PosnZ = header_transform["Pos"]

            # --- Sectors A to D: Each model has them, and each sector is 12 bytes; start at 0x28 - after world transforms
            sector_ofs = 0x28
            mesh_offsets_found = set()
            for sector_idx in range(4):
                sec = file_bytes[sector_ofs:sector_ofs + 12]
                debug_print(f"\n==== SECTOR {sector_idx} (0x{sector_ofs:02X} - 0x{sector_ofs+11:02X}) ====", logf)
                debug_print(f"[0x{sector_ofs:02X}] Sector raw bytes: {' '.join(f'{b:02X}' for b in sec)}", logf)

                # TODO: find out what these bools do
                Bool1 = bool(sec[0])
                Bool2 = bool(sec[1])
                # How many instances this sector has
                NumInstances = struct.unpack_from("<h", sec, 2)[0]
                # How many shadows this sector has
                NumShadows   = struct.unpack_from("<h", sec, 4)[0]
                # How many levels this sector has
                NumLevels    = struct.unpack_from("<h", sec, 6)[0]
                # How many lights this sector has
                NumLights    = struct.unpack_from("<h", sec, 8)[0]
                # How many textures this sector has
                NumTextures  = struct.unpack_from("<h", sec,10)[0]

                debug_print(f"[0x{sector_ofs:02X}] Bool1: {Bool1} (byte value: {sec[0]:02X})", logf)
                debug_print(f"[0x{sector_ofs+1:02X}] Bool2: {Bool2} (byte value: {sec[1]:02X})", logf)
                debug_print(f"[0x{sector_ofs+2:02X}] NumInstances (int16): {NumInstances}", logf)
                debug_print(f"[0x{sector_ofs+4:02X}] NumShadows   (int16): {NumShadows}", logf)
                debug_print(f"[0x{sector_ofs+6:02X}] NumLevels    (int16): {NumLevels}", logf)
                debug_print(f"[0x{sector_ofs+8:02X}] NumLights    (int16): {NumLights}", logf)
                debug_print(f"[0x{sector_ofs+10:02X}] NumTextures  (int16): {NumTextures}", logf)

                level_ofs = sector_ofs + 12

                # --- Read levels ---
                debug_print(f"Levels:", logf)
                for level_idx in range(NumLevels):
                    X_raw = struct.unpack_from("<i", file_bytes, level_ofs)[0]
                    Y_raw = struct.unpack_from("<i", file_bytes, level_ofs + 4)[0]
                    Z_raw = struct.unpack_from("<i", file_bytes, level_ofs + 8)[0]
                    NumInstances_lvl = struct.unpack_from("<h", file_bytes, level_ofs + 12)[0]
                    Flags_lvl = struct.unpack_from("<h", file_bytes, level_ofs + 14)[0]

                    X = X_raw / 4096.0
                    Y = Y_raw / 4096.0
                    Z = Z_raw / 4096.0

                    debug_print(f"    Level {level_idx}:", logf)
                    debug_print(f"      [0x{level_ofs:02X}] X (int32/4096): {X}", logf)
                    debug_print(f"      [0x{level_ofs+4:02X}] Y (int32/4096): {Y}", logf)
                    debug_print(f"      [0x{level_ofs+8:02X}] Z (int32/4096): {Z}", logf)
                    debug_print(f"      [0x{level_ofs+12:02X}] NumInstances (int16): {NumInstances_lvl}", logf)
                    debug_print(f"      [0x{level_ofs+14:02X}] Flags (int16): {Flags_lvl}", logf)

                    level_ofs += 16

                # --- Read instances ---
                debug_print(f"Instances:", logf)
                for instance_idx in range(NumInstances):
                    inst_base = level_ofs + instance_idx * 16
                    ID = struct.unpack_from('<h', file_bytes, inst_base)[0] # model ID
                    RenderListID = struct.unpack_from('<b', file_bytes, inst_base+2)[0]
                    BuildingSwap = struct.unpack_from('<b', file_bytes, inst_base+3)[0]
                    ResourceID = struct.unpack_from('<I', file_bytes, inst_base+4)[0]
                    MeshOffset = struct.unpack_from('<I', file_bytes, inst_base+8)[0]
                    Pointer = struct.unpack_from('<I', file_bytes, inst_base+12)[0] # usually empty

                    debug_print(f"  Instance {instance_idx}:", logf)
                    debug_print(f"    [0x{inst_base:02X}] ModelID (int16): {ID}", logf)
                    debug_print(f"    [0x{inst_base+2:02X}] RenderListID (int8): {RenderListID}", logf)
                    debug_print(f"    [0x{inst_base+3:02X}] BuildingSwap (int8): {BuildingSwap}", logf)
                    debug_print(f"    [0x{inst_base+4:02X}] ResourceID (uint32): 0x{ResourceID:08X} ({ResourceID})", logf)
                    debug_print(f"    [0x{inst_base+8:02X}] MeshOffset (uint32): 0x{MeshOffset:08X} ({MeshOffset})", logf)
                    debug_print(f"    [0x{inst_base+12:02X}] Pointer (uint32): 0x{Pointer:08X} ({Pointer})", logf)

                    if MeshOffset != 0:
                        mesh_offsets_found.add(MeshOffset)

                level_ofs += 16 * NumInstances
                
                # SHADOWS: Only read if NumShadows > 0
                shadow_base = level_ofs
                if NumShadows > 0:
                    shadow_stride = 20
                    debug_print(f"Shadows ({NumShadows} entries @0x{shadow_base:06X}):", logf)
                    for shadow_idx in range(NumShadows):
                        s_off = shadow_base + shadow_idx * shadow_stride

                        # Print raw bytes for this shadow entry
                        debug_print(f"    Shadow {shadow_idx}: [0x{s_off:06X}] " +
                                    file_bytes[s_off:s_off+shadow_stride].hex(' ').upper(), logf)

                        CenterX = struct.unpack_from('<i', file_bytes, s_off)[0] / 4096.0
                        CenterY   = struct.unpack_from('<i', file_bytes, s_off + 4)[0] / 4096.0
                        CenterZ  = struct.unpack_from('<e', file_bytes, s_off + 8)[0]   # CenterZ? theres gotta be a z
                        SizeX     = struct.unpack_from('<h', file_bytes, s_off + 10)[0] / 4096.0
                        SizeY     = struct.unpack_from('<h', file_bytes, s_off + 12)[0] / 4096.0
                        SizeZ  = struct.unpack_from('<h', file_bytes, s_off + 14)[0] / 4096.0   # SizeZ? theres gotta be a z
                        Unknown3  = struct.unpack_from('<h', file_bytes, s_off + 16)[0]
                        Id        = struct.unpack_from('B', file_bytes, s_off + 18)[0]  # shadow ID
                        Pad       = struct.unpack_from('B', file_bytes, s_off + 19)[0]

                        debug_print(f"      CenterX:   {CenterX}", logf)
                        debug_print(f"      CenterY:   {CenterY}", logf)
                        debug_print(f"      CenterZ:  {CenterZ}", logf)
                        debug_print(f"      SizeX:     {SizeX}", logf)
                        debug_print(f"      SizeY:     {SizeY}", logf)
                        debug_print(f"      Unknown2:  {SizeZ}", logf)
                        debug_print(f"      Unknown3:  {Unknown3}", logf)
                        debug_print(f"      Id:        {Id}", logf)
                        debug_print(f"      Padding:   {Pad}", logf)
                    # Advance level_ofs past the entire shadow block for subsequent reading
                    level_ofs += NumShadows * shadow_stride

                # LIGHTS: Only read if NumLights > 0
                light_base = level_ofs
                if NumLights > 0:
                    light_stride = 20  # Each light entry is 20 bytes
                    debug_print(f"Lights ({NumLights} entries @0x{light_base:06X}):", logf)

                    for light_idx in range(NumLights):
                        l_off = light_base + light_idx * light_stride

                        # Print raw bytes for this light entry
                        debug_print(f"    Light {light_idx}: [0x{l_off:06X}] " +
                                    file_bytes[l_off:l_off+light_stride].hex(' ').upper(), logf)

                        X_raw = struct.unpack_from('<I', file_bytes, l_off + 0)[0]
                        Y_raw = struct.unpack_from('<I', file_bytes, l_off + 4)[0]
                        Z_raw = struct.unpack_from('<I', file_bytes, l_off + 8)[0]
                        Size_raw = struct.unpack_from('<H', file_bytes, l_off + 12)[0]
                        Id = struct.unpack_from('<B', file_bytes, l_off + 14)[0]
                        # CW: RGB only(?)
                        R = struct.unpack_from('<B', file_bytes, l_off + 16)[0]
                        G = struct.unpack_from('<B', file_bytes, l_off + 17)[0]
                        B = struct.unpack_from('<B', file_bytes, l_off + 18)[0]

                        # Light XYZ conversion
                        X = X_raw / 4096.0
                        Y = Y_raw / 4096.0
                        Z = Z_raw / 4096.0
                        Size = Size_raw / 4096.0

                        debug_print(f"      X: {X}", logf)
                        debug_print(f"      Y: {Y}", logf)
                        debug_print(f"      Z: {Z}", logf)
                        debug_print(f"      Id: {Id}", logf)
                        debug_print(f"      Color: {R} {G} {B}", logf)
                        debug_print(f"      Size: {Size}", logf)
                        
                        # === Create point light in Blender ===
                        light_data = bpy.data.lights.new(name=f"CW_Light_{light_idx}", type='POINT')
                        light_object = bpy.data.objects.new(name=f"CW_Light_{light_idx}", object_data=light_data)
                        bpy.context.collection.objects.link(light_object)

                        # Set light location
                        light_object.location = (X, Y, Z)

                        # Normalize color to 0.0–1.0 and set
                        light_data.color = (R / 255.0, G / 255.0, B / 255.0)

                        # Assign light energy scaled by size
                        light_data.energy = max(1.0, Size * 1000.0)  # avoid energy = 0

                        # Optional: use size to set softness
                        light_data.shadow_soft_size = Size

                        # Optional: store light ID as custom property
                        light_object["CW_LightID"] = Id

                    # Advance offset after lights
                    level_ofs += NumLights * light_stride

                # TEXTURE IDs: Always read, but position depends on if shadows exist
                texture_ids = []
                if NumTextures > 0:
                    debug_print(f"Textures ({NumTextures} IDs):", logf)
                    for tex_idx in range(NumTextures):
                        tex_offset = level_ofs + tex_idx * 2
                        tex_id = struct.unpack_from('<H', file_bytes, tex_offset)[0]
                        texture_ids.append(tex_id)
                        debug_print(f"  [0x{tex_offset:02X}] Texture ID {tex_idx}: {tex_id}", logf)
                    level_ofs += NumTextures * 2

                # Update sector offset
                sector_size = 12 + (NumLevels * 16) + (NumInstances * 16) + (NumShadows * 20) + (NumLights * 20) + (NumTextures * 2)
                sector_ofs += sector_size

            # ---- Parse MeshOffsets, read GeometryMesh struct ----
            debug_print("\n==== MESH HEADERS FROM ALL INSTANCES ====", logf)
            for MeshOffset in sorted(mesh_offsets_found):
                if MeshOffset < 0 or MeshOffset > len(file_bytes) - 48:
                    debug_print(f"  [0x{MeshOffset:02X}] MeshOffset out of file bounds", logf)
                    continue
                mdl_ident = file_bytes[MeshOffset:MeshOffset+4]
                ident_str = ' '.join(f'{b:02X}' for b in mdl_ident)
                try:
                    mdl_ascii = mdl_ident.decode('ascii', errors='replace')
                except Exception:
                    mdl_ascii = '??'

                unknown = struct.unpack_from('<b', file_bytes, MeshOffset+4)[0]
                numMaterials = struct.unpack_from('<b', file_bytes, MeshOffset+5)[0] # number of textures the model has
                numVertices = struct.unpack_from('<h', file_bytes, MeshOffset+6)[0] 
                field8 = struct.unpack_from('<I', file_bytes, MeshOffset+8)[0]
                fieldC = struct.unpack_from('<I', file_bytes, MeshOffset+12)[0]  # TODO: what do the numbers mean Mason?
                boundmin = read_vec3_int4096(file_bytes, MeshOffset+16) # bounding box minimum
                boundmax = read_vec3_int4096(file_bytes, MeshOffset+28) # bounding box maximum
                uvOffset = struct.unpack_from('<f', file_bytes, MeshOffset+40)[0]  # float for offsetting uv's
                scaleFactor = struct.unpack_from('<f', file_bytes, MeshOffset+44)[0]  # scale factor for models
                debug_print(f"  [0x{MeshOffset:02X}] MDL Identifier: {ident_str} ('{mdl_ascii}')", logf)
                debug_print(f"    [0x{MeshOffset+4:02X}] Unknown (int8): {unknown}", logf)
                debug_print(f"    [0x{MeshOffset+5:02X}] numMaterials (int8): {numMaterials}", logf)
                debug_print(f"    [0x{MeshOffset+6:02X}] numVertices (int16): {numVertices}", logf)
                debug_print(f"    [0x{MeshOffset+8:02X}] Field 8 (uint32): 0x{field8:08X} ({field8})", logf)
                debug_print(f"    [0x{MeshOffset+12:02X}] Field C (uint32): 0x{fieldC:08X} ({fieldC})", logf)
                debug_print(f"    [0x{MeshOffset+16:02X}] BoundMin (3 floats): ({boundmin[0]}, {boundmin[1]}, {boundmin[2]})", logf)
                debug_print(f"    [0x{MeshOffset+28:02X}] BoundMax (3 floats): ({boundmax[0]}, {boundmax[1]}, {boundmax[2]})", logf)
                debug_print(f"    [0x{MeshOffset+40:02X}] uv Offset: {uvOffset}", logf)
                debug_print(f"    [0x{MeshOffset+44:02X}] Scale Factor: {scaleFactor}", logf)

                # Read vertex buffer for this mesh (CW: no index buffer)
                # X, Y, Z, NX, NY, NZ, U, V - so CW vertex stride is usually always 16 bytes.
                stride = 16
                vertex_base = MeshOffset + 48

                # --- Parse all vertices once (will use them for all parts) ---
                all_verts = []
                all_normals = []
                all_uvs = []
                for vi in range(numVertices):
                    v_off = vertex_base + vi * stride
                    
                # Read vertex buffer for this mesh
                # X, Y, Z, NX, NY, NZ, U, V - so CW vertex stride is usually always 16 bytes.
                stride = 16
                vertex_base = MeshOffset + 48
                debug_print(f"    [0x{vertex_base:02X}] Vertex Buffer ({numVertices} entries, stride {stride}):", logf)
                verts = []
                faces = []
                normals = []
                uvs = []

                for vi in range(numVertices):
                    v_off = vertex_base + vi * stride

                    # Read position (int16)
                    # integer 16 divided by scaleFactor
                    x_raw = struct.unpack_from('<h', file_bytes, v_off + 0)[0]
                    y_raw = struct.unpack_from('<h', file_bytes, v_off + 2)[0]
                    z_raw = struct.unpack_from('<h', file_bytes, v_off + 4)[0]
                    # Mobile divides by scale factor found in GeometryMesh struct
                    x = x_raw / scaleFactor + PosnX
                    y = y_raw / scaleFactor + PosnY
                    z = z_raw / scaleFactor + PosnZ

                    # Read normals (int16)
                    nx_raw = struct.unpack_from('<h', file_bytes, v_off + 6)[0]
                    ny_raw = struct.unpack_from('<h', file_bytes, v_off + 8)[0]
                    nz_raw = struct.unpack_from('<h', file_bytes, v_off + 10)[0]
                    # Mobile divides by 32767
                    nx = nx_raw / 32767.0
                    ny = ny_raw / 32767.0
                    nz = nz_raw / 32767.0

                    # Read UV (int16)
                    u_raw = struct.unpack_from('<h', file_bytes, v_off + 12)[0]
                    v_raw = struct.unpack_from('<h', file_bytes, v_off + 14)[0]
                    
                    # Mobile divides by 2048
                    u = (u_raw / 2048.0) + uvOffset # CW Mobile: divide the u by 2048, add uvOffset along x-axis
                    v = 1.0 - (v_raw / 2048.0) # CW Mobile: flip v's on their y-axis, divide by 2048

                    all_verts.append((x, y, z))
                    all_normals.append((nx, ny, nz))
                    all_uvs.append((u, v))

                # --- Parse and split by mesh part/material group ---
                vert_offset = 0
                material_table_offset = vertex_base + (numVertices * stride)

                # NOTE: For CW Mobile & probably PSP, "parts" are split by numMaterials, not numMeshes
                for mi in range(numMaterials):
                    m_off = material_table_offset + mi * 12

                    # Mobile divides by 2048(?)
                    u = u_raw / 2048.0
                    v = v_raw / 2048.0

                    # Hex and raw logging
                    debug_print(f"      Vertex {vi:3d}:", logf)
                    debug_print(f"        X:  offset 0x{v_off:06X}  bytes {file_bytes[v_off:v_off+2].hex(' ').upper()}  raw {x_raw:6d}  value {x:.6f}", logf)
                    debug_print(f"        Y:  offset 0x{v_off+2:06X}  bytes {file_bytes[v_off+2:v_off+4].hex(' ').upper()}  raw {y_raw:6d}  value {y:.6f}", logf)
                    debug_print(f"        Z:  offset 0x{v_off+4:06X}  bytes {file_bytes[v_off+4:v_off+6].hex(' ').upper()}  raw {z_raw:6d}  value {z:.6f}", logf)
                    debug_print(f"        Norm: ({nx:.6f}, {ny:.6f}, {nz:.6f})  UV: ({u:.6f}, {v:.6f})", logf)

                    # Import all vertices, normals, and uvs - for mesh's in Blender scene
                    verts.append((x, y, z))
                    normals.append((nx, ny, nz))
                    uvs.append((u, v))
                 
                # === Parse material list ===    
                materials = []
                material_table_offset = vertex_base + (numVertices * stride)
                for mi in range(numMaterials):
                    m_off = material_table_offset + mi * 12


                    tex_id         = struct.unpack_from('<H', file_bytes, m_off + 0)[0]
                    vertex_count   = struct.unpack_from('<H', file_bytes, m_off + 2)[0]
                    render_flags   = struct.unpack_from('<B', file_bytes, m_off + 4)[0]
                    node           = struct.unpack_from('<B', file_bytes, m_off + 5)[0]
                    field6         = struct.unpack_from('<B', file_bytes, m_off + 6)[0]
                    field7         = struct.unpack_from('<B', file_bytes, m_off + 7)[0]
                    variance_flags = struct.unpack_from('<i', file_bytes, m_off + 8)[0]


                    debug_print(f"---- Mesh Part {mi}: ----", logf)
                    debug_print(f"  Texture ID: {tex_id}", logf)
                    debug_print(f"  Vertex Count: {vertex_count}", logf)
                    debug_print(f"  Rendering Flags: {render_flags}", logf)
                    debug_print(f"  Node: {node}", logf)
                    debug_print(f"  Field6: {field6}", logf)
                    debug_print(f"  Field7: {field7}", logf)
                    debug_print(f"  VarianceFlags: {variance_flags}", logf)

                    # Vertices and uvs just for this part
                    part_verts = []
                    part_normals = []
                    part_uvs = []
                    for i in range(vertex_count):
                        idx = vert_offset + i
                        part_verts.append(all_verts[idx])
                        part_normals.append(all_normals[idx])
                        part_uvs.append(all_uvs[idx])

                    # NOTE: Faces for this mesh part: always flip the winding every triangle strip or you will break shit (RIP Hulkster brother)
                    part_faces = []
                    if vertex_count >= 3:
                        flip = False
                        for i in range(vertex_count - 2):
                            idx0 = i
                            idx1 = i + 1
                            idx2 = i + 2
                            if flip:
                                face = (idx0, idx2, idx1)
                            else:
                                face = (idx0, idx1, idx2)
                            if len(set(face)) == 3:
                                part_faces.append(face)
                            flip = not flip

                    # --- Create mesh for this mesh part/material group ---
                    mesh_name = f"CW_Model_{MeshOffset:06X}_part{mi}_tex{tex_id}"
                    mesh = bpy.data.meshes.new(mesh_name)
                    mesh.from_pydata(part_verts, [], part_faces)
                    mesh.update()

                    # UVs for this mesh part
                    uv_layer = mesh.uv_layers.new(name="UVMap")
                    for face in mesh.polygons:
                        for loop_index in face.loop_indices:
                            vert_index = mesh.loops[loop_index].vertex_index
                            uv = part_uvs[vert_index]
                            uv_layer.data[loop_index].uv = uv

                    # --- Assign material for this part ---
                    mat_name = f"texture{tex_id}"
                    if mat_name in bpy.data.materials:
                        mat = bpy.data.materials[mat_name]
                        mat.use_nodes = True
                        nodes = mat.node_tree.nodes
                        nodes.clear()
                        debug_print(f"    Material '{mat_name}' exists, clearing nodes and reloading image.", logf)
                    else:
                        mat = bpy.data.materials.new(name=mat_name)
                        mat.use_nodes = True
                        nodes = mat.node_tree.nodes
                        debug_print(f"    Created new material '{mat_name}' and will load image.", logf)
                    tex_image_node = nodes.new('ShaderNodeTexImage')
                    bsdf_node = nodes.new('ShaderNodeBsdfPrincipled')
                    output_node = nodes.new('ShaderNodeOutputMaterial')
                    tex_image_node.location = (-400, 300)
                    bsdf_node.location = (-100, 300)
                    output_node.location = (200, 300)
                    links = mat.node_tree.links
                    links.new(tex_image_node.outputs['Color'], bsdf_node.inputs['Base Color'])
                    links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])
                    image_path = os.path.join(os.path.dirname(self.filepath), f"{mat_name}.png")
                    debug_print(f"      Checking for image: {image_path}", logf)
                    if os.path.exists(image_path):
                        try:
                            img = bpy.data.images.load(image_path, check_existing=True)
                            tex_image_node.image = img
                            tex_image_node.interpolation = 'Smart'
                            debug_print(f"      Loaded texture image: {image_path}", logf)
                        except Exception as e:
                            debug_print(f"      Failed loading image {image_path}: {e}", logf)
                    else:
                        debug_print(f"      Texture image not found: {image_path}", logf)
                    mat["CW_TexID"] = tex_id
                    mesh.materials.append(mat)

                    # --- Create Blender object and link ---
                    obj = bpy.data.objects.new(mesh.name, mesh)
                    bpy.context.collection.objects.link(obj)

                    vert_offset += vertex_count
                   
                    debug_print(f"    Material {mi}:", logf)
                    debug_print(f"      Texture ID: {tex_id}", logf)
                    debug_print(f"      Vertex Count: {vertex_count}", logf)
                    debug_print(f"      Rendering Flags: {render_flags}", logf)
                    debug_print(f"      Node: {node}", logf)
                    debug_print(f"      Field6: {field6}", logf)
                    debug_print(f"      Field7: {field7}", logf)
                    debug_print(f"      VarianceFlags: {variance_flags}", logf)

                    materials.append(tex_id)

                
                # === Sort tri-strips from vertices(TODO: other 3 primitive types) === 
                flip = False
                for i in range(len(verts) - 2):
                    if flip:
                        faces.append((i, i+2, i+1))
                    else:
                        faces.append((i, i+1, i+2))
                    flip = not flip
                
                # === Create meshes === 
                mesh = bpy.data.meshes.new(f"CW_Model_{MeshOffset:06X}")
                mesh.from_pydata(verts, [], faces)
                mesh.update()
                
                # --- Add UV map and assign UV coordinates ---
                uv_layer = mesh.uv_layers.new(name="UVMap")
                for face in mesh.polygons:
                    for loop_index in face.loop_indices:
                        vert_index = mesh.loops[loop_index].vertex_index
                        uv = uvs[vert_index]
                        uv_layer.data[loop_index].uv = uv
                
                obj = bpy.data.objects.new(mesh.name, mesh)
                bpy.context.collection.objects.link(obj)
                
                # === Assign materials to the mesh via texture IDs ===
                if materials:
                    debug_print(f"    Assigning materials to mesh using MDL materials...", logf)
                    for tex_id in materials:
                        mat_name = f"texture{tex_id}"

                        # Get or create material
                        if mat_name in bpy.data.materials:
                            mat = bpy.data.materials[mat_name]
                            # Clear nodes so we can recreate them fresh
                            mat.use_nodes = True
                            nodes = mat.node_tree.nodes
                            nodes.clear()
                            debug_print(f"    Material '{mat_name}' exists, clearing nodes and reloading image.", logf)
                        else:
                            mat = bpy.data.materials.new(name=mat_name)
                            mat.use_nodes = True
                            nodes = mat.node_tree.nodes
                            debug_print(f"    Created new material '{mat_name}' and will load image.", logf)

                        # Create nodes every time
                        tex_image_node = nodes.new('ShaderNodeTexImage')
                        bsdf_node = nodes.new('ShaderNodeBsdfPrincipled')
                        output_node = nodes.new('ShaderNodeOutputMaterial')

                        # Setup node locations
                        tex_image_node.location = (-400, 300)
                        bsdf_node.location = (-100, 300)
                        output_node.location = (200, 300)

                        # Link shader nodes
                        links = mat.node_tree.links
                        links.new(tex_image_node.outputs['Color'], bsdf_node.inputs['Base Color'])
                        links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])

                        # Try to load the image from same dir every time
                        image_path = os.path.join(os.path.dirname(self.filepath), f"{mat_name}.png")
                        debug_print(f"      Checking for image: {image_path}", logf)

                        if os.path.exists(image_path):
                            try:
                                img = bpy.data.images.load(image_path, check_existing=True)
                                tex_image_node.image = img
                                tex_image_node.interpolation = 'Smart'
                                debug_print(f"      Loaded texture image: {image_path}", logf)
                            except Exception as e:
                                debug_print(f"      Failed loading image {image_path}: {e}", logf)
                        else:
                            debug_print(f"      Texture image not found: {image_path}", logf)

                        # Tag for later use
                        mat["CW_TexID"] = tex_id

                        obj.data.materials.append(mat)
                        debug_print(f"      Assigned material '{mat_name}' to mesh", logf)



        except Exception as e:
            tb_str = traceback.format_exc()
            if logf:
                logf.write("IMPORT ERROR\n")
                logf.write(tb_str)
                logf.flush()
            self.report({'ERROR'}, f"Import error: {e}\n{tb_str}")
            print(tb_str)
            if logf:
                logf.close()
            return {'CANCELLED'}

        if logf:
            debug_print("==== END OF DEBUG LOG ====", logf)
            logf.close()
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
