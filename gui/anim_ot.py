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

from pathlib import Path
from typing import List

import bpy
from bpy.types import Operator, Panel
from bpy_extras.io_utils import ImportHelper
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty

from ..ops import anim_importer

class IMPORT_SCENE_OT_leeds_anim(Operator, ImportHelper):
    bl_idname = "import_scene.leeds_anim"
    bl_label = "Import R* Leeds Stories ANIM"
    bl_description = "Import Rockstar Leeds .ANIM"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".anim"
    filter_glob: StringProperty(
        default="*.anim;*.ANIM",
        options={"HIDDEN"},
        maxlen=255,
    )

    import_all: BoolProperty(
        name="Import All Animations",
        description="Create a separate action for every animation in the file",
        default=True,
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
        description="Key translation channels from the ANIM file. Uses the imported model rest pose; root movement is controlled separately",
        default=True,
    )

    apply_root_motion: BoolProperty(
        name="Apply Root Translation",
        description="Include movement of the root bone",
        default=False,
    )

    pose_space_mode: EnumProperty(
        name="Pose",
        description="How decoded ANIM local transforms are converted into Blender pose channels",
        items=(
            (
                "MDL_REST_DELTA",
                "Imported Model Rest Pose",
                "Default for imported BLeeds pedmodels. Uses the source bone transforms saved by the model importer.",
            ),
            (
                "ANIM_FIRST_KEY_DELTA",
                "First Frame as Rest Pose",
                "Treat each track's first key as its authored Leeds local reference pose and apply subsequent motion as a Blender-rest-relative delta. Use this when the animation was made for a different skeleton.",
            ),
            (
                "PLR_REST_ROTATION_DELTA",
                "Original Rotation Delta",
                "Apply each rotation relative to the original model pose.",
            ),
            (
                "MDL_ABSOLUTE_POSE",
                "Model Local Pose",
                "Apply the animation through the complete model hierarchy.",
            ),
            (
                "RAW_BASIS",
                "Blender Local Pose",
                "Apply local rotations directly to Blender bones.",
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
        col.prop(self, "import_all")
        if not self.import_all:
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

        selected_index = 0 if self.import_all else self.animation_index
        if selected_index >= len(anim_file.animations):
            self.report(
                {"ERROR"},
                f"Animation Index {self.animation_index} is out of range; file has {len(anim_file.animations)} animation(s)",
            )
            return {"CANCELLED"}

        entry = anim_file.animations[selected_index]
        selected_armature = anim_importer.findSelectedArmature(context)
        if self.apply_to_selected_armature and selected_armature is not None:
            try:
                selected_game = str(selected_armature.get("bleeds_model_game", "") or "").upper().strip()
            except Exception:
                selected_game = ""
            if selected_game in {"MH2", "MANHUNT_2", "MH1", "MANHUNT", "MANHUNT_1"}:
                self.report(
                    {"ERROR"},
                    "Stories .anim is not a Manhunt animation container. Use R* Manhunt: Animation IFP (.ifp) for this armature.",
                )
                return {"CANCELLED"}

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

        if self.apply_to_selected_armature and self.import_all and mapped_count:
            selected_action = selected_armature.animation_data.action
            selected_action.use_fake_user = True
            for other_entry in anim_file.animations:
                if other_entry.index == entry.index:
                    continue
                try:
                    anim_importer.applyAnimEntryToArmature(
                        selected_armature, other_entry, self.filepath,
                        fps=self.fps, start_frame=self.start_frame,
                        apply_rotation=self.apply_rotation,
                        apply_translation=self.apply_translation,
                        translation_scale=self.translation_scale,
                        use_name_fallback=self.use_name_fallback,
                        use_table_index_fallback=self.use_table_index_fallback,
                        clear_existing_action=True,
                        pose_space_mode=self.pose_space_mode,
                        apply_root_motion=self.apply_root_motion,
                    )
                    selected_armature.animation_data.action.use_fake_user = True
                except Exception as exc:
                    selected_armature.animation_data.action = selected_action
                    self.report({"ERROR"}, f"Could not import {other_entry.name}: {exc}")
                    return {"CANCELLED"}
            selected_armature.animation_data.action = selected_action
            context.scene.frame_set(context.scene.frame_current)

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
                    f"Imported {len(anim_file.animations) if self.import_all else 1} animation(s); active {entry.name}: {mapped_count}/{len(entry.bones)} bones, {unmapped} unmatched",
                )
        else:
            self.report({"INFO"}, f"Parsed {Path(self.filepath).name}; created summary only")

        return {"FINISHED"}

class DATA_PT_leeds_anim_bone_id(Panel):
    bl_label = "BLeeds Animation Bone Mapping"
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
        layout.label(text="ANIM / IFP import checks these IDs first:")
        layout.label(text=f"BoneID: {bone.get('BoneID', 'not set')}")
        layout.label(text=f"bleeds_hanim_bone_id: {bone.get('bleeds_hanim_bone_id', 'not set')}")
        layout.label(text=f"bleeds_anim_bone_id: {bone.get('bleeds_anim_bone_id', 'not set')}")
        layout.label(text=f"node_index: {bone.get('node_index', 'not set')}")
        layout.label(text=f"bleeds_mdl_hierarchy_node_index: {bone.get('bleeds_mdl_hierarchy_node_index', 'not set')}")
        layout.separator()
        layout.label(text="Stories uses hash/direct IDs; Manhunt IFP uses MH2 Animation BoneID.")


from bpy_extras.io_utils import ExportHelper
from ..ops.anim_exporter import exportArmatureAnimation


class EXPORT_SCENE_OT_leeds_anim(Operator, ExportHelper):
    bl_idname = "export_scene.leeds_anim"
    bl_label = "Export Stories ANIM"
    filename_ext = ".anim"

    filter_glob: StringProperty(default="*.anim", options={"HIDDEN"})
    animation_name: StringProperty(name="Animation Name", default="animation", maxlen=24)
    start_frame: FloatProperty(name="First Frame", default=1.0)
    end_frame: FloatProperty(name="Last Frame", default=30.0)
    fps: FloatProperty(name="FPS", default=30.0, min=1.0, max=240.0)

    def invoke(self, context, event):
        armature = anim_importer.findSelectedArmature(context)
        action = armature.animation_data.action if armature and armature.animation_data else None
        if action:
            self.animation_name = str(action.get("bleeds_source_anim_name", action.name))[:24]
            self.start_frame, self.end_frame = action.frame_range
            self.fps = float(action.get("bleeds_anim_fps", context.scene.render.fps / context.scene.render.fps_base))
        else:
            self.start_frame = context.scene.frame_start
            self.end_frame = context.scene.frame_end
            self.fps = context.scene.render.fps / context.scene.render.fps_base
        return ExportHelper.invoke(self, context, event)

    def execute(self, context):
        try:
            bones, keys = exportArmatureAnimation(
                context, self.filepath, start_frame=self.start_frame, end_frame=self.end_frame,
                fps=self.fps, animation_name=self.animation_name)
        except Exception as exc:
            self.report({"ERROR"}, f"Could not export ANIM: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported {self.animation_name}: {bones} bones, {keys} keys per bone")
        return {"FINISHED"}
