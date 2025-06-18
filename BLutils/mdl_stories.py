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

from mathutils import Matrix, Vector
from bpy_extras.io_utils import ImportHelper
from bpy.types import Operator
from bpy.props import StringProperty

# • https://gtamods.com/wiki/Relocatable_chunk
# • https://gtamods.com/wiki/Leeds_Engine
# • https://gtamods.com/wiki/MDL
# • https://github.com/aap/librwgta

# --- LCS Bone Arrays ---
commonBoneOrder = (
    "Root", "Pelvis", "Spine", "Spine1", "Neck", "Head",
    "Bip01 L Clavicle", "L UpperArm", "L Forearm", "L Hand", "L Finger", "Bip01 R Clavicle",
    "R UpperArm", "R Forearm", "R Hand", "R Finger", "L Thigh", "L Calf",
    "L Foot", "L Toe0", "R Thigh", "R Calf", "R Foot", "R Toe0"
)
kamBoneID = (
    0, 1, 2, 3, 4, 5, 31, 32, 33, 34, 35, 21, 22, 23, 24, 25, 41, 42, 43, 2000, 51, 52, 53, 2001
)
kamFrameName = (
    "Root", "Pelvis", "Spine", "Spine1", "Neck", "Head",
    "Bip01~L~Clavicle", "L~UpperArm", "L~Forearm", "L~Hand", "L~Finger", "Bip01~R~Clavicle",
    "R~UpperArm", "R~Forearm", "R~Hand", "R~Finger", "L~Thigh", "L~Calf",
    "L~Foot", "L~Toe0", "R~Thigh", "R~Calf", "R~Foot", "R~Toe0"
)
kamBoneType = (
    0, 0, 0, 2, 0, 3, 2, 0, 0, 0, 1, 0, 0, 0, 0, 1, 2, 0, 0, 1, 0, 0, 0, 1
)
kamBoneIndex = (
    "00", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23"
)

commonBoneParents = {
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
    "R Toe0": "R Foot"
}

# --- VCS Bone Arrays ---
commonBoneOrderVCS = (
    "root", "pelvis", "spine", "spine1", "neck", "head",
    "jaw", "bip01_l_clavicle", "l_upperarm", "l_forearm", "l_hand", "l_finger",
    "bip01_r_clavicle", "r_upperarm", "r_forearm", "r_hand", "r_finger", "l_thigh",
    "l_calf", "l_foot", "l_toe0", "r_thigh", "r_calf", "r_foot", "r_toe0"
)
commonBoneNamesVCS = (
    "Root", "Pelvis", "Spine", "Spine1", "Neck", "Head",
    "Jaw", "Bip01 L Clavicle", "L UpperArm", "L Forearm", "L Hand", "L Finger",
    "Bip01 R Clavicle", "R UpperArm", "R Forearm", "R Hand", "R Finger", "L Thigh",
    "L Calf", "L Foot", "L Toe0", "R Thigh", "R Calf", "R Foot", "R Toe0"
)
kamBoneIDVCS = (
    0, 1, 2, 3, 4, 5,
    8, 31, 32, 33, 34, 35,
    21, 22, 23, 24, 25, 41,
    42, 43, 2000, 51, 52, 53,
    2001
)
kamFrameNameVCS = (
    "Root", "Pelvis", "Spine", "Spine1", "Neck", "Head",
    "Jaw", "Bip01~L~Clavicle", "L~UpperArm", "L~Forearm", "L~Hand", "L~Finger",
    "Bip01~R~Clavicle", "R~UpperArm", "R~Forearm", "R~Hand", "R~Finger", "L~Thigh",
    "L~Calf", "L~Foot", "L~Toe0", "R~Thigh", "R~Calf", "R~Foot", "R~Toe0"
)
kamBoneTypeVCS = (
    0, 0, 0, 2, 0, 2,
    3, 2, 0, 0, 0, 1,
    0, 0, 0, 0, 1, 2,
    0, 0, 1, 0, 0, 0,
    1
)
kamBoneIndexVCS = (
    "00", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23"
) # some obvious love for Kam here lol

commonBoneParentsVCS = {
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
    "r_toe0": "r_foot"
}


section_type = 1
file_size = 0
ptr2_before_tex = 0
ptr2_tex_name_list = 0
ptr2_ptr2_tex_name_list = 0
ptr_found = False
top_level_ptr = 0
x_scale = 0.0
y_scale = 0.0
z_scale = 0.0
atomics = []
imported_objects = []
strips = []
verts = []
faces = []
tex_coords = []
vertex_colors = []
normals = []
part_materials = []
part_offsets = []
cur_part = 0
valid_faces_indices = []
textures = []
atomics_count = 0
cur_atomic = 0
next_atomic = 0
imp_object_count = 0
vert_stage = 0
cur_strip_vert_count = 0
cur_strip_tvert_count = 0
cur_strip_vert_color_count = 0
cur_strip_normals_count = 0
cur_strip_face_count = 0
strip_count = 0
unknown_section_ptr = 0
cur_mat_id = 1
cur_strip_skin_data = []
cur_strip_skin_data_count = 0
cur_skin_data = None
bone_list = []
skin_modifier = None
first_frame = 0
frame_data_list = []
cur_frame_data = None
import_type = 0


class ImportMDLOperator(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.mdl_fixed"
    bl_label = "Import LCS/VCS .MDL (Fixed)"
    filename_ext = ".mdl"
    filter_glob: StringProperty(default="*.mdl", options={'HIDDEN'})

    def execute(self, context):
        return self.read_mdl(self.filepath)

    def read_mdl(self, filepath):
        try:
            with open(filepath, "rb") as f:
                
                debug_log = []
                
                def log(msg):
                    debug_log.append(str(msg))
                    print(msg)
                
                found_6C018000 = False
                
                def read_point3(f):
                    """Reads 3 float32s from the file and returns a Vector."""
                    return Vector(struct.unpack('<3f', f.read(12))) # Reads a Vector3

                def read_matrix3x4_with_offset(f, scale_factor=1.0):
                    """Reads a 3x4 matrix and logs the starting offset before reading."""
                    matrix_offset = f.tell()  
                    
                    # 3x4 Matrix has 4 rows
                    row1 = read_point3(f)  # rot
                    f.read(4)

                    row2 = read_point3(f) # rot
                    f.read(4)

                    row3 = read_point3(f) # rot
                    f.read(4)

                    row4 = read_point3(f) # position
                    f.read(4)

                    scale_factor = read_u32() # bone scaling factor

                    mat = Matrix((                         # RslMatrix
                        (row1.x, row2.x, row3.x, row4.x),
                        (row1.y, row2.y, row3.y, row4.y),  # Transpose row-order to Blender column-order
                        (row1.z, row2.z, row3.z, row4.z),
                        (0.0,    0.0,    0.0,    1.0)      # RslV3 - frame/bone position + scale factor
                    ))

                    return mat, matrix_offset, (row1, row2, row3, row4)
                
                def read_i16():
                    return struct.unpack('<h', f.read(2))[0]


                def read_u16():
                    return struct.unpack("<H", f.read(2))[0] # Reads an unsigned 16-bit integer

                def read_u32():
                    return struct.unpack("<I", f.read(4))[0] # Reads an unsigned 32-bit integer

                def read_f32():
                    return struct.unpack("<f", f.read(4))[0] # Reads a float-32

                def read_string(ptr):
                    if ptr == 0:
                        return None
                    current = f.tell()
                    f.seek(ptr)
                    s = b""
                    while True:
                        c = f.read(1)
                        if c == b"\x00" or c == b"":
                            break
                        s += c
                    f.seek(current)
                    return s.decode("utf-8", errors="ignore")
                
                actor_mdl = False 

                # --- Read Stories MDL Header ---
                log(f"✔ Opened: {filepath}")
                if f.read(4) != b'ldm\x00':  # Identifier for file(i.e PedModel) - where we begin to read
                    self.report({'ERROR'}, "Invalid Stories MDL header") # Not a Stories MDL?
                    return {'CANCELLED'}     # eject process if invalid
                shrink = read_u32()          # 1 if GTAG resource image, else always 0(file not shrank)
                file_len = read_u32()        # physical fiile size
                local_numTable = read_u32()  # local entries numtable
                global_numTable = read_u32() # global entries numtable
                if global_numTable == (local_numTable + 4): # if global_numTable after local than = VCS
                    actor_MDL = True
                    log(f"✔ Ped model/actor MDL detected.") # than this is an actor/ped model
                else:
                    numEntries = read_u32()  # read number of entries after local numTable?(=/= VCS)
                    log(f"✔ Non-actor MDL detected: possibly building or prop.") # than modelinfo =/= ped
                    f.seek(-4, 1)
                    
                numEntries = read_u32()  # number of entries
                ptr2_before_tex = read_u32() # whats this do?
                allocMem = read_u32()  # amount of memory allocated to file - alloc ptr?
                if global_numTable == (local_numTable + 4): # if global_numTable after local than = VCS
                    actor_MDL = True
                    log(f"✔ Ped model/actor MDL detected.") # than this is an actor/ped model
                    _ = read_u32()  # skip D-WORD 0x1D10 - dunno what this does.
                else:
                    log(f"✔ Non-actor MDL: moving forward for top ptr.") # than modelinfo =/= ped
                    _ = read_u32()  # skip D-WORD 0x1D10 - dunno what this does.
                    f.seek(-4, 1)
                top_level_ptr = read_u32()  # pointer at 0x24
                
                log(f"File Size: 0x{file_len}")
                log(f"Local numTable: 0x{local_numTable:X}, Global numTable: 0x{global_numTable:X}")
                log(f"Number of entries: 0x{numEntries}")
                log(f"Ptr2BeforeTexNameList: 0x{ptr2_before_tex:X}")
                log(f"Allocated memory: 0x{allocMem}")
                log(f"Top-level ptr or magic value: 0x{top_level_ptr:X}")

                f.seek(top_level_ptr)
                top_magic = read_u32()

                section_type = 0
                import_type = 0

                # Markers for Leeds sections since Leeds Engine doesn't use RW plug-ins
                LCSCLUMP = 0x00000002
                VCSCLUMP = 0x0000AA02
                LCSATOMIC1 = 0x01050001
                LCSATOMIC2 = 0x01000001
                VCSATOMIC1 = 0x0004AA01
                VCSATOMIC2 = 0x0004AA01
                VCSFRAME   = 0x0003AA01

                if top_magic in (LCSCLUMP, VCSCLUMP):
                    section_type = 7
                    import_type = 1 if top_magic == LCSCLUMP else 2
                elif top_magic in (LCSATOMIC1, LCSATOMIC2, VCSATOMIC1, VCSATOMIC2):
                    section_type = 2
                    import_type = 1 if top_magic in (LCSATOMIC1, LCSATOMIC2) else 2

                log(f"Section Type: {section_type}, Import Type: {import_type}")
                
                # --- Update parsing state to Section Type: 7 (Clump) if successful ---
                if section_type == 7:
                    log("✔ Detected Section Type: 7 (Clump)")
                    #RslElementGroup
                    clump_id = read_u32()
                    first_frame = read_u32()
                    first_atomic = read_u32() 
                    atomic_seek = first_atomic - 0x1C
                    f.seek(atomic_seek)
                    section_type = 2 
                    
                # --- Update parsing state to Section Type: 2 (Atomic) if successful -
                if section_type == 2: 
                    log("✔ Detected Section Type: 2 (Atomic)")
                
                    atomics = []
                    frame_data_list = []
                    dummies = []
                    bone_list = []
                    frame_ptr_list = []
                    root_bone_link = not actor_mdl
                    cur_atomic_index = 1
                    
                    # RslElement
                    atomic_start = f.tell()
                    log(f"Atomic section begins at: 0x{atomic_start:X}")

                    atomic_id = read_u32()
                    
                    frame_ptr = read_u32()
                    
                    f.seek(12, 1)

                    geom_ptr = read_u32()
                    
                    f.seek(4, 1)    # seeking back and forth feels like violating the MDL file
                    
                    clump_ptr = read_u32()  # link back to Clump
                    link_ptr = read_u32()   # RSLLLink
                    
                    
                    render_cb = read_u32()  # render callback
                    model_info_id = struct.unpack("<h", f.read(2))[0]
                    vis_id_flag = struct.unpack("<H", f.read(2))[0]
                    hierarchy_ptr = read_u32()

                    log(f"frame_ptr: 0x{frame_ptr:X}")
                    
                    log(f"geom_ptr:      0x{geom_ptr:X}")
                    
                    log(f"clump_ptr:     0x{clump_ptr:X}")
                    log(f"link_ptr:      0x{link_ptr:X}")
                    
                    log(f"render_cb:     0x{render_cb:X}")
                    log(f"model_info_id: {model_info_id}")
                    log(f"vis_id_flag:   0x{vis_id_flag:X}")
                    log(f"hierarchy_ptr: 0x{hierarchy_ptr:X}")

                    # Save current pos to return later
                    return_pos = f.tell()

                    cur_frame_ptr = frame_ptr
                    first_frame = cur_frame_ptr
                    parent_dummy = None
                    
                    
                    # --- Frame/Bone loop ---
                    while cur_frame_ptr != 0: # RSLNode
                        f.seek(cur_frame_ptr + 12)
                        temp = read_u32()  # This is a test field

                        bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
                        cur_dummy = bpy.context.active_object
                        cur_dummy.empty_display_size = 0.05
                        cur_dummy.name = "Bone"

                        if actor_mdl:
                            cur_dummy.show_in_front = True
                            cur_dummy.color = (1, 1, 0, 1)  # Yellow wireframe

                        bone_list.append(cur_dummy)

                        mat, matrix_offset, (row1, row2, row3, row4) = read_matrix3x4_with_offset(f, scale_factor=1.0)

                        
                        head = mat.to_translation()
                        tail = head + mat.to_3x3() @ Vector((0, 0.05, 0))  # Tail offset along local Y

                        cur_dummy.matrix_world = mat


                        # --- Seek to boneNamePtr ---
                        f.seek(cur_frame_ptr + 0xA4)
                        if import_type == 2:
                            f.seek(4, 1)  # skip 4 bytes
                        
                        #RslSkin(?)
                        bone_name_ptr = read_u32()
                        if bone_name_ptr != 0:
                            cur_pos = f.tell()
                            f.seek(bone_name_ptr)
                            name_bytes = bytearray()
                            while True:
                                b = f.read(1)
                                if b == b'\x00' or not b:
                                    break
                                name_bytes.append(b[0])
                            bone_name = name_bytes.decode('utf-8', errors='ignore')
                            cur_dummy.name = bone_name
                            f.seek(cur_pos)
                            
                        log(f"✔ Matrix offset: 0x{matrix_offset:X} for frame '{cur_dummy.name}'")
                        
    
                        # --- Create dummies for bone construction ---
                        dummies.append(cur_dummy)
                        frame_data_list.append({
                            'object': cur_dummy,
                            'name': cur_dummy.name,
                            'pointer': cur_frame_ptr
                        })

                        frame_ptr_list.append(cur_frame_ptr)
                        f.seek(cur_frame_ptr + 0x90)
                        next_frame_ptr = read_u32()
                        for _ in range(4):
                            read_u32()
                        if import_type == 2:
                            f.seek(4, 1)
                        bone_name_ptr = read_u32()

                        # --- Resolve end of chain ---
                        if next_frame_ptr == 0:
                            while frame_ptr_list:
                                last = frame_ptr_list.pop()
                                f.seek(last + 0x94)
                                next_frame_ptr = read_u32()
                                if next_frame_ptr != 0:
                                    break

                        cur_frame_ptr = next_frame_ptr

                    f.seek(return_pos)
                    log(f"✔ Loaded {len(dummies)} bones into Blender as empties.")
                    
                    # --- Map bone names to dummy objects ---
                    bone_name_to_dummy = {obj.name.lower(): obj for obj in bone_list}

                    # --- Apply parenting based on hierarchy ---
                    for child_name in commonBoneOrderVCS:
                        parent_name = commonBoneParentsVCS.get(child_name)
                        if parent_name:
                            child = bone_name_to_dummy.get(child_name)
                            parent = bone_name_to_dummy.get(parent_name)
                            if child and parent:
                                child.parent = parent
                                
                    # --- Convert all dummies to bones after importing ---
                    log("🔄 Converting dummies to bones...")

                    DELETE_ORIGINAL_DUMMIES = False
                    ARMATURE_NAME = "MDL_Armature"

                    # --- Create a new armature object ---
                    arm_data = bpy.data.armatures.new(ARMATURE_NAME)
                    arm_obj = bpy.data.objects.new(ARMATURE_NAME, arm_data)
                    bpy.context.collection.objects.link(arm_obj)

                    # --- Enter edit mode (necessary to construct the armature in Blender) ---
                    bpy.context.view_layer.objects.active = arm_obj
                    bpy.ops.object.select_all(action='DESELECT')
                    arm_obj.select_set(True)
                    bpy.ops.object.mode_set(mode='EDIT')

                    # --- Create one bone per dummy ---
                    name_to_bone = {}
                    for dummy in dummies:
                        bone = arm_data.edit_bones.new(dummy.name)
                        bone.head = dummy.matrix_world.to_translation()
                        bone.tail = bone.head + dummy.matrix_world.to_3x3() @ Vector((0, 0.05, 0))
                        bone.roll = 0
                        name_to_bone[dummy.name] = bone

                    # --- Set parent relationships ---
                    for dummy in dummies:
                        if dummy.parent and dummy.parent.name in name_to_bone:
                            child_bone = name_to_bone[dummy.name]
                            parent_bone = name_to_bone[dummy.parent.name]
                            child_bone.parent = parent_bone

                    bpy.ops.object.mode_set(mode='OBJECT')
                    
                    DELETE_ORIGINAL_DUMMIES = True # now get rid of our dummy helpers

                    if DELETE_ORIGINAL_DUMMIES:
                        bpy.ops.object.select_all(action='DESELECT')
                        for dummy in dummies:
                            dummy.select_set(True)
                        bpy.ops.object.delete()

                    log(f"✔ Converted {len(dummies)} dummies into bones.")

                    f.seek(geom_ptr)
                    section_type = 3
                    
                    # --- Update parsing state to section type 3 (Geometry) if successful ---                     
                    if section_type == 3:
                        log(" Detected Section Type: 3(Geometry)")
                        
                        
                        #RslMaterialList
                        part_materials = []
                        part_offsets = []
                        current_atomic_material_list = []

                        _ = read_u32()  # unknown0
                        _ = read_u32()  # unknown1
                        _ = read_u32()  # unknown2

                        material_list_ptr = read_u32()
                        material_count = read_u32()

                        log(f"🧵 Material List Ptr: 0x{material_list_ptr:X}")
                        log(f"🎨 Material Count: {material_count}")

                        if material_count > 0:
                            old_pos = f.tell()
                            f.seek(material_list_ptr)

                            for i in range(material_count):
                                log(f"  ↪ Reading Material {i + 1}/{material_count}")
                                current_material = {
                                    "offset": 0,
                                    "texture": None,
                                    "rgba": None,
                                    "specular": None
                                }
                                
                                #RslMaterial
                                cur_mat_ptr = read_u32()
                                log(f"    ⤷ Material Ptr: 0x{cur_mat_ptr:X}")
                                old_mat_pos = f.tell()
                                f.seek(cur_mat_ptr)

                                tex_ptr = read_u32()
                                log(f"    ⤷ Texture Ptr: 0x{tex_ptr:X}")
                                if tex_ptr > 0:
                                    temp_pos = f.tell()
                                    f.seek(tex_ptr)
                                    tex_name = read_string(tex_ptr)
                                    current_material["texture"] = tex_name
                                    log(f"    🎯 Texture Name: {tex_name}")
                                    f.seek(temp_pos)

                                rgba = read_u32()
                                current_material["rgba"] = rgba
                                log(f"    🎨 RGBA Value: 0x{rgba:08X}")

                                _ = read_u32()  # Unknown value

                                spec_ptr = read_u32()
                                log(f"    ⤷ Specular Ptr: 0x{spec_ptr:X}")
                                if spec_ptr > 0:
                                    temp_pos = f.tell()
                                    f.seek(spec_ptr)
                                    _ = read_u32()
                                    _ = read_u32()
                                    specular_value = read_f32()
                                    current_material["specular"] = specular_value
                                    log(f"    ✨ Specular: {specular_value:.6f}")
                                    f.seek(temp_pos)

                                f.seek(old_mat_pos)
                                current_atomic_material_list.append(current_material)

                            f.seek(old_pos)
                            
                            # Skip 13 DWORDs
                            for i in range(13):
                                f.read(4)
                            log("✔ Skipped 13 DWORDs")

                            # Read X/Y/Z scale as floats
                            
                            xscale_offset = f.tell()
                            xScale = struct.unpack('<f', f.read(4))[0]
                            yscale_offset = f.tell()
                            yScale = struct.unpack('<f', f.read(4))[0]
                            zscale_offset = f.tell()
                            zScale = struct.unpack('<f', f.read(4))[0]

                            log(f"🟧 xScale is at file offset: 0x{xscale_offset:X}")
                            log(f"🟧 yScale is at file offset: 0x{yscale_offset-4:X}")
                            log(f"🟧 zScale is at file offset: 0x{zscale_offset-4:X}")
                            log(f"✔ xScale: {xScale}, yScale: {yScale}, zScale: {zScale}")

                            # Read overall translation as floats, apply scale factor
                            scaleFactor = 69 # ;) seems to do the job
                            overallTranslation = {}
                            offset_x = f.tell()
                            overallTranslation['x'] = struct.unpack('<f', f.read(4))[0] * scaleFactor / 100
                            log(f"✔ overallTranslation['x'] read at file offset: 0x{offset_x:X} ({offset_x})")

                            # Read Y
                            offset_y = f.tell()
                            overallTranslation['y'] = struct.unpack('<f', f.read(4))[0] * scaleFactor / 100
                            log(f"✔ overallTranslation['y'] read at file offset: 0x{offset_y:X} ({offset_y})")

                            # Read Z
                            offset_z = f.tell()
                            overallTranslation['z'] = struct.unpack('<f', f.read(4))[0] * scaleFactor / 100
                            log(f"✔ overallTranslation['z'] read at file offset: 0x{offset_z:X} ({offset_z})")

                            log(f"✔ overallTranslation: {overallTranslation}")
                            
                            # Parse part offsets/materials
                            partOffsets = []
                            partMaterials = []

                            temp = struct.unpack('<I', f.read(4))[0]
                            while (temp & 0x60000000) != 0x60000000:
                                # 6 DWORDs, skipped
                                for i in range(6):
                                    f.read(4)
                                temp_offset = struct.unpack('<I', f.read(4))[0]
                                partOffsets.append(temp_offset)
                                short1 = struct.unpack('<H', f.read(2))[0]  # unused
                                temp_mat = struct.unpack('<H', f.read(2))[0]
                                partMaterials.append(temp_mat)
                                f.read(4)  # skip
                                f.read(4)  # skip
                                f.read(4)  # skip
                                temp = struct.unpack('<I', f.read(4))[0]
                                temp = temp & 0x60000000
                            log(f"✔ partOffsets: {partOffsets}")
                            log(f"✔ partMaterials: {partMaterials}")

                            # Seek back 4 bytes
                            f.seek(-4, 1)

                            # Geometry Parts Sub-Section
                            # going through our vertex stride here (x, y, z, u, v, etc...)
                            strips = []
                            stripCount = 0
                            geoStart = f.tell()
                            log(f"geoStart: 0x{geoStart:X}")

                            

                            for part_index, part_offset in enumerate(partOffsets):
                                part_addr = geoStart + part_offset
                                part_verts = []
            
                                vert_base = 0  # Always zero per part
                                if part_index + 1 < len(partOffsets):
                                    next_part_addr = geoStart + partOffsets[part_index + 1]
                                else:
                                    # Last part: go to EOF or section end
                                    f.seek(0, 2)
                                    next_part_addr = f.tell()
                                f.seek(part_addr)
                                log(f"\n🔄 Reading geometry part {part_index+1}/{len(partOffsets)} (Offset: 0x{part_addr:X})")
                                
                                if 'partOffsets' in locals():
                                    log("====== Geometry Part Offsets ======")
                                    for i, part_offset in enumerate(partOffsets):
                                        log(f"Part {i+1}: file offset 0x{geoStart + part_offset:X}")
                                    log("===================================")
                                
                                while f.tell() < next_part_addr:
                                    # Save the current offset in case we want to log where we start looking for markers
                                    marker_seek = f.tell()
                                    log(f"🔎 Looking for triangle strip marker at offset: 0x{marker_seek:X}")

                                    # Read 4 bytes as a potential marker
                                    marker = struct.unpack('<I', f.read(4))[0]
                                    log(f"   Read marker 0x{marker:08X} at 0x{marker_seek:X}")

                                    # Loop: skip chunks until we find a valid strip marker (top marker bits == 0x60000000)
                                    while (marker & 0x60000000) != 0x60000000 and f.tell() < next_part_addr:
                                        log(f"      Not a strip marker (got 0x{marker:08X}). Skipping 44 bytes (11 DWORDs) at 0x{f.tell():X}")
                                        for _ in range(11):
                                            f.read(4)  # Skip 4 bytes, 11 times (44 bytes total)
                                        skip_offset = f.tell()
                                        marker = struct.unpack('<I', f.read(4))[0]
                                        log(f"      Checked marker 0x{marker:08X} at 0x{skip_offset:X}")

                                    # If we didn't find a valid marker, break out
                                    if (marker & 0x60000000) != 0x60000000:
                                        log(f"✗ No valid strip marker found, breaking out at offset 0x{f.tell():X}")
                                        break  # No more strips in this part

                                    # Go back 4 bytes so the main strip reading code starts at the actual marker
                                    f.seek(marker_seek, 0)
                                    log(f"✔ Valid strip marker found at 0x{f.tell():X}, rewinding 4 bytes for strip reader.")

                                    for _ in range(4):
                                        f.read(4)
                                        
                

                                    tri_strip_start = f.tell()
                                    log(f"  Tri-Strip Start: 0x{tri_strip_start:X}")

                                    for _ in range(8):
                                        f.read(4)
                                    _ = struct.unpack('<H', f.read(2))[0]
                                    curStripVertCount = struct.unpack('<B', f.read(1))[0]
                                    padByte = struct.unpack('<B', f.read(1))[0]
                                    log(f"    - curStripVertCount: {curStripVertCount} (padByte={padByte}) at 0x{f.tell():X}")


                                    globalScale = scaleFactor * 0.00003
                                    
                                    
                                    vertex_data_offset = f.tell()  # Get current file pointer position
                                    log(f"    🧊 Vertex data begins at file offset: 0x{vertex_data_offset:X} ({vertex_data_offset})")
                                    
                                    verts = []
                                    
                                    for vi in range(curStripVertCount):
                                        offset_x = f.tell()
                                        x_raw = struct.unpack('<h', f.read(2))[0]
                                        offset_y = f.tell()
                                        y_raw = struct.unpack('<h', f.read(2))[0]
                                        offset_z = f.tell()
                                        z_raw = struct.unpack('<h', f.read(2))[0]

                                        x = x_raw * xScale * globalScale + overallTranslation['x']
                                        y = y_raw * yScale * globalScale + overallTranslation['y']
                                        z = z_raw * zScale * globalScale + overallTranslation['z']

                                        verts.append((x, y, z))
                                        
                                        
                                        
                                        log(f"        🧊 Vertex {vi}:")
                                        log(f"           • X Offset: 0x{offset_x:X}, Raw: {x_raw}, Final: {x:.6f}")
                                        log(f"           • Y Offset: 0x{offset_y:X}, Raw: {y_raw}, Final: {y:.6f}")
                                        log(f"           • Z Offset: 0x{offset_z:X}, Raw: {z_raw}, Final: {z:.6f}")
                                    
                                    

                                    
                                    part_verts.extend(verts)

                                    # --- Now we proceed to UV sub-section ---

                                    # -- Padding short if odd vertex count
                                    if (curStripVertCount % 2) == 1:
            
                                        pad_short = struct.unpack('<h', f.read(2))[0]
                                        log(f"    ⬛ Padding short after verts (odd count): {pad_short} at 0x{f.tell():X}")
                                        
                                        
                                    # -- Read sub-section: short, tvert count, extra byte
                                    _ = struct.unpack('<H', f.read(2))[0]  # Skip/Read short
                                    curStripTVertCount = struct.unpack('<B', f.read(1))[0]
                                    padByte2 = struct.unpack('<B', f.read(1))[0]
                                    log(f"    ⬛ curStripTVertCount: {curStripTVertCount} (pad2={padByte2}) at 0x{f.tell():X}")
                                    
                                    UV_SCALE = 2048.0  # or 4096.0 in some models - 2048 seems standard for LCS/VCS
                                    BONE_SCALE = 2048.0 # ditto unless found in data
                                             
                                    uvs = []
                                    for i in range(curStripTVertCount):
                                        u = struct.unpack('<h', f.read(2))[0]
                                        v = struct.unpack('<h', f.read(2))[0]
                                        u_f = u / UV_SCALE
                                        v_f = v / UV_SCALE
                                        uvs.append((u_f, v_f))
                                        log(f"      🟪 UV {i}: U={u_f:.6f}, V={v_f:.6f} (raw: {u}, {v})")
                                    
                                    # -After reading UVs:
                                    section_padding = 4 - ((2 * curStripTVertCount * 2) % 4)  # 2 shorts (4 bytes) per UV
                                    if section_padding != 4:
                                        f.read(section_padding)
                                        log(f"    🟦 Padding after UVs: {section_padding} bytes")
            

                                    # --- NOW, read all optional per-strip attribute subsections (vertcol, normals, skin, etc) ---
                                    while True:
                                        subsection_pos = f.tell()
                                        header = f.read(4)
                                        if len(header) < 4:
                                            break  # End of file or bad read

                                        # Interpret as both int and bytes
                                        marker_val = struct.unpack('<I', header)[0]
                                        b0, b1, b2, b3 = header[0], header[1], header[2], header[3]

                                        # --- If it's a strip marker, rewind and leave this per-strip attribute section ---
                                        if marker_val == 0x60000000 or marker_val == 0x6C018000:
                                            f.seek(subsection_pos, 0)
                                            log(f"✔ Found next strip marker at 0x{subsection_pos:X}")
                                            break  # Now, go to your main strip-searching logic

                                        # --- If it's a known per-strip attribute subsection ---
                                        elif b1 == 0x80 and b3 in (0x6F, 0x6A, 0x6C):
                                            # We have a per-strip attribute header!
                                            section_count = b2
                                            log(f"   >> Subsection header: b1={b1:02X}, count={section_count}, b3={b3:02X} at 0x{subsection_pos:X}")

                                            if b3 == 0x6F:
                                                log(f"      🎨 Reading {section_count} vertex colors")
                                                for i in range(section_count):
                                                    vcolor = struct.unpack('<H', f.read(2))[0]
                                                    r = (vcolor & 0x1F) * (1.0 / 31.0)
                                                    g = ((vcolor >> 5) & 0x1F) * (1.0 / 31.0)
                                                    b = ((vcolor >> 10) & 0x1F) * (1.0 / 31.0)
                                                    a = ((vcolor >> 15) & 0x01) * 1.0
                                                    log(f"         R={r:.3f} G={g:.3f} B={b:.3f} A={a:.1f} (raw=0x{vcolor:04X})")
                                                pad = 2 - ((2 * section_count) % 4)
                                                if pad != 4:
                                                    f.read(pad)

                                            elif b3 == 0x6A:
                                                log(f"      🧲 Reading {section_count} normals")
                                                for i in range(section_count):
                                                    nx = struct.unpack('<b', f.read(1))[0] / 127.0
                                                    ny = struct.unpack('<b', f.read(1))[0] / 127.0
                                                    nz = struct.unpack('<b', f.read(1))[0] / 127.0
                                                    log(f"         N={nx:.4f} {ny:.4f} {nz:.4f}")
                                                pad = 4 - ((3 * section_count) % 4)
                                                if pad != 4:
                                                    f.read(pad)

                                            elif b3 == 0x6C:
                                                log(f"      🦴 Reading {section_count} skin weights")
                                                for i in range(section_count):
                                                    bone1 = struct.unpack('<B', f.read(1))[0] // 4
                                                    f.read(1)
                                                    w1 = struct.unpack('<H', f.read(2))[0] / 2048.0
                                                    bone2 = struct.unpack('<B', f.read(1))[0] // 4
                                                    f.read(1)
                                                    w2 = struct.unpack('<H', f.read(2))[0] / 2048.0
                                                    bone3 = struct.unpack('<B', f.read(1))[0] // 4
                                                    f.read(1)
                                                    w3 = struct.unpack('<H', f.read(2))[0] / 2048.0
                                                    bone4 = struct.unpack('<B', f.read(1))[0] // 4
                                                    f.read(1)
                                                    w4 = struct.unpack('<H', f.read(2))[0] / 2048.0
                                                    log(f"         B1={bone1} W1={w1:.4f} ... B4={bone4} W4={w4:.4f}")
                                            continue  # After reading this subsection, see if there's another

                                        




                                if part_verts:
                                    mesh = bpy.data.meshes.new(f"ImportedMDL_Part{part_index}")
                                    obj = bpy.data.objects.new(f"ImportedMDL_Part{part_index}", mesh)
                                    bpy.context.collection.objects.link(obj)
                                    mesh.from_pydata(part_verts, [], [])
                                    mesh.update()
                                    log(f"✔ Imported mesh part {part_index} with {len(part_verts)} verts")
                                else:
                                    log(f"✗ No vertices found to import in part {part_index}!")
                            

        except Exception as e:
            self.report({'ERROR'}, f"Import error: {e}")
            # Try to write a failure log too
            txt_path = os.path.splitext(filepath)[0] + "_import_log.txt"
            try:
                with open(txt_path, 'w', encoding='utf-8') as outf:
                    outf.write('\n'.join(debug_log))
            except Exception:
                pass
            return {'CANCELLED'}

        # Write debug log to file at the end
        txt_path = os.path.splitext(filepath)[0] + "_import_log.txt"
        try:
            with open(txt_path, 'w', encoding='utf-8') as outf:
                outf.write('\n'.join(debug_log))
            log(f"✔ Debug log written to: {txt_path}")
        except Exception as e:
            log(f"✗ Failed to write debug log: {e}")

        return {'FINISHED'}


def menu_func_import(self, context):
    self.layout.operator(ImportMDLOperator.bl_idname, text="GTA .MDL (LCS/VCS Fixed)")


def register():
    bpy.utils.register_class(ImportMDLOperator)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.utils.unregister_class(ImportMDLOperator)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)


if __name__ == "__main__":
    register()   