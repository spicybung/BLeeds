# SPDX-License-Identifier: GPL-3.0-or-later
# BLeeds - R* Leeds tools for Blender
# Author: spicybung
# Years: 2025 -
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License
# as published by the Free Software Foundation, either version 3 of the License,
# or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty
# of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

bl_info = {
    "name": "BLeeds",
    "author": "spicybung",
    "version": (1, 0, 2),
    "blender": (3, 0, 0),
    "location": "File > Import / Export",
    "description": "Import/export for Rockstar Leeds formats",
    "warning": "Work In Progress",
    "category": "Import-Export",
}

import bpy
from bpy.utils import register_class, unregister_class

from .gui import gui


_classes = [
    gui.IMPORT_OT_Stories_mdl,
    gui.IMPORT_OT_COL2,
    gui.IMPORT_OT_tex,
    gui.IMPORT_OT_leeds_world,
    gui.IMPORT_OT_CW_wbl,
    gui.EXPORT_OT_CW_wbl,
    gui.EXPORT_OT_MDL_Bake_LeedsScalePos,
    gui.EXPORT_PT_MDL_LeedsScalePos,
    gui.EXPORT_PT_MDL_ExportOptions,
    gui.CW_InstanceProps,
    gui.CW_OT_LoadFromCustom,
    gui.CW_OT_SaveToCustom,
    gui.CW_MT_ExportChoice,
    gui.TOPBAR_MT_file_import_bleeds,
    gui.IMPORT_SCENE_OT_stories_lvz,
    gui.EXPORT_SCENE_OT_stories_mdl_ps2,
]


def register():
    for cls in _classes:
        register_class(cls)

    bpy.types.Object.cw_instance = bpy.props.PointerProperty(
        type=gui.CW_InstanceProps
    )

    if (2, 80, 0) > bpy.app.version:
        bpy.types.INFO_MT_file_import.append(gui.cw_menu_import)
        bpy.types.INFO_MT_file_export.append(gui.cw_menu_export)
    else:
        bpy.types.TOPBAR_MT_file_import.append(gui.cw_menu_import)
        bpy.types.TOPBAR_MT_file_export.append(gui.cw_menu_export)



def unregister():
    if (2, 80, 0) > bpy.app.version:
        bpy.types.INFO_MT_file_import.remove(gui.cw_menu_import)
        bpy.types.INFO_MT_file_export.remove(gui.cw_menu_export)
    else:
        bpy.types.TOPBAR_MT_file_import.remove(gui.cw_menu_import)
        bpy.types.TOPBAR_MT_file_export.remove(gui.cw_menu_export)

    del bpy.types.Object.cw_instance

    for cls in reversed(_classes):
        unregister_class(cls)
