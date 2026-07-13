# BLeeds - Scripts for working with R* Leeds (GTA Stories, Chinatown Wars, Manhunt 2, etc) formats in Blender
# Author: spicybung
# Years: 2025 - 2026

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

import bpy

from .. import infer_bleeds_entity_type
from bpy.props import (
    StringProperty,
    PointerProperty,
)
from bpy.types import (
    PropertyGroup,
    Operator,
    Panel,
    Menu,
)

class OBJECT_PT_bleeds_entity_stamp(Panel):
    bl_idname = "OBJECT_PT_bleeds_entity_stamp"
    bl_label = "BLeeds - Object"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"

    @classmethod
    def poll(cls, context):
        obj = getattr(context, "object", None)
        return obj is not None and infer_bleeds_entity_type(obj) != "UNKNOWN"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        obj = context.object
        inferred = infer_bleeds_entity_type(obj)

        # New imports carry the persistent enum. Legacy BLeeds objects are still
        # identified from their existing namespaced properties and shown clearly.
        stored = str(getattr(obj, "bleeds_entity_type", "UNKNOWN") or "UNKNOWN")
        box = layout.box()
        if stored != "UNKNOWN":
            box.prop(obj, "bleeds_entity_type", text="Type")
        else:
            labels = {"OBJECT": "Object", "COLLISION": "Collision", "2DFX": "2DFX"}
            row = box.row()
            row.label(text="Type")
            row.label(text=labels.get(inferred, "Unknown"))

        if inferred == "OBJECT":
            res_id = obj.get("blds_res_id", obj.get("blds_res_index", obj.get("blds_missing_requested_res_id", None)))
            row_link_id = obj.get("blds_row_link_id", obj.get("blds_ipl_id", obj.get("blds_img_ipl_id", obj.get("blds_missing_requested_ipl_id", None))))
            game_model_id = obj.get("blds_game_model_id", None)
            game_model_name = str(obj.get("blds_game_model_name", ""))
            if res_id is not None:
                box.label(text=f"RES ID: {int(res_id)}")
            if row_link_id is not None:
                box.label(text=f"ROWLINK ID: {int(row_link_id)}")
            if game_model_id is not None and int(game_model_id) >= 0:
                label = f"GAME MODEL ID: {int(game_model_id)}"
                if game_model_name:
                    label += f" ({game_model_name})"
                box.label(text=label)
                if str(obj.get("blds_identity_source", "")) == "MASTER_AERA_SECONDARY_ID":
                    area_index = int(obj.get("blds_identity_area_index", -1))
                    area_resource = int(obj.get("blds_identity_area_resource_index", -1))
                    if area_index >= 0 and area_resource >= 0:
                        box.label(text=f"AERA Identity: area {area_index}, resource {area_resource}")
            source = obj.get("blds_model_source", obj.get("blds_source", obj.get("blds_kind", "")))
            if source:
                box.label(text=f"Source: {source}")
        elif inferred == "COLLISION":
            shape = str(obj.get("bleeds_col2_shape", ""))
            if shape:
                box.label(text=f"Shape: {shape}")
            if obj.get("bleeds_col2_resource_id") is not None:
                box.label(text=f"Resource ID: {int(obj.get('bleeds_col2_resource_id', 0))}")
        elif inferred == "2DFX":
            effect_names = {0: "Light", 1: "Particle", 2: "Attractor", 3: "Ped Behaviour"}
            effect_type = int(obj.get("blds_2dfx_effect_type", -1))
            box.label(text=f"Effect: {effect_names.get(effect_type, 'Unknown')} ({effect_type})")
            if obj.get("blds_2dfx_visible_res_id") is not None:
                box.label(text=f"Model RES: {int(obj.get('blds_2dfx_visible_res_id', -1))}")
            if obj.get("blds_2dfx_game_model_id") is not None:
                box.label(text=f"GAME MODEL ID: {int(obj.get('blds_2dfx_game_model_id', -1))}")
            row_link = obj.get("blds_2dfx_row_link_id", obj.get("blds_2dfx_placement_ipl_id", None))
            if row_link is not None:
                box.label(text=f"ROWLINK ID: {int(row_link)}")
            source = str(obj.get("blds_2dfx_source", ""))
            if source:
                box.label(text=f"Source: {source}")


class CW_InstanceProps(PropertyGroup):
    mdl_name: StringProperty(
        name="Instance MDL",
        description="Name of the MDL associated with this instance",
        default="",
    )
    custom_id: StringProperty(
        name="Custom ID",
        description="Custom identifier for this CW instance",
        default="",
    )

class CW_OT_LoadFromCustom(Operator):
    bl_idname = "cw_instance.load_from_custom"
    bl_label = "Load from Custom"
    bl_description = "Load instance data from custom field"

    def execute(self, context):
        obj = context.object
        if obj is None or not hasattr(obj, "cw_instance"):
            self.report({"ERROR"}, "No active object or CW instance property.")
            return {"CANCELLED"}

        inst = obj.cw_instance

        self.report({"INFO"}, f"Loaded from custom ID: {inst.custom_id}")
        return {"FINISHED"}

class CW_OT_SaveToCustom(Operator):
    bl_idname = "cw_instance.save_to_custom"
    bl_label = "Save to Custom"
    bl_description = "Save instance data to custom field"

    def execute(self, context):
        obj = context.object
        if obj is None or not hasattr(obj, "cw_instance"):
            self.report({"ERROR"}, "No active object or CW instance property.")
            return {"CANCELLED"}

        inst = obj.cw_instance

        self.report({"INFO"}, f"Saved to custom ID: {inst.custom_id}")
        return {"FINISHED"}

class CW_MT_ExportChoice(Menu):
    bl_idname = "CW_MT_ExportChoice"
    bl_label = "BLeeds"

    def draw(self, context):
        layout = self.layout
        layout.operator(
            "export_scene.bleeds_stories_mdl",
            text="R* Leeds: Model (.mdl)",
        )
        layout.operator(
            "export_scene.leeds_lvz_img",
            text="R* Leeds: LeVelZlib IMG Archive (.lvz + .img)",
        )
        layout.operator(
            "export_scene.col2_leeds",
            text="R* Leeds: Collision Archive (.col2)",
        )
        layout.operator(
            "export_scene.cw_wbl",
            text="R* Leeds: Worldblock (.wbl)",
        )

class TOPBAR_MT_file_import_bleeds(Menu):
    bl_idname = "TOPBAR_MT_file_import_bleeds"
    bl_label = "BLeeds"

    def draw(self, context):
        layout = self.layout
        layout.operator(
            "import_scene.bleeds_stories_mdl",
            text="R* Leeds: Model (.mdl)",
        )
        layout.operator(
            "import_scene.leeds_anim",
            text="R* Leeds: Animation (.anim)",
        )
        layout.operator(
            "import_scene.col2_leeds",
            text="R* Leeds: Collision Archive (.col2)",
        )
        layout.operator(
            "import_scene.leeds_tex",
            text="R* Leeds: Texture Dictionary (.chk, .xtx, .tex)",
        )
        layout.operator(
            "import_scene.leeds_lvz_img",
            text="R* Leeds: LeVelZlib IMG Archive (.lvz + .img)",
        )
        layout.operator(
            "import_scene.leeds_world",
            text="R* Leeds: World Level (.wrld)",
        )
        layout.operator(
            "import_scene.cw_wbl",
            text="R* Leeds: Worldblock (.wbl)",
        )

def cw_menu_import(self, context):
    self.layout.menu(TOPBAR_MT_file_import_bleeds.bl_idname)

def cw_menu_export(self, context):
    self.layout.menu(CW_MT_ExportChoice.bl_idname)
