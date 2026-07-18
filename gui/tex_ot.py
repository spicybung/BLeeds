# BLeeds - GUI operators for R* Leeds CHK/XTX/TEX textures
# Author: spicybung
# Years: 2025 - 2026
#
# Import operator that hooks into Blender's File → Import menu
# via the main BLeeds add-on.

import bpy
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty

from ..ops import tex_importer

class IMPORT_OT_tex(Operator, ImportHelper):

    bl_idname = "import_scene.leeds_tex"
    bl_label = "Import Texture List"
    bl_description = "Import textures from a Rockstar Leeds CHK, XTX, or TEX file"
    bl_options = {'UNDO'}

    filename_ext = ".xtx"

    filter_glob: StringProperty(
        name="File Filter",
        description="Filter for texture dictionary files",
        default="*.chk;*.xtx;*.tex",
        options={'HIDDEN'},
        maxlen=255,
    )

    def execute(self, context):
        try:
            images = tex_importer.decode_chk_to_blender_images(
                self.filepath,
                platform="auto",
                prefix="",
            )
        except Exception as exc:
            self.report({'ERROR'}, f"Failed to import textures: {exc}")
            return {'CANCELLED'}

        name = bpy.path.display_name_from_filepath(self.filepath)
        count = len(images)
        if count == 0:
            self.report({'WARNING'}, f"No textures were decoded from '{name}'.")
        else:
            self.report({'INFO'}, f"Imported {count} textures from '{name}'.")

        return {'FINISHED'}

classes = (IMPORT_OT_tex,)

def register():
    for c in classes:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)

if __name__ == "__main__":
    register()
