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
import struct
import datetime
import traceback

import bpy

from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional

#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
#   This script is for .WBL - the file format for Chinatown Wars world sectors      #
#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
# - Script resources:
# • https://gtamods.com/wiki/Leeds_Engine (some assets point to CW being made in Unity? ports maybe?)
# • https://gtamods.com/wiki/MDL (TODO: update stub to include Chinatown Wars documentation)
# • https://web.archive.org/web/20221108130633/http://gtamodding.ru/wiki/GAME.PAK_(Chinatown_Wars)#.D0.9C.D0.BE.D0.B4.D0.B5.D0.BB.D0.B8 (*Russian*)
# • https://web.archive.org/web/20221108130633/http://gtamodding.ru/wiki/GAME.PAK_(Chinatown_Wars)?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (*English*)
# - Mod resources/cool stuff:
# • https://gtaforums.com/topic/781150-relctw-chinatown-wars-mobile-resource-explorer/  (*analyzes game.pak for mobile & partial support for psp*)
# • https://web.archive.org/web/20221005045615/https://github.com/DK22Pac/ctw-gxt-tools (*texture editor - in case the repo goes down*)


#######################################################
class read_chinatown:
    """Reads Chinatown Wars Worldblocks"""

    # ===== DEBUG CONFIGURATION =====
    DEBUG_MODE: bool = True
    # ===============================

    #######################################################
    # Small data containers
    #######################################################

    @dataclass
    class CWTransform:
        right: Tuple[float, float, float]
        top: Tuple[float, float, float]
        at: Tuple[float, float, float]
        pos: Tuple[float, float, float]
        padding: int

    #######################################################
    # Debug helpers
    #######################################################
    @classmethod
    def get_debug_logfile(cls, import_path: str) -> str:
        basename = os.path.basename(import_path)
        modelname, _ = os.path.splitext(basename)
        dirpath = os.path.dirname(import_path)
        log_path = os.path.join(dirpath, f"{modelname}_debuglog.txt")
        return log_path

    @classmethod
    def dprint(cls, s: str, logf=None, do_print: bool = True) -> None:
        if cls.DEBUG_MODE and do_print:
            print(s)
            if logf is not None:
                try:
                    logf.write(s + "\n")
                    logf.flush()
                except Exception as e:  
                    print(f"Failed to write to log file: {e}")

    @classmethod
    def print_bytes(cls, data: bytes, start: int = 0,
                    end: Optional[int] = None, logf=None) -> None:
        """Debug-print a slice of bytes in hex."""
        b = data[start:end]
        hexstr = " ".join(f"{x:02X}" for x in b)
        cls.dprint(f"[0x{start:02X}] {hexstr}", logf)
    
    @staticmethod
    def padhex(n: int, w: int = 8) -> str:
        """Return a zero-padded hex string."""
        return f"0x{n:0{w}X}"

    #######################################################
    # Binary helpers
    #######################################################
    @staticmethod
    def read_u8(data: bytes, offset: int) -> int:
        return struct.unpack_from("<B", data, offset)[0]

    @staticmethod
    def read_i8(data: bytes, offset: int) -> int:
        return struct.unpack_from("<b", data, offset)[0]

    @staticmethod
    def read_i16(data: bytes, offset: int) -> int:
        return struct.unpack_from("<h", data, offset)[0]

    @staticmethod
    def read_u16(data: bytes, offset: int) -> int:
        return struct.unpack_from("<H", data, offset)[0]

    @staticmethod
    def read_vec3_int4096(data: bytes, offset: int) -> Tuple[float, float, float]:
        x = struct.unpack_from("<i", data, offset + 0)[0] / 4096.0
        y = struct.unpack_from("<i", data, offset + 4)[0] / 4096.0
        z = struct.unpack_from("<i", data, offset + 8)[0] / 4096.0
        return (x, y, z)

    @classmethod
    def read_leeds_cw_transform(cls, data: bytes, offset: int,
                                logf=None) -> "read_chinatown.CWTransform":

        RightX = struct.unpack_from("<h", data, offset + 0x00)[0] / 4096.0
        RightY = struct.unpack_from("<h", data, offset + 0x02)[0] / 4096.0
        RightZ = struct.unpack_from("<h", data, offset + 0x04)[0] / 4096.0

        TopX = struct.unpack_from("<h", data, offset + 0x06)[0] / 4096.0
        TopY = struct.unpack_from("<h", data, offset + 0x08)[0] / 4096.0
        TopZ = struct.unpack_from("<h", data, offset + 0x0A)[0] / 4096.0

        AtX = struct.unpack_from("<h", data, offset + 0x0C)[0] / 4096.0
        AtY = struct.unpack_from("<h", data, offset + 0x0E)[0] / 4096.0
        AtZ = struct.unpack_from("<h", data, offset + 0x10)[0] / 4096.0

        Padding = struct.unpack_from("<h", data, offset + 0x12)[0]

        PosnX = struct.unpack_from("<i", data, offset + 0x14)[0] / 4096.0
        PosnY = struct.unpack_from("<i", data, offset + 0x18)[0] / 4096.0
        PosnZ = struct.unpack_from("<i", data, offset + 0x1C)[0] / 4096.0

        cls.dprint("    -Transform", logf)
        cls.dprint(f"      RightX {RightX:.6f}", logf)
        cls.dprint(f"      RightY {RightY:.6f}", logf)
        cls.dprint(f"      RightZ {RightZ:.6f}", logf)
        cls.dprint(f"      TopX   {TopX:.6f}", logf)
        cls.dprint(f"      TopY   {TopY:.6f}", logf)
        cls.dprint(f"      TopZ   {TopZ:.6f}", logf)
        cls.dprint(f"      AtX    {AtX:.6f}", logf)
        cls.dprint(f"      AtY    {AtY:.6f}", logf)
        cls.dprint(f"      AtZ    {AtZ:.6f}", logf)
        cls.dprint(f"      Padding {Padding}", logf)
        cls.dprint(f"      PosnX  {PosnX:.6f}", logf)
        cls.dprint(f"      PosnY  {PosnY:.6f}", logf)
        cls.dprint(f"      PosnZ  {PosnZ:.6f}", logf)

        return cls.CWTransform(
            right=(RightX, RightY, RightZ),
            top=(TopX, TopY, TopZ),
            at=(AtX, AtY, AtZ),
            pos=(PosnX, PosnY, PosnZ),
            padding=Padding,
        )

    #######################################################
    # Material bank 
    #######################################################
    class MaterialBank:

        def __init__(self, current_dir: str, logf=None):
            self.current_dir: str = current_dir
            self.logf = logf
            self.material_slots: List[Tuple[str, bpy.types.Material]] = []
            self.material_index_by_texid: Dict[int, int] = {}

        def get_slot(self, tex_id: int) -> int:
            """
            Get or create a material slot index for the given texture ID.
            """
            if tex_id in self.material_index_by_texid:
                return self.material_index_by_texid[tex_id]

            mat_name = f"texture{tex_id}"
            logf = self.logf

            if mat_name in bpy.data.materials:
                mat = bpy.data.materials[mat_name]
                read_chinatown.dprint(
                    f"    Material '{mat_name}' exists, rebuilding node tree.",
                    logf,
                )
            else:
                mat = bpy.data.materials.new(name=mat_name)
                read_chinatown.dprint(
                    f"    Created new material '{mat_name}' and will build node tree.",
                    logf,
                )

            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            nodes.clear()

            tex_image_node = nodes.new("ShaderNodeTexImage")
            bsdf_node = nodes.new("ShaderNodeBsdfPrincipled")
            output_node = nodes.new("ShaderNodeOutputMaterial")

            tex_image_node.location = (-400, 300)
            bsdf_node.location = (-100, 300)
            output_node.location = (200, 300)

            links = mat.node_tree.links
            links.new(tex_image_node.outputs["Color"], bsdf_node.inputs["Base Color"])
            links.new(bsdf_node.outputs["BSDF"], output_node.inputs["Surface"])

            output_node.is_active_output = True

            image_path = os.path.join(self.current_dir, f"{mat_name}.png")
            read_chinatown.dprint(f"      Checking for image: {image_path}", logf)
            if os.path.exists(image_path):
                try:
                    img = bpy.data.images.load(image_path, check_existing=True)
                    tex_image_node.image = img
                    tex_image_node.interpolation = "Smart"
                    read_chinatown.dprint(
                        f"      Loaded texture image: {image_path}", logf
                    )
                except Exception as e:
                    read_chinatown.dprint(
                        f"      Failed loading image {image_path}: {e}", logf
                    )
            else:
                read_chinatown.dprint(
                    f"      Texture image not found: {image_path}", logf
                )

            mat["CW_TexID"] = tex_id

            slot_index = len(self.material_slots)
            self.material_slots.append((mat_name, mat))
            self.material_index_by_texid[tex_id] = slot_index
            return slot_index

        def append_all_to_mesh(self, mesh: bpy.types.Mesh) -> None:
            """
            Append all materials in this bank as slots on the given mesh.
            """
            for _mat_name, mat in self.material_slots:
                mesh.materials.append(mat)

    #######################################################
    # Tri-strips
    #######################################################
    @staticmethod
    def tri_strip_to_tris(vertex_count: int) -> List[Tuple[int, int, int]]:
        faces: List[Tuple[int, int, int]] = []
        if vertex_count < 3:
            return faces

        flip = False
        for i in range(vertex_count - 2):
            i0, i1, i2 = i, i + 1, i + 2
            if flip:
                tri = (i0, i2, i1)
            else:
                tri = (i0, i1, i2)

            if len({i0, i1, i2}) == 3:
                faces.append(tri)

            flip = not flip

        return faces

    @classmethod
    def import_wbl(cls, filepath: str, context) -> None:

        logf = None

        world_verts: List[Tuple[float, float, float]] = []
        world_uvs: List[Tuple[float, float]] = []
        world_faces: List[Tuple[int, int, int]] = []
        world_face_material_indices: List[int] = []

        try:
            if cls.DEBUG_MODE:
                logpath = cls.get_debug_logfile(filepath)
                logf = open(logpath, "w", encoding="utf-8")
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cls.dprint(f"==== DEBUG LOG STARTED {now} ====", logf)

            with open(filepath, "rb") as f:
                file_bytes = f.read()

            cls.dprint("==== .WBL TRANSFORM HEADER (0x00 - 0x27) ====", logf)
            header_transform = cls.read_leeds_cw_transform(file_bytes, 0x00, logf)
            PosnX, PosnY, PosnZ = header_transform.pos

            sector_ofs = 0x28
            mesh_offsets_found = set()

            for sector_idx in range(4):
                sec = file_bytes[sector_ofs:sector_ofs + 12]
                cls.dprint(
                    f"\n==== SECTOR {sector_idx} (0x{sector_ofs:02X} - 0x{sector_ofs + 11:02X}) ====",
                    logf,
                )
                cls.dprint(
                    f"[0x{sector_ofs:02X}] Sector raw bytes: "
                    f"{' '.join(f'{b:02X}' for b in sec)}",
                    logf,
                )

                Bool1 = bool(sec[0])
                Bool2 = bool(sec[1])
                NumInstances = struct.unpack_from("<h", sec, 2)[0]
                NumShadows = struct.unpack_from("<h", sec, 4)[0]
                NumLevels = struct.unpack_from("<h", sec, 6)[0]
                NumLights = struct.unpack_from("<h", sec, 8)[0]
                NumTextures = struct.unpack_from("<h", sec, 10)[0]

                cls.dprint(
                    f"[0x{sector_ofs:02X}] Bool1: {Bool1} (byte value: {sec[0]:02X})",
                    logf,
                )
                cls.dprint(
                    f"[0x{sector_ofs + 1:02X}] Bool2: {Bool2} (byte value: {sec[1]:02X})",
                    logf,
                )
                cls.dprint(
                    f"[0x{sector_ofs + 2:02X}] NumInstances (int16): {NumInstances}",
                    logf,
                )
                cls.dprint(
                    f"[0x{sector_ofs + 4:02X}] NumShadows   (int16): {NumShadows}",
                    logf,
                )
                cls.dprint(
                    f"[0x{sector_ofs + 6:02X}] NumLevels    (int16): {NumLevels}",
                    logf,
                )
                cls.dprint(
                    f"[0x{sector_ofs + 8:02X}] NumLights    (int16): {NumLights}",
                    logf,
                )
                cls.dprint(
                    f"[0x{sector_ofs + 10:02X}] NumTextures  (int16): {NumTextures}",
                    logf,
                )

                level_ofs = sector_ofs + 12

                cls.dprint("Levels:", logf)
                for level_idx in range(NumLevels):
                    X_raw = struct.unpack_from("<i", file_bytes, level_ofs + 0)[0]
                    Y_raw = struct.unpack_from("<i", file_bytes, level_ofs + 4)[0]
                    Z_raw = struct.unpack_from("<i", file_bytes, level_ofs + 8)[0]
                    NumInstances_lvl = struct.unpack_from(
                        "<h", file_bytes, level_ofs + 12
                    )[0]
                    Flags_lvl = struct.unpack_from("<h", file_bytes, level_ofs + 14)[0]

                    X = X_raw / 4096.0
                    Y = Y_raw / 4096.0
                    Z = Z_raw / 4096.0

                    cls.dprint(f"    Level {level_idx}:", logf)
                    cls.dprint(
                        f"      [0x{level_ofs:02X}] X (int32/4096): {X}",
                        logf,
                    )
                    cls.dprint(
                        f"      [0x{level_ofs + 4:02X}] Y (int32/4096): {Y}",
                        logf,
                    )
                    cls.dprint(
                        f"      [0x{level_ofs + 8:02X}] Z (int32/4096): {Z}",
                        logf,
                    )
                    cls.dprint(
                        f"      [0x{level_ofs + 12:02X}] NumInstances (int16): {NumInstances_lvl}",
                        logf,
                    )
                    cls.dprint(
                        f"      [0x{level_ofs + 14:02X}] Flags (int16): {Flags_lvl}",
                        logf,
                    )

                    level_ofs += 16

                cls.dprint("Instances:", logf)
                for instance_idx in range(NumInstances):
                    inst_base = level_ofs + instance_idx * 16
                    ID = struct.unpack_from("<h", file_bytes, inst_base + 0)[0]
                    RenderListID = struct.unpack_from("<b", file_bytes, inst_base + 2)[0]
                    BuildingSwap = struct.unpack_from("<b", file_bytes, inst_base + 3)[0]
                    ResourceID = struct.unpack_from("<I", file_bytes, inst_base + 4)[0]
                    MeshOffset = struct.unpack_from("<I", file_bytes, inst_base + 8)[0]
                    Pointer = struct.unpack_from("<I", file_bytes, inst_base + 12)[0]

                    cls.dprint(f"  Instance {instance_idx}:", logf)
                    cls.dprint(
                        f"    [0x{inst_base:02X}] ModelID (int16): {ID}",
                        logf,
                    )
                    cls.dprint(
                        f"    [0x{inst_base + 2:02X}] RenderListID (int8): {RenderListID}",
                        logf,
                    )
                    cls.dprint(
                        f"    [0x{inst_base + 3:02X}] BuildingSwap (int8): {BuildingSwap}",
                        logf,
                    )
                    cls.dprint(
                        f"    [0x{inst_base + 4:02X}] ResourceID (uint32): "
                        f"0x{ResourceID:08X} ({ResourceID})",
                        logf,
                    )
                    cls.dprint(
                        f"    [0x{inst_base + 8:02X}] MeshOffset (uint32): "
                        f"0x{MeshOffset:08X} ({MeshOffset})",
                        logf,
                    )
                    cls.dprint(
                        f"    [0x{inst_base + 12:02X}] Pointer (uint32): "
                        f"0x{Pointer:08X} ({Pointer})",
                        logf,
                    )

                    if MeshOffset != 0:
                        mesh_offsets_found.add(MeshOffset)

                level_ofs += 16 * NumInstances

                shadow_base = level_ofs
                if NumShadows > 0:
                    shadow_stride = 20
                    cls.dprint(
                        f"Shadows ({NumShadows} entries @0x{shadow_base:06X}):",
                        logf,
                    )
                    for shadow_idx in range(NumShadows):
                        s_off = shadow_base + shadow_idx * shadow_stride
                        cls.dprint(
                            f"    Shadow {shadow_idx}: [0x{s_off:06X}] "
                            + file_bytes[s_off : s_off + shadow_stride]
                            .hex(" ")
                            .upper(),
                            logf,
                        )

                        CenterX = struct.unpack_from("<i", file_bytes, s_off + 0)[0] / 4096.0
                        CenterY = struct.unpack_from("<i", file_bytes, s_off + 4)[0] / 4096.0
                        CenterZ = struct.unpack_from("<e", file_bytes, s_off + 8)[0]
                        SizeX = struct.unpack_from("<h", file_bytes, s_off + 10)[0] / 4096.0
                        SizeY = struct.unpack_from("<h", file_bytes, s_off + 12)[0] / 4096.0
                        SizeZ = struct.unpack_from("<h", file_bytes, s_off + 14)[0] / 4096.0
                        Unknown3 = struct.unpack_from("<h", file_bytes, s_off + 16)[0]
                        Id = struct.unpack_from("B", file_bytes, s_off + 18)[0]
                        Pad = struct.unpack_from("B", file_bytes, s_off + 19)[0]

                        cls.dprint(f"      CenterX:   {CenterX}", logf)
                        cls.dprint(f"      CenterY:   {CenterY}", logf)
                        cls.dprint(f"      CenterZ:   {CenterZ}", logf)
                        cls.dprint(f"      SizeX:     {SizeX}", logf)
                        cls.dprint(f"      SizeY:     {SizeY}", logf)
                        cls.dprint(f"      Unknown2:  {SizeZ}", logf)
                        cls.dprint(f"      Unknown3:  {Unknown3}", logf)
                        cls.dprint(f"      Id:        {Id}", logf)
                        cls.dprint(f"      Padding:   {Pad}", logf)

                    level_ofs += NumShadows * shadow_stride

                light_base = level_ofs
                if NumLights > 0:
                    light_stride = 20
                    cls.dprint(
                        f"Lights ({NumLights} entries @0x{light_base:06X}):",
                        logf,
                    )
                    for light_idx in range(NumLights):
                        l_off = light_base + light_idx * light_stride
                        cls.dprint(
                            f"    Light {light_idx}: [0x{l_off:06X}] "
                            + file_bytes[l_off : l_off + light_stride]
                            .hex(" ")
                            .upper(),
                            logf,
                        )

                        X_raw = struct.unpack_from("<I", file_bytes, l_off + 0)[0]
                        Y_raw = struct.unpack_from("<I", file_bytes, l_off + 4)[0]
                        Z_raw = struct.unpack_from("<I", file_bytes, l_off + 8)[0]
                        Size_raw = struct.unpack_from("<H", file_bytes, l_off + 12)[0]
                        Id = struct.unpack_from("<B", file_bytes, l_off + 14)[0]
                        R = struct.unpack_from("<B", file_bytes, l_off + 16)[0]
                        G = struct.unpack_from("<B", file_bytes, l_off + 17)[0]
                        B = struct.unpack_from("<B", file_bytes, l_off + 18)[0]

                        X = X_raw / 4096.0
                        Y = Y_raw / 4096.0
                        Z = Z_raw / 4096.0
                        Size = Size_raw / 4096.0

                        cls.dprint(f"      X: {X}", logf)
                        cls.dprint(f"      Y: {Y}", logf)
                        cls.dprint(f"      Z: {Z}", logf)
                        cls.dprint(f"      Id: {Id}", logf)
                        cls.dprint(f"      Color: {R} {G} {B}", logf)
                        cls.dprint(f"      Size: {Size}", logf)

                        light_data = bpy.data.lights.new(
                            name=f"CW_Light_{light_idx}", type="POINT"
                        )
                        light_object = bpy.data.objects.new(
                            name=f"CW_Light_{light_idx}", object_data=light_data
                        )
                        context.collection.objects.link(light_object)
                        light_object.location = (X, Y, Z)
                        light_data.color = (R / 255.0, G / 255.0, B / 255.0)
                        light_data.energy = max(1.0, Size * 1000.0)
                        light_data.shadow_soft_size = Size
                        light_object["CW_LightID"] = Id

                    level_ofs += NumLights * light_stride

                if NumTextures > 0:
                    cls.dprint(f"Textures ({NumTextures} IDs):", logf)
                    for tex_idx in range(NumTextures):
                        tex_offset = level_ofs + tex_idx * 2
                        tex_id = struct.unpack_from("<H", file_bytes, tex_offset)[0]
                        cls.dprint(
                            f"  [0x{tex_offset:02X}] Texture ID {tex_idx}: {tex_id}",
                            logf,
                        )
                    level_ofs += NumTextures * 2

                sector_size = (
                    12
                    + (NumLevels * 16)
                    + (NumInstances * 16)
                    + (NumShadows * 20)
                    + (NumLights * 20)
                    + (NumTextures * 2)
                )
                sector_ofs += sector_size

            cls.dprint("\n==== MESH HEADERS FROM ALL INSTANCES ====", logf)

            current_dir = os.path.dirname(filepath)
            wbl_basename = os.path.basename(filepath)
            wbl_stem, _ = os.path.splitext(wbl_basename)

            material_bank = cls.MaterialBank(current_dir, logf)

            for MeshOffset in sorted(mesh_offsets_found):
                if MeshOffset < 0 or MeshOffset > len(file_bytes) - 48:
                    cls.dprint(
                        f"  [0x{MeshOffset:02X}] MeshOffset out of file bounds",
                        logf,
                    )
                    continue

                mdl_ident = file_bytes[MeshOffset : MeshOffset + 4]
                ident_str = " ".join(f"{b:02X}" for b in mdl_ident)
                try:
                    mdl_ascii = mdl_ident.decode("ascii", errors="replace")
                except Exception:
                    mdl_ascii = "??"

                unknown = struct.unpack_from("<b", file_bytes, MeshOffset + 4)[0]
                numMaterials = struct.unpack_from("<b", file_bytes, MeshOffset + 5)[0]
                numVertices = struct.unpack_from("<h", file_bytes, MeshOffset + 6)[0]
                field8 = struct.unpack_from("<f", file_bytes, MeshOffset + 8)[0]
                fieldC = struct.unpack_from("<f", file_bytes, MeshOffset + 12)[0]
                boundmin = cls.read_vec3_int4096(file_bytes, MeshOffset + 16)
                boundmax = cls.read_vec3_int4096(file_bytes, MeshOffset + 28)
                translationFactor = struct.unpack_from(
                    "<f", file_bytes, MeshOffset + 40
                )[0]
                scaleFactor = struct.unpack_from("<f", file_bytes, MeshOffset + 44)[0]

                cls.dprint(
                    f"  [0x{MeshOffset:02X}] MDL Identifier: {ident_str} ('{mdl_ascii}')",
                    logf,
                )
                cls.dprint(
                    f"    [0x{MeshOffset + 4:02X}] Unknown (int8): {unknown}",
                    logf,
                )
                cls.dprint(
                    f"    [0x{MeshOffset + 5:02X}] numMaterials (int8): {numMaterials}",
                    logf,
                )
                cls.dprint(
                    f"    [0x{MeshOffset + 6:02X}] numVertices (int16): {numVertices}",
                    logf,
                )
                cls.dprint(
                    f"    [0x{MeshOffset + 8:02X}] Field 8 (float): {field8} ({field8})",
                    logf,
                )
                cls.dprint(
                    f"    [0x{MeshOffset + 12:02X}] Field C (float): {fieldC} ({fieldC})",
                    logf,
                )
                cls.dprint(
                    f"    [0x{MeshOffset + 16:02X}] BoundMin (3 floats): "
                    f"({boundmin[0]}, {boundmin[1]}, {boundmin[2]})",
                    logf,
                )
                cls.dprint(
                    f"    [0x{MeshOffset + 28:02X}] BoundMax (3 floats): "
                    f"({boundmax[0]}, {boundmax[1]}, {boundmax[2]})",
                    logf,
                )
                cls.dprint(
                    f"    [0x{MeshOffset + 40:02X}] uv Offset: {translationFactor}",
                    logf,
                )
                cls.dprint(
                    f"    [0x{MeshOffset + 44:02X}] Scale Factor: {scaleFactor}",
                    logf,
                )

                stride = 16
                vertex_base = MeshOffset + 48

                all_verts: List[Tuple[float, float, float]] = []
                all_normals: List[Tuple[float, float, float]] = []
                all_uvs: List[Tuple[float, float]] = []

                for vi in range(numVertices):
                    v_off = vertex_base + vi * stride

                    x_raw = struct.unpack_from("<h", file_bytes, v_off + 0)[0]
                    y_raw = struct.unpack_from("<h", file_bytes, v_off + 2)[0]
                    z_raw = struct.unpack_from("<h", file_bytes, v_off + 4)[0]
                    x = x_raw / scaleFactor + PosnX
                    y = y_raw / scaleFactor + PosnY
                    z = z_raw / scaleFactor + PosnZ

                    nx_raw = struct.unpack_from("<h", file_bytes, v_off + 6)[0]
                    ny_raw = struct.unpack_from("<h", file_bytes, v_off + 8)[0]
                    nz_raw = struct.unpack_from("<h", file_bytes, v_off + 10)[0]
                    nx = nx_raw / 32768.0
                    ny = ny_raw / 32768.0
                    nz = nz_raw / 32768.0

                    u_raw = struct.unpack_from("<h", file_bytes, v_off + 12)[0]
                    v_raw = struct.unpack_from("<h", file_bytes, v_off + 14)[0]
                    u = (u_raw / 2048.0) + translationFactor * 2
                    v = 1.0 - (v_raw / 2048.0)

                    all_verts.append((x, y, z))
                    all_normals.append((nx, ny, nz))
                    all_uvs.append((u, v))

                vert_offset = 0
                material_table_offset = vertex_base + (numVertices * stride)

                for mi in range(numMaterials):
                    m_off = material_table_offset + mi * 12
                    tex_id = struct.unpack_from("<H", file_bytes, m_off + 0)[0]
                    vertex_count = struct.unpack_from("<H", file_bytes, m_off + 2)[0]
                    render_flags = struct.unpack_from("<B", file_bytes, m_off + 4)[0]
                    node = struct.unpack_from("<B", file_bytes, m_off + 5)[0]
                    field6 = struct.unpack_from("<B", file_bytes, m_off + 6)[0]
                    field7 = struct.unpack_from("<B", file_bytes, m_off + 7)[0]
                    variance_flags = struct.unpack_from("<i", file_bytes, m_off + 8)[0]

                    uv_mul = 3.0 if render_flags == 4 else 2.0

                    cls.dprint(f"---- Mesh Part {mi}: ----", logf)
                    cls.dprint(f"  Texture ID: {tex_id}", logf)
                    cls.dprint(f"  Vertex Count: {vertex_count}", logf)
                    cls.dprint(f"  Rendering Flags: {render_flags}", logf)
                    cls.dprint(f"  Node: {node}", logf)
                    cls.dprint(f"  Field6: {field6}", logf)
                    cls.dprint(f"  Field7: {field7}", logf)
                    cls.dprint(f"  VarianceFlags: {variance_flags}", logf)

                    global_base_index = len(world_verts)

                    for i in range(vertex_count):
                        idx = vert_offset + i
                        world_verts.append(all_verts[idx])

                        u_norm, v_norm = all_uvs[idx]
                        u_final = u_norm + translationFactor * uv_mul
                        world_uvs.append((u_final, v_norm))

                    local_faces = cls.tri_strip_to_tris(vertex_count)

                    mat_index = material_bank.get_slot(tex_id)
                    for (a, b, c) in local_faces:
                        world_faces.append(
                            (
                                global_base_index + a,
                                global_base_index + b,
                                global_base_index + c,
                            )
                        )
                        world_face_material_indices.append(mat_index)

                    vert_offset += vertex_count

            if world_faces and world_verts:
                mesh_name = f"CW_{wbl_stem}"
                mesh = bpy.data.meshes.new(mesh_name)
                mesh.from_pydata(world_verts, [], world_faces)
                mesh.update()

                uv_layer = mesh.uv_layers.new(name="UVMap")
                for poly_idx, poly in enumerate(mesh.polygons):
                    poly.material_index = world_face_material_indices[poly_idx]
                    for loop_index in poly.loop_indices:
                        v_idx = mesh.loops[loop_index].vertex_index
                        uv_layer.data[loop_index].uv = world_uvs[v_idx]

                material_bank.append_all_to_mesh(mesh)

                obj = bpy.data.objects.new(mesh.name, mesh)

                coll_name = f"{wbl_basename}"
                coll = bpy.data.collections.get(coll_name)
                if not coll:
                    coll = bpy.data.collections.new(coll_name)
                    if coll.name not in {c.name for c in context.scene.collection.children}:
                        context.scene.collection.children.link(coll)

                coll.objects.link(obj)

                if obj.name in context.collection.objects:
                    context.collection.objects.unlink(obj)
            else:
                cls.dprint(
                    "No vertices/faces accumulated for worldblock; nothing to create.",
                    logf,
                )

        except Exception as e:
            tb_str = traceback.format_exc()
            if logf:
                logf.write("IMPORT ERROR\n")
                logf.write(tb_str)
                logf.flush()
            raise RuntimeError(f"Import error while reading '{filepath}': {e}") from e
        finally:
            if logf:
                cls.dprint("==== END OF DEBUG LOG ====", logf)
                logf.close()
