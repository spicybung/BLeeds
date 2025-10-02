# BLeeds - Scripts for working with R* Leeds (GTA Stories, Chinatown Wars, Manhunt 2, etc) formats in Blender
# Author: spicybung
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

import bpy
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, BoolProperty

from ..gtaLib.mdl_mh2 import import_mh2


class IMPORT_OT_MH2_MDL(bpy.types.Operator, ImportHelper):
    """Import Rockstar Leeds Manhunt 2 MDL"""
    bl_idname = "import_scene.bleeds_mh2_mdl"
    bl_label = "Import an Manhunt 2 Model (.mdl)"
    bl_options = {'UNDO'}

    filename_ext = ".mdl"
    filter_glob: StringProperty(default="*.mdl", options={'HIDDEN'})

    group_into_collection: BoolProperty(
        name="Group into Collection",
        default=True,
        description="Put imported objects into a new collection"
    )

    def execute(self, context):
        ok = import_mh2(self.filepath, context,
                        collection_name=None if self.group_into_collection else None)
        return {'FINISHED'} if ok else {'CANCELLED'}
