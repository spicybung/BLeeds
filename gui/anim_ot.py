# SPDX-License-Identifier: GPL-3.0-or-later
# BLeeds - Blender operators for Rockstar Leeds ANIM files.

from pathlib import Path
from typing import List

import bpy
from bpy.types import Operator, Panel
from bpy_extras.io_utils import ImportHelper
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty

from ..ops import anim_importer

class IMPORT_SCENE_OT_leeds_anim(Operator, ImportHelper):
    bl_idname = "import_scene.leeds_anim"
    bl_label = "Import R* Leeds ANIM"
    bl_description = "Import animation data from a Rockstar Leeds ANIM file"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".anim"
    filter_glob: StringProperty(
        default="*.anim",
        options={"HIDDEN"},
        maxlen=255,
    )

    animation_index: IntProperty(
        name="Animation Index",
        description="Index inside the ANIM container to apply. A text summary is created so you can see every animation inside the file",
        default=0,
        min=0,
    )

    apply_to_selected_armature: BoolProperty(
        name="Apply to Selected Armature",
        description="Create/key an Action on the selected armature. Selecting an imported MDL mesh part or root also works if BLeeds can find its armature",
        default=True,
    )

    create_text_summary: BoolProperty(
        name="Create Text Summary",
        description="Create a Blender Text datablock containing parsed animation, mapping, and warning information",
        default=True,
    )

    apply_rotation: BoolProperty(
        name="Apply Rotation",
        description="Key quaternion rotation channels from the ANIM file",
        default=True,
    )

    apply_translation: BoolProperty(
        name="Apply Translation",
        description="Key translation channels from the ANIM file. Off by default for PLR ped weapon/body ANIMs because root translation is game/object motion and will explode an imported armature if double-applied",
        default=False,
    )

    apply_root_motion: BoolProperty(
        name="Apply Root Translation",
        description="Apply ANIM bone-id 0 translation. Root rotation is still applied by the MDL-rest solver because weapon/body PED ANIMs use it as the parent basis; leave translation off unless testing root/object motion.",
        default=False,
    )

    pose_space_mode: EnumProperty(
        name="Pose Space",
        description="How decoded ANIM local transforms are converted into Blender pose channels",
        items=(
            (
                "MDL_REST_DELTA",
                "Blender-Space Rest Delta",
                "Default for imported BLeeds pedmodels. Treats decoded ANIM rotations as absolute MDL-local bone rotations, converts them to a rest-relative Blender matrix_basis, applies root rotation, and locks root translation unless enabled.",
            ),
            (
                "PLR_REST_ROTATION_DELTA",
                "Raw ANIM Quaternion Delta",
                "Debug only. Treats decoded ANIM quaternions as raw rest-relative deltas; do not use this for normal Stories weapon PED ANIMs.",
            ),
            (
                "MDL_ABSOLUTE_POSE",
                "MDL Absolute Pose",
                "Debug. Solve the whole pose from ANIM local transforms through the imported MDL parent hierarchy, then key Blender pose matrices",
            ),
            (
                "RAW_BASIS",
                "Raw Blender Basis",
                "Debug/old behavior. Write decoded ANIM quaternions directly to pose bone rotation_quaternion",
            ),
        ),
        default="MDL_REST_DELTA",
    )

    translation_scale: FloatProperty(
        name="Translation Scale",
        description="Multiplier for half-float translation values before keying pose bone location",
        default=1.0,
        precision=6,
    )

    fps: FloatProperty(
        name="FPS",
        description="Seconds-to-Blender-frames multiplier for accumulated ANIM time",
        default=30.0,
        min=1.0,
        max=240.0,
    )

    start_frame: FloatProperty(
        name="Start Frame",
        description="Blender frame used for ANIM time 0",
        default=1.0,
    )

    use_name_fallback: BoolProperty(
        name="Use Name Fallback",
        description="If no BLeeds imported ID properties exist, try obvious GTA-style bone names for direct-id ANIM bones",
        default=True,
    )

    use_table_index_fallback: BoolProperty(
        name="Use Table Index Fallback",
        description="Use bone-table order only when the armature order matches the ANIM table",
        default=False,
    )

    clear_existing_action: BoolProperty(
        name="Create New Action",
        description="Create a new Action instead of adding keys to the active Action",
        default=True,
    )

    verbose_parse_log: BoolProperty(
        name="Verbose Parse Log",
        description="Include internal parser diagnostics in the Text summary",
        default=False,
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        col = layout.column(align=True)
        col.prop(self, "animation_index")
        col.prop(self, "apply_to_selected_armature")
        col.prop(self, "create_text_summary")

        box = layout.box()
        box.label(text="Channels")
        col = box.column(align=True)
        col.prop(self, "apply_rotation")
        col.prop(self, "apply_translation")
        col.prop(self, "pose_space_mode")
        col.prop(self, "apply_root_motion")
        col.prop(self, "translation_scale")

        box = layout.box()
        box.label(text="Timing")
        col = box.column(align=True)
        col.prop(self, "fps")
        col.prop(self, "start_frame")

        box = layout.box()
        box.label(text="Mapping")
        col = box.column(align=True)
        col.prop(self, "use_name_fallback")
        col.prop(self, "use_table_index_fallback")
        col.prop(self, "clear_existing_action")
        col.prop(self, "verbose_parse_log")

    def execute(self, context):
        try:
            anim_file = anim_importer.readAnimFile(self.filepath, use_logical_size=True, verbose=self.verbose_parse_log)
        except Exception as exc:
            self.report({"ERROR"}, f"Failed to read ANIM: {exc}")
            return {"CANCELLED"}

        if not anim_file.animations:
            self.report({"ERROR"}, "ANIM file parsed but contains no animations")
            return {"CANCELLED"}

        if self.animation_index >= len(anim_file.animations):
            self.report(
                {"ERROR"},
                f"Animation Index {self.animation_index} is out of range; file has {len(anim_file.animations)} animation(s)",
            )
            return {"CANCELLED"}

        entry = anim_file.animations[self.animation_index]
        selected_armature = anim_importer.findSelectedArmature(context)
        mapping_lines: List[str] = []
        mapped_count = 0
        keyed_count = 0

        if self.apply_to_selected_armature:
            try:
                mapped_count, keyed_count, mapping_lines = anim_importer.applyAnimEntryToArmature(
                    selected_armature,
                    entry,
                    self.filepath,
                    fps=self.fps,
                    start_frame=self.start_frame,
                    apply_rotation=self.apply_rotation,
                    apply_translation=self.apply_translation,
                    translation_scale=self.translation_scale,
                    use_name_fallback=self.use_name_fallback,
                    use_table_index_fallback=self.use_table_index_fallback,
                    clear_existing_action=self.clear_existing_action,
                    pose_space_mode=self.pose_space_mode,
                    apply_root_motion=self.apply_root_motion,
                )
            except Exception as exc:
                summary = anim_importer.buildImportSummary(
                    anim_file,
                    entry,
                    self.filepath,
                    armature_object=selected_armature,
                    mapped_count=0,
                    keyed_count=0,
                    mapping_lines=["ERROR: " + str(exc)],
                )
                anim_importer.ensureTextBlock("BLeeds_ANIM_import_failed", summary)
                self.report({"ERROR"}, f"Could not apply ANIM: {exc}")
                return {"CANCELLED"}

        if self.create_text_summary:
            text_name = "BLeeds_ANIM_" + Path(self.filepath).stem[:40]
            summary = anim_importer.buildImportSummary(
                anim_file,
                entry,
                self.filepath,
                armature_object=selected_armature,
                mapped_count=mapped_count,
                keyed_count=keyed_count,
                mapping_lines=mapping_lines,
            )
            anim_importer.ensureTextBlock(text_name, summary)

        if self.apply_to_selected_armature:
            unmapped = len(entry.bones) - mapped_count
            if mapped_count == 0:
                self.report(
                    {"WARNING"},
                    f"Parsed {entry.name}, but mapped 0 bones. Check the BLeeds_ANIM text summary for missing IDs/keys.",
                )
            else:
                self.report(
                    {"INFO"},
                    f"Imported {entry.name}: mapped {mapped_count}/{len(entry.bones)} bones, keyed {keyed_count} channels, unmapped {unmapped}",
                )
        else:
            self.report({"INFO"}, f"Parsed {Path(self.filepath).name}; created summary only")

        return {"FINISHED"}

class DATA_PT_leeds_anim_bone_id(Panel):
    bl_label = "BLeeds ANIM Bone Mapping"
    bl_idname = "DATA_PT_leeds_anim_bone_id"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "bone"

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == "ARMATURE" and context.bone is not None

    def draw(self, context):
        layout = self.layout
        bone = context.bone
        layout.label(text="ANIM import checks these imported IDs first:")
        layout.label(text=f"BoneID: {bone.get('BoneID', 'not set')}")
        layout.label(text=f"bleeds_hanim_bone_id: {bone.get('bleeds_hanim_bone_id', 'not set')}")
        layout.label(text=f"bleeds_anim_bone_id: {bone.get('bleeds_anim_bone_id', 'not set')}")
        layout.label(text=f"node_index: {bone.get('node_index', 'not set')}")
        layout.label(text=f"bleeds_mdl_hierarchy_node_index: {bone.get('bleeds_mdl_hierarchy_node_index', 'not set')}")
        layout.separator()
        layout.label(text="Hash-keyed weapon anims bridge through canonical HAnim IDs.")
