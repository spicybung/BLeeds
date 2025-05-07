bl_info = {
    "name": "MDL Importer",
    "author": "YourName",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "File > Import > MDL (.mdl)",
    "description": "Import MDL models (e.g. Manhunt 2 format)",
    "category": "Import-Export"
}

import importlib
from . import ops, ui

modules = [ops.mdl_importer, ui.import_panel]

def register():
    for mod in modules:
        importlib.reload(mod)
        mod.register()

def unregister():
    for mod in reversed(modules):
        mod.unregister()

if __name__ == "__main__":
    register()
