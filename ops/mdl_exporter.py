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
import json
import os
import struct
import tempfile
import zlib
from pathlib import Path

import numpy as np
from mathutils import Matrix, Vector

from ..rwLib.dff import readModel
from ..leedsLib.native_mdl import (
    decodePmlcContainer,
    rebuildPmlcGeometry,
    loadMh2NativeModel,
    mh2GeometryFingerprint,
)

def mh2ObjectValue(obj, name, default=None):
    if obj is None:
        return default
    value = None
    try:
        value = obj.get(name)
    except (AttributeError, TypeError, RuntimeError):
        pass
    if value is None or value == '':
        try:
            value = getattr(obj, name, None)
        except (AttributeError, TypeError, RuntimeError):
            pass
    return default if value is None or value == '' else value


def isMh2Member(obj):
    if obj is None:
        return False
    if str(mh2ObjectValue(obj, 'bleeds_model_game', '')).upper() == 'MH2':
        return True
    for name in (
        'bleeds_mh2_platform',
        'bleeds_mh2_native_text',
        'bleeds_mh2_objinfo_offset',
        'bleeds_mh2_clump_index',
        'bleeds_mh2_source_container',
        'bleeds_mh2_vertex_start',
    ):
        if mh2ObjectValue(obj, name) is not None:
            return True
    return False


def mh2Descendants(obj):
    try:
        return list(obj.children_recursive)
    except (AttributeError, TypeError, RuntimeError):
        return []


def isMh2RootObject(obj):
    if obj is None or getattr(obj, 'type', None) == 'MESH':
        return False
    if bool(mh2ObjectValue(obj, 'bleeds_is_mdl_root', False)) and isMh2Member(obj):
        return True
    if getattr(obj, 'type', None) in {'ARMATURE', 'EMPTY'}:
        if isMh2Member(obj):
            return True
        return any(isMh2Member(child) and getattr(child, 'type', None) == 'MESH'
                   for child in mh2Descendants(obj))
    return False


def getMh2RootFromObject(obj):
    # Prefer the outermost model node, not a child armature or a mesh part.
    candidates = []
    visited = set()
    while obj is not None and id(obj) not in visited:
        visited.add(id(obj))
        if isMh2RootObject(obj):
            candidates.append(obj)
        if getattr(obj, 'type', None) == 'MESH':
            for modifier in getattr(obj, 'modifiers', ()) or ():
                if getattr(modifier, 'type', None) == 'ARMATURE':
                    rig = getattr(modifier, 'object', None)
                    if rig is not None and isMh2RootObject(rig) and rig not in candidates:
                        candidates.append(rig)
        obj = getattr(obj, 'parent', None)
    return candidates[-1] if candidates else None


def mh2SceneObjects(context):
    objects = []
    seen = set()
    scene = getattr(context, 'scene', None)
    sources = [getattr(scene, 'objects', ()) if scene is not None else ()]
    try:
        import bpy
        sources.append(getattr(bpy.data, 'objects', ()))
    except (ImportError, AttributeError, RuntimeError):
        pass
    sources.append(getattr(context, 'selected_objects', ()) or ())
    sources.append((getattr(context, 'active_object', None), getattr(context, 'object', None)))
    for source in sources:
        try:
            values = list(source)
        except (TypeError, RuntimeError):
            continue
        for obj in values:
            if obj is not None and id(obj) not in seen:
                objects.append(obj)
                seen.add(id(obj))
    return objects


def getMh2RootCandidates(context):
    roots = []
    seen = set()
    for obj in mh2SceneObjects(context):
        root = getMh2RootFromObject(obj)
        if root is not None and id(root) not in seen:
            seen.add(id(root))
            roots.append(root)
    return roots


def recoverMh2RootProperties(root):
    # Older imports sometimes have the Manhunt 2 information on their mesh
    # objects rather than on the armature. Keep the existing scene usable.
    if root is None:
        return None
    nodes = [root] + mh2Descendants(root)
    source_keys = (
        'bleeds_mh2_native_text',
        'bleeds_mh2_native_sha256',
        'bleeds_mh2_path',
        'bleeds_mdl_filepath',
        'bleeds_mh2_platform',
        'bleeds_mdl_platform',
        'bleeds_mh2_model_class',
        'bleeds_mdl_type',
        'bleeds_mh2_part_slots',
        'bleeds_mh2_clump_index',
    )
    for name in source_keys:
        if mh2ObjectValue(root, name) is not None:
            continue
        for node in nodes[1:]:
            value = mh2ObjectValue(node, name)
            if value is not None:
                try:
                    root[name] = value
                except (TypeError, ValueError, RuntimeError):
                    pass
                break
    try:
        root['bleeds_model_game'] = 'MH2'
        root['bleeds_is_mdl_root'] = True
    except (TypeError, ValueError, RuntimeError):
        pass
    if mh2ObjectValue(root, 'bleeds_mh2_platform') is None:
        platform = str(mh2ObjectValue(root, 'bleeds_mdl_platform', 'PC')).upper()
        if platform in {'PC', 'PS2', 'PSP'}:
            root['bleeds_mh2_platform'] = platform
    if mh2ObjectValue(root, 'bleeds_mh2_model_class') is None:
        model_type = str(mh2ObjectValue(root, 'bleeds_mdl_type', 'PED')).upper()
        if model_type in {'SIM', 'PED', 'CUT'}:
            root['bleeds_mh2_model_class'] = model_type
    return root


def findMh2Root(context, preferred_name=None):
    roots = getMh2RootCandidates(context)
    if preferred_name:
        # Blender's file selector can have a different scene and an empty
        # selection. Resolve the saved object name against all open objects.
        for obj in mh2SceneObjects(context):
            if getattr(obj, 'name', None) == preferred_name:
                root = getMh2RootFromObject(obj)
                if root is not None:
                    return recoverMh2RootProperties(root)
        for root in roots:
            if root.name == preferred_name:
                return recoverMh2RootProperties(root)

    active = getattr(context, 'active_object', None) or getattr(context, 'object', None)
    if active is None:
        view_layer = getattr(context, 'view_layer', None)
        active = getattr(getattr(view_layer, 'objects', None), 'active', None)
    candidates = [active]
    candidates.extend(getattr(context, 'selected_objects', ()) or ())
    for candidate in candidates:
        root = getMh2RootFromObject(candidate)
        if root is not None:
            return recoverMh2RootProperties(root)
        if candidate is not None and isMh2Member(candidate):
            source = str(mh2ObjectValue(candidate, 'bleeds_mdl_filepath', '') or
                         mh2ObjectValue(candidate, 'bleeds_mh2_path', ''))
            clump = mh2ObjectValue(candidate, 'bleeds_mh2_clump_index')
            matching = [root for root in roots
                        if source and source in {
                            str(mh2ObjectValue(root, 'bleeds_mdl_filepath', '')),
                            str(mh2ObjectValue(root, 'bleeds_mh2_path', ''))
                        } and (clump is None or
                               mh2ObjectValue(root, 'bleeds_mh2_clump_index') is None or
                               str(clump) == str(mh2ObjectValue(root, 'bleeds_mh2_clump_index')))]
            if len(matching) == 1:
                return recoverMh2RootProperties(matching[0])

    if len(roots) == 1:
        return recoverMh2RootProperties(roots[0])
    if len(roots) > 1:
        raise ValueError('More than one Manhunt 2 model is open. Select the model you want to export.')
    raise ValueError('No Manhunt 2 model is loaded in this Blender file')



def normalizeMh2ArmatureNames(root):
    if root is None or getattr(root, 'type', None) != 'ARMATURE':
        return
    filepath = str(mh2ObjectValue(root, 'bleeds_mdl_filepath', '') or mh2ObjectValue(root, 'bleeds_mh2_path', '') or '')
    model_name = Path(filepath).stem.strip()
    if not model_name:
        return
    if root.name.casefold() == 'unnamed':
        root.name = model_name
    armature = getattr(root, 'data', None)
    if armature is not None and armature.name.casefold() == 'unnamed':
        armature.name = model_name + ' Skeleton'
    if armature is None:
        return
    root_bone = next((bone for bone in armature.bones if bone.parent is None), None)
    if root_bone is None:
        return
    root_bone.hide = True
    attachment_names = {
        'danny_broken_cutscene_l0',
        'weapstrap',
        'lurebagempty_(ct)',
    }
    for bone in armature.bones:
        if bone.name.casefold() in attachment_names:
            bone.hide = True
        elif bone.parent == root_bone and not bone.name.casefold().startswith('bip'):
            if (bone.head_local - root_bone.head_local).length < 0.10:
                bone.hide = True


def validateMh2ExportType(root, model_type='PED'):
    requested = str(model_type or 'PED').upper().strip()
    if requested not in {'SIM', 'PED', 'CUT'}:
        raise ValueError('Unsupported Manhunt 2 export model class: ' + requested)
    source_type = str(mh2ObjectValue(root, 'bleeds_mh2_model_class', '') or
                      mh2ObjectValue(root, 'bleeds_mdl_type', '') or '').upper().strip()
    if source_type not in {'SIM', 'PED', 'CUT'}:
        raise ValueError('Manhunt 2 model structure could not be determined')
    if requested == 'SIM' and source_type != 'SIM':
        raise ValueError('Cannot export a native clump as SimpleModel without rebuilding its native hierarchy')
    if requested in {'PED', 'CUT'} and source_type == 'SIM':
        raise ValueError('Cannot export a SimpleModel as a clump without native skeleton/clump records')


def encodeMh2Position(position, part, vertex_index, platform):
    source_offset = int(part['position_sources'][vertex_index])
    scale = part['scale']
    translation = part['translation']
    values = []
    for axis in range(3):
        factor = float(scale[axis])
        if not math.isfinite(factor) or abs(factor) < 1.0e-30:
            raise ValueError('MH2 source position scale is zero or invalid')
        values.append((float(position[axis]) - float(translation[axis])) / factor)

    component_size = 2 if platform == 'PS2' else int(part.get('position_size', 0))
    formats = {1: ('<3b', 128.0, -128, 127), 
               2: ('<3h', 32768.0, -32768, 32767), 
               4: ('<3f', 1.0, None, None)}
    if component_size not in formats:
        raise ValueError(f'Unsupported MH2 position component width: {component_size}')
    fmt, divisor, minimum, maximum = formats[component_size]
    if component_size == 4:
        encoded = tuple(values)
    else:
        encoded = tuple(int(round(value * divisor)) for value in values)
        if any(value < minimum or value > maximum for value in encoded):
            raise ValueError(f'MH2 vertex {vertex_index} exceeds its original signed position range')
    if not all(math.isfinite(float(value)) for value in encoded):
        raise ValueError(f'MH2 vertex {vertex_index} contains non-finite coordinates')
    return source_offset, struct.pack(fmt, *encoded)



def mh2ConsoleCornerValues(obj, part):
    mesh = obj.data
    vertex_count = len(mesh.vertices)
    uv_layer = getattr(mesh.uv_layers, 'active', None) if hasattr(mesh, 'uv_layers') else None
    color_layers = getattr(mesh, 'color_attributes', None)
    color_layer = None
    if color_layers is not None:
        color_layer = (color_layers.get('Prelight') or color_layers.get('Color')
                       or color_layers.get('Col') or getattr(color_layers, 'active_color', None))
    uv_values = [None] * vertex_count
    color_values = [None] * vertex_count
    normal_values = [None] * vertex_count
    if hasattr(mesh, 'calc_normals_split'):
        try:
            mesh.calc_normals_split()
        except (RuntimeError, AttributeError):
            pass
    for loop_index, loop in enumerate(mesh.loops):
        vertex_index = int(loop.vertex_index)
        if vertex_index < 0 or vertex_index >= vertex_count:
            raise ValueError(f'{obj.name}: mesh loop references an invalid vertex')
        attributes = (
            ('UV', uv_values, tuple(uv_layer.data[loop_index].uv) if uv_layer else None),
            ('vertex color', color_values,
             tuple(color_layer.data[loop_index if color_layer.domain == 'CORNER' else vertex_index].color)
             if color_layer else None),
            ('normal', normal_values,
             tuple(loop.normal) if hasattr(loop, 'normal') else tuple(mesh.vertices[vertex_index].normal)),
        )
        for label, values, value in attributes:
            if value is None:
                continue
            if not all(math.isfinite(float(component)) for component in value):
                raise ValueError(f'{obj.name}: vertex {vertex_index} has an invalid {label}')
            previous = values[vertex_index]
            if previous is not None and any(abs(float(a) - float(b)) > 0.0001
                                            for a, b in zip(previous, value)):
                raise ValueError(
                    f'{obj.name}: vertex {vertex_index} has different {label} values on its faces. '
                    'Split the vertex at the seam before exporting this native console mesh.'
                )
            values[vertex_index] = value
    for index, vertex in enumerate(mesh.vertices):
        if normal_values[index] is None:
            normal_values[index] = tuple(vertex.normal)
    return uv_values, normal_values, color_values


def mh2ConsoleQuantize(value, divisor, lower, upper, description):
    if not math.isfinite(float(value)):
        raise ValueError(f'{description}: non-finite number')
    number = int(round(float(value) * divisor))
    if number < lower or number > upper:
        raise ValueError(f'{description}: value {value:.6g} exceeds the native range')
    return number


def mh2ConsoleEncodeUv(value, width, scale, description):
    if len(value) != 2:
        raise ValueError(f'{description}: invalid UV')
    output = []
    for axis in range(2):
        factor = float(scale[axis])
        if not math.isfinite(factor) or abs(factor) < 1.0e-20:
            raise ValueError(f'{description}: zero/invalid native UV scale')
        output.append(float(value[axis]) / factor)
    if width == 1:
        return struct.pack('<2B', *(mh2ConsoleQuantize(v, 128, 0, 255, description) for v in output))
    if width == 2:
        return struct.pack('<2H', *(mh2ConsoleQuantize(v, 32768, 0, 65535, description) for v in output))
    if width == 4:
        return struct.pack('<2f', *output)
    raise ValueError(f'{description}: unsupported native UV size {width}')


def mh2ConsoleEncodeNormal(value, width, description):
    normal = Vector(value)
    if not all(math.isfinite(float(component)) for component in normal):
        raise ValueError(f'{description}: non-finite normal')
    if normal.length < 1.0e-15:
        raise ValueError(f'{description}: zero-length normal')
    normal.normalize()
    if width == 1:
        return struct.pack('<3b', *(max(-128, min(127, round(float(v) * 128))) for v in normal))
    if width == 2:
        return struct.pack('<3h', *(max(-32768, min(32767, round(float(v) * 32768))) for v in normal))
    if width == 4:
        return struct.pack('<3f', *normal)
    raise ValueError(f'{description}: unsupported native normal size {width}')


def mh2ConsoleEncodeColor(value, platform, color_format):
    rgba = [max(0, min(255, int(round(float(channel) * 255)))) for channel in value[:4]]
    if len(rgba) == 3:
        rgba.append(255)
    if len(rgba) != 4:
        raise ValueError('MH2 vertex colors must have three or four components')
    red, green, blue, alpha = rgba
    if platform == 'PS2':
        return struct.pack('<4B', red, green, blue, int(round(alpha * 128.0 / 255.0)))
    if color_format == 7:
        return struct.pack('<4B', red, green, blue, alpha)
    if color_format == 4:
        value = ((red * 31 + 127) // 255) | (((green * 63 + 127) // 255) << 5) | (((blue * 31 + 127) // 255) << 11)
    elif color_format == 5:
        value = ((red * 31 + 127) // 255) | (((green * 31 + 127) // 255) << 5) | (((blue * 31 + 127) // 255) << 10) | (0x8000 if alpha >= 128 else 0)
    elif color_format == 6:
        value = ((red * 15 + 127) // 255) | (((green * 15 + 127) // 255) << 4) | (((blue * 15 + 127) // 255) << 8) | (((alpha * 15 + 127) // 255) << 12)
    else:
        raise ValueError(f'Unsupported PSP color format {color_format}')
    return struct.pack('<H', value)


def mh2ConsoleEncodeWeights(influences, part, vertex_index, platform, description):
    address = part['weight_sources'][vertex_index]
    width = part['weight_component_sizes'][vertex_index]
    count = part['weight_component_counts'][vertex_index]
    if address is None:
        raise ValueError(f'{description}: native stream has no skin weights')
    if not influences or count < 1:
        raise ValueError(f'{description}: skin weights are missing')
    weights = {int(token): float(weight) for token, weight in influences if weight > 0.0}
    if not weights or any(not math.isfinite(w) or w < 0 for w in weights.values()):
        raise ValueError(f'{description}: invalid skin weights')
    total = sum(weights.values())
    if total <= 1.0e-15:
        raise ValueError(f'{description}: skin weights sum to zero')
    if platform == 'PS2':
        if count != 4 or len(weights) > 4:
            raise ValueError(f'{description}: PS2 supports at most four bone influences')
        normalized = sorted(((bone, weight / total) for bone, weight in weights.items()),
                            key=lambda item: item[1], reverse=True)
        native_words = []
        for bone, weight in normalized:
            if not 0 <= bone < 64:
                raise ValueError(f'{description}: PS2 skin palette index is out of range')
            bits = struct.unpack('<I', struct.pack('<f', weight))[0]
            native_words.append((bits & 0xFFFFFF00) | bone * 4)
        native_words.extend([0] * (4 - len(native_words)))
        return address, struct.pack('<4I', *native_words)
    palette = part['weight_palettes'][vertex_index]
    if not palette or count > len(palette):
        raise ValueError(f'{description}: invalid PSP bone palette')
    if any(token not in palette[:count] for token in weights):
        raise ValueError(f'{description}: bone is not in the original PSP strip palette')
    native_weights = [weights.get(int(palette[index]), 0.0) / total for index in range(count)]
    if width == 4:
        return address, struct.pack('<' + str(count) + 'f', *native_weights)
    maximum = 128 if width == 1 else 32768 if width == 2 else None
    if maximum is None:
        raise ValueError(f'{description}: unsupported PSP skin-weight format')
    scaled = [weight * maximum for weight in native_weights]
    rounded = [int(math.floor(value)) for value in scaled]
    remaining = maximum - sum(rounded)
    for index in sorted(range(count), key=lambda i: scaled[i] - rounded[i], reverse=True)[:remaining]:
        rounded[index] += 1
    return address, struct.pack('<' + str(count) + ('B' if width == 1 else 'H'), *rounded)


def mh2ConsoleSourceWeights(entry, obj, part, vertex_index):
    palette = entry['palette']
    names = obj.get('bleeds_mh2_skin_palette_names', '[]')
    try:
        names = json.loads(names) if isinstance(names, str) else list(names)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'{obj.name}: invalid stored MH2 bone palette') from exc
    if not names:
        names = [entry['bones'][bone]['name'] if bone is not None else '' for bone in palette]
    token_by_name = {str(name): token for token, name in enumerate(names) if name}
    expected = {}
    for token, weight in part['weights'][vertex_index]:
        expected[int(token)] = expected.get(int(token), 0.0) + float(weight)
    if not expected:
        return [], False
    actual = {}
    for membership in obj.data.vertices[vertex_index].groups:
        if membership.group < 0 or membership.group >= len(obj.vertex_groups):
            raise ValueError(f'{obj.name}: invalid skin vertex group index')
        group_name = str(obj.vertex_groups[membership.group].name)
        token = token_by_name.get(group_name)
        if token is None and membership.weight > 0.00001:
            raise ValueError(f'{obj.name}: bone group {group_name!r} is missing from its native palette')
        if token is not None and membership.weight > 0.00001:
            actual[token] = actual.get(token, 0.0) + float(membership.weight)
    if not actual:
        # Importing without an armature leaves the source weights intact.
        if len(obj.vertex_groups) == 0:
            return [], False
        raise ValueError(f'{obj.name}: skinned vertex {vertex_index} has no bone weights')
    total = sum(actual.values())
    if not math.isfinite(total) or total <= 0:
        raise ValueError(f'{obj.name}: skinned vertex {vertex_index} has invalid weights')
    normalized = [(token, weight / total) for token, weight in actual.items()]
    original_total = sum(expected.values())
    changed = (set(actual) != set(expected) or any(
        abs(actual.get(token, 0.0) / total - weight / original_total) > 0.0005
        for token, weight in expected.items()
    ))
    return normalized, changed


def mh2ConsoleWrite(patched, upper_bound, offset, data, description):
    if offset is None or int(offset) < 0 or int(offset) + len(data) > upper_bound:
        raise ValueError(f'{description}: native attribute offset is outside MH2 geometry')
    patched[int(offset):int(offset) + len(data)] = data



def exportMh2Model(context, output_path: str, root=None):
    if root is None:
        root = findMh2Root(context)
    root = recoverMh2RootProperties(root)
    if root.get('bleeds_mh2_clump_index') is None or not root.get('bleeds_mh2_path'):
        return exportMh2PcPositions(root, output_path)
    resource, entries = readModel(loadMh2NativeModel(root), platform='AUTO')
    clump_index = int(root['bleeds_mh2_clump_index'])
    if clump_index < 0 or clump_index >= len(entries):
        raise ValueError('MH2 source clump index is outside the original model')

    meshes = {}
    for obj in root.children_recursive:
        if getattr(obj, 'type', None) == 'MESH' and getattr(obj, 'mode', '') == 'EDIT':
            obj.update_from_editmode()
    for obj in root.children_recursive:
        if getattr(obj, 'type', None) != 'MESH':
            continue
        if obj.get('bleeds_model_game') != 'MH2':
            continue
        if int(obj.get('bleeds_mh2_clump_index', -1)) != clump_index:
            continue
        atomic_index = int(obj.get('bleeds_mh2_atomic_index', -1))
        part_index = int(obj.get('bleeds_mh2_part_index', -1))
        key = (atomic_index, part_index)
        if key in meshes:
            raise ValueError(f'Duplicate MH2 source part identity {key}')
        meshes[key] = obj
    if not meshes:
        raise ValueError('No MH2 mesh parts with source identity were found; reimport using this BLeeds version')

    entry = entries[clump_index]
    bones_by_offset = {bone['offset']: bone for bone in entry['bones']}
    inverse_rotation = Matrix.Rotation(-math.pi / 2.0, 4, 'X')
    patched = bytearray(resource.data)
    touched = 0
    changed = 0
    for (atomic_index, part_index), obj in sorted(meshes.items()):
        if atomic_index < 0 or atomic_index >= len(entry['objects']):
            raise ValueError(f'Invalid MH2 atomic index {atomic_index}')
        atomic = entry['objects'][atomic_index]
        if part_index < 0 or part_index >= len(atomic['parts']):
            raise ValueError(f'Invalid MH2 part index {part_index}')
        part = atomic['parts'][part_index]
        vertices = obj.data.vertices
        if len(vertices) != len(part['vertices']):
            raise ValueError(f'{obj.name}: topology changed ({len(vertices)} versus {len(part["vertices"])} source vertices)')
        if len(obj.data.polygons) != len(part['faces']):
            raise ValueError(f'{obj.name}: face count changed; source-preserving MH2 export cannot rebuild strips')
        face_count = len(part['faces'])
        if len(obj.data.loops) != face_count * 3:
            raise ValueError(f'{obj.name}: source-preserving MH2 export requires unchanged triangles')
        source_indices = np.asarray(part['faces'], dtype=np.int32).reshape(-1)
        current_indices = np.empty(len(obj.data.loops), dtype=np.int32)
        obj.data.loops.foreach_get('vertex_index', current_indices)
        if not np.array_equal(current_indices, source_indices):
            first_difference = int(np.flatnonzero(current_indices != source_indices)[0]) // 3
            raise ValueError(f'{obj.name}: face {first_difference} topology or winding differs from the source')

        weighted = any(part['weights'])
        uv_values, normal_values, color_values = mh2ConsoleCornerValues(obj, part)
        parent_record = bones_by_offset.get(atomic['parent'])
        parent_inverse = None
        if parent_record is not None and not weighted:
            parent_inverse = Matrix(tuple(tuple(parent_record['matrix'][column * 4 + row]
                                          for column in range(4)) for row in range(4))).inverted_safe()
        position_matrix = inverse_rotation @ obj.matrix_world
        if parent_inverse is not None:
            position_matrix = parent_inverse @ position_matrix
        normal_matrix = position_matrix.to_3x3().inverted().transposed()

        for vertex_index, vertex in enumerate(vertices):
            position = position_matrix @ Vector(vertex.co)
            source_position = part['vertices'][vertex_index]
            description = f'{obj.name}: vertex {vertex_index}'
            vertex_changed = False
            if any(abs(float(position[axis]) - float(source_position[axis])) >
                   1.0e-6 * max(1.0, abs(float(source_position[axis]))) for axis in range(3)):
                offset, encoded = encodeMh2Position(position, part, vertex_index, atomic['platform'])
                mh2ConsoleWrite(patched, resource.end, offset, encoded, description + ' position')
                vertex_changed = True

            uv = uv_values[vertex_index]
            if uv is not None:
                native_uv = (float(uv[0]), 1.0 - float(uv[1]))
                old_uv = part['uvs'][vertex_index]
                if max(abs(native_uv[axis] - old_uv[axis]) for axis in range(2)) > 0.00001:
                    address = part['uv_sources'][vertex_index]
                    width = part['uv_component_sizes'][vertex_index]
                    if address is None:
                        raise ValueError(description + ': native format has no UV stream')
                    encoded = mh2ConsoleEncodeUv(native_uv, width, part['uv_scales'][vertex_index], description)
                    mh2ConsoleWrite(patched, resource.end, address, encoded, description + ' UV')
                    vertex_changed = True

            if normal_values[vertex_index] is not None:
                native_normal = normal_matrix @ Vector(normal_values[vertex_index])
                old_normal = Vector(part['normals'][vertex_index])
                if native_normal.length > 0.000001 and old_normal.length > 0.000001:
                    native_normal.normalize()
                    old_normal.normalize()
                    if max(abs(float(native_normal[axis]) - float(old_normal[axis])) for axis in range(3)) > 0.008:
                        address = part['normal_sources'][vertex_index]
                        width = part['normal_component_sizes'][vertex_index]
                        if address is None:
                            raise ValueError(description + ': native format has no normal stream')
                        encoded = mh2ConsoleEncodeNormal(native_normal, width, description)
                        mh2ConsoleWrite(patched, resource.end, address, encoded, description + ' normal')
                        vertex_changed = True

            color = color_values[vertex_index]
            if color is not None:
                old_color = part['colors'][vertex_index]
                if max(abs(float(color[axis]) * 255.0 - float(old_color[axis])) for axis in range(4)) > 1.5:
                    address = part['color_sources'][vertex_index]
                    if address is None:
                        raise ValueError(description + ': native format has no vertex-color stream')
                    encoded = mh2ConsoleEncodeColor(color, atomic['platform'], part['color_formats'][vertex_index])
                    mh2ConsoleWrite(patched, resource.end, address, encoded, description + ' vertex color')
                    vertex_changed = True

            if weighted:
                influences, skin_changed = mh2ConsoleSourceWeights(entry, obj, part, vertex_index)
                if skin_changed:
                    address, encoded = mh2ConsoleEncodeWeights(
                        influences, part, vertex_index, atomic['platform'], description
                    )
                    mh2ConsoleWrite(patched, resource.end, address, encoded, description + ' skin weights')
                    vertex_changed = True
            touched += 1
            if vertex_changed:
                changed += 1

    if not touched:
        raise ValueError('No MH2 vertices were available to export')

    # Validate every rewritten pointer and the complete container before writing.
    _, verified_entries = readModel(bytes(patched), platform='AUTO')
    verified_entry = verified_entries[clump_index]
    for (atomic_index, part_index), obj in meshes.items():
        original_part = entry['objects'][atomic_index]['parts'][part_index]
        written_part = verified_entry['objects'][atomic_index]['parts'][part_index]
        if len(written_part['vertices']) != len(original_part['vertices']):
            raise ValueError(f'{obj.name}: MH2 round-trip vertex count changed')
        if written_part['faces'] != original_part['faces']:
            raise ValueError(f'{obj.name}: MH2 round-trip changed the native strip topology')
    resource.write(output_path, bytes(patched))
    return len(meshes), touched, changed


def exportMh2PcPositions(root, output_path):
    original = loadMh2NativeModel(root)
    payload, compressed_offset, compressed_suffix = decodePmlcContainer(original)

    patched = bytearray(payload)
    inverse_rotation = Matrix.Rotation(-math.pi / 2.0, 4, 'X')
    changed = 0
    processed = 0
    mesh_count = 0
    mesh_objects = [obj for obj in root.children_recursive
                    if obj.type == 'MESH' and 'bleeds_mh2_vertex_start' in obj]
    if not mesh_objects:
        raise ValueError('No MH2 PC mesh source offsets found; reimport this MDL')
    occupied = set()
    for obj in mesh_objects:
        count = int(obj.get('bleeds_mh2_num_vertices', -1))
        stride = int(obj.get('bleeds_mh2_vertex_stride', 0))
        start = int(obj['bleeds_mh2_vertex_start'])
        element_type = int(obj.get('bleeds_mh2_vertex_element_type', -1))
        layout = {0x52: 24, 0x152: 32, 0x252: 40, 0x115E: 52, 0x125E: 60}
        uv_offsets = {
            0x52: (), 0x152: (0x18,), 0x252: (0x18, 0x20),
            0x115E: (0x2C,), 0x125E: (0x2C, 0x34),
        }
        if element_type not in layout or stride < layout[element_type]:
            raise ValueError(f'{obj.name}: unknown vertex layout; cannot safely write positions')
        if obj.get('bleeds_mh2_invalid_vertex_count', 0):
            raise ValueError(f'{obj.name}: source contains invalid vertices; export is unsafe')
        parent_inverse = None
        if int(obj.get('bleeds_mh2_parent_bone_offset', 0)):
            original_parent = obj.get('bleeds_mh2_import_parent_matrix')
            if original_parent is None or len(original_parent) != 16:
                raise ValueError(f'{obj.name}: original parent-bone transform is unavailable; reimport with this version')
            parent_matrix = Matrix(tuple(
                tuple(float(original_parent[row * 4 + column]) for column in range(4))
                for row in range(4)
            ))
            if abs(parent_matrix.determinant()) < 1.0e-12:
                raise ValueError(f'{obj.name}: parent-bone matrix is singular')
            parent_inverse = parent_matrix.inverted()
        if count != len(obj.data.vertices) or count < 0 or start < 0 or start + stride * count > len(patched):
            raise ValueError(f'{obj.name}: vertex count or source buffer bounds changed')
        object_start = int(obj.get('bleeds_mh2_object_data_offset', 0))
        header_size = int(obj.get('bleeds_mh2_object_header_size', 0))
        material_stride = int(obj.get('bleeds_mh2_material_id_size', 0))
        if not object_start or not header_size or material_stride < 0 or object_start + header_size > len(patched):
            raise ValueError(f'{obj.name}: invalid object header source offsets')
        face_count = int(obj.get('bleeds_mh2_num_face_indices', 0)) // 3
        face_start = start - face_count * 6
        if face_start < object_start + header_size or len(obj.data.polygons) != face_count:
            raise ValueError(f'{obj.name}: face count changed or face buffer invalid')
        for face_index, polygon in enumerate(obj.data.polygons):
            native_face = struct.unpack_from('<3H', patched, face_start + face_index * 6)
            if tuple(polygon.vertices) != native_face:
                raise ValueError(f'{obj.name}: face {face_index} indices/winding changed')
        uv_by_vertex = []
        loop_vertex_indices = np.empty(len(obj.data.loops), dtype=np.int32)
        if uv_offsets[element_type]:
            obj.data.loops.foreach_get('vertex_index', loop_vertex_indices)
        for uv_layer_index, uv_offset in enumerate(uv_offsets[element_type]):
            if uv_layer_index >= len(obj.data.uv_layers):
                uv_by_vertex.append(None)
                continue
            layer = obj.data.uv_layers[uv_layer_index]
            vertex_uvs = [None] * count
            loop_uvs = np.empty(len(loop_vertex_indices) * 2, dtype=np.float32)
            layer.data.foreach_get('uv', loop_uvs)
            loop_uvs = loop_uvs.reshape((-1, 2))
            for loop_index, vertex_index in enumerate(loop_vertex_indices):
                vertex_index = int(vertex_index)
                uv = (float(loop_uvs[loop_index, 0]), float(loop_uvs[loop_index, 1]))
                previous = vertex_uvs[vertex_index]
                if previous is not None and any(abs(uv[axis] - previous[axis]) > 1.0e-5 for axis in range(2)):
                    raise ValueError(f'{obj.name}: UV{uv_layer_index + 1} has split coordinates on vertex '
                                     f'{vertex_index}; native vertex duplication is required')
                vertex_uvs[vertex_index] = uv
            uv_by_vertex.append(vertex_uvs)
        buffer_key = (start, stride, count)
        if buffer_key in occupied:
            raise ValueError(f'{obj.name}: duplicate MH2 source vertex buffer')
        occupied.add(buffer_key)
        mesh_position_changed = False
        for vertex_index, vertex in enumerate(obj.data.vertices):
            position = obj.matrix_world @ Vector(vertex.co)
            if parent_inverse is not None:
                position = parent_inverse @ position
            position = inverse_rotation @ position
            if not all(math.isfinite(float(value)) and abs(float(value)) < 100000.0 for value in position):
                raise ValueError(f'{obj.name}: invalid vertex {vertex_index} position')
            offset = start + vertex_index * stride
            old = struct.unpack_from('<3f', patched, offset)
            vertex_changed = False
            if any(abs(float(position[axis]) - old[axis]) > 1.0e-6 for axis in range(3)):
                struct.pack_into('<3f', patched, offset, *position)
                vertex_changed = True
                mesh_position_changed = True
            for uv_layer_index, uv_offset in enumerate(uv_offsets[element_type]):
                uv_values = uv_by_vertex[uv_layer_index]
                if uv_values is None or uv_values[vertex_index] is None:
                    continue
                u_value, blender_v = uv_values[vertex_index]
                original_uv = (u_value, 1.0 - blender_v)
                if not all(math.isfinite(value) and abs(value) < 10000.0 for value in original_uv):
                    raise ValueError(f'{obj.name}: invalid UV at vertex {vertex_index}')
                old_uv = struct.unpack_from('<2f', patched, offset + uv_offset)
                if any(abs(original_uv[axis] - old_uv[axis]) > 1.0e-6 for axis in range(2)):
                    struct.pack_into('<2f', patched, offset + uv_offset, *original_uv)
                    vertex_changed = True
            if vertex_changed:
                changed += 1
            processed += 1
        if mesh_position_changed:
            world_matrix = inverse_rotation @ obj.matrix_world
            world_positions = [tuple(world_matrix @ Vector(vertex.co)) for vertex in obj.data.vertices]
            bounds_min = [min(point[axis] for point in world_positions) for axis in range(3)]
            bounds_max = [max(point[axis] for point in world_positions) for axis in range(3)]
            center = tuple((bounds_min[axis] + bounds_max[axis]) * 0.5 for axis in range(3))
            half_height = (bounds_max[1] - bounds_min[1]) * 0.5
            original_bounds = struct.unpack_from('<4f', patched, object_start + 0x34)
            if any(abs(value - previous) > 0.00001 for value, previous in zip((*center, half_height), original_bounds)):
                struct.pack_into('<4f', patched, object_start + 0x34, *center, half_height)
            material_count = int(obj.get('bleeds_mh2_source_material_record_count', 0))
            if not 0 < material_count <= 4096 or material_stride < 32:
                raise ValueError(f'{obj.name}: original native material bounds are unavailable')
            positions = [struct.unpack_from('<3f', patched, start + i * stride) for i in range(count)]
            for record_index in range(material_count):
                record_start = object_start + header_size + record_index * material_stride
                index_count, material_id, index_offset = struct.unpack_from('<3H', patched, record_start + 24)
                if index_count % 3 or index_offset % 3 or index_offset + index_count > face_count * 3:
                    raise ValueError(f'{obj.name}: native material face range is invalid')
                indices = struct.unpack_from('<{}H'.format(index_count), patched, face_start + index_offset * 2)
                if not indices:
                    continue
                if any(index >= count for index in indices):
                    raise ValueError(f'{obj.name}: invalid native material vertex index')
                selected = [positions[index] for index in indices]
                bounds = tuple(min(point[axis] for point in selected) for axis in range(3)) + tuple(
                    max(point[axis] for point in selected) for axis in range(3)
                )
                original_record_bounds = struct.unpack_from('<6f', patched, record_start)
                if any(abs(value - previous) > 0.00001 for value, previous in zip(bounds, original_record_bounds)):
                    struct.pack_into('<6f', patched, record_start, *bounds)
        mesh_count += 1

    result = bytes(patched)
    if not changed:
        result = original
    elif compressed_offset is not None:
        result = original[:compressed_offset] + zlib.compress(result) + compressed_suffix
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', dir=str(destination.parent), 
                                         prefix=destination.name + '.', suffix='.tmp', 
                                         delete=False) as temporary:
            temporary_path = temporary.name
            temporary.write(result)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)
    return mesh_count, processed, changed


VERTEX_LAYOUTS = {
    0x52: (24, ()),
    0x152: (32, (24,)),
    0x252: (40, (24, 32)),
    0x115E: (52, (44,)),
    0x125E: (60, (44, 52)),
}


def readPcContainer(raw):
    if raw[:4] not in (b'PMLC', b'Z2HM'):
        raise ValueError('MH2 PC rebuild requires a PMLC or Z2HM source')
    data, offset, unused_data = decodePmlcContainer(raw)
    return data, raw[:8] if offset is not None else None, unused_data


def sourcePositionMatrix(obj):
    rotation_inverse = Matrix.Rotation(-math.pi / 2.0, 4, 'X')
    parent_values = obj.get('bleeds_mh2_import_parent_matrix')
    if int(obj.get('bleeds_mh2_parent_bone_offset', 0)) == 0:
        return rotation_inverse
    if parent_values is None or len(parent_values) != 16:
        raise ValueError(f'{obj.name}: missing original parent-bone transform')
    parent_matrix = Matrix(tuple(
        tuple(float(parent_values[row * 4 + column]) for column in range(4))
        for row in range(4)
    ))
    if abs(parent_matrix.determinant()) < 1.0e-12:
        raise ValueError(f'{obj.name}: non-invertible parent-bone transform')
    return rotation_inverse @ parent_matrix.inverted()


def mh2FaceMaterialIndex(obj, face_index, source_index=None):
    mesh = obj.data
    current = int(mesh.polygons[face_index].material_index)
    materials = getattr(mesh, 'materials', None)
    if materials is not None and len(materials) > 0:
        return current
    if current != 0:
        return current

    attributes = getattr(mesh, 'attributes', None)
    if attributes is not None:
        attribute = attributes.get('bleeds_mh2_source_material_index')
        if attribute is not None and len(attribute.data) > face_index:
            return int(attribute.data[face_index].value)

    get_property = getattr(mesh, 'get', None)
    source_indices = get_property('bleeds_mh2_source_face_material_indices', None) if callable(get_property) else None
    if source_indices is not None and face_index < len(source_indices):
        return int(source_indices[face_index])
    if source_index is not None:
        return int(source_index)
    return current


def encodePcGeometry(obj, source):
    old_start = int(obj.get('bleeds_mh2_object_data_offset', -1))
    header_size = int(obj.get('bleeds_mh2_object_header_size', 0))
    record_stride = int(obj.get('bleeds_mh2_material_id_size', 0))
    record_count = int(obj.get('bleeds_mh2_source_material_record_count', -1))
    vertex_stride = int(obj.get('bleeds_mh2_vertex_stride', 0))
    vertex_type = int(obj.get('bleeds_mh2_vertex_element_type', -1))
    old_vertex_start = int(obj.get('bleeds_mh2_vertex_start', -1))
    old_vertex_count = int(obj.get('bleeds_mh2_source_vertex_count', -1))
    if vertex_type not in VERTEX_LAYOUTS:
        raise ValueError(f'{obj.name}: unsupported native vertex type 0x{vertex_type:X}')
    minimum_stride, uv_offsets = VERTEX_LAYOUTS[vertex_type]
    if vertex_stride < minimum_stride or header_size != 180 or record_stride != 44:
        raise ValueError(f'{obj.name}: unsupported MH2 PC geometry layout')
    if record_count < 1 or record_count > 4096 or old_vertex_count < 0:
        raise ValueError(f'{obj.name}: invalid source mesh counts')
    if old_start < 48 or old_vertex_start < 48 or old_vertex_start + old_vertex_count * vertex_stride > len(source):
        raise ValueError(f'{obj.name}: native source vertex buffer is out of bounds')

    mesh = obj.data
    mesh.calc_loop_triangles()
    if any(len(poly.vertices) < 3 for poly in mesh.polygons):
        raise ValueError(f'{obj.name}: mesh contains degenerate polygons')
    active_uv_layers = list(mesh.uv_layers)[:len(uv_offsets)]
    color_layer = None
    if getattr(mesh, 'color_attributes', None):
        color_layer = (mesh.color_attributes.get('Color') or mesh.color_attributes.get('Col')
                       or mesh.color_attributes.active_color)

    def cornerNormal(loop_index, vertex_index):
        if hasattr(mesh, 'corner_normals') and len(mesh.corner_normals) > loop_index:
            return Vector(mesh.corner_normals[loop_index].vector)
        loop = mesh.loops[loop_index]
        if hasattr(loop, 'normal'):
            return Vector(loop.normal)
        return Vector(mesh.vertices[vertex_index].normal)

    def cornerColor(loop_index, vertex_index):
        if color_layer is None:
            return None
        color_index = loop_index if color_layer.domain == 'CORNER' else vertex_index
        return tuple(float(channel) for channel in color_layer.data[color_index].color)

    position_matrix = sourcePositionMatrix(obj) @ obj.matrix_world
    world_position_matrix = Matrix.Rotation(-math.pi / 2.0, 4, 'X') @ obj.matrix_world
    normal_matrix = position_matrix.to_3x3().inverted().transposed()
    source_vertices = memoryview(source)
    vertex_group_names = [group.name for group in obj.vertex_groups]
    vertex_map = {}
    base_vertex_count = min(len(mesh.vertices), old_vertex_count)
    rows = [bytes(source_vertices[
        old_vertex_start + index * vertex_stride:
        old_vertex_start + (index + 1) * vertex_stride
    ]) for index in range(base_vertex_count)]
    positions = [tuple(position_matrix @ Vector(mesh.vertices[index].co))
                 for index in range(base_vertex_count)]
    world_positions = [tuple(world_position_matrix @ Vector(mesh.vertices[index].co))
                       for index in range(base_vertex_count)]
    assigned_source_vertices = set()
    old_records_start = old_start + header_size
    old_records_end = old_records_start + record_count * record_stride
    if old_records_end > len(source):
        raise ValueError(f'{obj.name}: native material-ID records are truncated')
    record_material_ids = [struct.unpack_from('<H', source, old_records_start + index * record_stride + 26)[0]
                           for index in range(record_count)]
    material_record_lookup = {}
    for record_index, material_id in enumerate(record_material_ids):
        material_record_lookup.setdefault(material_id, record_index)
    native_material_count = struct.unpack_from('<I', source, old_start + 4)[0]
    if native_material_count < 1 or native_material_count > 4096:
        raise ValueError(f'{obj.name}: invalid native material table')
    source_face_materials = {}
    for record_index in range(record_count):
        record_start = old_records_start + record_index * record_stride
        index_count, material_id, first_index = struct.unpack_from('<3H', source, record_start + 24)
        for face_index in range(first_index // 3, (first_index + index_count) // 3):
            source_face_materials[face_index] = int(material_id)
    used_material_ids = {
        mh2FaceMaterialIndex(obj, face_index, source_face_materials.get(face_index))
        for face_index in range(len(mesh.polygons))
    }
    if any(index < 0 or index >= native_material_count for index in used_material_ids):
        raise ValueError(f'{obj.name}: assign faces to one of the {native_material_count} native material slots')
    for material_id in sorted(used_material_ids):
        if material_id not in material_record_lookup:
            material_record_lookup[material_id] = len(record_material_ids)
            record_material_ids.append(material_id)
    faces_by_material = [[] for index in record_material_ids]
    palette_value = obj.get('bleeds_mh2_skin_palette_names', '[]')
    if isinstance(palette_value, str):
        palette = json.loads(palette_value)
    else:
        palette = list(palette_value)
    if not isinstance(palette, list):
        raise ValueError(f'{obj.name}: native skin palette is invalid')
    palette_by_name = {}
    for index, name in enumerate(palette):
        if name:
            palette_by_name.setdefault(str(name), index)

    for triangle in mesh.loop_triangles:
        polygon = mesh.polygons[triangle.polygon_index]
        material_index = mh2FaceMaterialIndex(
            obj, triangle.polygon_index, source_face_materials.get(triangle.polygon_index)
        )
        if material_index not in material_record_lookup:
            raise ValueError(f'{obj.name}: material {material_index} needs a new native material record')
        material_record_index = material_record_lookup[material_index]
        face_indices = []
        for loop_index in triangle.loops:
            loop = mesh.loops[loop_index]
            vertex_index = int(loop.vertex_index)
            uv_values = tuple(tuple(float(value) for value in layer.data[loop_index].uv)
                              for layer in active_uv_layers)
            uv_values += ((0.0, 0.0),) * (len(uv_offsets) - len(uv_values))
            normal = cornerNormal(loop_index, vertex_index)
            color = cornerColor(loop_index, vertex_index)
            key = (vertex_index, uv_values, tuple(normal), color)
            if key not in vertex_map:
                if vertex_index < base_vertex_count and vertex_index not in assigned_source_vertices:
                    native_index = vertex_index
                    assigned_source_vertices.add(vertex_index)
                else:
                    native_index = len(rows)
                    if native_index >= 65535:
                        raise ValueError(f'{obj.name}: MH2 PC uses 16-bit face indices (maximum 65535 vertices)')
                vertex = mesh.vertices[vertex_index]
                position = position_matrix @ Vector(vertex.co)
                if not all(math.isfinite(value) and abs(value) < 100000.0 for value in position):
                    raise ValueError(f'{obj.name}: vertex {vertex_index} has invalid coordinates')
                if vertex_index < old_vertex_count:
                    row_start = old_vertex_start + vertex_index * vertex_stride
                    row = bytearray(source_vertices[row_start:row_start + vertex_stride])
                else:
                    row = bytearray(vertex_stride)
                preserve_source = vertex_index < old_vertex_count
                if not preserve_source or any(
                    abs(float(position[axis]) - source_value) > 0.000001
                    for axis, source_value in enumerate(struct.unpack_from('<3f', row, 0))
                ):
                    struct.pack_into('<3f', row, 0, *position)
                for uv_offset, uv in zip(uv_offsets, uv_values):
                    native_uv = (uv[0], 1.0 - uv[1])
                    if not all(math.isfinite(value) and abs(value) < 10000.0 for value in native_uv):
                        raise ValueError(f'{obj.name}: invalid UV coordinates')
                    source_uv = struct.unpack_from('<2f', row, uv_offset)
                    if not preserve_source or any(
                        abs(float(native_uv[axis]) - source_uv[axis]) > 0.000001
                        for axis in range(2)
                    ):
                        struct.pack_into('<2f', row, uv_offset, *native_uv)

                native_normal = normal_matrix @ normal
                if not all(math.isfinite(float(axis)) for axis in native_normal):
                    raise ValueError(f'{obj.name}: vertex {vertex_index} has a non-finite normal')
                if native_normal.length > 0.000001:
                    native_normal.normalize()
                normal_offset = 32 if vertex_type in (0x115E, 0x125E) else 12
                source_normal = struct.unpack_from('<3h', row, normal_offset)
                source_normal_vector = Vector(tuple(float(value) / 32768.0 for value in source_normal))
                if source_normal_vector.length > 0.000001:
                    source_normal_vector.normalize()
                normal_is_unchanged = preserve_source and (
                    native_normal.length <= 0.000001 or all(
                        abs(float(native_normal[axis]) - float(source_normal_vector[axis])) < 0.0001
                        for axis in range(3)
                    )
                )
                if not normal_is_unchanged:
                    normal_components = [max(-32768, min(32767, round(float(axis) * 32767)))
                                         for axis in native_normal]
                    struct.pack_into('<3h', row, normal_offset, *normal_components)
                    if not preserve_source:
                        struct.pack_into('<h', row, normal_offset + 6, 0)

                if color is not None:
                    color_offset = 40 if vertex_type in (0x115E, 0x125E) else 20
                    source_bgra = struct.unpack_from('<4B', row, color_offset)
                    source_rgba = tuple(float(source_bgra[index]) / 255.0 for index in (2, 1, 0, 3))
                    color_is_unchanged = preserve_source and all(
                        abs(float(color[axis]) - source_rgba[axis]) < 0.0015
                        for axis in range(4)
                    )
                    if not color_is_unchanged:
                        rgba = [max(0, min(255, round(float(channel) * 255))) for channel in color]
                        struct.pack_into('<4B', row, color_offset, rgba[2], rgba[1], rgba[0], rgba[3])

                if vertex_type in (0x115E, 0x125E):
                    influences = {}
                    for membership in vertex.groups:
                        if membership.group < 0 or membership.group >= len(vertex_group_names):
                            raise ValueError(f'{obj.name}: vertex {vertex_index} references an invalid bone group')
                        group_name = vertex_group_names[membership.group]
                        if not math.isfinite(float(membership.weight)):
                            raise ValueError(f'{obj.name}: vertex {vertex_index} has a non-finite skin weight')
                        palette_index = palette_by_name.get(group_name)
                        if palette_index is None and membership.weight > 0.000001:
                            raise ValueError(f'{obj.name}: bone group {group_name!r} is missing from its native palette')
                        if palette_index is not None and membership.weight > 0.000001:
                            if palette_index > 255:
                                raise ValueError(f'{obj.name}: native bone palette index exceeds eight bits')
                            influences[palette_index] = influences.get(palette_index, 0.0) + float(membership.weight)
                    if not influences:
                        if not preserve_source or vertex.groups:
                            raise ValueError(f'{obj.name}: skinned vertex {vertex_index} has no bone weights')
                        previous_weights = struct.unpack_from('<4f', row, 12)
                        previous_indices = struct.unpack_from('<4B', row, 28)
                        for index, weight in zip(previous_indices, previous_weights):
                            if weight > 0.000001:
                                influences[index] = influences.get(index, 0.0) + weight
                        if not influences:
                            raise ValueError(f'{obj.name}: skinned vertex {vertex_index} has no native weights')
                    total = sum(influences.values())
                    if total <= 0 or not math.isfinite(total):
                        raise ValueError(f'{obj.name}: vertex {vertex_index} has invalid bone weights')
                    influences = {index: weight / total for index, weight in influences.items()}
                    previous_weights = struct.unpack_from('<4f', row, 12)
                    previous_indices = struct.unpack_from('<4B', row, 28)
                    previous_influences = {}
                    for bone_index, weight in zip(previous_indices, previous_weights):
                        if weight > 0.000001:
                            previous_influences[bone_index] = previous_influences.get(bone_index, 0.0) + weight
                    skin_is_unchanged = preserve_source and (
                        set(previous_influences) == set(influences)
                        and all(abs(previous_influences[index] - influences[index]) < 0.0001
                                for index in influences)
                    )
                    if not skin_is_unchanged:
                        items = sorted(influences.items(), key=lambda item: item[1], reverse=True)[:4]
                        total = sum(weight for _, weight in items)
                        native_weights = [weight / total for _, weight in items]
                        native_indices = [index for index, _ in items]
                        native_weights.extend([0.0] * (4 - len(native_weights)))
                        native_indices.extend([0] * (4 - len(native_indices)))
                        struct.pack_into('<4f', row, 12, *native_weights)
                        struct.pack_into('<4B', row, 28, *native_indices)
                vertex_map[key] = native_index
                if native_index < len(rows):
                    rows[native_index] = bytes(row)
                    positions[native_index] = tuple(position)
                    world_positions[native_index] = tuple(world_position_matrix @ Vector(vertex.co))
                else:
                    rows.append(bytes(row))
                    positions.append(tuple(position))
                    world_positions.append(tuple(world_position_matrix @ Vector(vertex.co)))
            face_indices.append(vertex_map[key])
        if len(set(face_indices)) == 3:
            faces_by_material[material_record_index].append(tuple(face_indices))

    referenced_vertex_indices = {key[0] for key in vertex_map}
    for vertex_index, vertex in enumerate(mesh.vertices):
        if vertex_index in referenced_vertex_indices:
            continue
        if vertex_index >= old_vertex_count:
            raise ValueError(f'{obj.name}: new vertex {vertex_index} has no faces; connect it before export')
        row = bytearray(rows[vertex_index])
        position = position_matrix @ Vector(vertex.co)
        original_position = struct.unpack_from('<3f', row, 0)
        if any(abs(float(position[axis]) - original_position[axis]) > 0.000001 for axis in range(3)):
            struct.pack_into('<3f', row, 0, *position)
            rows[vertex_index] = bytes(row)
        positions[vertex_index] = tuple(position)
        world_positions[vertex_index] = tuple(world_position_matrix @ Vector(vertex.co))

    header = bytearray(source[old_start:old_start + header_size])
    records = bytearray(source[old_records_start:old_records_end])
    for material_id in record_material_ids[record_count:]:
        record = bytearray(record_stride)
        struct.pack_into('<H', record, 26, material_id)
        records.extend(record)
    struct.pack_into('<I', header, 0x2C, len(record_material_ids))
    faces = []
    for material_index, material_faces in enumerate(faces_by_material):
        offset = material_index * record_stride
        if (len(faces) + len(material_faces)) * 3 > 65535:
            raise ValueError(f'{obj.name}: native material face-index range overflows 16 bits')
        struct.pack_into('<H', records, offset + 24, len(material_faces) * 3)
        struct.pack_into('<H', records, offset + 26, record_material_ids[material_index])
        struct.pack_into('<H', records, offset + 28, len(faces) * 3)
        selected = [positions[index] for face in material_faces for index in face]
        if selected:
            bounds = [min(point[axis] for point in selected) for axis in range(3)]
            bounds.extend(max(point[axis] for point in selected) for axis in range(3))
            source_bounds = struct.unpack_from('<6f', records, offset)
            needs_new_bounds = any(
                bounds[axis] < source_bounds[axis] - 0.00001
                or bounds[axis + 3] > source_bounds[axis + 3] + 0.00001
                for axis in range(3)
            )
            if needs_new_bounds:
                struct.pack_into('<6f', records, offset, *bounds)
        faces.extend(material_faces)
    struct.pack_into('<I', header, 0x30, len(faces) * 3)
    struct.pack_into('<I', header, 0x50, len(rows))
    if world_positions:
        bounds_min = [min(position[axis] for position in world_positions) for axis in range(3)]
        bounds_max = [max(position[axis] for position in world_positions) for axis in range(3)]
        center = tuple((bounds_min[axis] + bounds_max[axis]) * 0.5 for axis in range(3))
        half_height = (bounds_max[1] - bounds_min[1]) * 0.5
        original_bounds = struct.unpack_from('<4f', header, 0x34)
        if any(abs(value - previous) > 0.00001 for value, previous in zip((*center, half_height), original_bounds)):
            struct.pack_into('<4f', header, 0x34, *center, half_height)
    block = bytearray(header)
    block.extend(records)
    face_pack = struct.Struct('<3H').pack
    block.extend(b''.join(face_pack(*face) for face in faces))
    block.extend(b''.join(rows))
    struct.pack_into('<I', block, 0x24, len(block) - 32)
    block.extend(bytes((-len(block)) % 4))
    return bytes(block), len(rows), len(faces)


def gatherMh2PcMeshes(root):
    objects = [obj for obj in root.children_recursive if getattr(obj, 'type', None) == 'MESH']
    by_offset = {}
    new_objects = []
    for obj in objects:
        offset = int(obj.get('bleeds_mh2_objinfo_offset', 0))
        if not offset:
            new_objects.append(obj)
            continue
        if offset in by_offset:
            raise ValueError('Two meshes use the same MH2 part: ' + str(obj.name))
        by_offset[offset] = obj

    stored_slots = root.get('bleeds_mh2_part_slots', '[]')
    try:
        slots = json.loads(stored_slots) if isinstance(stored_slots, str) else list(stored_slots)
    except (ValueError, TypeError) as exc:
        raise ValueError('MH2 part assignments are invalid: ' + str(exc)) from exc
    missing = []
    for slot in slots:
        properties = slot.get('properties', {})
        offset = int(properties.get('bleeds_mh2_objinfo_offset', 0))
        if offset and offset not in by_offset:
            missing.append(slot)

    # A replacement mesh can be parented to the MH2 root without retaining
    # the original Blender mesh object. Preserve the native part identity.
    for obj in new_objects:
        if not missing:
            raise ValueError(f'{obj.name}: no unused MH2 mesh part is available. Edit or replace the mesh data on an existing part.')
        if len(missing) > 1:
            names = [slot for slot in missing if slot.get('name') == obj.name]
            if len(names) == 1:
                slot = names[0]
            elif len(new_objects) == len(missing):
                slot = missing[0]
            else:
                raise ValueError(f'{obj.name}: several native part slots are free; set bleeds_mh2_objinfo_offset to choose a part')
        else:
            slot = missing[0]
        missing.remove(slot)
        properties = slot['properties']
        for key, value in properties.items():
            if key not in obj:
                obj[key] = value
        by_offset[int(properties['bleeds_mh2_objinfo_offset'])] = obj

    if not by_offset:
        raise ValueError('No MH2 PC mesh parts found beneath the selected root')
    return by_offset


def validateMh2PcRebuild(rebuilt, source_blocks):
    from ..rwLib.dff import Resource

    resource = Resource(rebuilt, b'PMLC')
    for object_info_offset, source_block in source_blocks.items():
        object_info_offset = int(object_info_offset)
        resource.check(object_info_offset, 28)
        object_offset = resource.uint(object_info_offset + 12)
        resource.check(object_offset, 180)
        material_count = resource.uint(object_offset + 0x2C)
        native_material_count = resource.uint(object_offset + 4)
        index_count = resource.uint(object_offset + 0x30)
        vertex_count = resource.uint(object_offset + 0x50)
        vertex_stride = resource.uint(object_offset + 0x60)
        vertex_type = resource.uint(object_offset + 0x90)
        if not 0 < material_count <= 4096 or not 0 < native_material_count <= 4096:
            raise ValueError(f'MH2 rebuilt mesh 0x{object_info_offset:X} has an invalid material table')
        if not 0 < vertex_count <= 65535 or vertex_type not in VERTEX_LAYOUTS:
            raise ValueError(f'MH2 rebuilt mesh 0x{object_info_offset:X} has an invalid vertex format')
        if vertex_stride < VERTEX_LAYOUTS[vertex_type][0] or index_count % 3:
            raise ValueError(f'MH2 rebuilt mesh 0x{object_info_offset:X} has invalid face data')
        index_start = object_offset + 180 + material_count * 44
        vertex_start = index_start + index_count * 2
        resource.check(vertex_start, vertex_count * vertex_stride)
        index_buffer = struct.unpack_from('<{}H'.format(index_count), resource.data, index_start)
        if any(index >= vertex_count for index in index_buffer):
            raise ValueError(f'MH2 rebuilt mesh 0x{object_info_offset:X} has an invalid vertex index')
        face_total = 0
        for record_index in range(material_count):
            record_offset = object_offset + 180 + record_index * 44
            count, material_index, start = struct.unpack_from('<3H', resource.data, record_offset + 24)
            if material_index >= native_material_count:
                raise ValueError(f'MH2 rebuilt mesh 0x{object_info_offset:X} uses an invalid material')
            if count % 3 or start != face_total or start + count > index_count:
                raise ValueError(f'MH2 rebuilt mesh 0x{object_info_offset:X} has an invalid face range')
            face_total += count
        if face_total != index_count:
            raise ValueError(f'MH2 rebuilt mesh 0x{object_info_offset:X} has unassigned faces')
        expected_vertex_count = struct.unpack_from('<I', source_block, 0x50)[0]
        expected_index_count = struct.unpack_from('<I', source_block, 0x30)[0]
        if vertex_count != expected_vertex_count or index_count != expected_index_count:
            raise ValueError(f'MH2 rebuilt mesh 0x{object_info_offset:X} does not match its exported geometry')
    return True




def mh2GeometryMatchesSource(obj, source, allow_position_uv_changes=False):
    try:
        start = int(obj.get('bleeds_mh2_object_data_offset', -1))
        header_size = int(obj.get('bleeds_mh2_object_header_size', -1))
        record_size = int(obj.get('bleeds_mh2_material_id_size', -1))
        record_count = int(obj.get('bleeds_mh2_source_material_record_count', -1))
        vertex_start = int(obj.get('bleeds_mh2_vertex_start', -1))
        stride = int(obj.get('bleeds_mh2_vertex_stride', -1))
        element_type = int(obj.get('bleeds_mh2_vertex_element_type', -1))
        source_vertex_count = int(obj.get('bleeds_mh2_source_vertex_count', -1))
        if (start < 48 or header_size != 180 or record_size != 44 or record_count < 1
                or element_type not in VERTEX_LAYOUTS or stride < VERTEX_LAYOUTS[element_type][0]):
            return False
        if vertex_start < 48 or source_vertex_count < 1:
            return False
        mesh = obj.data
        index_count = struct.unpack_from('<I', source, start + 0x30)[0]
        source_count = struct.unpack_from('<I', source, start + 0x50)[0]
        if len(mesh.vertices) != source_count or source_vertex_count != source_count:
            return False
        if len(mesh.polygons) * 3 != index_count or len(mesh.loops) != index_count:
            return False
        if vertex_start + source_count * stride > len(source):
            return False
        face_start = start + header_size + record_size * record_count
        if face_start + index_count * 2 != vertex_start:
            return False

        material_by_face = {}
        for record_index in range(record_count):
            record_offset = start + header_size + record_size * record_index
            record_indices, material_id, first_index = struct.unpack_from('<3H', source, record_offset + 24)
            if record_indices % 3 or first_index % 3:
                return False
            for index in range(first_index // 3, (first_index + record_indices) // 3):
                if index in material_by_face:
                    return False
                material_by_face[index] = material_id
        if len(material_by_face) != len(mesh.polygons):
            return False
        for face_index, polygon in enumerate(mesh.polygons):
            source_face = struct.unpack_from('<3H', source, face_start + face_index * 6)
            if len(polygon.vertices) != 3 or tuple(polygon.vertices) != source_face:
                return False
            if mh2FaceMaterialIndex(obj, face_index, material_by_face[face_index]) != int(material_by_face[face_index]):
                return False

        matrix = sourcePositionMatrix(obj) @ obj.matrix_world
        normal_matrix = matrix.to_3x3().inverted().transposed()
        uv_offsets = VERTEX_LAYOUTS[element_type][1]
        if len(mesh.uv_layers) < len(uv_offsets):
            return False
        selected_color = None
        if getattr(mesh, 'color_attributes', None) is not None:
            attributes = mesh.color_attributes
            selected_color = (attributes.get('Color') or attributes.get('Col')
                              or getattr(attributes, 'active_color', None))
        palette = json.loads(obj.get('bleeds_mh2_skin_palette_names', '[]'))
        group_names = [group.name for group in obj.vertex_groups]
        if element_type in (0x115E, 0x125E) and not palette:
            return False
        for vertex_index, vertex in enumerate(mesh.vertices):
            offset = vertex_start + vertex_index * stride
            current_position = matrix @ Vector(vertex.co)
            native_position = struct.unpack_from('<3f', source, offset)
            if (not allow_position_uv_changes and any(
                    abs(float(current_position[axis]) - native_position[axis]) > 0.000005
                    for axis in range(3))):
                return False
            if element_type in (0x115E, 0x125E):
                source_weights = struct.unpack_from('<4f', source, offset + 12)
                source_bones = struct.unpack_from('<4B', source, offset + 28)
                expected_weights = {}
                for bone_index, weight in zip(source_bones, source_weights):
                    if weight > 0.000001:
                        if bone_index >= len(palette):
                            return False
                        name = palette[bone_index]
                        expected_weights[name] = expected_weights.get(name, 0.0) + weight
                current_weights = {}
                for membership in vertex.groups:
                    if membership.group >= len(group_names):
                        return False
                    name = group_names[membership.group]
                    current_weights[name] = current_weights.get(name, 0.0) + membership.weight
                current_weights = {name: weight for name, weight in current_weights.items() if weight > 0.000001}
                total = sum(current_weights.values())
                if total <= 0 or set(current_weights) != set(expected_weights):
                    return False
                if any(abs(current_weights[name] / total - expected_weights[name]) > 0.0001
                       for name in expected_weights):
                    return False

        for loop_index, loop in enumerate(mesh.loops):
            vertex_index = int(loop.vertex_index)
            offset = vertex_start + vertex_index * stride
            for layer, uv_offset in zip(mesh.uv_layers, uv_offsets):
                actual_uv = layer.data[loop_index].uv
                u, v = struct.unpack_from('<2f', source, offset + uv_offset)
                if (not allow_position_uv_changes and (
                        abs(float(actual_uv[0]) - u) > 0.000005
                        or abs(float(actual_uv[1]) - (1.0 - v)) > 0.000005)):
                    return False
            if element_type in (0x115E, 0x125E):
                normal_offset, color_offset = 32, 40
            else:
                normal_offset, color_offset = 12, 20
            source_normal = Vector(tuple(float(value) / 32768.0
                                         for value in struct.unpack_from('<3h', source, offset + normal_offset)))
            if source_normal.length > 0.000001:
                source_normal.normalize()
            try:
                normal = loop.normal
            except AttributeError:
                normal = mesh.vertices[vertex_index].normal
            current_normal = normal_matrix @ Vector(normal)
            if current_normal.length > 0.000001:
                current_normal.normalize()
                if any(abs(float(current_normal[axis]) - float(source_normal[axis])) > 0.001
                       for axis in range(3)):
                    return False
            if selected_color is not None:
                bgra = struct.unpack_from('<4B', source, offset + color_offset)
                expected_color = tuple(float(bgra[index]) / 255.0 for index in (2, 1, 0, 3))
                color_index = loop_index if selected_color.domain == 'CORNER' else vertex_index
                current_color = selected_color.data[color_index].color
                if any(abs(float(current_color[axis]) - expected_color[axis]) > 0.0015
                       for axis in range(4)):
                    return False
        return True
    except (AttributeError, ValueError, TypeError, IndexError, struct.error,
            OverflowError, ZeroDivisionError, RuntimeError, KeyError):
        return False


def writeMh2NativeBytes(output_path, data):
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='wb', dir=str(destination.parent),
            prefix=destination.name + '.', suffix='.tmp', delete=False,
        ) as temporary:
            temporary_path = temporary.name
            temporary.write(data)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def mh2GeometryChanges(obj):
    saved = obj.get('bleeds_mh2_geometry_signature', '')
    if not saved:
        return None
    try:
        previous = json.loads(saved)
    except (TypeError, ValueError):
        return None
    current = mh2GeometryFingerprint(obj)
    if set(previous) != set(current):
        return None
    return {field for field in current if current[field] != previous[field]}


def exportMh2RebuiltModel(root, output_path):
    for obj in root.children_recursive:
        if getattr(obj, 'type', None) == 'MESH' and getattr(obj, 'mode', '') == 'EDIT':
            obj.update_from_editmode()
    root = recoverMh2RootProperties(root)
    original = loadMh2NativeModel(root)
    source, compressed_header, compressed_suffix = readPcContainer(original)
    meshes = gatherMh2PcMeshes(root)
    signatures = {offset: mh2GeometryChanges(obj) for offset, obj in meshes.items()}
    for offset, obj in meshes.items():
        if mh2GeometryMatchesSource(obj, source):
            signatures[offset] = set()
        elif signatures[offset] is None and mh2GeometryMatchesSource(
            obj, source, allow_position_uv_changes=True
        ):
            signatures[offset] = {'positions', 'uv'}
    total_vertices = sum(len(obj.data.vertices) for obj in meshes.values())
    total_faces = sum(len(obj.data.polygons) for obj in meshes.values())

    if signatures and all(changes == set() for changes in signatures.values()):
        writeMh2NativeBytes(output_path, original)
        return len(meshes), total_vertices, total_faces

    if signatures and all(
        changes is not None and changes <= {'positions', 'uv', 'transform'}
        for changes in signatures.values()
    ):
        exportMh2PcPositions(root, output_path)
        return len(meshes), total_vertices, total_faces

    geometry = {}
    for offset, obj in sorted(meshes.items()):
        if signatures[offset] == set():
            continue
        block, vertices, faces = encodePcGeometry(obj, source)
        geometry[offset] = block
    if not geometry:
        raise ValueError('No MH2 PC geometry was found beneath the selected model')

    rebuilt = rebuildPmlcGeometry(source, geometry)
    validateMh2PcRebuild(rebuilt, geometry)
    if compressed_header is not None:
        header = bytearray(compressed_header)
        struct.pack_into('<I', header, 4, len(rebuilt))
        rebuilt = bytes(header) + zlib.compress(rebuilt) + compressed_suffix
    writeMh2NativeBytes(output_path, rebuilt)
    return len(meshes), total_vertices, total_faces

