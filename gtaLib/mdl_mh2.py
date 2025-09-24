# BLeeds - Scripts for working with R* Leeds (GTA Stories, Manhunt 2, etc) formats in Blender
# Author: SpicyBung
# Years: 2025 - 

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

from bpy.types import Operator
from bpy.props import StringProperty
from bpy_extras.io_utils import ImportHelper

#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
#   This script is for Manhunt2 .MDLs, the file format for actors & props
#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
# - Script resources:
# • https://gtamods.com/wiki/Leeds_Engine
# • https://manhuntgame.fandom.com/wiki/MDL (specifications about Manhunt 2 MDLs)
# • https://web-archive-org.translate.goog/web/20180729204205/http://gtamodding.ru/wiki/CHK?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (MH2 textures)
# - Mod resources/cool stuff:
# • 

#######################################################
class read_mh2:

    #######################################################
    def __init__(self, path: str, context, collection_name: str | None = None):
        self.path = path
        self.context = context
        self.collection_name = collection_name

        self.file = None
        self.stem = os.path.splitext(os.path.basename(path))[0]
        self.collection = None
        self.armature_obj = None
        self.bone_map = {}          # offset -> dict(name, parent_offset, matrix)
        self.object_infos = []      # list[(info_offset, object_data_offset)]

    def run(self) -> bool:
        with open(self.path, "rb") as f:
            self.file = f
            self._read_header()
            self._read_entry()
            self._read_bones()
            self._build_armature()
            self._read_object_infos()
            self._read_objects_and_make_meshes()
        return True

    #######################################################

    def _read_header(self):
        f = self.file
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

        f.seek(entry_data_offset)
        
        coll_name = self.collection_name or f"MH2_{self.stem}"
        coll = bpy.data.collections.get(coll_name) or bpy.data.collections.new(coll_name)
        if coll.name not in {c.name for c in self.context.scene.collection.children}:
            self.context.scene.collection.children.link(coll)
        self.collection = coll

    def _read_entry(self):
        f = self.file
        # 7 ints (28 bytes)
        entry = struct.unpack("<7i", f.read(0x1C))
        self.root_bone_offset   = entry[0]
        self.bone_trans_idx_offs= entry[2]
        self.first_objinfo_offs = entry[4]
        self.last_objinfo_offs  = entry[5]

    def _read_bones(self):
        if not self.root_bone_offset:
            return
        self._read_bone_block(self.root_bone_offset)

    def _build_armature(self):
        arm = bpy.data.armatures.new(f"{self.stem}_Armature")
        arm_obj = bpy.data.objects.new(arm.name, arm)
        self.collection.objects.link(arm_obj)

        bpy.context.view_layer.objects.active = arm_obj
        bpy.ops.object.mode_set(mode="EDIT")

        edits = {}
        for off, b in self.bone_map.items():
            eb = arm.edit_bones.new(b["name"] or f"Bone_{off:08X}")
            head = b["matrix"].to_translation()
            tail = head + b["matrix"].to_3x3() @ Vector((0, 0.05, 0))
            eb.head, eb.tail = head, tail
            edits[off] = eb

        for off, b in self.bone_map.items():
            p = b["parent_offset"]
            if p in edits:
                edits[off].parent = edits[p]

        bpy.ops.object.mode_set(mode="OBJECT")
        self.armature_obj = arm_obj

    def _read_object_infos(self):
        f = self.file
        cur = self.first_objinfo_offs or self.last_objinfo_offs
        seen = set()
        infos = []

        while cur and cur not in seen:
            seen.add(cur)
            f.seek(cur)
            raw = f.read(28)
            if len(raw) < 28:
                break
            next_off, prev_off, parent_bone_off, object_data_off, _x, _y, _z = struct.unpack("<7i", raw)
            infos.append((cur, object_data_off))
            cur = next_off if next_off != 0 and next_off != cur else 0

        self.object_infos = infos

    def _read_objects_and_make_meshes(self):
        for idx, (_, obj_off) in enumerate(self.object_infos):
            self._read_object(idx, obj_off)

    #######################################################

    def _read_bone_block(self, offset: int):
        f = self.file
        f.seek(offset)
        blk = f.read(192)
        if len(blk) < 192:
            return

        # first 24 bytes contain several uint32; we skip the first u32 then read five
        sibling_offset, parent_ptr, _unk, subbone_offset, anim_data_idx_offset = \
            struct.unpack_from("<xI I I I I", blk, 0)

        # name at [24:64]
        name = blk[24:64].split(b"\x00")[0].decode("ascii", errors="replace")

        # world matrix at [128:192], stored row-major; transpose to Blender and convert Y-up -> Z-up
        raw = struct.unpack_from("<16f", blk, 128)
        M = Matrix((
            (raw[0], raw[4],  raw[8],  raw[12]),
            (raw[1], raw[5],  raw[9],  raw[13]),
            (raw[2], raw[6],  raw[10], raw[14]),
            (raw[3], raw[7],  raw[11], raw[15]),
        ))
        M = self._y_up_to_z_up(M)

        self.bone_map[offset] = {
            "name": name,
            "parent_offset": parent_ptr,
            "matrix": M,
        }

        if subbone_offset:
            self._read_bone_block(subbone_offset)
        if sibling_offset:
            self._read_bone_block(sibling_offset)

    #######################################################

    def _read_object(self, idx: int, obj_off: int):
        f = self.file
        f.seek(obj_off)
        head = f.read(180)
        if len(head) < 180:
            return

        (
            material_offset, num_materials, bone_trans_offset, unknown_f, unknown1,
            ux, uy, uz, model_chunk_flag, model_chunk_size,
            zero, numMaterialIDs, numFaceIndex,
            bs_x, bs_y, bs_z, bs_radius,
            scale_x, scale_y, scale_z,
            num_vertices, zero2_0, zero2_1, zero2_2,
            per_vertex_size, *rest
        ) = struct.unpack("<3I f I 3f 2I 3I 3f f 3f I 3I I 11I I 8I", head)

        vertex_element_type = rest[11]

        # faces
        f.seek(obj_off + 180 + (numMaterialIDs * 0x30))
        faces = []
        for _ in range(numFaceIndex // 3):
            tri = f.read(6)
            if len(tri) < 6:
                break
            a, b, c = struct.unpack("<3H", tri)
            if a < num_vertices and b < num_vertices and c < num_vertices:
                faces.append((a, b, c))

        # vertices
        vtx_off = obj_off + 180 + (numMaterialIDs * 32) + ((numFaceIndex // 3) * 6)
        f.seek(vtx_off + 36)
        verts, uvs = self._read_vertices_by_type(vertex_element_type, num_vertices)

        # materials
        mats = []
        if material_offset and num_materials > 0:
            f.seek(material_offset)
            for _ in range(num_materials):
                row = f.read(16)
                if len(row) < 16:
                    break
                tex_off, loaded = struct.unpack("<IB", row[:5])
                color = struct.unpack("4B", row[5:9])
                tex_name = self._read_c_string_at(tex_off) if tex_off else ""
                mats.append({"tex_name": tex_name, "color": color, "loaded": loaded})

        self._make_mesh(f"{self.stem}_{idx}", [tuple(v) for v in verts], faces, uvs, mats)

    #######################################################

    def _read_c_string_at(self, offset: int) -> str:
        f = self.file
        cur = f.tell()
        f.seek(offset)
        s = bytearray()
        while True:
            b = f.read(1)
            if not b or b == b"\x00":
                break
            s += b
        f.seek(cur)
        return s.decode("ascii", errors="replace")

    def _y_up_to_z_up(self, M: Matrix) -> Matrix:
        return M @ Matrix.Rotation(-3.14159265 / 2, 4, "X")

    def _read_vertices_by_type(self, vtype: int, count: int):
        f = self.file
        verts = []
        uvs = None

        for _ in range(count):
            if vtype == 0x52:
                data = f.read(24)
                pos = struct.unpack_from("<3f", data, 0)
                verts.append(pos)

            elif vtype == 0x152:
                data = f.read(32)
                pos = struct.unpack_from("<3f", data, 0)
                uv = struct.unpack_from("<2f", data, 22)
                verts.append(pos)
                if uvs is None:
                    uvs = []
                uvs.append(uv)

            elif vtype in (0x115E, 0x125E, 0x252):
                if vtype == 0x115E:
                    data = f.read(52)
                    pos = struct.unpack_from("<3f", data, 0)
                    uv = struct.unpack_from("<2f", data, 42)
                elif vtype == 0x125E:
                    data = f.read(60)
                    pos = struct.unpack_from("<3f", data, 0)
                    uv = struct.unpack_from("<2f", data, 42)
                else:  # 0x252
                    data = f.read(40)
                    pos = struct.unpack_from("<3f", data, 0)
                    uv = struct.unpack_from("<2f", data, 22)
                verts.append(pos)
                if uvs is None:
                    uvs = []
                uvs.append(uv)

            else:
                raise ValueError(f"Unknown VertexElementType: 0x{vtype:X}")

        return verts, uvs

    def _make_mesh(self, name, verts, faces, uvs, materials):
        me = bpy.data.meshes.new(name)
        me.from_pydata(verts, [], faces)
        me.update()

        if uvs:
            uv_layer = me.uv_layers.new(name="UVMap")
            for poly in me.polygons:
                for li in poly.loop_indices:
                    v_idx = me.loops[li].vertex_index
                    uv_layer.data[li].uv = uvs[v_idx]

        for mat in materials:
            mname = mat.get("tex_name") or "Material"
            m = bpy.data.materials.get(mname) or bpy.data.materials.new(mname)
            m.use_nodes = True
            me.materials.append(m)

        obj = bpy.data.objects.new(name, me)
        self.collection.objects.link(obj)
        return obj
#######################################################

# Public entry point used by the GUI operator
def import_mh2(path: str, context, collection_name: str | None = None) -> bool:
    return read_mh2(path, context, collection_name).run()
