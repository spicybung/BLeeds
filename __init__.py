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

__version__ = "1.0.7"

bl_info = {
    "name": "BLeeds",
    "author": "spicybung",
    "version": (1, 0, 7),
    "blender": (2, 90, 0),
    "location": "File > Import / Export",
    "description": "Rockstar Leeds import/export tools for Blender 2.90 and newer",
    "warning": "Work in progress",
    "category": "Import-Export",
}

import bpy
from bpy.utils import register_class, unregister_class
from bpy.props import BoolProperty, EnumProperty, FloatVectorProperty, StringProperty

from .gui import gui
from .compat import getFileImportMenuType, getFileExportMenuType, appendMenu, removeMenu

_classes = [
    gui.IMPORT_OT_Stories_mdl,
    gui.IMPORT_SCENE_OT_leeds_anim,
    gui.DATA_PT_leeds_anim_bone_id,
    gui.IMPORT_OT_COL2,
    gui.EXPORT_OT_COL2,
    gui.IMPORT_OT_tex,
    gui.IMPORT_OT_leeds_world,
    gui.IMPORT_OT_CW_wbl,
    gui.EXPORT_OT_CW_wbl,
    gui.EXPORT_OT_MDL_Bake_LeedsScalePos,
    gui.EXPORT_PT_MDL_LeedsScalePos,
    gui.EXPORT_OT_MDL_StampSemanticAttributes,
    gui.EXPORT_PT_MDL_SemanticAttributes,
    gui.CW_InstanceProps,
    gui.CW_OT_LoadFromCustom,
    gui.CW_OT_SaveToCustom,
    gui.CW_MT_ExportChoice,
    gui.TOPBAR_MT_file_import_bleeds,
    gui.IMPORT_SCENE_OT_stories_lvz,
    gui.EXPORT_SCENE_OT_stories_lvz_img,
    gui.EXPORT_SCENE_OT_stories_mdl_ps2,
]

def register_bleeds_mdl_object_props():
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

    if not hasattr(bpy.types.Object, "bleeds_model_game"):
        bpy.types.Object.bleeds_model_game = EnumProperty(
            name="Models",
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

    if not hasattr(bpy.types.Object, "bleeds_imported_export_mode"):
        bpy.types.Object.bleeds_imported_export_mode = EnumProperty(
            name="Internal PED Rebuild",
            description="Imported PEDs rebuild from live mesh data",
            items=[("REBUILD", "Rebuild", "Rebuild using calculated live data and ped_atomic_bind basis")],
            default="REBUILD",
        )

    if not hasattr(bpy.types.Object, "bleeds_export_use_normals"):
        bpy.types.Object.bleeds_export_use_normals = BoolProperty(
            name="Export Normals",
            description="Export normals into PS2 MDL DMA/VIF geometry streams",
            default=True,
        )

    if not hasattr(bpy.types.Object, "bleeds_leeds_scale_base"):
        bpy.types.Object.bleeds_leeds_scale_base = FloatVectorProperty(
            name="Leeds Scale (Base)",
            description="Base in-game scale stored by the MDL",
            size=3,
            default=(1.0, 1.0, 1.0),
            subtype="XYZ",
        )

    if not hasattr(bpy.types.Object, "bleeds_leeds_pos_base"):
        bpy.types.Object.bleeds_leeds_pos_base = FloatVectorProperty(
            name="Leeds Pos (Base)",
            description="Base in-game position stored by the MDL",
            size=3,
            default=(0.0, 0.0, 0.0),
            subtype="TRANSLATION",
        )

def unregister_bleeds_mdl_object_props():
    for prop_name in (
        "bleeds_is_mdl_root",
        "bleeds_mdl_platform",
        "bleeds_model_game",
        "bleeds_mdl_type",
        "bleeds_mdl_filepath",
        "bleeds_imported_export_mode",
        "bleeds_export_use_normals",
        "bleeds_leeds_scale_base",
        "bleeds_leeds_pos_base",
    ):
        if hasattr(bpy.types.Object, prop_name):
            delattr(bpy.types.Object, prop_name)

def register():
    register_bleeds_mdl_object_props()

    for cls in _classes:
        register_class(cls)

    bpy.types.Object.cw_instance = bpy.props.PointerProperty(
        type=gui.CW_InstanceProps
    )

    appendMenu(getFileImportMenuType(), gui.cw_menu_import)
    appendMenu(getFileExportMenuType(), gui.cw_menu_export)

def unregister():
    removeMenu(getFileImportMenuType(), gui.cw_menu_import)
    removeMenu(getFileExportMenuType(), gui.cw_menu_export)

    if hasattr(bpy.types.Object, "cw_instance"):
        del bpy.types.Object.cw_instance

    for cls in reversed(_classes):
        unregister_class(cls)

    unregister_bleeds_mdl_object_props()
