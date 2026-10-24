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

import base64
import json
import struct
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

from ..rwLib.dff import readDff, writeDff, replaceGeometryVertices, replaceLeedsVertices, replaceLeedsAttributes
from ..rwLib.txd import MobileTxd
from ..leedsLib.native_mobile import writeAtomic


def frameMatrix(values):
    return Matrix(((values[0], values[3], values[6], values[9]),
                   (values[1], values[4], values[7], values[10]),
                   (values[2], values[5], values[8], values[11]),
                   (0.0, 0.0, 0.0, 1.0)))


def flattenMatrix(matrix):
    return [float(value) for row in matrix for value in row]


def importTextures(path):
    dictionary = MobileTxd(Path(path).read_bytes())
    images = {}
    for texture in dictionary.textures:
        pixels = dictionary.pixels(texture)
        image = bpy.data.images.new(texture.name, texture.width, texture.height, alpha=True)
        image.pixels.foreach_set((pixels[::-1].astype('float32') / 255.0).ravel())
        image.pack()
        image['bleeds_mobile_txd'] = str(Path(path).resolve())
        image['bleeds_mobile_texture'] = texture.name
        images[texture.name.casefold()] = image
    return images


def importDff(context, path, source='MOBILE'):
    if context.object is not None and context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    raw = Path(path).read_bytes()
    clumps = readDff(raw, source)
    collection = bpy.data.collections.new(Path(path).stem)
    context.scene.collection.children.link(collection)
    root = bpy.data.objects.new(Path(path).stem, None)
    collection.objects.link(root)
    root['bleeds_dff_source'] = base64.b64encode(raw).decode('ascii')
    root['bleeds_dff_profile'] = source
    root['bleeds_model_game'] = 'LCS'
    root['bleeds_dff_path'] = str(Path(path).resolve())
    images = {}
    sidecars = [p for p in Path(path).parent.iterdir()
                if p.stem.casefold() == Path(path).stem.casefold() and p.suffix.casefold() == '.txd']
    if source == 'MOBILE' and sidecars:
        images = importTextures(sidecars[0])
    created = [root]
    for clump_index, clump in enumerate(clumps):
        frames = clump['frames']
        world = {}
        def globalFrame(index):
            if index not in world:
                frame = frames[index]
                local = frameMatrix(frame['values'])
                world[index] = globalFrame(frame['parent']) @ local if frame['parent'] >= 0 else local
            return world[index]
        for frame in frames:
            globalFrame(frame['index'])
        armature = None
        bones = {}
        if any(frame['bone_id'] is not None and frame['bone_id'] >= 0 for frame in frames):
            data = bpy.data.armatures.new(root.name + '_bones')
            armature = bpy.data.objects.new(root.name + '_bones', data)
            collection.objects.link(armature)
            armature.parent = root
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
        for atomic_index, atomic in enumerate(clump['atomics']):
            materials = []
            for index, entry in enumerate(atomic['materials']):
                material = bpy.data.materials.new(entry['name'] or 'material_%d' % index)
                material.diffuse_color = tuple(channel / 255.0 for channel in entry['color'])
                material.use_nodes = True
                shader = material.node_tree.nodes.get('Principled BSDF')
                shader.inputs['Base Color'].default_value = material.diffuse_color
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
                obj.parent = root
                obj.matrix_local = world[atomic['frame']]
                obj['bleeds_dff_part'] = [clump_index, atomic_index, part_index]
                obj['bleeds_dff_original_uvs'] = json.dumps(part['uvs'])
                obj['bleeds_dff_original_matrix'] = flattenMatrix(obj.matrix_local)
                for material in materials:
                    mesh.materials.append(material)
                for polygon in mesh.polygons:
                    source_materials = part.get('face_materials')
                    polygon.material_index = source_materials[polygon.index] if source_materials else part['material']
                if part['uvs']:
                    layer = mesh.uv_layers.new(name='UVMap')
                    for loop in mesh.loops:
                        uv = part['uvs'][loop.vertex_index]
                        layer.data[loop.index].uv = (uv[0], 1.0 - uv[1])
                if part['normals'] and len(part['normals']) == len(mesh.vertices):
                    mesh.normals_split_custom_set_from_vertices(part['normals'])
                    if hasattr(mesh, 'use_auto_smooth'):
                        mesh.use_auto_smooth = True
                if part['colors'] and len(part['colors']) == len(mesh.vertices):
                    if hasattr(mesh, 'color_attributes'):
                        color_layer = mesh.color_attributes.new(name='Color', type='BYTE_COLOR', domain='POINT')
                        for index, color in enumerate(part['colors']):
                            color_layer.data[index].color = tuple(float(channel) / 255.0 for channel in color)
                    else:
                        color_layer = mesh.vertex_colors.new(name='Color')
                        for loop in mesh.loops:
                            color_layer.data[loop.index].color = tuple(float(channel) / 255.0 for channel in part['colors'][loop.vertex_index])
                native_part = part.get('source')
                if armature and native_part:
                    by_skin_index = {frame['skin_index']: bones[frame['index']] for frame in frames
                                     if frame['index'] in bones and frame['skin_index'] is not None}
                    groups = {}
                    for strip in native_part.strips_meta:
                        for index, (indices, weights) in enumerate(zip(strip.skin_indices, strip.skin_weights)):
                            for bone_index, weight in zip(indices, weights):
                                if weight <= 0.0:
                                    continue
                                name = by_skin_index.get(bone_index)
                                if name is None:
                                    raise ValueError('Mobile skin refers to an unknown bone index: %d' % bone_index)
                                if name not in groups:
                                    groups[name] = obj.vertex_groups.new(name=name)
                                groups[name].add([strip.base_vertex_index + index], float(weight), 'ADD')
                    if groups:
                        modifier = obj.modifiers.new('Armature', 'ARMATURE')
                        modifier.object = armature
                obj['bleeds_dff_skin_indices'] = json.dumps({name: index for index, name in by_skin_index.items()} if armature and native_part else {})
                obj['bleeds_dff_original_weights'] = json.dumps([[ [group.group, group.weight] for group in vertex.groups] for vertex in mesh.vertices])
                obj['bleeds_dff_original_materials'] = [polygon.material_index for polygon in mesh.polygons]
                created.append(obj)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in created:
        obj.select_set(True)
    context.view_layer.objects.active = next((obj for obj in created if obj.type == 'ARMATURE'), root)
    return created


def findDffRoot(obj):
    while obj is not None and 'bleeds_dff_source' not in obj:
        obj = obj.parent
    return obj


def dffFrameWorldMatrices(frames):
    matrices = {}
    def resolve(index):
        if index not in matrices:
            frame = frames[index]
            local = frameMatrix(frame['values'])
            matrices[index] = resolve(frame['parent']) @ local if frame['parent'] >= 0 else local
        return matrices[index]
    for frame in frames:
        resolve(frame['index'])
    return matrices


def materialDescription(material, source_index):
    if material is None:
        return dict(color=(1.0, 1.0, 1.0, 1.0), texture='', source_index=source_index)
    color = tuple(material.diffuse_color)
    texture = str(material.get('bleeds_texture_name', ''))
    if material.use_nodes and material.node_tree:
        shader = next((node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED'), None)
        if shader:
            color = tuple(shader.inputs['Base Color'].default_value)
            if 'Alpha' in shader.inputs:
                color = color[:3] + (float(shader.inputs['Alpha'].default_value),)
            links = shader.inputs['Base Color'].links
            image_node = next((link.from_node for link in links if link.from_node.type == 'TEX_IMAGE'), None)
            if image_node and image_node.image:
                texture = str(image_node.image.get('bleeds_mobile_texture', image_node.image.name))
    return dict(color=color, texture=texture, source_index=source_index)


def collectMobileSurfaces(context, root, clump_index, atomic_index, clump, atomic, objects):
    from ..rwLib.native_mobile_dff import MobileVertex
    frames = clump['frames']
    frames_world = dffFrameWorldMatrices(frames)
    geometry_world = root.matrix_world @ frames_world[atomic['frame']]
    armatures = [obj for obj in root.children_recursive if obj.type == 'ARMATURE']
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
    skinned = any(weight > 0.0 for part in atomic['parts'] for strip in part.get('source').strips_meta
                  for weights in strip.skin_weights for weight in weights) if atomic['geometry'].version == 0xF00D else False
    surfaces = {}
    descriptions = []
    material_ids = {}
    for obj in objects:
        mesh = obj.data
        mesh.calc_loop_triangles()
        if hasattr(mesh, 'calc_normals_split'):
            mesh.calc_normals_split()
        transform = geometry_world.inverted() @ obj.matrix_world
        normal_transform = transform.to_3x3().inverted().transposed()
        reverse_winding = transform.to_3x3().determinant() < 0.0
        uv_layer = mesh.uv_layers.active
        color_layer = mesh.color_attributes.active_color if hasattr(mesh, 'color_attributes') else mesh.vertex_colors.active
        source_part = int(obj.get('bleeds_dff_part', (clump_index, atomic_index, 0))[2])
        mapping = dict(bone_names)
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
            material = mesh.materials[slot] if slot < len(mesh.materials) else None
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


def exportDff(context, path):
    from ..rwLib.native_mobile_dff import rebuildMobileGeometry, buildMobileMaterialList
    from ..rwLib.dff import readLeedsGeometry
    root = findDffRoot(context.object)
    if root is None:
        raise ValueError('Select an imported DFF or a mesh parented to its root')
    if context.object and context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    clumps = readDff(base64.b64decode(root['bleeds_dff_source']), root['bleeds_dff_profile'])
    objects = {}
    atomic_keys = [(ci, ai) for ci, clump in enumerate(clumps) for ai, atomic in enumerate(clump['atomics'])]
    for obj in root.children_recursive:
        if obj.type != 'MESH':
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
                raise ValueError('Geometry rebuilding is implemented for LCS mobile native DFFs; this prototype uses a different format')
            surfaces, descriptions = collectMobileSurfaces(context, root, clump_index, atomic_index, clump, atomic, meshes)
            source, sections = readLeedsGeometry(atomic['geometry'])
            material_list = buildMobileMaterialList(descriptions, sections)
            rebuildMobileGeometry(atomic['geometry'], surfaces, material_list)
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
