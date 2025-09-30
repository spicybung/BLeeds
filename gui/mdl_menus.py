# BLeeds - Scripts for working with R* Leeds (GTA Stories, Chinatown Wars, Manhunt 2, etc) formats in Blender
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

from bpy.props import StringProperty, FloatProperty, BoolProperty, IntProperty

class CW_InstanceProps(bpy.types.PropertyGroup):
    wbl_name: StringProperty(name="WBL Name", description="Name shown for this imported WBL chunk or instance", default="")
    mdl_name: StringProperty(name="MDL Name", description="MDL identifier or source filename without extension", default="")
    import_scale: FloatProperty(name="Import Scale", description="Scale applied when building meshes from WBL/MDL data", default=1.0, min=0.0001, max=1000.0, soft_min=0.001, soft_max=100.0)
    uv_offset: FloatProperty(name="UV Offset", description="Horizontal UV offset applied to imported vertices", default=0.0)
    is_light: BoolProperty(name="Is Light", description="Marks this object as a light parsed from the source", default=False)
    part_index: IntProperty(name="Part Index", description="Part index inside the source block (mesh index)", default=0, min=0)
    flags: IntProperty(name="Flags", description="Flags parsed from the source entry", default=0, min=0)

class CW_OT_LoadFromCustom(bpy.types.Operator):
    """Load Rockstar Leeds custom block into the active object"""
    bl_idname = "object.cw_load_from_custom"
    bl_label = "Load From Custom"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.object
        if obj is None:
            self.report({'ERROR'}, "No active object")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Loaded custom data into: {obj.name}")
        return {'FINISHED'}


class CW_OT_SaveToCustom(bpy.types.Operator):
    """Save active object's data back into a Rockstar Leeds custom block"""
    bl_idname = "object.cw_save_to_custom"
    bl_label = "Save To Custom"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.object
        if obj is None:
            self.report({'ERROR'}, "No active object")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Saved custom data from: {obj.name}")
        return {'FINISHED'}


class CW_PT_Instance(bpy.types.Panel):
    """Sidebar panel to view/edit CW_InstanceProps and trigger load/save"""
    bl_label = "BLeeds Instance"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BLeeds"

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def draw(self, context):
        layout = self.layout
        obj = context.object
        inst = getattr(obj, "cw_instance", None)

        if inst is None:
            layout.label(text="cw_instance not set on this object", icon="INFO")
            layout.operator("object.cw_load_from_custom", icon="IMPORT")
            return

        col = layout.column(align=True)
        col.prop(inst, "wbl_name")
        col.prop(inst, "mdl_name")
        col.prop(inst, "import_scale")
        col.prop(inst, "uv_offset")
        col.prop(inst, "is_light")
        col.prop(inst, "part_index")
        col.prop(inst, "flags")

        row = layout.row(align=True)
        row.operator("object.cw_load_from_custom", icon="IMPORT")
        row.operator("object.cw_save_to_custom", icon="EXPORT")

class CW_MT_ImportChoice(bpy.types.Menu):
    """File > Import menu for Rockstar Leeds formats"""
    bl_idname = "CW_MT_import_choice"
    bl_label = "Rockstar Leeds Import"

    def draw(self, context):
        layout = self.layout
        layout.operator("import_scene.cw_wbl", text="CW WBL (.wbl)")
        layout.operator("import_scene.cw_mdl", text="CW MDL (.mdl)")
        layout.operator("import_scene.mh2_mdl", text="MH2 MDL (.mdl)")


class CW_MT_ExportChoice(bpy.types.Menu):
    """File > Export menu for Rockstar Leeds formats"""
    bl_idname = "CW_MT_export_choice"
    bl_label = "Rockstar Leeds Export"

    def draw(self, context):
        layout = self.layout
        layout.operator("export_scene.cw_wbl", text="WBL (.wbl)")

class TOPBAR_MT_file_import_bleeds(bpy.types.Menu):
    bl_idname = "TOPBAR_MT_file_import_bleeds"
    bl_label  = "BLeeds"

    def draw(self, context):
        layout = self.layout
        layout.operator("import_scene.cw_wbl",
                        text="R* Leeds: Chinatown Wars Worldblock (.wbl)",
                        icon='MESH_GRID')
        layout.operator("import_scene.mh2_mdl",
                text="R* Leeds: Manhunt 2 Model (.mdl)",
                icon='MESH_GRID')

def _menu_import_append(self, context):
    self.layout.menu(TOPBAR_MT_file_import_bleeds.bl_idname)

def cw_menu_import(self, context):
    self.layout.menu(TOPBAR_MT_file_import_bleeds.bl_idname)

def cw_menu_export(self, context):
    layout = self.layout
    layout.operator("export_scene.cw_wbl", text="Rockstar Leeds: WBL (.wbl)")

classes = (CW_InstanceProps,
           CW_OT_LoadFromCustom,
           CW_OT_SaveToCustom,
           CW_PT_Instance,
           TOPBAR_MT_file_import_bleeds
           )
def register():
    for c in classes: bpy.utils.register_class(c)
    bpy.utils.register_class(TOPBAR_MT_file_import_bleeds)
    bpy.types.TOPBAR_MT_file_import.append(_menu_import_append)
def unregister():
    for c in reversed(classes): bpy.utils.unregister_class(c)
    bpy.types.TOPBAR_MT_file_import.remove(_menu_import_append)
    bpy.utils.unregister_class(TOPBAR_MT_file_import_bleeds)