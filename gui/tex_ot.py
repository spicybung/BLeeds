# BLeeds - GUI operators for R* Leeds CHK/XTX/TEX textures
# Author: spicybung
# Years: 2025 -
#
# Import operator that hooks into Blender's File → Import menu
# via the main BLeeds add-on.

import bpy
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, EnumProperty

from ..ops import tex_importer


class IMPORT_OT_tex(Operator, ImportHelper):
    """Import a Rockstar Leeds CHK/XTX/TEX texture list"""

    bl_idname = "import_scene.leeds_tex"
    bl_label = "Import Texture List"
    bl_options = {'PRESET', 'UNDO'}

    filename_ext = ".chk"

    filter_glob: StringProperty(
        name="File Filter",
        description="Filter for texture dictionary files",
        default="*.chk;*.xtx;*.tex",
        options={'HIDDEN'},
        maxlen=255,
    )

    platform: EnumProperty(
        name="Platform",
        description="Decode PSP or PS2 textures (or auto-detect)",
        items=(
            ('auto', "Auto", "Detect format for each texture"),
            ('psp', "PSP", "Force PSP decoding"),
            ('ps2', "PS2", "Force PS2 decoding"),
        ),
        default='auto',
    )

    prefix: StringProperty(
        name="Name Prefix",
        description="Prefix to add in front of imported image names",
        default="",
        maxlen=64,
    )

    def execute(self, context):
        try:
            images = tex_importer.decode_chk_to_blender_images(
                self.filepath,
                platform=self.platform,
                prefix=self.prefix,
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

classes = (IMPORT_OT_tex)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()