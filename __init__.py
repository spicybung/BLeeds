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

import bpy

from bpy.utils import register_class, unregister_class
from .gui import gui


bl_info = {
    "name": "BLeeds",
    "author": "SpicyBung",
    "version": (0, 0, 1),
    "blender": (2, 80, 0),
    "category": "Import-Export",
    "location": "File > Import/Export; Properties > Object",
    "description": "Import/Export for Leeds Engine file formats",
}

_classes = [
    gui.IMPORT_OT_CW_mdl,
    gui.EXPORT_OT_CW_mdl,
    gui.IMPORT_OT_MH2_mdl,
    gui.IMPORT_OT_CW_wbl,
    gui.EXPORT_OT_CW_wbl,
    gui.CW_InstanceProps,
    gui.CW_OT_LoadFromCustom,
    gui.CW_OT_SaveToCustom,
    gui.CW_PT_Instance,
    gui.CW_MT_ImportChoice,
    gui.CW_MT_ExportChoice,
    gui.TOPBAR_MT_file_import_bleeds
]

def register():
    for cls in _classes:
        register_class(cls)

    bpy.types.Object.cw_instance = bpy.props.PointerProperty(type=gui.CW_InstanceProps)

    if (2, 80, 0) > bpy.app.version:
        bpy.types.INFO_MT_file_import.append(gui.cw_menu_import)
    else:
        bpy.types.TOPBAR_MT_file_import.append(gui.cw_menu_import)

def unregister():
    if (2, 80, 0) > bpy.app.version:
        bpy.types.INFO_MT_file_import.remove(gui.cw_menu_import)
        bpy.types.INFO_MT_file_export.remove(gui.cw_menu_import)
    else:
        bpy.types.TOPBAR_MT_file_import.remove(gui.cw_menu_import)

    if hasattr(bpy.types.Object, "cw_instance"):
        del bpy.types.Object.cw_instance

    for cls in reversed(_classes):
        unregister_class(cls)

if __name__ == "__main__":
    register()
