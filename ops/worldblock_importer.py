# BLeeds - Scripts for working with R* Leeds (GTA Stories, Chinatown Wars, Manhunt 2, etc) formats in Blender
# Author: spicybung
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
import traceback

import bpy
from bpy.types import Operator
from bpy.props import StringProperty, CollectionProperty
from bpy_extras.io_utils import ImportHelper

from ..leedsLib.worldblock import read_chinatown as RC

#######################################################
def ensure_bytes(file_bytes):
    """Ensure we always end up with a bytes object for parsing."""
    if isinstance(file_bytes, (bytes, bytearray, memoryview)):
        return bytes(file_bytes)
    if isinstance(file_bytes, str):
        with open(file_bytes, "rb") as fh:
            return fh.read()
    raise TypeError(
        f"file_bytes must be bytes/bytearray/memoryview or a path str, not {type(file_bytes).__name__}"
    )

#######################################################
class worldblock_importer:
    """
    Helper for building a single CW mesh from a WBL GeometryMesh header.

    This is intentionally low-level so it can be called either from the
    dedicated WBL import operator below, or from other modules that
    need to build meshes from embedded CW geometry.
    """

    @staticmethod
    def build_wbl(
        file_bytes,
        mesh_offset: int,
        pos_xyz,
        material_bank: RC.MaterialBank,
        collection: bpy.types.Collection,
        wbl_stem: str,
        logf=None,
    ):
        file_bytes = ensure_bytes(file_bytes)

        PX, PY, PZ = pos_xyz
        if mesh_offset < 0 or mesh_offset + 48 > len(file_bytes):
            RC.dprint(f"[0x{mesh_offset:06X}] out of bounds", logf)
            return None

        numMaterials = struct.unpack_from("<b", file_bytes, mesh_offset + 5)[0]
        numVertices = struct.unpack_from("<h", file_bytes, mesh_offset + 6)[0]
        translationFactor = struct.unpack_from("<f", file_bytes, mesh_offset + 40)[0]
        scaleFactor = struct.unpack_from("<f", file_bytes, mesh_offset + 44)[0]

        stride = 16
        vbase = mesh_offset + 48

        all_verts = []
        all_uvs = []

        for vi in range(numVertices):
            off = vbase + vi * stride
            x_raw = struct.unpack_from("<h", file_bytes, off + 0)[0]
            y_raw = struct.unpack_from("<h", file_bytes, off + 2)[0]
            z_raw = struct.unpack_from("<h", file_bytes, off + 4)[0]
            u_raw = struct.unpack_from("<h", file_bytes, off + 12)[0]
            v_raw = struct.unpack_from("<h", file_bytes, off + 14)[0]

            x = x_raw / scaleFactor + PX
            y = y_raw / scaleFactor + PY
            z = z_raw / scaleFactor + PZ
            u = (u_raw / 2048.0) + translationFactor * 2
            v = 1.0 - (v_raw / 2048.0)

            all_verts.append((x, y, z))
            all_uvs.append((u, v))

        verts = []
        uvs = []
        faces = []
        face_mats = []

        vert_offset = 0
        mtab = vbase + numVertices * stride

        for mi in range(numMaterials):
            m_off = mtab + mi * 12
            tex_id = struct.unpack_from("<H", file_bytes, m_off + 0)[0]
            vertex_count = struct.unpack_from("<H", file_bytes, m_off + 2)[0]

            base = len(verts)
            for i in range(vertex_count):
                idx = vert_offset + i
                verts.append(all_verts[idx])
                uvs.append(all_uvs[idx])

            local_faces = RC.tri_strip_to_tris(vertex_count)
            mat_slot = material_bank.get_slot(tex_id)

            for (a, b, c) in local_faces:
                faces.append((base + a, base + b, base + c))
                face_mats.append(mat_slot)

            vert_offset += vertex_count

        name = f"CW_Worldblock{wbl_stem}_MDL_{mesh_offset:06X}"
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(verts, [], faces)
        mesh.update()

        uv_layer = mesh.uv_layers.new(name="UVMap")
        for poly_index, poly in enumerate(mesh.polygons):
            poly.material_index = face_mats[poly_index]
            for loop_index in poly.loop_indices:
                v_idx = mesh.loops[loop_index].vertex_index
                uv_layer.data[loop_index].uv = uvs[v_idx]

        material_bank.append_all_to_mesh(mesh)

        obj = bpy.data.objects.new(mesh.name, mesh)
        collection.objects.link(obj)

        return obj


class IMPORT_OT_wbl(Operator, ImportHelper):
    """Import Chinatown Wars worldblock sectors (.wbl)."""

    bl_idname = "import_scene.cw_worldblock"
    bl_label = "R* Leeds: Worldblock (.wbl)"
    filename_ext = ".wbl"

    filter_glob: StringProperty(
        default="*.wbl",
        options={"HIDDEN"},
    )
    files: CollectionProperty(type=bpy.types.PropertyGroup)

    def execute(self, context):
        filepaths = []
        if self.files:
            directory = os.path.dirname(self.filepath)
            for f in self.files:
                filepaths.append(os.path.join(directory, f.name))
        else:
            filepaths.append(self.filepath)

        for fp in filepaths:
            try:
                RC.import_wbl(fp, context)
            except Exception as exc:
                tb = traceback.format_exc()
                self.report({"ERROR"}, f"Failed to import '{fp}': {exc}")
                print(tb)
                return {"CANCELLED"}

        return {"FINISHED"}

#######################################################
def register():
    bpy.utils.register_class(IMPORT_OT_wbl)


def unregister():
    bpy.utils.unregister_class(IMPORT_OT_wbl)


if __name__ == "__main__":
    register()
