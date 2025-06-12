bl_info = {
    "name": "Import LCS/VCS .MDL (Fixed)",
    "author": "spicybung",
    "version": (0, 0, 1),
    "blender": (2, 80, 0),
    "location": "File > Import > GTA .MDL (LCS/VCS)",
    "description": "Import LCS/VCS .MDL",
    "category": "Import-Export"
}

import bpy
import struct
from bpy_extras.io_utils import ImportHelper
from bpy.types import Operator
from bpy.props import StringProperty




class ImportMDLOperator(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.mdl_fixed"
    bl_label = "Import LCS/VCS .MDL"
    bl_description = "Import a GTA LCS/VCS .MDL file"
    filename_ext = ".mdl"
    filter_glob: StringProperty(default="*.mdl", options={'HIDDEN'})

    def execute(self, context):
        return self.read_mdl(self.filepath)

    def read_mdl(self, filepath):
        try:
            with open(filepath, "rb") as f:  # Read file as bytes
                print(f"✔ Opened: {filepath}")

                scaleFactor = 100.0 

                def read_frame_chain(f, start_ptr, import_type, scale_factor):
                    """Parses a chain of frames starting at frame_ptr, creating Blender empties and returning them."""
                    bones = []
                    visited_ptrs = set()
                    current_ptr = start_ptr

                    while current_ptr != 0 and current_ptr not in visited_ptrs:
                        visited_ptrs.add(current_ptr)

                        f.seek(current_ptr + 8)
                        _ = read_u32()  # unknown

                        # Read 3x3 rotation matrix and translation vector
                        rot1 = (read_f32(), read_f32(), read_f32()); _ = read_u32()
                        rot2 = (read_f32(), read_f32(), read_f32()); _ = read_u32()
                        rot3 = (read_f32(), read_f32(), read_f32()); _ = read_u32()
                        trans = (read_f32(), read_f32(), read_f32()); _ = read_u32()

                        trans = tuple(coord * (scale_factor / 100.0) for coord in trans)

                        if import_type == 2:
                            f.seek(4, 1)

                        bone_name_ptr = read_u32()
                        name = "unnamed"
                        if bone_name_ptr > 0:
                            f.seek(bone_name_ptr)
                            name_bytes = bytearray()
                            while True:
                                c = f.read(1)
                                if not c or c == b'\x00':
                                    break
                                name_bytes.append(c[0])
                            name = name_bytes.decode("utf-8", errors="ignore")

                        # Create empty object in Blender
                        empty = bpy.data.objects.new(name, None)
                        empty.empty_display_type = 'ARROWS'
                        empty.location = trans
                        bpy.context.collection.objects.link(empty)
                        bones.append(empty)

                        # Get next pointer from current frame
                        f.seek(current_ptr + 0x90)
                        next_ptr = read_u32()

                        current_ptr = next_ptr

                    print(f"✔ Imported {len(bones)} bones/frames.")
                    return bones


                def read_u32():
                    return struct.unpack("<I", f.read(4))[0]  # Read unsigned 32bit integer
                
                def read_f32():
                    return struct.unpack("<f", f.read(4))[0]  # Read float-32
                
                def jump_and_read_u32(offset=4):
                    f.seek(offset, 1)  # Jump ahead by 'offset' bytes relative to current position
                    return struct.unpack("<I", f.read(4))[0]


                # --- Header parsing ---
                magic = f.read(4)
                if magic != b'ldm\x00': # .mdl in reverse endianness
                    self.report({'ERROR'}, "Invalid MDL header.")
                    return {'CANCELLED'}
                print(f"✔ Header: {magic.decode(errors='ignore')!r}")

                shrink = read_u32()  # loaded by Leeds Engine but seemingly unused - maybe used later?
                file_len = read_u32()         # physical fiile size
                local_numTable = read_u32()   # local entries numtable
                global_numTable = read_u32()  # global entries numtable 
                numEntries = read_u32()  # number of entries
                ptr2_before_tex = read_u32()
                allocMem = read_u32()  # amount of memory allocated to file
                _ = read_u32()  # skip D-WORD 0x1D10
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

                    # Update parsing state as if in section type 2
                    section_type = 2
                    atomics_count = 1
                    cur_atomic = 1

                    print("✔ Jumped to embedded atomic (Section 2 emulation)")
                    print("--- End of header parsing ---")

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
                    
                    f.seek(22, 1)
                    
                    frame_ptr = read_u32()
                    print(f"frame_ptr: 0x{frame_ptr:X}")

                    bones = read_frame_chain(f, frame_ptr, import_type, scaleFactor)
                    
                    
                    return {'FINISHED'}
            
            if section_type == 3:
                    print(f"✔ Parsing Section 3 (Geometry) at offset {f.tell():X}")

                    _ = read_u32()
                    _ = read_u32()
                    _ = read_u32()

                    material_list_ptr = read_u32()
                    material_count = read_u32()

                    materials = []

                    if material_count > 0:
                        old_pos = f.tell()
                        f.seek(material_list_ptr)

                        for _ in range(material_count):
                            mat_ptr = read_u32()
                            old_mat_pos = f.tell()

                            f.seek(mat_ptr)
                            tex_ptr = read_u32()

                            material = {'texture': '', 'rgba': 0, 'specular': 0.0}

                            if tex_ptr != 0:
                                temp_pos = f.tell()
                                f.seek(tex_ptr)
                                texture_bytes = bytearray()
                                while True:
                                    b = f.read(1)
                                    if b == b'\x00' or not b:
                                        break
                                    texture_bytes.append(b[0])
                                material['texture'] = texture_bytes.decode('utf-8', errors='ignore')
                                f.seek(temp_pos)

                            material['rgba'] = read_u32()
                            _ = read_u32()
                            spec_ptr = read_u32()

                            if spec_ptr != 0:
                                temp_pos = f.tell()
                                f.seek(spec_ptr)
                                _ = read_u32()
                                _ = read_u32()
                                material['specular'] = read_f32()
                                f.seek(temp_pos)

                            f.seek(old_mat_pos)
                            materials.append(material)

                        f.seek(old_pos)

                    for _ in range(13):
                        _ = read_u32()

                    x_scale = read_f32()
                    y_scale = read_f32()
                    z_scale = read_f32()

                    overall_translation = (
                        read_f32(),
                        read_f32(),
                        read_f32()
                    )

                    overall_translation = tuple(coord * (scaleFactor / 100.0) for coord in overall_translation)

                    part_offsets = []
                    part_materials = []

                    temp = read_u32()
                    temp_check = temp & 0x60000000

                    while temp_check != 0x60000000:
                        for _ in range(6):
                            _ = read_u32()

                        temp = read_u32()
                        part_offsets.append(temp)

                        _ = struct.unpack('<H', f.read(2))[0]
                        material_idx = struct.unpack('<H', f.read(2))[0]
                        part_materials.append(material_idx)

                        _ = read_u32()
                        _ = read_u32()
                        _ = read_u32()

                        temp = read_u32()
                        temp_check = temp & 0x60000000

                    f.seek(-4, 1)

                    print("✔ Geometry Parts Sub-Section Reached")
                    
                    geo_start = f.tell()
                    print(f"→ Geometry start: 0x{geo_start:X}")

                    strips = []
                    strip_count = 0

                    while True:
                        cur_part = 0
                        cur_pos = f.tell()

                        for i, offset in enumerate(part_offsets):
                            if cur_pos >= geo_start + offset:
                                cur_part += 1
                            else:
                                break

                        temp = read_u32()
                        temp_check = temp & 0x60000000

                        # Skip until we hit the 0x60000000 block
                        while temp_check != 0x60000000:
                            for _ in range(11):
                                _ = read_u32()
                            temp = read_u32()
                            temp_check = temp & 0x60000000

                        f.seek(-4, 1)

                        # If we haven't yet hit a 6C018000 tag, skip 4 unknowns
                        for _ in range(4):
                            _ = read_u32()

                        tri_strip_start = f.tell()
                        print(f"→ Tri-strip start: 0x{tri_strip_start:X}")

                        for _ in range(12):
                            _ = read_u32()

                        _ = struct.unpack('<H', f.read(2))[0]
                        cur_strip_vert_count = struct.unpack('<B', f.read(1))[0]
                        _ = struct.unpack('<B', f.read(1))[0]  # Unknown byte

                        verts = []
                        faces = []
                        valid_faces_indices = []

                        cur_strip_face_count = 0

                        for i in range(cur_strip_vert_count):
                            x = struct.unpack('<h', f.read(2))[0]
                            y = struct.unpack('<h', f.read(2))[0]
                            z = struct.unpack('<h', f.read(2))[0]

                            vert = (
                                (x * x_scale * scaleFactor / 100.0) + overall_translation[0],
                                (y * y_scale * scaleFactor / 100.0) + overall_translation[1],
                                (z * z_scale * scaleFactor / 100.0) + overall_translation[2],
                            )
                            verts.append(vert)

                            if i > 1:
                                cur_strip_face_count += 1
                                # triangle strip face order (flip every other face)
                                if i % 2 == 0:
                                    face = (i - 2, i - 1, i)
                                else:
                                    face = (i - 1, i - 2, i)
                                faces.append(face)
                                valid_faces_indices.append(True)

                        if cur_strip_vert_count % 2 == 1:
                            _ = struct.unpack('<h', f.read(2))[0]

                        # store or print the strip
                        strips.append({
                            'verts': verts,
                            'faces': faces,
                            'material_index': part_materials[cur_part] if cur_part < len(part_materials) else -1
                        })

                        strip_count += 1

                        # stop
                        if f.tell() >= file_len:
                            break

                    print(f"✔ Parsed {strip_count} triangle strips")

            #  Section 4(F0) type handling ()        
            if section_type == 4:



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