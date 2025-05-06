import struct
import bpy
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper

class IMPORT_OT_read_mdl_header(Operator, ImportHelper):
    bl_idname = "import_scene.read_mdl_header"
    bl_label = "Import MDL and Read Header"
    filename_ext = ".mdl"
    filter_glob: bpy.props.StringProperty(default="*.mdl", options={'HIDDEN'})

    def execute(self, context):
        def read_bone(f, offset, depth=0):
            indent = "  " * depth
            f.seek(offset)
            bone_data = f.read(24)
            if len(bone_data) < 24:
                print(f"{indent}!! Incomplete bone read at 0x{offset:08X}")
                return

            bone = struct.unpack("<6I", bone_data)
            sibling_offset = bone[1]
            parent_offset = bone[2]
            subbone_offset = bone[4]
            anim_data_idx_offset = bone[5]

            print(f"{indent}==== Bone at 0x{offset:08X} ====")
            print(f"{indent}Sibling Offset:         0x{sibling_offset:08X}")
            print(f"{indent}Parent Offset:          0x{parent_offset:08X}")
            print(f"{indent}SubBone Offset:         0x{subbone_offset:08X}")
            print(f"{indent}AnimBoneDataIdx Offset: 0x{anim_data_idx_offset:08X}")
            print(f"{indent}=============================")

            if subbone_offset != 0:
                read_bone(f, subbone_offset, depth + 1)
            if sibling_offset != 0:
                read_bone(f, sibling_offset, depth)

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
                read_bone(f, root_bone_offset)
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
                obj_chunk = f.read(64)
                if len(obj_chunk) < 64:
                    print("!! Incomplete Object Header read")
                else:
                    material_offset, num_materials, bone_trans_offset, unknown_f, unknown1, *rest = struct.unpack("<3I f I 12s", obj_chunk[:32])
                    print("==== Reading Object Chunk Header ====")
                    print(f"Material Offset:          0x{material_offset:08X}")
                    print(f"Num Materials:            {num_materials}")
                    print(f"BoneTransDataIndexOffset: 0x{bone_trans_offset:08X}")
                    print(f"Unknown Float:            {unknown_f}")
                    print(f"Unknown Int:              0x{unknown1:08X}")
                    print("======================================\n")
            else:
                print("ObjectInfo Offset not valid — skipping object read.\n")
                
            # -------------------------------
            # Read Materials if present
            # -------------------------------
            if material_offset != 0 and num_materials > 0:
                print(f"Reading {num_materials} Material(s) at offset 0x{material_offset:08X}:\n")
                f.seek(material_offset)

                for i in range(num_materials):
                    start_pos = f.tell()
                    mat_data = f.read(12)  # TexNameOffset (4), bLoaded (1), ColorRGBA (4), padding (3)
                    if len(mat_data) < 12:
                        print(f"Material {i}: Incomplete material struct")
                        continue

                    texname_offset, b_loaded = struct.unpack("<IB", mat_data[:5])
                    color_rgba = struct.unpack("4B", mat_data[5:9])

                    print(f"  Material {i}:")
                    print(f"    Texture Offset:    0x{texname_offset:08X}")
                    print(f"    Loaded Flag:       {b_loaded}")
                    print(f"    Diffuse RGBA:      ({color_rgba[0]}, {color_rgba[1]}, {color_rgba[2]}, {color_rgba[3]})")

                    # Save position, jump to TexNameOffset to read texture name
                    next_mat_pos = start_pos + 12
                    f.seek(texname_offset)

                    tex_bytes = bytearray()
                    while True:
                        c = f.read(1)
                        if not c or c == b'\x00':
                            break
                        tex_bytes.extend(c)

                    texname = tex_bytes.decode("ascii", errors="ignore")
                    print(f"    Texture Name:      {texname}\n")

                    # Go to next material entry
                    f.seek(next_mat_pos)
            # -------------------------------
            # Read BoneTransDataIndex if present
            # -------------------------------
            if bone_trans_index_offset != 0:
                f.seek(bone_trans_index_offset)
                bone_idx_data = f.read(8)
                if len(bone_idx_data) == 8:
                    num_bones, bone_trans_data_offset = struct.unpack("<II", bone_idx_data)

                    print(f"==== Reading BoneTransDataIndex ====")
                    print(f"Num Bones:               {num_bones}")
                    print(f"BoneTransData Offset:    0x{bone_trans_data_offset:08X}")
                    print("======================================\n")

                    if bone_trans_data_offset != 0:
                        f.seek(bone_trans_data_offset)
                        print(f"-- Reading {num_bones} Bone Inverse Matrices --")
                        for i in range(num_bones):
                            floats = struct.unpack("<16f", f.read(64))
                            print(f"  Bone {i} Inverse Matrix:")
                            for r in range(0, 16, 4):
                                print(f"    {floats[r]:.4f} {floats[r+1]:.4f} {floats[r+2]:.4f} {floats[r+3]:.4f}")
                        print()
                else:
                    print("!! BoneTransDataIndex read was incomplete.\n")
            else:
                print("No BoneTransDataIndex present.\n")

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
