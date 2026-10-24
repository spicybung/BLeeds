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

import math

from . import anim_importer
from ..leedsLib.anim import AnimFile, AnimEntry, BoneAnim, AnimFrame, writeAnimFile
from ..data.bone_data import DIRECT_ID_PROPERTY_NAMES, directIdFromBoneName


def exportArmatureAnimation(context, path, *, start_frame, end_frame, fps, animation_name):
    armature = anim_importer.findSelectedArmature(context)
    if armature is None or armature.animation_data is None or armature.animation_data.action is None:
        raise ValueError("Select an armature with an active animation")
    if not all(math.isfinite(value) for value in (start_frame, end_frame, fps)) or fps <= 0 or end_frame < start_frame:
        raise ValueError("Choose a valid frame range and a positive FPS")
    action = armature.animation_data.action
    mode = str(action.get("bleeds_anim_pose_space_mode", "MDL_REST_DELTA"))
    if mode not in {"MDL_REST_DELTA", "DEFAULT", "", "RAW_BASIS"}:
        raise ValueError("Export requires Imported Model Rest Pose or Blender Local Pose; reimport using that pose setting")
    scale = float(action.get("bleeds_anim_translation_scale", 1.0))
    if not math.isfinite(scale) or scale == 0.0:
        raise ValueError("The animation translation scale must be finite and nonzero")
    tracks = []
    identities = set()
    native_rig = anim_importer.isNativeLeedsMdlArmature(armature)
    for pose_bone in armature.pose.bones:
        bone_id = anim_importer.getIntCustomProperty(pose_bone.bone, DIRECT_ID_PROPERTY_NAMES)
        if bone_id is None:
            bone_id = anim_importer.getIntCustomProperty(pose_bone, DIRECT_ID_PROPERTY_NAMES)
        if bone_id is None and not native_rig:
            bone_id = directIdFromBoneName(pose_bone.name)
        if bone_id is None or bone_id < 0 or bone_id == 255:
            continue
        if bone_id > 65535 or bone_id in identities:
            raise ValueError(f"{pose_bone.name}: invalid or duplicate animation bone ID")
        identities.add(bone_id)
        source_rest, source_label = anim_importer.getImportedMdlRestLocalMatrix(armature, pose_bone)
        blender_rest = anim_importer.getBlenderRestLocalMatrix(armature, pose_bone)
        if mode != "RAW_BASIS" and source_rest is None:
            raise ValueError(f"{pose_bone.name}: source model rest pose is missing")
        track = BoneAnim(len(tracks), 0x17, 0, 0, bone_id, bone_id, 0, bone_id)
        tracks.append((pose_bone.name, track, source_rest, blender_rest))
    if not tracks:
        raise ValueError("No animation bone IDs were found on this armature")
    frame_numbers = [float(start_frame)]
    frame_numbers.extend(float(frame) for frame in range(math.floor(start_frame) + 1, math.ceil(end_frame)) if frame < end_frame)
    if end_frame > start_frame:
        frame_numbers.append(float(end_frame))
    if len(frame_numbers) > 65535:
        raise ValueError("ANIM supports at most 65535 keys per bone")
    scene = context.scene
    previous_frame = scene.frame_current
    previous_subframe = scene.frame_subframe
    try:
        for frame_number in frame_numbers:
            whole_frame = math.floor(frame_number)
            scene.frame_set(whole_frame, subframe=frame_number - whole_frame)
            evaluated = armature.evaluated_get(context.evaluated_depsgraph_get())
            time = (frame_number - start_frame) / fps
            for name, track, source_rest, blender_rest in tracks:
                pose_bone = evaluated.pose.bones[name]
                parent_args = {}
                if pose_bone.parent is not None:
                    parent_args["parent_matrix"] = pose_bone.parent.matrix
                    parent_args["parent_matrix_local"] = pose_bone.parent.bone.matrix_local
                basis = pose_bone.bone.convert_local_to_pose(
                    pose_bone.matrix, pose_bone.bone.matrix_local, invert=True, **parent_args)
                if mode == "RAW_BASIS":
                    local = basis
                else:
                    source_rotation = anim_importer.rotationOnlyMatrix(source_rest)
                    blender_rotation = anim_importer.rotationOnlyMatrix(blender_rest)
                    conversion = blender_rotation.inverted() @ source_rotation
                    local = source_rest @ conversion.inverted() @ basis @ conversion
                location, rotation, local_scale = local.decompose()
                rotation.normalize()
                if track.frames:
                    previous = track.frames[-1].rotation_xyzw
                    if sum(a * b for a, b in zip(previous, (rotation.x, rotation.y, rotation.z, rotation.w))) < 0.0:
                        rotation.negate()
                previous_time = track.frames[-1].absolute_time if track.frames else 0.0
                track.frames.append(AnimFrame(
                    (rotation.x, rotation.y, rotation.z, rotation.w), time - previous_time, time,
                    tuple(value / scale for value in location), tuple(local_scale)))
    finally:
        scene.frame_set(previous_frame, subframe=previous_subframe)
    bones = [item[1] for item in tracks]
    for bone in bones:
        bone.frame_count = len(bone.frames)
    entry = AnimEntry(0, 0, 0, animation_name, len(bones), 0, (end_frame - start_frame) / fps, bones)
    result = AnimFile(b"mina" + bytes(28), 0, 0, 0, [], [entry])
    writeAnimFile(path, result)
    return len(bones), len(frame_numbers)
