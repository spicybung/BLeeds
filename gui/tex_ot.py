# BLeeds - GUI operators for R* Leeds CHK/XTX/TEX textures
# Author: spicybung
# Years: 2025 - 2026

import os

import bpy
from bpy.types import Operator, Panel
from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.props import StringProperty

from ..ops import tex_importer


class IMPORT_OT_tex(Operator, ImportHelper):
    bl_idname = "import_scene.leeds_tex"
    bl_label = "Import Texture"
    bl_description = "Decode a Rockstar Leeds CHK/XTX/TEX texture container"
    bl_options = {"UNDO"}

    filename_ext = ".xtx"
    filter_glob: StringProperty(
        name="File Filter",
        description="Filter for Leeds texture container files",
        default="*.chk;*.xtx;*.tex",
        options={"HIDDEN"},
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
            self.report({"ERROR"}, f"Failed to import textures: {exc}")
            return {"CANCELLED"}

        name = bpy.path.display_name_from_filepath(self.filepath)
        count = len(images)
        if count == 0:
            self.report({"WARNING"}, f"No textures were decoded from '{name}'.")
        else:
            self.report({"INFO"}, f"Imported {count} textures from '{name}'.")
        return {"FINISHED"}


class EXPORT_OT_tex(Operator, ExportHelper):
    bl_idname = "export_scene.leeds_tex"
    bl_label = "Export Texture"
    bl_description = "Export image textures used by the selected objects to a Leeds CHK/XTX/TEX container"

    filename_ext = ".xtx"
    filter_glob: StringProperty(
        default="*.chk;*.xtx;*.tex",
        options={"HIDDEN"},
        maxlen=255,
    )

    def invoke(self, context, event):
        scene = context.scene
        extension = str(getattr(scene, "bleeds_texture_format", "XTX") or "XTX").lower()
        self.filename_ext = "." + extension
        self.filter_glob = "*.chk;*.xtx;*.tex"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        scene = context.scene
        extension = str(getattr(scene, "bleeds_texture_format", "XTX") or "XTX").lower()
        platform = str(getattr(scene, "bleeds_texture_platform", "PS2") or "PS2").upper()

        filepath = str(self.filepath or "")
        root, current_extension = os.path.splitext(filepath)
        if current_extension.lower() not in {".chk", ".xtx", ".tex"}:
            filepath = root + "." + extension

        try:
            from ..ops import tex_exporter
            images = tex_exporter.collect_images_from_context(context)
            bit_depth = getattr(scene, "bleeds_texture_bit_depth", "AUTO")
            count = tex_exporter.export_leeds_texture_container(filepath, images, platform=platform, bit_depth=bit_depth)
        except Exception as exc:
            self.report({"ERROR"}, f"Failed to export texture container: {exc}")
            return {"CANCELLED"}

        self.report({"INFO"}, f"Exported {count} texture(s): {filepath}")
        return {"FINISHED"}


class SCENE_PT_bleeds_texture_io(Panel):
    bl_idname = "SCENE_PT_bleeds_texture_io"
    bl_label = "BLeeds - Texture I/O"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.use_property_split = True
        layout.use_property_decorate = False

        column = layout.column(align=True)
        column.prop(scene, "bleeds_texture_format", text="Texture Format")
        column.prop(scene, "bleeds_texture_platform", text="Platform")
        column.prop(scene, "bleeds_texture_bit_depth", text="Bit Depth")

        row = layout.row(align=True)
        row.operator("import_scene.leeds_tex", text="Import Texture", icon="IMPORT")
        row.operator("export_scene.leeds_tex", text="Export Texture", icon="EXPORT")




classes = (IMPORT_OT_tex, EXPORT_OT_tex, SCENE_PT_bleeds_texture_io)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
