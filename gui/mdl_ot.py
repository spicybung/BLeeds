# BLeeds - Scripts for working with R* Leeds (GTA Stories, Chinatown Wars, Manhunt 2, etc) formats in Blender
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
import struct
import bpy

from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.props import StringProperty, BoolProperty

from ..gtaLib.mdl_cw import read_chinatown as RC, write_chinatown as WC
from ..gtaLib.mdl_mh2 import import_mh2


class IMPORT_OT_MH2_mdl(bpy.types.Operator, ImportHelper):
    """Import Rockstar Leeds Manhunt 2 MDL"""
    bl_idname = "import_scene.mh2_mdl"
    bl_label = "Import an Manhunt 2 Model (.mdl)"
    bl_options = {'UNDO'}

    filename_ext = ".mdl"
    filter_glob: StringProperty(default="*.mdl", options={'HIDDEN'})

    group_into_collection: BoolProperty(
        name="Group into Collection",
        default=True,
        description="Put imported objects into a new collection"
    )

    def execute(self, context):
        ok = import_mh2(self.filepath, context,
                        collection_name=None if self.group_into_collection else None)
        return {'FINISHED'} if ok else {'CANCELLED'}

#######################################################
class IMPORT_OT_CW_mdl(Operator, ImportHelper):
    bl_idname = "import_scene.cw_mdl"
    bl_label = "Import CW MDL (.mdl)"
    filename_ext = ".mdl"
    filter_glob: StringProperty(default="*.mdl", options={'HIDDEN'})

    def execute(self, context):
        try:
            with open(self.filepath, "rb") as f:
                b = f.read()

            if len(b) < 48:
                raise RuntimeError("MDL too small")

            numMaterials = struct.unpack_from('<b', b, 5)[0]
            numVertices  = struct.unpack_from('<h', b, 6)[0]
            translationFactor     = struct.unpack_from('<f', b, 40)[0]
            scaleFactor  = struct.unpack_from('<f', b, 44)[0]
            stride = 16
            vbase = 48

            basename = os.path.basename(self.filepath)
            stem, _  = os.path.splitext(basename)
            coll_name = f"mdl{basename}"
            coll = bpy.data.collections.get(coll_name)
            if not coll:
                coll = bpy.data.collections.new(coll_name)
                if coll.name not in {c.name for c in bpy.context.scene.collection.children}:
                    bpy.context.scene.collection.children.link(coll)

            mat_bank = RC.MaterialBank(os.path.dirname(self.filepath), None)

            all_verts, all_uvs = [], []
            for vi in range(numVertices):
                off = vbase + vi*stride
                x_raw = struct.unpack_from('<h', b, off+0)[0]
                y_raw = struct.unpack_from('<h', b, off+2)[0]
                z_raw = struct.unpack_from('<h', b, off+4)[0]
                u_raw = struct.unpack_from('<h', b, off+12)[0]
                v_raw = struct.unpack_from('<h', b, off+14)[0]
                all_verts.append((x_raw/scaleFactor, y_raw/scaleFactor, z_raw/scaleFactor))
                all_uvs.append((u_raw/2048.0, 1.0 - (v_raw/2048.0)))

            verts, uvs, faces, f_mats = [], [], [], []
            vert_offset = 0
            mtab = vbase + numVertices*stride

            for mi in range(numMaterials):
                m_off        = mtab + mi*12
                tex_id       = struct.unpack_from('<H', b, m_off+0)[0]
                vertex_count = struct.unpack_from('<H', b, m_off+2)[0]

                base = len(verts)
                for i in range(vertex_count):
                    idx = vert_offset + i
                    verts.append(all_verts[idx]); uvs.append(all_uvs[idx])

                local = RC.tri_strip_to_tris(vertex_count)
                mslot = mat_bank.get_slot(tex_id)
                for (a,b,c) in local:
                    faces.append((base+a, base+b, base+c)); f_mats.append(mslot)

                vert_offset += vertex_count

            name = f"CW_MDL_{stem}"
            mesh = bpy.data.meshes.new(name)
            mesh.from_pydata(verts, [], faces)
            mesh.update()

            uv_layer = mesh.uv_layers.new(name="UVMap")
            for pi, poly in enumerate(mesh.polygons):
                poly.material_index = f_mats[pi]
                for li in poly.loop_indices:
                    v_idx = mesh.loops[li].vertex_index
                    uv_layer.data[li].uv = uvs[v_idx]

            mat_bank.append_all_to_mesh(mesh)
            obj = bpy.data.objects.new(mesh.name, mesh)
            coll.objects.link(obj)

            self.report({'INFO'}, "MDL import finished")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
#######################################################
class EXPORT_OT_CW_mdl(Operator, ExportHelper):
    bl_idname = "export_scene.cw_mdl"
    bl_label = "Export CW MDL (.mdl)"
    filename_ext = ".mdl"
    filter_glob: StringProperty(default="*.mdl", options={'HIDDEN'})

    def execute(self, context):
        try:
            obj = context.active_object
            if not obj or obj.type != 'MESH':
                raise RuntimeError("select a mesh object")
            verts, uvs, parts, sf, uvo = WC.extract_mesh_to_mdl_payload(obj)
            blob = WC.write_mdl_bytes(
                vertices_worldspace=verts,
                uvs=uvs,
                parts=parts,
                scaleFactor=sf,
                translationFactor=uvo,
                base_transform_pos=(0,0,0)
            )
            WC.write_file(self.filepath, blob)
            self.report({'INFO'}, f"Exported MDL: {self.filepath}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        

#######################################################
def register():

    bpy.utils.register_class(IMPORT_OT_CW_mdl)
    bpy.utils.register_class(EXPORT_OT_CW_mdl)
    bpy.utils.register_class(IMPORT_OT_MH2_mdl)

def unregister():
    bpy.utils.unregister_class(IMPORT_OT_CW_mdl)
    bpy.utils.unregister_class(EXPORT_OT_CW_mdl)

    bpy.utils.unregister_class(IMPORT_OT_MH2_mdl)

if __name__ == "__main__":
    register()
