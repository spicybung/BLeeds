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

import bpy
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

#######################################################
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
            text="R* Leeds: 3D Model (.mdl)",
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
            text="R* Leeds: 3D Model (.mdl)",
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
