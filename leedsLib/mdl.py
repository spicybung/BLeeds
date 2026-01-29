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
import math
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any

from mathutils import Matrix, Vector

#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
#   This script is for Stories .MDLs, the file format for actors & props            #
#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
# - Script resources:
# • https://gtamods.com/wiki/Relocatable_chunk (pre-process)
# • https://gtamods.com/wiki/Leeds_Engine (TODO: update stub)
# • https://gtamods.com/wiki/MDL (TODO: update stub with more documentation in own words)
# • https://github.com/aap/librwgta (*re'd RW/Leeds Engine source by The_Hero*)
# • https://github.com/aap/librwgta/blob/master/tools/storiesconv/rsl.h (ditto)
# • https://github.com/aap/librwgta/blob/master/tools/storiesconv/rslconv.cpp (ditto)
# • https://web.archive.org/web/20180712151513/http://gtamodding.ru/wiki/MDL (*Russian*)
# • https://web.archive.org/web/20180712151513/http://gtamodding.ru/wiki/MDL_importer (*ditto - by Alex/AK73 & good resource to start*)
# • https://web.archive.org/web/20180714005051/https://www.gtamodding.ru/wiki/GTA_Stories_RAW_Editor (ditto)
# • https://web-archive-org.translate.goog/web/20180712151513/http://gtamodding.ru/wiki/MDL?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (*English*)
# • https://web-archive-org.translate.goog/web/20180725082416/http://gtamodding.ru/wiki/MDL_importer?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (by Alex/AK73 - good resource to start w/out any other documentation)
# - Mod resources/cool stuff:
# • https://developer.valvesoftware.com/wiki/MDL_(Quake) (Rockstar Leeds MDL is loosely based on Quake MDL)
# • https://libertycity.net/files/gta-liberty-city-stories/48612-yet-another-img-editor.html (GTA3xx .img: .mdls, textures, animations)
# • https://gtaforums.com/topic/838537-lcsvcs-dir-files/
# • https://gtaforums.com/topic/285544-gtavcslcs-modding/
# • https://thegtaplace.com/forums/topic/12002-gtavcslcs-modding/
# • http://aap.papnet.eu/gta/RE/lcs_pipes.txt (a brief binary example of how bitflags work for PS2/PSP/Mobile Stories games)
# • https://libertycity.net/articles/gta-vice-city-stories/6773-how-one-of-the-best-grand-theft-auto.html
# • https://umdatabase.net/view.php?id=CB00495D (database collection of Grand Theft Auto prototypes)
# • https://www.ign.com/articles/2005/09/10/gta-liberty-city-stories-2 ( ...it's IGN, but old IGN at least)
# • https://lcsteam.net/community/forum/index.php/topic,337.msg9335.html#msg9335 (RW 3.7/4.0, .MDL's, .WRLD's, .BSP's... )
# • https://www.gamedeveloper.com/programming/opinion-why-on-earth-would-we-write-our-own-game-engine- (Renderwares fate)
# • https://vkvideo.ru/playlist/-76377865_3/video143954957_456239182?linked=1 ( *Russian* - VCS PSP MDL viewer by Daniil Sayanov)


#######################################################
# === LCS Bone Arrays ===

commonBoneOrder: Tuple[str, ...] = (
    "Root", "Pelvis", "Spine", "Spine1", "Neck", "Head",
    "Bip01 L Clavicle", "L UpperArm", "L Forearm", "L Hand", "L Finger", "Bip01 R Clavicle",
    "R UpperArm", "R Forearm", "R Hand", "R Finger", "L Thigh", "L Calf",
    "L Foot", "L Toe0", "R Thigh", "R Calf", "R Foot", "R Toe0"
)

kamBoneID: Tuple[int, ...] = (
    0, 1, 2, 3, 4, 5, 31, 32, 33, 34, 35, 21, 22, 23, 24, 25, 41, 42, 43, 2000, 51, 52, 53, 2001
)

kamFrameName: Tuple[str, ...] = (
    "Root", "Pelvis", "Spine", "Spine1", "Neck", "Head",
    "Bip01~L~Clavicle", "L~UpperArm", "L~Forearm", "L~Hand", "L~Finger", "Bip01~R~Clavicle",
    "R~UpperArm", "R~Forearm", "R~Hand", "R~Finger", "L~Thigh", "L~Calf",
    "L~Foot", "L~Toe0", "R~Thigh", "R~Calf", "R~Foot", "R~Toe0"
)

kamBoneType: Tuple[int, ...] = (
    0, 0, 0, 2, 0, 3, 2, 0, 0, 0, 1, 0, 0, 0, 0, 1, 2, 0, 0, 1, 0, 0, 0, 1
)

kamBoneIndex: Tuple[str, ...] = (
    "00", "01", "02", "03", "04", "05", "06", "07", "08", "09",
    "10", "11", "12", "13", "14", "15", "16", "17", "18", "19",
    "20", "21", "22", "23"
)

commonBoneParentsLCS: Dict[str, str] = {
    "Pelvis": "Root",
    "Spine": "Pelvis",
    "Spine1": "Spine",
    "Neck": "Spine1",
    "Head": "Neck",
    "Bip01 L Clavicle": "Spine1",
    "L UpperArm": "Bip01 L Clavicle",
    "L Forearm": "L UpperArm",
    "L Hand": "L Forearm",
    "L Finger": "L Hand",
    "Bip01 R Clavicle": "Spine1",
    "R UpperArm": "Bip01 R Clavicle",
    "R Forearm": "R UpperArm",
    "R Hand": "R Forearm",
    "R Finger": "R Hand",
    "L Thigh": "Pelvis",
    "L Calf": "L Thigh",
    "L Foot": "L Calf",
    "L Toe0": "L Foot",
    "R Thigh": "Pelvis",
    "R Calf": "R Thigh",
    "R Foot": "R Calf",
    "R Toe0": "R Foot",
}

#######################################################
# === VCS Bone Arrays ===

commonBoneOrderVCS: Tuple[str, ...] = (
    "root", "pelvis", "spine", "spine1", "neck", "head",
    "jaw", "bip01_l_clavicle", "l_upperarm", "l_forearm", "l_hand", "l_finger",
    "bip01_r_clavicle", "r_upperarm", "r_forearm", "r_hand", "r_finger", "l_thigh",
    "l_calf", "l_foot", "l_toe0", "r_thigh", "r_calf", "r_foot", "r_toe0"
)

commonBoneNamesVCS: Tuple[str, ...] = (
    "Root", "Pelvis", "Spine", "Spine1", "Neck", "Head",
    "Jaw", "Bip01 L Clavicle", "L UpperArm", "L Forearm", "L Hand", "L Finger",
    "Bip01 R Clavicle", "R UpperArm", "R Forearm", "R Hand", "R Finger", "L Thigh",
    "L Calf", "L Foot", "L Toe0", "R Thigh", "R Calf", "R Foot", "R Toe0"
)

kamBoneIDVCS: Tuple[int, ...] = (
    0, 1, 2, 3, 4, 5,
    8, 31, 32, 33, 34, 35,
    21, 22, 23, 24, 25, 41,
    42, 43, 2000, 51, 52, 53,
    2001
)

kamFrameNameVCS: Tuple[str, ...] = (
    "Root", "Pelvis", "Spine", "Spine1", "Neck", "Head",
    "Jaw", "Bip01~L~Clavicle", "L~UpperArm", "L~Forearm", "L~Hand", "L~Finger",
    "Bip01~R~Clavicle", "R~UpperArm", "R~Forearm", "R~Hand", "R~Finger", "L~Thigh",
    "L~Calf", "L~Foot", "L~Toe0", "R~Thigh", "R~Calf", "R~Foot", "R~Toe0"
)

kamBoneTypeVCS: Tuple[int, ...] = (
    0, 0, 0, 2, 0, 2,
    3, 2, 0, 0, 0, 1,
    0, 0, 0, 0, 1, 2,
    0, 0, 1, 0, 0, 0,
    1
)

kamBoneIndexVCS: Tuple[str, ...] = (
    "00", "01", "02", "03", "04", "05", "06", "07",
    "08", "09", "10", "11", "12", "13", "14", "15",
    "16", "17", "18", "19", "20", "21", "22", "23"
)

commonBoneParentsVCS: Dict[str, str] = {
    "pelvis": "root",
    "spine": "pelvis",
    "spine1": "spine",
    "neck": "spine1",
    "head": "neck",
    "jaw": "head",
    "bip01_l_clavicle": "spine1",
    "l_upperarm": "bip01_l_clavicle",
    "l_forearm": "l_upperarm",
    "l_hand": "l_forearm",
    "l_finger": "l_hand",
    "bip01_r_clavicle": "spine1",
    "r_upperarm": "bip01_r_clavicle",
    "r_forearm": "r_upperarm",
    "r_hand": "r_forearm",
    "r_finger": "r_hand",
    "l_thigh": "pelvis",
    "l_calf": "l_thigh",
    "l_foot": "l_calf",
    "l_toe0": "l_foot",
    "r_thigh": "pelvis",
    "r_calf": "r_thigh",
    "r_foot": "r_calf",
    "r_toe0": "r_foot",
}

#######################################################
# === Model Rendering Flags ===
FLAG_DRAWLAST: int = 0x4 | 0x8
FLAG_ADDITIVE: int = 0x8
FLAG_NO_ZWRITE: int = 0x40
FLAG_NO_SHADOWS: int = 0x80
FLAG_NO_BACKFACE_CULLING: int = 0x200000

#######################################################
# === Dataclasses and high-level containers ===
@dataclass
class StripSkinData:
    indices: List[int]
    weights: List[float]


@dataclass
class StripMeta:
    """Per-triangle-strip metadata."""
    base_vertex_index: int
    vertex_count: int
    skin_indices: List[List[int]] = field(default_factory=list)
    skin_weights: List[List[float]] = field(default_factory=list)


@dataclass
class StoriesPartGeom:
    """Geometry for one PS2 Stories 'part'."""
    verts: List[Tuple[float, float, float]] = field(default_factory=list)
    faces: List[Tuple[int, int, int]] = field(default_factory=list)
    uvs: List[Tuple[float,float]] = field(default_factory=list)
    strips_meta: List[StripMeta] = field(default_factory=list)
    vertex_colors: List[Any] = field(default_factory=list)
    loop_colors: List[Any] = field(default_factory=list)
    material_id: int = 0


@dataclass
class StoriesMaterialDesc:
    offset: int = 0
    texture: str = ""
    rgba: int = 0
    specular: float = 0.0


@dataclass
class StoriesPSPMesh:
    """Decoded PSP mesh/strip."""
    index: int
    verts: List[Tuple[float, float, float]] = field(default_factory=list)
    faces: List[Tuple[int, int, int]] = field(default_factory=list)
    uvs: List[Tuple[float, float]] = field(default_factory=list)
    colors: List[Tuple[int, int, int, int]] = field(default_factory=list)
    normals: List[Tuple[float, float, float]] = field(default_factory=list)
    bone_indices: List[List[int]] = field(default_factory=list)
    bone_weights: List[List[float]] = field(default_factory=list)
    mat_id: int = 0
    uv_scale: Tuple[float, float] = (1.0, 1.0)
    bonemap: List[int] = field(default_factory=list)


@dataclass
class StoriesArmatureInfo:
    """Raw frame/bone data, detached from Blender."""
    frame_mats_local: Dict[int, Matrix] = field(default_factory=dict)
    frame_mats_world: Dict[int, Matrix] = field(default_factory=dict)
    frame_names: Dict[int, str] = field(default_factory=dict)
    root_frame_ptr: int = 0


@dataclass
class StoriesGeometryInfo:
    """Holds PS2 geometry info for a single atomic."""
    part_offsets: List[int] = field(default_factory=list)
    part_material_ids: List[int] = field(default_factory=list)
    x_scale: float = 1.0
    y_scale: float = 1.0
    z_scale: float = 1.0
    translation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    materials: List[StoriesMaterialDesc] = field(default_factory=list)
    parts: List[StoriesPartGeom] = field(default_factory=list)


@dataclass
class StoriesPSPGeometryInfo:
    """Holds PSP geometry info for a single atomic."""
    flags: int = 0
    num_strips: int = 0
    num_verts: int = 0
    scale: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    pos: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    uv_format: int = 0
    col_format: int = 0
    norm_format: int = 0
    pos_format: int = 0
    weight_format: int = 0
    index_format: int = 0
    num_weights_per_vertex: int = 0
    materials: List[StoriesMaterialDesc] = field(default_factory=list)
    meshes: List[StoriesPSPMesh] = field(default_factory=list)


@dataclass
class StoriesAtomicInfo:
    """Decoded atomic block (section_type=2)."""
    section_type: int = 0
    import_type: int = 0
    frame_ptr: int = 0
    geom_ptr: int = 0
    model_info_id: int = 0
    vis_id_flag: int = 0
    hierarchy_ptr: int = 0
    armature: StoriesArmatureInfo = field(default_factory=StoriesArmatureInfo)
    ps2_geometry: StoriesGeometryInfo = field(default_factory=StoriesGeometryInfo)
    psp_geometry: StoriesPSPGeometryInfo = field(default_factory=StoriesPSPGeometryInfo)


@dataclass
class StoriesMDLContext:
    """Top-level parsed state for a Stories MDL file."""
    filepath: str
    platform: str
    mdl_type: str
    shrink: int = 0
    file_len: int = 0
    local_num_table: int = 0
    global_num_table: int = 0
    num_entries: int = 0
    ptr2_before_tex: int = 0
    allocated_memory: int = 0
    top_level_ptr: int = 0
    section_type: int = 0
    import_type: int = 0
    actor_mdl: bool = False
    renderflags_offset: int = 0
    debug_log: List[str] = field(default_factory=list)
    atomic: StoriesAtomicInfo = field(default_factory=StoriesAtomicInfo)
    root_names: Tuple[str, ...] = ("dummy",)

    def log(self, msg: str) -> None:
        self.debug_log.append(str(msg))
        print(msg)


#######################################################
# === Binary reading helpers ===


def read_i8(f) -> int:
    return struct.unpack("<b", f.read(1))[0]


def read_u8(f) -> int:
    return struct.unpack("<B", f.read(1))[0]


def read_i16(f) -> int:
    return struct.unpack("<h", f.read(2))[0]


def read_u16(f) -> int:
    return struct.unpack("<H", f.read(2))[0]


def read_i32(f) -> int:
    return struct.unpack("<i", f.read(4))[0]


def read_u32(f) -> int:
    return struct.unpack("<I", f.read(4))[0]


def read_bu32(f) -> int:
    return struct.unpack(">I", f.read(4))[0]


def read_f32(f) -> float:
    return struct.unpack("<f", f.read(4))[0]


def read_string(f, ptr: int) -> str:
    if ptr == 0:
        return ""
    current = f.tell()
    f.seek(ptr)
    s = bytearray()
    while True:
        c = f.read(1)
        if c == b"\x00" or c == b"":
            break
        s += c
    f.seek(current)
    return s.decode("utf-8", errors="ignore")


def read_point3(f) -> Vector:
    return Vector(struct.unpack("<3f", f.read(12)))


#######################################################
# === Matrix helpers ===


def read_local_matrix(f) -> Tuple[Matrix, int, Tuple[Vector, Vector, Vector, Vector]]:
    matrix_offset = f.tell()

    row1 = read_point3(f)  
    f.read(4)
    row2 = read_point3(f)  
    f.read(4)
    row3 = read_point3(f)  
    f.read(4)
    row4 = read_point3(f)  
    f.read(4)

    scale_factor = 1.0
    x = row4.x * scale_factor
    y = row4.y * scale_factor
    z = row4.z * scale_factor
    row4_scaled = Vector((x, y, z))

    mat = Matrix(
        (
            (row1.x, row2.x, row3.x, row4_scaled.x),
            (row1.y, row2.y, row3.y, row4_scaled.y),
            (row1.z, row2.z, row3.z, row4_scaled.z),
            (0.0, 0.0, 0.0, 1.0),
        )
    )
    return mat, matrix_offset, (row1, row2, row3, row4_scaled)


def read_global_matrix(f, offset: int) -> Matrix:
    cur = f.tell()
    f.seek(offset)

    row1 = read_point3(f)
    f.read(4)
    row2 = read_point3(f)
    f.read(4)
    row3 = read_point3(f)
    f.read(4)
    row4 = read_point3(f)
    f.read(4)

    f.seek(cur)

    scale_factor = 1.0
    x = row4.x * scale_factor
    y = row4.y * scale_factor
    z = row4.z * scale_factor
    row4_scaled = Vector((x, y, z))

    M = Matrix(
        (
            (row1.x, row2.x, row3.x, row4_scaled.x),
            (row1.y, row2.y, row3.y, row4_scaled.y),
            (row1.z, row2.z, row3.z, row4_scaled.z),
            (0.0, 0.0, 0.0, 1.0),
        )
    )
    return M


#######################################################
# === Small helpers for names, flags, etc ===
def canon_frame_name(name: str) -> str:
    return name.lower().replace("~", "_").replace(" ", "_")


def get_render_flag_names(render_flags: int) -> List[str]:
    names: List[str] = []
    if render_flags & FLAG_DRAWLAST:
        names.append("FLAG_DRAWLAST")
    if render_flags & FLAG_ADDITIVE:
        names.append("FLAG_ADDITIVE")
    if render_flags & FLAG_NO_ZWRITE:
        names.append("FLAG_NO_ZWRITE")
    if render_flags & FLAG_NO_SHADOWS:
        names.append("FLAG_NO_SHADOWS")
    if render_flags & FLAG_NO_BACKFACE_CULLING:
        names.append("FLAG_NO_BACKFACE_CULLING")
    if not names:
        names.append("No known render flags set")
    return names


#######################################################
# === Frame / Armature reading (no Blender objects) ===


def process_frame_tree(ctx: StoriesMDLContext, f, frame_ptr: int) -> StoriesArmatureInfo:
    arm = StoriesArmatureInfo()
    if frame_ptr == 0:
        return arm

    arm.root_frame_ptr = frame_ptr

    def _walk(ptr: int, parent_world: Matrix) -> None:
        if ptr == 0:
            return

        if ctx.platform == "PS2":
            name_ptr_offset = ptr + 0xA4
        else:
            name_ptr_offset = ptr + 0xA8
        if ctx.import_type == 2:
            name_ptr_offset += 4

        f.seek(name_ptr_offset)
        bone_name_ptr = read_u32(f)
        if bone_name_ptr != 0:
            cur = f.tell()
            f.seek(bone_name_ptr)
            name_bytes = bytearray()
            while True:
                b = f.read(1)
                if b == b"\x00" or not b:
                    break
                name_bytes.append(b[0])
            bone_name = name_bytes.decode("utf-8", errors="ignore")
            f.seek(cur)
        else:
            bone_name = "Bone"

        f.seek(ptr + 0x10)
        local_mat, _, _ = read_local_matrix(f)
        world_mat = parent_world @ local_mat

        arm.frame_mats_local[ptr] = local_mat
        arm.frame_mats_world[ptr] = world_mat
        arm.frame_names[ptr] = bone_name

        global_mat = read_global_matrix(f, ptr + 0x50)
        ctx.log(
            f"Frame 0x{ptr:X}: name='{bone_name}', local={local_mat}, world={world_mat}, global={global_mat}"
        )

        f.seek(ptr + 0x90)
        child_ptr = read_u32(f)
        f.seek(ptr + 0x94)
        sibling_ptr = read_u32(f)

        if child_ptr != 0:
            _walk(child_ptr, world_mat)
        if sibling_ptr != 0:
            _walk(sibling_ptr, parent_world)

    _walk(frame_ptr, Matrix.Identity(4))
    return arm


#######################################################
# === Material reading (PS2 + PSP share this block) ===
def read_material_list(ctx: StoriesMDLContext, f) -> List[StoriesMaterialDesc]:
    mats: List[StoriesMaterialDesc] = []

    _ = read_u32(f)
    _ = read_u32(f)
    _ = read_u32(f)

    material_list_ptr = read_u32(f)
    material_count = read_u32(f)

    ctx.log(f"🧵 Material List Ptr: 0x{material_list_ptr:X}")
    ctx.log(f"🎨 Material Count: {material_count}")

    if material_count <= 0:
        return mats

    old_pos = f.tell()
    f.seek(material_list_ptr)

    for i in range(material_count):
        ctx.log(f"  ↪ Reading Material {i + 1}/{material_count}")
        cur_mat = StoriesMaterialDesc()
        cur_mat.offset = f.tell()
        cur_mat_ptr = read_u32(f)
        ctx.log(f"    ⤷ Material Ptr: 0x{cur_mat_ptr:X}")
        old_mat_pos = f.tell()
        f.seek(cur_mat_ptr)

        tex_ptr = read_u32(f)
        ctx.log(f"    ⤷ Texture Ptr: 0x{tex_ptr:X}")
        if tex_ptr > 0:
            temp_pos = f.tell()
            f.seek(tex_ptr)
            tex_name = read_string(f, tex_ptr)
            cur_mat.texture = tex_name
            ctx.log(f"    🎯 Texture Name: {tex_name}")
            f.seek(temp_pos)

        rgba = read_u32(f)
        cur_mat.rgba = rgba
        ctx.log(f"    🎨 RGBA Value: 0x{rgba:08X}")

        _ = read_u32(f)

        spec_ptr = read_u32(f)
        ctx.log(f"    ⤷ Specular Ptr: 0x{spec_ptr:X}")
        if spec_ptr > 0:
            temp_pos = f.tell()
            f.seek(spec_ptr)
            _ = read_u32(f)
            _ = read_u32(f)
            spec_val = read_f32(f)
            cur_mat.specular = spec_val
            ctx.log(f"    ✨ Specular: {spec_val:.6f}")
            f.seek(temp_pos)

        f.seek(old_mat_pos)
        mats.append(cur_mat)

    f.seek(old_pos)
    return mats


#######################################################
# === PS2 Geometry read (parts, strips, skin) ===
def read_ps2_geometry(ctx: StoriesMDLContext, f, geom_ptr: int) -> StoriesGeometryInfo:
    g = StoriesGeometryInfo()
    ctx.log("Detected Section Type: 3 (Geometry, PS2)")

    f.seek(geom_ptr)

    g.materials = read_material_list(ctx, f)

    for i in range(13):
        f.read(4)
    ctx.log("✔ Skipped 13 DWORDs")

    xscale_offset = f.tell()
    g.x_scale = read_f32(f)
    yscale_offset = f.tell()
    g.y_scale = read_f32(f)
    zscale_offset = f.tell()
    g.z_scale = read_f32(f)
    ctx.log(f"🟧 xScale is at file offset: 0x{xscale_offset:X}")
    ctx.log(f"🟧 yScale is at file offset: 0x{yscale_offset - 4:X}")
    ctx.log(f"🟧 zScale is at file offset: 0x{zscale_offset - 4:X}")
    ctx.log(f"✔ xScale: {g.x_scale}, yScale: {g.y_scale}, zScale: {g.z_scale}")

    scale_factor = 100.0
    global_scale = scale_factor * 0.00000030518203134641490805874367518203

    offset_x = f.tell()
    tx = read_f32(f) * scale_factor / 100.0
    ctx.log(f"✔ TranslationFactor X read at file offset: 0x{offset_x:X} ({offset_x})")

    offset_y = f.tell()
    ty = read_f32(f) * scale_factor / 100.0
    ctx.log(f"✔ TranslationFactor Y read at file offset: 0x{offset_y:X} ({offset_y})")

    offset_z = f.tell()
    tz = read_f32(f) * scale_factor / 100.0
    ctx.log(f"✔ TranslationFactor Z read at file offset: 0x{offset_z:X} ({offset_z})")

    g.translation = (tx, ty, tz)
    ctx.log(f"✔ TranslationFactor: {g.translation}")

    part_offsets: List[int] = []
    part_material_ids: List[int] = []

    part_table_seek = f.tell()

    prop_offsets_from_table = None
    prop_geo_start = None

    peek_bytes = f.read(4)
    marker_val = struct.unpack_from("<I", peek_bytes)[0] if len(peek_bytes) == 4 else 0

    mdl_type_u = (str(getattr(ctx, "mdl_type", "") or "")).upper().strip()

    if (marker_val & 0xFF000000) == 0x60000000:
        has_part_table = False

    elif mdl_type_u == "PED":
        has_part_table = True

    else:
        part_count_hint = len(g.materials) if g.materials else 0
        has_part_table = True  

        if part_count_hint > 0:
            f.seek(part_table_seek)
            offs = [read_u32(f) for _ in range(part_count_hint)]

            monotonic = (offs[0] == 0) and all(offs[i] <= offs[i + 1] for i in range(len(offs) - 1))
            sane = all(o < 0x400000 for o in offs)

            found_dma = None
            scan_base = part_table_seek
            max_scan = 0x800  
            for i in range(0, max_scan, 4):
                f.seek(scan_base + i)
                buf = f.read(4)
                if len(buf) < 4:
                    break
                v = struct.unpack_from("<I", buf)[0]
                if (v & 0xFF000000) == 0x60000000:
                    found_dma = scan_base + i
                    break

            if monotonic and sane and found_dma is not None:
                has_part_table = False
                prop_offsets_from_table = offs
                prop_geo_start = found_dma

    f.seek(part_table_seek)


    if has_part_table:
        ctx.log("✔ Detected explicit part table (ped/clump). Reading part offsets...")
        temp = read_u32(f)
        while True:
            if (temp & 0x60000000) == 0x60000000:
                break
            for _ in range(6):
                f.read(4)
            temp_offset = read_u32(f)
            part_offsets.append(temp_offset)
            _short1 = read_u16(f)
            temp_mat = read_u16(f)
            part_material_ids.append(temp_mat)
            f.read(4)
            f.read(4)
            f.read(4)
            temp = read_u32(f)
        f.seek(-4, 1)
        geo_start = f.tell()
        g.part_offsets = part_offsets
        g.part_material_ids = part_material_ids
        ctx.log(f"✔ partOffsets: {part_offsets}")
        ctx.log(f"✔ partMaterials: {part_material_ids}")
        ctx.log(f"geoStart: 0x{geo_start:X}")
    else:
        if prop_offsets_from_table is not None and prop_geo_start is not None:
            part_offsets = list(prop_offsets_from_table)
            part_material_ids = list(range(len(part_offsets)))
            geo_start = int(prop_geo_start)

            g.part_offsets = part_offsets
            g.part_material_ids = part_material_ids

            ctx.log("✔ Detected prop offset table (u32 offsets).")
            ctx.log(f"✔ partOffsets: {part_offsets}")
            ctx.log(f"✔ partMaterials: {part_material_ids}")
            ctx.log(f"geoStart: 0x{geo_start:X}")

            f.seek(geo_start, 0)
        else:
            part_count = len(g.materials) if g.materials else 0
            scan_base = f.tell()
            initial_offset = 0
            found = False
            search_limit = 0x100
            for i in range(search_limit):
                f.seek(scan_base + i)
                buf = f.read(4)
                if len(buf) < 4:
                    break
                marker_val = struct.unpack_from("<I", buf)[0]
                if (marker_val & 0xFF000000) == 0x60000000:
                    initial_offset = i
                    found = True
                    break
            if found:
                dma_tag_pos = scan_base + initial_offset
                geo_start_tmp = dma_tag_pos - 4
                offset_acc = 4
                for p in range(part_count):
                    part_offsets.append(offset_acc)
                    part_material_ids.append(p)
                    f.seek(geo_start_tmp + offset_acc)
                    tag_buf = f.read(4)
                    if len(tag_buf) < 4:
                        break
                    tag_val = struct.unpack_from("<I", tag_buf)[0]
                    qwc = tag_val & 0xFFFF
                    seg_size = (qwc * 16) + 16
                    offset_acc += seg_size
            else:
                for p in range(part_count):
                    part_offsets.append(0)
                    part_material_ids.append(p)
            dma_tag_pos = scan_base + initial_offset
            geo_start = dma_tag_pos - 4
            f.seek(geo_start, 0)
            g.part_offsets = part_offsets
            g.part_material_ids = part_material_ids
            ctx.log(f"✔ partOffsets: {part_offsets}")
            ctx.log(f"✔ partMaterials: {part_material_ids}")
            ctx.log(f"geoStart: 0x{geo_start:X}")
    
        if g.part_offsets:
            ctx.log("====== Geometry dmaPacket Offsets ======")
            for i, po in enumerate(g.part_offsets):
                ctx.log(f"Part {i + 1}: dmaPacket offset 0x{(geo_start + po):X}")
            ctx.log("===================================")
    

    def scan_for_vif_header(
        *,
        start: int,
        end: int,
        wanted_cmd: int,
        max_scan_bytes: int = 0x200,
        step: int = 4,
        require_b1_80: bool = True,
    ) -> Optional[Tuple[int, bytes]]:
        if end < start:
            return None
        scan_end = min(end, start + max_scan_bytes)
        pos = start
        while pos + 4 <= scan_end:
            f.seek(pos, 0)
            hdr = f.read(4)
            if len(hdr) < 4:
                return None
            b0, b1, b2, b3 = hdr[0], hdr[1], hdr[2], hdr[3]
            if require_b1_80 and b1 != 0x80:
                pos += step
                continue
            if b3 == wanted_cmd:
                return pos, hdr
            pos += step
        return None

    for part_index, part_offset in enumerate(part_offsets):
        part_addr = geo_start + part_offset

        part = StoriesPartGeom()
        part.material_id = int(part_material_ids[part_index])

        if part_index + 1 < len(part_offsets):
            next_part_addr = geo_start + part_offsets[part_index + 1]
        else:
            f.seek(0, 2)
            next_part_addr = f.tell()

        f.seek(part_addr)
        ctx.log(
            f"\n🔄 Reading geometry dmaOffset {part_index + 1}/{len(part_offsets)} (Offset: 0x{part_addr:X})"
        )

        while f.tell() < next_part_addr:
            marker_seek = f.tell()
            ctx.log(f"🔎 Looking for triangle strip marker at offset: 0x{marker_seek:X}")

            marker = read_u32(f)
            ctx.log(f"   Read marker 0x{marker:08X} at 0x{marker_seek:X}")

            if marker == 0x6C018000:
                split_flag_offset = marker_seek
                ctx.log(
                    f"✔ 0x6C018000 split flag found at 0x{split_flag_offset:X} -- reading split section header..."
                )

                _marker_bytes = f.read(4)
                zeros1_offset = f.tell()
                zeros1 = f.read(4)
                ctx.log(
                    f"  [0x{zeros1_offset:X}] zeros1: {zeros1.hex()} (should be 00 00 00 00)"
                )
                zeros2_offset = f.tell()
                zeros2 = f.read(4)
                ctx.log(
                    f"  [0x{zeros2_offset:X}] zeros2: {zeros2.hex()} (should be 00 00 00 00)"
                )

                vert_count1_offset = f.tell()
                vert_count1 = read_u8(f)
                ctx.log(f"  [0x{vert_count1_offset:X}] vert_count1: {vert_count1}")
                pad3_offset = f.tell()
                pad3 = f.read(3)
                ctx.log(
                    f"  [0x{pad3_offset:X}] pad3: {pad3.hex()} (should be 00 00 00)"
                )

                vert_count2_offset = f.tell()
                vert_count2 = read_u8(f)
                ctx.log(f"  [0x{vert_count2_offset:X}] vert_count2: {vert_count2}")

                flags_offset = f.tell()
                flags = read_u16(f)
                vert_count_dma = flags & 0x7FFF
                culling_disabled = bool(flags & 0x8000)
                ctx.log(f"  [0x{flags_offset:X}] flags: 0x{flags:04X}")
                ctx.log(f"     - vert_count_dma (flags & 0x7FFF): {vert_count_dma}")
                ctx.log(f"     - culling_disabled (flags & 0x8000): {culling_disabled}")

                pad4_offset = f.tell()
                pad4 = f.read(4)
                ctx.log(f"  [0x{pad4_offset:X}] pad4: {pad4.hex()}")

                tech1_offset = f.tell()
                tech1 = f.read(4)
                ctx.log(
                    f"  [0x{tech1_offset:X}] tech1: {tech1.hex()} (typically 40404020)"
                )

                tech2_offset = f.tell()
                tech2 = f.read(4)
                ctx.log(f"  [0x{tech2_offset:X}] tech2: {tech2.hex()}")

                f.seek(marker_seek)

                if vert_count1 != vert_count2:
                    ctx.log(
                        f"  WARNING: vert_count1 ({vert_count1}) != vert_count2 ({vert_count2}) at 0x{f.tell():X}"
                    )
                else:
                    ctx.log(f"✔ Vertex counts match: {vert_count1}")
                ctx.log("=== END OF 0x6C018000 SPLIT BLOCK ===")

            f.seek(16, 1)

            while (marker & 0x60000000) != 0x60000000 and f.tell() < next_part_addr:
                ctx.log(
                    f"      Not a tri-strip flag (got 0x{marker:08X}). Skipping 44 bytes (11 DWORDs) at 0x{f.tell():X}"
                )
                for _ in range(11):
                    f.read(4)
                skip_offset = f.tell()
                marker = read_u32(f)
                ctx.log(
                    f"      Checked tri-strip marker 0x{marker:08X} at 0x{skip_offset:X}"
                )

            if (marker & 0x60000000) != 0x60000000:
                ctx.log(f"✗ No valid strip marker found, breaking out at offset 0x{f.tell():X}")
                break

            if marker == 0x60000000:
                ctx.log(
                    f"✔ 0x60000000 tri-strip flag found at 0x{marker_seek:X}, skipping 16 bytes to 0x{marker_seek + 16:X}"
                )
                f.seek(marker_seek, 0)
            elif marker == 0x6C018000:
                ctx.log(
                    f"✔ 0x6C018000 split section marker found at 0x{marker_seek:X}, rewinding to flag for detailed breakdown"
                )
                f.seek(marker_seek, 0)
            else:
                ctx.log(
                    f"✔ Valid tri-strip flag (0x{marker:08X}) found at 0x{marker_seek:X}, rewinding to flag"
                )
                f.seek(-4, 1)

            for _ in range(4):
                f.read(4)

            tri_strip_start = f.tell()
            ctx.log(f"  Tri-Strip Start: 0x{tri_strip_start:X}")

            for _ in range(8):
                f.read(4)
            _ = read_u16(f)
            cur_strip_vert_count = read_u8(f)
            pad_byte = read_u8(f)
            ctx.log(
                f"    - curStripVertCount: {cur_strip_vert_count} (padByte={pad_byte}) at 0x{f.tell():X}"
            )

            vertex_data_offset = f.tell()
            ctx.log(
                f"    🧊 Vertex data begins at file offset: 0x{vertex_data_offset:X} ({vertex_data_offset})"
            )

            verts: List[Tuple[float, float, float]] = []
            skin_indices: List[List[int]] = []
            skin_weights: List[List[float]] = []

            base_idx = len(part.verts)

            for vi in range(cur_strip_vert_count):
                offset_x = f.tell()
                x_raw = read_i16(f)
                offset_y = f.tell()
                y_raw = read_i16(f)
                offset_z = f.tell()
                z_raw = read_i16(f)

                x = x_raw * g.x_scale * global_scale + tx
                y = y_raw * g.y_scale * global_scale + ty
                z = z_raw * g.z_scale * global_scale + tz

                verts.append((x, y, z))

                ctx.log(f"        🧊 Vertex {vi}:")
                ctx.log(
                    f"           • X Offset: 0x{offset_x:X}, Raw: {x_raw}, Final: {x:.6f}"
                )
                ctx.log(
                    f"           • Y Offset: 0x{offset_y:X}, Raw: {y_raw}, Final: {y:.6f}"
                )
                ctx.log(
                    f"           • Z Offset: 0x{offset_z:X}, Raw: {z_raw}, Final: {z:.6f}"
                )

            part.verts.extend(verts)

            for i in range(2, cur_strip_vert_count):
                if (i % 2) == 0:
                    v0 = base_idx + i - 2
                    v1 = base_idx + i - 1
                    v2 = base_idx + i
                else:
                    v0 = base_idx + i - 1
                    v1 = base_idx + i - 2
                    v2 = base_idx + i
                if v0 != v1 and v1 != v2 and v2 != v0:
                    part.faces.append((v0, v1, v2))

            if (cur_strip_vert_count % 2) == 1:
                pad_short_pos = f.tell()
                pad_short = read_i16(f)
                ctx.log(
                    f"    ⬛ Padding short after verts (odd count): {pad_short} at 0x{pad_short_pos:X}"
                )

            align4 = f.tell() % 4
            if align4:
                pad_bytes = 4 - align4
                f.read(pad_bytes)
                ctx.log(f"    🟦 Align to dword after verts: {pad_bytes} bytes")

            
            uv_header_pos = f.tell()
            uv_header = None
            found = scan_for_vif_header(
                start=uv_header_pos,
                end=next_part_addr,
                wanted_cmd=0x76,
                max_scan_bytes=0x200,
                step=4,
                require_b1_80=True,
            )
            if found:
                uv_header_pos, uv_header = found
                ctx.log(f"    ✔ Found UV header by scan at 0x{uv_header_pos:X}")
            else:
                f.seek(uv_header_pos, 0)
                uv_header = f.read(4)
                if len(uv_header) < 4:
                    break
                ctx.log(
                    f"    ⚠ UV header scan failed; using current position 0x{uv_header_pos:X}"
                )

            f.seek(uv_header_pos + 4, 0)
            b0, b1, b2, b3 = uv_header[0], uv_header[1], uv_header[2], uv_header[3]
            cur_strip_tvert_count = int(b2)
            if cur_strip_tvert_count <= 0 or cur_strip_tvert_count > 0x80:
                ctx.log(
                    f"    ⚠ UV count b2={cur_strip_tvert_count} looks invalid; using curStripVertCount={cur_strip_vert_count}"
                )
                cur_strip_tvert_count = int(cur_strip_vert_count)
            ctx.log(
                f"    ⬛ UV header at 0x{uv_header_pos:X}: b0=0x{b0:02X}, b1=0x{b1:02X}, b2 (count)={cur_strip_tvert_count}, b3=0x{b3:02X}"
            )
            if b3 != 0x76:
                ctx.log(f"    ⚠ Unexpected UV section header b3=0x{b3:02X} at 0x{uv_header_pos:X}")

            uvs: List[Tuple[float, float]] = []
            uv_bytes = f.read(cur_strip_tvert_count * 2)
            for i in range(cur_strip_tvert_count):
                if (i * 2 + 1) < len(uv_bytes):
                    u_raw = uv_bytes[i * 2]
                    v_raw = uv_bytes[i * 2 + 1]
                    u_f = u_raw / 127.5
                    v_f = v_raw / 127.5
                    uvs.append((u_f, v_f))
                    ctx.log(
                        f"      🟪 UV {i}: U={u_f:.6f}, V={v_f:.6f} (raw: {u_raw}, {v_raw})"
                    )
            pad = (4 - ((cur_strip_tvert_count * 2) % 4)) % 4
            if pad:
                f.read(pad)
                ctx.log(f"    🟦 Padding after UVs: {pad} bytes")
            part.uvs.extend(uvs)

            while True:
                subsection_pos = f.tell()
                header = f.read(4)
                if len(header) < 4:
                    break

                marker_val = struct.unpack("<I", header)[0]
                b0, b1, b2, b3 = header[0], header[1], header[2], header[3]

                if marker_val == 0x60000000:
                    ctx.log(
                        f"✔ Found 0x60000000 strip marker at 0x{subsection_pos:X} -- skipping 16 bytes"
                    )
                    f.seek(16, 1)
                    break
                elif marker_val == 0x6C018000:
                    ctx.log(
                        f"✔ Found 0x6C018000 split flag at 0x{subsection_pos:X} -- rewinding to marker"
                    )
                    f.seek(subsection_pos, 0)
                    break

                if b1 == 0x80 and b3 in (0x6F, 0x6A, 0x6C):
                    section_count = b2
                    ctx.log(
                        f"   >> Subsection header: b1={b1:02X}, count={section_count}, b3={b3:02X} at 0x{subsection_pos:X}"
                    )

                    if b3 == 0x6F:
                        ctx.log(f"      🎨 Reading {section_count} vertex colors")
                        for i in range(section_count):
                            vcolor = read_u16(f)
                            r = (vcolor & 0x1F) * (1.0 / 32.0)
                            gcol = ((vcolor >> 5) & 0x1F) * (1.0 / 32.0)
                            b = ((vcolor >> 10) & 0x1F) * (1.0 / 32.0)
                            a = ((vcolor >> 15) & 0x01) * 1.0
                            ctx.log(
                                f"         R={r:.3f} G={gcol:.3f} B={b:.3f} A={a:.1f} (raw=0x{vcolor:04X})"
                            )
                        pad = 2 - ((2 * section_count) % 4)
                        if pad != 4:
                            f.read(pad)

                    elif b3 == 0x6A:
                        ctx.log(f"      🧲 Reading {section_count} normals")
                        norms: List[Tuple[float, float, float]] = []
                        for i in range(section_count):
                            nx = read_i8(f) / 128.0
                            ny = read_i8(f) / 128.0
                            nz = read_i8(f) / 128.0
                            norms.append((nx, ny, nz))
                            ctx.log(f"         N={nx:.4f} {ny:.4f} {nz:.4f}")
                        pad = 4 - ((3 * section_count) % 4)
                        if pad != 4:
                            f.read(pad)

                        if section_count:
                            if not hasattr(part, 'normals'):
                                part.normals = []  
                            part.normals.extend(norms)

                    elif b3 == 0x6C:
                        ctx.log(f"      🦴 Reading {section_count} skin weights")
                        for i in range(section_count):
                            bone1 = read_u16(f) // 4
                            _ = read_u8(f)
                            w1 = read_u8(f) / 128.0
                            bone2 = read_u16(f) // 4
                            _ = read_u8(f)
                            w2 = read_u8(f) / 128.0
                            bone3 = read_u16(f) // 4
                            _ = read_u8(f)
                            w3 = read_u8(f) / 128.0
                            bone4 = read_u16(f) // 4
                            _ = read_u8(f)
                            w4 = read_u8(f) / 128.0

                            ctx.log(
                                f"         B1={bone1} W1={w1:.4f} ... B4={bone4} W4={w4:.4f}"
                            )

                            indices = [bone1, bone2, bone3, bone4]
                            weights = [w1, w2, w3, w4]

                            skin_indices.append(indices)
                            skin_weights.append(weights)
                    continue

            if len(skin_indices) != cur_strip_vert_count or len(skin_weights) != cur_strip_vert_count:
                ctx.log(
                    f"[WARN] strip verts={cur_strip_vert_count}, skin_idx={len(skin_indices)}, skin_wts={len(skin_weights)} — padding zeros to match"
                )
                while len(skin_indices) < cur_strip_vert_count:
                    skin_indices.append([0, 0, 0, 0])
                    skin_weights.append([0.0, 0.0, 0.0, 0.0])
                skin_indices = skin_indices[:cur_strip_vert_count]
                skin_weights = skin_weights[:cur_strip_vert_count]

            strip_meta = StripMeta(
                base_vertex_index=base_idx,
                vertex_count=cur_strip_vert_count,
                skin_indices=[list(lst) for lst in skin_indices],
                skin_weights=[list(lst) for lst in skin_weights],
            )
            part.strips_meta.append(strip_meta)
            skin_indices.clear()
            skin_weights.clear()

        g.parts.append(part)

    return g


#######################################################
# === PSP Geometry read ===
def read_psp_geometry(ctx: StoriesMDLContext, f, geom_ptr: int) -> StoriesPSPGeometryInfo:
    g = StoriesPSPGeometryInfo()
    ctx.log("Attempting PSP Stories MDL read...")

    f.seek(geom_ptr)
    header_offset = f.tell()

    g.materials = read_material_list(ctx, f)

    f.seek(12, 1)

    psp_header = f.read(0x48)
    if len(psp_header) != 0x48:
        raise Exception("Not enough bytes for PSP geometry header!")

    (
        size,
        flags,
        num_strips,
        unk1,
        bound0,
        bound1,
        bound2,
        bound3,
        scale_x,
        scale_y,
        scale_z,
        num_verts,
        pos_x,
        pos_y,
        pos_z,
        unk2,
        offset,
        unk3,
    ) = struct.unpack("<4I4f3fi3fiIf", psp_header)

    g.flags = flags
    g.num_strips = num_strips
    g.num_verts = num_verts
    g.scale = (scale_x, scale_y, scale_z)
    g.pos = (pos_x, pos_y, pos_z)

    uvfmt = flags & 0x3
    colfmt = (flags >> 2) & 0x7
    normfmt = (flags >> 5) & 0x3
    posfmt = (flags >> 7) & 0x3
    wghtfmt = (flags >> 9) & 0x3
    idxfmt = (flags >> 11) & 0x3
    nwght = ((flags >> 14) & 0x7) + 1

    g.uv_format = uvfmt
    g.col_format = colfmt
    g.norm_format = normfmt
    g.pos_format = posfmt
    g.weight_format = wghtfmt
    g.index_format = idxfmt
    g.num_weights_per_vertex = nwght

    known_flag_formats = {0x120, 0x121, 0x115, 0x114, 0xA1, 0x1C321}
    if flags not in known_flag_formats:
        ctx.log(f"⚠️ Unknown PSP geometry flags format: 0x{flags:X}")
        raise Exception(f"Unknown PSP geometry flags format: 0x{flags:X}")
    else:
        ctx.log(f"✔ Known PSP geometry flags format: 0x{flags:X}")

    ctx.log("----- Flags Format Case Breakdown -----")

    if uvfmt == 0:
        ctx.log("  uvfmt   = 0: No UV coordinates (case 0) [OK]")
    elif uvfmt == 1:
        ctx.log("  uvfmt   = 1: U8 UVs (case 1) [OK]")
    else:
        ctx.log(f"  uvfmt   = {uvfmt}: Unsupported UV format! [ERROR]")
        raise Exception(f"Unsupported tex coord format (uvfmt={uvfmt})")

    if colfmt == 0:
        ctx.log("  colfmt  = 0: No vertex color (case 0) [OK]")
    elif colfmt == 5:
        ctx.log("  colfmt  = 5: 16-bit RGBA5551 color (case 5) [OK]")
    else:
        ctx.log(f"  colfmt  = {colfmt}: Unsupported vertex color format! [ERROR]")
        raise Exception(f"Unsupported color format (colfmt={colfmt})")

    if normfmt == 0:
        ctx.log("  normfmt = 0: No normals (case 0) [OK]")
    elif normfmt == 1:
        ctx.log("  normfmt = 1: S8 normals (case 1) [OK]")
    else:
        ctx.log(f"  normfmt = {normfmt}: Unsupported normal format! [ERROR]")
        raise Exception(f"Unsupported normal format (normfmt={normfmt})")

    if posfmt == 1:
        ctx.log("  posfmt  = 1: S8 positions (case 1) [OK]")
    elif posfmt == 2:
        ctx.log("  posfmt  = 2: S16 positions (case 2) [OK]")
    else:
        ctx.log(f"  posfmt  = {posfmt}: Unsupported vertex position format! [ERROR]")
        raise Exception(f"Unsupported vertex format (posfmt={posfmt})")

    if wghtfmt == 0:
        ctx.log("  wghtfmt = 0: No weights/skin [OK]")
    elif wghtfmt == 1:
        ctx.log("  wghtfmt = 1: U8 weights/skin [OK]")
    else:
        ctx.log(f"  wghtfmt = {wghtfmt}: Unsupported weights format! [ERROR]")
        raise Exception(f"Unsupported weight format (wghtfmt={wghtfmt})")

    if idxfmt == 0:
        ctx.log("  idxfmt  = 0: Index format [OK]")
    else:
        ctx.log(f"  idxfmt  = {idxfmt}: Unsupported/invalid index format! [ERROR]")
        raise Exception(f"idxfmt must be 0 (got {idxfmt})")

    ctx.log(f"  nwght   = {nwght}: Number of weights per vertex (parsed as ((flags>>14) & 7) + 1)")
    ctx.log("--------------------------------------")

    ctx.log("----- PSP Geometry Struct -----")
    ctx.log(f"  size      (header+data): {size} (0x{size:08X})")
    ctx.log(f"  flags     (VTYPE)      : {flags} (0x{flags:08X})")
    ctx.log(f"  numStrips              : {num_strips}")
    ctx.log(f"  unk1                   : {unk1} (0x{unk1:08X})")
    ctx.log(f"  bound   [0]            : {bound0}")
    ctx.log(f"  bound   [1]            : {bound1}")
    ctx.log(f"  bound   [2]            : {bound2}")
    ctx.log(f"  bound   [3]            : {bound3}")
    ctx.log(f"  scale_x                : {scale_x}")
    ctx.log(f"  scale_y                : {scale_y}")
    ctx.log(f"  scale_z                : {scale_z}")
    ctx.log(f"  numVerts               : {num_verts}")
    ctx.log(f"  pos_x                  : {pos_x}")
    ctx.log(f"  pos_y                  : {pos_y}")
    ctx.log(f"  pos_z                  : {pos_z}")
    ctx.log(f"  unk2                   : {unk2} (0x{unk2:08X})")
    ctx.log(f"  offset (to vertices)   : {offset} (0x{offset:08X})")
    ctx.log(f"  unk3                   : {unk3}")
    ctx.log("--------------------------------")

    mesh_list: List[Dict[str, Any]] = []
    for i in range(num_strips):
        mesh_offset = f.tell()
        mesh_bytes = f.read(0x30)
        if len(mesh_bytes) != 0x30:
            ctx.log(
                f"✗ ERROR: Could not read 0x30 bytes for sPspGeometryMesh[{i}] at 0x{mesh_offset:X}"
            )
            break

        (
            m_offset,
            m_num_triangles,
            m_mat_id,
            m_unk1,
            m_uv_scale0,
            m_uv_scale1,
            m_unk2_0,
            m_unk2_1,
            m_unk2_2,
            m_unk2_3,
            m_unk3,
            *m_bonemap,
        ) = struct.unpack("<I H H f 2f 4f f 8B", mesh_bytes)

        ctx.log(f"\n---- [sPspGeometryMesh {i + 1}/{num_strips}] ----")
        ctx.log(f"  File Offset        : 0x{mesh_offset:X}")
        ctx.log(f"  offset (to tris)   : 0x{m_offset:08X}")
        ctx.log(f"  numTriangles       : {m_num_triangles}")
        ctx.log(f"  matID              : {m_mat_id}")
        ctx.log(f"  unk1               : {m_unk1}")
        ctx.log(f"  uvScale            : ({m_uv_scale0}, {m_uv_scale1})")
        ctx.log(
            f"  unk2[0..3]         : ({m_unk2_0}, {m_unk2_1}, {m_unk2_2}, {m_unk2_3})"
        )
        ctx.log(f"  unk3               : {m_unk3}")
        ctx.log(f"  bonemap            : {list(m_bonemap)}")

        mesh_dict = {
            "offset": m_offset,
            "numTriangles": m_num_triangles,
            "matID": m_mat_id,
            "unk1": m_unk1,
            "uvScale": (m_uv_scale0, m_uv_scale1),
            "unk2": (m_unk2_0, m_unk2_1, m_unk2_2, m_unk2_3),
            "unk3": m_unk3,
            "bonemap": list(m_bonemap),
            "raw_bytes": mesh_bytes,
            "file_offset": mesh_offset,
        }
        mesh_list.append(mesh_dict)

    ctx.log(
        f"✔ Finished reading {len(mesh_list)} sPspGeometryMesh structs (expected: {num_strips})\n"
    )

    vertex_buffer_file_offset = header_offset + offset - 168
    ctx.log(f"Vertex buffer begins at file offset: 0x{vertex_buffer_file_offset:X}")

    f.seek(vertex_buffer_file_offset)
    vertex_buffer = f.read(num_verts * 24)
    if len(vertex_buffer) < num_verts:
        raise Exception("Not enough data for vertex buffer!")

    for mesh_index, mesh in enumerate(mesh_list):
        ctx.log(f"--- Building mesh for sPspGeometryMesh {mesh_index + 1}/{len(mesh_list)} ---")
        m = StoriesPSPMesh(index=mesh_index)
        m.mat_id = mesh["matID"]
        m.uv_scale = mesh["uvScale"]
        m.bonemap = list(mesh["bonemap"])

        tri_strip_offset = vertex_buffer_file_offset + mesh["offset"]
        f.seek(tri_strip_offset)

        bytes_per_vert = 20
        verts_to_skip = 10
        skip_bytes = bytes_per_vert * verts_to_skip
        f.seek(skip_bytes, 1)
        ctx.log(
            f"⏩ Skipped first {verts_to_skip} verts ({skip_bytes} bytes) for mesh {mesh_index}"
        )

        num_strip_verts = mesh["numTriangles"] + 2
        ctx.log(
            f"🟩 [PSP] Reading Mesh/Strip {mesh_index}: Vertex data starts at file offset 0x{tri_strip_offset:X} ({tri_strip_offset})"
        )
        ctx.log(
            f"  Tri-strip data for mesh {mesh_index}: offset=0x{tri_strip_offset:X}, numTriangles={mesh['numTriangles']}, thus numVertices={num_strip_verts}"
        )

        for vi in range(num_strip_verts):
            vertex_data = f.read(20)
            if len(vertex_data) < 8:
                ctx.log(f"    ! Not enough data for vertex {vi} of strip {mesh_index}")
                break

            local_o = 0

            if wghtfmt:
                weights_raw = [vertex_data[local_o + j] for j in range(nwght)]
                local_o += nwght

                K = min(4, nwght)
                w4 = [weights_raw[j] / 128.0 for j in range(K)]
                if K < 4:
                    w4.extend([0.0] * (4 - K))

                palette = mesh.get("bonemap") or []
                idx4: List[int] = []
                for j in range(K):
                    idx4.append(palette[j] if j < len(palette) else 0)
                if K < 4:
                    idx4.extend([0] * (4 - K))

                s = sum(w4)
                if s > 0.0:
                    w4 = [w / s for w in w4]

                if nwght > 4 and any(x != 0 for x in weights_raw[4:]):
                    ctx.log(
                        f"PSP: vertex had {nwght} weights; extra bytes beyond 4 were non-zero and ignored: {weights_raw[4:]}"
                    )

                m.bone_weights.append(w4)
                m.bone_indices.append(idx4)

            u_val = 0.0
            v_val = 0.0
            if uvfmt == 1:
                u_val = vertex_data[local_o] / 128.0 * mesh["uvScale"][0]
                v_val = vertex_data[local_o + 1] / 128.0 * mesh["uvScale"][1]
                m.uvs.append((u_val, v_val))
                local_o += 2

            col_val = None
            if colfmt == 5:
                local_o = ((local_o + 1) // 2) * 2
                col = struct.unpack_from("<H", vertex_data, local_o)[0]
                r = (col & 0x1F) * 255 // 0x1F
                g_c = ((col >> 5) & 0x1F) * 255 // 0x1F
                b_c = ((col >> 10) & 0x1F) * 255 // 0x1F
                a_c = 0xFF if (col & 0x8000) else 0
                col_val = (r, g_c, b_c, a_c)
                m.colors.append(col_val)
                local_o += 2

            norm_val = None
            if normfmt == 1:
                nx = struct.unpack_from("<b", vertex_data, local_o)[0] / 128.0
                ny = struct.unpack_from("<b", vertex_data, local_o + 1)[0] / 128.0
                nz = struct.unpack_from("<b", vertex_data, local_o + 2)[0] / 128.0
                norm_val = (nx, ny, nz)
                m.normals.append(norm_val)
                local_o += 3

            px = 0.0
            py = 0.0
            pz = 0.0
            if posfmt == 1:
                px = struct.unpack_from("<b", vertex_data, local_o)[0] / 128.0 * scale_x + pos_x
                py = struct.unpack_from("<b", vertex_data, local_o + 1)[0] / 128.0 * scale_y + pos_y
                pz = struct.unpack_from("<b", vertex_data, local_o + 2)[0] / 128.0 * scale_z + pos_z
                local_o += 3
            elif posfmt == 2:
                local_o = ((local_o + 1) // 2) * 2
                px = (
                    struct.unpack_from("<h", vertex_data, local_o)[0] / 32768.0 * scale_x
                    + pos_x
                )
                py = (
                    struct.unpack_from("<h", vertex_data, local_o + 2)[0] / 32768.0 * scale_y
                    + pos_y
                )
                pz = (
                    struct.unpack_from("<h", vertex_data, local_o + 4)[0] / 32768.0 * scale_z
                    + pos_z
                )
                local_o += 6

            m.verts.append((px, py, pz))

            ctx.log(
                f"    Vertex {vi}: pos=({px}, {py}, {pz})  uv=({u_val}, {v_val})  color={col_val}  normal={norm_val}"
            )

        for i in range(2, num_strip_verts):
            if (i % 2) == 0:
                v0 = i - 2
                v1 = i - 1
                v2 = i
            else:
                v0 = i - 1
                v1 = i - 2
                v2 = i
            if v0 != v1 and v1 != v2 and v2 != v0:
                m.faces.append((v0, v1, v2))

        ctx.log(
            f"✔ Built PSP mesh {mesh_index}: verts={len(m.verts)}, faces={len(m.faces)}"
        )
        g.meshes.append(m)

    ctx.log("✔ All PSP geometry meshes have been parsed (no Blender objects created here).")
    return g


#######################################################
# === Top-level Stories MDL reader as a class ===
class read_stories:
    """Class-based Stories MDL reader, matching read_chinatown / read_lvz style."""

    def __init__(self, filepath: str, platform: str, mdl_type: str):
        self.filepath = filepath
        self.platform = platform
        self.mdl_type = mdl_type
        self.ctx: StoriesMDLContext | None = None

    def read(self) -> StoriesMDLContext:
        ctx = StoriesMDLContext(
            filepath=self.filepath,
            platform=self.platform,
            mdl_type=self.mdl_type,
        )

        filepath = self.filepath
        platform = self.platform
        mdl_type = self.mdl_type

        with open(filepath, "rb") as f:
            ctx.log(f"✔ Opened: {filepath}")
            if f.read(4) != b"ldm\x00":
                ctx.log("Invalid Stories MDL header.")
                raise ValueError("Invalid Stories MDL header")

            ctx.shrink = read_u32(f)
            ctx.file_len = read_u32(f)
            ctx.local_num_table = read_u32(f)
            ctx.global_num_table = read_u32(f)

            is_psp = platform == "PSP"
            if is_psp:
                ctx.log("Detected PSP MDL: Skipping 4 bytes after global_numTable.")
                f.seek(-4, 1)

            if ctx.global_num_table == (ctx.local_num_table + 4):
                ctx.actor_mdl = True
                ctx.log("✔ Ped/actor or prop MDL detected.")
            else:
                f.seek(-4, 1)
                ctx.num_entries = read_u32(f)
                ctx.log("✔ Non-actor MDL detected: possibly a prop.")
                if is_psp:
                    f.seek(4, 1)

            ctx.num_entries = read_u32(f)
            ctx.ptr2_before_tex = read_u32(f)
            ctx.allocated_memory = read_u32(f)

            next_ptr_offset = f.tell()
            possible_ptr = read_u32(f)
            ctx.log(f"Pointer after allocMem (offset 0x{next_ptr_offset:X}): 0x{possible_ptr:X}")

            def is_known_vtable(val: int) -> bool:
                KNOWN_VTABLES = {
                    0x00000002,  
                    0x0000AA02,  
                    0x0004AA01,  
                    0x0300AA00,  
                    0x01050001,  
                    0x01000001,  
                }
                return val in KNOWN_VTABLES or (val & 0xFFFF) in {v & 0xFFFF for v in KNOWN_VTABLES}

            peek_type = "unknown"
            string_val = ""
            file_current = f.tell()
            if 0 < possible_ptr < ctx.file_len:
                f.seek(possible_ptr)
                peek_bytes = f.read(8)
                s = peek_bytes.split(b"\x00")[0]
                if s and all(32 <= b <= 126 for b in s):
                    string_val = s.decode("ascii", errors="ignore")
                    peek_type = "string"
                else:
                    val = struct.unpack("<I", peek_bytes[:4])[0]
                    if is_known_vtable(val):
                        peek_type = "vtable"
                    else:
                        peek_type = "struct_or_flags"
                f.seek(file_current)
            else:
                if is_known_vtable(possible_ptr):
                    peek_type = "vtable"
                elif 32 <= (possible_ptr & 0xFF) <= 126:
                    peek_type = "string_candidate"
                else:
                    peek_type = "unknown"
            ctx.log(
                f"Analysis: pointer after allocMem is {peek_type}"
                + (f" ('{string_val}')" if string_val else "")
            )

            renderflags_offset = 0

            if peek_type == "vtable":
                ctx.log("This pointer is a vtable/top-level struct (Clump/Atomic etc).")
                ctx.top_level_ptr = possible_ptr
            elif peek_type in ("string", "string_candidate"):
                ctx.log(
                    f"This pointer is a string (probably a material/texture name): '{string_val}'"
                )
            elif peek_type == "struct_or_flags":
                ctx.log(
                    "This pointer appears to point to a struct or flags; treat as renderflags offset or substruct."
                )
                renderflags_offset = possible_ptr
                if mdl_type == "SIM":
                    f.seek(-4, 1)
                ctx.top_level_ptr = read_u32(f)
            else:
                ctx.log("Pointer after allocMem type could not be determined; treating as unknown/flags.")
                renderflags_offset = possible_ptr
                ctx.top_level_ptr = read_u32(f)

            ctx.renderflags_offset = renderflags_offset

            ctx.log(f"File Size: 0x{ctx.file_len:X}")
            ctx.log(f"Local Realloc Table: 0x{ctx.local_num_table:X}, Global Realloc Table: 0x{ctx.global_num_table:X}")
            ctx.log(f"Number of entries: 0x{ctx.num_entries:X}")
            ctx.log(f"Ptr2BeforeTexNameList: 0x{ctx.ptr2_before_tex:X}")
            ctx.log(f"Allocated memory: 0x{ctx.allocated_memory:X}")
            ctx.log(f"Top-level ptr or magic value: 0x{ctx.top_level_ptr:X}")

            f.seek(ctx.top_level_ptr)
            top_magic = read_u32(f)

            LCSCLUMPPS2 = 0x00000002
            VCSCLUMPPS2 = 0x0000AA02
            CLUMPPSP = 0x00000002
            LCSATOMIC1 = 0x01050001
            LCSATOMIC2 = 0x01000001
            VCSATOMIC1 = 0x0004AA01
            VCSATOMIC2 = 0x0004AA01
            VCSATOMICPSP1 = 0x00041601
            VCSATOMICPSP2 = 0x01F40400

            ctx.section_type = 0
            ctx.import_type = 0

            if top_magic in (LCSCLUMPPS2, VCSCLUMPPS2):
                ctx.section_type = 7
                if is_psp:
                    if top_magic == CLUMPPSP:
                        ctx.log(" Top magic matches PSP values, setting import type 3.")
                        ctx.import_type = 3
                else:
                    ctx.import_type = 1 if top_magic == LCSCLUMPPS2 else 2
            elif top_magic in (LCSATOMIC1, LCSATOMIC2, VCSATOMIC1, VCSATOMIC2):
                ctx.section_type = 2
                ctx.import_type = 1 if top_magic in (LCSATOMIC1, LCSATOMIC2) else 2
            elif top_magic in (VCSATOMICPSP1, VCSATOMICPSP2):
                ctx.section_type = 2
                ctx.import_type = 3 if top_magic in (VCSATOMICPSP1, VCSATOMICPSP2) else 2

            ctx.log(f"Section Type: {ctx.section_type}, Import Type: {ctx.import_type}")

            atomic_info = StoriesAtomicInfo()
            ctx.atomic = atomic_info

            if ctx.section_type == 7:
                ctx.log("✔ Detected Section Type: 7 (Clump)")
                clump_id = read_u32(f)
                first_frame = read_u32(f)
                first_atomic = read_u32(f)
                atomic_seek = first_atomic - 0x1C
                f.seek(atomic_seek)
                ctx.section_type = 2

            if ctx.section_type == 2:
                ctx.log("✔ Detected Section Type: 2 (Atomic)")

                atomic_start = f.tell()
                ctx.log(f"Atomic section begins at: 0x{atomic_start:X}")

                if mdl_type == "SIM":
                    f.seek(-4, 1)
                    ctx.log("MDL type is Prop: performed f.seek(-4, 1) before reading atomic_id.")
                else:
                    ctx.log("MDL type is Ped: did NOT perform f.seek(-4, 1) before reading atomic_id.")

                atomic_id = read_u32(f)
                frame_ptr = read_u32(f)
                prev_link = read_u32(f)
                prev_link2 = read_u32(f)
                padAAAA = read_u32(f)
                geom_ptr = read_u32(f)
                f.seek(4, 1)
                clump_ptr = read_u32(f)
                link_ptr = read_u32(f)
                render_cb = read_u32(f)
                model_info_id = struct.unpack("<h", f.read(2))[0]
                vis_id_flag = struct.unpack("<H", f.read(2))[0]
                hierarchy_ptr = read_u32(f)

                ctx.log(f"frame_ptr: 0x{frame_ptr:X}")
                ctx.log(f"previous link: {prev_link:X}")
                ctx.log(f"previous link 2: {prev_link2:X}")
                ctx.log(f"pad AAAA: {padAAAA:X}")
                ctx.log(f"geom_ptr:      0x{geom_ptr:X}")
                ctx.log(f"clump_ptr:     0x{clump_ptr:X}")
                ctx.log(f"link_ptr:      0x{link_ptr:X}")
                ctx.log(f"render_cb:     0x{render_cb:X}")
                ctx.log(f"model_info_id: {model_info_id}")
                ctx.log(f"vis_id_flag:   0x{vis_id_flag:X}")
                ctx.log(f"hierarchy_ptr: 0x{hierarchy_ptr:X}")

                atomic_info.section_type = ctx.section_type
                atomic_info.import_type = ctx.import_type
                atomic_info.frame_ptr = frame_ptr
                atomic_info.geom_ptr = geom_ptr
                atomic_info.model_info_id = model_info_id
                atomic_info.vis_id_flag = vis_id_flag
                atomic_info.hierarchy_ptr = hierarchy_ptr

                if mdl_type == "PED":
                    try:
                        arm = process_frame_tree(ctx, f, frame_ptr)
                        atomic_info.armature = arm
                    except Exception as e:
                        ctx.log(f"⚠️ Failed to build armature: {e}")
                        atomic_info.armature = None

                if platform == "PS2":
                    atomic_info.ps2_geometry = read_ps2_geometry(ctx, f, geom_ptr)
                else:
                    atomic_info.psp_geometry = read_psp_geometry(ctx, f, geom_ptr)

        txt_path = os.path.splitext(filepath)[0] + "_import_log.txt"
        try:
            with open(txt_path, "w", encoding="utf-8") as outf:
                outf.write("\n".join(ctx.debug_log))
            ctx.log(f"✔ Debug log written to: {txt_path}")
        except Exception as e:
            ctx.log(f"✗ Failed to write debug log: {e}")

        self.ctx = ctx
        return ctx


def read_stories_mdl(filepath: str, platform: str, mdl_type: str) -> StoriesMDLContext:
    reader = read_stories(filepath, platform, mdl_type)
    return reader.read()

# VTables / IDs
LCSCLUMPPS2 = 0x00000002
VCSCLUMPPS2 = 0x0000AA02

LCSATOMIC1 = 0x01050001
LCSATOMIC2 = 0x01000001
VCSATOMIC1 = 0x0004AA01
VCSATOMIC2 = 0x0300AA00

FIRST_SECTION_OFFSET = 0x24

# VIF / GIF constants
TRI_STRIP_FLAG = 0x60000041

VIF_UNPACK = 0x6C018000

VIF_STMASK = 0x20000000
VIF_STROW = 0x30000000

VIF_POS_HEADER = 0x79000000
VIF_TEX_HEADER = 0x76004000

VIF_MSCAL = 0x14000006


@dataclass
class Ps2Vertex:
    x: float
    y: float
    z: float
    u: float
    v: float
    nx: float = 0.0
    ny: float = 0.0
    nz: float = 1.0
    r: int = 255
    g: int = 255
    b: int = 255
    a: int = 255


@dataclass
class ScalePos:
    scale: Tuple[float, float, float]
    pos: Tuple[float, float, float]


def write_u8(buf: bytearray, value: int) -> None:
    buf += struct.pack("<B", value & 0xFF)


def write_u16(buf: bytearray, value: int) -> None:
    buf += struct.pack("<H", value & 0xFFFF)


def write_i16(buf: bytearray, value: int) -> None:
    buf += struct.pack("<h", int(value))


def write_u32(buf_or_value, value: int | None = None):

    if value is None:
        return struct.pack("<I", int(buf_or_value) & 0xFFFFFFFF)

    buf = buf_or_value
    buf += struct.pack("<I", int(value) & 0xFFFFFFFF)
    return None

def reserve_u32(buf: bytearray, initial_value: int = 0) -> int:
    off = len(buf)
    write_u32(buf, initial_value)
    return off


def write_i32(buf: bytearray, value: int) -> None:
    buf += struct.pack("<i", int(value))


def write_f32(buf: bytearray, value: float) -> None:
    buf += struct.pack("<f", float(value))


def align_buffer(buf: bytearray, alignment: int) -> None:
    remainder = len(buf) % alignment
    if remainder != 0:
        buf += b"\x00" * (alignment - remainder)

def pad_bytes_to(data: bytearray, alignment: int) -> None:
    r = len(data) % alignment
    if r:
        data.extend(b"\x00" * (alignment - r))

def pad_to_sector(buf: bytearray, sector: int = 0x800) -> None:
    pad = (-len(buf)) % sector
    if pad:
        buf += b"\x00" * pad


def read_root_base_scale_pos(root_obj) -> Optional[ScalePos]:
    def vec3_from_any(v) -> Optional[Tuple[float, float, float]]:
        if v is None:
            return None
        if isinstance(v, (list, tuple)) and len(v) >= 3:
            return (float(v[0]), float(v[1]), float(v[2]))
        try:
            return (float(v[0]), float(v[1]), float(v[2]))
        except Exception:
            return None

    if hasattr(root_obj, "bleeds_leeds_scale_base") and hasattr(root_obj, "bleeds_leeds_pos_base"):
        s = vec3_from_any(getattr(root_obj, "bleeds_leeds_scale_base"))
        p = vec3_from_any(getattr(root_obj, "bleeds_leeds_pos_base"))
        if s is not None and p is not None:
            return ScalePos(scale=s, pos=p)

    for sk, pk in (
        ("bleeds_leeds_scale_base", "bleeds_leeds_pos_base"),
        ("mdl_scale", "mdl_pos"),
        ("leeds_scale", "leeds_pos"),
    ):
        if isinstance(root_obj, dict):
            s = vec3_from_any(root_obj.get(sk))
            p = vec3_from_any(root_obj.get(pk))
        else:
            s = vec3_from_any(root_obj.get(sk) if hasattr(root_obj, "get") else (root_obj[sk] if sk in root_obj else None))
            p = vec3_from_any(root_obj.get(pk) if hasattr(root_obj, "get") else (root_obj[pk] if pk in root_obj else None))
        if s is not None and p is not None:
            return ScalePos(scale=s, pos=p)

    return None


def compute_effective_scale_pos(root_obj) -> Optional[ScalePos]:
    base = read_root_base_scale_pos(root_obj)
    if base is None:
        return None

    sx, sy, sz = base.scale
    px, py, pz = base.pos

    rs = getattr(root_obj, "scale", None)
    rl = getattr(root_obj, "location", None)

    if rs is None or rl is None:
        return base

    eff_scale = (float(sx) * float(rs[0]), float(sy) * float(rs[1]), float(sz) * float(rs[2]))
    eff_pos = (
        (float(px) * float(rs[0])) + float(rl[0]),
        (float(py) * float(rs[1])) + float(rl[1]),
        (float(pz) * float(rs[2])) + float(rl[2]),
    )

    eps = 1e-10
    if abs(eff_scale[0]) < eps or abs(eff_scale[1]) < eps or abs(eff_scale[2]) < eps:
        return None

    return ScalePos(scale=eff_scale, pos=eff_pos)



# -----------------------------------------------------------------------------
# PS2 triangle strip limits
#
# Leeds PS2 SimpleModel geometry uses a single VU microprogram that expects a
# bounded per-strip vertex buffer. In practice (and in retail assets), a single
# stitched triangle strip never exceeds 70 vertices. If you exceed this, the
# game will either drop triangles, corrupt attributes, or crash depending on the
# build and platform.
# -----------------------------------------------------------------------------
PS2_MAX_TRISTRIP_VERTS: int = 70


def split_ps2_tristrip_vertices(
    strip: List["Ps2Vertex"],
    *,
    max_verts: int = PS2_MAX_TRISTRIP_VERTS,
    overlap: int = 2,
) -> List[List["Ps2Vertex"]]:
    if max_verts < 3:
        max_verts = 3
    if overlap < 0:
        overlap = 0
    if overlap >= max_verts:
        overlap = max_verts - 1

    n = len(strip)
    if n <= max_verts:
        return [strip] if strip else []

    chunks: List[List["Ps2Vertex"]] = []

    start = 0
    while start < n:
        if start == 0:
            end = min(n, max_verts)
            chunks.append(strip[start:end])
            start = end
            continue

        chunk_start = max(0, start - overlap)
        end = min(n, chunk_start + max_verts)
        chunks.append(strip[chunk_start:end])

        start = end

    chunks = [c for c in chunks if len(c) >= 3]
    return chunks

def build_ps2_dma_for_strip(
    verts: List[Ps2Vertex],
    *,
    use_normals: bool = True,
    max_batch_verts: int = 0,
    scale_pos_override: Optional[ScalePos] = None,
    rounding_mode: str = "ROUND",
) -> Tuple[bytearray, ScalePos]:

    if not verts:
        return bytearray(), ScalePos(scale=(1.0, 1.0, 1.0), pos=(0.0, 0.0, 0.0))

    max_verts_per_chunk = 70
    if max_batch_verts > 0:
        max_verts_per_chunk = max(3, min(int(max_batch_verts), 70))

    if len(verts) > 255:
        verts = verts[:255]

    def apply_round(v: float) -> float:
        mode = rounding_mode.upper()
        if mode == "FLOOR":
            return math.floor(v)
        if mode == "CEIL":
            return math.ceil(v)
        return round(v)

    if scale_pos_override is not None:
        scale_pos = scale_pos_override
    else:
        min_x = min(v.pos[0] for v in verts)
        min_y = min(v.pos[1] for v in verts)
        min_z = min(v.pos[2] for v in verts)
        max_x = max(v.pos[0] for v in verts)
        max_y = max(v.pos[1] for v in verts)
        max_z = max(v.pos[2] for v in verts)

        sx = (max_x - min_x) / 32767.0 if (max_x - min_x) != 0.0 else 1.0
        sy = (max_y - min_y) / 32767.0 if (max_y - min_y) != 0.0 else 1.0
        sz = (max_z - min_z) / 32767.0 if (max_z - min_z) != 0.0 else 1.0

        scale_pos = ScalePos(
            scale=(
                apply_round(sx * 1e12) / 1e12,
                apply_round(sy * 1e12) / 1e12,
                apply_round(sz * 1e12) / 1e12,
            ),
            pos=(min_x, min_y, min_z),
        )

    def encode_pos_i16(x: float, axis: int) -> int:
        sc = scale_pos.scale[axis]
        base = scale_pos.pos[axis]
        if sc == 0.0:
            return 0
        v = (x - base) / sc
        mode = rounding_mode.upper()
        if mode == "FLOOR":
            q = math.floor(v)
        elif mode == "CEIL":
            q = math.ceil(v)
        else:
            q = int(round(v))
        return max(-32768, min(32767, q))

    def encode_uv_u16(u: float) -> int:
        q = int(round(u * 65535.0))
        return max(0, min(65535, q))

    def encode_normal_i8(n: float) -> int:
        q = int(round(n * 127.0))
        return max(-128, min(127, q))

    chunks: List[List[Ps2Vertex]] = []
    cursor = 0

    while cursor < len(verts):
        if cursor == 0:
            take = min(max_verts_per_chunk, len(verts))
            chunks.append(verts[0:take])
            cursor = take
            continue

        bridge_a = verts[cursor - 2]
        bridge_b = verts[cursor - 1]

        chunk: List[Ps2Vertex] = [bridge_a, bridge_b]

        if ((cursor - 2) & 1) == 1:
            chunk.insert(0, bridge_a)

        cap = max_verts_per_chunk - len(chunk)
        if cap <= 0:
            cap = 1

        take = min(cap, len(verts) - cursor)
        chunk.extend(verts[cursor:cursor + take])
        chunks.append(chunk)
        cursor += take

    dma = bytearray()

    pos_addr = 0x0100
    uv_addr = 0x0300
    nrm_addr = 0x0400

    for chunk in chunks:
        count = len(chunk)

        payload = bytearray()

        payload.extend(write_u32(0))
        payload.extend(write_u32(0))
        payload.extend(write_u32(0))
        payload.extend(write_u32(0))

        payload.extend(write_u32(0x79000000))
        payload.extend(write_u32(0x00000000))

        payload.extend(write_u32(0x83000000))
        payload.extend(write_u32(0))
        payload.extend(write_u32(0))
        payload.extend(write_u32(0))
        payload.extend(write_u32(0))

        pos_header = (0x79 << 24) | ((count & 0xFF) << 16) | (0x8000 | pos_addr)
        payload.extend(write_u32(pos_header))

        for v in chunk:
            payload.extend(write_i16(encode_pos_i16(v.pos[0], 0)))
            payload.extend(write_i16(encode_pos_i16(v.pos[1], 1)))
            payload.extend(write_i16(encode_pos_i16(v.pos[2], 2)))
            payload.extend(write_i16(0))

        uv_header = (0x83 << 24) | ((count & 0xFF) << 16) | (0x8000 | uv_addr)
        payload.extend(write_u32(uv_header))

        for v in chunk:
            payload.extend(write_u16(encode_uv_u16(v.uv[0])))
            payload.extend(write_u16(encode_uv_u16(v.uv[1])))

        if use_normals:
            nrm_header = (0x82 << 24) | ((count & 0xFF) << 16) | (0x8000 | nrm_addr)
            payload.extend(write_u32(nrm_header))

            for v in chunk:
                nx = encode_normal_i8(v.normal[0])
                ny = encode_normal_i8(v.normal[1])
                nz = encode_normal_i8(v.normal[2])
                payload.extend(struct.pack("<bbbB", nx, ny, nz, 0))

        payload.extend(write_u32(0x14000000))

        while (len(payload) % 16) != 0:
            payload.append(0)

        qwc = len(payload) // 16

        dma.extend(struct.pack("<HHI", qwc, 0, 0x01000000))
        dma.extend(write_u32(0))
        dma.extend(write_u32(0))
        dma.extend(payload)

    return dma, scale_pos

@dataclass
class HeaderPatchInfo:
    file_len_off: int
    local_num_off: int
    global_num_off: int
    num_entries_off: int
    ptr2_before_tex_off: int
    alloc_mem_off: int
    ptr_after_alloc_off: int

def get_cached_atomic_hash_key(root_obj) -> int:
    if root_obj is None:
        return 0
    for key in ("bleeds_atomic_hash_key", "leeds_atomic_hash_key", "mdl_atomic_hash_key"):
        if key in root_obj:
            try:
                return int(root_obj[key]) & 0xFFFFFFFF
            except Exception:
                return 0
    return 0


def set_cached_atomic_hash_key(root_obj, value: int) -> None:
    if root_obj is None:
        return
    root_obj["bleeds_atomic_hash_key"] = int(value) & 0xFFFFFFFF


def begin_mdl_header(buf: bytearray) -> HeaderPatchInfo:
    buf += b"ldm\x00"
    write_u32(buf, 0)  

    file_len_off          = reserve_u32(buf, 0)
    local_num_off         = reserve_u32(buf, 0)
    global_num_off        = reserve_u32(buf, 0)
    num_entries_off       = reserve_u32(buf, 0)
    ptr2_before_tex_off   = reserve_u32(buf, 0)
    alloc_mem_off         = reserve_u32(buf, 0)
    ptr_after_alloc_off   = reserve_u32(buf, 0)

    return HeaderPatchInfo(
        file_len_off=file_len_off,
        local_num_off=local_num_off,
        global_num_off=global_num_off,
        num_entries_off=num_entries_off,
        ptr2_before_tex_off=ptr2_before_tex_off,
        alloc_mem_off=alloc_mem_off,
        ptr_after_alloc_off=ptr_after_alloc_off,
    )


def write_pointer_tables(buf: bytearray, pointer_fields: List[int]) -> Tuple[int, int]:
    align_buffer(buf, 4)
    local_num_offset = len(buf)
    pointer_count = len(pointer_fields)
    write_u32(buf, pointer_count)

    global_num_offset = len(buf)
    for off in pointer_fields:
        write_u32(buf, off)

    return local_num_offset, global_num_offset


def finalize_mdl_header(
    buf: bytearray,
    header: HeaderPatchInfo,
    file_size: int,
    local_num_offset: int,
    global_num_offset: int,
    pointer_count: int,
) -> None:
    struct.pack_into("<I", buf, header.file_len_off, file_size)
    struct.pack_into("<I", buf, header.local_num_off, local_num_offset)
    struct.pack_into("<I", buf, header.global_num_off, global_num_offset)
    struct.pack_into("<I", buf, header.num_entries_off, pointer_count)
    struct.pack_into("<I", buf, header.ptr2_before_tex_off, local_num_offset)

    alloc_mem = 0x00010000
    struct.pack_into("<I", buf, header.alloc_mem_off, alloc_mem)

    struct.pack_into("<I", buf, header.ptr_after_alloc_off, FIRST_SECTION_OFFSET)


PendingTexture = Tuple[int, str]


def write_material(
    buf: bytearray,
    tex_name: str,
    pointer_fields: List[int],
    pending_textures: List[PendingTexture],
) -> int:
    material_offset = len(buf)

    tex_ptr_field = len(buf)
    write_u32(buf, 0)
    pointer_fields.append(tex_ptr_field)

    write_u32(buf, 0xFFFFFFFF)  
    write_u32(buf, 0)           
    write_u32(buf, 0)           

    pending_textures.append((tex_ptr_field, tex_name))
    return material_offset


def write_texture_strings_after_tables(
    buf: bytearray,
    pending_textures: List[PendingTexture],
) -> None:
    for tex_ptr_field, tex_name in pending_textures:
        align_buffer(buf, 4)
        string_offset = len(buf)

        name_bytes = tex_name.encode("ascii", errors="ignore") + b"\x00"
        buf.extend(name_bytes)

        struct.pack_into("<I", buf, tex_ptr_field, string_offset)


def resolve_texture_name_identity(out: bytearray, atomic2_offset: int) -> int:
    frames_offset = len(out)

    for _ in range(2):
        out.extend(struct.pack(
            "<15fI",
            1.0, 0.0, 0.0, 0.0,  
            0.0, 1.0, 0.0, 0.0,  
            0.0, 0.0, 1.0, 0.0,  
            0.0, 0.0, 0.0,       
            1                  
        ))

    out.extend(struct.pack("<2I", 0, 0))
    out.extend(struct.pack("<I", int(atomic2_offset) & 0xFFFFFFFF))
    out.extend(struct.pack("<I", 0xAAAAAAAA))
    out.extend(struct.pack("<I", 0xFFFFFFFF))
    out.extend(struct.pack("<3I", 0, 0, 0))

    return frames_offset


def write_geometry_and_material(
    buf: bytearray,
    pointer_fields: List[int],
    part_materials: List[int],
    scale_pos: ScalePos,
    dma_packets: List[bytearray],
    material_offsets: List[int],
) -> int:

    if len(part_materials) != len(dma_packets):
        raise ValueError("part_materials and dma_packets length mismatch")

    align_buffer(buf, 16)
    geom_offset = len(buf)

    buf.extend(struct.pack("<III", 8, 0, 1))

    material_list_ptr_field = len(buf)
    buf.extend(struct.pack("<I", 0))
    pointer_fields.append(material_list_ptr_field)

    material_count = len(material_offsets)
    buf.extend(struct.pack("<I", material_count))

    buf.extend(struct.pack("<III", 0, 0, 0))

    align_buffer(buf, 16)
    material_list_offset = len(buf)
    struct.pack_into("<I", buf, material_list_ptr_field, material_list_offset)

    for mat_off in material_offsets:
        field_off = len(buf)
        buf.extend(struct.pack("<I", mat_off))
        pointer_fields.append(field_off)

    for _ in range(8):
        buf.extend(struct.pack("<I", 0))

    sx, sy, sz = scale_pos.scale
    px, py, pz = scale_pos.pos
    buf.extend(struct.pack("<ffffff", sx, sy, sz, px, py, pz))

    align_buffer(buf, 16)
    part_offset_field_offsets: List[int] = []

    for mat_index in part_materials:
        buf.extend(struct.pack("<I", 0))                
        buf.extend(struct.pack("<6I", 0, 0, 0, 0, 0, 0))
        part_offset_field_offsets.append(len(buf))
        buf.extend(struct.pack("<I", 0))                
        buf.extend(struct.pack("<H", 0))                
        buf.extend(struct.pack("<H", mat_index & 0xFFFF))
        buf.extend(struct.pack("<3I", 0, 0, 0))

    align_buffer(buf, 16)
    dma_start = len(buf)

    for i, packet in enumerate(dma_packets):
        rel = len(buf) - dma_start
        struct.pack_into("<I", buf, part_offset_field_offsets[i], rel)
        buf.extend(packet)

    align_buffer(buf, 16)
    return geom_offset


def write_simplemodel_ps2_prop_mdl(
    filepath: str,
    scale_pos,
    dma_packets: List[bytes],
    material_names: List[str],
    atomic_hash_key: int = 0,
    material_vcols: Optional[List[int]] = None,
    bounds: Optional[Tuple[float, float, float, float]] = None,
    unknown_geom_ints: Optional[List[int]] = None,
    geom_block_override: Optional[bytes] = None,
) -> None:

    if not material_names:
        material_names = ["default"]

    if material_vcols is None or len(material_vcols) < len(material_names):
        default_v = 0xFF959595
        material_vcols = (material_vcols or []) + [default_v] * (len(material_names) - (len(material_vcols) if material_vcols else 0))

    HEADER_SIZE = 0x24
    ATOMIC2_OFF = 0x30
    MATRICES_OFF = 0x40
    ATOMIC1_OFF = 0xE0
    TEXLIST_OFF = 0x120
    GEOM_HDR_OFF = 0x150
    PART_TABLE_OFF = 0x1B0
    DMA_START_OFF = 0x210

    out = bytearray(b"\x00" * DMA_START_OFF)

    out[0:4] = b"ldm\x00"
    struct.pack_into("<I", out, 0x04, 0)              
    struct.pack_into("<I", out, 0x08, 0)              
    struct.pack_into("<I", out, 0x0C, 0)              
    struct.pack_into("<I", out, 0x10, 0)              
    struct.pack_into("<I", out, 0x14, 16)             
    struct.pack_into("<I", out, 0x18, 0)              
    struct.pack_into("<I", out, 0x1C, 0x00010000)      
    struct.pack_into("<I", out, 0x20, ATOMIC1_OFF)     

    struct.pack_into("<I", out, ATOMIC2_OFF + 0x00, 0x0300AA00)  
    struct.pack_into("<I", out, ATOMIC2_OFF + 0x04, 0)
    atomic1_prev_entry = ATOMIC1_OFF + 0x08
    struct.pack_into("<I", out, ATOMIC2_OFF + 0x08, atomic1_prev_entry)
    struct.pack_into("<I", out, ATOMIC2_OFF + 0x0C, atomic1_prev_entry)

    tmp = bytearray()
    resolve_texture_name_identity(tmp, ATOMIC2_OFF)
    out[MATRICES_OFF:MATRICES_OFF + len(tmp)] = tmp


    struct.pack_into("<I", out, ATOMIC1_OFF + 0x00, 0x0004AA01)         
    struct.pack_into("<I", out, ATOMIC1_OFF + 0x04, ATOMIC2_OFF)        
    struct.pack_into("<I", out, ATOMIC1_OFF + 0x08, ATOMIC2_OFF + 0x08) 
    struct.pack_into("<I", out, ATOMIC1_OFF + 0x0C, ATOMIC2_OFF + 0x08) 
    struct.pack_into("<I", out, ATOMIC1_OFF + 0x10, 0)

    struct.pack_into("<I", out, ATOMIC1_OFF + 0x14, GEOM_HDR_OFF)
    struct.pack_into("<I", out, ATOMIC1_OFF + 0x18, 0)

    hk = int(atomic_hash_key) & 0xFFFFFFFF
    struct.pack_into("<I", out, ATOMIC1_OFF + 0x1C, hk)
    struct.pack_into("<I", out, ATOMIC1_OFF + 0x20, hk)

    struct.pack_into("<I", out, ATOMIC1_OFF + 0x24, 0)
    struct.pack_into("<I", out, ATOMIC1_OFF + 0x28, GEOM_HDR_OFF)

    struct.pack_into("<I", out, ATOMIC1_OFF + 0x2C, 0)
    struct.pack_into("<I", out, ATOMIC1_OFF + 0x30, 0)

    struct.pack_into("<I", out, ATOMIC1_OFF + 0x34, 0)
    struct.pack_into("<I", out, ATOMIC1_OFF + 0x38, int(material_vcols[0]) & 0xFFFFFFFF)

    num_parts = len(dma_packets)
    struct.pack_into("<I", out, TEXLIST_OFF - 0x04, num_parts)

    num_tex = len(material_names)
    struct.pack_into("<I", out, TEXLIST_OFF + 0x00, TEXLIST_OFF + 0x04)
    struct.pack_into("<I", out, TEXLIST_OFF + 0x04, 0)
    struct.pack_into("<I", out, TEXLIST_OFF + 0x08, 0)
    struct.pack_into("<f", out, TEXLIST_OFF + 0x0C, 1.0)
    struct.pack_into("<I", out, TEXLIST_OFF + 0x10, num_tex)
    struct.pack_into("<I", out, TEXLIST_OFF + 0x14, ATOMIC1_OFF + 0x34)
    struct.pack_into("<I", out, TEXLIST_OFF + 0x18, TEXLIST_OFF + 0x1C)
    struct.pack_into("<I", out, TEXLIST_OFF + 0x1C, 0)
    second_vcol = material_vcols[1] if num_tex > 1 else material_vcols[0]
    struct.pack_into("<I", out, TEXLIST_OFF + 0x20, int(second_vcol) & 0xFFFFFFFF)
    struct.pack_into("<I", out, TEXLIST_OFF + 0x24, num_tex)
    struct.pack_into("<I", out, TEXLIST_OFF + 0x28, 0)
    struct.pack_into("<I", out, TEXLIST_OFF + 0x2C, 0)

    if geom_block_override is None:
        struct.pack_into("<I", out, GEOM_HDR_OFF + 0x00, 8)
        struct.pack_into("<I", out, GEOM_HDR_OFF + 0x04, 0)
        struct.pack_into("<I", out, GEOM_HDR_OFF + 0x08, 1)
        struct.pack_into("<I", out, GEOM_HDR_OFF + 0x0C, TEXLIST_OFF + 0x14)
        struct.pack_into("<I", out, GEOM_HDR_OFF + 0x10, num_tex)
        struct.pack_into("<I", out, GEOM_HDR_OFF + 0x14, 0x10)
        struct.pack_into("<I", out, GEOM_HDR_OFF + 0x18, 0)  
        struct.pack_into("<I", out, GEOM_HDR_OFF + 0x1C, 0)  
        if bounds is not None:
            bx, by, bz, br = bounds
            struct.pack_into("<f", out, GEOM_HDR_OFF + 0x20, float(bx))
            struct.pack_into("<f", out, GEOM_HDR_OFF + 0x24, float(by))
            struct.pack_into("<f", out, GEOM_HDR_OFF + 0x28, float(bz))
            struct.pack_into("<f", out, GEOM_HDR_OFF + 0x2C, float(br))
        else:
            struct.pack_into("<4f", out, GEOM_HDR_OFF + 0x20, 0.0, 0.0, 0.0, 0.0)
        ints = [0, 0, 0, 0, 0, 0]
        if unknown_geom_ints:
            for i, v in enumerate(unknown_geom_ints[:6]):
                ints[i] = int(v) & 0xFFFFFFFF
        for idx, val in enumerate(ints):
            struct.pack_into("<I", out, GEOM_HDR_OFF + 0x30 + idx*4, val)
        sx, sy, sz = scale_pos.scale
        tx, ty, tz = scale_pos.pos
        struct.pack_into("<f", out, GEOM_HDR_OFF + 0x48, float(sx))
        struct.pack_into("<f", out, GEOM_HDR_OFF + 0x4C, float(sy))
        struct.pack_into("<f", out, GEOM_HDR_OFF + 0x50, float(sz))
        struct.pack_into("<f", out, GEOM_HDR_OFF + 0x54, float(tx))
        struct.pack_into("<f", out, GEOM_HDR_OFF + 0x58, float(ty))
        struct.pack_into("<f", out, GEOM_HDR_OFF + 0x5C, float(tz))
        required_size = PART_TABLE_OFF + len(dma_packets) * 4
        if len(out) < required_size:
            out.extend(b"\x00" * (required_size - len(out)))
        rel_off = 0
        for i, pkt in enumerate(dma_packets):
            struct.pack_into("<I", out, PART_TABLE_OFF + 4 * i, rel_off)
            rel_off += len(pkt)
    else:
        block = geom_block_override
        if not isinstance(block, (bytes, bytearray)):
            raise TypeError("geom_block_override must be bytes or bytearray")
        max_len = DMA_START_OFF - GEOM_HDR_OFF
        blen = min(len(block), max_len)
        out[GEOM_HDR_OFF:GEOM_HDR_OFF + blen] = block[:blen]

    for pkt in dma_packets:
        out.extend(pkt)

    def align(n: int, a: int) -> int:
        return (n + (a - 1)) & ~(a - 1)

    out_off = len(out)
    out_off = align(out_off, 0x10)
    if len(out) < out_off:
        out.extend(b"\x00" * (out_off - len(out)))

    local_num_table_off = out_off
    s0 = material_names[0].encode("ascii", errors="replace") + b"\x00"
    out.extend(s0)

    global_num_table_off = align(len(out), 4)
    if len(out) < global_num_table_off:
        out.extend(b"\x00" * (global_num_table_off - len(out)))

    pointer_offsets = [
        0x38,   
        0x3C,   
        0xC8,   
        0xE4,   
        0xE8,   
        0xEC,   
        0xF4,   
        0x114,  
        0x120,  
        0x128,  
        0x134,  
        0x138,  
        0x13C,  
        0x15C,  
        0x20,   
        0x104,  
    ]

    ptr2_before_tex_off = global_num_table_off + 4 + (len(pointer_offsets) - 1) * 4

    out.extend(struct.pack("<I", ptr2_before_tex_off))
    for o in pointer_offsets:
        out.extend(struct.pack("<I", o))

    out_off2 = align(len(out), 0x10)
    if len(out) < out_off2:
        out.extend(b"\x00" * (out_off2 - len(out)))

    string1_off = local_num_table_off
    if len(material_names) > 1:
        string1_off = len(out)
        s1 = material_names[1].encode("ascii", errors="replace") + b"\x00"
        out.extend(s1)

    struct.pack_into("<I", out, TEXLIST_OFF + 0x08, local_num_table_off)
    struct.pack_into("<I", out, TEXLIST_OFF + 0x1C, string1_off)
    struct.pack_into("<I", out, ATOMIC1_OFF + 0x34, string1_off)

    struct.pack_into("<I", out, 0x0C, local_num_table_off)
    struct.pack_into("<I", out, 0x10, global_num_table_off)
    struct.pack_into("<I", out, 0x18, ptr2_before_tex_off)

    logical_len = len(out)
    struct.pack_into("<I", out, 0x08, logical_len)

    pad = (0x800 - (len(out) % 0x800)) % 0x800
    if pad:
        out.extend(b"\x00" * pad)

    with open(filepath, "wb") as f:
        f.write(out)

def write_simplemodel_ps2_ped_mdl(
    filepath: str,
    *,
    scale_pos: ScalePos,
    dma_packets: List[bytearray],
    material_names: List[str],
) -> None:
    if len(dma_packets) == 0:
        raise RuntimeError("No DMA packets provided for export.")
    if len(material_names) != len(dma_packets):
        raise RuntimeError("material_names must match dma_packets length.")

    buf = bytearray()
    pointer_fields: List[int] = []
    pending_textures: List[PendingTexture] = []

    header_info = begin_mdl_header(buf)

    clump_offset = len(buf)
    write_u32(buf, VCSCLUMPPS2)

    clump_first_frame_field = len(buf); write_u32(buf, 0); pointer_fields.append(clump_first_frame_field)
    clump_first_atomic_field = len(buf); write_u32(buf, 0); pointer_fields.append(clump_first_atomic_field)
    clump_last_atomic_field = len(buf); write_u32(buf, 0); pointer_fields.append(clump_last_atomic_field)

    atomic_offset = len(buf)
    write_u32(buf, VCSATOMIC1)

    frame_ptr_field = len(buf); write_u32(buf, 0); pointer_fields.append(frame_ptr_field)

    prev_link1_off = len(buf); write_u32(buf, 0)
    prev_link2_off = len(buf); write_u32(buf, 0)

    write_u32(buf, 0xAAAAAAAA)

    geom_ptr_field = len(buf); write_u32(buf, 0); pointer_fields.append(geom_ptr_field)

    write_u32(buf, 0)  

    clump_ptr_field = len(buf); write_u32(buf, clump_offset); pointer_fields.append(clump_ptr_field)
    link_ptr_field = len(buf); write_u32(buf, clump_offset); pointer_fields.append(link_ptr_field)

    write_u32(buf, 0x12)  
    write_i32(buf, -1)    
    write_u32(buf, 0)     

    hierarchy_ptr_field = len(buf); write_u32(buf, 0); pointer_fields.append(hierarchy_ptr_field)

    material_ptr_field = len(buf); write_u32(buf, 0); pointer_fields.append(material_ptr_field)

    write_u32(buf, 0)  

    frames_offset = resolve_texture_name_identity(buf)
    struct.pack_into("<I", buf, frame_ptr_field, frames_offset)

    prev_val = frames_offset + 0x08
    struct.pack_into("<I", buf, prev_link1_off, prev_val)
    struct.pack_into("<I", buf, prev_link2_off, prev_val)

    first_atomic_addr = atomic_offset + 0x1C
    struct.pack_into("<I", buf, clump_first_frame_field, frames_offset)
    struct.pack_into("<I", buf, clump_first_atomic_field, first_atomic_addr)
    struct.pack_into("<I", buf, clump_last_atomic_field, first_atomic_addr)

    align_buffer(buf, 16)
    material_offsets: List[int] = []
    for name in material_names:
        material_offsets.append(
            write_material(buf, name, pointer_fields, pending_textures)
        )
    struct.pack_into("<I", buf, material_ptr_field, material_offsets[0] if material_offsets else 0)

    part_materials = list(range(len(dma_packets)))
    geom_offset = write_geometry_and_material(
        buf=buf,
        pointer_fields=pointer_fields,
        part_materials=part_materials,
        scale_pos=scale_pos,
        dma_packets=dma_packets,
        material_offsets=material_offsets,
    )
    struct.pack_into("<I", buf, geom_ptr_field, geom_offset)

    local_num_offset, global_num_offset = write_pointer_tables(buf, pointer_fields)
    write_texture_strings_after_tables(buf, pending_textures)

    file_size = len(buf)
    finalize_mdl_header(
        buf=buf,
        header=header_info,
        file_size=file_size,
        local_num_offset=local_num_offset,
        global_num_offset=global_num_offset,
        pointer_count=len(pointer_fields),
    )

    pad_to_sector(buf)

    with open(filepath, "wb") as f:
        f.write(buf)
