# BLeeds - Blender operator definitions for Leeds world importer
# Author: spicybung
# Years: 2025 -
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import bpy
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty
from bpy.types import Operator

from ..ops import world_importer


class IMPORT_OT_leeds_world(Operator, ImportHelper):
    """Import a Rockstar Leeds World"""

    bl_idname = "import_scene.leeds_world"
    bl_label = "Import World"
    bl_options = {"UNDO"}
    filename_ext = ".wrld"
    filter_glob: StringProperty(
        default="*.wrld",
        options={"HIDDEN"},
        maxlen=255,
    )

    def execute(self, context):
        try:
            world_importer.log_and_import(
                self.filepath,
                decode_textures=True,
                write_log=True,
                build_models=True,
            )
        except Exception as exc:
            self.report({'ERROR'}, f"Failed to import WRLD: {exc}")
            raise
        return {'FINISHED'}


def menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_leeds_world.bl_idname, text="R* Leeds: World (.wrld)")


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
