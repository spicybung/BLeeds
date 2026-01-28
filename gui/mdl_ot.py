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

from ..ops import mdl_importer

import bpy
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.props import (
    IntProperty,

    StringProperty,
    BoolProperty,
    EnumProperty,
)


class IMPORT_OT_Stories_mdl(Operator, ImportHelper):
    """Import a Rockstar Leeds Stories MDL"""
    bl_idname = "import_scene.bleeds_stories_mdl"
    bl_label = "Import SimpleModel"
    bl_options = {"PRESET", "UNDO"}

    filename_ext = ".mdl"
    filter_glob: StringProperty(
        default="*.mdl",
        options={"HIDDEN"},
        maxlen=255,
    )

    platform: EnumProperty(
        name="Platform",
        description="Platform this Stories MDL was built for",
        items=(
            ("PS2", "PS2", "PlayStation 2 (Liberty City Stories / Vice City Stories)"),
            ("PSP", "PSP", "PlayStation Portable (Liberty City Stories / Vice City Stories)"),
        ),
        default="PS2",
    )

    mdl_type: EnumProperty(
        name="Model Type",
        description="Whether this MDL is a ped/actor or a prop",
        items=(
            ("SIM", "SimpleModel", "Simple / prop model without bones"),
            ("PED", "PedModel / Actor", "Pedestrian / actor model with bones"),
            ("CUT", "CutsceneModel / Actor", "Cutscene / actor model with bones"),
            ("VEH", "VehicleModel", "Vehicle model"),
        ),
        default="SIM",
    )

    create_armature: BoolProperty(
        name="Create Armature (if present)",
        description="If enabled and the MDL has frame data, create an Armature object and parent meshes to it",
        default=True,
    )

    link_to_scene: BoolProperty(
        name="Link Collection To Scene",
        description="Link the created collection to the active scene",
        default=True,
    )

    collection_name: StringProperty(
        name="Collection Name",
        description="Collection to place imported objects in (blank = file name)",
        default="",
        maxlen=1024,
    )

    def execute(self, context):
        filepath = self.filepath
        collection_name = self.collection_name

        try:
            created_objects = mdl_importer.import_stories_mdl(
                context=context,
                filepath=filepath,
                platform=self.platform,
                mdl_type=self.mdl_type,
                collection_name=collection_name,
                create_armature=self.create_armature,
                link_to_scene=self.link_to_scene,
            )

            if created_objects:
                for obj in created_objects:
                    obj.select_set(True)
                if created_objects[0] is not None:
                    context.view_layer.objects.active = created_objects[0]

            self.report({"INFO"}, f"Imported Stories MDL: {filepath}")
            return {"FINISHED"}

        except Exception as exc:
            self.report({"ERROR"}, f"Failed to import Stories MDL: {exc}")
            return {"CANCELLED"}


class EXPORT_SCENE_OT_stories_mdl_ps2(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.bleeds_stories_mdl"
    bl_label = "Export R* Leeds Stories MDL"
    bl_options = {"UNDO"}

    filename_ext = ".mdl"
    filter_glob: StringProperty(
        default="*.mdl",
        options={"HIDDEN"},
        maxlen=255,
    )

    mdl_type: EnumProperty(
        name="Type",
        description="Export type (PROP uses Atomic root; PED uses Clump+Atomic)",
        items=(
            ("SIM", "SIM", "Prop / SimpleModel"),
            ("PED", "PED", "Ped / Clump"),
        ),
        default="SIM",
    )

    max_batch_verts: IntProperty(
        name="Max Batch Verts",
        description=(
            "Maximum vertices per VIF segment.  When set to 0, the exporter "
            "automatically chooses an appropriate size based on the mesh."
        ),
        default=0,
        min=0,
        max=255,
        options={"HIDDEN"},
    )

    rounding_mode: EnumProperty(
        name="Rounding",
        description="How to quantize float -> int16 for position encoding.",
        items=(
            ("ROUND", "Round", "round()"),
            ("TRUNC", "Trunc", "int()"),
            ("FLOOR", "Floor", "math.floor()"),
            ("CEIL", "Ceil", "math.ceil()"),
        ),
        default="ROUND",
    )

    use_normals: BoolProperty(
        name="Export Normals",
        description="Include the normals stream in the PS2 DMA payload if exists",
        default=False,
    )

    def execute(self, context):
        from ..ops import mdl_exporter

        try:
            mdl_exporter.export_stories_mdl_ps2(
                context=context,
                filepath=self.filepath,
                mdl_type=self.mdl_type,
                max_batch_verts=self.max_batch_verts,
                rounding_mode=self.rounding_mode,
                use_normals=self.use_normals,
            )
        except Exception as exc:
            self.report({"ERROR"}, f"Export Stories MDL failed: {exc}")
            return {"CANCELLED"}

        self.report({"INFO"}, f"Exported Stories MDL: {self.filepath}")
        return {"FINISHED"}

