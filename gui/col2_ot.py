from __future__ import annotations
import bpy
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.props import BoolProperty, StringProperty

from ..ops import col2_importer, col2_exporter

class IMPORT_OT_COL2(Operator, ImportHelper):
    bl_idname = "import_scene.col2_leeds"
    bl_label = "Rockstar Leeds Collision"
    bl_options = {"PRESET", "UNDO"}

    filename_ext = ".col2"
    filter_glob: StringProperty(default="*.col2;*.COL2", options={"HIDDEN"})

    import_aabb_boxes: BoolProperty(
        name="Import AABB Boxes",
        description="Display COL2 box/AABB collision primitives as wireframe box objects instead of hiding them behind mesh-only collision",
        default=True,
    )

    import_empty_model_bounds: BoolProperty(
        name="Import Empty Model Bounds",
        description="When a CColModel has no triangle mesh and no readable CBox table, display its model bounding AABB as a wire box",
        default=True,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "import_aabb_boxes")
        layout.prop(self, "import_empty_model_bounds")

    def execute(self, context):
        created, _report = col2_importer.import_col2_file(
            self.filepath,
            context,
            import_box_primitives=self.import_aabb_boxes,
            import_empty_model_aabb=self.import_empty_model_bounds,
        )
        self.report(
            {"INFO"},
            f"COL2 parsed. Objects created: {len(created)}",
        )
        return {"FINISHED"}

class EXPORT_OT_COL2(Operator, ExportHelper):
    bl_idname = "export_scene.col2_leeds"
    bl_label = "Rockstar Leeds Collision"
    bl_options = {"PRESET", "UNDO"}

    filename_ext = ".col2"
    filter_glob: StringProperty(default="*.col2;*.COL2", options={"HIDDEN"})

    selected_only: BoolProperty(
        name="Selected Objects Only",
        description="Export selected collision objects only. Disable to export every object marked as a BLeeds COL2 collision object in the scene",
        default=True,
    )

    force_selected_to_aabb: BoolProperty(
        name="Export Selected as AABB",
        description="Export selected mesh objects as box/AABB collision primitives instead of triangle meshes",
        default=False,
    )

    pad_to_sector: BoolProperty(
        name="Pad to 2048 Bytes",
        description="Pad the written COL2 archive to a 2048-byte sector boundary while keeping the logical header size exact",
        default=True,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "selected_only")
        layout.prop(self, "force_selected_to_aabb")
        layout.prop(self, "pad_to_sector")

    def execute(self, context):
        try:
            result, _report = col2_exporter.export_col2_file(
                self.filepath,
                context,
                selected_only=self.selected_only,
                force_selected_to_aabb=self.force_selected_to_aabb,
                pad_to_sector=self.pad_to_sector,
            )
        except Exception as exc:
            self.report({"ERROR"}, f"COL2 export failed: {exc}")
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            f"COL2 exported: {result['model_count']} models, {result['reloc_count']} reloc entries",
        )
        return {"FINISHED"}
