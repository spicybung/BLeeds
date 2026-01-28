# BLeeds - R* Leeds COL2 operators (ImportHelper etc.)
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
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import bpy
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty

from ..ops import col2_importer


class IMPORT_OT_COL2(Operator, ImportHelper):
    """Import a Rockstar Leeds COL2 collision library"""
    bl_idname = "import_scene.col2_leeds"
    bl_label = "Rockstar Leeds Collision"
    bl_options = {"PRESET", "UNDO"}

    filename_ext = ".col2"
    filter_glob: StringProperty(default="*.col2;*.COL2", options={"HIDDEN"})

    def execute(self, context):
        created, _report = col2_importer.import_col2_file(self.filepath, context)
        self.report(
            {"INFO"},
            f"COL2 parsed. Objects created: {len(created)}",
        )
        return {"FINISHED"}
