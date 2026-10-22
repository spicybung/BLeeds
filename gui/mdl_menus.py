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
from typing import Optional, Tuple

import bpy
from .. import get_mesh_attribute
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatVectorProperty,
    PointerProperty,
    StringProperty,
)
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree


def isArmatureObject(self, object):
    return object is not None and object.type == 'ARMATURE'


def armatureBoneMatchKey(bone):
    for property_name in ("bleeds_hanim_bone_id", "bleeds_mdl_anim_bone_id", "BoneID"):
        try:
            if property_name in bone:
                return ("ID", int(bone[property_name]))
        except (TypeError, ValueError):
            continue
    return ("NAME", "".join(character for character in bone.name.lower() if character.isalnum()))


def armatureBoneDepth(bone):
    depth = 0
    parent = bone.parent
    while parent is not None:
        depth += 1
        parent = parent.parent
    return depth


def writeArmatureSnapLog(lines):
    log_name = "BLeeds Armature Snap Log"
    log = bpy.data.texts.get(log_name)
    if log is None:
        log = bpy.data.texts.new(log_name)
    log.clear()
    log.write("\n".join(lines) + "\n")
    for line in lines:
        print("[BLeeds Snap] " + line)


def normalizeSnapVertexGroups(mesh_obj, bone_names, log_lines):
    aliases = {
        "l_callf": "l_calf",
        "r_callf": "r_calf",
    }
    for old_name, new_name in aliases.items():
        group = mesh_obj.vertex_groups.get(old_name)
        if group is None or new_name not in bone_names:
            continue
        destination = mesh_obj.vertex_groups.get(new_name)
        if destination is None:
            group.name = new_name
            log_lines.append("GROUP RENAMED: %s %s -> %s" % (mesh_obj.name, old_name, new_name))
            continue
        weights = []
        for vertex in mesh_obj.data.vertices:
            source_weight = next((entry.weight for entry in vertex.groups if entry.group == group.index), 0.0)
            destination_weight = next((entry.weight for entry in vertex.groups if entry.group == destination.index), 0.0)
            if source_weight > 0.0:
                weights.append((vertex.index, min(1.0, source_weight + destination_weight)))
        for vertex_index, weight in weights:
            destination.add([vertex_index], weight, 'REPLACE')
        mesh_obj.vertex_groups.remove(group)
        log_lines.append("GROUP MERGED: %s %s -> %s (%d vertices)" % (
            mesh_obj.name, old_name, new_name, len(weights)
        ))


def snapBarycentricWeights(point, first, second, third):
    edge_a = second - first
    edge_b = third - first
    relative = point - first
    aa = edge_a.dot(edge_a)
    ab = edge_a.dot(edge_b)
    bb = edge_b.dot(edge_b)
    ra = relative.dot(edge_a)
    rb = relative.dot(edge_b)
    determinant = aa * bb - ab * ab
    if abs(determinant) < 0.000000000001:
        return (1.0, 0.0, 0.0)
    second_weight = (bb * ra - ab * rb) / determinant
    third_weight = (aa * rb - ab * ra) / determinant
    first_weight = 1.0 - second_weight - third_weight
    weights = [max(0.0, first_weight), max(0.0, second_weight), max(0.0, third_weight)]
    total = sum(weights)
    return tuple(weight / total for weight in weights)


def redistributeSnapReferenceWeights(target, reference, mesh_objects, log_lines):
    reference_objects = [
        obj for obj in bpy.data.objects
        if obj.type == 'MESH' and any(
            modifier.type == 'ARMATURE' and modifier.object == reference
            for modifier in obj.modifiers
        )
    ]
    if not reference_objects:
        raise ValueError("Reference armature has no skinned meshes")

    target_bones = {bone.name.lower(): bone.name for bone in target.data.bones}
    target_ids = {}
    repeated_ids = set()
    for bone in target.data.bones:
        key = armatureBoneMatchKey(bone)
        if key[0] == 'ID':
            if key[1] in target_ids:
                repeated_ids.add(key[1])
            target_ids[key[1]] = bone.name
    for bone_id in repeated_ids:
        target_ids.pop(bone_id, None)

    source_to_target = {}
    for bone in reference.data.bones:
        matching = target_bones.get(bone.name.lower())
        key = armatureBoneMatchKey(bone)
        if matching is None and key[0] == 'ID':
            matching = target_ids.get(key[1])
        if matching is not None:
            source_to_target[bone.name] = matching
    source_to_target.update({"l_callf": "l_calf", "r_callf": "r_calf"})

    positions = []
    triangles = []
    weights_by_vertex = []
    for reference_mesh in reference_objects:
        mesh = reference_mesh.data
        transform = reference.matrix_world.inverted_safe() @ reference_mesh.matrix_world
        group_names = {group.index: group.name for group in reference_mesh.vertex_groups}
        offset = len(positions)
        for vertex in mesh.vertices:
            positions.append(transform @ vertex.co)
            weights = {}
            for group in vertex.groups:
                name = source_to_target.get(group_names.get(group.group))
                if name is not None and group.weight > 0.0:
                    weights[name] = weights.get(name, 0.0) + group.weight
            weights_by_vertex.append(weights)
        mesh.calc_loop_triangles()
        for triangle in mesh.loop_triangles:
            indices = tuple(offset + index for index in triangle.vertices)
            if (positions[indices[1]] - positions[indices[0]]).cross(
                positions[indices[2]] - positions[indices[0]]
            ).length_squared > 0.000000000001:
                triangles.append(indices)

    if not triangles:
        raise ValueError("Reference meshes contain no usable triangles")
    tree = BVHTree.FromPolygons(positions, triangles, all_triangles=True)
    replacements = []
    for mesh_obj in mesh_objects:
        transform = target.matrix_world.inverted_safe() @ mesh_obj.matrix_world
        mesh_weights = {}
        for vertex in mesh_obj.data.vertices:
            hit, normal, triangle_index, distance = tree.find_nearest(transform @ vertex.co)
            if triangle_index is None:
                continue
            indices = triangles[triangle_index]
            factors = snapBarycentricWeights(
                hit, positions[indices[0]], positions[indices[1]], positions[indices[2]]
            )
            result = {}
            for index, factor in zip(indices, factors):
                for name, weight in weights_by_vertex[index].items():
                    result[name] = result.get(name, 0.0) + weight * factor
            total = sum(result.values())
            if total > 0.000001:
                mesh_weights[vertex.index] = {name: weight / total for name, weight in result.items() if weight > 0.000001}
        replacements.append((mesh_obj, mesh_weights))

    count = 0
    for mesh_obj, mesh_weights in replacements:
        if not mesh_weights:
            continue
        indices = list(mesh_weights)
        for group in list(mesh_obj.vertex_groups):
            if group.name in target_bones.values() or group.name in ("l_callf", "r_callf"):
                group.remove(indices)
        for vertex_index, weights in mesh_weights.items():
            for name, weight in weights.items():
                group = mesh_obj.vertex_groups.get(name)
                if group is None:
                    group = mesh_obj.vertex_groups.new(name=name)
                group.add([vertex_index], weight, 'REPLACE')
            count += 1
        log_lines.append("REFERENCE WEIGHTS: %s %d vertices" % (mesh_obj.name, len(mesh_weights)))
    log_lines.append("Reference weights transferred: %d vertices from %d meshes" % (
        count, len(reference_objects)
    ))
    return count


class OBJECT_OT_BLeeds_SnapArmature(bpy.types.Operator):
    bl_idname = "bleeds.snap_armature_to_reference"
    bl_label = "Snap Armature"
    bl_description = "Match the bones to another armature"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        target = context.object
        source = getattr(context.scene, "bleeds_reference_armature", None)
        return target is not None and target.type == 'ARMATURE' and source is not None and source != target

    def execute(self, context):
        target = context.object
        source = context.scene.bleeds_reference_armature
        if target == source:
            self.report({'ERROR'}, "Select a different armature")
            return {'CANCELLED'}

        use_pose = bool(context.scene.bleeds_reference_use_pose)
        use_reference_weights = bool(context.scene.bleeds_reference_weights)
        log_lines = [
            "Target: %s" % target.name,
            "Reference: %s" % source.name,
            "Use Current Pose: %s" % use_pose,
            "Use Reference Weights: %s" % use_reference_weights,
            "Frame: %d" % context.scene.frame_current,
            "Target pose display: %s" % target.data.pose_position,
            "Target animation: %s" % (target.animation_data.action.name if target.animation_data and target.animation_data.action else "none"),
        ]
        source_by_name = {}
        source_by_id = {}
        duplicate_ids = set()
        for source_bone in source.data.bones:
            normalized = "".join(character for character in source_bone.name.lower() if character.isalnum())
            source_by_name[normalized] = source_bone
            key = armatureBoneMatchKey(source_bone)
            if key[0] == "ID":
                if key[1] in source_by_id:
                    duplicate_ids.add(key[1])
                source_by_id[key[1]] = source_bone
        for duplicate_id in duplicate_ids:
            source_by_id.pop(duplicate_id, None)

        source_to_target = Matrix.Identity(4)
        transforms = {}
        for target_bone in target.data.bones:
            normalized = "".join(character for character in target_bone.name.lower() if character.isalnum())
            matched = source_by_name.get(normalized)
            key = armatureBoneMatchKey(target_bone)
            if matched is None and key[0] == "ID":
                matched = source_by_id.get(key[1])
            if matched is None:
                log_lines.append("UNMATCHED: %s (%s)" % (target_bone.name, str(key)))
                continue
            log_lines.append("MATCH: %s -> %s (%s)" % (target_bone.name, matched.name, str(key)))
            pose_bone = source.pose.bones.get(matched.name) if use_pose else None
            if pose_bone is not None:
                matrix = pose_bone.matrix.copy()
                head = pose_bone.head.copy()
                tail = pose_bone.tail.copy()
            else:
                matrix = matched.matrix_local.copy()
                head = matched.head_local.copy()
                tail = matched.tail_local.copy()
            rotation_angle = math.degrees(
                target_bone.matrix_local.to_quaternion().rotation_difference(
                    matrix.to_quaternion()).angle
            )
            rotation_angle = min(rotation_angle, 360.0 - rotation_angle)
            reference_bone_neutral = pose_bone is None or all(
                abs(pose_bone.matrix_basis[row][col] - float(row == col)) < 0.0001
                for row in range(4) for col in range(4)
            )
            if (head - target_bone.head_local).length < 0.005 and rotation_angle > 120.0 and reference_bone_neutral:
                log_lines.append("PRESERVED BONE AXIS: %s (reference differs by %.2f degrees)" % (
                    target_bone.name, rotation_angle
                ))
                matrix = target_bone.matrix_local.copy()
                head = target_bone.head_local.copy()
                tail = target_bone.tail_local.copy()
            if (head - target_bone.head_local).length < 0.00001 and (
                tail - target_bone.tail_local
            ).length < 0.00001:
                matrix = target_bone.matrix_local.copy()
            transforms[target_bone.name] = (
                source_to_target @ matrix,
                source_to_target @ head,
                source_to_target @ tail,
            )

        if not transforms:
            writeArmatureSnapLog(log_lines)
            self.report({'ERROR'}, "No matching bones found")
            return {'CANCELLED'}

        matched_bone_count = len(transforms)
        source_pose_count = sum(
            1 for bone in source.pose.bones
            if any(abs(bone.matrix_basis[row][col] - float(row == col)) > 0.0001
                   for row in range(4) for col in range(4))
        )
        target_pose_count = sum(
            1 for bone in target.pose.bones
            if any(abs(bone.matrix_basis[row][col] - float(row == col)) > 0.0001
                   for row in range(4) for col in range(4))
        )
        log_lines.append("Non-neutral pose bones: reference=%d target=%d" % (source_pose_count, target_pose_count))
        old_rest = {bone.name: bone.matrix_local.copy() for bone in target.data.bones}
        pending_bones = {bone.name for bone in target.data.bones if bone.name not in transforms}
        while pending_bones:
            resolved_bones = set()
            for bone_name in pending_bones:
                bone = target.data.bones[bone_name]
                if bone.parent is None or bone.parent.name not in transforms:
                    continue
                parent_matrix = transforms[bone.parent.name][0]
                parent_change = parent_matrix @ old_rest[bone.parent.name].inverted_safe()
                transforms[bone_name] = (
                    parent_change @ bone.matrix_local,
                    parent_change @ bone.head_local,
                    parent_change @ bone.tail_local,
                )
                resolved_bones.add(bone_name)
            if not resolved_bones:
                break
            pending_bones.difference_update(resolved_bones)
        log_lines.append("Matched bones: %d; inherited bones: %d; unchanged bones: %d" % (
            matched_bone_count, len(transforms) - matched_bone_count, len(pending_bones)
        ))
        bones_by_depth = sorted(
            target.data.bones,
            key=armatureBoneDepth
        )
        for bone in bones_by_depth:
            if bone.parent is None or bone.name not in transforms or bone.parent.name not in transforms:
                continue
            parent = bone.parent
            original_offset = bone.head_local - parent.tail_local
            connection_tolerance = max(0.005, parent.length * 0.12)
            if original_offset.length > connection_tolerance:
                continue
            parent_matrix, _, parent_tail = transforms[parent.name]
            child_matrix, child_head, child_tail = transforms[bone.name]
            parent_rotation_change = (
                parent_matrix.to_3x3() @ old_rest[parent.name].to_3x3().inverted_safe()
            )
            expected_head = parent_tail + parent_rotation_change @ original_offset
            correction = expected_head - child_head
            if correction.length <= 0.0001:
                continue
            transforms[bone.name] = (
                Matrix.Translation(correction) @ child_matrix,
                child_head + correction,
                child_tail + correction,
            )
            log_lines.append("JOINT ALIGNED: %s -> %s shift=%.4f" % (
                parent.name, bone.name, correction.length
            ))
        for bone in reversed(bones_by_depth):
            parent = bone.parent
            if parent is None or bone.name not in transforms or parent.name not in transforms:
                continue
            if not any(part in parent.name.lower() for part in (
                "clavicle", "upperarm", "forearm"
            )):
                continue
            parent_matrix, parent_head, parent_tail = transforms[parent.name]
            child_head = transforms[bone.name][1]
            original_gap = bone.head_local - parent.tail_local
            desired_tail = child_head - original_gap
            if (desired_tail - parent_tail).length <= 0.0001:
                continue
            if (desired_tail - parent_head).length <= 0.0001:
                continue
            log_lines.append("ARM JOINT: %s -> %s tail shift=%.4f" % (
                parent.name, bone.name, (desired_tail - parent_tail).length
            ))
            transforms[parent.name] = (parent_matrix, parent_head, desired_tail)
        attached_meshes = []
        for obj in context.scene.objects:
            if obj.type != 'MESH' or obj.parent_type == 'BONE':
                continue
            bound_to_target = any(
                modifier.type == 'ARMATURE' and modifier.object == target
                for modifier in obj.modifiers
            )
            if not bound_to_target:
                continue
            if obj.data.shape_keys is not None:
                self.report({'ERROR'}, "Apply shape keys on %s before snapping" % obj.name)
                return {'CANCELLED'}
            if obj.data.users > 1:
                obj.data = obj.data.copy()
            attached_meshes.append(obj)

        if use_reference_weights:
            try:
                redistributeSnapReferenceWeights(target, source, attached_meshes, log_lines)
            except (ValueError, RuntimeError) as error:
                log_lines.append("REFERENCE WEIGHTS FAILED: %s" % error)
                writeArmatureSnapLog(log_lines)
                self.report({'ERROR'}, str(error))
                return {'CANCELLED'}

        previous_mode = target.mode
        try:
            if previous_mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.mode_set(mode='EDIT')
            for bone_name, (matrix, head, tail) in transforms.items():
                edit_bone = target.data.edit_bones.get(bone_name)
                if edit_bone is None:
                    continue
                edit_bone.use_connect = False
                edit_bone.head = head
                edit_bone.tail = tail if (tail - head).length > 0.00001 else head + Vector((0, 0.1, 0))
                roll_axis = matrix.to_3x3() @ Vector((0.0, 0.0, 1.0))
                if roll_axis.length > 0.00001:
                    edit_bone.align_roll(roll_axis)
        finally:
            if target.mode == 'EDIT':
                bpy.ops.object.mode_set(mode='OBJECT')
            if previous_mode in {'POSE', 'EDIT'}:
                bpy.ops.object.mode_set(mode=previous_mode)

        new_rest = {bone.name: bone.matrix_local.copy() for bone in target.data.bones}
        rest_changes = {}
        for name, old_matrix in old_rest.items():
            new_matrix = new_rest.get(name)
            if new_matrix is not None:
                rest_changes[name] = new_matrix @ old_matrix.inverted_safe()
                if any(part in name.lower() for part in ('spine', 'arm', 'clavicle', 'shoulder', 'pelvis')):
                    old_head = old_matrix.translation
                    new_head = new_matrix.translation
                    angle = math.degrees(old_matrix.to_quaternion().rotation_difference(
                        new_matrix.to_quaternion()).angle)
                    angle = min(angle, 360.0 - angle)
                    log_lines.append("BONE: %s old=(%.4f, %.4f, %.4f) new=(%.4f, %.4f, %.4f) shift=%.4f rotation=%.2f degrees" % (
                        name, old_head.x, old_head.y, old_head.z,
                        new_head.x, new_head.y, new_head.z, (new_head - old_head).length, angle
                    ))

        adjusted_vertices = 0
        vertex_records = []
        shared_positions = {}
        seam_tolerance = 0.0001
        boundary_records = []
        unmatched_groups = {}
        for mesh_obj in attached_meshes:
            normalizeSnapVertexGroups(mesh_obj, old_rest, log_lines)
            mesh_to_armature = target.matrix_world.inverted_safe() @ mesh_obj.matrix_world
            armature_to_mesh = mesh_to_armature.inverted_safe()
            group_names = {group.index: group.name for group in mesh_obj.vertex_groups}
            mesh = mesh_obj.data
            edge_counts = {}
            for polygon in mesh.polygons:
                for edge in polygon.edge_keys:
                    key = tuple(sorted(edge))
                    edge_counts[key] = edge_counts.get(key, 0) + 1
            boundary_vertices = set()
            for edge, count in edge_counts.items():
                if count == 1:
                    boundary_vertices.update(edge)
            log_lines.append("MESH: %s vertices=%d boundary=%d modifiers=%d" % (
                mesh_obj.name, len(mesh.vertices), len(boundary_vertices), len(mesh_obj.modifiers)
            ))
            for vertex in mesh.vertices:
                position = mesh_to_armature @ vertex.co
                weighted_position = Vector((0.0, 0.0, 0.0))
                total_weight = 0.0
                for group in vertex.groups:
                    bone_name = group_names.get(group.group)
                    rest_change = rest_changes.get(bone_name)
                    if bone_name not in old_rest or group.weight <= 0.0:
                        if group.weight > 0.0 and bone_name not in old_rest:
                            group_key = "%s/%s" % (mesh_obj.name, bone_name)
                            unmatched_groups[group_key] = unmatched_groups.get(group_key, 0) + 1
                        continue
                    if rest_change is not None:
                        weighted_position += (rest_change @ position) * group.weight
                    else:
                        weighted_position += position * group.weight
                    total_weight += group.weight
                if total_weight <= 0.0:
                    continue
                destination = weighted_position / total_weight
                record_index = len(vertex_records)
                vertex_records.append((mesh_obj, vertex.index, position, destination, armature_to_mesh))
                key = tuple(round(float(axis) / seam_tolerance) for axis in position)
                shared_positions.setdefault(key, []).append(record_index)
                if vertex.index in boundary_vertices:
                    boundary_records.append(record_index)

        displacements = [destination - position for _, _, position, destination, _ in vertex_records]
        for record_indices in shared_positions.values():
            if len(record_indices) < 2:
                continue
            reference_position = vertex_records[record_indices[0]][2]
            coincident = [
                index for index in record_indices
                if (vertex_records[index][2] - reference_position).length <= seam_tolerance
            ]
            if len(coincident) < 2:
                continue
            common_displacement = sum(
                (displacements[index] for index in coincident), Vector((0.0, 0.0, 0.0))
            ) / len(coincident)
            for index in coincident:
                displacements[index] = common_displacement.copy()

        stitched_pairs = 0
        if boundary_records:
            rest_heads = [bone.head_local for bone in target.data.bones]
            skeleton_height = max((head.z for head in rest_heads), default=1.0) - min(
                (head.z for head in rest_heads), default=0.0
            )
            seam_radius = max(0.0005, abs(skeleton_height) * 0.0075)
            spatial_index = KDTree(len(boundary_records))
            for index, record_index in enumerate(boundary_records):
                spatial_index.insert(vertex_records[record_index][2], index)
            spatial_index.balance()
            original_displacements = [delta.copy() for delta in displacements]
            seam_adjustments = {}
            for index, record_index in enumerate(boundary_records):
                mesh_obj, _, position, _, _ = vertex_records[record_index]
                neighbors = [
                    (distance, boundary_records[other_index])
                    for _, other_index, distance in spatial_index.find_range(position, seam_radius)
                    if boundary_records[other_index] != record_index
                    and vertex_records[boundary_records[other_index]][0] != mesh_obj
                ]
                if not neighbors:
                    continue
                distance, other_record = min(neighbors, key=lambda entry: entry[0])
                factor = max(0.0, 1.0 - distance / seam_radius)
                if factor <= 0.0:
                    continue
                proposed = original_displacements[record_index].lerp(
                    original_displacements[other_record], factor * 0.5
                )
                seam_adjustments[record_index] = proposed
                stitched_pairs += 1
            for record_index, displacement in seam_adjustments.items():
                displacements[record_index] = displacement
            log_lines.append("Boundary pairs adjusted: %d (radius %.6f)" % (stitched_pairs, seam_radius))

        log_lines.append("Unmatched vertex groups: %s" % (
            ", ".join("%s=%d" % (name, count) for name, count in sorted(unmatched_groups.items()))
            if unmatched_groups else "none"
        ))

        for index, (mesh_obj, vertex_index, position, _, armature_to_mesh) in enumerate(vertex_records):
            mesh_obj.data.vertices[vertex_index].co = armature_to_mesh @ (position + displacements[index])
            adjusted_vertices += 1
        for mesh_obj in attached_meshes:
            mesh_obj.data.update()
        log_lines.append("Vertices adjusted: %d" % adjusted_vertices)
        writeArmatureSnapLog(log_lines)

        target["bleeds_mdl_force_live_rest_pose"] = True
        target["bleeds_mdl_use_live_armature_rest"] = True
        self.report({'INFO'}, "Matched %d bones and moved %d vertices" % (matched_bone_count, adjusted_vertices))
        return {'FINISHED'}


class OBJECT_PT_BLeeds_SnapArmature(bpy.types.Panel):
    bl_label = "BLeeds - Armature"
    bl_idname = "OBJECT_PT_BLeeds_SnapArmature"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'object'

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'ARMATURE'

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene, "bleeds_reference_armature", text="Reference")
        layout.prop(context.scene, "bleeds_reference_use_pose", text="Use Current Pose")
        layout.prop(context.scene, "bleeds_reference_weights", text="Use Reference Weights")
        layout.operator(OBJECT_OT_BLeeds_SnapArmature.bl_idname, icon='ARMATURE_DATA')

def find_mdl_root(obj: Optional[bpy.types.Object]) -> Optional[bpy.types.Object]:
    if obj is None:
        return None

    cur = obj
    while cur is not None:

        if getattr(cur, "bleeds_is_mdl_root", False):
            return cur

        try:
            if bool(cur.get("bleeds_is_mdl_root", False)):
                return cur
        except Exception:
            pass

        cur = cur.parent

    return None


def get_mdl_root_game(root: Optional[bpy.types.Object]) -> str:
    if root is None:
        return ""
    try:
        if str(root.get("bleeds_mh2_asset_variant", "") or "").strip():
            return "MH2"
        if str(root.get("bleeds_mh2_platform", "") or "").strip():
            return "MH2"
    except Exception:
        pass
    try:
        value = str(root.get("bleeds_model_game", "") or "").upper().strip()
        if value:
            return value
    except Exception:
        pass
    try:
        value = getattr(root, "bleeds_model_game", "")
        if value:
            return str(value).upper().strip()
    except Exception:
        pass
    return ""


def gather_mdl_mesh_children(root: Optional[bpy.types.Object]):
    if root is None:
        return []
    meshes = []
    stack = list(getattr(root, "children", []) or [])
    visited = set()
    while stack:
        obj = stack.pop(0)
        if obj is None:
            continue
        pointer = id(obj)
        if pointer in visited:
            continue
        visited.add(pointer)
        if getattr(obj, "type", None) == "MESH":
            meshes.append(obj)
        stack.extend(list(getattr(obj, "children", []) or []))
    return meshes

def read_root_base_scale_pos(root: bpy.types.Object) -> Tuple[Vector, Vector]:

    if hasattr(root, "bleeds_leeds_scale_base") and hasattr(root, "bleeds_leeds_pos_base"):
        return Vector(root.bleeds_leeds_scale_base), Vector(root.bleeds_leeds_pos_base)

    scale = root.get("bleeds_leeds_scale_base", [1.0, 1.0, 1.0])
    pos = root.get("bleeds_leeds_pos_base", [0.0, 0.0, 0.0])
    return Vector(scale), Vector(pos)

def compute_effective_scale_pos(root: bpy.types.Object) -> Tuple[Vector, Vector]:
    base_scale, base_pos = read_root_base_scale_pos(root)

    root_scale = Vector((root.scale.x, root.scale.y, root.scale.z))
    root_loc = Vector((root.location.x, root.location.y, root.location.z))

    effective_scale = Vector((
        base_scale.x * root_scale.x,
        base_scale.y * root_scale.y,
        base_scale.z * root_scale.z,
    ))
    effective_pos = Vector((
        base_pos.x * root_scale.x + root_loc.x,
        base_pos.y * root_scale.y + root_loc.y,
        base_pos.z * root_scale.z + root_loc.z,
    ))
    return effective_scale, effective_pos

def value_as_power_of_two_fraction_hint(value: float, eps: float = 1e-6) -> str:
    if value == 0.0:
        return "0"
    sign = "-" if value < 0.0 else ""
    v = abs(float(value))

    for p in range(0, 21):
        candidate = 1.0 / (2.0 ** p) if p > 0 else 1.0
        if abs(v - candidate) <= eps:
            if p == 0:
                return f"{sign}1"
            return f"{sign}1/{2**p}"

    for p in range(1, 21):
        candidate = float(2 ** p)
        if abs(v - candidate) <= eps:
            return f"{sign}{2**p}"

    return ""

class EXPORT_OT_MDL_Bake_LeedsScalePos(bpy.types.Operator):
    bl_idname = "bleeds.mdl_bake_leeds_scale_pos"
    bl_label = "Bake Root into Leeds Scale/Pos"
    bl_description = "Bake the root transform into the stored Leeds scale and position"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        root = find_mdl_root(context.object)
        return root is not None

    def execute(self, context: bpy.types.Context) -> set:
        root = find_mdl_root(context.object)
        if root is None:
            self.report({"ERROR"}, "No BLeeds MDL root found.")
            return {"CANCELLED"}

        cached_world = {}
        for obj in root.children_recursive:
            cached_world[obj.name] = obj.matrix_world.copy()

        eff_scale, eff_pos = compute_effective_scale_pos(root)

        if hasattr(root, "bleeds_leeds_scale_base"):
            root.bleeds_leeds_scale_base = (eff_scale.x, eff_scale.y, eff_scale.z)
        else:
            root["bleeds_leeds_scale_base"] = [eff_scale.x, eff_scale.y, eff_scale.z]

        if hasattr(root, "bleeds_leeds_pos_base"):
            root.bleeds_leeds_pos_base = (eff_pos.x, eff_pos.y, eff_pos.z)
        else:
            root["bleeds_leeds_pos_base"] = [eff_pos.x, eff_pos.y, eff_pos.z]

        root.location = (0.0, 0.0, 0.0)
        root.rotation_euler = (0.0, 0.0, 0.0)
        root.scale = (1.0, 1.0, 1.0)

        for obj in root.children_recursive:
            mw = cached_world.get(obj.name, None)
            if mw is not None:
                obj.matrix_world = mw

        return {"FINISHED"}

class EXPORT_PT_MDL_LeedsScalePos(bpy.types.Panel):
    bl_idname = "EXPORT_PT_MDL_LeedsScalePos"
    bl_label = "BLeeds - Export Object"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        root = find_mdl_root(context.object)
        return root is not None and get_mdl_root_game(root) != "MH2"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        root = find_mdl_root(context.object)
        if root is None:
            layout.label(text="No BLeeds MDL root found.")
            return

        box = layout.box()
        col = box.column(align=True)
        col.label(text=f"Root: {root.name}")

        hash_key = None
        try:
            if hasattr(root, "bleeds_mdl_atomic_hash_key"):
                hash_key = int(root.bleeds_mdl_atomic_hash_key)
            elif "bleeds_mdl_atomic_hash_key" in root:
                hash_key = int(root["bleeds_mdl_atomic_hash_key"])
        except Exception:
            pass
        if hash_key is not None:
            col.label(text=f"Hash Key: 0x{hash_key:08X}")

        meta = col.column(align=True)
        if hasattr(root, "bleeds_mdl_platform"):
            meta.prop(root, "bleeds_mdl_platform", text="Platform")
        else:
            meta.label(text=f"Platform: {root.get('bleeds_mdl_platform', 'Unknown')}")

        if hasattr(root, "bleeds_mdl_type"):
            meta.prop(root, "bleeds_mdl_type", text="MDL Type")
        else:
            meta.label(text=f"MDL Type: {root.get('bleeds_mdl_type', 'Unknown')}")

        if hasattr(root, "bleeds_mdl_filepath"):
            meta.prop(root, "bleeds_mdl_filepath", text="Source")
        else:
            src = root.get("bleeds_mdl_filepath", "")
            if src:
                meta.label(text=f"Source: {src}")

        if hasattr(root, "bleeds_export_use_normals"):
            meta.prop(root, "bleeds_export_use_normals", text="Export Normals")
        if hasattr(root, "bleeds_export_gouraud_shading"):
            meta.prop(root, "bleeds_export_gouraud_shading", text="Gouraud Shading")

        layout.separator()
        base_box = layout.box()
        base_box.label(text="MDL Base (In-Game)")

        if hasattr(root, "bleeds_leeds_scale_base"):
            base_box.prop(root, "bleeds_leeds_scale_base", text="Scale")
        else:
            base_box.prop(root, '["bleeds_leeds_scale_base"]', text="Scale")

        if hasattr(root, "bleeds_leeds_pos_base"):
            base_box.prop(root, "bleeds_leeds_pos_base", text="Pos")
        else:
            base_box.prop(root, '["bleeds_leeds_pos_base"]', text="Pos")

        base_scale, base_pos = read_root_base_scale_pos(root)
        hint_row = base_box.row(align=True)
        hint_row.label(text="Scale hint:")
        hint_row.label(
            text=(
                f"X {value_as_power_of_two_fraction_hint(base_scale.x)}  "
                f"Y {value_as_power_of_two_fraction_hint(base_scale.y)}  "
                f"Z {value_as_power_of_two_fraction_hint(base_scale.z)}"
            )
        )

        if abs(root.rotation_euler.x) > 1e-6 or abs(root.rotation_euler.y) > 1e-6 or abs(root.rotation_euler.z) > 1e-6:
            warn = eff_box.column(align=True)
            warn.alert = True
            warn.label(text="Warning: Root rotation is non-zero.")
            warn.label(text="MDL scale/pos is axis-aligned; rotation is not represented in the file.")

        layout.separator()
        layout.operator(EXPORT_OT_MDL_Bake_LeedsScalePos.bl_idname, icon="FILE_TICK")

        try:

            from ..ops.mdl_exporter import gather_mesh_parts
        except Exception:
            gather_mesh_parts = None
        if gather_mesh_parts is not None and root is not None:
            try:
                meshes = gather_mesh_parts(context, root)
            except Exception:
                meshes = []
            counts = []
            depsgraph = context.evaluated_depsgraph_get()
            for obj in meshes:

                try:
                    obj_eval = obj.evaluated_get(depsgraph)
                    mesh_eval = obj_eval.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
                    counts.append(len(mesh_eval.vertices))
                except Exception:
                    counts.append(0)
                finally:
                    try:
                        obj_eval.to_mesh_clear()
                    except Exception:
                        pass

            try:
                if hasattr(root, "bleeds_mdl_part_batch_verts"):
                    root.bleeds_mdl_part_batch_verts = [int(x) for x in counts]
                else:
                    root["bleeds_mdl_part_batch_verts"] = [int(x) for x in counts]
            except Exception:
                pass
            if counts:
                geom_box = layout.box()
                geom_box.label(text="Geometry Stats")
                for i, cnt in enumerate(counts):
                    geom_box.label(text=f"Part {i}: {cnt} verts")

class EXPORT_OT_MDL_StampSemanticAttributes(bpy.types.Operator):
    bl_idname = "bleeds.mdl_stamp_semantic_attributes"
    bl_label = "Stamp/Refresh MDL Attributes"
    bl_description = "Create or refresh the MDL export attributes on model meshes"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return find_mdl_root(context.object) is not None

    def execute(self, context: bpy.types.Context) -> set:
        root = find_mdl_root(context.object)
        if root is None:
            self.report({"ERROR"}, "No BLeeds MDL root found.")
            return {"CANCELLED"}

        try:
            from ..ops.mdl_exporter import gather_mesh_parts, writeMdlSemanticDefaultsForExport, normalizeMdlCustomPedVertexGroupsForExport, writeMdlCanonicalPedIdentityMapProps
        except Exception as exc:
            self.report({"ERROR"}, f"Could not load MDL semantic attribute writer: {exc}")
            return {"CANCELLED"}

        try:
            meshes = gather_mesh_parts(context, root)
        except Exception as exc:
            self.report({"ERROR"}, f"Could not gather MDL mesh parts: {exc}")
            return {"CANCELLED"}

        rebuilt_groups = 0
        try:
            writeMdlCanonicalPedIdentityMapProps(root, None, root)
        except Exception:
            pass
        for part_index, obj in enumerate(meshes):
            writeMdlSemanticDefaultsForExport(obj, part_index)
            rebuilt_groups += int(normalizeMdlCustomPedVertexGroupsForExport(obj, root) or 0)

        if rebuilt_groups:
            self.report({"INFO"}, f"Stamped BLeeds MDL attributes on {len(meshes)} mesh part(s); rebuilt custom PED vertex groups on {rebuilt_groups} vertices.")
        else:
            self.report({"INFO"}, f"Stamped BLeeds MDL attributes on {len(meshes)} mesh part(s).")
        return {"FINISHED"}

def readMdlIdProp(owner, key: str, default=None):
    try:
        if owner is not None and key in owner:
            return owner[key]
    except Exception:
        pass
    return default

def getMdlAttributeExpectedCount(mesh: bpy.types.Mesh, domain: str) -> int:
    domain_key = str(domain or "").upper().strip()
    if domain_key == "POINT":
        return len(mesh.vertices)
    if domain_key == "FACE":
        return len(mesh.polygons)
    if domain_key == "CORNER":
        return len(mesh.loops)
    if domain_key == "EDGE":
        return len(mesh.edges)
    return 0

class EXPORT_PT_MDL_SemanticAttributes(bpy.types.Panel):
    bl_idname = "EXPORT_PT_MDL_SemanticAttributes"
    bl_label = "BLeeds - Properties/Attributes"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        root = find_mdl_root(context.object)
        return root is not None and get_mdl_root_game(root) != "MH2"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.use_property_split = False
        layout.use_property_decorate = False

        root = find_mdl_root(context.object)
        if root is None:
            layout.label(text="No BLeeds MDL root found.")
            return

        try:
            from ..ops.mdl_exporter import gather_mesh_parts
        except Exception:
            gather_mesh_parts = None

        meshes = []
        if gather_mesh_parts is not None:
            try:
                meshes = gather_mesh_parts(context, root)
            except Exception:
                meshes = []

        active_mesh_obj = context.object if context.object is not None and context.object.type == 'MESH' else None
        if active_mesh_obj is None and meshes:
            active_mesh_obj = meshes[0]

        root_box = layout.box()
        root_box.label(text="Model")
        root_col = root_box.column(align=True)
        for name, value in (
            ("Name", root.name),
            ("Platform", getattr(root, 'bleeds_mdl_platform', readMdlIdProp(root, 'bleeds_mdl_platform', 'Unknown'))),
            ("Type", getattr(root, 'bleeds_mdl_type', readMdlIdProp(root, 'bleeds_mdl_type', 'Unknown'))),
            ("Meshes", str(len(meshes))),
        ):
            row = root_col.row(align=True)
            row.label(text=name)
            row.label(text=str(value))

        if active_mesh_obj is None:
            layout.label(text="No active mesh part found under this MDL root.")
            return

        mesh = active_mesh_obj.data
        mesh_box = layout.box()
        mesh_box.label(text="Mesh")
        mesh_col = mesh_box.column(align=True)
        for name, value in (
            ("Object", active_mesh_obj.name),
            ("Vertices", str(len(mesh.vertices))),
            ("Faces", str(len(mesh.polygons))),
            ("Loops", str(len(mesh.loops))),
            ("Part", str(readMdlIdProp(active_mesh_obj, 'bleeds_mdl_part_index', readMdlIdProp(mesh, 'bleeds_mdl_source_part_index', 'none')))),
            ("Material", str(readMdlIdProp(active_mesh_obj, 'bleeds_mdl_part_material_id', readMdlIdProp(mesh, 'bleeds_mdl_source_material_index', 'none')))),
        ):
            row = mesh_col.row(align=True)
            row.label(text=name)
            row.label(text=value)

        strip_counts = readMdlIdProp(mesh, 'bleeds_mdl_source_strip_counts', [])
        try:
            strip_count = len(strip_counts)
            strip_vertex_total = sum(int(v) for v in strip_counts)
        except Exception:
            strip_count = 0
            strip_vertex_total = 0
        for name, value in (("Strips", strip_count), ("Strip vertices", strip_vertex_total)):
            row = mesh_col.row(align=True)
            row.label(text=name)
            row.label(text=str(value))

        attr_box = layout.box()
        attr_box.label(text="Attributes")
        attr_specs = [
            ("bleeds_mdl_part_index", "FACE"),
            ("bleeds_mdl_material_index", "FACE"),
            ("bleeds_mdl_source_strip_index", "FACE"),
            ("bleeds_mdl_source_strip_triangle_index", "FACE"),
            ("bleeds_mdl_corner_source_emit_index", "CORNER"),
            ("bleeds_mdl_corner_source_export_vertex_index", "CORNER"),
            ("bleeds_mdl_corner_source_strip_index", "CORNER"),
            ("bleeds_mdl_corner_source_strip_vertex_index", "CORNER"),
            ("bleeds_mdl_corner_skin_raw0", "CORNER"),
            ("bleeds_mdl_corner_skin_raw1", "CORNER"),
            ("bleeds_mdl_corner_skin_raw2", "CORNER"),
            ("bleeds_mdl_corner_skin_raw3", "CORNER"),
            ("bleeds_mdl_point_source_emit_index", "POINT"),
            ("bleeds_mdl_point_source_export_vertex_index", "POINT"),
            ("bleeds_mdl_point_source_strip_index", "POINT"),
            ("bleeds_mdl_point_source_strip_vertex_index", "POINT"),
            ("bleeds_mdl_point_skin_raw0", "POINT"),
            ("bleeds_mdl_point_skin_raw1", "POINT"),
            ("bleeds_mdl_point_skin_raw2", "POINT"),
            ("bleeds_mdl_point_skin_raw3", "POINT"),
        ]
        missing = 0
        invalid = 0
        for attr_name, domain in attr_specs:
            attr = get_mesh_attribute(mesh, attr_name)
            if attr is None:
                missing += 1
            else:
                try:
                    count = len(attr.data)
                except (AttributeError, TypeError):
                    count = -1
                if count != getMdlAttributeExpectedCount(mesh, domain):
                    invalid += 1
        summary_row = attr_box.row(align=True)
        summary_row.alert = bool(missing or invalid)
        summary_row.label(text="Present: %d/%d" % (len(attr_specs) - missing, len(attr_specs)))
        summary_row.label(text="Invalid: %d" % invalid)
        attr_box.operator(EXPORT_OT_MDL_StampSemanticAttributes.bl_idname, text="Update Attributes", icon="FILE_REFRESH")
        attr_box.prop(context.scene, "bleeds_show_mdl_attributes", text="Show Details")
        if not context.scene.bleeds_show_mdl_attributes:
            return
        attr_col = attr_box.column(align=True)
        for attr_name, domain in attr_specs:
            expected = getMdlAttributeExpectedCount(mesh, domain)
            attr = get_mesh_attribute(mesh, attr_name)
            row = attr_col.row(align=True)
            if attr is None:
                row.alert = True
                row.label(text=f"Missing: {attr_name}")
                continue
            try:
                actual = len(attr.data)
            except Exception:
                actual = -1
            if actual != expected:
                row.alert = True
            row.label(text=f"{attr_name} ({actual}/{expected})")

class OBJECT_PT_MDL_Manhunt2Properties(bpy.types.Panel):
    bl_idname = "OBJECT_PT_MDL_Manhunt2Properties"
    bl_label = "BLeeds Manhunt 2 MDL"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        root = find_mdl_root(context.object)
        return root is not None and get_mdl_root_game(root) == "MH2"

    def draw(self, context: bpy.types.Context) -> None:
        import os

        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        root = find_mdl_root(context.object)
        if root is None:
            layout.label(text="No BLeeds MH2 MDL root found.")
            return

        meshes = gather_mdl_mesh_children(root)
        active_mesh = context.object if context.object is not None and context.object.type == "MESH" else None
        if active_mesh not in meshes:
            active_mesh = meshes[0] if meshes else None

        model_box = layout.box()
        model_box.label(text="Model")
        model_col = model_box.column(align=True)
        model_col.label(text="Root: {}".format(root.name))
        model_col.label(text="Game: Manhunt 2")
        detected_type = str(root.get("bleeds_mh2_model_class", "") or "").upper().strip()
        if not detected_type:
            detected_type = "PED" if int(root.get("bleeds_mh2_bone_count", 0)) > 0 else "SIM"
        detected_platform = str(root.get("bleeds_mh2_platform", "") or "").upper().strip()
        if not detected_platform:
            detected_platform = "PSP" if str(root.get("bleeds_mh2_asset_variant", "")).upper() == "PSP_BETA" else "PC"
        model_col.label(text="MDL Type: {}".format("PedModel" if detected_type == "PED" else "SimpleModel"))
        model_col.label(text="Platform: {}".format(detected_platform))
        source_path = str(getattr(root, "bleeds_mdl_filepath", root.get("bleeds_mdl_filepath", "")) or "")
        if source_path:
            model_col.label(text="Source: {}".format(os.path.basename(source_path)))
        model_col.label(text="Bones: {}".format(int(root.get("bleeds_mh2_bone_count", 0))))
        model_col.label(text="Mesh parts: {}".format(len(meshes)))

        format_box = layout.box()
        format_box.label(text="Detected MH2 Structure")
        format_col = format_box.column(align=True)
        format_col.label(text="Asset: {}".format(root.get("bleeds_mh2_asset_variant", "Unknown")))
        format_col.label(text="Entry: {}".format(root.get("bleeds_mh2_entry_layout", "Unknown")))
        format_col.label(text="Bones: {}".format(root.get("bleeds_mh2_bone_record_layout", "Unknown")))
        format_col.label(text="Object header: {}".format(root.get("bleeds_mh2_object_header_layout", "Unknown")))

        texture_box = layout.box()
        texture_box.label(text="Textures")
        texture_col = texture_box.column(align=True)
        texture_path = str(root.get("bleeds_mh2_texture_source_path", "") or "")
        if texture_path:
            texture_col.label(text="TEX: {}".format(os.path.basename(texture_path)))
        else:
            texture_col.label(text="TEX: Not imported")
        texture_col.label(text="Images: {}".format(int(root.get("bleeds_mh2_texture_image_count", 0))))

        if active_mesh is None:
            return

        mesh = active_mesh.data
        mesh_box = layout.box()
        mesh_box.label(text="Active MH2 Mesh Part")
        mesh_col = mesh_box.column(align=True)
        mesh_col.label(text="Object: {}".format(active_mesh.name))
        mesh_col.label(text="Vertices: {}".format(len(mesh.vertices)))
        mesh_col.label(text="Faces: {}".format(len(mesh.polygons)))
        mesh_col.label(text="Materials: {}".format(len(mesh.materials)))
        parent_bone = str(active_mesh.get("bleeds_mh2_parent_bone_name", "") or "")
        if parent_bone:
            mesh_col.label(text="Parent bone: {}".format(parent_bone))
        vertex_element_type = int(active_mesh.get("bleeds_mh2_vertex_element_type", 0))
        mesh_col.label(text="Vertex element: 0x{:X}".format(vertex_element_type))
        mesh_col.label(text="Vertex stride: 0x{:X}".format(int(active_mesh.get("bleeds_mh2_vertex_stride", 0))))
        mesh_col.label(text="Vertex layout: {}".format(active_mesh.get("bleeds_mh2_vertex_layout", "Unknown")))
        mesh_col.label(text="UV layers: {}".format(int(active_mesh.get("bleeds_mh2_uv_layer_count", len(mesh.uv_layers)))))
        mesh_col.label(text="Skin weights: {}".format("Yes" if bool(active_mesh.get("bleeds_mh2_has_skin_weights", False)) else "No"))
        mesh_col.label(text="Weighted vertices: {}".format(int(active_mesh.get("bleeds_mh2_weighted_vertex_count", 0))))


def register() -> None:
    bpy.utils.register_class(OBJECT_OT_BLeeds_SnapArmature)
    bpy.utils.register_class(OBJECT_PT_BLeeds_SnapArmature)
    bpy.utils.register_class(EXPORT_OT_MDL_Bake_LeedsScalePos)
    bpy.utils.register_class(EXPORT_PT_MDL_LeedsScalePos)
    bpy.utils.register_class(EXPORT_OT_MDL_StampSemanticAttributes)
    bpy.utils.register_class(EXPORT_PT_MDL_SemanticAttributes)
    bpy.utils.register_class(OBJECT_PT_MDL_Manhunt2Properties)

    bpy.types.Scene.bleeds_reference_armature = PointerProperty(
        name="Reference Armature", type=bpy.types.Object, poll=isArmatureObject)
    bpy.types.Scene.bleeds_reference_use_pose = BoolProperty(
        name="Use Current Pose", default=True)
    bpy.types.Scene.bleeds_reference_weights = BoolProperty(
        name="Use Reference Weights", default=False)
    bpy.types.Scene.bleeds_show_mdl_attributes = BoolProperty(
        name="Show Details", default=False)

    if not hasattr(bpy.types.Object, "bleeds_is_mdl_root"):
        bpy.types.Object.bleeds_is_mdl_root = BoolProperty(
            name="BLeeds MDL Root",
            description="Marks this object as the root of an imported BLeeds MDL",
            default=False,
        )

    if not hasattr(bpy.types.Object, "bleeds_mdl_platform"):
        bpy.types.Object.bleeds_mdl_platform = EnumProperty(
            name="Platform",
            description="Leeds model platform for this MDL",
            items=[
                ("PS2", "PS2", "PlayStation 2"),
                ("PSP", "PSP", "PlayStation Portable"),
                ("PC", "PC", "Windows PC"),
            ],
            default="PS2",
        )

    if not hasattr(bpy.types.Object, "bleeds_model_game"):
        bpy.types.Object.bleeds_model_game = EnumProperty(
            name="3D Models",
            description="Leeds 3D model family",
            items=[
                ("LCS", "LCS", "Grand Theft Auto: Liberty City Stories"),
                ("VCS", "VCS", "Grand Theft Auto: Vice City Stories"),
                ("MH2", "MH2", "Manhunt 2"),
            ],
            default="VCS",
        )

    if not hasattr(bpy.types.Object, "bleeds_mdl_type"):
        bpy.types.Object.bleeds_mdl_type = EnumProperty(
            name="MDL Type",
            description="Leeds MDL model class",
            items=[
                ("SIM", "SimpleModel", "Prop or simple model"),
                ("PED", "PedModel", "Pedestrian or skinned actor model"),
                ("CUT", "CutsceneModel", "Cutscene actor model"),
                ("VEH", "VehModel", "Vehicle model"),
            ],
            default="SIM",
        )

    if not hasattr(bpy.types.Object, "bleeds_mdl_filepath"):
        bpy.types.Object.bleeds_mdl_filepath = StringProperty(
            name="Source File",
            description="Original MDL file path used for import",
            default="",
            subtype="FILE_PATH",
        )

    if not hasattr(bpy.types.Object, "bleeds_imported_export_mode"):
        bpy.types.Object.bleeds_imported_export_mode = EnumProperty(
            name="Internal PED Rebuild",
            description="Imported PEDs rebuild from live mesh data",
            items=[("REBUILD", "Rebuild", "Rebuild using calculated live data and ped_atomic_bind basis")],
            default="REBUILD",
        )

    if not hasattr(bpy.types.Object, "bleeds_leeds_scale_base"):
        bpy.types.Object.bleeds_leeds_scale_base = FloatVectorProperty(
            name="Leeds Scale (Base)",
            description="Base in-game scale stored by the MDL (used for vertex decode)",
            size=3,
            default=(1.0, 1.0, 1.0),
            subtype="XYZ",
        )

    if not hasattr(bpy.types.Object, "bleeds_leeds_pos_base"):
        bpy.types.Object.bleeds_leeds_pos_base = FloatVectorProperty(
            name="Leeds Pos (Base)",
            description="Base in-game position stored by the MDL (used for vertex decode)",
            size=3,
            default=(0.0, 0.0, 0.0),
            subtype="TRANSLATION",
        )

def unregister() -> None:

    for property_name in ("bleeds_reference_armature", "bleeds_reference_use_pose", "bleeds_reference_weights", "bleeds_show_mdl_attributes"):
        if hasattr(bpy.types.Scene, property_name):
            delattr(bpy.types.Scene, property_name)

    bpy.utils.unregister_class(OBJECT_PT_MDL_Manhunt2Properties)
    bpy.utils.unregister_class(EXPORT_PT_MDL_SemanticAttributes)
    bpy.utils.unregister_class(EXPORT_OT_MDL_StampSemanticAttributes)
    bpy.utils.unregister_class(EXPORT_PT_MDL_LeedsScalePos)
    bpy.utils.unregister_class(EXPORT_OT_MDL_Bake_LeedsScalePos)
    bpy.utils.unregister_class(OBJECT_PT_BLeeds_SnapArmature)
    bpy.utils.unregister_class(OBJECT_OT_BLeeds_SnapArmature)

    for prop_name in (
        "bleeds_is_mdl_root",
        "bleeds_mdl_platform",
        "bleeds_model_game",
        "bleeds_mdl_type",
        "bleeds_mdl_filepath",
        "bleeds_leeds_scale_base",
        "bleeds_leeds_pos_base",
    ):
        if hasattr(bpy.types.Object, prop_name):
            delattr(bpy.types.Object, prop_name)
