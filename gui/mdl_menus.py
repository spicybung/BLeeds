# BLeeds - Scripts for working with R* Leeds (GTA Stories, Chinatown Wars)
# Author: spicybung
# Years: 2025 - 2026
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import math
from typing import Optional, Tuple

import bpy
from .. import get_mesh_attribute
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatVectorProperty,
    StringProperty,
)
from mathutils import Vector

def find_mdl_root(obj: Optional[bpy.types.Object]) -> Optional[bpy.types.Object]:
    if obj is None:
        return None

    cur = obj
    while cur is not None:

        if getattr(cur, "bleeds_is_mdl_root", False):
            return cur

        try:
            if bool(cur.get("bleeds_is_mdl_root", False)):
                return cur
        except Exception:
            pass

        cur = cur.parent

    return None


def get_mdl_root_game(root: Optional[bpy.types.Object]) -> str:
    if root is None:
        return ""
    try:
        if str(root.get("bleeds_mh2_asset_variant", "") or "").strip():
            return "MH2"
        if str(root.get("bleeds_mh2_platform", "") or "").strip():
            return "MH2"
    except Exception:
        pass
    try:
        value = str(root.get("bleeds_model_game", "") or "").upper().strip()
        if value:
            return value
    except Exception:
        pass
    try:
        value = getattr(root, "bleeds_model_game", "")
        if value:
            return str(value).upper().strip()
    except Exception:
        pass
    return ""


def gather_mdl_mesh_children(root: Optional[bpy.types.Object]):
    if root is None:
        return []
    meshes = []
    stack = list(getattr(root, "children", []) or [])
    visited = set()
    while stack:
        obj = stack.pop(0)
        if obj is None:
            continue
        pointer = id(obj)
        if pointer in visited:
            continue
        visited.add(pointer)
        if getattr(obj, "type", None) == "MESH":
            meshes.append(obj)
        stack.extend(list(getattr(obj, "children", []) or []))
    return meshes

def read_root_base_scale_pos(root: bpy.types.Object) -> Tuple[Vector, Vector]:

    if hasattr(root, "bleeds_leeds_scale_base") and hasattr(root, "bleeds_leeds_pos_base"):
        return Vector(root.bleeds_leeds_scale_base), Vector(root.bleeds_leeds_pos_base)

    scale = root.get("bleeds_leeds_scale_base", [1.0, 1.0, 1.0])
    pos = root.get("bleeds_leeds_pos_base", [0.0, 0.0, 0.0])
    return Vector(scale), Vector(pos)

def compute_effective_scale_pos(root: bpy.types.Object) -> Tuple[Vector, Vector]:
    base_scale, base_pos = read_root_base_scale_pos(root)

    root_scale = Vector((root.scale.x, root.scale.y, root.scale.z))
    root_loc = Vector((root.location.x, root.location.y, root.location.z))

    effective_scale = Vector((
        base_scale.x * root_scale.x,
        base_scale.y * root_scale.y,
        base_scale.z * root_scale.z,
    ))
    effective_pos = Vector((
        base_pos.x * root_scale.x + root_loc.x,
        base_pos.y * root_scale.y + root_loc.y,
        base_pos.z * root_scale.z + root_loc.z,
    ))
    return effective_scale, effective_pos

def value_as_power_of_two_fraction_hint(value: float, eps: float = 1e-6) -> str:
    if value == 0.0:
        return "0"
    sign = "-" if value < 0.0 else ""
    v = abs(float(value))

    for p in range(0, 21):
        candidate = 1.0 / (2.0 ** p) if p > 0 else 1.0
        if abs(v - candidate) <= eps:
            if p == 0:
                return f"{sign}1"
            return f"{sign}1/{2**p}"

    for p in range(1, 21):
        candidate = float(2 ** p)
        if abs(v - candidate) <= eps:
            return f"{sign}{2**p}"

    return ""

class EXPORT_OT_MDL_Bake_LeedsScalePos(bpy.types.Operator):
    bl_idname = "bleeds.mdl_bake_leeds_scale_pos"
    bl_label = "Bake Root into Leeds Scale/Pos"
    bl_description = "Bake the root transform into the stored Leeds scale and position"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        root = find_mdl_root(context.object)
        return root is not None

    def execute(self, context: bpy.types.Context) -> set:
        root = find_mdl_root(context.object)
        if root is None:
            self.report({"ERROR"}, "No BLeeds MDL root found.")
            return {"CANCELLED"}

        cached_world = {}
        for obj in root.children_recursive:
            cached_world[obj.name] = obj.matrix_world.copy()

        eff_scale, eff_pos = compute_effective_scale_pos(root)

        if hasattr(root, "bleeds_leeds_scale_base"):
            root.bleeds_leeds_scale_base = (eff_scale.x, eff_scale.y, eff_scale.z)
        else:
            root["bleeds_leeds_scale_base"] = [eff_scale.x, eff_scale.y, eff_scale.z]

        if hasattr(root, "bleeds_leeds_pos_base"):
            root.bleeds_leeds_pos_base = (eff_pos.x, eff_pos.y, eff_pos.z)
        else:
            root["bleeds_leeds_pos_base"] = [eff_pos.x, eff_pos.y, eff_pos.z]

        root.location = (0.0, 0.0, 0.0)
        root.rotation_euler = (0.0, 0.0, 0.0)
        root.scale = (1.0, 1.0, 1.0)

        for obj in root.children_recursive:
            mw = cached_world.get(obj.name, None)
            if mw is not None:
                obj.matrix_world = mw

        return {"FINISHED"}

class EXPORT_PT_MDL_LeedsScalePos(bpy.types.Panel):
    bl_idname = "EXPORT_PT_MDL_LeedsScalePos"
    bl_label = "BLeeds - Export Object"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        root = find_mdl_root(context.object)
        return root is not None and get_mdl_root_game(root) != "MH2"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        root = find_mdl_root(context.object)
        if root is None:
            layout.label(text="No BLeeds MDL root found.")
            return

        box = layout.box()
        col = box.column(align=True)
        col.label(text=f"Root: {root.name}")

        hash_key = None
        try:
            if hasattr(root, "bleeds_mdl_atomic_hash_key"):
                hash_key = int(root.bleeds_mdl_atomic_hash_key)
            elif "bleeds_mdl_atomic_hash_key" in root:
                hash_key = int(root["bleeds_mdl_atomic_hash_key"])
        except Exception:
            pass
        if hash_key is not None:
            col.label(text=f"Hash Key: 0x{hash_key:08X}")

        meta = col.column(align=True)
        if hasattr(root, "bleeds_mdl_platform"):
            meta.prop(root, "bleeds_mdl_platform", text="Platform")
        else:
            meta.label(text=f"Platform: {root.get('bleeds_mdl_platform', 'Unknown')}")

        if hasattr(root, "bleeds_mdl_type"):
            meta.prop(root, "bleeds_mdl_type", text="MDL Type")
        else:
            meta.label(text=f"MDL Type: {root.get('bleeds_mdl_type', 'Unknown')}")

        if hasattr(root, "bleeds_mdl_filepath"):
            meta.prop(root, "bleeds_mdl_filepath", text="Source")
        else:
            src = root.get("bleeds_mdl_filepath", "")
            if src:
                meta.label(text=f"Source: {src}")

        if hasattr(root, "bleeds_export_use_normals"):
            meta.prop(root, "bleeds_export_use_normals", text="Export Normals")
        if hasattr(root, "bleeds_export_gouraud_shading"):
            meta.prop(root, "bleeds_export_gouraud_shading", text="Gouraud Shading")

        layout.separator()
        base_box = layout.box()
        base_box.label(text="MDL Base (In-Game)")

        if hasattr(root, "bleeds_leeds_scale_base"):
            base_box.prop(root, "bleeds_leeds_scale_base", text="Scale")
        else:
            base_box.prop(root, '["bleeds_leeds_scale_base"]', text="Scale")

        if hasattr(root, "bleeds_leeds_pos_base"):
            base_box.prop(root, "bleeds_leeds_pos_base", text="Pos")
        else:
            base_box.prop(root, '["bleeds_leeds_pos_base"]', text="Pos")

        base_scale, base_pos = read_root_base_scale_pos(root)
        hint_row = base_box.row(align=True)
        hint_row.label(text="Scale hint:")
        hint_row.label(
            text=(
                f"X {value_as_power_of_two_fraction_hint(base_scale.x)}  "
                f"Y {value_as_power_of_two_fraction_hint(base_scale.y)}  "
                f"Z {value_as_power_of_two_fraction_hint(base_scale.z)}"
            )
        )

        if abs(root.rotation_euler.x) > 1e-6 or abs(root.rotation_euler.y) > 1e-6 or abs(root.rotation_euler.z) > 1e-6:
            warn = eff_box.column(align=True)
            warn.alert = True
            warn.label(text="Warning: Root rotation is non-zero.")
            warn.label(text="MDL scale/pos is axis-aligned; rotation is not represented in the file.")

        layout.separator()
        layout.operator(EXPORT_OT_MDL_Bake_LeedsScalePos.bl_idname, icon="FILE_TICK")

        try:

            from ..ops.mdl_exporter import gather_mesh_parts
        except Exception:
            gather_mesh_parts = None
        if gather_mesh_parts is not None and root is not None:
            try:
                meshes = gather_mesh_parts(context, root)
            except Exception:
                meshes = []
            counts = []
            depsgraph = context.evaluated_depsgraph_get()
            for obj in meshes:

                try:
                    obj_eval = obj.evaluated_get(depsgraph)
                    mesh_eval = obj_eval.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
                    counts.append(len(mesh_eval.vertices))
                except Exception:
                    counts.append(0)
                finally:
                    try:
                        obj_eval.to_mesh_clear()
                    except Exception:
                        pass

            try:
                if hasattr(root, "bleeds_mdl_part_batch_verts"):
                    root.bleeds_mdl_part_batch_verts = [int(x) for x in counts]
                else:
                    root["bleeds_mdl_part_batch_verts"] = [int(x) for x in counts]
            except Exception:
                pass
            if counts:
                geom_box = layout.box()
                geom_box.label(text="Geometry Stats")
                for i, cnt in enumerate(counts):
                    geom_box.label(text=f"Part {i}: {cnt} verts")

class EXPORT_OT_MDL_StampSemanticAttributes(bpy.types.Operator):
    bl_idname = "bleeds.mdl_stamp_semantic_attributes"
    bl_label = "Stamp/Refresh MDL Attributes"
    bl_description = "Create or refresh the MDL export attributes on model meshes"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return find_mdl_root(context.object) is not None

    def execute(self, context: bpy.types.Context) -> set:
        root = find_mdl_root(context.object)
        if root is None:
            self.report({"ERROR"}, "No BLeeds MDL root found.")
            return {"CANCELLED"}

        try:
            from ..ops.mdl_exporter import gather_mesh_parts, writeMdlSemanticDefaultsForExport, normalizeMdlCustomPedVertexGroupsForExport, writeMdlCanonicalPedIdentityMapProps
        except Exception as exc:
            self.report({"ERROR"}, f"Could not load MDL semantic attribute writer: {exc}")
            return {"CANCELLED"}

        try:
            meshes = gather_mesh_parts(context, root)
        except Exception as exc:
            self.report({"ERROR"}, f"Could not gather MDL mesh parts: {exc}")
            return {"CANCELLED"}

        rebuilt_groups = 0
        try:
            writeMdlCanonicalPedIdentityMapProps(root, None, root)
        except Exception:
            pass
        for part_index, obj in enumerate(meshes):
            writeMdlSemanticDefaultsForExport(obj, part_index)
            rebuilt_groups += int(normalizeMdlCustomPedVertexGroupsForExport(obj, root) or 0)

        if rebuilt_groups:
            self.report({"INFO"}, f"Stamped BLeeds MDL attributes on {len(meshes)} mesh part(s); rebuilt custom PED vertex groups on {rebuilt_groups} vertices.")
        else:
            self.report({"INFO"}, f"Stamped BLeeds MDL attributes on {len(meshes)} mesh part(s).")
        return {"FINISHED"}

def readMdlIdProp(owner, key: str, default=None):
    try:
        if owner is not None and key in owner:
            return owner[key]
    except Exception:
        pass
    return default

def getMdlAttributeExpectedCount(mesh: bpy.types.Mesh, domain: str) -> int:
    domain_key = str(domain or "").upper().strip()
    if domain_key == "POINT":
        return len(mesh.vertices)
    if domain_key == "FACE":
        return len(mesh.polygons)
    if domain_key == "CORNER":
        return len(mesh.loops)
    if domain_key == "EDGE":
        return len(mesh.edges)
    return 0

class EXPORT_PT_MDL_SemanticAttributes(bpy.types.Panel):
    bl_idname = "EXPORT_PT_MDL_SemanticAttributes"
    bl_label = "BLeeds MDL Properties / Attributes"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        root = find_mdl_root(context.object)
        return root is not None and get_mdl_root_game(root) != "MH2"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.use_property_split = False
        layout.use_property_decorate = False

        root = find_mdl_root(context.object)
        if root is None:
            layout.label(text="No BLeeds MDL root found.")
            return

        layout.operator(EXPORT_OT_MDL_StampSemanticAttributes.bl_idname, icon="FILE_REFRESH")

        try:
            from ..ops.mdl_exporter import gather_mesh_parts
        except Exception:
            gather_mesh_parts = None

        meshes = []
        if gather_mesh_parts is not None:
            try:
                meshes = gather_mesh_parts(context, root)
            except Exception:
                meshes = []

        active_mesh_obj = context.object if context.object is not None and context.object.type == 'MESH' else None
        if active_mesh_obj is None and meshes:
            active_mesh_obj = meshes[0]

        root_box = layout.box()
        root_box.label(text="Root MDL Properties")
        root_col = root_box.column(align=True)
        root_col.label(text=f"Root: {root.name}")
        root_col.label(text=f"Platform: {getattr(root, 'bleeds_mdl_platform', readMdlIdProp(root, 'bleeds_mdl_platform', 'Unknown'))}")
        root_col.label(text=f"Type: {getattr(root, 'bleeds_mdl_type', readMdlIdProp(root, 'bleeds_mdl_type', 'Unknown'))}")
        root_col.label(text=f"Mesh parts: {len(meshes)}")

        if active_mesh_obj is None:
            layout.label(text="No active mesh part found under this MDL root.")
            return

        mesh = active_mesh_obj.data
        mesh_box = layout.box()
        mesh_box.label(text="Active Mesh Part")
        mesh_col = mesh_box.column(align=True)
        mesh_col.label(text=f"Object: {active_mesh_obj.name}")
        mesh_col.label(text=f"Verts/Faces/Loops: {len(mesh.vertices)} / {len(mesh.polygons)} / {len(mesh.loops)}")
        mesh_col.label(text=f"Origin: {readMdlIdProp(mesh, 'bleeds_mdl_semantic_attributes_origin', 'none')}")
        mesh_col.label(text=f"Version: {readMdlIdProp(mesh, 'bleeds_mdl_semantic_attributes_version', 'none')}")
        mesh_col.label(text=f"Part index: {readMdlIdProp(active_mesh_obj, 'bleeds_mdl_part_index', readMdlIdProp(mesh, 'bleeds_mdl_source_part_index', 'none'))}")
        mesh_col.label(text=f"Material index: {readMdlIdProp(active_mesh_obj, 'bleeds_mdl_part_material_id', readMdlIdProp(mesh, 'bleeds_mdl_source_material_index', 'none'))}")

        strip_counts = readMdlIdProp(mesh, 'bleeds_mdl_source_strip_counts', [])
        try:
            strip_count = len(strip_counts)
            strip_vertex_total = sum(int(v) for v in strip_counts)
        except Exception:
            strip_count = 0
            strip_vertex_total = 0
        mesh_col.label(text=f"Source strips: {strip_count}, strip verts: {strip_vertex_total}")

        attr_box = layout.box()
        attr_box.label(text="Required Semantic Attributes")
        attr_specs = [
            ("bleeds_mdl_part_index", "FACE"),
            ("bleeds_mdl_material_index", "FACE"),
            ("bleeds_mdl_source_strip_index", "FACE"),
            ("bleeds_mdl_source_strip_triangle_index", "FACE"),
            ("bleeds_mdl_corner_source_emit_index", "CORNER"),
            ("bleeds_mdl_corner_source_export_vertex_index", "CORNER"),
            ("bleeds_mdl_corner_source_strip_index", "CORNER"),
            ("bleeds_mdl_corner_source_strip_vertex_index", "CORNER"),
            ("bleeds_mdl_point_source_emit_index", "POINT"),
            ("bleeds_mdl_point_source_export_vertex_index", "POINT"),
            ("bleeds_mdl_point_source_strip_index", "POINT"),
            ("bleeds_mdl_point_source_strip_vertex_index", "POINT"),
        ]
        attr_col = attr_box.column(align=True)
        for attr_name, domain in attr_specs:
            expected = getMdlAttributeExpectedCount(mesh, domain)
            attr = get_mesh_attribute(mesh, attr_name)
            row = attr_col.row(align=True)
            if attr is None:
                row.alert = True
                row.label(text=f"Missing {domain}: {attr_name}")
                continue
            try:
                actual = len(attr.data)
            except Exception:
                actual = -1
            if actual != expected:
                row.alert = True
            row.label(text=f"{domain}: {attr_name} ({actual}/{expected})")

class OBJECT_PT_MDL_Manhunt2Properties(bpy.types.Panel):
    bl_idname = "OBJECT_PT_MDL_Manhunt2Properties"
    bl_label = "BLeeds Manhunt 2 MDL"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        root = find_mdl_root(context.object)
        return root is not None and get_mdl_root_game(root) == "MH2"

    def draw(self, context: bpy.types.Context) -> None:
        import os

        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        root = find_mdl_root(context.object)
        if root is None:
            layout.label(text="No BLeeds MH2 MDL root found.")
            return

        meshes = gather_mdl_mesh_children(root)
        active_mesh = context.object if context.object is not None and context.object.type == "MESH" else None
        if active_mesh not in meshes:
            active_mesh = meshes[0] if meshes else None

        model_box = layout.box()
        model_box.label(text="Model")
        model_col = model_box.column(align=True)
        model_col.label(text="Root: {}".format(root.name))
        model_col.label(text="Game: Manhunt 2")
        detected_type = str(root.get("bleeds_mh2_model_class", "") or "").upper().strip()
        if not detected_type:
            detected_type = "PED" if int(root.get("bleeds_mh2_bone_count", 0)) > 0 else "SIM"
        detected_platform = str(root.get("bleeds_mh2_platform", "") or "").upper().strip()
        if not detected_platform:
            detected_platform = "PSP" if str(root.get("bleeds_mh2_asset_variant", "")).upper() == "PSP_BETA" else "PC"
        model_col.label(text="MDL Type: {}".format("PedModel" if detected_type == "PED" else "SimpleModel"))
        model_col.label(text="Platform: {}".format(detected_platform))
        source_path = str(getattr(root, "bleeds_mdl_filepath", root.get("bleeds_mdl_filepath", "")) or "")
        if source_path:
            model_col.label(text="Source: {}".format(os.path.basename(source_path)))
        model_col.label(text="Bones: {}".format(int(root.get("bleeds_mh2_bone_count", 0))))
        model_col.label(text="Mesh parts: {}".format(len(meshes)))

        format_box = layout.box()
        format_box.label(text="Detected MH2 Structure")
        format_col = format_box.column(align=True)
        format_col.label(text="Asset: {}".format(root.get("bleeds_mh2_asset_variant", "Unknown")))
        format_col.label(text="Entry: {}".format(root.get("bleeds_mh2_entry_layout", "Unknown")))
        format_col.label(text="Bones: {}".format(root.get("bleeds_mh2_bone_record_layout", "Unknown")))
        format_col.label(text="Object header: {}".format(root.get("bleeds_mh2_object_header_layout", "Unknown")))

        texture_box = layout.box()
        texture_box.label(text="Textures")
        texture_col = texture_box.column(align=True)
        texture_path = str(root.get("bleeds_mh2_texture_source_path", "") or "")
        if texture_path:
            texture_col.label(text="TEX: {}".format(os.path.basename(texture_path)))
        else:
            texture_col.label(text="TEX: Not imported")
        texture_col.label(text="Images: {}".format(int(root.get("bleeds_mh2_texture_image_count", 0))))

        if active_mesh is None:
            return

        mesh = active_mesh.data
        mesh_box = layout.box()
        mesh_box.label(text="Active MH2 Mesh Part")
        mesh_col = mesh_box.column(align=True)
        mesh_col.label(text="Object: {}".format(active_mesh.name))
        mesh_col.label(text="Vertices: {}".format(len(mesh.vertices)))
        mesh_col.label(text="Faces: {}".format(len(mesh.polygons)))
        mesh_col.label(text="Materials: {}".format(len(mesh.materials)))
        parent_bone = str(active_mesh.get("bleeds_mh2_parent_bone_name", "") or "")
        if parent_bone:
            mesh_col.label(text="Parent bone: {}".format(parent_bone))
        vertex_element_type = int(active_mesh.get("bleeds_mh2_vertex_element_type", 0))
        mesh_col.label(text="Vertex element: 0x{:X}".format(vertex_element_type))
        mesh_col.label(text="Vertex stride: 0x{:X}".format(int(active_mesh.get("bleeds_mh2_vertex_stride", 0))))
        mesh_col.label(text="Vertex layout: {}".format(active_mesh.get("bleeds_mh2_vertex_layout", "Unknown")))
        mesh_col.label(text="UV layers: {}".format(int(active_mesh.get("bleeds_mh2_uv_layer_count", len(mesh.uv_layers)))))
        mesh_col.label(text="Skin weights: {}".format("Yes" if bool(active_mesh.get("bleeds_mh2_has_skin_weights", False)) else "No"))
        mesh_col.label(text="Weighted vertices: {}".format(int(active_mesh.get("bleeds_mh2_weighted_vertex_count", 0))))


def register() -> None:
    bpy.utils.register_class(EXPORT_OT_MDL_Bake_LeedsScalePos)
    bpy.utils.register_class(EXPORT_PT_MDL_LeedsScalePos)
    bpy.utils.register_class(EXPORT_OT_MDL_StampSemanticAttributes)
    bpy.utils.register_class(EXPORT_PT_MDL_SemanticAttributes)
    bpy.utils.register_class(OBJECT_PT_MDL_Manhunt2Properties)

    if not hasattr(bpy.types.Object, "bleeds_is_mdl_root"):
        bpy.types.Object.bleeds_is_mdl_root = BoolProperty(
            name="BLeeds MDL Root",
            description="Marks this object as the root of an imported BLeeds MDL",
            default=False,
        )

    if not hasattr(bpy.types.Object, "bleeds_mdl_platform"):
        bpy.types.Object.bleeds_mdl_platform = EnumProperty(
            name="Platform",
            description="Leeds model platform for this MDL",
            items=[
                ("PS2", "PS2", "PlayStation 2"),
                ("PSP", "PSP", "PlayStation Portable"),
                ("PC", "PC", "Windows PC"),
            ],
            default="PS2",
        )

    if not hasattr(bpy.types.Object, "bleeds_model_game"):
        bpy.types.Object.bleeds_model_game = EnumProperty(
            name="3D Models",
            description="Leeds 3D model family",
            items=[
                ("LCS", "LCS", "Grand Theft Auto: Liberty City Stories"),
                ("VCS", "VCS", "Grand Theft Auto: Vice City Stories"),
                ("MH2", "MH2", "Manhunt 2"),
            ],
            default="VCS",
        )

    if not hasattr(bpy.types.Object, "bleeds_mdl_type"):
        bpy.types.Object.bleeds_mdl_type = EnumProperty(
            name="MDL Type",
            description="Leeds MDL model class",
            items=[
                ("SIM", "SimpleModel", "Prop or simple model"),
                ("PED", "PedModel", "Pedestrian or skinned actor model"),
                ("CUT", "CutsceneModel", "Cutscene actor model"),
                ("VEH", "VehModel", "Vehicle model"),
            ],
            default="SIM",
        )

    if not hasattr(bpy.types.Object, "bleeds_mdl_filepath"):
        bpy.types.Object.bleeds_mdl_filepath = StringProperty(
            name="Source File",
            description="Original MDL file path used for import",
            default="",
            subtype="FILE_PATH",
        )

    if not hasattr(bpy.types.Object, "bleeds_imported_export_mode"):
        bpy.types.Object.bleeds_imported_export_mode = EnumProperty(
            name="Internal PED Rebuild",
            description="Imported PEDs rebuild from live mesh data",
            items=[("REBUILD", "Rebuild", "Rebuild using calculated live data and ped_atomic_bind basis")],
            default="REBUILD",
        )

    if not hasattr(bpy.types.Object, "bleeds_leeds_scale_base"):
        bpy.types.Object.bleeds_leeds_scale_base = FloatVectorProperty(
            name="Leeds Scale (Base)",
            description="Base in-game scale stored by the MDL (used for vertex decode)",
            size=3,
            default=(1.0, 1.0, 1.0),
            subtype="XYZ",
        )

    if not hasattr(bpy.types.Object, "bleeds_leeds_pos_base"):
        bpy.types.Object.bleeds_leeds_pos_base = FloatVectorProperty(
            name="Leeds Pos (Base)",
            description="Base in-game position stored by the MDL (used for vertex decode)",
            size=3,
            default=(0.0, 0.0, 0.0),
            subtype="TRANSLATION",
        )

def unregister() -> None:

    bpy.utils.unregister_class(OBJECT_PT_MDL_Manhunt2Properties)
    bpy.utils.unregister_class(EXPORT_PT_MDL_SemanticAttributes)
    bpy.utils.unregister_class(EXPORT_OT_MDL_StampSemanticAttributes)
    bpy.utils.unregister_class(EXPORT_PT_MDL_LeedsScalePos)
    bpy.utils.unregister_class(EXPORT_OT_MDL_Bake_LeedsScalePos)

    for prop_name in (
        "bleeds_is_mdl_root",
        "bleeds_mdl_platform",
        "bleeds_model_game",
        "bleeds_mdl_type",
        "bleeds_mdl_filepath",
        "bleeds_leeds_scale_base",
        "bleeds_leeds_pos_base",
    ):
        if hasattr(bpy.types.Object, prop_name):
            delattr(bpy.types.Object, prop_name)
