import bpy
import struct

from math import radians, pi
from mathutils import Matrix, Vector
from bpy_extras.io_utils import ImportHelper
from bpy.types import Operator
from bpy.props import StringProperty


# See info: https://gtamods.com/wiki/Relocatable_chunk
# and: https://gtamods.com/wiki/Leeds_Engine
# also: https://gtamods.com/wiki/MDL

commonBoneOrderVCS = [
    "root", "pelvis", "spine", "spine1", "neck", "head",
    "jaw", "bip01_l_clavicle", "l_upperarm", "l_forearm", "l_hand", "l_finger",
    "bip01_r_clavicle", "r_upperarm", "r_forearm", "r_hand", "r_finger",
    "l_thigh", "l_calf", "l_foot", "l_toe0",
    "r_thigh", "r_calf", "r_foot", "r_toe0"
]

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

global_scale = 1.0
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
overall_translation = Vector((0.0, 0.0, 0.0))
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

                    mat = Matrix((
                        (row1.x, row2.x, row3.x, row4.x),
                        (row1.y, row2.y, row3.y, row4.y),  # Transpose row-order to Blender column-order
                        (row1.z, row2.z, row3.z, row4.z),
                        (0.0,    0.0,    0.0,    1.0)      # Frame/bone position + scale factor
                    ))

                    return mat, matrix_offset, (row1, row2, row3, row4)

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

                # --- Header ---
                print(f"✔ Opened: {filepath}")
                if f.read(4) != b'ldm\x00':  # Identifier at start of file - where we begin to read
                    self.report({'ERROR'}, "Invalid Stories MDL header") # Not a Stories MDL?
                    return {'CANCELLED'}     # eject process if invalid
                shrink = read_u32()          # 1 if GTAG resource image, else always 0(unused)
                file_len = read_u32()        # physical fiile size
                local_numTable = read_u32()  # local entries numtable
                global_numTable = read_u32() # global entries numtable
                if global_numTable == (local_numTable + 4): # if global_numTable after local than = VCS
                    actor_MDL = True
                    print(f"✔ Ped model/actor MDL detected.") # than this is an actor/ped model
                else:
                    numEntries = read_u32()  # read number of entries after local numTable?(=/= VCS)
                    print(f"✔ Non-actor MDL detected: building or MH2.") # than modelinfo =/= ped
                numEntries = read_u32()  # number of entries
                ptr2_before_tex = read_u32() # whats this do?
                allocMem = read_u32()  # amount of memory allocated to file - alloc ptr?
                _ = read_u32()  # skip D-WORD 0x1D10 - dunno what this does.
                top_level_ptr = read_u32()  # pointer at 0x24
                
                print(f"File Size: 0x{file_len}")
                print(f"Local numTable: 0x{local_numTable:X}, Global numTable: 0x{global_numTable:X}")
                print(f"Number of entries: 0x{numEntries}")
                print(f"Ptr2BeforeTexNameList: 0x{ptr2_before_tex:X}")
                print(f"Allocated memory: 0x{allocMem}")
                print(f"Top-level ptr or magic value: 0x{top_level_ptr:X}")

                f.seek(top_level_ptr)
                top_magic = read_u32()

                section_type = 0
                import_type = 0

                LCSCLUMP = 0x00000002
                VCSCLUMP = 0x0000AA02
                LCSATOMIC1 = 0x01050001
                LCSATOMIC2 = 0x01000001
                VCSATOMIC1 = 0x0004AA01
                VCSATOMIC2 = 0x0004AA01

                if top_magic in (LCSCLUMP, VCSCLUMP):
                    section_type = 7
                    import_type = 1 if top_magic == LCSCLUMP else 2
                elif top_magic in (LCSATOMIC1, LCSATOMIC2, VCSATOMIC1, VCSATOMIC2):
                    section_type = 2
                    import_type = 1 if top_magic in (LCSATOMIC1, LCSATOMIC2) else 2

                print(f"Section Type: {section_type}, Import Type: {import_type}")
                
                # --- Update parsing state to Section Type: 7 (Clump) if successful ---
                if section_type == 7:
                    clump_id = read_u32()
                    first_frame = read_u32()
                    first_atomic = read_u32()
                    atomic_seek = first_atomic - 0x1C
                    f.seek(atomic_seek)
                    section_type = 2 
                    
                # --- Update parsing state to Section Type: 2 (Atomic) if successful -
                if section_type == 2: 
                    print("✔ Detected Section Type 2: Atomic") # RSLElementGroup

                    atomics = []
                    frame_data_list = []
                    dummies = []
                    bone_list = []
                    frame_ptr_list = []
                    root_bone_link = not actor_mdl
                    cur_atomic_index = 1

                    atomic_start = f.tell()
                    print(f"Atomic section begins at: 0x{atomic_start:X}")

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

                    print(f"frame_ptr: 0x{frame_ptr:X}")
                    
                    print(f"geom_ptr:      0x{geom_ptr:X}")
                    
                    print(f"clump_ptr:     0x{clump_ptr:X}")
                    print(f"link_ptr:      0x{link_ptr:X}")
                    
                    print(f"render_cb:     0x{render_cb:X}")
                    print(f"model_info_id: {model_info_id}")
                    print(f"vis_id_flag:   0x{vis_id_flag:X}")
                    print(f"hierarchy_ptr: 0x{hierarchy_ptr:X}")

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
                            
                        print(f"✔ Matrix offset: 0x{matrix_offset:X} for frame '{cur_dummy.name}'")
                        
    
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
                    print(f"✔ Loaded {len(dummies)} bones into Blender as empties.")
                    
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
                    print("🔄 Converting dummies to bones...")

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
                    
                    DELETE_ORIGINAL_DUMMIES = True # get rid of our dummy helpers

                    if DELETE_ORIGINAL_DUMMIES:
                        bpy.ops.object.select_all(action='DESELECT')
                        for dummy in dummies:
                            dummy.select_set(True)
                        bpy.ops.object.delete()

                    print(f"✔ Converted {len(dummies)} dummies into bones.")

                    f.seek(geom_ptr)
                    section_type = 3
                    
                    # --- Update parsing state to section type 3 (Geometry) if successful---                     
                    if section_type == 3:
                        print(" Reading Section Type: 3(Geometry)")

                        part_materials = []
                        part_offsets = []
                        current_atomic_material_list = []

                        _ = read_u32()  # unknown0
                        _ = read_u32()  # unknown1
                        _ = read_u32()  # unknown2

                        material_list_ptr = read_u32()
                        material_count = read_u32()

                        print(f"🧵 Material List Ptr: 0x{material_list_ptr:X}")
                        print(f"🎨 Material Count: {material_count}")

                        if material_count > 0:
                            old_pos = f.tell()
                            f.seek(material_list_ptr)

                            for i in range(material_count):
                                print(f"  ↪ Reading Material {i + 1}/{material_count}")
                                current_material = {
                                    "offset": 0,
                                    "texture": None,
                                    "rgba": None,
                                    "specular": None
                                }

                                cur_mat_ptr = read_u32()
                                print(f"    ⤷ Material Ptr: 0x{cur_mat_ptr:X}")
                                old_mat_pos = f.tell()
                                f.seek(cur_mat_ptr)

                                tex_ptr = read_u32()
                                print(f"    ⤷ Texture Ptr: 0x{tex_ptr:X}")
                                if tex_ptr > 0:
                                    temp_pos = f.tell()
                                    f.seek(tex_ptr)
                                    tex_name = read_string(tex_ptr)
                                    current_material["texture"] = tex_name
                                    print(f"    🎯 Texture Name: {tex_name}")
                                    f.seek(temp_pos)

                                rgba = read_u32()
                                current_material["rgba"] = rgba
                                print(f"    🎨 RGBA Value: 0x{rgba:08X}")

                                _ = read_u32()  # Unknown value

                                spec_ptr = read_u32()
                                print(f"    ⤷ Specular Ptr: 0x{spec_ptr:X}")
                                if spec_ptr > 0:
                                    temp_pos = f.tell()
                                    f.seek(spec_ptr)
                                    _ = read_u32()
                                    _ = read_u32()
                                    specular_value = read_f32()
                                    current_material["specular"] = specular_value
                                    print(f"    ✨ Specular: {specular_value:.6f}")
                                    f.seek(temp_pos)

                                f.seek(old_mat_pos)
                                current_atomic_material_list.append(current_material)

                            f.seek(old_pos)
                            
                            # Step 1: Skip 13 DWORDs
                            for i in range(13):
                                f.read(4)
                            print("✔ Skipped 13 DWORDs")

                            # Step 2: Read X/Y/Z scale as floats
                            
                            xscale_offset = f.tell()
                            xScale = struct.unpack('<f', f.read(4))[0]
                            yscale_offset = f.tell()
                            yScale = struct.unpack('<f', f.read(4))[0]
                            zscale_offset = f.tell()
                            zScale = struct.unpack('<f', f.read(4))[0]

                            print(f"🟧 xScale is at file offset: 0x{xscale_offset:X}")
                            print(f"🟧 yScale is at file offset: 0x{yscale_offset-4:X}")
                            print(f"🟧 zScale is at file offset: 0x{zscale_offset-4:X}")
                            print(f"✔ xScale: {xScale}, yScale: {yScale}, zScale: {zScale}")

                            # Step 3: Read overall translation as floats, apply scale factor
                            scaleFactor = 1.0  
                            overallTranslation = {}
                            overallTranslation['x'] = struct.unpack('<f', f.read(4))[0] * scaleFactor / 100
                            overallTranslation['y'] = struct.unpack('<f', f.read(4))[0] * scaleFactor / 100
                            overallTranslation['z'] = struct.unpack('<f', f.read(4))[0] * scaleFactor / 100
                            print(f"✔ overallTranslation: {overallTranslation}")

                            # Step 4: Parse part offsets/materials
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
                            print(f"✔ partOffsets: {partOffsets}")
                            print(f"✔ partMaterials: {partMaterials}")

                            # Seek back 4 bytes, as in MaxScript
                            f.seek(-4, 1)

                            # Step 5: Geometry Parts Sub-Section
                            strips = []
                            stripCount = 0
                            geoStart = f.tell()
                            print(f"geoStart: 0x{geoStart:X}")
                            

                     
        except Exception as e:
            self.report({'ERROR'}, f"Import error: {e}")
            return {'CANCELLED'}

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