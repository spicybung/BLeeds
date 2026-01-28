# BLeeds - Scripts for working with R* Leeds (GTA Stories, Chinatown Wars)
# Author: spicybung
# Years: 2025 -
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

from __future__ import annotations

import math
from typing import Optional, Tuple

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatVectorProperty,
    StringProperty,
)
from mathutils import Vector


def find_mdl_root(obj: Optional[bpy.types.Object]) -> Optional[bpy.types.Object]:
    """Walk up the parent chain and return the first object marked as a BLeeds MDL root."""
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


def read_root_base_scale_pos(root: bpy.types.Object) -> Tuple[Vector, Vector]:
    """Read base scale/pos from either typed props or ID props."""
    if hasattr(root, "bleeds_leeds_scale_base") and hasattr(root, "bleeds_leeds_pos_base"):
        return Vector(root.bleeds_leeds_scale_base), Vector(root.bleeds_leeds_pos_base)

    scale = root.get("bleeds_leeds_scale_base", [1.0, 1.0, 1.0])
    pos = root.get("bleeds_leeds_pos_base", [0.0, 0.0, 0.0])
    return Vector(scale), Vector(pos)


def compute_effective_scale_pos(root: bpy.types.Object) -> Tuple[Vector, Vector]:
    """Compute the current effective in-game scale/pos, based on the root transform."""
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
    """Return a friendly fraction hint for values like 0.5, 0.25, 0.0625, 0.03125."""
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
    """Bake the current root transform into the stored Leeds scale/pos and reset the root."""
    bl_idname = "bleeds.mdl_bake_leeds_scale_pos"
    bl_label = "Bake Root into Leeds Scale/Pos"
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
        return find_mdl_root(context.object) is not None

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

        layout.separator()
        tr_box = layout.box()
        tr_box.label(text="Blender Root Transform")
        tr_box.prop(root, "location")
        tr_box.prop(root, "rotation_euler", text="Rotation")
        tr_box.prop(root, "scale")

        layout.separator()
        eff_box = layout.box()
        eff_box.label(text="Effective (In-Game) After Root")

        eff_scale, eff_pos = compute_effective_scale_pos(root)
        eff_box.label(text=f"Scale: ({eff_scale.x:.8g}, {eff_scale.y:.8g}, {eff_scale.z:.8g})")
        eff_box.label(text=f"Pos:   ({eff_pos.x:.8g}, {eff_pos.y:.8g}, {eff_pos.z:.8g})")

        eff_hint_row = eff_box.row(align=True)
        eff_hint_row.label(text="Scale hint:")
        eff_hint_row.label(
            text=(
                f"X {value_as_power_of_two_fraction_hint(eff_scale.x)}  "
                f"Y {value_as_power_of_two_fraction_hint(eff_scale.y)}  "
                f"Z {value_as_power_of_two_fraction_hint(eff_scale.z)}"
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
            counts: list[int] = []
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


# --------------------------------------------------------------------------
# Export Normals Toggle
#
# The exporter now supports enabling/disabling normal export via a property
# stored on the MDL root.  This panel exposes a checkbox to control
# ``bleeds_export_use_normals`` for the active root.  When enabled the
# exporter writes a normals stream immediately after the UV stream for
# each DMA packet.

class EXPORT_PT_MDL_ExportOptions(bpy.types.Panel):
    bl_idname = "EXPORT_PT_MDL_ExportOptions"
    bl_label = "BLeeds Export Options"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        obj = context.object
        return obj is not None and find_mdl_root(obj) is not None

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        root = find_mdl_root(context.object)
        if root is None:
            layout.label(text="No BLeeds MDL root found.")
            return

        if not hasattr(root, "bleeds_export_use_normals") and "bleeds_export_use_normals" not in root:
            try:
                root["bleeds_export_use_normals"] = False
            except Exception:
                pass

        try:
            layout.prop(root, '["bleeds_export_use_normals"]', text="Export Normals")
        except Exception:
            layout.label(text="Unable to access export normals flag.")


def register() -> None:
    bpy.utils.register_class(EXPORT_OT_MDL_Bake_LeedsScalePos)
    bpy.utils.register_class(EXPORT_PT_MDL_LeedsScalePos)
    bpy.utils.register_class(EXPORT_PT_MDL_ExportOptions)

    if not hasattr(bpy.types.Object, "bleeds_is_mdl_root"):
        bpy.types.Object.bleeds_is_mdl_root = BoolProperty(
            name="BLeeds MDL Root",
            description="Marks this object as the root of an imported BLeeds MDL",
            default=False,
        )

    if not hasattr(bpy.types.Object, "bleeds_mdl_platform"):
        bpy.types.Object.bleeds_mdl_platform = EnumProperty(
            name="Platform",
            description="Stories platform for this MDL",
            items=[
                ("PS2", "PS2", "PlayStation 2"),
                ("PSP", "PSP", "PlayStation Portable"),
            ],
            default="PS2",
        )

    if not hasattr(bpy.types.Object, "bleeds_mdl_type"):
        bpy.types.Object.bleeds_mdl_type = EnumProperty(
            name="MDL Type",
            description="Stories MDL type",
            items=[
                ("PED", "PED", "Ped/character model"),
                ("SIM", "SIM", "Prop model"),
                ("VEH", "VEH", "Vehicle model"),
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
    bpy.utils.unregister_class(EXPORT_PT_MDL_ExportOptions)
    bpy.utils.unregister_class(EXPORT_PT_MDL_LeedsScalePos)
    bpy.utils.unregister_class(EXPORT_OT_MDL_Bake_LeedsScalePos)

    for prop_name in (
        "bleeds_is_mdl_root",
        "bleeds_mdl_platform",
        "bleeds_mdl_type",
        "bleeds_mdl_filepath",
        "bleeds_leeds_scale_base",
        "bleeds_leeds_pos_base",
    ):
        if hasattr(bpy.types.Object, prop_name):
            delattr(bpy.types.Object, prop_name)
