# BLeeds - Scripts for working with R* Leeds (GTA Stories, Manhunt 2, etc) formats in Blender
# Author: spicybung
# Years: 2025 - 2026

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
from bpy_extras.io_utils import ImportHelper
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator

from ..ops import world_importer
from . import drawImportLogOptions, runImport

class IMPORT_OT_leeds_world(Operator, ImportHelper):

    bl_idname = "import_scene.leeds_world"
    bl_label = "Import World Level"
    bl_description = "Import Rockstar Leeds .WRLD, .BSP"
    bl_options = {"UNDO"}
    filename_ext = ".wrld"
    filter_glob: StringProperty(
        default="*.wrld;*.bsp;*.WRLD;*.BSP",
        options={"HIDDEN"},
        maxlen=255,
    )

    import_textures: BoolProperty(name="Import Textures", default=True)
    print_debug_log: BoolProperty(name="Print Debug Log", default=False)
    print_text_log: BoolProperty(name="Print Text Log", default=False)

    def draw(self, context):
        self.layout.prop(self, "import_textures")
        drawImportLogOptions(self.layout, self)

    def execute(self, context):
        return runImport(self, context, self.executeImport)

    def executeImport(self, context):
        try:

            from pathlib import Path
            from ..rwLib.dff import unwrapResource
            raw = unwrapResource(Path(self.filepath).read_bytes())
            if raw[:4] == b"DLRW":
                from ..ops.world_importer import importWorld
                importWorld(context,self.filepath,import_textures=self.import_textures)
                return {"FINISHED"}
            world_importer.log_and_import(
                self.filepath,
                decode_textures=self.import_textures,
                write_log=False,
                build_models=True,
            )
        except Exception as exc:
            print("World Level import failed: {}".format(exc))
            self.report({'ERROR'}, f"Failed to import World Level: {exc}")
            return {"CANCELLED"}
        from ..ops.uv_playback import requestNativeUvPlayback
        requestNativeUvPlayback(context)
        return {'FINISHED'}

def menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_leeds_world.bl_idname, text="R* Leeds: World Level (.wrld, .bsp)")

classes = (IMPORT_OT_leeds_world,)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
