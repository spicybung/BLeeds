import bpy

def menu_func_import(self, context):
    self.layout.operator("import_scene.mdl", text="MDL (.mdl)")

def register():
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
