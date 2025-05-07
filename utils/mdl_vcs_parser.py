import os
import struct
import bpy
from mathutils import Matrix, Vector
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper

class IMPORT_OT_read_vcs_mdl_header(Operator, ImportHelper):
    bl_idname = "import_scene.read_vcs_mdl_header"
    bl_label = "Import VCS MDL and Read Header"
    filename_ext = ".mdl"
    filter_glob: bpy.props.StringProperty(default="*.mdl", options={'HIDDEN'})

    def execute(self, context):
        bone_map = {}

        def read_element_group(f, offset):
            f.seek(offset)
            raw = f.read(12)
            if len(raw) < 12:
                print(f"!! Failed to read RslElementGroup at 0x{offset:08X}")
                return 0
            rsl_type, subtype, flags, priv_flags = struct.unpack("4B", raw[:4])
            next_ptr, prev_ptr = struct.unpack("<2I", raw[4:12])

            print("\n🎯 RslElementGroup")
            print(f"Type:         {rsl_type}")
            print(f"Subtype:      {subtype}")
            print(f"Flags:        {flags}")
            print(f"PrivateFlags: {priv_flags}")
            print(f"First Element Link:  0x{next_ptr:08X}")
            print(f"Last Element Link:   0x{prev_ptr:08X}")

            return next_ptr, offset  # link pointer and the group start for circular test

        def read_element(f, offset):
                f.seek(offset)
                raw = f.read(34)
                if len(raw) < 34:
                    print(f"❌ RslElement block too short at 0x{offset:08X}")
                    return None, None

                print(f"\n📄 Raw RslElement @ 0x{offset:08X}: {raw.hex(' ', 4)}")

                obj_type, obj_subtype, flags, priv_flags = struct.unpack("4B", raw[:4])
                geometry_ptr = struct.unpack("<I", raw[4:8])[0]
                clump_ptr = struct.unpack("<I", raw[12:16])[0]
                link_next, link_prev = struct.unpack("<2I", raw[16:24])
                render_cb = struct.unpack("<I", raw[24:28])[0]
                model_info_id, vis_id_flag = struct.unpack("<hH", raw[28:32])
                hier_ptr = struct.unpack("<I", raw[32:36])[0] if len(raw) >= 36 else 0  # safety for overread

                print(f"\n🔶 RslElement")
                print(f"Type/Subtype:          {obj_type}/{obj_subtype}")
                print(f"Flags:                 {flags}")
                print(f"Private Flags:         {priv_flags}")
                print(f"Geometry Ptr:          0x{geometry_ptr:08X}")
                print(f"Clump (ElementGroup):  0x{clump_ptr:08X}")
                print(f"Link Next:             0x{link_next:08X}")
                print(f"Link Prev:             0x{link_prev:08X}")
                print(f"RenderCB Ptr:          0x{render_cb:08X}")
                print(f"Model Info ID:         {model_info_id}")
                print(f"Vis ID Flag:           {vis_id_flag}")
                print(f"Anim Tree Ptr:         0x{hier_ptr:08X}")

                return link_next, offset


        with open(self.filepath, "rb") as f:
            header_data = f.read(0x30)
            if len(header_data) != 0x30:
                self.report({'ERROR'}, "MDL header too short.")
                return {'CANCELLED'}

            ident, version, filesize, datasize, tocoffset, tocnum, zero1, zero2, entry_end, entry_start, material, material2 = struct.unpack("<4sIIIIIIIiiii", header_data)
            ident = ident.decode('ascii')

            print("==== Reading MDL Header ====")
            print(f"Signature:           {ident}")
            print(f"Version:             {version:08X}")
            print(f"File Size:           {filesize} bytes")
            print(f"Data Size:           {datasize} bytes")
            print(f"Offset Table Start:  0x{tocoffset:08X}")
            print(f"Num Table Entries:   {tocnum}")
            print(f"Data Size (again):   0x{zero1:08X}")
            print(f"Allocated Mem Size:  0x{zero2:08X}")
            print(f"First Entry Offset:  0x{entry_start:08X}")
            print(f"Last Entry Offset:   0x{entry_end:08X}")
            print(f"Material Offset:   0x{material:08X}")
            print(f"Unknown Offset 1:   0x{material2:08X}")
            print("============================\n")


            # ================================
            # === Read VCS-Style Materials ===
            # ================================
            f.seek(material)
            print("==== Reading Materials at 0x%08X ====" % material)

            for i in range(16):  
                entry_offset = f.tell()
                entry = f.read(16)
                if len(entry) < 16:
                    print(f"Reached end of material data at {entry_offset:08X}")
                    break

                texname_ptr, r, g, b, a, shader_flags, unused1 = struct.unpack("<I4B2I", entry)

                # Store current pointer
                current_pos = f.tell()

                # Go read the string
                f.seek(texname_ptr)
                name_bytes = bytearray()
                while True:
                    byte = f.read(1)
                    if byte == b'\x00' or byte == b'':
                        break
                    name_bytes.append(byte[0])
                tex_name = name_bytes.decode('ascii', errors='replace')

                print(f"\n🎨 Material[{i}] @ 0x{entry_offset:08X}")
                print(f"Texture Ptr:   0x{texname_ptr:08X}")
                print(f"Name:          {tex_name}")
                print(f"Color RGBA:    ({r}, {g}, {b}, {a})")
                print(f"Shader Flags:  0x{shader_flags:08X}")
                print(f"Unused Data:   0x{unused1:08X}")

                # Looks like we've found the Material struct.
                # Return to where we left off
                f.seek(current_pos)



        return {'FINISHED'}

def menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_read_vcs_mdl_header.bl_idname, text="Read VCS MDL (.mdl)")

def register():
    bpy.utils.register_class(IMPORT_OT_read_vcs_mdl_header)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.utils.unregister_class(IMPORT_OT_read_vcs_mdl_header)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

if __name__ == "__main__":
    register()