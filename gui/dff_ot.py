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

import os

import bpy
from bpy.props import CollectionProperty, EnumProperty, StringProperty
from bpy.types import Operator, OperatorFileListElement
from bpy_extras.io_utils import ImportHelper, ExportHelper


class IMPORT_OT_BLeeds_DFF(Operator, ImportHelper):
    bl_idname = "import_scene.bleeds_dff"
    bl_label = "R* Studios: DFF (.dff)"
    bl_description = "Import RenderWare .DFF"
    bl_options = {"PRESET", "UNDO"}

    filename_ext = ".dff"
    filter_glob: StringProperty(
        default="*.dff;*.DFF",
        options={"HIDDEN"},
        maxlen=255,
    )
    files: CollectionProperty(
        name="Selected DFF files",
        type=OperatorFileListElement,
        options={"HIDDEN"},
    )
    directory: StringProperty(
        name="Directory",
        subtype="DIR_PATH",
        options={"HIDDEN"},
    )

    source: EnumProperty(
        name="Source",
        items=(("MOBILE", "LCS Mobile", "LCS iOS and Android assets"),
               ("BETA", "LCS Prototype", "Standard RenderWare geometry from prototype files")),
        default="MOBILE",
    )

    def draw(self, context):
        self.layout.prop(self, "source")

    def gatherFilepaths(self):
        paths = []
        directory = str(getattr(self, "directory", "") or "")
        selected_files = list(getattr(self, "files", []) or [])

        if selected_files and directory:
            for item in selected_files:
                name = str(getattr(item, "name", "") or "")
                if name:
                    paths.append(os.path.join(directory, name))

        filepath = str(getattr(self, "filepath", "") or "")
        if not paths and filepath:
            paths.append(filepath)

        unique_paths = []
        seen = set()
        for path in paths:
            normalized = os.path.normpath(path)
            key = os.path.normcase(normalized)
            if key in seen:
                continue
            seen.add(key)
            unique_paths.append(normalized)
        return unique_paths

    def execute(self, context):
        filepaths = self.gatherFilepaths()
        if not filepaths:
            self.report({"ERROR"}, "No DFF files were selected")
            return {"CANCELLED"}

        imported = 0
        failed = []
        for filepath in filepaths:
            try:
                from ..ops.native_mobile import importDff
                importDff(context, filepath, self.source)
                imported += 1
            except Exception as exc:
                failed.append("{}: {}".format(os.path.basename(filepath), exc))

        if imported == 0:
            if failed:
                self.report({"ERROR"}, "DFF import failed: {}".format(failed[0]))
            return {"CANCELLED"}

        if failed:
            self.report(
                {"WARNING"},
                "Imported {} DFF file(s); {} failed".format(imported, len(failed)),
            )
        else:
            self.report({"INFO"}, "Imported {} DFF file(s)".format(imported))
        return {"FINISHED"}


class EXPORT_OT_BLeeds_DFF(Operator, ExportHelper):
    bl_idname = "export_scene.bleeds_dff"
    bl_label = "Export LCS Mobile DFF"
    bl_description = "Export edited LCS mobile DFF meshes, UVs, materials, and skin weights"
    bl_options = {"PRESET"}

    filename_ext = ".dff"
    filter_glob: StringProperty(default="*.dff", options={"HIDDEN"}, maxlen=255)

    def execute(self, context):
        try:
            from ..ops.native_mobile import exportDff
            exportDff(context, self.filepath)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "Exported LCS mobile DFF")
        return {"FINISHED"}
