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

import importlib
import bpy

from . import mdl_importer
from . import mdl_parser
from . import matrix_utils

bl_info = {
    "name": "BLeeds",
    "author": "spicybung",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "File > Import > MDL (.mdl)",
    "description": "Import Leeds GTA Stories/CW & Manhunt 2 .MDL model(s).",
    "category": "Import-Export"
}

modules = [mdl_importer, mdl_parser, matrix_utils]

def register():
    for mod in modules:
        importlib.reload(mod)
        if hasattr(mod, "register"):
            mod.register()
    bpy.types.TOPBAR_MT_file_import.append(mdl_importer.menu_func_import)

def unregister():
    for mod in reversed(modules):
        if hasattr(mod, "unregister"):
            mod.unregister()
    bpy.types.TOPBAR_MT_file_import.remove(mdl_importer.menu_func_import)

if __name__ == "__main__":
    register()
