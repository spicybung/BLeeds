# BLeeds - RenderWare DFF import operator
# Author: spicybung
# Years: 2025 - 2026

import os

import bpy
from bpy.props import CollectionProperty, EnumProperty, StringProperty
from bpy.types import Operator, OperatorFileListElement
from bpy_extras.io_utils import ImportHelper, ExportHelper


class IMPORT_OT_BLeeds_DFF(Operator, ImportHelper):
    bl_idname = "import_scene.bleeds_dff"
    bl_label = "R* Studios: DFF (.dff)"
    bl_description = "Import a RenderWare DFF with automatic format detection through the installed DemonFF/DragonFF importer"
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

        if not hasattr(bpy.ops.import_scene, "dff"):
            self.report(
                {"ERROR"},
                "No RenderWare DFF importer is registered. Enable DemonFF or DragonFF, then retry.",
            )
            return {"CANCELLED"}

        imported = 0
        failed = []
        for filepath in filepaths:
            try:
                result = bpy.ops.import_scene.dff(filepath=filepath)
                if "FINISHED" in result:
                    imported += 1
                else:
                    failed.append(os.path.basename(filepath))
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
    bl_label = "Export R* Studios DFF"
    bl_description = "Export DFF through DemonFF/DragonFF with an explicit platform/game profile"
    bl_options = {"PRESET"}

    filename_ext = ".dff"
    filter_glob: StringProperty(default="*.dff", options={"HIDDEN"}, maxlen=255)

    platform: EnumProperty(
        name="Platform",
        description="DFF export target",
        items=(
            ("PSP", "PSP DFF", "RenderWare DFF profile for PSP-era Rockstar assets"),
            ("SA_PC", "GTA San Andreas PC", "RenderWare DFF profile for GTA San Andreas on PC"),
        ),
        default="SA_PC",
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(self, "platform")

    def execute(self, context):
        if not hasattr(bpy.ops.export_scene, "dff"):
            self.report({"ERROR"}, "No DFF exporter is registered. Enable DemonFF or DragonFF, then retry.")
            return {"CANCELLED"}

        op = bpy.ops.export_scene.dff
        kwargs = {"filepath": self.filepath}

        try:
            rna = op.get_rna_type()
            prop_names = {prop.identifier for prop in rna.properties}
        except Exception:
            prop_names = set()

        if self.platform == "SA_PC":
            candidates = {
                "version": "0x36003",
                "dff_version": "0x36003",
                "rw_version": "0x36003",
                "game": "SA",
                "game_version": "SA",
                "platform": "PC",
            }
        else:
            candidates = {
                "version": "0x34003",
                "dff_version": "0x34003",
                "rw_version": "0x34003",
                "game": "LCS",
                "game_version": "LCS",
                "platform": "PSP",
            }

        for name, value in candidates.items():
            if name in prop_names:
                kwargs[name] = value

        try:
            result = op(**kwargs)
        except TypeError:
            result = op(filepath=self.filepath)
        except Exception as exc:
            self.report({"ERROR"}, "DFF export failed: {}".format(exc))
            return {"CANCELLED"}

        if "FINISHED" not in result:
            self.report({"ERROR"}, "DFF exporter did not finish")
            return {"CANCELLED"}

        self.report({"INFO"}, "Exported {}: {}".format("PSP DFF" if self.platform == "PSP" else "GTA SA PC DFF", self.filepath))
        return {"FINISHED"}
