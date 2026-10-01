# BLeeds - Manhunt IFP application helpers
# Author: spicybung
# Years: 2025 - 2026
# SPDX-License-Identifier: GPL-3.0-or-later

import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import bpy
    from mathutils import Matrix, Quaternion, Vector
except Exception:
    bpy = None
    Matrix = None
    Quaternion = None
    Vector = None

from .anim_importer import findSelectedArmature, getBlenderRestLocalMatrix, ensureTextBlock
from ..leedsLib.ifp import ManhuntIfpAnimation, ManhuntIfpFile, ManhuntIfpTrack, readManhuntIfpFile


MH2_NAME_TO_ANIMATION_BONE_ID = {
    "bip01": 1000,
    "root": 1000,
    "head": 1001,
    "l_calf": 1002,
    "bip01_l_clavicle": 1003,
    "l_clavicle": 1003,
    "l_finger0": 1004,
    "l_finger1": 1005,
    "l_finger01": 1006,
    "l_finger2": 1008,
    "l_finger11": 1011,
    "l_finger21": 1013,
    "l_foot": 1019,
    "l_forearm": 1020,
    "l_hand": 1021,
    "l_thigh": 1023,
    "l_toe": 1024,
    "l_toe0": 1024,
    "l_upperarm": 1039,
    "neck": 1040,
    "pelvis": 1045,
    "r_calf": 1056,
    "bip01_r_clavicle": 1057,
    "r_clavicle": 1057,
    "r_finger0": 1058,
    "r_finger1": 1059,
    "r_finger01": 1060,
    "r_finger2": 1062,
    "r_finger11": 1065,
    "r_finger21": 1067,
    "r_foot": 1073,
    "r_forearm": 1074,
    "r_hand": 1075,
    "r_thigh": 1077,
    "r_toe": 1078,
    "r_toe0": 1078,
    "r_upperarm": 1093,
    "spine": 1094,
    "spine1": 1095,
    "spine2": 1096,
}

MH2_AUXILIARY_BONE_IDS = {
    3333, 4444, 5001, 5002, 5003, 5004, 5005, 5006, 5007, 5008,
    5013, 5014, 5015, 5017, 5018, 5019, 5020, 5021, 5555, 6666,
}

MANHUNT_ID_PROPERTY_NAMES = (
    "bleeds_mh2_anim_bone_id",
    "bleeds_anim_bone_id",
    "bleeds_mdl_anim_bone_id",
    "BoneID",
    "anim_bone_id",
)


def normalizeMh2BoneName(name: str) -> str:
    text = str(name or "").strip().lower()
    for character in (" ", ".", "-", "~"):
        text = text.replace(character, "_")
    while "__" in text:
        text = text.replace("__", "_")
    text = text.strip("_")
    if text.startswith("bip01_"):
        suffix = text[6:]
        if suffix in MH2_NAME_TO_ANIMATION_BONE_ID:
            return suffix
    text = text.replace("left_", "l_").replace("right_", "r_")
    text = text.replace("upper_arm", "upperarm").replace("lower_arm", "forearm")
    text = text.replace("lowerarm", "forearm")
    return text.strip("_")


def mh2BoneIdFromName(name: str):
    normalized = normalizeMh2BoneName(name)
    if normalized in MH2_NAME_TO_ANIMATION_BONE_ID:
        return int(MH2_NAME_TO_ANIMATION_BONE_ID[normalized])
    with_prefix = "bip01_" + normalized
    if with_prefix in MH2_NAME_TO_ANIMATION_BONE_ID:
        return int(MH2_NAME_TO_ANIMATION_BONE_ID[with_prefix])
    return None


def readIntProperty(owner, names):
    if owner is None:
        return None
    for name in names:
        try:
            value = owner.get(name)
        except Exception:
            value = None
        if value is None:
            continue
        try:
            return int(value)
        except Exception:
            continue
    return None


def getMh2RigFamily(armature_object) -> str:
    if armature_object is None:
        return "UNKNOWN"
    owners = [armature_object, getattr(armature_object, "data", None)]
    for owner in owners:
        if owner is None:
            continue
        for key in ("bleeds_model_game", "DemonFF_Game"):
            try:
                value = str(owner.get(key, "") or "").upper().strip()
            except Exception:
                value = ""
            if value in ("MH2", "MANHUNT_2"):
                return "MANHUNT_2"
            if value in ("MH1", "MANHUNT", "MANHUNT_1"):
                return "MANHUNT_1"
    return "UNKNOWN"


def buildMh2PoseBoneLookup(armature_object):
    by_id: Dict[int, object] = {}
    source_by_id: Dict[int, str] = {}
    duplicates: Dict[int, List[str]] = {}
    if armature_object is None:
        return by_id, source_by_id, duplicates

    for pose_bone in armature_object.pose.bones:
        data_bone = armature_object.data.bones.get(pose_bone.name)
        bone_id = None
        source = ""
        for owner_name, owner in (("pose", pose_bone), ("data", data_bone)):
            bone_id = readIntProperty(owner, MANHUNT_ID_PROPERTY_NAMES)
            if bone_id is not None:
                source = "{} custom property".format(owner_name)
                break
        if bone_id is None:
            bone_id = mh2BoneIdFromName(pose_bone.name)
            if bone_id is not None:
                source = "retail MH2 name fallback"
        if bone_id is None:
            continue
        if bone_id in by_id:
            duplicates.setdefault(int(bone_id), [by_id[bone_id].name]).append(pose_bone.name)
            continue
        by_id[int(bone_id)] = pose_bone
        source_by_id[int(bone_id)] = source
    return by_id, source_by_id, duplicates


def sourceQuaternionToBlender(rotation_xyzw):
    if Quaternion is None:
        return None
    x, y, z, w = (float(value) for value in rotation_xyzw)
    source_quaternion = Quaternion((w, x, y, z))
    if source_quaternion.magnitude <= 0.000001:
        source_quaternion = Quaternion((1.0, 0.0, 0.0, 0.0))
    else:
        source_quaternion.normalize()

    # Manhunt 2 IFP is authored by MaxScript as row-vector local transforms.
    # Blender uses column vectors, so row -> column is the inverse quaternion.
    # Use the exact +90 degree X coordinate basis used by the MH2 MDL importer.
    source_column = source_quaternion.inverted()
    axis = Quaternion((math.cos(math.pi / 4.0), math.sin(math.pi / 4.0), 0.0, 0.0))
    converted = axis @ source_column @ axis.inverted()
    if converted.magnitude > 0.000001:
        converted.normalize()
    return converted


def sourcePositionToBlender(translation_xyz):
    if Matrix is None or Vector is None:
        return None
    axis = Matrix.Rotation(math.pi / 2.0, 3, "X")
    return axis @ Vector(tuple(float(value) for value in translation_xyz))


def matrixFromFlatProperty(value):
    if Matrix is None or value is None:
        return None
    try:
        values = [float(item) for item in value]
    except Exception:
        return None
    if len(values) != 16:
        return None
    try:
        return Matrix((
            values[0:4],
            values[4:8],
            values[8:12],
            values[12:16],
        ))
    except Exception:
        return None


def getMh2RestLocalMatrix(armature_object, pose_bone):
    # matrix_basis is defined against Blender's actual rest hierarchy.  Use
    # that exact basis first; the preserved source local matrix remains useful
    # for diagnostics and as a fallback only.  This is the same destination-
    # local rule that fixed MH2 in DemonFF v22.
    blender_rest = getBlenderRestLocalMatrix(armature_object, pose_bone)
    if blender_rest is not None:
        return blender_rest, "live Blender bone.matrix_local"

    data_bone = armature_object.data.bones.get(pose_bone.name)
    for owner in (pose_bone, data_bone):
        if owner is None:
            continue
        for property_name in (
            "bleeds_mh2_local_rest_matrix",
            "bleeds_mdl_import_local_matrix",
        ):
            try:
                matrix = matrixFromFlatProperty(owner.get(property_name))
            except Exception:
                matrix = None
            if matrix is not None:
                return matrix, property_name
    return Matrix.Identity(4), "identity fallback"


def composeMh2AbsoluteLocal(rest_local, frame, track, apply_rotation: bool, apply_translation: bool):
    if Matrix is None:
        return None
    target_local = rest_local.copy()

    if apply_rotation:
        rotation = sourceQuaternionToBlender(frame.rotation_xyzw)
        if rotation is not None:
            rotation_matrix = rotation.to_matrix().to_4x4()
            for row in range(3):
                for column in range(3):
                    target_local[row][column] = rotation_matrix[row][column]

    if apply_translation and track.has_translation:
        position = sourcePositionToBlender(frame.translation_xyz)
        if position is not None:
            target_local.translation = position

    return target_local


def resetArmaturePose(armature_object) -> int:
    if Matrix is None or armature_object is None:
        return 0
    count = 0
    for pose_bone in armature_object.pose.bones:
        try:
            pose_bone.matrix_basis = Matrix.Identity(4)
            pose_bone.rotation_mode = "QUATERNION"
            count += 1
        except Exception:
            continue
    return count


def setActionInterpolation(action, interpolation: str = "LINEAR") -> None:
    if action is None:
        return
    try:
        for curve in action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = interpolation
    except Exception:
        pass


def sanitizeIfpActionName(name: str, source_path: str) -> str:
    base = str(name or "").strip() or Path(source_path).stem
    safe = "".join(character if character not in "\\/:*?\"<>|" else "_" for character in base)
    return safe[:64] or "Manhunt_IFP"


def applyManhuntIfpAnimation(
    armature_object,
    animation: ManhuntIfpAnimation,
    source_path: str,
    *,
    fps: float = 24.0,
    start_frame: float = 1.0,
    apply_rotation: bool = True,
    apply_translation: bool = True,
    allow_foreign_rig: bool = False,
):
    if bpy is None or Matrix is None:
        raise RuntimeError("Blender modules are not available")
    if armature_object is None or getattr(armature_object, "type", None) != "ARMATURE":
        raise RuntimeError("Select a Manhunt armature or one of its child meshes before importing IFP")

    rig_family = getMh2RigFamily(armature_object)
    if rig_family not in ("MANHUNT_2", "MANHUNT_1") and not allow_foreign_rig:
        raise RuntimeError(
            "Selected armature is not marked as a BLeeds Manhunt rig. Import the matching MH2 MDL first, or explicitly enable foreign-rig fallback."
        )

    lookup, source_by_id, duplicates = buildMh2PoseBoneLookup(armature_object)
    previous_action_name = None
    armature_object.animation_data_create()
    try:
        previous_action = armature_object.animation_data.action
        previous_action_name = getattr(previous_action, "name", None)
        armature_object.animation_data.action = None
    except Exception:
        pass

    reset_count = resetArmaturePose(armature_object)
    action = bpy.data.actions.new(sanitizeIfpActionName(animation.name, source_path))
    action.use_fake_user = True
    action["bleeds_source_ifp_path"] = source_path
    action["bleeds_source_ifp_name"] = animation.name
    action["bleeds_source_ifp_index"] = int(animation.index)
    action["bleeds_source_ifp_game"] = "MANHUNT_2" if any(track.sequence_flag == "SEQT" for track in animation.tracks) else "MANHUNT_1"
    action["bleeds_mh2_quaternion_convention"] = "XYZW_MAX_ROW_TO_COLUMN_INVERSE_PLUS90_X"
    action["bleeds_ifp_solver"] = "MANHUNT_DIRECT_LOCAL_REST_BASIS"
    armature_object.animation_data.action = action

    mapped_count = 0
    keyed_frame_count = 0
    ignored_auxiliary_count = 0
    mapping_lines: List[str] = []
    mapped_targets = set()

    for track in animation.tracks:
        pose_bone = lookup.get(int(track.bone_id))
        if pose_bone is None:
            if int(track.bone_id) in MH2_AUXILIARY_BONE_IDS:
                ignored_auxiliary_count += 1
                mapping_lines.append(
                    "IGNORED auxiliary BoneID {} frames={}".format(track.bone_id, len(track.frames))
                )
            else:
                mapping_lines.append(
                    "UNMAPPED BoneID {} frames={}".format(track.bone_id, len(track.frames))
                )
            continue

        if pose_bone.name in mapped_targets:
            mapping_lines.append(
                "DUPLICATE target {!r} from BoneID {}; track skipped".format(pose_bone.name, track.bone_id)
            )
            continue
        mapped_targets.add(pose_bone.name)
        mapped_count += 1
        rest_local, rest_source = getMh2RestLocalMatrix(armature_object, pose_bone)
        rest_inverse = rest_local.inverted_safe()
        pose_bone.rotation_mode = "QUATERNION"

        for frame in track.frames:
            target_local = composeMh2AbsoluteLocal(
                rest_local,
                frame,
                track,
                apply_rotation=bool(apply_rotation),
                apply_translation=bool(apply_translation),
            )
            if target_local is None:
                continue
            basis = rest_inverse @ target_local
            try:
                location, rotation, scale = basis.decompose()
            except Exception:
                continue
            if rotation.magnitude > 0.000001:
                rotation.normalize()
            pose_bone.location = location
            pose_bone.rotation_quaternion = rotation
            pose_bone.scale = scale
            frame_number = float(start_frame) + float(frame.time) * float(fps)
            pose_bone.keyframe_insert(data_path="location", frame=frame_number)
            pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame_number)
            pose_bone.keyframe_insert(data_path="scale", frame=frame_number)
            keyed_frame_count += 1

        mapping_lines.append(
            "MAPPED BoneID {} -> {!r} via {}; frames={} rest={}".format(
                track.bone_id,
                pose_bone.name,
                source_by_id.get(int(track.bone_id), "unknown"),
                len(track.frames),
                rest_source,
            )
        )

    setActionInterpolation(action, "LINEAR")
    armature_object.animation_data.action = action
    action["bleeds_ifp_mapped_tracks"] = int(mapped_count)
    action["bleeds_ifp_keyed_frames"] = int(keyed_frame_count)
    action["bleeds_ifp_ignored_auxiliary"] = int(ignored_auxiliary_count)
    action["bleeds_ifp_pose_reset_bones"] = int(reset_count)

    end_frame = float(start_frame) + float(animation.total_time) * float(fps)
    try:
        bpy.context.scene.frame_start = min(int(bpy.context.scene.frame_start), int(start_frame))
        bpy.context.scene.frame_end = max(int(bpy.context.scene.frame_end), int(math.ceil(end_frame)) + 1)
        bpy.context.scene.frame_set(int(start_frame))
    except Exception:
        pass

    if duplicates:
        mapping_lines.append("RIG DUPLICATE BoneID values: {}".format(duplicates))
    mapping_lines.insert(
        0,
        "solver=MANHUNT_DIRECT_LOCAL_REST_BASIS quaternion=XYZW_MAX_ROW_TO_COLUMN_INVERSE_PLUS90_X previous_action={!r} reset_bones={}".format(
            previous_action_name, reset_count
        ),
    )
    return action, mapped_count, keyed_frame_count, ignored_auxiliary_count, mapping_lines


def buildIfpImportSummary(
    ifp_file: ManhuntIfpFile,
    animation: ManhuntIfpAnimation,
    source_path: str,
    armature_object=None,
    mapped_count: int = 0,
    keyed_frame_count: int = 0,
    ignored_auxiliary_count: int = 0,
    mapping_lines: Optional[List[str]] = None,
) -> str:
    lines = [
        "BLeeds 1.2.0 Manhunt IFP Import",
        "Source: {}".format(source_path),
        "Game: {}".format(ifp_file.game),
        "Container: {}".format(ifp_file.container),
        "Quaternion decode: XYZW -> Max row-to-column inverse -> +90deg X basis",
        "Solver: absolute source local -> destination rest-local matrix_basis",
        "Partial clip policy: only explicit IFP track owners receive F-curves",
    ]
    if armature_object is not None:
        lines.append("Armature: {} ({})".format(armature_object.name, getMh2RigFamily(armature_object)))
    lines.extend((
        "Selected animation: [{}] {}".format(animation.index, animation.name),
        "Tracks: {}".format(len(animation.tracks)),
        "Mapped tracks: {}".format(mapped_count),
        "Keyed source frames: {}".format(keyed_frame_count),
        "Ignored auxiliary tracks: {}".format(ignored_auxiliary_count),
        "",
        ifp_file.summaryText(include_tracks=False),
    ))
    if mapping_lines:
        lines.append("")
        lines.append("Mapping:")
        lines.extend(mapping_lines)
    return "\n".join(lines)
