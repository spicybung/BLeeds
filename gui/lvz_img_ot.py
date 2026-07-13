# BLeeds - Scripts for working with R* Leeds (GTA Stories, Chinatown Wars, Manhunt 2, etc) formats in Blender
# Author: spicybung
# Years: 2025 - 2026

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

from pathlib import Path

import bpy
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.props import StringProperty, BoolProperty
from ..leedsLib import lvz_img as LVZ
from ..ops import lvz_img_importer


class IMPORT_SCENE_OT_stories_lvz(Operator, ImportHelper):
    bl_idname = "import_scene.leeds_lvz_img"
    bl_label = "Import LVZ + IMG"
    bl_description = "Import a map from a matching Rockstar Leeds LVZ and IMG pair"
    bl_options = {'REGISTER'}

    filename_ext = ".lvz"

    csv_dedup_res_ids: BoolProperty(
        name="CSV unique + log detailed blocks",
        default=True,
    )
    apply_img_transforms: BoolProperty(
        name="Apply IMG transforms to MDL objects",
        default=True,
    )
    debug_print: BoolProperty(
        name="Debug print",
        default=False,
    )
    write_debug_log: BoolProperty(
        name="Write debug log next to LVZ",
        default=True,
    )

    filter_glob: StringProperty(
        default="*.lvz;*.LVZ",
        options={'HIDDEN'},
        maxlen=255,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "csv_dedup_res_ids")
        layout.prop(self, "apply_img_transforms")
        layout.prop(self, "debug_print")
        layout.prop(self, "write_debug_log")
        layout.separator()
        layout.label(text="IMG and GAME.DTZ are auto-detected beside the LVZ.", icon='INFO')

    def execute(self, context):
        try:
            return lvz_img_importer.import_lvz_img_archive(
                operator=self,
                context=context,
                lvz_path=self.filepath,
                csv_dedup_res_ids=self.csv_dedup_res_ids,
                apply_img_transforms=self.apply_img_transforms,
                debug_print=self.debug_print,
                write_debug_log=self.write_debug_log,
                game_dtz_path="",
                import_game_dtz_2dfx=True,
            )
        except Exception as exc:
            lvz_img_importer.finish_active_import_progress(context, succeeded=False, message="Import failed")
            self.report({'ERROR'}, "LVZ + IMG import failed: {}".format(exc))
            return {'CANCELLED'}
        finally:
            lvz_img_importer.finish_active_import_progress(context)

class EXPORT_SCENE_OT_stories_lvz_img(Operator, ExportHelper):
    bl_idname = "export_scene.leeds_lvz_img"
    bl_label = "Export LVZ + IMG"
    bl_description = "Export map data to a Rockstar Leeds LVZ and IMG pair"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".lvz"

    filter_glob: StringProperty(
        default="*.lvz;*.LVZ",
        options={'HIDDEN'},
        maxlen=255,
    )

    source_lvz_path: StringProperty(
        name="Source LVZ",
        description="Original LVZ to use as the LVZ carrier/base. Imported objects stamp this automatically.",
        default="",
        subtype='FILE_PATH',
    )

    source_img_path: StringProperty(
        name="Source IMG",
        description="Original IMG to rewrite. If empty, BLeeds looks next to Source LVZ.",
        default="",
        subtype='FILE_PATH',
    )

    selected_only: BoolProperty(
        name="Selected objects only",
        description="Only update IMG rows for selected imported LVZ objects",
        default=False,
    )

    update_transforms: BoolProperty(
        name="Write IMG transforms",
        description="Write live Blender object matrix_world values back into IMG instance rows",
        default=True,
    )

    update_bounds: BoolProperty(
        name="Write IMG bounds",
        description="Recalculate the IMG half-float bounding sphere from each mesh object's local vertices",
        default=True,
    )

    update_all_matching_instances: BoolProperty(
        name="Update all matching RES instances",
        description="When an object has no exact IMG row stamp, update every IMG row with the same RES id instead of only the first one",
        default=False,
    )

    update_textures: BoolProperty(
        name="Write LVZ textures marked dirty",
        description="Only re-encode LVZ textures whose material/image is explicitly marked dirty/exportable; unchanged textures are preserved",
        default=False,
    )

    texture_swizzle_ps2: BoolProperty(
        name="PS2 texture swizzle",
        description="Write PS2-style swizzled 4bpp texture indices for LVZ texture resources",
        default=True,
    )

    write_debug_log: BoolProperty(
        name="Write export log",
        description="Write an LVZ+IMG export log next to the output LVZ",
        default=True,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "source_lvz_path")
        layout.prop(self, "source_img_path")
        layout.separator()
        layout.prop(self, "selected_only")
        layout.prop(self, "update_transforms")
        layout.prop(self, "update_bounds")
        layout.prop(self, "update_all_matching_instances")
        layout.separator()
        layout.prop(self, "update_textures")
        if self.update_textures:
            box = layout.box()
            box.label(text="Only textures marked dirty/exportable are rewritten.")
            box.label(text="Unmarked LVZ texture blobs are preserved.")
            box.label(text="Texture swizzle is auto-detected from the LVZ platform.")
        layout.prop(self, "write_debug_log")

    def invoke(self, context, event):
        objects = LVZ.collect_lvz_img_export_objects(context, selected_only=False)
        if objects:
            if not self.source_lvz_path:
                self.source_lvz_path = LVZ.find_source_path_from_objects(objects, "blds_source_lvz_path")
            if not self.source_img_path:
                self.source_img_path = LVZ.find_source_path_from_objects(objects, "blds_source_img_path")
            if not self.source_img_path and self.source_lvz_path:
                self.source_img_path = LVZ.find_source_img_next_to_lvz(self.source_lvz_path)
        return ExportHelper.invoke(self, context, event)

    def execute(self, context):
        if not self.filepath:
            self.report({'ERROR'}, "No output LVZ path selected.")
            return {'CANCELLED'}
        try:
            auto_swizzle_ps2 = True
            source_for_platform = self.source_lvz_path
            if not source_for_platform:
                source_for_platform = LVZ.find_source_path_from_objects(
                    LVZ.collect_lvz_img_export_objects(context, selected_only=False),
                    "blds_source_lvz_path"
                )
            if source_for_platform:
                try:
                    raw = Path(source_for_platform).read_bytes()
                    decomp, _ = LVZ.safe_decompress(raw)
                    img_path = self.source_img_path or LVZ.find_source_img_next_to_lvz(source_for_platform)
                    img_bytes = LVZ.read_img_file_bytes(img_path) if img_path else b""
                    platform_reader = LVZ.read_img(img_bytes=img_bytes, lvz_bytes=decomp) if img_bytes else None
                    if platform_reader is not None:
                        auto_swizzle_ps2 = platform_reader.detect_platform_from_lvz_groups().upper() == "PS2"
                except Exception:
                    auto_swizzle_ps2 = True
            result = LVZ.write_lvz_img_scene_archive(
                context=context,
                source_lvz_path=self.source_lvz_path,
                source_img_path=self.source_img_path,
                output_lvz_path=self.filepath,
                selected_only=self.selected_only,
                update_transforms=self.update_transforms,
                update_bounds=self.update_bounds,
                update_all_matching_instances=self.update_all_matching_instances,
                update_textures=self.update_textures,
                texture_swizzle_ps2=auto_swizzle_ps2,
                write_debug_log=self.write_debug_log,
            )
        except Exception as exc:
            self.report({'ERROR'}, f"LVZ+IMG export failed: {exc}")
            return {'CANCELLED'}

        self.report(
            {'INFO'},
            f"LVZ+IMG exported: {result['changed_rows']} IMG rows updated; {result.get('changed_textures', 0)} textures updated; {result['skipped_objects']} objects skipped."
        )
        return {'FINISHED'}
