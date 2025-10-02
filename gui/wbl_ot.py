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

import traceback
import os
import struct
import datetime
import bpy
from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.props import StringProperty, CollectionProperty, BoolProperty
from ..gtaLib.mdl_cw import read_chinatown as RC, write_chinatown as WC
from ..ops.cw_importer import cw_mdl_importer

def _ensure_bytes(d):
    if isinstance(d, (bytes, bytearray, memoryview)):
        return bytes(d)
    if isinstance(d, str):
        with open(d, "rb") as fh:
            return fh.read()
    # Fail fast with a clear message (this is your current error)
    raise TypeError(f"a bytes-like object is required, not '{type(d).__name__}'")

class IMPORT_OT_CW_wbl(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.cw_wbl"
    bl_label = "Import CW Worldblock (.wbl)"
    filename_ext = ".wbl"
    filter_glob: StringProperty(default="*.wbl", options={'HIDDEN'})
    files: CollectionProperty(type=bpy.types.PropertyGroup)
    import_as_mdls: BoolProperty(name="Import as MDLs", default=False)

    def draw(self, context):
        self.layout.prop(self, "import_as_mdls")

    def execute(self, context):

        fps = []
        if self.files:
            d = os.path.dirname(self.filepath)
            for f in self.files:
                fps.append(os.path.join(d, f.name))
        else:
            fps.append(self.filepath)
        for fp in fps:
            self._import_one(fp, context)
        return {'FINISHED'}

    def _import_one(self, filepath, context):
        logf = None
        if RC.DEBUG_MODE:
            logf = open(RC.get_debug_logfile(filepath), "w", encoding="utf-8")
            RC.dprint(f"==== DEBUG LOG START {datetime.datetime.now()} ====", logf)
        try:
            with open(filepath, "rb") as fh:
                file_bytes = fh.read()
            b = _ensure_bytes(file_bytes) 

            hdr = RC.read_leeds_cw_transform(b, 0x00, logf)
            PX, PY, PZ = hdr["Pos"]

            cur = os.path.dirname(filepath)
            base = os.path.basename(filepath)
            stem, _ = os.path.splitext(base)

            coll_name = f"worldblock{base}"
            coll = bpy.data.collections.get(coll_name)
            if not coll:
                coll = bpy.data.collections.new(coll_name)
                if coll.name not in {c.name for c in bpy.context.scene.collection.children}:
                    bpy.context.scene.collection.children.link(coll)

            mat_bank = RC.MaterialBank(cur, logf)
            mesh_offsets, lights = RC.collect_mesh_offsets_and_lights(b, logf)
            RC.create_lights(lights, coll)

            if not self.import_as_mdls:
                # WHOLE WBL → pass BYTES buffer b
                self._build_merged(
                    b,                                # ← bytes
                    sorted(mesh_offsets),             # ← list[int] offsets
                    (PX, PY, PZ),
                    stem,
                    mat_bank,
                    coll,
                    logf,
                )
            else:
                # Import-as-MDLs → also pass BYTES buffer b to the importer
                for mo in sorted(mesh_offsets):
                    cw_mdl_importer.build_wbl(
                        file_bytes=b,                 # ← bytes (NOT size, NOT len, NOT count)
                        mesh_offset=mo,               # ← int offset
                        pos_xyz=(PX, PY, PZ),
                        material_bank=mat_bank,
                        collection=coll,
                        wbl_stem=stem,
                        logf=logf,
                    )

        except Exception as e:
            tb_str = traceback.format_exc()
            if logf:
                logf.write("IMPORT ERROR\n")
                logf.write(tb_str)
                logf.flush()
            self.report({'ERROR'}, f"Import error: {e}\n{tb_str}")
            print(tb_str)
            return {'CANCELLED'}
        finally:
            if logf:
                RC.dprint("==== DEBUG LOG END ====", logf)
                logf.close()
        return {'FINISHED'}

    def _build_merged(self, b, mesh_offsets, pos, stem, mat_bank, coll, logf=None):
        b = _ensure_bytes(b)
        PX, PY, PZ = pos
        wv, wuv, wf = [], [], []
        wf_mats = []
        for MeshOffset in mesh_offsets:
            # Unpack ONLY from b (the bytes)
            numMaterials = struct.unpack_from('<b', b, MeshOffset + 5)[0]
            numVertices  = struct.unpack_from('<h', b, MeshOffset + 6)[0]
            translationFactor     = struct.unpack_from('<f', b, MeshOffset + 40)[0]
            scaleFactor  = struct.unpack_from('<f', b, MeshOffset + 44)[0]

            stride      = 16
            vertex_base = MeshOffset + 48

            all_verts, all_uvs = [], []
            for vi in range(numVertices):
                off = vertex_base + vi*stride
                x_raw = struct.unpack_from('<h', b, off+0)[0]
                y_raw = struct.unpack_from('<h', b, off+2)[0]
                z_raw = struct.unpack_from('<h', b, off+4)[0]
                u_raw = struct.unpack_from('<h', b, off+12)[0]
                v_raw = struct.unpack_from('<h', b, off+14)[0]
                all_verts.append((x_raw/scaleFactor + PX, y_raw/scaleFactor + PY, z_raw/scaleFactor + PZ))
                all_uvs.append(((u_raw/2048.0) + translationFactor*2, 1.0 - (v_raw/2048.0)))

            vert_offset = 0
            mtab = vertex_base + numVertices*stride
            for mi in range(numMaterials):
                m_off        = mtab + mi*12
                tex_id       = struct.unpack_from('<H', b, m_off+0)[0]
                vertex_count = struct.unpack_from('<H', b, m_off+2)[0]
                render_flags = struct.unpack_from('<B', b, m_off+4)[0]


                uv_mul = -2.0 if render_flags == 4 else 1.0

                base = len(wv)
                for i in range(vertex_count):
                    idx = vert_offset + i 
                    wv.append(all_verts[idx])
                    u_norm, v_norm = all_uvs[idx]
                    u_final = u_norm + translationFactor * uv_mul
                    wuv.append((u_final, v_norm))

                local = RC.tri_strip_to_tris(vertex_count)
                mslot = mat_bank.get_slot(tex_id)
                for (ia, ib, ic) in local:
                    wf.append((base+ia, base+ib, base+ic))
                    wf_mats.append(mslot)

                vert_offset += vertex_count

        if not (wf and wv):
            RC.dprint("nothing to create", logf)
            return

        name = f"CW_Worldblock{stem}"
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(wv, [], wf)
        mesh.update()

        uv_layer = mesh.uv_layers.new(name="UVMap")
        for pi, poly in enumerate(mesh.polygons):
            poly.material_index = wf_mats[pi]
            for li in poly.loop_indices:
                v_idx = mesh.loops[li].vertex_index
                uv_layer.data[li].uv = wuv[v_idx]

        mat_bank.append_all_to_mesh(mesh)
        obj = bpy.data.objects.new(mesh.name, mesh)
        coll.objects.link(obj)

class EXPORT_OT_CW_wbl(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.cw_wbl"
    bl_label = "Export CW Worldblock (.wbl)"
    filename_ext = ".wbl"
    filter_glob: StringProperty(default="*.wbl", options={'HIDDEN'})

    def execute(self, context):
        try:
            sel = [o for o in context.selected_objects if o.type in {'MESH', 'EMPTY', 'LIGHT'}]
            if not sel:
                raise RuntimeError("select objects (mesh/light) to export")

            hdr = {"Right": (1,0,0), "Top": (0,1,0), "At": (0,0,1), "Pos": (0,0,0), "Padding": 0}
            sectors = [{"instances": [], "shadows": [], "levels": [], "lights": []} for _ in range(4)]
            textures_by_sector = [[] for _ in range(4)]
            mdls = []
            mesh_idx_map = {}

            for o in sel:
                if o.type == 'MESH':
                    verts, uvs, parts, sf, uvo = WC.extract_mesh_to_mdl_payload(o)
                    blob = WC.write_mdl_bytes(
                        vertices_worldspace=verts, uvs=uvs, parts=parts,
                        scaleFactor=sf, translationFactor=uvo, base_transform_pos=(0,0,0)
                    )
                    mesh_idx_map[o.name] = len(mdls)
                    mdls.append(blob)
                elif o.type == 'LIGHT':
                    sectors[0]["lights"].append({
                        "X": o.location.x, "Y": o.location.y, "Z": o.location.z,
                        "Size": max(0.001, o.data.shadow_soft_size),
                        "Id": int(o.get("CW_LightID", 0)),
                        "RGB": (int(o.data.color[0]*255), int(o.data.color[1]*255), int(o.data.color[2]*255))
                    })

            for _, idx in mesh_idx_map.items():
                sectors[0]["instances"].append({
                    "ID": 0, "RenderListID": 0, "BuildingSwap": 0,
                    "ResourceID": 0, "MeshRef": idx, "Pointer": 0
                })

            blob = WC.write_wbl_bytes(
                transform_header=hdr,
                sectors=sectors,
                textures_by_sector=textures_by_sector,
                mdls=mdls
            )
            WC.write_file(self.filepath, blob)
            self.report({'INFO'}, f"Exported WBL: {self.filepath}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

classes = (IMPORT_OT_CW_wbl, EXPORT_OT_CW_wbl)
def register():
    for c in classes: bpy.utils.register_class(c)
def unregister():
    for c in reversed(classes): bpy.utils.unregister_class(c)
