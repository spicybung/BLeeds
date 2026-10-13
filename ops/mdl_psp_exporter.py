import math
import base64
import os
import struct
import zlib

import bpy
from mathutils import Matrix, Vector

from ..leedsLib import mdl
from ..leedsLib.psp import PspResource
from . import mdl_exporter


def readPspMatrix(owner, key, fallback):
    value = owner.get(key) if owner is not None else None
    if value is None or len(value) != 16:
        return fallback.copy()
    return Matrix(tuple(tuple(float(value[row * 4 + column]) for column in range(4)) for row in range(4)))


def collectPspFrames(root, armature, source_context):
    records = {}
    source_frames = source_context.atomic.armature if source_context is not None else None
    if source_frames is not None:
        for pointer, name in source_frames.frame_names.items():
            parent = source_frames.frame_parent_ptrs.get(pointer, 0)
            records[pointer] = {
                'key': pointer, 'name': name, 'parent': parent if parent in source_frames.frame_names else None,
                'world': source_frames.frame_mats_world[pointer].copy(), 'source_pointer': pointer,
                'bone_id': 255, 'bone_type': 0,
            }
        for entry in getattr(source_frames, 'hierarchy_entries', []):
            pointer = entry['frame_ptr']
            if pointer in records:
                records[pointer]['bone_id'] = entry['bone_id']
                records[pointer]['bone_type'] = entry['bone_type']
    bone_keys = {}
    if armature is not None:
        frame_names = armature.get('bleeds_mdl_frame_bone_names', {})
        pointers_by_bone = {str(name): int(pointer) for pointer, name in frame_names.items()}
        for bone in armature.data.bones:
            pointer = pointers_by_bone.get(bone.name, int(bone.get('bleeds_frame_ptr', 0)))
            key = pointer if pointer in records else 'bone:' + bone.name
            bone_keys[bone.name] = key
            imported = readPspMatrix(bone, 'bleeds_blender_import_global_matrix', bone.matrix_local)
            original = records[key]['world'] if key in records else bone.matrix_local
            world = bone.matrix_local @ imported.inverted_safe() @ original
            if key in records:
                bone_id = records[key]['bone_id']
                bone_type = records[key]['bone_type']
            else:
                bone_id = int(bone.get('bleeds_mdl_raw_hanim_bone_id', bone.get('BoneID', len(bone_keys) - 1)))
                bone_type = int(bone.get('bleeds_mdl_hierarchy_bone_type', bone.get('BoneType', 0)))
            if 'bleeds_psp_bone_id' in bone:
                bone_id = int(bone['bleeds_psp_bone_id'])
            elif 'bleeds_psp_import_display_bone_id' in bone and int(bone.get('BoneID', bone_id)) != int(bone['bleeds_psp_import_display_bone_id']):
                bone_id = int(bone['BoneID'])
            records[key] = {
                'key': key, 'name': records[key]['name'] if key in records else bone.name,
                'parent': None, 'world': world.copy(), 'source_pointer': pointer if pointer in records else 0,
                'bone_id': bone_id, 'bone_type': bone_type,
            }
        for bone in armature.data.bones:
            key = bone_keys[bone.name]
            records[key]['parent'] = bone_keys.get(bone.parent.name) if bone.parent is not None else None
    else:
        empties = [obj for obj in root.children_recursive if obj.type == 'EMPTY']
        empty_keys = {}
        for obj in empties:
            pointer = int(obj.get('bleeds_frame_ptr', 0))
            empty_keys[obj] = pointer if pointer in records else 'frame:' + obj.name
        for obj in empties:
            pointer = int(obj.get('bleeds_frame_ptr', 0))
            key = pointer if pointer in records else 'frame:' + obj.name
            parent = empty_keys.get(obj.parent)
            records[key] = {
                'key': key, 'name': str(obj.get('bleeds_frame_name', obj.name)),
                'parent': parent if parent in records else None,
                'world': root.matrix_world.inverted_safe() @ obj.matrix_world,
                'source_pointer': pointer, 'bone_id': 0, 'bone_type': 0,
            }
    if not records:
        records['root'] = {'key': 'root', 'name': root.name, 'parent': None,
                           'world': Matrix.Identity(4), 'source_pointer': 0, 'bone_id': 0, 'bone_type': 0}
    roots = [key for key, record in records.items() if record['parent'] not in records]
    if len(roots) != 1:
        records['root'] = {'key': 'root', 'name': root.name, 'parent': None,
                           'world': Matrix.Identity(4), 'source_pointer': 0, 'bone_id': 0, 'bone_type': 0}
        for key in roots:
            records[key]['parent'] = 'root'
        roots = ['root']
    children = {key: [] for key in records}
    for key, record in records.items():
        if record['parent'] in children:
            children[record['parent']].append(key)
    ordered = []
    visiting = set()

    def visit(key):
        if key in visiting:
            raise ValueError("PSP frame hierarchy contains a cycle")
        visiting.add(key)
        ordered.append(records[key])
        for child in children[key]:
            visit(child)

    visit(roots[0])
    if len(ordered) != len(records) or len(ordered) > 256:
        raise ValueError("PSP skin hierarchy must contain at most 256 connected frames")
    node_by_key = {record['key']: index for index, record in enumerate(ordered)}
    animation_records = ordered
    if source_frames is not None and getattr(source_frames, 'hierarchy_entries', None):
        anchor = int(source_frames.hierarchy_anchor_ptr)
        animation_records = []

        def visitAnimation(key):
            animation_records.append(records[key])
            for child in children[key]:
                visitAnimation(child)

        if anchor in records:
            visitAnimation(anchor)
        else:
            animation_records = ordered
    node_by_key = {record['key']: index for index, record in enumerate(animation_records)}
    if source_frames is None or any(not record['source_pointer'] for record in animation_records):
        stack_depth = 0
        animation_keys = {record['key'] for record in animation_records}
        for record in animation_records:
            siblings = [key for key in children.get(record['parent'], []) if key in animation_keys]
            flags = 0
            if record['key'] in siblings and siblings.index(record['key']) < len(siblings) - 1:
                flags |= 2
                stack_depth += 1
            if not any(key in animation_keys for key in children[record['key']]) and stack_depth:
                flags |= 1
                stack_depth -= 1
            record['bone_type'] = flags
    bone_nodes = {name: node_by_key[key] for name, key in bone_keys.items() if key in node_by_key}
    return ordered, bone_nodes, animation_records


def appendPspFrames(resource, records, skinned, game, animation_records):
    offsets = {}
    for record in records:
        offset = resource.reserve(0xB0, 16)
        offsets[record['key']] = offset
        source_pointer = record['source_pointer']
        if source_pointer and source_pointer + 0xB0 <= len(resource.data):
            resource.data[offset:offset + 0xB0] = resource.data[source_pointer:source_pointer + 0xB0]
        else:
            struct.pack_into("<I", resource.data, offset, 0x300)
    root_offset = offsets[records[0]['key']]
    children = {record['key']: [] for record in records}
    record_by_key = {record['key']: record for record in records}
    for record in records:
        if record['parent'] in children:
            children[record['parent']].append(record['key'])
    for record in records:
        offset = offsets[record['key']]
        parent_key = record['parent']
        parent_offset = offsets.get(parent_key, 0)
        local = record['world']
        if parent_key in record_by_key:
            local = record_by_key[parent_key]['world'].inverted_safe() @ record['world']
        resource.matrix(offset + 0x10, local)
        resource.matrix(offset + 0x50, record['world'])
        resource.pointer(offset + 4, parent_offset)
        resource.pointer(offset + 8, offset + 8)
        resource.pointer(offset + 12, offset + 8)
        child_keys = children[record['key']]
        resource.pointer(offset + 0x90, offsets[child_keys[0]] if child_keys else 0)
        siblings = children.get(parent_key, [])
        sibling_index = siblings.index(record['key']) if record['key'] in siblings else -1
        next_key = siblings[sibling_index + 1] if 0 <= sibling_index < len(siblings) - 1 else None
        resource.pointer(offset + 0x94, offsets.get(next_key, 0))
        resource.pointer(offset + 0x98, root_offset)
        struct.pack_into('<I', resource.data, offset + 0x9C, int(record['bone_id']) & 0xFFFFFFFF)
        resource.pointer(offset + 0xA4, 0)
        resource.pointer(offset + 0xA8, resource.string(record['name']))
    hierarchy = 0
    skin = 0
    if skinned:
        animation_count = len(animation_records)
        animation_root = offsets[animation_records[0]['key']]
        hierarchy = resource.reserve(0x38 if game == 'VCS' else 0x60, 16)
        struct.pack_into("<II", resource.data, hierarchy, 0x3000, animation_count)
        matrices = resource.reserve(animation_count * 64, 64)
        inverse = resource.reserve(animation_count * 64, 64)
        entries = resource.reserve(animation_count * 8)
        for index, record in enumerate(animation_records):
            if not 0 <= record['bone_id'] <= 255:
                raise ValueError("PSP animation bone IDs must fit in one byte")
            resource.matrix(matrices + index * 64, Matrix.Identity(4))
            resource.matrix(inverse + index * 64, record['world'].inverted_safe())
            flags = int(record['bone_type']) & 255
            packed = record['bone_id'] | (index << 8) | (flags << 16)
            struct.pack_into("<II", resource.data, entries + index * 8, packed, 0)
            resource.pointer(offsets[record['key']] + 0xA4, hierarchy if index == 0 else 0)
        resource.pointer(hierarchy + 0x28, matrices)
        resource.pointer(hierarchy + 0x2C, matrices)
        resource.pointer(hierarchy + 0x30, entries)
        resource.pointer(hierarchy + 0x34, animation_root)
        if game == 'LCS':
            struct.pack_into('<II', resource.data, hierarchy + 0x38, 0x24, 0x24)
            resource.pointer(hierarchy + 0x50, hierarchy)
        skin = resource.reserve(0x34)
        struct.pack_into("<II", resource.data, skin, animation_count, animation_count)
        resource.pointer(skin + 12, inverse)
    return offsets, hierarchy, skin


def pspVertexWeights(obj, mesh, vertex_index, bone_nodes):
    pairs = {}
    for assignment in mesh.vertices[vertex_index].groups:
        if assignment.weight <= 0:
            continue
        group = obj.vertex_groups[assignment.group]
        if group.name not in bone_nodes:
            continue
        node = bone_nodes[group.name]
        pairs[node] = pairs.get(node, 0.0) + float(assignment.weight)
    if not pairs:
        raise ValueError("%s: vertex %d has no mapped skin weights" % (obj.name, vertex_index))
    if len(pairs) > 8:
        raise ValueError("%s: vertex %d uses more than eight skin bones" % (obj.name, vertex_index))
    total = sum(pairs.values())
    if not math.isfinite(total) or total <= 0:
        raise ValueError("%s: vertex %d has invalid skin weights" % (obj.name, vertex_index))
    return [(node, weight / total) for node, weight in sorted(pairs.items())]


def pspCornerColor(mesh, loop_index):
    attributes = getattr(mesh, 'color_attributes', None)
    attribute = attributes.active_color if attributes is not None else None
    if attribute is None:
        return (255, 255, 255, 255)
    index = loop_index if attribute.domain == 'CORNER' else mesh.loops[loop_index].vertex_index
    value = attribute.data[index]
    color = value.color
    return tuple(max(0, min(255, round(float(channel) * 255.0))) for channel in color)


def getPspExportMesh(context, obj):
    modifiers = [modifier for modifier in obj.modifiers if modifier.type == 'ARMATURE']
    states = [modifier.show_viewport for modifier in modifiers]
    if not any(modifier.show_viewport and modifier.type != 'ARMATURE' for modifier in obj.modifiers):
        return obj.data, None
    try:
        for modifier in modifiers:
            modifier.show_viewport = False
        context.view_layer.update()
        graph = context.evaluated_depsgraph_get()
        evaluated = obj.evaluated_get(graph)
        mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
        return mesh, evaluated
    finally:
        for modifier, state in zip(modifiers, states):
            modifier.show_viewport = state
        context.view_layer.update()


def collectPspStrips(context, obj, root, export_matrix, bone_nodes, skinned, use_normals):
    mesh, evaluated_owner = getPspExportMesh(context, obj)
    if mesh is None:
        raise ValueError("%s has no mesh data" % obj.name)
    try:
        mesh.calc_loop_triangles()
        mesh.calc_normals_split()
        uv_layer = mesh.uv_layers.active
        has_colors = bool(getattr(mesh, 'color_attributes', None) and mesh.color_attributes.active_color)
        normal_matrix = export_matrix.to_3x3().inverted_safe().transposed()
        reversed_winding = export_matrix.to_3x3().determinant() < 0
        materials = []
        material_slots = {}
        strips = []
        current = None
        current_bones = set()
        native_strip = len(mesh.polygons) == len(mesh.vertices) - 2 and len(mesh.vertices) >= 3
        if native_strip:
            for index, polygon in enumerate(mesh.polygons, 2):
                expected = (index - 2, index - 1, index) if index % 2 == 0 else (index - 1, index - 2, index)
                if tuple(polygon.vertices) != expected or polygon.material_index != mesh.polygons[0].material_index:
                    native_strip = False
                    break
        if native_strip and not reversed_winding:
            loops_by_vertex = [[] for vertex in mesh.vertices]
            for loop in mesh.loops:
                loops_by_vertex[loop.vertex_index].append(loop.index)
            vertices = []
            palette = set()
            for vertex in mesh.vertices:
                loops = loops_by_vertex[vertex.index]
                if not loops:
                    native_strip = False
                    break
                loop_index = loops[0]
                uv = tuple(uv_layer.data[loop_index].uv) if uv_layer else (0.0, 0.0)
                normal = mesh.loops[loop_index].normal
                color = pspCornerColor(mesh, loop_index)
                if any((uv_layer and (uv_layer.data[other].uv - Vector(uv)).length > 1e-7) or
                       (use_normals and (mesh.loops[other].normal - normal).length > 1e-6) or
                       (has_colors and pspCornerColor(mesh, other) != color) for other in loops):
                    native_strip = False
                    break
                weights = pspVertexWeights(obj, mesh, vertex.index, bone_nodes) if skinned else []
                palette.update(node for node, weight in weights if weight > 0)
                position = export_matrix @ vertex.co
                vertices.append({'position': tuple(position), 'normal': tuple((normal_matrix @ normal).normalized()),
                                 'uv': uv, 'color': color, 'weights': weights})
            if native_strip and len(palette) <= 8 and len(vertices) <= 65537:
                material_index = mesh.polygons[0].material_index
                material = mesh.materials[material_index] if material_index < len(mesh.materials) else None
                strip = {'material': 0, 'vertices': vertices, 'has_uv': uv_layer is not None,
                         'has_colors': has_colors, 'has_normals': bool(use_normals)}
                return [strip], [material]
        for triangle in mesh.loop_triangles:
            material_index = int(triangle.material_index)
            if material_index not in material_slots:
                material_slots[material_index] = len(materials)
                material = mesh.materials[material_index] if material_index < len(mesh.materials) else None
                materials.append(material)
            loops = list(triangle.loops)
            if reversed_winding:
                loops.reverse()
            vertices = []
            triangle_bones = set()
            for loop_index in loops:
                vertex_index = mesh.loops[loop_index].vertex_index
                position = export_matrix @ mesh.vertices[vertex_index].co
                normal = normal_matrix @ mesh.loops[loop_index].normal
                uv = tuple(float(value) for value in uv_layer.data[loop_index].uv) if uv_layer else (0.0, 0.0)
                weights = pspVertexWeights(obj, mesh, vertex_index, bone_nodes) if skinned else []
                triangle_bones.update(node for node, weight in weights if weight > 0)
                record = {'position': tuple(position), 'normal': tuple(normal.normalized()), 'uv': uv,
                          'color': pspCornerColor(mesh, loop_index), 'weights': weights}
                if not all(math.isfinite(value) for value in record['position'] + record['normal'] + uv):
                    raise ValueError("%s contains non-finite vertex data" % obj.name)
                vertices.append(record)
            if len(triangle_bones) > 8:
                raise ValueError("%s: triangle %d uses more than eight skin bones" % (obj.name, triangle.index))
            output_material = material_slots[material_index]
            if (current is None or current['material'] != output_material or
                    len(current_bones | triangle_bones) > 8 or len(current['vertices']) + 6 > 65537):
                current = {'material': output_material, 'vertices': [], 'has_uv': uv_layer is not None,
                           'has_colors': has_colors, 'has_normals': bool(use_normals)}
                strips.append(current)
                current_bones = set()
            if current['vertices']:
                previous_count = len(current['vertices'])
                current['vertices'].extend((current['vertices'][-1], vertices[0], vertices[0]))
                if (previous_count + 3) % 2:
                    current['vertices'].append(vertices[0])
            current['vertices'].extend(vertices)
            current_bones.update(triangle_bones)
        if not strips:
            raise ValueError("%s has no triangles to export" % obj.name)
        return strips, materials
    finally:
        mdl_exporter.clearEvaluatedMeshForMdlExport(evaluated_owner)


def appendPspAtomic(resource, frame, geometry, clump, hierarchy, model_id, visibility, game, skinned, kind):
    offset = resource.reserve(0x34, 16)
    identifier = 0x01050001 if game == 'LCS' else 0x0004F301 if skinned else 0x00041601
    if game == 'VCS' and kind == 'VEH':
        identifier = 0x00041901
    struct.pack_into("<I", resource.data, offset, identifier)
    resource.pointer(offset + 4, frame)
    resource.pointer(offset + 20, geometry)
    resource.pointer(offset + 24, clump)
    resource.pointer(offset + 44, hierarchy)
    callback = 0x12 if skinned else 1 if kind == 'VEH' else 0
    struct.pack_into("<IHH", resource.data, offset + 36, callback,
                     int(model_id) & 65535, int(visibility) & 65535)
    return offset


def linkPspAtomics(resource, atomics, frames, clump, extras):
    by_frame = {}
    regular = [offset for offset in atomics if offset not in extras]
    if clump:
        head = clump + 8
        resource.pointer(head, regular[0] + 28 if regular else head)
        resource.pointer(head + 4, regular[-1] + 28 if regular else head)
        for index, offset in enumerate(regular):
            resource.pointer(offset + 28, regular[index + 1] + 28 if index + 1 < len(regular) else head)
            resource.pointer(offset + 32, regular[index - 1] + 28 if index else head)
    for offset in atomics:
        frame = struct.unpack_from("<I", resource.data, offset + 4)[0]
        by_frame.setdefault(frame, []).append(offset)
        if offset in extras:
            resource.pointer(offset + 24, 0)
            resource.pointer(offset + 28, 0)
            resource.pointer(offset + 32, 0)
    for frame in frames.values():
        head = frame + 8
        attached = by_frame.get(frame, [])
        resource.pointer(head, attached[0] + 8 if attached else head)
        resource.pointer(head + 4, attached[-1] + 8 if attached else head)
        for index, offset in enumerate(attached):
            resource.pointer(offset + 8, attached[index + 1] + 8 if index + 1 < len(attached) else head)
            resource.pointer(offset + 12, attached[index - 1] + 8 if index else head)


def pspMaterialColor(material):
    if material is None:
        return 0xFFFFFFFF
    raw = material.get('bleeds_mdl_material_rgba_hex')
    original = int(str(raw), 16) if raw else None
    color = tuple(material.diffuse_color)
    if material.use_nodes and material.node_tree:
        shader = next((node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED'), None)
        if shader is not None:
            color = tuple(shader.inputs['Base Color'].default_value)
    if original is not None:
        expected = tuple(((original >> (channel * 8)) & 255) / 255.0 for channel in range(4))
        if original == 0:
            expected = (0.0, 0.0, 0.0, 1.0)
        if max(abs(color[channel] - expected[channel]) for channel in range(4)) < 1e-6:
            return original
    values = [max(0, min(255, round(float(channel) * 255.0))) for channel in color]
    return sum(value << (channel * 8) for channel, value in enumerate(values))


def exportPspMdl(context, filepath, mdl_type='SIM', use_normals=True, export_game='VCS'):
    root = mdl_exporter.find_mdl_root(context)
    kind = str(mdl_type).upper()
    game = str(export_game).upper()
    if kind not in {'SIM', 'PED', 'CUT', 'VEH'} or game not in {'LCS', 'VCS'}:
        raise ValueError("Choose LCS or VCS and a supported model type")
    meshes = [obj for obj in root.children_recursive if obj.type == 'MESH']
    meshes.sort(key=lambda obj: mdl_exporter.natural_sort_key(obj.name))
    if not meshes:
        raise ValueError("No mesh parts found under the model root")
    armatures = {modifier.object for obj in meshes for modifier in obj.modifiers
                 if modifier.type == 'ARMATURE' and modifier.object is not None}
    if len(armatures) > 1:
        raise ValueError("A PSP model must use one skin armature")
    armature = next(iter(armatures), None)
    skinned = armature is not None and kind in {'PED', 'CUT'}
    source_context = None
    source = None
    source_path = str(root.get('bleeds_mdl_source_filepath', root.get('bleeds_mdl_filepath', '')))
    candidate = None
    if source_path and os.path.isfile(source_path):
        with open(source_path, 'rb') as source_file:
            candidate = source_file.read()
    elif root.get('bleeds_psp_source_metadata'):
        candidate = zlib.decompress(base64.b64decode(root['bleeds_psp_source_metadata']))
    if candidate is not None:
        probe = mdl.probeStoriesResourceHeader(candidate)
        if probe and probe['platform'] == 'PSP' and probe['mdl_type_hint'] == kind:
            source = candidate
            source_context = mdl.read_stories(source_path, 'PSP', kind, game=game, data=source).read()
    if source is None and root.get('bleeds_mdl_detected_platform') == 'PSP' and kind == root.get('bleeds_mdl_detected_type'):
        raise ValueError("The original PSP model data is missing. Import the source MDL again to retain its collision and vehicle data.")
    resource = PspResource(source)
    if source_context is None and kind == 'VEH':
        resource.data.extend(bytes(0xF4 - len(resource.data)))
    records, bone_nodes, animation_records = collectPspFrames(root, armature if skinned else None, source_context)
    frames, hierarchy, skin = appendPspFrames(resource, records, skinned, game, animation_records)
    root_frame = frames[records[0]['key']]
    frame_by_pointer = {record['source_pointer']: frames[record['key']] for record in records if record['source_pointer']}
    world_by_frame = {frames[record['key']]: record['world'] for record in records}
    if source is not None:
        for field in list(resource.relocations):
            value = struct.unpack_from('<I', resource.data, field)[0]
            if value in frame_by_pointer:
                resource.pointer(field, frame_by_pointer[value])
    clump = 0
    if kind != 'SIM':
        clump = source_context.clump_ptr if source_context is not None else resource.reserve(16)
        struct.pack_into("<I", resource.data, clump, 2)
        resource.pointer(clump + 4, root_frame)
    if source_context is None:
        resource.pointer(0x20, clump)
    elif source_context.clump_ptr:
        probe = mdl.probeStoriesResourceHeader(source)
        if probe['pointer_offset'] != clump:
            resource.pointer(probe['pointer_offset'], clump)
    source_atomics = {atomic.atomic_offset: atomic for atomic in (source_context.atomics or [source_context.atomic])} if source_context else {}
    grouped = {}
    for obj in meshes:
        original = int(obj.get('bleeds_mdl_atomic_offset', 0))
        key = original if original in source_atomics else 0 if kind in {'SIM', 'PED'} else obj.name
        has_skin = skinned and any(modifier.type == 'ARMATURE' and modifier.object == armature for modifier in obj.modifiers)
        grouped.setdefault((key, has_skin), []).append(obj)
    atomics = []
    extras = []
    material_cache = {}
    material_replacements = {}
    reused_atomics = set()
    for (key, atomic_skinned), objects in grouped.items():
        original = source_atomics.get(key)
        frame = frame_by_pointer.get(original.frame_ptr, root_frame) if original else root_frame
        if kind in {'VEH', 'CUT'}:
            parent = objects[0].parent
            while parent is not None and parent != root:
                pointer = int(parent.get('bleeds_frame_ptr', 0))
                if pointer in frame_by_pointer:
                    frame = frame_by_pointer[pointer]
                    break
                custom_key = 'frame:' + parent.name
                if custom_key in frames:
                    frame = frames[custom_key]
                    break
                parent = parent.parent
        strips = []
        materials = []
        for obj in objects:
            export_matrix = world_by_frame[frame].inverted_safe() @ root.matrix_world.inverted_safe() @ obj.matrix_world
            part_strips, part_materials = collectPspStrips(context, obj, root, export_matrix, bone_nodes, atomic_skinned, use_normals)
            for strip in part_strips:
                strip['material'] += len(materials)
            strips.extend(part_strips)
            materials.extend(part_materials)
        material_offsets = []
        for material in materials:
            material_key = material.as_pointer() if material is not None else 0
            if material_key in material_cache:
                material_offsets.append(material_cache[material_key])
                continue
            name = mdl_exporter.resolve_texture_name(material) if material is not None else ''
            has_image = bool(material is not None and material.use_nodes and material.node_tree and
                             any(node.type == 'TEX_IMAGE' and node.image is not None for node in material.node_tree.nodes))
            if material is not None and not has_image and 'bleeds_mdl_texture_name' in material:
                name = str(material['bleeds_mdl_texture_name'])
            if len(name.encode('ascii', 'replace')) > 31:
                raise ValueError("PSP texture names must be at most 31 characters: %s" % name)
            rgba = pspMaterialColor(material)
            source_entry = int(material.get('bleeds_mdl_material_entry_offset', 0)) if material is not None else 0
            source_material = struct.unpack_from('<I', source, source_entry)[0] if source and source_entry else 0
            material_offset = resource.material(name, rgba, source_material if source else 0)
            material_offsets.append(material_offset)
            material_cache[material_key] = material_offset
            if source_material:
                material_replacements[source_material] = material_offset
        geometry = resource.geometry(strips, material_offsets, skin if atomic_skinned else 0)
        if original is not None and original.atomic_offset not in reused_atomics:
            offset = original.atomic_offset
            reused_atomics.add(offset)
            resource.pointer(offset + 4, frame)
            resource.pointer(offset + 20, geometry)
            resource.pointer(offset + 24, clump)
            resource.pointer(offset + 44, hierarchy if atomic_skinned else 0)
        else:
            model_id = int(root.get('bleeds_mdl_model_info_id', -1))
            visibility = int(objects[0].get('bleeds_mdl_vis_id_flag', root.get('bleeds_mdl_vis_id_flag', 0)))
            offset = appendPspAtomic(resource, frame, geometry, clump, hierarchy if atomic_skinned else 0,
                                     model_id, visibility, game, atomic_skinned, kind)
        atomics.append(offset)
        if (original is not None and original.atomic_source.startswith('extra')) or any(obj.get('bleeds_mdl_vehicle_extra', False) for obj in objects):
            extras.append(offset)
    if kind == 'SIM':
        if len(atomics) != 1:
            raise ValueError("SimpleModel export must contain one Atomic")
        resource.pointer(0x20, atomics[0])
        model_id = int(root.get('bleeds_mdl_model_info_id', -1))
        struct.pack_into('<H', resource.data, atomics[0] + 0x28, model_id & 65535)
        if 'bleeds_mdl_atomic_hash_key' in root or source_context is None:
            hash_key = int(root.get('bleeds_mdl_atomic_hash_key', 0)) & 0xFFFFFFFF
            struct.pack_into("<II", resource.data, atomics[0] + 28, hash_key, hash_key)
    if kind == 'VEH':
        if source_context is not None:
            for field in range(0x2C, 0xF4, 4):
                old_material = struct.unpack_from('<I', source, field)[0]
                if old_material in material_replacements:
                    resource.pointer(field, material_replacements[old_material])
        extra_array = resource.reserve(4 * len(extras)) if extras else 0
        struct.pack_into("<I", resource.data, 0x24, len(extras))
        resource.pointer(0x28, extra_array)
        for index, atomic in enumerate(extras):
            resource.pointer(extra_array + index * 4, atomic)
    linkPspAtomics(resource, atomics, frames, clump, extras)
    payload = resource.finish(atomics[0])
    with open(filepath, 'wb') as output:
        output.write(payload)
    return {'atomics': len(atomics), 'frames': len(records), 'meshes': len(meshes), 'bytes': len(payload)}
