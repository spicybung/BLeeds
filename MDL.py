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
        with open(self.filepath, "rb") as f:
            data = f.read(0x28)  # First 40 bytes of MDLHeader
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
            # Read First EntryIndex
            # -------------------------------
            f.seek(first_entry_offset)
            entry_index_data = f.read(16)  # EntryIndex is 4 ints = 16 bytes
            entry_index = struct.unpack("<iiii", entry_index_data)

            print("==== Reading First EntryIndex ====")
            print(f"Next Entry Offset:   0x{entry_index[0]:08X}")
            print(f"Prev Entry Offset:   0x{entry_index[1]:08X}")
            print(f"Entry Data Offset:   0x{entry_index[2]:08X}")
            print(f"Zero Field:          {entry_index[3]}")
            print("==================================\n")

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
