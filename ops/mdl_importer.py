import bpy
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from . import mdl_parser

class IMPORT_OT_mdl(Operator, ImportHelper):
    bl_idname = "import_scene.mdl"
    bl_label = "Import Manhunt 2 MDL"
    filename_ext = ".mdl"
    filter_glob: bpy.props.StringProperty(default="*.mdl", options={'HIDDEN'})

    def execute(self, context):
        print(f"Starting import of MDL: {self.filepath}")
        
        try:
            # This will invoke all the parsing and Blender object creation
            mdl_parser.read_mdl(self.filepath, context)
            print("✅ MDL import finished successfully.")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to import MDL: {str(e)}")
            print(f"❌ Import failed: {e}")
            return {'CANCELLED'}
        
        return {'FINISHED'}

def menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_mdl.bl_idname, text="Manhunt 2 MDL (.mdl)")

def register():
    bpy.utils.register_class(IMPORT_OT_mdl)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.utils.unregister_class(IMPORT_OT_mdl)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

if __name__ == "__main__":
    register()
