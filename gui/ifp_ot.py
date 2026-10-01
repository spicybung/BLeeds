# SPDX-License-Identifier: GPL-3.0-or-later
# BLeeds - Blender operator for Manhunt IFP files.

from pathlib import Path

import bpy
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty

from ..ops import ifp_importer


class IMPORT_SCENE_OT_bleeds_manhunt_ifp(Operator, ImportHelper):
    bl_idname = "import_scene.bleeds_manhunt_ifp"
    bl_label = "R* Studios: IFP (.ifp)"
    bl_description = "Import Manhunt 1/2 ANCT IFP animation data onto a matching BLeeds armature"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".ifp"
    filter_glob: StringProperty(default="*.ifp", options={"HIDDEN"}, maxlen=255)

    game: EnumProperty(
        name="Game",
        description="Validate the ANCT sequence type or auto-detect it",
        items=(
            ("AUTO", "Auto", "Detect Manhunt 1 SEQU or Manhunt 2 SEQT"),
            ("MANHUNT_1", "Manhunt 1", "Require SEQU tracks"),
            ("MANHUNT_2", "Manhunt 2", "Require SEQT tracks"),
        ),
        default="AUTO",
    )

    animation_index: IntProperty(
        name="Animation Index",
        description="Animation index inside the flattened ANCT/BLOC library; starts at 0",
        default=0,
        min=0,
    )

    fps: FloatProperty(
        name="FPS",
        description="Seconds-to-Blender-frames multiplier",
        default=24.0,
        min=1.0,
        max=240.0,
    )

    start_frame: FloatProperty(
        name="Start Frame",
        description="Blender frame used for IFP time 0",
        default=1.0,
    )

    apply_rotation: BoolProperty(
        name="Apply Rotation",
        description="Apply Manhunt local quaternion tracks",
        default=True,
    )

    apply_translation: BoolProperty(
        name="Apply Translation",
        description="Apply KRT0/FrameType 2/3 translation, including root motion",
        default=True,
    )

    allow_foreign_rig: BoolProperty(
        name="Allow Foreign Rig Fallback",
        description="Allow name/BoneID mapping onto an armature not marked as a BLeeds Manhunt rig. Off by default to avoid silent cross-game deformation",
        default=False,
    )

    create_text_summary: BoolProperty(
        name="Create Text Summary",
        description="Create a Blender Text datablock with parser and BoneID mapping diagnostics",
        default=True,
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(self, "game")
        layout.prop(self, "animation_index")

        box = layout.box()
        box.label(text="Channels")
        box.prop(self, "apply_rotation")
        box.prop(self, "apply_translation")

        box = layout.box()
        box.label(text="Timing")
        box.prop(self, "fps")
        box.prop(self, "start_frame")

        box = layout.box()
        box.label(text="Rig Safety")
        box.prop(self, "allow_foreign_rig")
        box.prop(self, "create_text_summary")

    def execute(self, context):
        try:
            ifp_file = ifp_importer.readManhuntIfpFile(self.filepath, expected_game=self.game)
        except Exception as exc:
            self.report({"ERROR"}, "Failed to read Manhunt IFP: {}".format(exc))
            return {"CANCELLED"}

        if not ifp_file.animations:
            self.report({"ERROR"}, "IFP parsed but contains no animations")
            return {"CANCELLED"}
        if self.animation_index >= len(ifp_file.animations):
            self.report(
                {"ERROR"},
                "Animation Index {} is out of range; file has {} animation(s)".format(
                    self.animation_index, len(ifp_file.animations)
                ),
            )
            return {"CANCELLED"}

        armature_object = ifp_importer.findSelectedArmature(context)
        animation = ifp_file.animations[self.animation_index]
        mapping_lines = []
        mapped_count = 0
        keyed_frame_count = 0
        ignored_auxiliary_count = 0
        try:
            action, mapped_count, keyed_frame_count, ignored_auxiliary_count, mapping_lines = ifp_importer.applyManhuntIfpAnimation(
                armature_object,
                animation,
                self.filepath,
                fps=self.fps,
                start_frame=self.start_frame,
                apply_rotation=self.apply_rotation,
                apply_translation=self.apply_translation,
                allow_foreign_rig=self.allow_foreign_rig,
            )
        except Exception as exc:
            summary = ifp_importer.buildIfpImportSummary(
                ifp_file,
                animation,
                self.filepath,
                armature_object=armature_object,
                mapping_lines=["ERROR: {}".format(exc)],
            )
            ifp_importer.ensureTextBlock("BLeeds_IFP_import_failed", summary)
            self.report({"ERROR"}, "Could not apply IFP: {}".format(exc))
            return {"CANCELLED"}

        if self.create_text_summary:
            summary = ifp_importer.buildIfpImportSummary(
                ifp_file,
                animation,
                self.filepath,
                armature_object=armature_object,
                mapped_count=mapped_count,
                keyed_frame_count=keyed_frame_count,
                ignored_auxiliary_count=ignored_auxiliary_count,
                mapping_lines=mapping_lines,
            )
            text_name = "BLeeds_IFP_" + Path(self.filepath).stem[:40]
            ifp_importer.ensureTextBlock(text_name, summary)

        unmapped = max(0, len(animation.tracks) - mapped_count - ignored_auxiliary_count)
        self.report(
            {"INFO"},
            "Imported {}: mapped {}/{} tracks, keyed {} samples, ignored {} auxiliary, unmapped {}".format(
                animation.name,
                mapped_count,
                len(animation.tracks),
                keyed_frame_count,
                ignored_auxiliary_count,
                unmapped,
            ),
        )
        return {"FINISHED"}
