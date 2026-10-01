# BLeeds - Scripts for working with R* Leeds (GTA Stories, Chinatown Wars, Manhunt 2, etc) formats in Blender
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
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import bpy
    from mathutils import Quaternion, Matrix, Vector
except Exception:
    bpy = None
    Quaternion = None
    Matrix = None
    Vector = None

from ..data.bone_data import (
    DIRECT_ID_PROPERTY_NAMES,
    BONE_KEY_PROPERTY_NAMES,
    HASH16_PROPERTY_NAMES,
    TABLE_INDEX_PROPERTY_NAMES,
    DIRECT_ID_NAME_HINTS,
    NORMALIZED_NAME_TO_DIRECT_ID,
    normalizeAnimBoneName,
    directIdFromBoneName,
)

from ..leedsLib.anim import (
    AnimFile,
    AnimFrame,
    AnimReadError,
    AnimLog,
    AnimEntry,
    BoneAnim,
    buildAnimationTimeline,
    formatAnimBoneTarget,
    readAnimBytes,
    readAnimFile,
    resolvePedAnimBoneId,
    sampleBoneAnimFrameAtTime,
)

def getIntCustomProperty(owner, names: Iterable[str]) -> Optional[int]:
    if owner is None:
        return None
    for name in names:
        try:
            if name not in owner:
                continue
            return int(owner.get(name))
        except Exception:
            continue
    return None

def buildPoseBoneLookup(armature_object) -> Tuple[Dict[int, object], Dict[int, object], Dict[int, object], Dict[int, object], Dict[int, str]]:
    by_direct_id: Dict[int, object] = {}
    by_bone_key: Dict[int, object] = {}
    by_hash16: Dict[int, object] = {}
    by_table_index: Dict[int, object] = {}
    direct_id_source: Dict[int, str] = {}

    if armature_object is None or getattr(armature_object, "type", None) != "ARMATURE":
        return by_direct_id, by_bone_key, by_hash16, by_table_index, direct_id_source

    for pose_bone in armature_object.pose.bones:
        data_bone = armature_object.data.bones.get(pose_bone.name)

        name_direct_id = directIdFromBoneName(pose_bone.name)
        if name_direct_id is not None:
            by_direct_id[int(name_direct_id)] = pose_bone
            direct_id_source[int(name_direct_id)] = "canonical bone-name map"

        for owner in (pose_bone, data_bone):
            direct_id = getIntCustomProperty(owner, DIRECT_ID_PROPERTY_NAMES)
            if direct_id is not None and int(direct_id) not in by_direct_id:
                by_direct_id[int(direct_id)] = pose_bone
                direct_id_source.setdefault(int(direct_id), "anim-id property")

            bone_key = getIntCustomProperty(owner, BONE_KEY_PROPERTY_NAMES)
            if bone_key is not None:
                by_bone_key.setdefault(bone_key & 0xFFFFFFFF, pose_bone)

            hash16 = getIntCustomProperty(owner, HASH16_PROPERTY_NAMES)
            if hash16 is not None:
                by_hash16.setdefault(hash16 & 0xFFFF, pose_bone)

            table_index = getIntCustomProperty(owner, TABLE_INDEX_PROPERTY_NAMES)
            if table_index is not None:
                by_table_index.setdefault(table_index, pose_bone)

    return by_direct_id, by_bone_key, by_hash16, by_table_index, direct_id_source

def findPoseBoneByNameFallback(armature_object, direct_bone_id: int):
    if armature_object is None:
        return None

    for name in DIRECT_ID_NAME_HINTS.get(int(direct_bone_id), ()):
        pose_bone = armature_object.pose.bones.get(name)
        if pose_bone is not None:
            return pose_bone

    for pose_bone in armature_object.pose.bones:
        name_direct_id = directIdFromBoneName(pose_bone.name)
        if name_direct_id is not None and int(name_direct_id) == int(direct_bone_id):
            return pose_bone

    return None

def findPoseBoneForAnimBone(
    armature_object,
    bone: BoneAnim,
    *,
    use_name_fallback: bool,
    use_table_index_fallback: bool,
    lookup: Tuple[Dict[int, object], Dict[int, object], Dict[int, object], Dict[int, object], Dict[int, str]],
):
    by_direct_id, by_bone_key, by_hash16, by_table_index, direct_id_source = lookup
    resolved_direct_id, resolved_reason = resolvePedAnimBoneId(bone)

    if bone.direct_bone_id is not None and bone.direct_bone_id in by_direct_id:
        return by_direct_id[bone.direct_bone_id], direct_id_source.get(int(bone.direct_bone_id), "direct-id property")

    if bone.bone_key in by_bone_key:
        return by_bone_key[bone.bone_key], "bone-key property"

    if bone.hash16 in by_hash16:
        return by_hash16[bone.hash16], "hash16 property"

    if (
        bone.direct_bone_id is None
        and resolved_direct_id is not None
        and resolved_direct_id in by_direct_id
    ):
        return by_direct_id[resolved_direct_id], f"{resolved_reason} -> {direct_id_source.get(int(resolved_direct_id), 'direct-id property')}"

    if use_name_fallback and resolved_direct_id is not None:
        pose_bone = findPoseBoneByNameFallback(armature_object, resolved_direct_id)
        if pose_bone is not None:
            return pose_bone, f"{resolved_reason} -> name fallback"

    # A direct/hashed PED identity must never silently fall through to raw pose
    # list position. Blender bone order is not the Leeds HAnim identity space.
    # Table-index fallback is reserved for tracks that truly have no semantic
    # identity and for armatures carrying an explicit hierarchy-node table.
    has_semantic_identity = (
        bone.direct_bone_id is not None
        or resolved_direct_id is not None
        or int(getattr(bone, "bone_key", 0) or 0) != 0
        or int(getattr(bone, "hash16", 0) or 0) != 0
    )

    if use_table_index_fallback and not has_semantic_identity and bone.table_index in by_table_index:
        return by_table_index[bone.table_index], "table-index property"

    if use_table_index_fallback and not has_semantic_identity:
        names = [pose_bone.name for pose_bone in armature_object.pose.bones]
        if 0 <= bone.table_index < len(names):
            return armature_object.pose.bones.get(names[bone.table_index]), "raw pose-bone index fallback"

    return None, "unmapped"

def armatureHasImportedMdlRestData(armature_object) -> bool:
    if armature_object is None or getattr(armature_object, "type", None) != "ARMATURE":
        return False

    for owner in (armature_object, getattr(armature_object, "data", None)):
        if owner is None:
            continue
        try:
            if "bleeds_mdl_frame_ptrs" in owner or "bleeds_mdl_hierarchy_node_names" in owner:
                return True
        except Exception:
            continue
    return False


def armatureDeformsMesh(armature_object, mesh_object) -> bool:
    if armature_object is None or mesh_object is None:
        return False
    if getattr(mesh_object, "type", None) != "MESH":
        return False

    try:
        for modifier in mesh_object.modifiers:
            if getattr(modifier, "type", None) != "ARMATURE":
                continue
            if getattr(modifier, "object", None) is armature_object:
                return True
    except Exception:
        pass
    return False


def scoreArmatureCandidate(armature_object, active_object=None) -> int:
    if armature_object is None or getattr(armature_object, "type", None) != "ARMATURE":
        return -1

    score = 0
    if armature_object is active_object:
        score += 1000
    if armatureHasImportedMdlRestData(armature_object):
        score += 400

    if active_object is not None and getattr(active_object, "type", None) == "MESH":
        if armatureDeformsMesh(armature_object, active_object):
            score += 800
        if getattr(active_object, "parent", None) is armature_object:
            score += 200

    try:
        for child in armature_object.children_recursive:
            if armatureDeformsMesh(armature_object, child):
                score += 20
                break
    except Exception:
        pass

    return score


def findSelectedArmature(context):
    if bpy is None:
        return None

    active = getattr(context, "object", None)
    if active is not None and getattr(active, "type", None) == "ARMATURE":
        return active

    candidates = []
    seen_ids = set()

    def add_candidate(candidate):
        if candidate is None or getattr(candidate, "type", None) != "ARMATURE":
            return
        candidate_id = id(candidate)
        if candidate_id in seen_ids:
            return
        seen_ids.add(candidate_id)
        candidates.append(candidate)

    if active is not None:
        # The Armature modifier is the authoritative deform relationship. Prefer
        # it over object parenting because imported MDL roots can contain more
        # than one armature or helper hierarchy.
        try:
            for modifier in active.modifiers:
                if getattr(modifier, "type", None) == "ARMATURE":
                    add_candidate(getattr(modifier, "object", None))
        except Exception:
            pass

        parent = getattr(active, "parent", None)
        while parent is not None:
            add_candidate(parent)
            parent = getattr(parent, "parent", None)

        try:
            for child in active.children_recursive:
                add_candidate(child)
        except Exception:
            pass

    try:
        for obj in context.selected_objects:
            add_candidate(obj)
    except Exception:
        pass

    if not candidates:
        return None

    candidates.sort(
        key=lambda candidate: (
            scoreArmatureCandidate(candidate, active),
            str(getattr(candidate, "name", "")),
        ),
        reverse=True,
    )
    return candidates[0]

def sanitizeActionName(name: str, path: str) -> str:
    base = str(name).strip() or Path(path).stem
    safe = "".join(ch if ch not in "\\/:*?\"<>|" else "_" for ch in base)
    return safe[:64] or "Leeds_ANIM"

def ensureTextBlock(name: str, text: str):
    if bpy is None:
        return None
    block = bpy.data.texts.get(name)
    if block is None:
        block = bpy.data.texts.new(name)
    block.clear()
    block.write(text)
    return block

def buildMappingDiagnosticLines(armature_object, entry: AnimEntry) -> List[str]:
    lines: List[str] = []
    lookup = buildPoseBoneLookup(armature_object)
    by_direct_id, by_bone_key, by_hash16, by_table_index, direct_id_source = lookup
    lines.append(
        "Armature lookup: "
        f"direct_ids={sorted(by_direct_id.keys())} "
        f"bone_keys={len(by_bone_key)} hash16={len(by_hash16)} table_indices={sorted(by_table_index.keys())}"
    )
    for bone in entry.bones:
        resolved_direct_id, resolved_reason = resolvePedAnimBoneId(bone)
        if bone.direct_bone_id is not None:
            pipeline = f"direct-id {bone.direct_bone_id}"
        elif resolved_direct_id is not None:
            pipeline = f"hash16 0x{bone.hash16:04X} -> ped-id {resolved_direct_id} ({resolved_reason})"
        else:
            pipeline = f"hash16 0x{bone.hash16:04X} unresolved"

        if resolved_direct_id is not None and resolved_direct_id in by_direct_id:
            target = by_direct_id[resolved_direct_id]
            source = direct_id_source.get(int(resolved_direct_id), "direct-id lookup")
            lines.append(f"PIPE OK bone[{bone.table_index:02d}] {pipeline} -> {getattr(target, 'name', '<unnamed>')!r} via {source}")
        elif bone.bone_key in by_bone_key:
            target = by_bone_key[bone.bone_key]
            lines.append(f"PIPE OK bone[{bone.table_index:02d}] key 0x{bone.bone_key:08X} -> {getattr(target, 'name', '<unnamed>')!r} via bone-key property")
        elif bone.hash16 in by_hash16:
            target = by_hash16[bone.hash16]
            lines.append(f"PIPE OK bone[{bone.table_index:02d}] hash16 0x{bone.hash16:04X} -> {getattr(target, 'name', '<unnamed>')!r} via hash16 property")
        else:
            lines.append(f"PIPE MISS bone[{bone.table_index:02d}] {pipeline} key=0x{bone.bone_key:08X}")
    return lines

VCS_PED_RUNTIME_FRAME_GLOBAL_ROWS = {
    'male_base01': ((1.0, -2.137341438222958e-18, 0.0, 4.467536118824e-09), (2.137341438222958e-18, 1.0, 0.0, 0.034034959971904755), (0.0, 0.0, 1.0, 1.3512089252471924), (0.0, 0.0, 0.0, 1.0)),
    'root': ((-1.430511474609375e-06, -1.0, 0.0, 0.0), (1.0, -1.430511474609375e-06, 0.0, 0.0), (0.0, -0.0, 1.0, 0.996275007724762), (0.0, 0.0, 0.0, 1.0)),
    'pelvis': ((1.4007091522216797e-06, -2.8014183044433594e-06, -1.0, 0.0), (2.0037305148434825e-12, 1.0, -2.8312206268310547e-06, 0.0), (1.0, 0.0, 1.3709068298339844e-06, 0.996275007724762), (0.0, 0.0, 0.0, 1.0)),
    'spine': ((5.161336602554911e-08, 1.3589575473815785e-06, -1.0, 3.177025531542199e-09), (0.0007962306262925267, 0.9999997019767761, 1.3291955838212743e-06, -0.00014456371718551964), (0.9999997019767761, -0.0007962306262925267, 2.0728975869133137e-08, 1.0960111618041992), (0.0, 0.0, 0.0, 1.0)),
    'spine1': ((5.161336602554911e-08, 1.3589575473815785e-06, -1.0, 8.823777264410637e-09), (0.0007962306262925267, 0.9999997019767761, 1.3291955838212743e-06, -0.00019139170763082802), (0.9999997019767761, -0.0007962306262925267, 2.0728975869133137e-08, 1.2775012254714966), (0.0, 0.0, 0.0, 1.0)),
    'neck': ((-6.706928701305515e-08, 1.3581900475401198e-06, -1.0, 1.6097574828677352e-08), (0.08230458945035934, 0.99660724401474, 1.318259251092968e-06, -0.0001101364177884534), (0.99660724401474, -0.08230458945035934, -2.0842934134179814e-07, 1.5177991390228271), (0.0, 0.0, 0.0, 1.0)),
    'head': ((4.09056042371958e-08, 1.3594043366538244e-06, -1.0, 5.054726415210098e-09), (-1.4280445839176537e-06, 1.0, 1.3296015595187782e-06, 0.011305262334644794), (1.0, 1.4280442428571405e-06, 1.1105230512953312e-08, 1.6560256481170654), (0.0, 0.0, 0.0, 1.0)),
    'jaw': ((0.9999999403953552, 1.3594060419563903e-06, -1.3299987813297776e-06, 3.102416457068102e-08), (-1.3296033785081818e-06, 1.0, 2.468798498966862e-09, 0.030347924679517746), (1.3598011037174729e-06, -2.467231752234511e-09, 0.9999999403953552, 1.6580487489700317), (0.0, 0.0, 0.0, 1.0)),
    'bip01_l_clavicle': ((-0.9998235106468201, 1.4161036006044014e-06, 0.018785972148180008, -0.030353982001543045), (-1.4445416809394374e-06, -1.0, -6.428360421750767e-08, -1.210070621482373e-07), (0.018785974010825157, -8.658349059942338e-08, 0.9998235106468201, 1.5177900791168213), (0.0, 0.0, 0.0, 1.0)),
    'l_upperarm': ((-0.33415302634239197, -0.26167112588882446, -0.905466616153717, -0.20133663713932037), (0.5750886797904968, -0.8177363872528076, 0.02408745512366295, -3.680422366869607e-07), (-0.7467360496520996, -0.5126747488975525, 0.4237332046031952, 1.5210028886795044), (0.0, 0.0, 0.0, 1.0)),
    'l_forearm': ((-0.30512621998786926, -0.29500502347946167, -0.905466616153717, -0.2941475212574005), (0.657017171382904, -0.7534906268119812, 0.024087443947792053, 0.15973031520843506), (-0.6893666386604309, -0.5875574946403503, 0.4237331449985504, 1.3135972023010254), (0.0, 0.0, 0.0, 1.0)),
    'l_hand': ((-0.26784390211105347, 0.905204176902771, -0.32994672656059265, -0.3750544786453247), (0.742031455039978, -0.02462085150182247, -0.6699127554893494, 0.33394432067871094), (-0.614531397819519, -0.4242629110813141, -0.6650955677032471, 1.1308053731918335), (0.0, 0.0, 0.0, 1.0)),
    'l_finger': ((-0.26784390211105347, 0.905466616153717, -0.3292258381843567, -0.40409088134765625), (0.742031455039978, -0.02408743090927601, -0.6699321866035461, 0.41438645124435425), (-0.614531397819519, -0.4237331748008728, -0.6654331684112549, 1.0641852617263794), (0.0, 0.0, 0.0, 1.0)),
    'bip01_r_clavicle': ((0.9998235106468201, 1.4161034869175637e-06, 0.018785983324050903, 0.03035401552915573), (1.4441035318668582e-06, -1.0, 1.1870826455151473e-07, -3.333495612878323e-08), (0.018785983324050903, -8.910305382414663e-08, -0.9998235106468201, 1.5177900791168213), (0.0, 0.0, 0.0, 1.0)),
    'r_upperarm': ((0.3316374123096466, 0.2652413249015808, -0.9053527116775513, 0.20133666694164276), (0.5765477418899536, -0.8165821433067322, -0.02804054692387581, 2.1362528457302687e-07), (-0.7467323541641235, -0.5126798152923584, -0.42373350262641907, 1.5210028886795044), (0.0, 0.0, 0.0, 1.0)),
    'r_forearm': ((0.3048934042453766, 0.29559487104415894, -0.9053527116775513, 0.29344886541366577), (0.6516339182853699, -0.7580150961875916, -0.028040511533617973, 0.1601361632347107), (-0.694559633731842, -0.5814092755317688, -0.4237334728240967, 1.3135981559753418), (0.0, 0.0, 0.0, 1.0)),
    'r_hand': ((0.26755040884017944, -0.9050891399383545, -0.33049988746643066, 0.37429410219192505), (0.7372397184371948, -0.028558198362588882, 0.6750273108482361, 0.3329227566719055), (-0.6203984022140503, -0.4242614805698395, 0.6596270799636841, 1.1294294595718384), (0.0, 0.0, 0.0, 1.0)),
    'r_finger': ((0.2675504982471466, -0.905351996421814, -0.32977911829948425, 0.4032987356185913), (0.7372397184371948, -0.028020642697811127, 0.6750498414039612, 0.4128454029560089), (-0.6203984022140503, -0.42373618483543396, 0.6599646806716919, 1.0621732473373413), (0.0, 0.0, 0.0, 1.0)),
    'l_thigh': ((9.81965442292676e-08, -1.3347868161872611e-06, 1.0, -0.10089899599552155), (0.04557426646351814, 0.9989609718322754, 1.3587272178483545e-06, -1.892473591169619e-07), (-0.9989609718322754, 0.04557426646351814, 1.8872876239584002e-07, 0.9962750673294067), (0.0, 0.0, 0.0, 1.0)),
    'l_calf': ((2.7663955393109063e-07, -1.3115635510985157e-06, 1.0, -0.10089896619319916), (-0.0765017494559288, 0.9970694184303284, 1.3586858358394238e-06, 0.020030789077281952), (-0.9970694184303284, -0.0765017494559288, 2.0529428468307742e-07, 0.5572077631950378), (0.0, 0.0, 0.0, 1.0)),
    'l_foot': ((-4.0884270191554606e-08, -1.4152042240311857e-06, 1.0, -0.1008988618850708), (8.171591048267146e-08, 0.9999999403953552, 1.4450067737925565e-06, -0.01673281379044056), (-0.9999999403953552, 8.171618759433841e-08, -1.1081792372635846e-08, 0.07805705815553665), (0.0, 0.0, 0.0, 1.0)),
    'l_toe0': ((-1.4301052715381957e-06, 8.558771469324711e-08, 1.0, -0.10089904069900513), (0.9999998807907104, -2.2111199982077778e-08, 1.4599078212995664e-06, 0.10902117192745209), (2.2111541042590943e-08, 0.9999998807907104, -5.578531769856454e-08, 0.00200808048248291), (0.0, 0.0, 0.0, 1.0)),
    'r_thigh': ((-7.931470236144378e-08, -1.4989196870374144e-06, 1.0, 0.10089899599552155), (0.04557426646351814, 0.9989609718322754, 1.5307798548747087e-06, 1.0223379831586499e-07), (-0.9989609718322754, 0.04557426646351814, 1.8882200691905382e-08, 0.996275007724762), (0.0, 0.0, 0.0, 1.0)),
    'r_calf': ((1.0987241694238037e-07, -1.4986715086706681e-06, 1.0, 0.10089895129203796), (-0.0765017494559288, 0.9970694184303284, 1.5324878859246382e-06, 0.02003108523786068), (-0.9970694184303284, -0.0765017494559288, 2.4701771295099206e-08, 0.5572077035903931), (0.0, 0.0, 0.0, 1.0)),
    'r_foot': ((-4.0913210597182115e-08, -1.4148914715406136e-06, 1.0, 0.10089898109436035), (8.171615206720162e-08, 0.9999999403953552, 1.4446943623624975e-06, -0.016732515767216682), (-0.9999999403953552, 8.171620891062048e-08, -1.1110759423615946e-08, 0.07805702835321426), (0.0, 0.0, 0.0, 1.0)),
    'r_toe0': ((-1.4297925190476235e-06, 8.561665509887462e-08, 1.0, 0.10089880228042603), (0.9999998807907104, -2.2111441566607937e-08, 1.4595954098695074e-06, 0.10902146995067596), (2.2111562358873016e-08, 0.9999998807907104, -5.581428652590148e-08, 0.0020080506801605225), (0.0, 0.0, 0.0, 1.0)),
}

def defaultVcsPedGlobalMatrixForBoneName(bone_name: str):
    if Matrix is None:
        return None
    try:
        canon = normalizeAnimBoneName(str(bone_name))
    except Exception:
        canon = str(bone_name or '').strip().lower().replace(' ', '').replace('_', '')
    if not canon:
        return None
    for raw_name, rows in VCS_PED_RUNTIME_FRAME_GLOBAL_ROWS.items():
        try:
            if normalizeAnimBoneName(raw_name) == canon:
                return Matrix(rows)
        except Exception:
            continue
    return None

MDL_LOCAL_MATRIX_PROPERTY_NAMES = (
    "bleeds_mdl_import_local_matrix",
    "bleeds_mdl_export_local_matrix",
    "bleeds_frame_local_matrix",
    "bleeds_mdl_import_global_matrix",
)

BLENDER_LOCAL_MATRIX_PROPERTY_NAMES = (
    "bleeds_blender_import_local_matrix",
    "bleeds_blender_rest_local_matrix",
)

MDL_GLOBAL_MATRIX_PROPERTY_NAMES = (
    "bleeds_mdl_import_global_matrix",
    "bleeds_mdl_frame_import_global_matrix",
    "bleeds_mdl_export_world_matrix",
    "bleeds_frame_matrix",
)

def matrixFromFlatProperty(values):
    if Matrix is None:
        return None
    try:
        raw = [float(value) for value in list(values)]
    except Exception:
        return None
    if len(raw) < 16:
        return None
    return Matrix((
        (raw[0], raw[1], raw[2], raw[3]),
        (raw[4], raw[5], raw[6], raw[7]),
        (raw[8], raw[9], raw[10], raw[11]),
        (raw[12], raw[13], raw[14], raw[15]),
    ))

def getMatrixCustomProperty(owner, names: Iterable[str]):
    if owner is None:
        return None, "none"
    for name in names:
        try:
            if name not in owner:
                continue
            matrix = matrixFromFlatProperty(owner.get(name))
            if matrix is not None:
                return matrix, str(name)
        except Exception:
            continue
    return None, "none"

def getArmatureRestPropertyOwners(armature_object):
    owners = []
    seen = set()

    def addOwner(owner):
        if owner is None:
            return
        marker = id(owner)
        if marker in seen:
            return
        seen.add(marker)
        owners.append(owner)

    addOwner(armature_object)
    try:
        addOwner(armature_object.data)
    except Exception:
        pass

    parent = getattr(armature_object, "parent", None)
    guard = 0
    while parent is not None and guard < 16:
        addOwner(parent)
        try:
            addOwner(parent.data)
        except Exception:
            pass
        parent = getattr(parent, "parent", None)
        guard += 1

    try:
        for collection in getattr(armature_object, "users_collection", []) or []:
            for obj in getattr(collection, "objects", []) or []:
                addOwner(obj)
                try:
                    addOwner(obj.data)
                except Exception:
                    pass
    except Exception:
        pass

    return owners

def readStringListProperty(owner, name: str):
    if owner is None:
        return []
    try:
        if name not in owner:
            return []
        value = owner.get(name)
    except Exception:
        return []
    try:
        return [str(item) for item in list(value)]
    except Exception:
        return []

def readFloatListProperty(owner, name: str):
    if owner is None:
        return []
    try:
        if name not in owner:
            return []
        value = owner.get(name)
    except Exception:
        return []
    try:
        return [float(item) for item in list(value)]
    except Exception:
        return []

def findFrameNameIndex(names: Sequence[str], bone_name: str) -> Optional[int]:
    target = str(bone_name)
    try:
        exact_index = list(names).index(target)
        return int(exact_index)
    except Exception:
        pass

    target_norm = normalizeAnimBoneName(target)
    for index, name in enumerate(names):
        try:
            if normalizeAnimBoneName(str(name)) == target_norm:
                return int(index)
        except Exception:
            continue
    return None

def getNamedMatrixFromFrameArray(owner, bone_name: str, matrix_property_names: Sequence[str]):
    if Matrix is None or owner is None:
        return None, "none"
    names = readStringListProperty(owner, "bleeds_mdl_frame_names")
    if not names:
        return None, "none"
    index = findFrameNameIndex(names, bone_name)
    if index is None:
        return None, "none"

    for matrix_property_name in matrix_property_names:
        values = readFloatListProperty(owner, matrix_property_name)
        start = int(index) * 16
        end = start + 16
        if len(values) < end:
            continue
        matrix = matrixFromFlatProperty(values[start:end])
        if matrix is not None:
            owner_name = getattr(owner, "name", owner.__class__.__name__)
            return matrix, f"{matrix_property_name}[{index}] on {owner_name}"
    return None, "none"

def getNamedMatrixFromArmatureFrameArrays(armature_object, pose_bone, matrix_property_names: Sequence[str]):
    if Matrix is None or armature_object is None or pose_bone is None:
        return None, "none"
    bone_name = str(getattr(pose_bone, "name", ""))
    if not bone_name:
        return None, "none"
    for owner in getArmatureRestPropertyOwners(armature_object):
        matrix, source = getNamedMatrixFromFrameArray(owner, bone_name, matrix_property_names)
        if matrix is not None:
            return matrix, source
    return None, "none"

def matrixRestDifferenceScore(a, b):
    if Matrix is None or a is None or b is None:
        return 0.0
    try:
        ma = Matrix(a)
        mb = Matrix(b)
    except Exception:
        return 0.0
    total = 0.0
    try:
        for row in range(4):
            for col in range(4):
                total = max(total, abs(float(ma[row][col]) - float(mb[row][col])))
    except Exception:
        return 0.0
    return float(total)

def getImportedMdlRestGlobalMatrix(armature_object, pose_bone):
    if Matrix is None or armature_object is None or pose_bone is None:
        return None, "none"
    data_bone = armature_object.data.bones.get(pose_bone.name)
    for owner in (pose_bone, data_bone):
        matrix, source = getMatrixCustomProperty(owner, MDL_GLOBAL_MATRIX_PROPERTY_NAMES)
        if matrix is not None:
            return matrix, source

    matrix, source = getNamedMatrixFromArmatureFrameArrays(
        armature_object,
        pose_bone,
        (
            "bleeds_mdl_frame_import_global_matrices",
            "bleeds_mdl_frame_global_matrices",
            "bleeds_mdl_frame_world_matrices",
            "bleeds_mdl_frame_computed_world_matrices",
        ),
    )
    if matrix is not None:
        return matrix, source

    # Do not inject a canned VCS skeleton basis into arbitrary/custom/LCS rigs.
    # The fallback remains available only as an explicit diagnostic opt-in.
    allow_default_vcs_basis = False
    for owner in (armature_object, getattr(armature_object, "data", None)):
        if owner is None:
            continue
        try:
            if "bleeds_anim_allow_default_vcs_runtime_basis" in owner:
                allow_default_vcs_basis = bool(owner["bleeds_anim_allow_default_vcs_runtime_basis"])
                if allow_default_vcs_basis:
                    break
        except Exception:
            pass
    if allow_default_vcs_basis:
        default_matrix = defaultVcsPedGlobalMatrixForBoneName(getattr(pose_bone, 'name', ''))
        if default_matrix is not None:
            return default_matrix, 'explicit default VCS PS2 PED runtime frame matrix fallback'

    return None, "none"

def getImportedMdlRestLocalFromGlobal(armature_object, pose_bone):
    this_global, this_source = getImportedMdlRestGlobalMatrix(armature_object, pose_bone)
    if this_global is None:
        return None, "none"
    try:
        parent_pose = pose_bone.parent
    except Exception:
        parent_pose = None
    if parent_pose is None:
        return this_global.copy(), f"{this_source} as root local"
    parent_global, parent_source = getImportedMdlRestGlobalMatrix(armature_object, parent_pose)
    if parent_global is None:
        return this_global.copy(), f"{this_source} without parent global"
    try:
        return parent_global.inverted_safe() @ this_global, f"{this_source} relative to parent {parent_source}"
    except Exception:
        try:
            return parent_global.inverted() @ this_global, f"{this_source} relative to parent {parent_source}"
        except Exception:
            return this_global.copy(), f"{this_source} local fallback after parent invert fail"

def getBlenderRestLocalMatrix(armature_object, pose_bone):
    if Matrix is None or armature_object is None or pose_bone is None:
        return None
    data_bone = armature_object.data.bones.get(pose_bone.name)
    if data_bone is None:
        return Matrix.Identity(4)
    try:
        if data_bone.parent is not None:
            return data_bone.parent.matrix_local.inverted() @ data_bone.matrix_local
        return data_bone.matrix_local.copy()
    except Exception:
        return Matrix.Identity(4)

def getImportedMdlRestLocalMatrix(armature_object, pose_bone):
    if Matrix is None or armature_object is None or pose_bone is None:
        return None, "none"
    data_bone = armature_object.data.bones.get(pose_bone.name)

    computed_from_global, computed_source = getImportedMdlRestLocalFromGlobal(armature_object, pose_bone)

    stored_matrix = None
    stored_source = "none"
    for owner in (pose_bone, data_bone):
        matrix, source = getMatrixCustomProperty(owner, MDL_LOCAL_MATRIX_PROPERTY_NAMES[:3])
        if matrix is not None:
            stored_matrix = matrix
            stored_source = source
            break

    if stored_matrix is None:
        array_local, array_source = getNamedMatrixFromArmatureFrameArrays(
            armature_object,
            pose_bone,
            (
                "bleeds_mdl_frame_import_local_matrices",
                "bleeds_mdl_frame_local_matrices",
            ),
        )
        if array_local is not None:
            stored_matrix = array_local
            stored_source = array_source

    if stored_matrix is not None and computed_from_global is not None:
        diff = matrixRestDifferenceScore(stored_matrix, computed_from_global)

        if diff > 0.01:
            return computed_from_global, f"repaired local from {computed_source}; rejected stale {stored_source} diff={diff:.6f}"
        return stored_matrix, stored_source

    if computed_from_global is not None:
        return computed_from_global, f"computed from {computed_source}"

    if stored_matrix is not None:
        return stored_matrix, stored_source

    try:
        if data_bone is not None and data_bone.parent is None:
            for owner in (pose_bone, data_bone):
                matrix, source = getMatrixCustomProperty(owner, ("bleeds_mdl_import_global_matrix", "bleeds_frame_matrix"))
                if matrix is not None:
                    return matrix, source
    except Exception:
        pass

    blender_rest = getBlenderRestLocalMatrix(armature_object, pose_bone)
    if blender_rest is not None:
        return blender_rest, "blender bone.matrix_local fallback"
    return Matrix.Identity(4), "identity fallback"

def getImportedBlenderRestLocalMatrix(armature_object, pose_bone):
    if Matrix is None or armature_object is None or pose_bone is None:
        return None, "none"

    data_bone = armature_object.data.bones.get(pose_bone.name)
    live_rest = getBlenderRestLocalMatrix(armature_object, pose_bone)

    stored_matrix = None
    stored_source = "none"
    for owner in (pose_bone, data_bone):
        matrix, source = getMatrixCustomProperty(owner, BLENDER_LOCAL_MATRIX_PROPERTY_NAMES)
        if matrix is not None:
            stored_matrix = matrix
            stored_source = source
            break

    if stored_matrix is None:
        matrix, source = getNamedMatrixFromArmatureFrameArrays(
            armature_object,
            pose_bone,
            (
                "bleeds_blender_frame_import_local_matrices",
                "bleeds_blender_frame_local_matrices",
            ),
        )
        if matrix is not None:
            stored_matrix = matrix
            stored_source = source

    # The stored Blender matrix describes the rest pose at import time. If the
    # artist edited the armature in Edit Mode after importing, matrix_local is
    # now the correct target rest basis for animation retargeting. Reusing the
    # stale import-time target basis makes otherwise-valid Leeds absolute-local
    # animation deltas contort the edited rig.
    if live_rest is not None and stored_matrix is not None:
        diff = matrixRestDifferenceScore(live_rest, stored_matrix)
        if diff > 1.0e-4:
            return live_rest, f"live edited Blender rest; replaced stale {stored_source} diff={diff:.6f}"
        return stored_matrix, stored_source

    if live_rest is not None:
        return live_rest, "live Blender bone.matrix_local"
    if stored_matrix is not None:
        return stored_matrix, stored_source
    return Matrix.Identity(4), "identity fallback"

def rotationOnlyMatrix(matrix_value):
    if Matrix is None:
        return None
    try:
        quat = matrix_value.to_quaternion()
        return quat.to_matrix().to_4x4()
    except Exception:
        return Matrix.Identity(4)

def convertMdlLocalDeltaToBlenderBasis(source_mdl_rest, blender_rest, source_delta):
    if Matrix is None:
        return source_delta
    if source_mdl_rest is None or blender_rest is None or source_delta is None:
        return source_delta

    source_rot = rotationOnlyMatrix(source_mdl_rest)
    blender_rot = rotationOnlyMatrix(blender_rest)
    if source_rot is None or blender_rot is None:
        return source_delta

    try:
        source_to_blender_child = blender_rot.inverted_safe() @ source_rot
    except Exception:
        source_to_blender_child = Matrix.Identity(4)
    try:
        return source_to_blender_child @ source_delta @ source_to_blender_child.inverted_safe()
    except Exception:
        return source_delta

def normalizeAnimQuaternion(rotation_xyzw: Tuple[float, float, float, float]):
    if Quaternion is None:
        return None
    x, y, z, w = rotation_xyzw
    qx = float(x)
    qy = float(y)
    qz = float(z)
    qw = float(w)
    magnitude = math.sqrt(qw * qw + qx * qx + qy * qy + qz * qz)
    if not math.isfinite(magnitude) or magnitude <= 0.000001:
        return Quaternion((1.0, 0.0, 0.0, 0.0))
    inv_magnitude = 1.0 / magnitude
    return Quaternion((
        qw * inv_magnitude,
        qx * inv_magnitude,
        qy * inv_magnitude,
        qz * inv_magnitude,
    ))

def makePoseQuaternionContinuous(pose_bone, previous_quaternion=None):
    if Quaternion is None or pose_bone is None:
        return previous_quaternion
    try:
        current = pose_bone.rotation_quaternion.copy()
    except Exception:
        return previous_quaternion

    try:
        current.normalize()
    except Exception:
        pass

    if previous_quaternion is not None:
        try:
            dot = (
                float(current.w) * float(previous_quaternion.w)
                + float(current.x) * float(previous_quaternion.x)
                + float(current.y) * float(previous_quaternion.y)
                + float(current.z) * float(previous_quaternion.z)
            )
            if dot < 0.0:
                current = Quaternion((-float(current.w), -float(current.x), -float(current.y), -float(current.z)))
        except Exception:
            pass

    try:
        pose_bone.rotation_quaternion = current
    except Exception:
        pass
    try:
        return current.copy()
    except Exception:
        return current


def finalizeImportedAnimActionCurves(action, start_frame: float, end_frame: float) -> int:
    if action is None:
        return 0
    changed = 0
    lo = min(float(start_frame), float(end_frame)) - 1.0e-5
    hi = max(float(start_frame), float(end_frame)) + 1.0e-5
    try:
        fcurves = list(action.fcurves)
    except Exception:
        return 0

    for fcurve in fcurves:
        try:
            points = list(fcurve.keyframe_points)
        except Exception:
            continue
        for keyframe in points:
            try:
                frame_value = float(keyframe.co[0])
            except Exception:
                continue
            if frame_value < lo or frame_value > hi:
                continue
            try:
                # Leeds skeletal keys are sampled/interpolated by the game;
                # Blender's default Bezier handles can overshoot quaternion
                # components and visibly contort an otherwise-correct rig.
                keyframe.interpolation = 'LINEAR'
                changed += 1
            except Exception:
                pass
    try:
        action["bleeds_anim_interpolation"] = "LINEAR"
        action["bleeds_anim_linear_key_count"] = int(changed)
    except Exception:
        pass
    return int(changed)


def safeMatrixInverted(matrix_value):
    if Matrix is None:
        return None
    try:
        return matrix_value.inverted()
    except Exception:
        try:
            return matrix_value.inverted_safe()
        except Exception:
            return Matrix.Identity(4)

def poseBoneDepth(pose_bone) -> int:
    depth = 0
    parent = getattr(pose_bone, "parent", None)
    while parent is not None and depth < 512:
        depth += 1
        parent = getattr(parent, "parent", None)
    return depth

def getPoseBoneByName(armature_object, name: str):
    try:
        return armature_object.pose.bones.get(str(name))
    except Exception:
        return None

def getPoseBoneRestLocalMatrixForAbsolutePose(armature_object, pose_bone):

    rest_local, rest_source = getImportedMdlRestLocalMatrix(armature_object, pose_bone)
    if rest_local is not None:
        return rest_local, rest_source
    blender_rest = getBlenderRestLocalMatrix(armature_object, pose_bone)
    if blender_rest is not None:
        return blender_rest, "blender bone.matrix_local fallback"
    return Matrix.Identity(4), "identity fallback"

def resolveBoneLocalForTime(
    armature_object,
    pose_bone,
    bone_by_pose_name: Dict[str, BoneAnim],
    time_value: float,
    *,
    apply_rotation: bool,
    apply_translation: bool,
    translation_scale: float,
    apply_root_motion: bool,
) -> Tuple[object, str, bool]:
    rest_local, rest_source = getPoseBoneRestLocalMatrixForAbsolutePose(armature_object, pose_bone)
    anim_bone = bone_by_pose_name.get(str(pose_bone.name))
    if anim_bone is None:
        return rest_local, rest_source, False

    resolved_direct_id, _reason = resolvePedAnimBoneId(anim_bone)
    is_root_bone = int(resolved_direct_id if resolved_direct_id is not None else -1) == 0
    root_translation_locked = is_root_bone and not bool(apply_root_motion)

    sample = sampleBoneAnimFrameAtTime(anim_bone, time_value)
    if sample is None:
        return rest_local, rest_source, False

    target_local = composeAnimLocalMatrix(
        sample,
        rest_local,
        bone=anim_bone,
        apply_rotation=apply_rotation,
        apply_translation=bool(apply_translation) and not root_translation_locked,
        translation_scale=translation_scale,
    )
    if target_local is None:
        return rest_local, rest_source, False
    if root_translation_locked:
        return target_local, rest_source + " / root translation locked, root rotation applied", True
    return target_local, rest_source, True

def applyAnimEntryAsAbsolutePose(
    armature_object,
    entry: AnimEntry,
    mapped_items: Sequence[Tuple[BoneAnim, object, str]],
    *,
    fps: float,
    start_frame: float,
    apply_rotation: bool,
    apply_translation: bool,
    translation_scale: float,
    apply_root_motion: bool,
) -> Tuple[int, List[str]]:
    if Matrix is None:
        return 0, ["absolute-pose solver unavailable: mathutils.Matrix is missing"]

    bone_by_pose_name: Dict[str, BoneAnim] = {}
    reason_by_pose_name: Dict[str, str] = {}
    for anim_bone, pose_bone, reason in mapped_items:
        bone_by_pose_name[str(pose_bone.name)] = anim_bone
        reason_by_pose_name[str(pose_bone.name)] = str(reason)

    pose_bones = [pose_bone for _anim_bone, pose_bone, _reason in mapped_items]
    pose_bones.sort(key=poseBoneDepth)
    timeline = buildAnimationTimeline(entry)
    keyed_count = 0
    solver_log: List[str] = []
    root_locked_count = 0
    rest_source_counts: Dict[str, int] = {}
    previous_quaternion_by_bone: Dict[str, object] = {}

    for time_value in timeline:
        target_global_by_name: Dict[str, object] = {}
        local_source_by_name: Dict[str, str] = {}
        local_applied_by_name: Dict[str, bool] = {}

        def buildTargetGlobal(pose_bone):
            bone_name = str(pose_bone.name)
            if bone_name in target_global_by_name:
                return target_global_by_name[bone_name]

            parent = getattr(pose_bone, "parent", None)
            if parent is not None:
                parent_global = buildTargetGlobal(parent)
            else:
                parent_global = Matrix.Identity(4)

            local_matrix, source, was_anim_applied = resolveBoneLocalForTime(
                armature_object,
                pose_bone,
                bone_by_pose_name,
                time_value,
                apply_rotation=apply_rotation,
                apply_translation=apply_translation,
                translation_scale=translation_scale,
                apply_root_motion=apply_root_motion,
            )
            local_source_by_name[bone_name] = source
            local_applied_by_name[bone_name] = bool(was_anim_applied)
            target_global = parent_global @ local_matrix
            target_global_by_name[bone_name] = target_global
            return target_global

        for pose_bone in pose_bones:
            parent = getattr(pose_bone, "parent", None)
            while parent is not None:
                buildTargetGlobal(parent)
                parent = getattr(parent, "parent", None)
            buildTargetGlobal(pose_bone)

        for pose_bone in pose_bones:
            bone_name = str(pose_bone.name)
            target_global = target_global_by_name.get(bone_name)
            if target_global is None:
                continue
            try:
                pose_bone.matrix = target_global
            except Exception:
                try:
                    loc, rot, sca = target_global.decompose()
                    pose_bone.location = loc
                    pose_bone.rotation_quaternion = rot
                    pose_bone.scale = sca
                except Exception:
                    continue

        try:
            bpy.context.view_layer.update()
        except Exception:
            pass

        frame_number = float(start_frame) + float(time_value) * float(fps)
        for pose_bone in pose_bones:
            bone_name = str(pose_bone.name)
            anim_bone = bone_by_pose_name.get(bone_name)
            if anim_bone is None:
                continue
            source = local_source_by_name.get(bone_name, "unknown")
            rest_source_counts[source] = rest_source_counts.get(source, 0) + 1
            resolved_direct_id, _reason = resolvePedAnimBoneId(anim_bone)
            is_root_bone = int(resolved_direct_id if resolved_direct_id is not None else -1) == 0
            if is_root_bone and not bool(apply_root_motion):
                root_locked_count += 1
            if local_applied_by_name.get(bone_name, False):
                if apply_rotation and anim_bone.has_rotation:
                    previous_quaternion_by_bone[bone_name] = makePoseQuaternionContinuous(
                        pose_bone, previous_quaternion_by_bone.get(bone_name)
                    )

                pose_bone.keyframe_insert(data_path="location", frame=frame_number)
                pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame_number)
                pose_bone.keyframe_insert(data_path="scale", frame=frame_number)
                keyed_count += 1

    solver_log.append(
        f"absolute-pose solver: key_times={len(timeline)} mapped_pose_bones={len(pose_bones)} "
        f"root_translation={'applied' if bool(apply_root_motion) else 'locked'} root_rotation=applied root_translation_locked_keys={root_locked_count}"
    )
    for source, count in sorted(rest_source_counts.items()):
        solver_log.append(f"absolute-pose rest source: {source}: {count}")
    for anim_bone, pose_bone, reason in mapped_items:
        solver_log.append(
            f"ABSPOSE bone[{anim_bone.table_index:02d}] {formatAnimBoneTarget(anim_bone)} -> {pose_bone.name!r} via {reason}"
        )
    return keyed_count, solver_log

def composeAnimLocalMatrix(
    anim_frame: AnimFrame,
    rest_local_matrix,
    *,
    bone: BoneAnim,
    apply_rotation: bool,
    apply_translation: bool,
    translation_scale: float,
):
    if Matrix is None or Vector is None:
        return None

    rest_local = rest_local_matrix.copy() if rest_local_matrix is not None else Matrix.Identity(4)
    rest_translation = rest_local.to_translation()
    rest_rotation = rest_local.to_quaternion()
    rest_scale = rest_local.to_scale()

    if apply_translation and bone.has_translation:
        tx, ty, tz = anim_frame.translation_xyz
        translation = Vector((
            float(tx) * float(translation_scale),
            float(ty) * float(translation_scale),
            float(tz) * float(translation_scale),
        ))
    else:
        translation = rest_translation

    if apply_rotation and bone.has_rotation:
        rotation = normalizeAnimQuaternion(anim_frame.rotation_xyzw)
    else:
        rotation = rest_rotation

    if rotation is None:
        rotation = Quaternion((1.0, 0.0, 0.0, 0.0))

    if bone.has_scale:
        sx, sy, sz = anim_frame.scale_xyz
        scale = Vector((float(sx), float(sy), float(sz)))
    else:
        scale = rest_scale

    matrix = Matrix.Translation(translation) @ rotation.to_matrix().to_4x4()
    try:
        matrix = matrix @ Matrix.Diagonal((float(scale.x), float(scale.y), float(scale.z), 1.0))
    except Exception:
        pass
    return matrix

def applyPoseFrameRawBasis(
    pose_bone,
    anim_frame: AnimFrame,
    bone: BoneAnim,
    *,
    apply_rotation: bool,
    apply_translation: bool,
    translation_scale: float,
) -> int:
    keyed = 0
    if apply_rotation and bone.has_rotation:
        quat = normalizeAnimQuaternion(anim_frame.rotation_xyzw)
        if quat is None:
            quat = Quaternion((1.0, 0.0, 0.0, 0.0))
        pose_bone.rotation_quaternion = quat
        keyed += 1

    if apply_translation and bone.has_translation:
        tx, ty, tz = anim_frame.translation_xyz
        pose_bone.location = (
            float(tx) * float(translation_scale),
            float(ty) * float(translation_scale),
            float(tz) * float(translation_scale),
        )
        keyed += 1

    return keyed

def applyPoseFrameRestDelta(
    armature_object,
    pose_bone,
    anim_frame: AnimFrame,
    bone: BoneAnim,
    *,
    apply_rotation: bool,
    apply_translation: bool,
    translation_scale: float,
    apply_root_motion: bool,
):
    if Matrix is None:
        return 0, "no mathutils Matrix"

    resolved_direct_id, _reason = resolvePedAnimBoneId(bone)
    is_root_bone = int(resolved_direct_id if resolved_direct_id is not None else -1) == 0
    root_translation_locked = is_root_bone and not bool(apply_root_motion)

    mdl_rest_local, mdl_rest_source = getImportedMdlRestLocalMatrix(armature_object, pose_bone)
    if mdl_rest_local is None:
        mdl_rest_local = Matrix.Identity(4)
        mdl_rest_source = "identity fallback"

    blender_rest_local, blender_rest_source = getImportedBlenderRestLocalMatrix(armature_object, pose_bone)
    if blender_rest_local is None:
        blender_rest_local = getBlenderRestLocalMatrix(armature_object, pose_bone) or Matrix.Identity(4)
        blender_rest_source = "live Blender bone.matrix_local fallback"

    target_mdl_local = composeAnimLocalMatrix(
        anim_frame,
        mdl_rest_local,
        bone=bone,
        apply_rotation=apply_rotation,
        apply_translation=bool(apply_translation) and not root_translation_locked,
        translation_scale=translation_scale,
    )
    if target_mdl_local is None:
        return 0, f"{mdl_rest_source} -> {blender_rest_source}"

    mdl_rest_inv = safeMatrixInverted(mdl_rest_local)
    source_delta = mdl_rest_inv @ target_mdl_local
    basis = convertMdlLocalDeltaToBlenderBasis(mdl_rest_local, blender_rest_local, source_delta)

    try:
        pose_bone.matrix_basis = basis
    except Exception:
        loc, rot, sca = basis.decompose()
        pose_bone.location = loc
        pose_bone.rotation_quaternion = rot
        pose_bone.scale = sca

    if root_translation_locked:
        return 1, f"MDL absolute-local rest delta source {mdl_rest_source} -> Blender basis {blender_rest_source}; root translation locked, root rotation applied"
    return 1, f"MDL absolute-local rest delta source {mdl_rest_source} -> Blender basis {blender_rest_source}"

def applyPoseFrameAnimReferenceDelta(
    armature_object,
    pose_bone,
    anim_frame: AnimFrame,
    reference_frame: AnimFrame,
    bone: BoneAnim,
    *,
    apply_rotation: bool,
    apply_translation: bool,
    translation_scale: float,
    apply_root_motion: bool,
):
    if Matrix is None or Quaternion is None:
        return 0, "no mathutils Matrix/Quaternion"

    resolved_direct_id, _reason = resolvePedAnimBoneId(bone)
    is_root_bone = int(resolved_direct_id if resolved_direct_id is not None else -1) == 0
    root_translation_locked = is_root_bone and not bool(apply_root_motion)

    blender_rest_local, blender_rest_source = getImportedBlenderRestLocalMatrix(armature_object, pose_bone)
    if blender_rest_local is None:
        blender_rest_local = getBlenderRestLocalMatrix(armature_object, pose_bone) or Matrix.Identity(4)
        blender_rest_source = "live Blender bone.matrix_local fallback"

    basis = Matrix.Identity(4)
    changed_basis = False

    if apply_rotation and bone.has_rotation:
        reference_rotation = normalizeAnimQuaternion(reference_frame.rotation_xyzw)
        current_rotation = normalizeAnimQuaternion(anim_frame.rotation_xyzw)
        if reference_rotation is None:
            reference_rotation = Quaternion((1.0, 0.0, 0.0, 0.0))
        if current_rotation is None:
            current_rotation = Quaternion((1.0, 0.0, 0.0, 0.0))

        # Leeds weapon/layer clips use current * inverse(reference).
        # The opposite order rotates around the wrong local axes.
        source_delta = current_rotation @ reference_rotation.inverted()
        source_delta_matrix = source_delta.to_matrix().to_4x4()

        # The first ANIM key is the reference pose, not the source axis basis.
        # Rebase through the actual imported MDL rest-local basis.
        mdl_rest_local, _mdl_rest_source = getImportedMdlRestLocalMatrix(armature_object, pose_bone)
        if mdl_rest_local is None:
            mdl_rest_local = getBlenderRestLocalMatrix(armature_object, pose_bone) or Matrix.Identity(4)

        basis = convertMdlLocalDeltaToBlenderBasis(
            mdl_rest_local,
            blender_rest_local,
            source_delta_matrix,
        )
        changed_basis = True

    if apply_translation and bone.has_translation and not root_translation_locked:
        tx = (float(anim_frame.translation_xyz[0]) - float(reference_frame.translation_xyz[0])) * float(translation_scale)
        ty = (float(anim_frame.translation_xyz[1]) - float(reference_frame.translation_xyz[1])) * float(translation_scale)
        tz = (float(anim_frame.translation_xyz[2]) - float(reference_frame.translation_xyz[2])) * float(translation_scale)
        try:
            basis.translation = Vector((tx, ty, tz))
        except Exception:
            pass
        changed_basis = True

    if not changed_basis:
        return 0, f"ANIM first-key delta -> Blender basis {blender_rest_source}"

    try:
        pose_bone.matrix_basis = basis
    except Exception:
        loc, rot, sca = basis.decompose()
        pose_bone.location = loc
        pose_bone.rotation_mode = "QUATERNION"
        pose_bone.rotation_quaternion = rot
        pose_bone.scale = sca

    if root_translation_locked:
        return 1, f"ANIM first-key delta -> Blender basis {blender_rest_source}; root translation locked"
    return 1, f"ANIM first-key delta -> Blender basis {blender_rest_source}"

def resetArmaturePoseToRest(armature_object) -> int:
    reset_count = 0
    if armature_object is None:
        return reset_count
    for pose_bone in armature_object.pose.bones:
        try:
            pose_bone.rotation_mode = "QUATERNION"
            pose_bone.matrix_basis = Matrix.Identity(4)
            reset_count += 1
            continue
        except Exception:
            pass
        try:
            pose_bone.location = (0.0, 0.0, 0.0)
            pose_bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
            pose_bone.scale = (1.0, 1.0, 1.0)
            reset_count += 1
        except Exception:
            pass
    return reset_count

def applyPoseFramePlrRestRotationDelta(
    armature_object,
    pose_bone,
    anim_frame: AnimFrame,
    bone: BoneAnim,
    *,
    apply_rotation: bool,
    apply_translation: bool,
    translation_scale: float,
    apply_root_motion: bool,
):

    resolved_direct_id, _reason = resolvePedAnimBoneId(bone)
    is_root = int(resolved_direct_id if resolved_direct_id is not None else -1) == 0

    keyed = 0

    root_translation_locked = is_root and not bool(apply_root_motion)

    basis = Matrix.Identity(4)
    changed_basis = False

    if apply_rotation and bone.has_rotation:
        quat = normalizeAnimQuaternion(anim_frame.rotation_xyzw)
        if quat is None:
            quat = Quaternion((1.0, 0.0, 0.0, 0.0))
        try:
            source_delta = quat.to_matrix().to_4x4()
        except Exception:
            source_delta = Matrix.Identity(4)

        mdl_rest_local, _mdl_rest_source = getImportedMdlRestLocalMatrix(armature_object, pose_bone)
        if mdl_rest_local is None:
            mdl_rest_local = getBlenderRestLocalMatrix(armature_object, pose_bone) or Matrix.Identity(4)

        blender_rest_local, _blender_rest_source = getImportedBlenderRestLocalMatrix(armature_object, pose_bone)
        if blender_rest_local is None:
            blender_rest_local = getBlenderRestLocalMatrix(armature_object, pose_bone) or Matrix.Identity(4)

        try:
            basis = convertMdlLocalDeltaToBlenderBasis(mdl_rest_local, blender_rest_local, source_delta)
        except Exception:
            basis = source_delta
        changed_basis = True

    if apply_translation and bone.has_translation and not root_translation_locked:
        tx, ty, tz = anim_frame.translation_xyz
        try:
            basis.translation = Vector((
                float(tx) * float(translation_scale),
                float(ty) * float(translation_scale),
                float(tz) * float(translation_scale),
            ))
        except Exception:
            pass
        changed_basis = True

    if changed_basis:
        try:
            pose_bone.matrix_basis = basis
        except Exception:
            try:
                loc, rot, sca = basis.decompose()
                pose_bone.location = loc
                pose_bone.rotation_mode = "QUATERNION"
                pose_bone.rotation_quaternion = rot
                pose_bone.scale = sca
            except Exception:
                pass
        keyed += 1

    try:
        pose_bone.scale = (1.0, 1.0, 1.0)
    except Exception:
        pass

    return keyed

def isPedWeaponAnimationEntry(entry: AnimEntry) -> bool:
    try:
        name = str(getattr(entry, "name", "") or "").upper().strip()
    except Exception:
        name = ""

    if not name.startswith((
        "WEAPON_",
        "COLT45_",
        "PYTHON_",
        "SHOTGUN_",
        "RIFLE_",
        "UZI_",
        "TEC9_",
        "AK47_",
        "M4_",
    )):
        return False

    direct_ids = set()
    try:
        for bone in list(getattr(entry, "bones", []) or []):
            resolved_id, _reason = resolvePedAnimBoneId(bone)
            if resolved_id is not None:
                direct_ids.add(int(resolved_id))
    except Exception:
        return False

    return {0, 1, 2, 3, 4, 5}.issubset(direct_ids)

def isNativeLeedsMdlArmature(armature_object) -> bool:
    if armature_object is None or getattr(armature_object, "type", None) != "ARMATURE":
        return False

    owners = (armature_object, getattr(armature_object, "data", None))
    has_frame_arrays = False
    for owner in owners:
        if owner is None:
            continue
        try:
            if "bleeds_mdl_frame_ptrs" in owner or "bleeds_mdl_hierarchy_node_names" in owner:
                has_frame_arrays = True
                break
        except Exception:
            pass

    if not has_frame_arrays:
        return False

    imported_rest_bones = 0
    direct_id_bones = 0
    try:
        for bone in armature_object.data.bones:
            try:
                if "bleeds_mdl_import_local_matrix" in bone or "bleeds_mdl_import_global_matrix" in bone:
                    imported_rest_bones += 1
            except Exception:
                pass
            try:
                if getArmatureBoneDirectAnimId(bone) >= 0:
                    direct_id_bones += 1
            except Exception:
                pass
    except Exception:
        return False

    return imported_rest_bones >= 6 and direct_id_bones >= 6

def findImportedMdlRootForArmature(armature_object):
    current = armature_object
    while current is not None:
        for property_name in (
            "bleeds_mdl_source_filepath",
            "bleeds_mdl_filepath",
            "bleeds_mdl_atomic_frame_ptr",
            "bleeds_mdl_hierarchy_node_names",
        ):
            try:
                if property_name in current:
                    if current is not armature_object or property_name in {"bleeds_mdl_source_filepath", "bleeds_mdl_filepath"}:
                        return current
            except Exception:
                pass
        current = getattr(current, "parent", None)
    return getattr(armature_object, "parent", None)


def collectImportedMdlMeshesForArmature(armature_object, context=None) -> List[object]:
    if armature_object is None:
        return []

    meshes: List[object] = []
    seen_ids = set()

    def add_mesh(obj):
        if obj is None or getattr(obj, "type", None) != "MESH":
            return
        obj_id = id(obj)
        if obj_id in seen_ids:
            return
        seen_ids.add(obj_id)
        meshes.append(obj)

    try:
        for child in armature_object.children_recursive:
            add_mesh(child)
    except Exception:
        pass

    root_object = findImportedMdlRootForArmature(armature_object)
    if root_object is not None:
        try:
            for child in root_object.children_recursive:
                if getattr(child, "type", None) != "MESH":
                    continue
                is_stories_mesh = False
                try:
                    mdl_type = str(child.get("bleeds_mdl_type", "") or "").upper().strip()
                    skin_binding = str(child.get("bleeds_mdl_skin_binding", "") or "").upper().strip()
                    is_stories_mesh = mdl_type in {"PED", "CUT"} or skin_binding == "PED_SKIN_STREAM_ARMATURE"
                except Exception:
                    pass
                if is_stories_mesh or armatureDeformsMesh(armature_object, child):
                    add_mesh(child)
        except Exception:
            pass

    if context is not None:
        try:
            for obj in context.selected_objects:
                if getattr(obj, "type", None) == "MESH" and armatureDeformsMesh(armature_object, obj):
                    add_mesh(obj)
        except Exception:
            pass

    return meshes


def normalizeBindingBoneName(name: str) -> str:
    normalized = normalizeAnimBoneName(str(name or ""))
    return "".join(ch for ch in normalized if ch.isalnum())


def repairImportedMdlMeshBinding(mesh_object, armature_object) -> Tuple[bool, str]:
    if mesh_object is None or getattr(mesh_object, "type", None) != "MESH":
        return False, "not a mesh"
    if armature_object is None or getattr(armature_object, "type", None) != "ARMATURE":
        return False, "not an armature"

    changed = False
    armature_modifiers = []
    try:
        armature_modifiers = [modifier for modifier in mesh_object.modifiers if getattr(modifier, "type", None) == "ARMATURE"]
    except Exception:
        armature_modifiers = []

    armature_modifier = None
    for modifier in armature_modifiers:
        if getattr(modifier, "object", None) is armature_object:
            armature_modifier = modifier
            break

    if armature_modifier is None:
        for modifier in armature_modifiers:
            try:
                mesh_object.modifiers.remove(modifier)
                changed = True
            except Exception:
                pass
        armature_modifier = mesh_object.modifiers.new(name="Armature", type="ARMATURE")
        armature_modifier.object = armature_object
        changed = True
    else:
        for modifier in armature_modifiers:
            if modifier is armature_modifier:
                continue
            try:
                mesh_object.modifiers.remove(modifier)
                changed = True
            except Exception:
                pass

    for attribute_name, attribute_value in (
        ("use_vertex_groups", True),
        ("use_bone_envelopes", False),
        ("show_viewport", True),
        ("show_render", True),
    ):
        try:
            if getattr(armature_modifier, attribute_name) != attribute_value:
                setattr(armature_modifier, attribute_name, attribute_value)
                changed = True
        except Exception:
            pass

    try:
        bone_names = {str(bone.name) for bone in armature_object.data.bones}
    except Exception:
        bone_names = set()

    normalized_to_bone = {}
    for bone_name in bone_names:
        normalized = normalizeBindingBoneName(bone_name)
        if normalized and normalized not in normalized_to_bone:
            normalized_to_bone[normalized] = bone_name

    renamed_groups = 0
    unmatched_groups = []
    try:
        for vertex_group in mesh_object.vertex_groups:
            group_name = str(vertex_group.name)
            if group_name in bone_names:
                continue
            matching_name = normalized_to_bone.get(normalizeBindingBoneName(group_name))
            if matching_name:
                vertex_group.name = matching_name
                renamed_groups += 1
                changed = True
            else:
                unmatched_groups.append(group_name)
    except Exception:
        pass

    try:
        saved_world = mesh_object.matrix_world.copy()
        if getattr(mesh_object, "parent", None) is not armature_object or getattr(mesh_object, "parent_type", "") != "OBJECT":
            mesh_object.parent = armature_object
            mesh_object.parent_type = "OBJECT"
            mesh_object.parent_bone = ""
            mesh_object.matrix_parent_inverse = armature_object.matrix_world.inverted_safe()
            mesh_object.matrix_world = saved_world
            changed = True
    except Exception:
        pass

    weighted_vertices = 0
    matching_influences = 0
    total_influences = 0
    try:
        group_name_by_index = {group.index: str(group.name) for group in mesh_object.vertex_groups}
        for vertex in mesh_object.data.vertices:
            vertex_has_weight = False
            for membership in vertex.groups:
                weight = float(getattr(membership, "weight", 0.0))
                if weight <= 1.0e-8:
                    continue
                total_influences += 1
                group_name = group_name_by_index.get(int(membership.group), "")
                if group_name in bone_names:
                    matching_influences += 1
                    vertex_has_weight = True
            if vertex_has_weight:
                weighted_vertices += 1
    except Exception:
        pass

    valid = bool(armature_modifier is not None and getattr(armature_modifier, "object", None) is armature_object)
    valid = valid and weighted_vertices > 0 and matching_influences > 0

    try:
        mesh_object["bleeds_armature_parent_relationship"] = "OBJECT_CHILD_OF_ARMATURE"
        mesh_object["bleeds_armature_name"] = str(armature_object.name)
        mesh_object["bleeds_mdl_skin_binding"] = "PED_SKIN_STREAM_ARMATURE"
        mesh_object["bleeds_mdl_binding_repair_valid"] = bool(valid)
        mesh_object["bleeds_mdl_binding_repair_weighted_vertices"] = int(weighted_vertices)
        mesh_object["bleeds_mdl_binding_repair_matching_influences"] = int(matching_influences)
        mesh_object["bleeds_mdl_binding_repair_total_influences"] = int(total_influences)
        mesh_object["bleeds_mdl_binding_repair_renamed_groups"] = int(renamed_groups)
        mesh_object["bleeds_mdl_binding_repair_unmatched_groups"] = list(unmatched_groups[:64])
    except Exception:
        pass

    status = (
        f"mesh={getattr(mesh_object, 'name', '<unnamed>')!r} "
        f"valid={valid} weighted_vertices={weighted_vertices} "
        f"matching_influences={matching_influences}/{total_influences} "
        f"renamed_groups={renamed_groups} parent={getattr(getattr(mesh_object, 'parent', None), 'name', None)!r}"
    )
    return valid, status


def repairImportedMdlMeshBindingsForArmature(armature_object, context=None) -> Tuple[List[object], List[str]]:
    meshes = collectImportedMdlMeshesForArmature(armature_object, context)
    lines: List[str] = []
    valid_meshes: List[object] = []

    for mesh_object in meshes:
        valid, status = repairImportedMdlMeshBinding(mesh_object, armature_object)
        lines.append("BIND " + status)
        if valid:
            valid_meshes.append(mesh_object)

    if not meshes:
        lines.append(
            "BIND WARNING: no imported PED/CUT mesh parts were found for the target armature; "
            "the action can animate bones without deforming the visible MDL."
        )
    elif not valid_meshes:
        lines.append(
            "BIND ERROR: imported mesh parts were found, but none have usable vertex-group influences matching this armature."
        )

    return valid_meshes, lines


def captureEvaluatedMeshWorldPositions(mesh_object, depsgraph) -> List[Tuple[float, float, float]]:
    evaluated_object = mesh_object.evaluated_get(depsgraph)
    evaluated_mesh = getattr(evaluated_object, "data", None)
    if evaluated_mesh is None:
        return []

    matrix_world = evaluated_object.matrix_world
    positions: List[Tuple[float, float, float]] = []
    for vertex in evaluated_mesh.vertices:
        world = matrix_world @ vertex.co
        positions.append((float(world.x), float(world.y), float(world.z)))
    return positions


def measureImportedMdlAnimationMotion(
    armature_object,
    mesh_objects: Sequence[object],
    *,
    start_frame: float,
    end_frame: float,
) -> Tuple[bool, float, List[str]]:
    if bpy is None or not mesh_objects:
        return False, 0.0, ["DEFORM CHECK: no Blender mesh objects available"]

    scene = bpy.context.scene
    previous_frame = float(scene.frame_current)
    depsgraph = bpy.context.evaluated_depsgraph_get()

    sample_frames = [float(start_frame)]
    action = None
    try:
        action = armature_object.animation_data.action if armature_object.animation_data is not None else None
    except Exception:
        action = None

    if action is not None:
        key_frames = set()
        try:
            for fcurve in action.fcurves:
                for keyframe in fcurve.keyframe_points:
                    frame_value = float(keyframe.co[0])
                    if frame_value >= float(start_frame) - 1.0e-5 and frame_value <= float(end_frame) + 1.0e-5:
                        key_frames.add(frame_value)
        except Exception:
            key_frames = set()
        if key_frames:
            sample_frames.extend(sorted(key_frames))

    if len(sample_frames) <= 1:
        sample_frames.extend([
            float(start_frame) + (float(end_frame) - float(start_frame)) * 0.5,
            float(end_frame),
        ])

    unique_frames = []
    for frame in sample_frames:
        if not any(abs(frame - existing) <= 1.0e-5 for existing in unique_frames):
            unique_frames.append(frame)

    try:
        scene.frame_set(int(math.floor(unique_frames[0])), subframe=float(unique_frames[0] - math.floor(unique_frames[0])))
    except TypeError:
        scene.frame_set(int(round(unique_frames[0])))
    depsgraph.update()

    reference_positions = {}
    for mesh_object in mesh_objects:
        try:
            reference_positions[id(mesh_object)] = captureEvaluatedMeshWorldPositions(mesh_object, depsgraph)
        except Exception:
            reference_positions[id(mesh_object)] = []

    max_displacement = 0.0
    moving_mesh_names = set()
    checked_vertex_count = 0

    for frame in unique_frames[1:]:
        try:
            scene.frame_set(int(math.floor(frame)), subframe=float(frame - math.floor(frame)))
        except TypeError:
            scene.frame_set(int(round(frame)))
        depsgraph.update()

        for mesh_object in mesh_objects:
            reference = reference_positions.get(id(mesh_object), [])
            if not reference:
                continue
            try:
                current = captureEvaluatedMeshWorldPositions(mesh_object, depsgraph)
            except Exception:
                continue
            count = min(len(reference), len(current))
            checked_vertex_count += count
            for index in range(count):
                rx, ry, rz = reference[index]
                cx, cy, cz = current[index]
                dx = cx - rx
                dy = cy - ry
                dz = cz - rz
                displacement = math.sqrt(dx * dx + dy * dy + dz * dz)
                if displacement > max_displacement:
                    max_displacement = displacement
                if displacement > 1.0e-6:
                    moving_mesh_names.add(str(getattr(mesh_object, "name", "<unnamed>")))

    try:
        scene.frame_set(int(math.floor(previous_frame)), subframe=float(previous_frame - math.floor(previous_frame)))
    except TypeError:
        scene.frame_set(int(round(previous_frame)))
    depsgraph.update()

    moved = max_displacement > 1.0e-6
    lines = [
        "DEFORM CHECK: "
        f"moved={moved} max_world_vertex_displacement={max_displacement:.9f} "
        f"checked_vertices={checked_vertex_count} sampled_frames={unique_frames} "
        f"moving_meshes={sorted(moving_mesh_names)}"
    ]
    return moved, max_displacement, lines


def shouldAutoUseSafePedWeaponAnimMode(armature_object, entry: AnimEntry, requested_mode: str) -> bool:
    mode = str(requested_mode or "").upper().strip()
    if mode not in {"MDL_REST_DELTA", "DEFAULT", ""}:
        return False
    if not isPedWeaponAnimationEntry(entry):
        return False

    # A BLeeds-imported Leeds MDL already carries the source MDL local/rest basis.
    # Its ANIM tracks must be interpreted as absolute Leeds local poses relative to
    # that imported rest basis. First-key normalization is only the cross-rig path.
    return not isNativeLeedsMdlArmature(armature_object)

def shouldLogPedWeaponAbsoluteLocalMode(armature_object, entry: AnimEntry, requested_mode: str) -> bool:
    return False

def applyAnimEntryToArmature(
    armature_object,
    entry: AnimEntry,
    source_path: str,
    *,
    fps: float,
    start_frame: float,
    apply_rotation: bool,
    apply_translation: bool,
    translation_scale: float,
    use_name_fallback: bool,
    use_table_index_fallback: bool,
    clear_existing_action: bool,
    pose_space_mode: str = "MDL_REST_DELTA",
    apply_root_motion: bool = False,
) -> Tuple[int, int, List[str]]:
    if bpy is None or Quaternion is None:
        raise RuntimeError("Blender modules are not available")
    if armature_object is None or getattr(armature_object, "type", None) != "ARMATURE":
        raise RuntimeError("Select an armature, an imported MDL mesh part, or the imported MDL root before importing ANIM")

    bound_mdl_meshes, binding_lines = repairImportedMdlMeshBindingsForArmature(
        armature_object,
        bpy.context,
    )

    previous_active = bpy.context.view_layer.objects.active
    previous_mode = None
    try:
        previous_mode = previous_active.mode if previous_active is not None else None
    except Exception:
        previous_mode = None

    try:
        if previous_active is not None and previous_active.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass

    bpy.context.view_layer.objects.active = armature_object
    armature_object.select_set(True)
    try:
        bpy.ops.object.mode_set(mode="POSE")
    except Exception:
        pass

    reset_pose_bones = resetArmaturePoseToRest(armature_object)

    armature_object.animation_data_create()
    if clear_existing_action or armature_object.animation_data.action is None:
        action = bpy.data.actions.new(sanitizeActionName(entry.name, source_path))
        action["bleeds_source_anim_path"] = source_path
        action["bleeds_source_anim_name"] = entry.name
        action["bleeds_source_anim_index"] = int(entry.index)
        action["bleeds_source_anim_total_time"] = float(entry.total_time)
        action["bleeds_anim_pose_space_mode"] = str(pose_space_mode)
        armature_object.animation_data.action = action
    else:
        action = armature_object.animation_data.action

    lookup = buildPoseBoneLookup(armature_object)
    mapped_count = 0
    keyed_count = 0
    log_lines: List[str] = []
    log_lines.extend(binding_lines)
    log_lines.append(f"POSE RESET before ANIM apply: {reset_pose_bones} pose bones reset to rest matrix_basis")
    mapped_items: List[Tuple[BoneAnim, object, str]] = []

    for bone in entry.bones:
        pose_bone, reason = findPoseBoneForAnimBone(
            armature_object,
            bone,
            use_name_fallback=use_name_fallback,
            use_table_index_fallback=use_table_index_fallback,
            lookup=lookup,
        )
        if pose_bone is None:
            log_lines.append(
                f"UNMAPPED bone[{bone.table_index:02d}] flags=0x{bone.flags:04X} "
                f"key=0x{bone.bone_key:08X} target={formatAnimBoneTarget(bone)} frames={len(bone.frames)}"
            )
            continue

        mapped_count += 1
        pose_bone.rotation_mode = "QUATERNION"
        mapped_items.append((bone, pose_bone, reason))
        log_lines.append(
            f"MAPPED bone[{bone.table_index:02d}] {formatAnimBoneTarget(bone)} -> {pose_bone.name!r} via {reason}; frames={len(bone.frames)}"
        )

    mode = str(pose_space_mode).upper()
    native_leeds_mdl = isNativeLeedsMdlArmature(armature_object)
    if shouldAutoUseSafePedWeaponAnimMode(armature_object, entry, mode):
        mode = "ANIM_FIRST_KEY_DELTA"
        log_lines.append(
            "AUTO pose mode: non-native/cross-rig weapon PED animation uses ANIM_FIRST_KEY_DELTA. "
            "Native Leeds MDLs keep MDL_REST_DELTA and use their imported source rest matrices."
        )
    elif native_leeds_mdl and mode in {"DEFAULT", ""}:
        mode = "MDL_REST_DELTA"
        log_lines.append(
            "AUTO pose mode: native Leeds MDL uses MDL_REST_DELTA from imported source local/global rest matrices."
        )

    try:
        action["bleeds_anim_pose_space_mode"] = str(mode)
        action["bleeds_anim_native_leeds_mdl_target"] = bool(native_leeds_mdl)
    except Exception:
        pass
    if mode in ("MDL_ABSOLUTE_POSE", "ABSOLUTE_POSE", "ABSOLUTE_MDL_POSE"):
        keyed_count, solver_lines = applyAnimEntryAsAbsolutePose(
            armature_object,
            entry,
            mapped_items,
            fps=fps,
            start_frame=start_frame,
            apply_rotation=apply_rotation,
            apply_translation=apply_translation,
            translation_scale=translation_scale,
            apply_root_motion=apply_root_motion,
        )
        log_lines.extend(solver_lines)
    else:
        for bone, pose_bone, _reason in mapped_items:
            rest_source_for_log = None
            previous_quaternion = None
            for anim_frame in bone.frames:
                frame_number = float(start_frame) + float(anim_frame.absolute_time) * float(fps)

                if mode in ("ANIM_FIRST_KEY_DELTA", "FIRST_KEY_DELTA", "LEEDS_REFERENCE_DELTA"):
                    reference_frame = bone.frames[0] if bone.frames else anim_frame
                    keyed_here, rest_source = applyPoseFrameAnimReferenceDelta(
                        armature_object,
                        pose_bone,
                        anim_frame,
                        reference_frame,
                        bone,
                        apply_rotation=apply_rotation,
                        apply_translation=apply_translation,
                        translation_scale=translation_scale,
                        apply_root_motion=apply_root_motion,
                    )
                    rest_source_for_log = rest_source_for_log or rest_source
                    if keyed_here:
                        if apply_rotation and bone.has_rotation:
                            previous_quaternion = makePoseQuaternionContinuous(pose_bone, previous_quaternion)
                        pose_bone.keyframe_insert(data_path="location", frame=frame_number)
                        pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame_number)
                        pose_bone.keyframe_insert(data_path="scale", frame=frame_number)
                        keyed_count += 1
                elif mode == "RAW_BASIS":
                    keyed_here = applyPoseFrameRawBasis(
                        pose_bone,
                        anim_frame,
                        bone,
                        apply_rotation=apply_rotation,
                        apply_translation=apply_translation,
                        translation_scale=translation_scale,
                    )
                    if apply_rotation and bone.has_rotation:
                        previous_quaternion = makePoseQuaternionContinuous(pose_bone, previous_quaternion)
                        pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame_number)
                    if apply_translation and bone.has_translation:
                        pose_bone.keyframe_insert(data_path="location", frame=frame_number)
                    keyed_count += keyed_here
                elif mode in ("MDL_REST_DELTA", "DEFAULT", "", "MDL_REST_ROTATION_DELTA", "PED_REST_ROTATION_DELTA", "SAFE_DELTA"):
                    keyed_here, rest_source = applyPoseFrameRestDelta(
                        armature_object,
                        pose_bone,
                        anim_frame,
                        bone,
                        apply_rotation=apply_rotation,
                        apply_translation=apply_translation,
                        translation_scale=translation_scale,
                        apply_root_motion=apply_root_motion,
                    )
                    rest_source_for_log = rest_source_for_log or rest_source
                    if keyed_here:
                        if apply_rotation and bone.has_rotation:
                            previous_quaternion = makePoseQuaternionContinuous(pose_bone, previous_quaternion)
                        pose_bone.keyframe_insert(data_path="location", frame=frame_number)
                        pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame_number)
                        pose_bone.keyframe_insert(data_path="scale", frame=frame_number)
                        keyed_count += 1
                elif mode in ("PLR_REST_ROTATION_DELTA", "RAW_REST_ROTATION_DELTA", "DEBUG_PLR_REST_ROTATION_DELTA"):
                    keyed_here = applyPoseFramePlrRestRotationDelta(
                        armature_object,
                        pose_bone,
                        anim_frame,
                        bone,
                        apply_rotation=apply_rotation,
                        apply_translation=apply_translation,
                        translation_scale=translation_scale,
                        apply_root_motion=apply_root_motion,
                    )
                    if keyed_here:
                        if apply_translation and bone.has_translation:
                            pose_bone.keyframe_insert(data_path="location", frame=frame_number)
                        if apply_rotation and bone.has_rotation:
                            previous_quaternion = makePoseQuaternionContinuous(pose_bone, previous_quaternion)
                            pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame_number)
                        pose_bone.keyframe_insert(data_path="scale", frame=frame_number)
                        keyed_count += keyed_here
                    rest_source_for_log = rest_source_for_log or "debug PLR/raw rest rotation delta"
                else:
                    keyed_here, rest_source = applyPoseFrameRestDelta(
                        armature_object,
                        pose_bone,
                        anim_frame,
                        bone,
                        apply_rotation=apply_rotation,
                        apply_translation=apply_translation,
                        translation_scale=translation_scale,
                        apply_root_motion=apply_root_motion,
                    )
                    rest_source_for_log = rest_source_for_log or rest_source
                    if keyed_here:
                        if apply_rotation and bone.has_rotation:
                            previous_quaternion = makePoseQuaternionContinuous(pose_bone, previous_quaternion)
                        pose_bone.keyframe_insert(data_path="location", frame=frame_number)
                        pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame_number)
                        pose_bone.keyframe_insert(data_path="scale", frame=frame_number)
                        keyed_count += 1

            if rest_source_for_log:
                log_lines.append(f"    applied using {rest_source_for_log}")

    end_frame = float(start_frame) + max(0.0, float(entry.total_time)) * float(fps)
    scene = bpy.context.scene
    scene.frame_start = min(int(scene.frame_start), int(start_frame))
    scene.frame_end = max(int(scene.frame_end), int(math.ceil(end_frame)) + 1)

    linear_key_count = finalizeImportedAnimActionCurves(action, float(start_frame), float(end_frame))
    if linear_key_count:
        log_lines.append(f"Interpolation: set {linear_key_count} imported keyframe points to LINEAR.")

    if action is not None:
        action["bleeds_anim_mapped_bones"] = int(mapped_count)
        action["bleeds_anim_keyed_channels"] = int(keyed_count)
        action["bleeds_anim_unmapped_bones"] = int(len(entry.bones) - mapped_count)

    try:
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass

    moved_mesh, max_mesh_displacement, deformation_lines = measureImportedMdlAnimationMotion(
        armature_object,
        bound_mdl_meshes,
        start_frame=float(start_frame),
        end_frame=float(end_frame),
    )
    log_lines.extend(deformation_lines)

    if bound_mdl_meshes and not moved_mesh and mapped_count > 0 and keyed_count > 0:
        rebound_meshes, rebound_lines = repairImportedMdlMeshBindingsForArmature(
            armature_object,
            bpy.context,
        )
        log_lines.append("DEFORM CHECK: first evaluation did not move the MDL; reasserted modifier/parent binding and retested.")
        log_lines.extend(rebound_lines)
        moved_mesh, max_mesh_displacement, retry_lines = measureImportedMdlAnimationMotion(
            armature_object,
            rebound_meshes,
            start_frame=float(start_frame),
            end_frame=float(end_frame),
        )
        bound_mdl_meshes = rebound_meshes
        log_lines.extend(retry_lines)

    try:
        if action is not None:
            action["bleeds_anim_bound_mdl_mesh_count"] = int(len(bound_mdl_meshes))
            action["bleeds_anim_deforms_bound_mdl_mesh"] = bool(moved_mesh)
            action["bleeds_anim_max_mesh_displacement"] = float(max_mesh_displacement)
        armature_object["bleeds_anim_bound_mdl_mesh_count"] = int(len(bound_mdl_meshes))
        armature_object["bleeds_anim_deforms_bound_mdl_mesh"] = bool(moved_mesh)
        armature_object["bleeds_anim_max_mesh_displacement"] = float(max_mesh_displacement)
    except Exception:
        pass

    try:
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass

    if previous_active is not None:
        try:
            bpy.context.view_layer.objects.active = previous_active
            previous_active.select_set(True)
            if previous_mode and previous_mode != "OBJECT":
                bpy.ops.object.mode_set(mode=previous_mode)
        except Exception:
            pass

    return mapped_count, keyed_count, log_lines

def buildImportSummary(
    anim_file: AnimFile,
    entry: AnimEntry,
    source_path: str,
    *,
    armature_object=None,
    mapped_count: int = 0,
    keyed_count: int = 0,
    mapping_lines: Optional[List[str]] = None,
) -> str:
    lines: List[str] = []
    lines.append(f"Source: {source_path}")
    if armature_object is not None:
        lines.append(f"Armature: {getattr(armature_object, 'name', '<unknown>')}")
    lines.append(anim_file.summaryText(include_bones=True))
    lines.append("")
    lines.append(f"Selected animation: [{entry.index:02d}] {entry.name}")
    lines.append(f"Mapped bones: {mapped_count}/{len(entry.bones)}")
    lines.append(f"Keyed channels: {keyed_count}")
    if armature_object is not None:
        lines.append("")
        lines.append("Hash -> bone_id pipeline diagnostic:")
        lines.extend(buildMappingDiagnosticLines(armature_object, entry))
    if mapping_lines:
        lines.append("")
        lines.append("Mapping:")
        lines.extend(mapping_lines)
    if anim_file.log_text:
        lines.append("")
        lines.append("Parser log:")
        lines.append(anim_file.log_text)
    return "\n".join(lines)

