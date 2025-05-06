import struct
import bpy
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper

class IMPORT_OT_read_mdl_header(Operator, ImportHelper):
    bl_idname = "import_scene.read_mdl_header"
    bl_label = "Import MDL and Read Header"
    filename_ext = ".mdl"
    filter_glob: bpy.props.StringProperty(default="*.mdl", options={'HIDDEN'})

    def read_bone(self, f, offset, depth=0):
        indent = "  " * depth
        f.seek(offset)
        bone_data = f.read(24)
        bone = struct.unpack("<6i", bone_data)

        sibling_offset = bone[1]
        parent_offset = bone[2]
        subbone_offset = bone[4]
        anim_bone_index_offset = bone[5]

        print(f"{indent}==== Bone at 0x{offset:08X} ====")
        print(f"{indent}Sibling Offset:         0x{sibling_offset:08X}")
        print(f"{indent}Parent Offset:          0x{parent_offset:08X}")
        print(f"{indent}SubBone Offset:         0x{subbone_offset:08X}")
        print(f"{indent}AnimBoneDataIdx Offset: 0x{anim_bone_index_offset:08X}")
        print(f"{indent}=============================")

        if subbone_offset > 0:
            self.read_bone(f, subbone_offset, depth + 1)

        if sibling_offset > 0:
            self.read_bone(f, sibling_offset, depth)

    def execute(self, context):
        with open(self.filepath, "rb") as f:
            # Step 1: Read MDLHeader
            data = f.read(0x28)
            header = struct.unpack("<4sIIIIIIIii", data)
            signature = header[0].decode("ascii")
            first_entry_offset = header[8]

            # -------------------------------
            # Read MDL Header
            # Signature is determined by ModelInfo struct
            # i.e PMLC = Ped Model Liberty City
            # -------------------------------

            print("\n==== Reading MDL Header ====")
            print(f"Signature:           {signature}")          # ModelInfo struct
            print(f"Version:             {header[1]:08X}")
            print(f"File Size:           {header[2]} bytes")    # Physical size
            print(f"Data Size:           {header[3]} bytes")
            print(f"Offset Table Start:  0x{header[4]:08X}")
            print(f"Num Table Entries:   {header[5]}")
            print(f"Zero1:               {header[6]}")          # Padding
            print(f"Zero2:               {header[7]}")          # Padding
            print(f"First Entry Offset:  0x{first_entry_offset:08X}")
            print(f"Last Entry Offset:   0x{header[9]:08X}")
            print("============================\n")

            # -------------------------------
            # Read EntryIndex
            # -------------------------------
            f.seek(first_entry_offset)
            entry_index = struct.unpack("<iiii", f.read(16))
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
            entry = struct.unpack("<7i", f.read(0x1C))

            root_bone_offset = entry[0]
            first_obj_info_offset = entry[4]
            last_obj_info_offset = entry[5]
            unknown = entry[3]

            print("==== Reading Entry ====")
            print(f"Root Bone Offset:         0x{root_bone_offset:08X}")
            print(f"First ObjectInfo Offset:  0x{first_obj_info_offset:08X}")
            print(f"Last ObjectInfo Offset:   0x{last_obj_info_offset:08X}")
            print(f"Unknown Field:            0x{unknown:08X}")
            print("==================================\n")

            # -------------------------------
            # Read Root Boone & Traverse
            # -------------------------------
            if root_bone_offset > 0:
                print("Traversing Bone Hierarchy:")
                self.read_bone(f, root_bone_offset)
            else:
                print("Root Bone Offset is 0 — skipping root bone read.\n")

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
