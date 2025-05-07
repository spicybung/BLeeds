import bpy
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from ..utils import mdl_parser

class IMPORT_OT_mdl(Operator, ImportHelper):
    bl_idname = "import_scene.mdl"
    bl_label = "Import MDL"
    filename_ext = ".mdl"

    def execute(self, context):
        mdl_parser.read_mdl(self.filepath, context)
        return {'FINISHED'}

def register():
    bpy.utils.register_class(IMPORT_OT_mdl)

def unregister():
    bpy.utils.unregister_class(IMPORT_OT_mdl)
