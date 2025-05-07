import struct
import bpy
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper

class IMPORT_OT_read_vcs_mdl(Operator, ImportHelper):
    bl_idname = "import_scene.read_vcs_mdl"
    bl_label = "Read VCS MDL"
    filename_ext = ".mdl"
    filter_glob: bpy.props.StringProperty(default="*.mdl", options={'HIDDEN'})

    def execute(self, context):
        with open(self.filepath, "rb") as f:
            print(f"\n📂 Reading Vice City Stories-style MDL file: {self.filepath}")
            # ====================
            # Read MDL File Header
            # ====================
            header_data = f.read(0x28)
            if len(header_data) != 0x28:
                self.report({'ERROR'}, "MDL header too short.")
                return {'CANCELLED'}

            ident, version, filesize, datasize, tocoffset, tocnum, zero1, zero2, entry_start, entry_end = struct.unpack("<4sIIIIIIIii", header_data)
            ident = ident.decode('ascii')

            print("==== MDL HEADER ====")
            print(f"Identifier:       {ident}")
            print(f"Version:          {version:08X}")
            print(f"File Size:        {filesize}")
            print(f"Data Size:        {datasize}")
            print(f"TOC Offset:       0x{tocoffset:08X}")
            print(f"TOC Entry Count:  {tocnum}")
            print(f"Entry Start:      0x{entry_start:08X}")
            print(f"Entry End:        0x{entry_end:08X}")
            print("====================\n")

            # =====================
            # Read Entry Index
            # =====================
            f.seek(entry_start)
            entry_index = struct.unpack("<4i", f.read(16))
            next_entry, prev_entry, data_offset, zero = entry_index

            print("==== ENTRY INDEX ====")
            print(f"Next Entry Offset: 0x{next_entry:08X}")
            print(f"Prev Entry Offset: 0x{prev_entry:08X}")
            print(f"Data Offset:       0x{data_offset:08X}")
            print(f"Zero (padding):    {zero}")
            print("=====================\n")

            # =====================
            # Read Entry Data Block
            # =====================
            f.seek(data_offset)
            entry_data = f.read(28)
            root_bone_offset, _, _, unknown, obj_info_start, obj_info_end, _ = struct.unpack("<7i", entry_data)

            print("==== ENTRY DATA ====")
            print(f"Root Bone Offset:      0x{root_bone_offset:08X}")
            print(f"First ObjectInfo:      0x{obj_info_start:08X}")
            print(f"Last ObjectInfo:       0x{obj_info_end:08X}")
            print(f"Unknown Field:         0x{unknown:08X}")
            print("======================\n")

            # =============================
            # Traverse ObjectInfo Chunks
            # =============================
            current_offset = obj_info_start
            visited_offsets = set()
            obj_index = 0

            while current_offset != 0 and current_offset not in visited_offsets:
                visited_offsets.add(current_offset)
                f.seek(current_offset)
                data = f.read(28)
                if len(data) < 28:
                    print(f"!! Incomplete ObjectInfo at 0x{current_offset:08X}")
                    break

                next_offset, prev_offset, bone_offset, data_offset, root_offset, zero, const_three = struct.unpack("<7i", data)

                print(f"---- ObjectInfo #{obj_index} ----")
                print(f"Offset:             0x{current_offset:08X}")
                print(f"Next:               0x{next_offset:08X}")
                print(f"Prev:               0x{prev_offset:08X}")
                print(f"Parent Bone Offset: 0x{bone_offset:08X}")
                print(f"Object Data Offset: 0x{data_offset:08X}")
                print(f"Root Entry Offset:  0x{root_offset:08X}")
                print(f"Zero Field:         0x{zero:08X}")
                print(f"Always 3?:          0x{const_three:08X}")
                print("------------------------------\n")

                current_offset = next_offset
                obj_index += 1

            print(f"✅ Completed parsing {obj_index} ObjectInfos.")
        return {'FINISHED'}

def menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_read_vcs_mdl.bl_idname, text="Import VCS MDL (.mdl)")

def register():
    bpy.utils.register_class(IMPORT_OT_read_vcs_mdl)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.utils.unregister_class(IMPORT_OT_read_vcs_mdl)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

if __name__ == "__main__":
    register()
