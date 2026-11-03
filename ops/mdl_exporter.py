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
import os
import struct
import tempfile
import zlib
from pathlib import Path

import numpy as np
from mathutils import Matrix, Vector

from ..rwLib.dff import readModel
from ..leedsLib.native_mdl import decodePmlcContainer, rebuildPmlcGeometry

def findMh2Root(context):
    candidates = []
    active = getattr(context, 'active_object', None) or getattr(context, 'object', None)
    if active is not None:
        candidates.append(active)
    candidates.extend(getattr(context, 'selected_objects', ()))
    for candidate in candidates:
        obj = candidate
        while obj is not None:
            if (obj.get('bleeds_model_game') == 'MH2' and
                    (obj.get('bleeds_is_mdl_root') or obj.get('bleeds_mh2_path')) and
                    (obj.get('bleeds_mh2_path') or obj.get('bleeds_mdl_filepath')) and
                    (obj.get('bleeds_mh2_clump_index') is not None or
                     obj.get('bleeds_mh2_platform') in {'PC', 'PSP'})):
                return obj
            obj = obj.parent
    raise ValueError('Select an imported MH2 model root or one of its mesh parts')


def validateMh2ExportType(root, model_type='AUTO'):
    requested = str(model_type or 'AUTO').upper().strip()
    if requested not in {'AUTO', 'SIM', 'PED', 'CUT'}:
        raise ValueError('Unsupported Manhunt 2 export model class: ' + requested)
    if requested == 'AUTO':
        return

    source_type = str(root.get('bleeds_mh2_model_class', '') or
                      root.get('bleeds_mdl_type', '') or '').upper().strip()
    if source_type not in {'SIM', 'PED', 'CUT'}:
        raise ValueError('Imported Manhunt 2 model class is unavailable; reimport the source MDL')
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


def exportMh2Model(context, output_path: str):
    root = findMh2Root(context)
    if not root.get('bleeds_mh2_path'):
        return exportMh2PcPositions(root, output_path)
    source_path = Path(str(root['bleeds_mh2_path']))
    if not source_path.is_file():
        raise FileNotFoundError(f'MH2 source MDL is missing: {source_path}')
    resource, entries = readModel(source_path.read_bytes(), platform='AUTO')
    clump_index = int(root['bleeds_mh2_clump_index'])
    if clump_index < 0 or clump_index >= len(entries):
        raise ValueError('MH2 source clump index is outside the original model')

    meshes = {}
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
        parent_record = bones_by_offset.get(atomic['parent'])
        parent_inverse = None
        if parent_record is not None and not weighted:
            parent_inverse = Matrix(tuple(tuple(parent_record['matrix'][column * 4 + row]
                                          for column in range(4)) for row in range(4))).inverted_safe()

        for vertex_index, vertex in enumerate(vertices):
            position = inverse_rotation @ Vector(vertex.co)
            if parent_inverse is not None:
                position = parent_inverse @ position
            source_position = part['vertices'][vertex_index]
            if all(abs(float(position[axis]) - float(source_position[axis])) <= 
                   1.0e-6 * max(1.0, abs(float(source_position[axis]))) for axis in range(3)):
                touched += 1
                continue
            offset, encoded = encodeMh2Position(position, part, vertex_index, atomic['platform'])
            if offset < 0 or offset + len(encoded) > resource.end:
                raise ValueError(f'{obj.name}: source vertex offset exceeds MH2 payload')
            patched[offset:offset + len(encoded)] = encoded
            touched += 1
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
    source_path = Path(str(root.get('bleeds_mdl_filepath', '')))
    if not source_path.is_file():
        raise FileNotFoundError(f'MH2 PC source model is missing: {source_path}')
    original = source_path.read_bytes()
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
        for vertex_index, vertex in enumerate(obj.data.vertices):
            position = Vector(vertex.co)
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
    if len(mesh.uv_layers) < len(uv_offsets):
        raise ValueError(f'{obj.name}: missing native UV layers')
    active_uv_layers = list(mesh.uv_layers)[:len(uv_offsets)]
    color_layer = None
    if getattr(mesh, 'color_attributes', None):
        color_layer = mesh.color_attributes.get('Color') or mesh.color_attributes.active_color

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

    position_matrix = sourcePositionMatrix(obj)
    normal_matrix = position_matrix.to_3x3().inverted().transposed()
    source_vertices = memoryview(source)
    vertex_group_names = [group.name for group in obj.vertex_groups]
    vertex_map = {}
    rows = []
    positions = []
    old_records_start = old_start + header_size
    old_records_end = old_records_start + record_count * record_stride
    if old_records_end > len(source):
        raise ValueError(f'{obj.name}: native material-ID records are truncated')
    record_material_ids = [struct.unpack_from('<H', source, old_records_start + index * record_stride + 26)[0]
                           for index in range(record_count)]
    material_record_lookup = {}
    for record_index, material_id in enumerate(record_material_ids):
        material_record_lookup.setdefault(material_id, record_index)
    faces_by_material = [[] for index in range(record_count)]
    palette = list(obj.get('bleeds_mh2_skin_palette_names', []))
    palette_by_name = {}
    for index, name in enumerate(palette):
        if name:
            palette_by_name.setdefault(str(name), index)

    for triangle in mesh.loop_triangles:
        polygon = mesh.polygons[triangle.polygon_index]
        material_index = int(polygon.material_index)
        if material_index not in material_record_lookup:
            raise ValueError(f'{obj.name}: material {material_index} needs a new native material record')
        material_record_index = material_record_lookup[material_index]
        face_indices = []
        for loop_index in triangle.loops:
            loop = mesh.loops[loop_index]
            vertex_index = int(loop.vertex_index)
            uv_values = tuple(tuple(float(value) for value in layer.data[loop_index].uv)
                              for layer in active_uv_layers)
            normal = cornerNormal(loop_index, vertex_index)
            color = cornerColor(loop_index, vertex_index)
            key = (vertex_index, uv_values, tuple(normal), color)
            if key not in vertex_map:
                if len(rows) >= 65535:
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
                struct.pack_into('<3f', row, 0, *position)
                for uv_offset, uv in zip(uv_offsets, uv_values):
                    native_uv = (uv[0], 1.0 - uv[1])
                    if not all(math.isfinite(value) and abs(value) < 10000.0 for value in native_uv):
                        raise ValueError(f'{obj.name}: invalid UV coordinates')
                    struct.pack_into('<2f', row, uv_offset, *native_uv)
                native_normal = normal_matrix @ normal
                if not all(math.isfinite(float(axis)) for axis in native_normal):
                    raise ValueError(f'{obj.name}: vertex {vertex_index} has a non-finite normal')
                if native_normal.length > 0.000001:
                    native_normal.normalize()
                normal_offset = 32 if vertex_type in (0x115E, 0x125E) else 12
                normal_components = [max(-32768, min(32767, round(float(axis) * 32767)))
                                     for axis in native_normal]
                struct.pack_into('<4h', row, normal_offset, *normal_components, 0)
                if color is not None:
                    color_offset = 40 if vertex_type in (0x115E, 0x125E) else 20
                    rgba = [max(0, min(255, round(float(channel) * 255))) for channel in color]
                    struct.pack_into('<4B', row, color_offset, rgba[2], rgba[1], rgba[0], rgba[3])
                if vertex_type in (0x115E, 0x125E):
                    influences = []
                    for membership in vertex.groups:
                        group_name = vertex_group_names[membership.group]
                        if not math.isfinite(float(membership.weight)):
                            raise ValueError(f'{obj.name}: vertex {vertex_index} has a non-finite skin weight')
                        palette_index = palette_by_name.get(group_name)
                        if palette_index is None and membership.weight > 0.000001:
                            raise ValueError(f'{obj.name}: bone group {group_name!r} is missing from its native palette')
                        if palette_index is not None and membership.weight > 0.000001:
                            if palette_index > 255:
                                raise ValueError(f'{obj.name}: native bone palette index exceeds eight bits')
                            influences.append((palette_index, float(membership.weight)))
                    influences.sort(key=lambda item: item[1], reverse=True)
                    if len(influences) > 4:
                        raise ValueError(f'{obj.name}: vertex {vertex_index} exceeds four native skin influences')
                    if influences:
                        total = sum(weight for _, weight in influences)
                        native_weights = [weight / total for _, weight in influences]
                        native_indices = [index for index, _ in influences]
                        native_weights.extend([0.0] * (4 - len(native_weights)))
                        native_indices.extend([0] * (4 - len(native_indices)))
                        struct.pack_into('<4f', row, 12, *native_weights)
                        struct.pack_into('<4B', row, 28, *native_indices)
                    elif vertex_index >= old_vertex_count:
                        raise ValueError(f'{obj.name}: new skinned vertex {vertex_index} has no palette weights')
                vertex_map[key] = len(rows)
                rows.append(bytes(row))
                positions.append(tuple(position))
            face_indices.append(vertex_map[key])
        if len(set(face_indices)) == 3:
            faces_by_material[material_record_index].append(tuple(face_indices))

    header = bytearray(source[old_start:old_start + header_size])
    records = bytearray(source[old_records_start:old_records_end])
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
            struct.pack_into('<6f', records, offset, *bounds)
        faces.extend(material_faces)
    struct.pack_into('<I', header, 0x30, len(faces) * 3)
    struct.pack_into('<I', header, 0x50, len(rows))
    if positions:
        bounds_min = [min(position[axis] for position in positions) for axis in range(3)]
        bounds_max = [max(position[axis] for position in positions) for axis in range(3)]
        center = tuple((bounds_min[axis] + bounds_max[axis]) * 0.5 for axis in range(3))
        radius = max(math.sqrt(sum((position[axis] - center[axis]) ** 2 for axis in range(3)))
                     for position in positions)
        struct.pack_into('<4f', header, 0x34, *center, radius)
    block = bytearray(header)
    block.extend(records)
    face_pack = struct.Struct('<3H').pack
    block.extend(b''.join(face_pack(*face) for face in faces))
    block.extend(b''.join(rows))
    struct.pack_into('<I', block, 0x24, len(block) - 32)
    block.extend(bytes((-len(block)) % 4))
    return bytes(block), len(rows), len(faces)


def exportMh2RebuiltModel(root, output_path):
    source_path = Path(str(root.get('bleeds_mdl_filepath', '')))
    if not source_path.is_file():
        raise FileNotFoundError(f'MH2 source MDL is missing: {source_path}')
    original = source_path.read_bytes()
    source, compressed_header, compressed_suffix = readPcContainer(original)
    geometry = {}
    total_vertices = 0
    total_faces = 0
    for obj in root.children_recursive:
        if obj.type != 'MESH' or 'bleeds_mh2_objinfo_offset' not in obj:
            continue
        offset = int(obj['bleeds_mh2_objinfo_offset'])
        if offset in geometry:
            raise ValueError(f'Duplicate native MH2 object-info offset 0x{offset:X}')
        block, vertices, faces = encodePcGeometry(obj, source)
        geometry[offset] = block
        total_vertices += vertices
        total_faces += faces
    if not geometry:
        raise ValueError('No source-backed MH2 PC geometry was found beneath this root')
    rebuilt = rebuildPmlcGeometry(source, geometry)
    if compressed_header is not None:
        header = bytearray(compressed_header)
        struct.pack_into('<I', header, 4, len(rebuilt))
        rebuilt = bytes(header) + zlib.compress(rebuilt) + compressed_suffix
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile('wb', dir=str(destination.parent), 
                                         prefix=destination.name + '.', suffix='.tmp', 
                                         delete=False) as temporary:
            temporary_path = temporary.name
            temporary.write(rebuilt)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)
    return len(geometry), total_vertices, total_faces

