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

from .mesh_compat import objectChildren, meshColorLayer
from .object_types import isModelMesh, isObjectExportable
from contextlib import contextmanager
import base64
import json
import math
import struct
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

from ..rwLib.dff import readDff, writeDff
from ..leedsLib.native_mobile import writeAtomic


def frameMatrix(values):
    return Matrix(((values[0], values[3], values[6], values[9]),
                   (values[1], values[4], values[7], values[10]),
                   (values[2], values[5], values[8], values[11]),
                   (0.0, 0.0, 0.0, 1.0)))


def flattenMatrix(matrix):
    return [float(value) for row in matrix for value in row]


def importTextures(path, platform='AUTO'):
    from ..rwLib.dff import unwrapResource
    raw = Path(path).read_bytes()
    if unwrapResource(raw)[:4] == b'TCDT':
        from .tex_importer import importTextures as importMh2Textures
        return importMh2Textures(path, platform)
    from ..rwLib.txd import openTextures
    dictionary = openTextures(raw)
    images = {}
    try:
        for texture in dictionary.textures:
            pixels = dictionary.pixels(texture)
            image = bpy.data.images.new(texture.name, texture.width, texture.height, alpha=True)
            images[texture.name.casefold()] = image
            image.pixels.foreach_set((pixels[::-1].astype('float32') / 255.0).ravel())
            image.pack()
            image['bleeds_mobile_txd'] = str(Path(path).resolve())
            image['bleeds_mobile_texture'] = texture.name
            image['bleeds_txd_platform'] = getattr(texture, 'platform', 'Mobile')
            image['bleeds_txd_format'] = getattr(texture, 'format', '%d-bit' % texture.depth)
            image['bleeds_txd_levels'] = texture.mip_count
    except Exception:
        for image in images.values():
            bpy.data.images.remove(image, do_unlink=True)
        raise
    return images


def importDffData(context, path, source='MOBILE', import_textures=True):
    from ..rwLib.dff import unwrapResource
    raw = Path(path).read_bytes()
    if unwrapResource(raw)[:4] == b'PMLC':
        from .mdl_importer import importModel
        platform = {'MH2_PS2':'PS2', 'MH2_PSP':'PSP'}.get(source, 'AUTO')
        return importModel(context, path, platform, import_textures=import_textures)
    if source.startswith('MH2'):
        raise ValueError('Expected a Manhunt 2 PMLC model container')
    if context.object is not None and context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    clumps = readDff(raw, source)
    collection = bpy.data.collections.new(Path(path).stem)
    context.scene.collection.children.link(collection)
    root = bpy.data.objects.new(Path(path).stem, None)
    collection.objects.link(root)
    root['bleeds_dff_source'] = base64.b64encode(raw).decode('ascii')
    native_mobile = any(atomic['geometry'].version == 0xF00D for clump in clumps for atomic in clump['atomics'])
    root['bleeds_dff_profile'] = 'MOBILE' if native_mobile else ('BETA' if source == 'BETA' else 'RENDERWARE')
    if native_mobile or source == 'BETA':
        root['bleeds_model_game'] = 'LCS'
    root['bleeds_dff_version'] = clumps[0]['root'].version if clumps else 0
    root['bleeds_dff_frame_count'] = sum(len(clump['frames']) for clump in clumps)
    root['bleeds_dff_mesh_count'] = sum(len(clump['atomics']) for clump in clumps)
    root['bleeds_dff_bone_count'] = sum(sum(frame['bone_id'] is not None and frame['bone_id'] >= 0 for frame in clump['frames']) for clump in clumps)
    root['bleeds_dff_path'] = str(Path(path).resolve())
    images = {}
    sidecars = [p for p in Path(path).parent.iterdir()
                if p.stem.casefold() == Path(path).stem.casefold() and p.suffix.casefold() == '.txd']
    if import_textures and sidecars:
        try:
            images = importTextures(sidecars[0])
        except (ValueError, OSError) as exc:
            print('BLeeds: could not load matching textures: %s' % exc)
    created = [root]
    for clump_index, clump in enumerate(clumps):
        frames = clump['frames']
        world = dffFrameWorldMatrices(frames)
        armature = None
        bones = {}
        if any(frame['bone_id'] is not None and frame['bone_id'] >= 0 for frame in frames):
            data = bpy.data.armatures.new(root.name + '_bones')
            armature = bpy.data.objects.new(root.name + '_bones', data)
            collection.objects.link(armature)
            armature.parent = root
            if native_mobile or source == 'BETA':
                armature['bleeds_model_game'] = 'LCS'
            armature['bleeds_mdl_frame_ptrs'] = [frame['index'] + 1 for frame in frames]
            armature['bleeds_mdl_frame_names'] = [frame['name'] for frame in frames]
            armature['bleeds_mdl_frame_local_matrices'] = [value for frame in frames for value in flattenMatrix(frameMatrix(frame['values']))]
            bpy.ops.object.select_all(action='DESELECT')
            armature.select_set(True)
            context.view_layer.objects.active = armature
            bpy.ops.object.mode_set(mode='EDIT')
            for frame in frames:
                if frame['bone_id'] is None or frame['bone_id'] < 0:
                    continue
                bone = data.edit_bones.new(frame['name'])
                bone.matrix = world[frame['index']]
                bone.length = 0.05
                bones[frame['index']] = bone.name
            for frame in frames:
                if frame['index'] not in bones:
                    continue
                parent = frame['parent']
                while parent >= 0 and parent not in bones:
                    parent = frames[parent]['parent']
                if parent >= 0:
                    data.edit_bones[bones[frame['index']]].parent = data.edit_bones[bones[parent]]
            bpy.ops.object.mode_set(mode='OBJECT')
            for frame in frames:
                if frame['index'] not in bones:
                    continue
                bone = data.bones[bones[frame['index']]]
                bone['bone_id'] = frame['bone_id']
                bone['bleeds_anim_bone_id'] = frame['bone_id']
                parent = frame['parent']
                while parent >= 0 and parent not in bones:
                    parent = frames[parent]['parent']
                source_local = world[parent].inverted() @ world[frame['index']] if parent >= 0 else world[frame['index']]
                bone['bleeds_mdl_import_local_matrix'] = flattenMatrix(source_local)
                bone['bleeds_mdl_import_global_matrix'] = flattenMatrix(world[frame['index']])
                blender_local = bone.parent.matrix_local.inverted() @ bone.matrix_local if bone.parent else bone.matrix_local
                bone['bleeds_blender_import_local_matrix'] = flattenMatrix(blender_local)
            created.append(armature)
        frame_objects = {}
        for frame in frames:
            if frame['index'] in bones:
                continue
            helper = bpy.data.objects.new(frame['name'], None)
            collection.objects.link(helper)
            helper.parent = root
            helper.matrix_world = root.matrix_world @ world[frame['index']]
            helper['bleeds_dff_frame'] = frame['index']
            helper['bleeds_dff_clump'] = clump_index
            frame_objects[frame['index']] = helper
            created.append(helper)
        for frame in frames:
            helper = frame_objects.get(frame['index'])
            if helper is not None and frame['parent'] in frame_objects:
                matrix = helper.matrix_world.copy()
                helper.parent = frame_objects[frame['parent']]
                helper.matrix_world = matrix
        for atomic_index, atomic in enumerate(clump['atomics']):
            materials = []
            for index, entry in enumerate(atomic['materials']):
                material = bpy.data.materials.new(entry['name'] or 'material_%d' % index)
                material.diffuse_color = tuple(channel / 255.0 for channel in entry['color'])
                material.use_nodes = True
                shader = material.node_tree.nodes.get('Principled BSDF')
                shader.inputs['Base Color'].default_value = material.diffuse_color
                shader.inputs['Alpha'].default_value = material.diffuse_color[3]
                material['bleeds_texture_name'] = entry['name']
                material['bleeds_dff_material_index'] = index
                image = images.get(entry['name'].casefold())
                if image is not None:
                    node = material.node_tree.nodes.new('ShaderNodeTexImage')
                    node.image = image
                    material.node_tree.links.new(node.outputs['Color'], shader.inputs['Base Color'])
                    material.node_tree.links.new(node.outputs['Alpha'], shader.inputs['Alpha'])
                materials.append(material)
            for part_index, part in enumerate(atomic['parts']):
                mesh = bpy.data.meshes.new('%s_%d_%d' % (root.name, atomic_index, part_index))
                mesh.from_pydata(part['vertices'], [], part['faces'])
                mesh.update()
                obj = bpy.data.objects.new(mesh.name, mesh)
                collection.objects.link(obj)
                obj.parent = frame_objects.get(atomic['frame'], root)
                obj.matrix_world = root.matrix_world @ world[atomic['frame']]
                obj['bleeds_dff_geometry_version'] = atomic['geometry'].version
                obj['bleeds_dff_frame_name'] = frames[atomic['frame']]['name']
                obj['bleeds_dff_part'] = [clump_index, atomic_index, part_index]
                obj['bleeds_dff_original_uvs'] = json.dumps(part['uvs'])
                obj['bleeds_dff_original_matrix'] = flattenMatrix(obj.matrix_local)
                for material in materials:
                    mesh.materials.append(material)
                source_materials = part.get('face_materials')
                material_indices = (np.asarray(source_materials, dtype=np.int32) if source_materials
                                    else np.full(len(mesh.polygons), part['material'], dtype=np.int32))
                mesh.polygons.foreach_set('material_index', material_indices)
                loop_vertices = np.empty(len(mesh.loops), dtype=np.int32)
                mesh.loops.foreach_get('vertex_index', loop_vertices)
                for uv_index, coordinates in enumerate(part.get('uv_sets', [part['uvs']])):
                    if not coordinates:
                        continue
                    layer = mesh.uv_layers.new(name='UVMap' if uv_index == 0 else 'UVMap.%03d' % uv_index)
                    uv_values = np.asarray(coordinates, dtype=np.float32)[loop_vertices].copy()
                    uv_values[:, 1] = 1.0 - uv_values[:, 1]
                    layer.data.foreach_set('uv', uv_values.ravel())
                if mesh.uv_layers:
                    mesh.uv_layers.active_index = 0
                if part['normals'] and len(part['normals']) == len(mesh.vertices):
                    mesh.normals_split_custom_set_from_vertices(part['normals'])
                    if hasattr(mesh, 'use_auto_smooth'):
                        mesh.use_auto_smooth = True
                if part['colors'] and len(part['colors']) == len(mesh.vertices):
                    if hasattr(mesh, 'color_attributes'):
                        color_layer = mesh.color_attributes.new(name='Color', type='BYTE_COLOR', domain='POINT')
                        color_values = np.asarray(part['colors'], dtype=np.float32) / 255.0
                        color_layer.data.foreach_set('color', color_values.ravel())
                    else:
                        color_layer = mesh.vertex_colors.new(name='Color')
                        color_values = np.asarray(part['colors'], dtype=np.float32)[loop_vertices] / 255.0
                        color_layer.data.foreach_set('color', color_values.ravel())
                native_part = part.get('source')
                by_skin_index = {}
                if armature and (native_part or part.get('weights')):
                    by_skin_index = {frame['skin_index']: bones[frame['index']] for frame in frames
                                     if frame['index'] in bones and frame['skin_index'] is not None}
                    groups = {}
                    weights_by_vertex = {}
                    source_weights = list(enumerate(part.get('weights', [])))
                    if native_part:
                        source_weights = [(strip.base_vertex_index + index, list(zip(indices, weights)))
                                          for strip in native_part.strips_meta
                                          for index, (indices, weights) in enumerate(zip(strip.skin_indices, strip.skin_weights))]
                    for vertex_index, influences in source_weights:
                        if vertex_index < 0 or vertex_index >= len(mesh.vertices):
                            raise ValueError('A skeleton weight refers to a missing mesh vertex')
                        accumulated = weights_by_vertex.setdefault(vertex_index, {})
                        for bone_index, weight in influences:
                            if not math.isfinite(float(weight)) or weight <= 0.0:
                                continue
                            name = by_skin_index.get(bone_index)
                            if name is None:
                                raise ValueError('The mesh refers to an unknown skeleton bone: %d' % bone_index)
                            accumulated[name] = accumulated.get(name, 0.0) + float(weight)
                    for vertex_index, influences in weights_by_vertex.items():
                        total_weight = sum(influences.values())
                        if not math.isfinite(total_weight) or total_weight <= 0.0:
                            continue
                        for name, weight in influences.items():
                            if name not in groups:
                                groups[name] = obj.vertex_groups.new(name=name)
                            groups[name].add([vertex_index], weight / total_weight, 'REPLACE')
                    if groups:
                        modifier = obj.modifiers.new('Armature', 'ARMATURE')
                        modifier.object = armature
                obj['bleeds_dff_skin_indices'] = json.dumps({name: index for index, name in by_skin_index.items()} if armature else {})
                obj['bleeds_dff_original_weights'] = json.dumps([[ [group.group, group.weight] for group in vertex.groups] for vertex in mesh.vertices])
                obj['bleeds_dff_original_materials'] = [polygon.material_index for polygon in mesh.polygons]
                created.append(obj)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in created:
        obj.select_set(True)
    context.view_layer.objects.active = next((obj for obj in created if obj.type == 'ARMATURE'), root)
    return created


def importDff(context, path, source='AUTO', import_textures=True):
    # Remove anything this import created if the file fails partway through.
    collections = ('objects', 'meshes', 'armatures', 'materials', 'images', 'collections')
    before = {name: set(getattr(bpy.data, name)) for name in collections}
    active = context.view_layer.objects.active
    selected = list(context.selected_objects)
    try:
        return importDffData(context, path, source, import_textures)
    except Exception:
        if context.object is not None and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for name in collections:
            data = getattr(bpy.data, name)
            for item in list(data):
                if item not in before[name]:
                    data.remove(item, do_unlink=True)
        for obj in selected:
            if obj.name in context.view_layer.objects:
                obj.select_set(True)
        if active is not None and active.name in context.view_layer.objects:
            context.view_layer.objects.active = active
        raise


def findDffRoot(obj):
    while obj is not None and 'bleeds_dff_source' not in obj:
        obj = obj.parent
    return obj


def dffFrameWorldMatrices(frames):
    matrices = {}
    for start in range(len(frames)):
        chain = []
        visiting = set()
        index = start
        while index not in matrices:
            if index < 0 or index >= len(frames):
                raise ValueError('Mobile frame hierarchy refers to an invalid parent index')
            if index in visiting:
                raise ValueError('Mobile frame hierarchy contains a parent cycle')
            visiting.add(index)
            chain.append(index)
            parent = frames[index]['parent']
            if parent == -1:
                break
            index = parent
        for index in reversed(chain):
            frame = frames[index]
            local = frameMatrix(frame['values'])
            matrices[index] = matrices[frame['parent']] @ local if frame['parent'] >= 0 else local
    return matrices


def materialDescription(material, source_index):
    if material is None:
        return dict(color=(1.0, 1.0, 1.0, 1.0), texture='', source_index=source_index)
    color = tuple(material.diffuse_color)
    texture = next((str(material[key]) for key in ('bleeds_texture_name', 'bleeds_mh2_texture_name',
                    'bleeds_mdl_texture_name', 'bleeds_material_texture_name') if key in material), '')
    if material.use_nodes and material.node_tree:
        shader = next((node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED'), None)
        if shader:
            color = tuple(shader.inputs['Base Color'].default_value)
            if 'Alpha' in shader.inputs:
                alpha = float(shader.inputs['Alpha'].default_value)
                color = color[:3] + ((alpha if alpha != 1.0 else color[3]),)
            links = shader.inputs['Base Color'].links
            image_node = next((link.from_node for link in links if link.from_node.type == 'TEX_IMAGE'), None)
            if image_node and image_node.image:
                image = image_node.image
                texture = str(image.get('bleeds_mobile_texture', '') or image.get('bleeds_texture_name', '') or Path(image.name).stem)
    return dict(color=color, texture=texture, source_index=source_index)


@contextmanager
def mobileExportMesh(context, obj):
    # Export the visible mesh changes without applying the current skeleton pose.
    if not any(modifier.show_viewport and modifier.type != 'ARMATURE' for modifier in obj.modifiers):
        yield obj.data
        return
    states = [(modifier, modifier.show_viewport) for modifier in obj.modifiers if modifier.type == 'ARMATURE']
    temporary = None
    evaluated = None
    try:
        for modifier, state in states:
            modifier.show_viewport = False
        context.view_layer.update()
        graph = context.evaluated_depsgraph_get()
        evaluated = obj.evaluated_get(graph)
        temporary = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=graph).copy()
        evaluated.to_mesh_clear()
        evaluated = None
        yield temporary
    finally:
        if evaluated is not None:
            evaluated.to_mesh_clear()
        if temporary is not None:
            bpy.data.meshes.remove(temporary)
        for modifier, state in states:
            modifier.show_viewport = state
        context.view_layer.update()


def updateMobileFrames(context, root, clumps):
    # Save edits to the named model frames as well as edits to the meshes.
    context.view_layer.update()
    inverse = root.matrix_world.inverted()
    helpers = {}
    for obj in objectChildren(root):
        if obj.get('bleeds_dff_frame') is not None and obj.get('bleeds_dff_clump') is not None:
            key = (int(obj['bleeds_dff_clump']), int(obj['bleeds_dff_frame']))
            if key in helpers:
                raise ValueError('More than one object uses the same model frame: ' + obj.name)
            helpers[key] = obj
    for clump_index, clump in enumerate(clumps):
        frames = clump['frames']
        worlds = dffFrameWorldMatrices(frames)
        for frame in frames:
            helper = helpers.get((clump_index, frame['index']))
            if helper is not None:
                worlds[frame['index']] = inverse @ helper.matrix_world
        frame_list = next(section for section in clump['sections'] if section.type_id == 0xE)
        structure = next(section for section in frame_list.children() if section.type_id == 1)
        data = bytearray(structure.payload)
        for frame in frames:
            if (clump_index, frame['index']) not in helpers:
                continue
            parent = frame['parent']
            matrix = worlds[parent].inverted() @ worlds[frame['index']] if parent >= 0 else worlds[frame['index']]
            frame['values'] = mobileFrameValues(matrix)
            struct.pack_into('<12f', data, 4 + frame['index'] * 56, *frame['values'])
        structure.payload = bytes(data)
        frame_list.payload = b''.join(child.toBytes() for child in frame_list.children())


def collectMobileSurfaces(context, root, clump_index, atomic_index, clump, atomic, objects):
    from ..rwLib.native_mobile_dff import MobileVertex
    frames = clump['frames']
    frames_world = dffFrameWorldMatrices(frames)
    geometry_world = root.matrix_world @ frames_world[atomic['frame']]
    armatures = [obj for obj in objectChildren(root) if obj.type == 'ARMATURE']
    bone_names = {}
    for frame in frames:
        if frame['skin_index'] is not None:
            bone_names[frame['name']] = frame['skin_index']
    for armature in armatures:
        for bone in armature.data.bones:
            bone_id = bone.get('bleeds_anim_bone_id', bone.get('bone_id'))
            matches = [frame for frame in frames if frame['bone_id'] == bone_id and frame['skin_index'] is not None]
            if len(matches) == 1:
                bone_names[bone.name] = matches[0]['skin_index']
    skinned = bool(atomic.get('skinned')) or any(weight > 0.0 for part in atomic['parts'] if part.get('source') for strip in part['source'].strips_meta
                  for weights in strip.skin_weights for weight in weights)
    surfaces = {}
    descriptions = []
    material_ids = {}
    for obj in objects:
        with mobileExportMesh(context, obj) as mesh:
            mesh.calc_loop_triangles()
            if hasattr(mesh, 'calc_normals_split'):
                mesh.calc_normals_split()
            transform = geometry_world.inverted() @ obj.matrix_world
            normal_transform = transform.to_3x3().inverted().transposed()
            reverse_winding = transform.to_3x3().determinant() < 0.0
            uv_layer = mesh.uv_layers.active
            color_layer = meshColorLayer(mesh)
            source_part = int(obj.get('bleeds_dff_part', (clump_index, atomic_index, 0))[2])
            mapping = dict(bone_names)
            if not atomic.get('converted'):
                mapping.update(json.loads(obj.get('bleeds_dff_skin_indices', '{}')))
            weights = {}
            for vertex in mesh.vertices:
                influences = []
                if skinned:
                    for group in vertex.groups:
                        if group.weight <= 0.0:
                            continue
                        name = obj.vertex_groups[group.group].name
                        if name not in mapping:
                            continue
                        influences.append((int(mapping[name]), float(group.weight)))
                    if not influences:
                        raise ValueError('%s: vertex %d has no skeleton weights' % (obj.name, vertex.index))
                    if len(influences) > 4:
                        raise ValueError('%s: vertex %d has more than four skeleton weights' % (obj.name, vertex.index))
                    total = sum(weight for bone, weight in influences)
                    influences = [(bone, weight / total) for bone, weight in sorted(influences)]
                weights[vertex.index] = tuple(influences)
            for triangle in mesh.loop_triangles:
                slot = triangle.material_index
                material = obj.material_slots[slot].material if slot < len(obj.material_slots) else None
                key = material.as_pointer() if material is not None else None
                if key not in material_ids:
                    source_index = int(material.get('bleeds_dff_material_index', slot)) if material else slot
                    material_ids[key] = len(descriptions)
                    descriptions.append(materialDescription(material, source_index))
                material_index = material_ids[key]
                surface_key = (source_part, material_index)
                surface = surfaces.setdefault(surface_key, dict(source_part=source_part, material=material_index, triangles=[]))
                corners = []
                for loop_index in triangle.loops:
                    loop = mesh.loops[loop_index]
                    vertex = mesh.vertices[loop.vertex_index]
                    position = transform @ vertex.co
                    normal = mesh.corner_normals[loop_index].vector if hasattr(mesh, 'corner_normals') else loop.normal
                    normal = normal_transform @ normal
                    if normal.length_squared:
                        normal.normalize()
                    uv = uv_layer.data[loop_index].uv if uv_layer else (0.0, 1.0)
                    color = (255, 255, 255, 255)
                    if color_layer:
                        index = vertex.index if getattr(color_layer, 'domain', 'CORNER') == 'POINT' else loop_index
                        color = tuple(max(0, min(255, round(channel * 255.0))) for channel in color_layer.data[index].color)
                    corners.append(MobileVertex(tuple(position), (float(uv[0]), 1.0 - float(uv[1])),
                                                 tuple(normal), color, weights[vertex.index]))
                if reverse_winding:
                    corners[1], corners[2] = corners[2], corners[1]
                surface['triangles'].append(tuple(corners))
    return list(surfaces.values()), descriptions


def exportImportedDff(context, path, root=None):
    from ..rwLib.native_mobile_dff import rebuildMobileGeometry, buildMobileMaterialList
    from ..rwLib.dff import readLeedsGeometry
    root = root or findDffRoot(context.object)
    if root is None:
        raise ValueError('Select an imported DFF or a mesh parented to its root')
    if not isObjectExportable(root):
        raise ValueError("This model is marked Don't Export")
    if context.object and context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    clumps = readDff(base64.b64decode(root['bleeds_dff_source']), root['bleeds_dff_profile'])
    updateMobileFrames(context, root, clumps)
    objects = {}
    atomic_keys = [(ci, ai) for ci, clump in enumerate(clumps) for ai, atomic in enumerate(clump['atomics'])]
    for obj in objectChildren(root):
        if not isModelMesh(obj):
            continue
        owner = obj
        while owner is not None and owner != root and 'bleeds_dff_part' not in owner:
            owner = owner.parent
        if owner is not None and 'bleeds_dff_part' in owner:
            key = tuple(owner['bleeds_dff_part'][:2])
        elif len(atomic_keys) == 1:
            key = atomic_keys[0]
        else:
            raise ValueError('Parent new mesh %s to a mesh belonging to its DFF frame' % obj.name)
        if key not in atomic_keys:
            raise ValueError('Mesh refers to an unknown DFF atomic: ' + obj.name)
        objects.setdefault(key, []).append(obj)
    for clump_index, clump in enumerate(clumps):
        for atomic_index, atomic in enumerate(clump['atomics']):
            meshes = objects.get((clump_index, atomic_index), [])
            if not meshes or not any(len(obj.data.polygons) for obj in meshes):
                clump['sections'] = [section for section in clump['sections'] if section is not atomic['chunk']]
                atomic['removed'] = True
                continue
            if atomic['geometry'].version != 0xF00D:
                raise ValueError('Convert this model with LCS Mobile export')
            surfaces, descriptions = collectMobileSurfaces(context, root, clump_index, atomic_index, clump, atomic, meshes)
            source, sections = readLeedsGeometry(atomic['geometry'])
            material_list = buildMobileMaterialList(descriptions, sections)
            import copy
            geometry = copy.deepcopy(atomic['geometry'])
            rebuildMobileGeometry(geometry, surfaces, material_list)
            if atomic['shared']:
                atomic['children'].insert(1, geometry)
            else:
                atomic['children'] = [geometry if child is atomic['geometry'] else child for child in atomic['children']]
            atomic['geometry'] = geometry
            atomic['shared'] = False
    remaining_atomics = 0
    for clump in clumps:
        clump['atomics'] = [atomic for atomic in clump['atomics'] if not atomic.get('removed')]
        structure = next(section for section in clump['sections'] if section.type_id == 1)
        payload = bytearray(structure.payload)
        struct.pack_into('<I', payload, 0, len(clump['atomics']))
        structure.payload = bytes(payload)
        remaining_atomics += len(clump['atomics'])
    if not remaining_atomics:
        raise ValueError('The DFF has no mesh faces to export')
    output = writeDff(clumps, rebuild_sizes=True)
    readDff(output, root['bleeds_dff_profile'])
    writeAtomic(path, output)
    return remaining_atomics


def mobileExportObjects(context, root=None, selected_objects=None):
    from .object_types import importedModelOwner
    selected = list(context.selected_objects if selected_objects is None else selected_objects)
    active = context.object
    root = root or importedModelOwner(active)
    if root is None and active is not None:
        root = active
        while root.parent is not None:
            root = root.parent
        if root.type == 'MESH' and len(selected) > 1:
            root = None
    candidates = ([root] + objectChildren(root)) if root is not None else selected
    meshes = [obj for obj in candidates if isModelMesh(obj) and len(obj.data.polygons)]
    if not meshes:
        raise ValueError('Select a model with mesh faces to export')
    armatures = []
    for obj in meshes:
        rigs = [modifier.object for modifier in obj.modifiers
                if modifier.type == 'ARMATURE' and modifier.object is not None]
        if obj.parent is not None and obj.parent.type == 'ARMATURE':
            rigs.append(obj.parent)
        rigs = list(dict.fromkeys(rigs))
        if len(rigs) > 1:
            raise ValueError('%s uses more than one skeleton' % obj.name)
        for rig in rigs:
            if not isObjectExportable(rig):
                raise ValueError('%s uses a skeleton marked Don\'t Export' % obj.name)
            if rig not in armatures:
                armatures.append(rig)
    return root, meshes, armatures


def mobileFrameValues(matrix):
    values = [float(matrix[row][column]) for column in range(3) for row in range(3)]
    values.extend(float(matrix[row][3]) for row in range(3))
    if not all(math.isfinite(value) for value in values):
        raise ValueError('A model frame contains an invalid position or rotation')
    return tuple(values)


def mobileBoneOrder(armature):
    ordered = []
    def visit(bone):
        ordered.append(bone)
        for child in bone.children:
            visit(child)
    for bone in armature.data.bones:
        if bone.parent is None:
            visit(bone)
    if len(ordered) > 64:
        raise ValueError('%s has %d bones; LCS Mobile supports up to 64 per skeleton' % (armature.name, len(ordered)))
    return ordered


def buildMobileFrames(root, meshes, armatures):
    # Build the frame tree from this model; an original DFF is not needed.
    from ..rwLib.chunks import RenderWareChunk
    origin = root.matrix_world if root is not None else Matrix.Identity(4)
    try:
        inverse = origin.inverted()
    except ValueError:
        raise ValueError('The model has a zero scale; give it a nonzero scale before export')
    frames = [dict(index=0, parent=-1, name=root.name if root else 'model', values=mobileFrameValues(Matrix.Identity(4)),
                   bone_id=None, skin_index=None)]
    objects = []
    for obj in meshes + armatures:
        lineage = []
        current = obj
        while current is not None and current != root:
            lineage.append(current)
            current = current.parent
        for current in reversed(lineage):
            if current not in objects and isObjectExportable(current):
                objects.append(current)
    object_frames = {root: 0} if root is not None else {}
    worlds = {0: Matrix.Identity(4)}
    extensions = [[]]
    for obj in objects:
        parent = object_frames.get(obj.parent, 0)
        world = inverse @ obj.matrix_world
        local = worlds[parent].inverted() @ world
        index = len(frames)
        object_frames[obj] = index
        worlds[index] = world
        frames.append(dict(index=index, parent=parent, name=obj.name, values=mobileFrameValues(local), bone_id=None, skin_index=None))
        extensions.append([])
    rig_maps = {}
    for rig in armatures:
        if rig not in object_frames:
            object_frames[rig] = 0
        ordered = mobileBoneOrder(rig)
        ids = {}
        used_ids = set()
        reserved_ids = {int(bone[key]) for bone in ordered for key in ('bleeds_anim_bone_id', 'bleeds_hanim_bone_id',
                        'bleeds_mdl_anim_bone_id', 'BoneID', 'bone_id') if key in bone and int(bone[key]) != 255}
        for bone in ordered:
            bone_id = next((int(bone[key]) for key in ('bleeds_anim_bone_id', 'bleeds_hanim_bone_id',
                            'bleeds_mdl_anim_bone_id', 'BoneID', 'bone_id') if key in bone), None)
            if bone_id is None or bone_id == 255 or bone_id < 0:
                bone_id = next(value for value in range(0x7FFFFFFF) if value not in used_ids and value not in reserved_ids)
            if bone_id < 0 or bone_id > 0x7FFFFFFF or bone_id in used_ids:
                raise ValueError('%s has a missing or repeated animation bone ID: %s' % (rig.name, bone.name))
            ids[bone.name] = bone_id
            used_ids.add(bone_id)
        bone_frames = {}
        rig_map = {}
        hierarchy = []
        stack_depth = 0
        for skin_index, bone in enumerate(ordered):
            parent = bone_frames[bone.parent.name] if bone.parent else object_frames[rig]
            local = bone.parent.matrix_local.inverted() @ bone.matrix_local if bone.parent else bone.matrix_local
            frame_index = len(frames)
            bone_frames[bone.name] = frame_index
            rig_map[bone.name] = skin_index
            frames.append(dict(index=frame_index, parent=parent, name=bone.name, values=mobileFrameValues(local),
                               bone_id=ids[bone.name], skin_index=skin_index))
            extensions.append([])
            siblings = list(bone.parent.children) if bone.parent else [item for item in ordered if item.parent is None]
            flags = 0
            if siblings.index(bone) < len(siblings) - 1:
                flags |= 2
                stack_depth += 1
            if not bone.children and stack_depth:
                flags |= 1
                stack_depth -= 1
            hierarchy.append((ids[bone.name], skin_index, flags))
        if ordered:
            for bone in ordered:
                count = len(ordered) if bone == ordered[0] else 0
                payload = struct.pack('<3I', 0x100, ids[bone.name], count)
                if count:
                    payload += struct.pack('<2I', 0, 36)
                    payload += b''.join(struct.pack('<3I', *entry) for entry in hierarchy)
                extensions[bone_frames[bone.name]].append(RenderWareChunk(0x11E, 0x310, payload))
        rig_maps[rig] = rig_map
    structure = struct.pack('<I', len(frames))
    for frame in frames:
        structure += struct.pack('<12fiI', *frame['values'], frame['parent'], 0)
    children = [RenderWareChunk(1, 0x310, structure)]
    for frame, plugins in zip(frames, extensions):
        name = frame['name'].encode('utf-8') + b'\0'
        plugins.insert(0, RenderWareChunk(0x253F2FE, 0x310, name))
        children.append(RenderWareChunk(3, 0x310, b''.join(plugin.toBytes() for plugin in plugins)))
    frame_list = RenderWareChunk(0xE, 0x310, b''.join(child.toBytes() for child in children))
    return frames, frame_list, object_frames, rig_maps, origin


def exportConvertedMobileDff(context, path, root=None, selected_objects=None):
    from types import SimpleNamespace
    from ..rwLib.chunks import RenderWareChunk
    from ..rwLib.native_mobile_dff import rebuildMobileGeometry, buildMobileMaterialList
    if context.object is not None and context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    root, meshes, armatures = mobileExportObjects(context, root, selected_objects)
    frames, frame_list, object_frames, rig_maps, origin = buildMobileFrames(root, meshes, armatures)
    proxy = SimpleNamespace(matrix_world=origin, children_recursive=armatures)
    clump = dict(frames=frames)
    groups = {}
    for obj in meshes:
        rigs = [modifier.object for modifier in obj.modifiers if modifier.type == 'ARMATURE' and modifier.object in armatures]
        if not rigs and obj.parent in armatures:
            rigs = [obj.parent]
        rig = rigs[0] if rigs else None
        key = (rig, None) if rig else (None, obj)
        groups.setdefault(key, []).append(obj)
    atomics = []
    for (rig, static_object), group in groups.items():
        frame_index = object_frames[rig] if rig else object_frames.get(static_object, 0)
        geometry_spec = dict(frame=frame_index, parts=[], skinned=rig is not None, converted=True)
        rig_frames = frames if rig is None else [dict(frame, skin_index=rig_maps[rig].get(frame['name'])) for frame in frames]
        surfaces, descriptions = collectMobileSurfaces(context, proxy, 0, len(atomics), dict(frames=rig_frames), geometry_spec, group)
        material_list = buildMobileMaterialList(descriptions, [])
        geometry = rebuildMobileGeometry(None, surfaces, material_list)
        children = [RenderWareChunk(1, 0x310, struct.pack('<4I', frame_index, 0, 5, 0)), geometry,
                    RenderWareChunk(3, 0x310, b'')]
        atomics.append(RenderWareChunk(0x14, 0x310, b''.join(child.toBytes() for child in children)))
    sections = [RenderWareChunk(1, 0x310, struct.pack('<I', len(atomics))), frame_list] + atomics + [RenderWareChunk(3, 0x310, b'')]
    output = RenderWareChunk(0x10, 0x310, b''.join(section.toBytes() for section in sections)).toBytes()
    decoded = readDff(output, 'MOBILE')
    if sum(len(item['atomics']) for item in decoded) != len(groups):
        raise ValueError('The saved model is missing mesh objects')
    writeAtomic(path, output)
    return len(groups)


def exportDff(context, path, root=None, selected_objects=None):
    # Keep the original file details when editing Mobile files. Build a new file for other models.
    from .object_types import importedModelOwner
    root = root or importedModelOwner(context.object)
    if root is not None and root.get('bleeds_dff_source') and root.get('bleeds_dff_profile') == 'MOBILE':
        original = readDff(base64.b64decode(root['bleeds_dff_source']), 'MOBILE')
        if all(atomic['geometry'].version == 0xF00D for clump in original for atomic in clump['atomics']):
            return exportImportedDff(context, path, root)
    return exportConvertedMobileDff(context, path, root, selected_objects)


def applyDffTextures(images):
    matched = 0
    for material in bpy.data.materials:
        name = str(material.get('bleeds_texture_name', ''))
        image = images.get(name.casefold())
        if image is None:
            continue
        material.use_nodes = True
        shader = next((node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED'), None)
        if shader is None:
            continue
        node = next((node for node in material.node_tree.nodes if node.type == 'TEX_IMAGE' and
                     node.image is not None and str(node.image.get('bleeds_mobile_texture', '')).casefold() == name.casefold()), None)
        if node is None:
            node = material.node_tree.nodes.new('ShaderNodeTexImage')
        node.image = image
        material.node_tree.links.new(node.outputs['Color'], shader.inputs['Base Color'])
        material.node_tree.links.new(node.outputs['Alpha'], shader.inputs['Alpha'])
        matched += 1
    return matched
