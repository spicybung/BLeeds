import struct
import bpy
from mathutils import Matrix, Vector
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper

class IMPORT_OT_read_mdl_header(Operator, ImportHelper):
    bl_idname = "import_scene.read_mdl_header"
    bl_label = "Import MDL and Read Header"
    filename_ext = ".mdl"
    filter_glob: bpy.props.StringProperty(default="*.mdl", options={'HIDDEN'})

    def execute(self, context):
        
        bone_map = {}
        
        def read_bone(f, offset, depth=0, parent_offset=0):
            indent = "  " * depth
            f.seek(offset)
            bone_data = f.read(192)
            if len(bone_data) < 192:
                print(f"{indent}!! Incomplete bone read at 0x{offset:08X}")
                return

            # Unpack first 24 bytes
            header = struct.unpack("<6I", bone_data[:24])
            sibling_offset = header[1]
            parent_ptr = header[2]
            subbone_offset = header[4]
            anim_data_idx_offset = header[5]

            # Read name (next 40 bytes)
            bone_name_bytes = bone_data[24:64]
            bone_name = bone_name_bytes.split(b'\x00')[0].decode('ascii', errors='replace')

            # Read WorldPos matrix (last 64 bytes of the 192-byte bone block)
            world_matrix_raw = bone_data[128:192]
            raw = struct.unpack("<16f", world_matrix_raw)

            # Convert from column-major to row-major
            mat = Matrix((
                (raw[0], raw[4], raw[8],  raw[12]),
                (raw[1], raw[5], raw[9],  raw[13]),
                (raw[2], raw[6], raw[10], raw[14]),
                (raw[3], raw[7], raw[11], raw[15])
            ))

            # Optional: convert from Y-up to Z-up (rotate -90° around X)
            y_up_to_z_up = Matrix.Rotation(-3.14159265 / 2, 4, 'X')
            mat = mat @ y_up_to_z_up

            # Store bone with correct matrix
            bone_map[offset] = {
                'name': bone_name,
                'parent_offset': parent_ptr,
                'matrix': mat
            }


            print(f"{indent}==== Bone at 0x{offset:08X} ====")
            print(f"{indent}Name:                   {bone_name}")
            print(f"{indent}Sibling Offset:         0x{sibling_offset:08X}")
            print(f"{indent}Parent Offset:          0x{parent_ptr:08X}")
            print(f"{indent}SubBone Offset:         0x{subbone_offset:08X}")
            print(f"{indent}AnimBoneDataIdx Offset: 0x{anim_data_idx_offset:08X}")
            print(f"{indent}=============================")

            if subbone_offset != 0:
                read_bone(f, subbone_offset, depth + 1, offset)
            if sibling_offset != 0:
                read_bone(f, sibling_offset, depth, parent_offset)
                
        anim_bone_map = {}

        def read_anim_bone_data(f, anim_data_idx_offset):
            f.seek(anim_data_idx_offset)
            raw = f.read(24)
            num_bones, _, _, anim_data_offset, _, _ = struct.unpack("<6I", raw)
            
            f.seek(anim_data_offset)
            for _ in range(num_bones):
                bone_id, bone_type, bone_offset = struct.unpack("<HHI", f.read(8))
                anim_bone_map[bone_id] = {
                    "offset": bone_offset,
                    "type": bone_type
                }


        def read_vertex_by_type(f, vtype, count):
            vertices = []
            for _ in range(count):
                if vtype == 0x52:
                    data = struct.unpack("<3f3hH4B", f.read(28))
                    pos = data[0:3]
                    norm = tuple(i / 32768.0 for i in data[3:6])
                    color = data[7:11]
                    vertices.append((pos, norm, color, None))
                elif vtype == 0x152:
                    data = struct.unpack("<3f3hH4B2f", f.read(36))
                    pos = data[0:3]
                    norm = tuple(i / 32768.0 for i in data[3:6])
                    color = data[7:11]
                    uv = data[11:13]
                    vertices.append((pos, norm, color, uv))
                elif vtype == 0x115E:
                    data = struct.unpack("<3f4f4B3hH4B2f", f.read(52))
                    pos = data[0:3]
                    skin_weights = data[3:7]
                    bone_ids = data[7:11]
                    norm = tuple(i / 32768.0 for i in data[11:14])
                    color = data[15:19]
                    uv = data[19:21]
                    vertices.append((pos, norm, color, uv, skin_weights, bone_ids))
                elif vtype == 0x125E:
                    data = struct.unpack("<3f4f4B3hH4B4f", f.read(60))
                    pos = data[0:3]
                    skin_weights = data[3:7]
                    bone_ids = data[7:11]
                    norm = tuple(i / 32768.0 for i in data[11:14])
                    color = data[15:19]
                    uv1 = data[19:21]
                    uv2 = data[21:23]
                    vertices.append((pos, norm, color, uv1, uv2, skin_weights, bone_ids))
                elif vtype == 0x252:
                    data = struct.unpack("<3f3hH4B4f", f.read(44))
                    pos = data[0:3]
                    norm = tuple(i / 32768.0 for i in data[3:6])
                    color = data[7:11]
                    uv1 = data[11:13]
                    uv2 = data[13:15]
                    vertices.append((pos, norm, color, uv1, uv2))
                else:
                    raise ValueError(f"Unknown VertexElementType: 0x{vtype:X}")
            return vertices

        with open(self.filepath, "rb") as f:
            # -------------------------------
            # Read WDR Header
            # -------------------------------
            data = f.read(0x28)
            header = struct.unpack("<4sIIIIIIIii", data)

            signature = header[0].decode("ascii")
            first_entry_offset = header[8]

            print("\n==== Reading MDL Header ====")
            print(f"Signature:           {signature}")
            print(f"Version:             {header[1]:08X}")
            print(f"File Size:           {header[2]} bytes")
            print(f"Data Size:           {header[3]} bytes")
            print(f"Offset Table Start:  0x{header[4]:08X}")
            print(f"Num Table Entries:   {header[5]}")
            print(f"Zero1:               {header[6]}")
            print(f"Zero2:               {header[7]}")
            print(f"First Entry Offset:  0x{first_entry_offset:08X}")
            print(f"Last Entry Offset:   0x{header[9]:08X}")
            print("============================\n")

            # -------------------------------
            # Read EntryIndex
            # -------------------------------
            f.seek(first_entry_offset)
            entry_index_data = f.read(16)
            entry_index = struct.unpack("<iiii", entry_index_data)
            entry_data_offset = entry_index[2]

            print("==== Reading First EntryIndex ====")
            print(f"Next Entry Offset:   0x{entry_index[0]:08X}")
            print(f"Prev Entry Offset:   0x{entry_index[1]:08X}")
            print(f"Entry Data Offset:   0x{entry_data_offset:08X}")
            print(f"Zero Field:          {entry_index[3]}")
            print("==================================\n")

            # -------------------------------
            # Read Entry Structure
            # -------------------------------
            f.seek(entry_data_offset)
            entry_struct_data = f.read(0x1C)
            entry = struct.unpack("<7i", entry_struct_data)

            root_bone_offset = entry[0]
            unknown = entry[3]
            first_obj_info_offset = entry[4]
            last_obj_info_offset = entry[5]


            print("==== Reading Entry ====")
            print(f"Root Bone Offset:         0x{root_bone_offset:08X}")
            print(f"First ObjectInfo Offset:  0x{first_obj_info_offset:08X}")
            print(f"Last ObjectInfo Offset:   0x{last_obj_info_offset:08X}")
            print(f"Unknown Field:            0x{unknown:08X}")
            print("==================================\n")

            # -------------------------------
            # Read Bone Hierarchy
            # -------------------------------
            if root_bone_offset > 0:
                print("Traversing Bone Hierarchy:")
                # Read root bone's first 24 bytes to get anim_data_idx_offset
                f.seek(root_bone_offset)
                root_bone_raw = f.read(24)
                if len(root_bone_raw) < 24:
                    print("!! Root bone read failed")
                else:
                    anim_data_idx_offset = struct.unpack("<6I", root_bone_raw)[5]
                    read_bone(f, root_bone_offset)
                    if anim_data_idx_offset > 0:
                        read_anim_bone_data(f, anim_data_idx_offset)

            else:
                print("Root Bone Offset is 0 — skipping root bone read.\n")

            # -------------------------------
            # Read ObjectInfo
            # -------------------------------
            object_info_offset = first_obj_info_offset
            if object_info_offset == 0 and last_obj_info_offset > 0:
                print("First ObjectInfo Offset is 0 — falling back to Last ObjectInfo Offset.\n")
                object_info_offset = last_obj_info_offset

            if object_info_offset > 0:
                f.seek(object_info_offset)
                object_info_data = f.read(28)
                object_info = struct.unpack("<7i", object_info_data)

                object_data_offset = object_info[3]

                print("==== Reading ObjectInfo ====")
                print(f"Next Object Offset:       0x{object_info[0]:08X}")
                print(f"Prev Object Offset:       0x{object_info[1]:08X}")
                print(f"Parent Bone Offset:       0x{object_info[2]:08X}")
                print(f"Object Data Offset:       0x{object_data_offset:08X}")
                print(f"Root Entry Offset:        0x{object_info[4]:08X}")
                print(f"Zero Field:               0x{object_info[5]:08X}")
                print(f"Unknown (Always 3):       0x{object_info[6]:08X}")
                print("==================================\n")

            # -------------------------------
            # Read Object Chunk Header
            # -------------------------------
            f.seek(object_data_offset)
            obj_chunk = f.read(180)
            if len(obj_chunk) < 180:
                print("!! Incomplete Object Header read")
            else:
                (
                    material_offset, num_materials, bone_trans_offset, unknown_f, unknown1,
                    ux, uy, uz, model_chunk_flag, model_chunk_size,
                    zero, numMaterialIDs, numFaceIndex,
                    bs_x, bs_y, bs_z, bs_radius,
                    scale_x, scale_y, scale_z,
                    num_vertices, zero2_0, zero2_1, zero2_2,
                    per_vertex_size,
                    unk4_0, unk4_1, unk4_2, unk4_3, unk4_4,
                    unk4_5, unk4_6, unk4_7, unk4_8, unk4_9, unk4_10,
                    vertex_element_type,
                    unk5_0, unk5_1, unk5_2, unk5_3,
                    unk5_4, unk5_5, unk5_6, unk5_7
                ) = struct.unpack("<3I f I 3f 2I 3I 3f f 3f I 3I I 11I I 8I", obj_chunk)

                unknown4 = [unk4_0, unk4_1, unk4_2, unk4_3, unk4_4, unk4_5, unk4_6, unk4_7, unk4_8, unk4_9, unk4_10]
                unknown5 = [unk5_0, unk5_1, unk5_2, unk5_3, unk5_4, unk5_5, unk5_6, unk5_7]

                print("==== Reading Object Chunk Header ====")
                print(f"Material Offset:           0x{material_offset:08X}")
                print(f"Num Materials:             {num_materials}")
                print(f"BoneTransDataIndexOffset:  0x{bone_trans_offset:08X}")
                print(f"Unknown Float:             {unknown_f}")
                print(f"Unknown Int:               0x{unknown1:08X}")
                print(f"Unknown3 Vector:           ({ux:.4f}, {uy:.4f}, {uz:.4f})")
                print(f"Model Chunk Flag:          0x{model_chunk_flag:08X}")
                print(f"Model Chunk Size:          {model_chunk_size}")
                print(f"Zero:                      0x{zero:08X}")
                print(f"Number of Material IDs:    {numMaterialIDs}")
                print(f"Number of Face Indices:    {numFaceIndex}")
                print(f"Bounding Sphere XYZ:       ({bs_x:.3f}, {bs_y:.3f}, {bs_z:.3f})")
                print(f"Bounding Sphere Radius:    {bs_radius:.3f}")
                print(f"Bounding Scale XYZ:        ({scale_x:.3f}, {scale_y:.3f}, {scale_z:.3f})")
                print(f"Number of Vertices:        {num_vertices}")
                print(f"Zero2 (int[3]):            ({zero2_0}, {zero2_1}, {zero2_2})")
                print(f"Per-Vertex Element Size:   {per_vertex_size}")
                print(f"Unknown4 (int[11]):        {unknown4}")
                print(f"Vertex Element Type:       0x{vertex_element_type:X}")
                print(f"Unknown5 (int[8]):         {unknown5}")
                print("======================================\n")

                
            # -------------------------------
            # Read BoneTransDataIndex (header)
            # -------------------------------
            bone_matrices = []

            if bone_trans_offset != 0:
                f.seek(bone_trans_offset)
                bone_data_idx_raw = f.read(8)
                if len(bone_data_idx_raw) < 8:
                    print("!! Incomplete BoneTransDataIndex struct")
                else:
                    num_bones, bone_data_offset = struct.unpack("<2I", bone_data_idx_raw)
                    print(f"\n==== BoneTransformDataIndex ====")
                    print(f"Number of Bones:           {num_bones}")
                    print(f"BoneTransData Offset:      0x{bone_data_offset:08X}")
                    
            # -------------------------------
            # Read Bone Transform Matrices
            # -------------------------------
            bone_matrices = []

            if bone_trans_offset != 0:
                f.seek(bone_trans_offset)
                bone_data_idx_raw = f.read(8)
                if len(bone_data_idx_raw) < 8:
                    print("!! Incomplete BoneTransDataIndex struct")
                else:
                    num_bones, bone_data_offset = struct.unpack("<2I", bone_data_idx_raw)
                    print(f"\n==== Bone Transform Data ====")
                    print(f"Number of Bones:           {num_bones}")
                    print(f"BoneTransData Offset:      0x{bone_data_offset:08X}")

                    f.seek(bone_data_offset)
                    for i in range(num_bones):
                        matrix_raw = f.read(64)
                        if len(matrix_raw) < 64:
                            print(f"!! Incomplete matrix read for bone {i}")
                            break

                        raw = struct.unpack("<16f", matrix_raw)

                        # Convert from column-major to row-major
                        mat = Matrix((
                            (raw[0], raw[4], raw[8],  raw[12]),
                            (raw[1], raw[5], raw[9],  raw[13]),
                            (raw[2], raw[6], raw[10], raw[14]),
                            (raw[3], raw[7], raw[11], raw[15])
                        ))

                        # Optional: Rotate Y-up to Z-up
                        y_up_to_z_up = Matrix.Rotation(-3.14159265 / 2, 4, 'X')  # -90° X
                        mat = mat @ y_up_to_z_up

                        bone_matrices.append(mat)

                        print(f"Bone {i} Transform Matrix:")
                        for row in mat:
                            print(f"  ({row[0]:.6f}, {row[1]:.6f}, {row[2]:.6f}, {row[3]:.6f})")

                    print("======================================\n")

            else:
                print("No BoneTransDataIndex offset found (0). Skipping.")


            # -------------------------------
            # Read Materials
            # -------------------------------
            materials = []
            if material_offset != 0 and num_materials > 0:
                f.seek(material_offset)
                for i in range(num_materials):
                    mat_raw = f.read(16)
                    if len(mat_raw) < 16:
                        print(f"!! Material {i} read incomplete")
                        break

                    tex_offset, b_loaded = struct.unpack("<IB", mat_raw[:5])
                    color = struct.unpack("4B", mat_raw[5:9])
                    # Skips 3 bytes of padding

                    # Save current position to come back after reading TexName
                    current = f.tell()

                    # Read Texture Name
                    f.seek(tex_offset)
                    tex_name_bytes = bytearray()
                    while True:
                        b = f.read(1)
                        if not b or b == b'\x00':
                            break
                        tex_name_bytes += b
                    tex_name = tex_name_bytes.decode("ascii", errors="replace")

                    materials.append({
                        "tex_name": tex_name,
                        "color": color,
                        "loaded": b_loaded
                    })

                    print(f"Material {i}: Loaded={b_loaded}, Color RGBA={color}, TexName='{tex_name}'")

                    f.seek(current)
            else:
                print("No material block found or num_materials == 0.")
                
                

            print("Creating Blender Armature from Matrices...")
            arm_data = bpy.data.armatures.new("MDL_Armature")
            arm_obj = bpy.data.objects.new("MDL_Armature", arm_data)
            bpy.context.collection.objects.link(arm_obj)
            bpy.context.view_layer.objects.active = arm_obj
            bpy.ops.object.mode_set(mode='EDIT')

            bone_lookup = {}

            # Create all bones first
            for offset, bone_data in bone_map.items():
                name = bone_data["name"]
                matrix = bone_data.get("matrix")  # Must be added below
                if matrix is None:
                    continue

                edit_bone = arm_data.edit_bones.new(name)
                head = matrix.to_translation()
                tail = head + matrix.to_3x3() @ Vector((0, 0.05, 0))  # Y axis tail offset

                edit_bone.head = head
                edit_bone.tail = tail
                bone_lookup[offset] = edit_bone

            # Assign parent relationships
            for offset, bone_data in bone_map.items():
                parent_offset = bone_data["parent_offset"]
                if parent_offset in bone_lookup and offset in bone_lookup:
                    bone_lookup[offset].parent = bone_lookup[parent_offset]

            bpy.ops.object.mode_set(mode='OBJECT')
            print("Armature created.")



        return {'FINISHED'}

def menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_read_mdl_header.bl_idname, text="Read MDL Header (.mdl)")

def register():
    bpy.utils.register_class(IMPORT_OT_read_mdl_header)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.utils.unregister_class(IMPORT_OT_read_mdl_header)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

if __name__ == "__main__":
    register()
