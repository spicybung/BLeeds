import importlib
import bpy

from . import mdl_importer
from . import mdl_parser
from . import matrix_utils

bl_info = {
    "name": "Manhunt 2 MDL Importer",
    "author": "spicybung",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "File > Import > MDL (.mdl)",
    "description": "Importer for Manhunt 2 .mdl models.",
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
