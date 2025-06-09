import bpy
import struct

from bpy_extras.io_utils import ImportHelper
from bpy.types import Operator
from bpy.props import StringProperty


# See info: https://gtamods.com/wiki/Relocatable_chunk
# and: https://gtamods.com/wiki/Leeds_Engine
# also: https://gtamods.com/wiki/MDL

class ImportMDLOperator(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.mdl_stories"
    bl_label = "Import LCS/VCS .MDL"
    bl_description = "Import a GTA LCS/VCS .MDL file"
    filename_ext = ".mdl"
    filter_glob: StringProperty(default="*.mdl", options={'HIDDEN'})

    def execute(self, context):
        return self.read_mdl(self.filepath)

    def read_mdl(self, filepath):
        try:
            with open(filepath, "rb") as f:  # Read the file as bytes
                print(f"✔ Opened: {filepath}")

                scaleFactor = 100.0 # for bones
                
                def read_matrix3x4(f):
                    row1 = struct.unpack("<3f", f.read(12))
                    f.read(4)  # skip padding
                    row2 = struct.unpack("<3f", f.read(12))
                    f.read(4)
                    row3 = struct.unpack("<3f", f.read(12))
                    f.read(4)
                    row4 = struct.unpack("<3f", f.read(12)) # 3 floats - 12 bytes per row
                    f.read(4)
                    return row1, row2, row3, row4   # Read frame/bone transformation matrix

                def read_u32():
                    return struct.unpack("<I", f.read(4))[0]  # Read unsigned 32bit integer
                
                def read_f32():
                    return struct.unpack("<f", f.read(4))[0]  # Read float-32
                
                def jump_and_read_u32(offset=4):
                    f.seek(offset, 1)  # Jump ahead by offset bytes relative to current position
                    return struct.unpack("<I", f.read(4))[0]


                # --- Header parsing ---
                magic = f.read(4)
                if magic != b'ldm\x00': # .mdl in reverse endianness
                    self.report({'ERROR'}, "Not a valid MDL header.")
                    return {'CANCELLED'}
                print(f"✔ Header: {magic.decode(errors='ignore')!r}")

                shrink = read_u32()  # 1 if GTAG resource image, else always 0(unused)
                file_len = read_u32()         # physical fiile size
                local_numTable = read_u32()   # local entries numtable
                global_numTable = read_u32()  # global entries numtable 
                numEntries = read_u32()  # number of entries
                ptr2_before_tex = read_u32()
                allocMem = read_u32()  # amount of memory allocated to file
                _ = read_u32()  # skip D-WORD 0x1D10, dunno what this does, bud.
                top_level_ptr = read_u32()  # pointer at 0x24

                print(f"File Size: 0x{file_len}")
                print(f"Local numTable: 0x{local_numTable:X}, Global numTable: 0x{global_numTable:X}")
                print(f"Number of entries: 0x{numEntries}")
                print(f"Ptr2BeforeTexNameList: 0x{ptr2_before_tex:X}")
                print(f"Allocated memory: 0x{allocMem}")
                print(f"Top-level ptr or magic value: 0x{top_level_ptr:X}")

                if top_level_ptr >= file_len:
                    print("❌ Top-level pointer is beyond file size.")
                    return {'CANCELLED'}

                f.seek(top_level_ptr)
                top_magic = read_u32()
                print(f"Magic at top-level ptr: 0x{top_magic:X}")

                # --- Section & import type detection ---
                section_type = 0
                import_type = 0

                LCSCLUMP = 0x00000002
                LCSATOMIC1 = 0x01050001
                LCSATOMIC2 = 0x01000001
                VCSCLUMP = 0x0000AA02
                VCSATOMIC1 = 0x0004AA01
                VCSATOMIC2 = 0x0004AA01

                if top_magic in (LCSCLUMP, VCSCLUMP):
                    section_type = 7
                    import_type = 1 if top_magic == LCSCLUMP else 2
                elif top_magic in (LCSATOMIC1, LCSATOMIC2, VCSATOMIC1, VCSATOMIC2):
                    section_type = 2
                    import_type = 1 if top_magic in (LCSATOMIC1, LCSATOMIC2) else 2
                else:
                    print(f"❌ Unrecognized pointer content: 0x{top_magic:X}")

                print(f"Section Type: {section_type}")
                print(f"Import Type: {import_type} (0=Unknown, 1=LCS, 2=VCS)")

                # --- Section 7 handling (Clump) ---
                if section_type == 7:

                    f.seek(-4, 1)

                    print("✔ Detected Section Type 7: Clump")

                    clump_start = f.tell()
                    print(f"Clump found at: 0x{clump_start:X}")

                    clump_id = read_u32()
                    first_frame = read_u32()
                    first_atomic_pos = read_u32()

                    print(f"firstFrame: 0x{first_frame:X}")
                    print(f"firstAtomicPos: 0x{first_atomic_pos:X}")

                    atomic_seek_pos = first_atomic_pos - 0x1C
                    print(f"→ Seeking to atomic at: 0x{atomic_seek_pos:X}")

                    if atomic_seek_pos >= file_len:
                        print("❌ Atomic pointer is beyond file size.")
                        return {'CANCELLED'}

                    f.seek(atomic_seek_pos)

                    # --- Update parsing state to section type 2 if successful---
                    section_type = 2
                    atomics_count = 1
                    cur_atomic = 1

                    print("✔ Begin reading Section Type 2")
                    print("--- End of header parsing ---")

                # --- Section 2 handling (Atomic) ---
                if section_type == 2: 
                    print("✔ Detected Section Type 2: Atomic")

                    atomics = []
                    frame_data_list = []
                    dummies = []
                    bone_list = []
                    frame_ptr_list = []

                    actor_mdl = False
                    root_bone_link = not actor_mdl  # dun goofed here pretty sure...
                    cur_atomic_index = 1

                    atomic_start = f.tell()
                    print(f"Atomic section begins at: 0x{atomic_start:X}")

                    _ = read_u32()  # Unknown
                    
                    f.seek(20, 1)
                    
                    frame_ptr = read_u32()
                    print(f"frame_ptr: 0x{frame_ptr:X}")
                    
                    f.seek(-8, 1)

                    geom_ptr = read_u32()
                    
                    f.seek(4, 1)    # seeking back and forth feels like violating the MDL file
                    
                    clump_ptr = read_u32()
                    link_ptr = read_u32()
                    
                    
                    render_cb = read_u32()  # render callback
                    
                    
                    model_info_id = struct.unpack("<h", f.read(2))[0]
                    
                    
                    vis_id_flag = struct.unpack("<H", f.read(2))[0]
                    hierarchy_ptr = read_u32()
                    
                    print(f"geom_ptr:      0x{geom_ptr:X}")
                    print(f"clump_ptr:     0x{clump_ptr:X}")
                    print(f"link_ptr:      0x{link_ptr:X}")
                    print(f"render_cb:     0x{render_cb:X}")
                    print(f"model_info_id: {model_info_id}")
                    print(f"vis_id_flag:   0x{vis_id_flag:X}")
                    print(f"hierarchy_ptr: 0x{hierarchy_ptr:X}")

                    return_pos = f.tell()
                    cur_frame_ptr = frame_ptr
                    first_frame = cur_frame_ptr
                    parent_dummy = None
                    
                    frames = []
                    
                    f.seek(cur_frame_ptr + 4)
                    print(f"cur_frame_ptr:      0x{cur_frame_ptr + 4:X}")
                    new_frame_ptr = read_u32()
                    print(f"new_frame_ptr:      0x{new_frame_ptr + 12:X}")
                    
                    row1, row2, row3, row4 = read_matrix3x4(f)

                    transform_matrix = (row1, row2, row3, row4)
                    
                    f.seek(new_frame_ptr + 12 + 0x98)
                    if import_type == 2:
                        f.seek(4, 1) # skip extra 4 bytes if VCS!
                        name_ptr = struct.unpack("<I", f.read(4))[0]
                    
                    print(f"name_ptr: 0x{name_ptr:X}")
                    
                    
                    print("✔ Frame Transform Matrix:")
                    print(f"  Row 1: {row1[0]:.6f}, {row1[1]:.6f}, {row1[2]:.6f}")
                    print(f"  Row 2: {row2[0]:.6f}, {row2[1]:.6f}, {row2[2]:.6f}")
                    print(f"  Row 3: {row3[0]:.6f}, {row3[1]:.6f}, {row3[2]:.6f}")
                    print(f"  Row 4: {row4[0]:.6f}, {row4[1]:.6f}, {row4[2]:.6f}")


                    

                      
                    return {'FINISHED'}



        except Exception as e:
            self.report({'ERROR'}, f"Error reading file: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}


def menu_func_import(self, context):
    self.layout.operator(ImportMDLOperator.bl_idname, text="GTA .MDL (LCS/VCS)")


def register():
    bpy.utils.register_class(ImportMDLOperator)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.utils.unregister_class(ImportMDLOperator)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)


if __name__ == "__main__":
    register()