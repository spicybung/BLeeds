# BLeeds - Scripts for working with R* Leeds (GTA Stories, Manhunt 2, etc) formats in Blender
# Author: SpicyBung
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
