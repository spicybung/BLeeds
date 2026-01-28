# BLeeds - Scripts for working with R* Leeds (GTA Stories, Manhunt 2, etc) formats in Blender
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

import os
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Any

import bpy
from mathutils import Matrix, Vector

from ..leedsLib import mdl as stories_mdl


@dataclass
class StoriesImportContext:
    """Light wrapper around the raw StoriesMDLContext for Blender import."""
    filepath: str
    platform: str
    mdl_type: str
    shrink: int
    import_type: int
    atomic: Any
    debug_log: List[str] = field(default_factory=list)

    def log(self, msg: str) -> None:
        self.debug_log.append(str(msg))
        print(msg)


# Simple material cache so we reuse materials across parts/meshes
MATERIAL_CACHE: Dict[str, bpy.types.Material] = {}


def get_bone_name_list(import_type: int) -> List[str]:
    """
    Return the canonical bone name list for LCS/VCS based on import_type.

    import_type mapping (as used in mdl.py):
        0,1   → LCS PS2/PSP
        2,3   → VCS PS2/PSP
    """
    names: List[str] = []

    if import_type in (0, 1):
        for name in stories_mdl.commonBoneNamesLCS:
            names.append(name)
    elif import_type in (2, 3):
        for name in stories_mdl.commonBoneNamesVCS:
            names.append(name)
    else:
        for i in range(32):
            names.append(f"bone_{i:02d}")

    return names


def get_bone_parent_map(import_type: int) -> Dict[str, str]:
    """Return parent name mapping for LCS or VCS, based on import_type."""
    if import_type in (0, 1):
        return dict(stories_mdl.commonBoneParentsLCS)
    if import_type in (2, 3):
        return dict(stories_mdl.commonBoneParentsVCS)
    return {}


def create_armature_from_context(
    context: bpy.types.Context,
    stories_ctx: Any,
    collection: bpy.types.Collection,
    name_suffix: str,
) -> bpy.types.Object:
    """
    Build an Armature object from Stories MDL frame data.
    Parenting is done by matching names through common Stories parent tables.
    The armature is placed in world space using the frame_mats_world matrices.
    """
    atomic = stories_ctx.atomic
    arm_info = atomic.armature

    if not arm_info.frame_names:
        return None

    view_layer = context.view_layer
    old_active = view_layer.objects.active
    old_mode = context.mode

    base_name = os.path.splitext(os.path.basename(stories_ctx.filepath))[0]
    arm_data = bpy.data.armatures.new(f"{base_name}_{name_suffix}")
    arm_obj = bpy.data.objects.new(arm_data.name, arm_data)
    collection.objects.link(arm_obj)

    view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")

    bone_parent_map = get_bone_parent_map(stories_ctx.import_type)
    name_to_edit_bone: Dict[str, bpy.types.EditBone] = {}

    for ptr, name in arm_info.frame_names.items():
        if ptr not in arm_info.frame_mats_world:
            continue

        world_mat = arm_info.frame_mats_world[ptr]
        head = world_mat.to_translation()

        y_axis = Vector((world_mat[0][1], world_mat[1][1], world_mat[2][1]))
        if y_axis.length == 0.0:
            y_axis = Vector((0.0, 0.1, 0.0))
        else:
            y_axis.normalize()
            y_axis *= 0.1

        tail = head + y_axis

        edit_bone = arm_data.edit_bones.new(name)
        edit_bone.head = head
        edit_bone.tail = tail

        name_to_edit_bone[name] = edit_bone

    for name, edit_bone in name_to_edit_bone.items():
        parent_name = bone_parent_map.get(name)
        if parent_name and parent_name in name_to_edit_bone:
            edit_bone.parent = name_to_edit_bone[parent_name]

    bpy.ops.object.mode_set(mode="OBJECT")

    if old_active is not None:
        try:
            view_layer.objects.active = old_active
            bpy.ops.object.mode_set(mode=old_mode)
        except Exception:
            pass

    return arm_obj


def match_mesh_to_armature_space(
    obj: bpy.types.Object,
    stories_ctx: Any,
    arm_obj: bpy.types.Object,
) -> None:
    """
    Move a mesh object into the same space as the armature using the
    frame_mats_world entry for the atomic's frame_ptr and attach an
    armature modifier.
    """
    if arm_obj is None:
        return

    atomic = stories_ctx.atomic
    arm_info = atomic.armature
    frame_ptr = atomic.frame_ptr

    world_mat = arm_info.frame_mats_world.get(frame_ptr)
    if world_mat is not None:
        obj.matrix_world = world_mat

    for mod in list(obj.modifiers):
        if mod.type == "ARMATURE":
            obj.modifiers.remove(mod)

    arm_mod = obj.modifiers.new(name="Armature", type="ARMATURE")
    arm_mod.object = arm_obj

    obj.parent = arm_obj
    obj.matrix_parent_inverse = arm_obj.matrix_world.inverted()



def parent_object_keep_world(child_obj: bpy.types.Object, parent_obj: bpy.types.Object) -> None:
    """Parent a Blender object while preserving its world-space transform."""
    if child_obj is None or parent_obj is None:
        return

    saved_world = child_obj.matrix_world.copy()
    child_obj.parent = parent_obj
    child_obj.matrix_parent_inverse = parent_obj.matrix_world.inverted()
    child_obj.matrix_world = saved_world
def get_or_create_material_for_stories(
    mat_desc: Any,
    index: int,
) -> bpy.types.Material:
    """Create a Principled BSDF material from a Stories material description (no images loaded)."""
    key = getattr(mat_desc, "texture", "") or f"StoriesMat_{index:03d}"
    if key in MATERIAL_CACHE:
        return MATERIAL_CACHE[key]

    mat = bpy.data.materials.new(name=key)
    mat.use_nodes = True

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    for n in list(nodes):
        nodes.remove(n)

    out = nodes.new(type="ShaderNodeOutputMaterial")
    out.location = (300, 0)

    bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)

    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    rgba = getattr(mat_desc, "rgba", 0)
    r = (rgba & 0xFF) / 255.0
    g = ((rgba >> 8) & 0xFF) / 255.0
    b = ((rgba >> 16) & 0xFF) / 255.0
    a = ((rgba >> 24) & 0xFF) / 255.0 if rgba != 0 else 1.0

    bsdf.inputs["Base Color"].default_value = (r, g, b, a)

    MATERIAL_CACHE[key] = mat
    return mat


def assign_ps2_skin(
    obj: bpy.types.Object,
    part: Any,
    import_type: int,
    arm_obj: bpy.types.Object,
) -> None:
    """
    Assign vertex groups and weights for PS2 Stories geometry.
    Uses per-strip bone indices / weights from part.strips_meta.
    """
    if arm_obj is None:
        return

    me = obj.data
    vertex_count = len(me.vertices)
    if vertex_count == 0:
        return

    obj.vertex_groups.clear()

    bone_names = get_bone_name_list(import_type)
    vg_by_index: Dict[int, bpy.types.VertexGroup] = {}

    def get_vg(bone_index: int) -> bpy.types.VertexGroup:
        if bone_index not in vg_by_index:
            if 0 <= bone_index < len(bone_names):
                name = bone_names[bone_index]
            else:
                name = f"bone_{bone_index:02d}"
            vg_by_index[bone_index] = obj.vertex_groups.new(name=name)
        return vg_by_index[bone_index]

    for strip in part.strips_meta:
        base = strip.base_vertex_index
        count = strip.vertex_count

        if not strip.skin_indices or not strip.skin_weights:
            continue

        for local_i in range(count):
            vert_index = base + local_i
            if vert_index < 0 or vert_index >= vertex_count:
                continue

            for bone_index, weight in zip(strip.skin_indices[local_i], strip.skin_weights[local_i]):
                if weight <= 0.0:
                    continue
                vg = get_vg(bone_index)
                vg.add([vert_index], weight, "REPLACE")


def assign_psp_skin(
    obj: bpy.types.Object,
    mesh_data: Any,
    import_type: int,
    arm_obj: bpy.types.Object,
) -> None:
    """
    Assign vertex groups and weights for PSP Stories geometry.
    PSP format stores weights slightly differently but conceptually similar.
    """
    if arm_obj is None:
        return

    me = obj.data
    vertex_count = len(me.vertices)
    if vertex_count == 0:
        return

    obj.vertex_groups.clear()

    bone_names = get_bone_name_list(import_type)
    vg_by_index: Dict[int, bpy.types.VertexGroup] = {}

    def get_vg(bone_index: int) -> bpy.types.VertexGroup:
        if bone_index not in vg_by_index:
            if 0 <= bone_index < len(bone_names):
                name = bone_names[bone_index]
            else:
                name = f"bone_{bone_index:02d}"
            vg_by_index[bone_index] = obj.vertex_groups.new(name=name)
        return vg_by_index[bone_index]

    if not getattr(mesh_data, "bone_indices", None) or not getattr(mesh_data, "bone_weights", None):
        return

    for vert_index in range(vertex_count):
        if vert_index >= len(mesh_data.bone_indices):
            break
        indices = mesh_data.bone_indices[vert_index]
        weights = mesh_data.bone_weights[vert_index]
        for bone_index, weight in zip(indices, weights):
            if weight <= 0.0:
                continue
            vg = get_vg(bone_index)
            vg.add([vert_index], weight, "REPLACE")


def build_ps2_meshes(
    context: bpy.types.Context,
    stories_ctx: Any,
    collection: bpy.types.Collection,
    arm_obj: bpy.types.Object,
) -> List[bpy.types.Object]:
    """Create Blender mesh objects for PS2 Stories geometry."""
    atomic = stories_ctx.atomic
    geo = atomic.ps2_geometry

    created_objects: List[bpy.types.Object] = []
    base_name = os.path.splitext(os.path.basename(stories_ctx.filepath))[0]

    for part_index, part in enumerate(geo.parts):
        name = f"{base_name}_ps2_p{part_index:02d}"

        verts = list(part.verts)
        faces = list(part.faces)

        me = bpy.data.meshes.new(name)
        me.from_pydata(verts, [], faces)
        me.update(calc_edges=True)

        uvs = getattr(part, "uvs", None)
        if uvs:
            uv_layer = me.uv_layers.new(name="UVMap")
            uv_data = uv_layer.data
            for poly in me.polygons:
                for loop_index in range(poly.loop_start, poly.loop_start + poly.loop_total):
                    if loop_index >= len(me.loops):
                        continue
                    vert_index = me.loops[loop_index].vertex_index
                    if vert_index < len(uvs):
                        u, v = uvs[vert_index]
                        uv_data[loop_index].uv = (u, 1.0 - v)

        colors = getattr(part, "vertex_colors", None)
        if not colors:
            colors = getattr(part, "loop_colors", None)
        if colors:
            color_attr = me.color_attributes.new(
                name="Col",
                type="BYTE_COLOR",
                domain="CORNER",
            )
            col_data = color_attr.data
            for poly in me.polygons:
                for loop_index in range(poly.loop_start, poly.loop_start + poly.loop_total):
                    if loop_index >= len(me.loops):
                        continue
                    vert_index = me.loops[loop_index].vertex_index
                    if vert_index < len(colors):
                        r, g, b, a = colors[vert_index]
                        col_data[loop_index].color = (
                            r / 255.0,
                            g / 255.0,
                            b / 255.0,
                            a / 255.0,
                        )

        obj = bpy.data.objects.new(name, me)
        collection.objects.link(obj)

        if geo.materials and 0 <= part.material_id < len(geo.materials):
            mat_desc = geo.materials[part.material_id]
            mat = get_or_create_material_for_stories(mat_desc, part.material_id)
            if mat is not None:
                if len(obj.data.materials) == 0:
                    obj.data.materials.append(mat)
                else:
                    obj.data.materials[0] = mat

        if arm_obj is not None:
            match_mesh_to_armature_space(obj, stories_ctx, arm_obj)
            assign_ps2_skin(obj, part, stories_ctx.import_type, arm_obj)

        created_objects.append(obj)

        try:
            norms = getattr(part, "normals", None)
            if norms:
                obj["bleeds_imported_normals"] = [
                    (float(n[0]), float(n[1]), float(n[2])) for n in norms
                ]
        except Exception:
            pass

    return created_objects


def build_psp_meshes(
    context: bpy.types.Context,
    stories_ctx: Any,
    collection: bpy.types.Collection,
    arm_obj: bpy.types.Object,
) -> List[bpy.types.Object]:
    """Create Blender mesh objects for PSP Stories geometry."""
    atomic = stories_ctx.atomic
    geo = atomic.psp_geometry

    created_objects: List[bpy.types.Object] = []
    base_name = os.path.splitext(os.path.basename(stories_ctx.filepath))[0]

    for mesh_index, mesh_data in enumerate(geo.meshes):
        name = f"{base_name}_psp_m{mesh_index:02d}"

        verts: List[Tuple[float, float, float]] = list(mesh_data.verts)
        faces: List[Tuple[int, int, int]] = list(mesh_data.faces)

        me = bpy.data.meshes.new(name)
        me.from_pydata(verts, [], faces)
        me.update(calc_edges=True)

        if getattr(mesh_data, "uvs", None):
            uv_layer = me.uv_layers.new(name="UVMap")
            uv_data = uv_layer.data
            for poly in me.polygons:
                for loop_index in range(poly.loop_start, poly.loop_start + poly.loop_total):
                    if loop_index >= len(me.loops):
                        continue
                    vert_index = me.loops[loop_index].vertex_index
                    if vert_index < len(mesh_data.uvs):
                        u, v = mesh_data.uvs[vert_index]
                        uv_data[loop_index].uv = (u, 1.0 - v)

        colors = getattr(mesh_data, "colors", None)
        if colors:
            color_attr = me.color_attributes.new(
                name="Col",
                type="BYTE_COLOR",
                domain="CORNER",
            )
            col_data = color_attr.data
            for poly in me.polygons:
                for loop_index in range(poly.loop_start, poly.loop_start + poly.loop_total):
                    if loop_index >= len(me.loops):
                        continue
                    vert_index = me.loops[loop_index].vertex_index
                    if vert_index < len(colors):
                        r, g, b, a = colors[vert_index]
                        col_data[loop_index].color = (
                            r / 255.0,
                            g / 255.0,
                            b / 255.0,
                            a / 255.0,
                        )

        obj = bpy.data.objects.new(name, me)
        collection.objects.link(obj)

        if geo.materials and 0 <= mesh_data.mat_id < len(geo.materials):
            mat_desc = geo.materials[mesh_data.mat_id]
            mat = get_or_create_material_for_stories(mat_desc, mesh_data.mat_id)
            if mat is not None:
                if len(obj.data.materials) == 0:
                    obj.data.materials.append(mat)
                else:
                    obj.data.materials[0] = mat

        if arm_obj is not None:
            match_mesh_to_armature_space(obj, stories_ctx, arm_obj)
            assign_psp_skin(obj, mesh_data, stories_ctx.import_type, arm_obj)

        created_objects.append(obj)

    return created_objects


def build_stories_armature_from_frame_mats(
    context,
    arm_info: stories_mdl.StoriesArmatureInfo,
    armature_name: str,
    collection: bpy.types.Collection,
    debug: bool = False,
) -> bpy.types.Object:
    """
    Alternate armature builder that takes a StoriesArmatureInfo directly.
    Kept for compatibility – main code path uses create_armature_from_context().
    """
    frame_mats_world = arm_info.frame_mats_world
    frame_names = arm_info.frame_names

    arm_data = bpy.data.armatures.new(armature_name)
    armature_obj = bpy.data.objects.new(armature_name, arm_data)
    collection.objects.link(armature_obj)

    bones_by_ptr: Dict[int, bpy.types.EditBone] = {}

    with context.temp_override(object=armature_obj):
        bpy.ops.object.mode_set(mode='EDIT')

        for frame_ptr, name in frame_names.items():
            if frame_ptr not in frame_mats_world:
                continue

            world_mat = frame_mats_world[frame_ptr]
            head = world_mat.to_translation()

            y_axis = Vector((world_mat[0][1], world_mat[1][1], world_mat[2][1]))
            if y_axis.length == 0.0:
                y_axis = Vector((0.0, 0.1, 0.0))
            else:
                y_axis.normalize()
                y_axis *= 0.1

            tail = head + y_axis

            eb = arm_data.edit_bones.new(name)
            eb.head = head
            eb.tail = tail
            bones_by_ptr[frame_ptr] = eb

        bpy.ops.object.mode_set(mode='OBJECT')

    if debug:
        print(f"Created armature '{armature_name}' with {len(bones_by_ptr)} bones")

    return armature_obj


def import_stories_mdl(
    context: bpy.types.Context,
    filepath: str,
    platform: str,
    mdl_type: str,
    collection_name: str,
    create_armature: bool,
    link_to_scene: bool,
) -> List[bpy.types.Object]:
    """
    High-level entry point used by the GUI operator to import a Stories MDL file.
    """
    stories_reader = stories_mdl.read_stories(filepath, platform, mdl_type)
    ctx_raw = stories_reader.read()

    stories_ctx = StoriesImportContext(
        filepath=ctx_raw.filepath,
        platform=ctx_raw.platform,
        mdl_type=ctx_raw.mdl_type,
        shrink=ctx_raw.shrink,
        import_type=ctx_raw.import_type,
        atomic=ctx_raw.atomic,
        debug_log=list(ctx_raw.debug_log),
    )

    if collection_name and collection_name in bpy.data.collections:
        collection = bpy.data.collections[collection_name]
    else:
        collection = bpy.data.collections.new(collection_name or "Stories_MDL")
        if link_to_scene:
            context.scene.collection.children.link(collection)

    base_name = os.path.splitext(os.path.basename(filepath))[0]
    root_name = f"{base_name}_ROOT"
    root_obj = bpy.data.objects.new(root_name, None)
    root_obj.empty_display_type = "PLAIN_AXES"
    root_obj.empty_display_size = 0.5
    collection.objects.link(root_obj)

    scale_base = (1.0, 1.0, 1.0)
    pos_base = (0.0, 0.0, 0.0)
    atomic = stories_ctx.atomic
    if platform == "PS2" and getattr(atomic, "ps2_geometry", None) is not None:
        geo = atomic.ps2_geometry
        scale_base = (float(geo.x_scale), float(geo.y_scale), float(geo.z_scale))
        pos_base = (float(geo.translation[0]), float(geo.translation[1]), float(geo.translation[2]))
    elif platform != "PS2" and getattr(atomic, "psp_geometry", None) is not None:
        geo = atomic.psp_geometry
        scale_base = (float(geo.scale[0]), float(geo.scale[1]), float(geo.scale[2]))
        pos_base = (float(geo.pos[0]), float(geo.pos[1]), float(geo.pos[2]))

    try:
        root_obj.bleeds_is_mdl_root = True
        root_obj.bleeds_mdl_platform = platform
        root_obj.bleeds_mdl_type = mdl_type
        root_obj.bleeds_mdl_filepath = filepath
        root_obj.bleeds_leeds_scale_base = scale_base
        root_obj.bleeds_leeds_pos_base = pos_base
    except Exception:
        root_obj["bleeds_is_mdl_root"] = True
        root_obj["bleeds_mdl_platform"] = str(platform)
        root_obj["bleeds_mdl_type"] = str(mdl_type)
        root_obj["bleeds_mdl_filepath"] = str(filepath)
        root_obj["bleeds_leeds_scale_base"] = [float(scale_base[0]), float(scale_base[1]), float(scale_base[2])]
        root_obj["bleeds_leeds_pos_base"] = [float(pos_base[0]), float(pos_base[1]), float(pos_base[2])]

    created_objects: List[bpy.types.Object] = []

    strip_counts: list[int] = []
    try:
        dbg = getattr(stories_ctx, "debug_log", None)
        if dbg:
            import re
            for line in dbg:
                m = re.search(r"curStripVertCount:\s*(\d+)", str(line))
                if m:
                    try:
                        strip_counts.append(int(m.group(1)))
                    except Exception:
                        pass
        if strip_counts:
            try:
                root_obj.bleeds_imported_strip_counts = [int(x) for x in strip_counts]
            except Exception:
                root_obj["bleeds_imported_strip_counts"] = [int(x) for x in strip_counts]
    except Exception:
        pass

    arm_obj: bpy.types.Object = None
    if create_armature and mdl_type == "PED":
        arm_obj = create_armature_from_context(
            context=context,
            stories_ctx=stories_ctx,
            collection=collection,
            name_suffix="Arm",
        )

    if platform == "PS2":
        created_objects.extend(
            build_ps2_meshes(
                context=context,
                stories_ctx=stories_ctx,
                collection=collection,
                arm_obj=arm_obj,
            )
        )
    else:
        created_objects.extend(
            build_psp_meshes(
                context=context,
                stories_ctx=stories_ctx,
                collection=collection,
                arm_obj=arm_obj,
            )
        )


    if arm_obj is None:
        for obj in created_objects:
            if obj is not None and obj.type == "MESH":
                parent_object_keep_world(obj, root_obj)
    if arm_obj is not None:
        parent_object_keep_world(arm_obj, root_obj)
        created_objects.insert(0, arm_obj)


    created_objects.insert(0, root_obj)

    return created_objects
