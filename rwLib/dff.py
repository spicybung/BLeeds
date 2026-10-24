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

import io
import math
import struct

from .chunks import readChunks, readMobileDffChunks


def readGeometry(chunk):
    if chunk.type_id != 0x0F:
        raise ValueError('Expected a RenderWare geometry')
    sections = chunk.children()
    structure = next((item for item in sections if item.type_id == 1), None)
    if structure is None or len(structure.payload) < 16:
        raise ValueError('Missing geometry structure')
    data = structure.payload
    flags, triangle_count, vertex_count, morph_count = struct.unpack_from('<4I', data)
    if flags & 0x01000000:
        raise ValueError('This DFF uses native geometry; its vertex format is not supported yet')
    offset = 16
    version = structure.version
    rw_version = (((version >> 14) & 0x3FF00) + 0x30000) | ((version >> 16) & 0x3F) if version & 0xFFFF0000 else version << 8
    if rw_version < 0x34000:
        offset += 12
    def take(fmt, count):
        nonlocal offset
        stride = struct.calcsize(fmt)
        if count > (len(data) - offset) // stride:
            raise ValueError('Incomplete geometry data')
        values = [struct.unpack_from(fmt, data, offset + index * stride) for index in range(count)]
        offset += count * stride
        return values
    colors = take('<4B', vertex_count) if flags & 8 else []
    uv_count = (flags >> 16) & 255
    if not uv_count:
        uv_count = 2 if flags & 0x80 else int(bool(flags & 4))
    uvs = [take('<2f', vertex_count) for index in range(uv_count)]
    triangles = take('<4H', triangle_count)
    faces = [(item[1], item[0], item[3]) for item in triangles]
    if any(index >= vertex_count for face in faces for index in face):
        raise ValueError('DFF triangle references a missing vertex')
    morphs = []
    for index in range(morph_count):
        sphere = take('<4f', 1)[0]
        has_vertices, has_normals = take('<2I', 1)[0]
        vertex_offset = offset
        vertices = take('<3f', vertex_count) if has_vertices else []
        normal_offset = offset
        normals = take('<3f', vertex_count) if has_normals else []
        if not all(math.isfinite(value) for vector in vertices + normals for value in vector):
            raise ValueError('DFF contains non-finite vertex data')
        morphs.append(dict(sphere=sphere, vertices=vertices, normals=normals,
                           vertex_offset=vertex_offset, normal_offset=normal_offset))
    return dict(flags=flags, vertex_count=vertex_count, faces=faces,
                materials=[item[2] for item in triangles], colors=colors, uvs=uvs,
                morphs=morphs, sections=sections)


def replaceGeometryVertices(chunk, vertices):
    geometry = readGeometry(chunk)
    if len(vertices) != geometry['vertex_count'] or len(geometry['morphs']) != 1:
        raise ValueError('Vertex editing requires unchanged topology and one morph target')
    morph = geometry['morphs'][0]
    if not morph['vertices']:
        raise ValueError('DFF has no editable vertices')
    structure = next(item for item in geometry['sections'] if item.type_id == 1)
    payload = bytearray(structure.payload)
    for index, vertex in enumerate(vertices):
        if len(vertex) != 3 or not all(math.isfinite(value) for value in vertex):
            raise ValueError('Invalid vertex position')
        struct.pack_into('<3f', payload, morph['vertex_offset'] + index * 12, *vertex)
    center = tuple((min(v[axis] for v in vertices) + max(v[axis] for v in vertices)) * 0.5
                   for axis in range(3)) if vertices else (0.0, 0.0, 0.0)
    radius = max((math.sqrt(sum((v[axis] - center[axis]) ** 2 for axis in range(3)))
                  for v in vertices), default=0.0)
    struct.pack_into('<4f', payload, morph['vertex_offset'] - 24, *center, radius)
    structure.payload = bytes(payload)
    chunk.payload = b''.join(section.toBytes() for section in geometry['sections'])
    return chunk


def readLeedsGeometry(chunk):
    from ..leedsLib import native_mdl
    if chunk.version != 0xF00D or len(chunk.payload) < 64:
        raise ValueError('Expected a Leeds mobile geometry block')
    packed = struct.unpack_from('<I', chunk.payload, 16)[0]
    geometry_size = packed & 0xFFFFF
    part_count = packed >> 20
    if not part_count or 64 + part_count * 48 > geometry_size or geometry_size > len(chunk.payload):
        raise ValueError('Invalid Leeds geometry size or part count')
    wrapped = bytearray(32) + chunk.payload[:geometry_size]
    table_offset = len(wrapped)
    wrapped.extend(bytes(part_count * 20))
    struct.pack_into('<II', wrapped, 12, table_offset, part_count)
    for index in range(part_count):
        struct.pack_into('<I', wrapped, table_offset + index * 4, table_offset + part_count * 4 + index * 16)
    context = native_mdl.StoriesMDLContext('', 'PS2', 'PED', game='LCS', file_len=len(wrapped))
    context.log = lambda message: None
    geometry = native_mdl.read_ps2_geometry(context, io.BytesIO(wrapped), 0)
    if len(geometry.parts) != part_count or any(not part.verts for part in geometry.parts):
        raise ValueError('Could not read every part of the Leeds geometry')
    sections = chunk.parsed_children if hasattr(chunk, "parsed_children") else readChunks(chunk.payload[geometry_size:])
    return geometry, sections


def readMaterialNames(sections):
    material_list = next((section for section in sections if section.type_id == 8), None)
    if material_list is None:
        return []
    result = []
    for material in material_list.children():
        if material.type_id != 7:
            continue
        sections = material.children()
        structure = next((section for section in sections if section.type_id == 1), None)
        color = tuple(structure.payload[4:8]) if structure and len(structure.payload) >= 8 else (255, 255, 255, 255)
        texture = next((section for section in sections if section.type_id == 6), None)
        name = ''
        if texture:
            name_chunk = next((section for section in texture.children() if section.type_id == 2), None)
            if name_chunk:
                name = name_chunk.payload.split(b'\0', 1)[0].decode('ascii', errors='replace')
        result.append(dict(name=name, color=color))
    return result


def replaceLeedsVertices(chunk, part_vertices):
    geometry, sections = readLeedsGeometry(chunk)
    if len(part_vertices) != len(geometry.parts):
        raise ValueError('The mobile geometry part count has changed')
    payload = bytearray(chunk.payload)
    scale = (geometry.x_scale, geometry.y_scale, geometry.z_scale)
    translation = geometry.translation
    factor = 0.00003051820313464149
    for part, vertices in zip(geometry.parts, part_vertices):
        if len(vertices) != len(part.verts):
            raise ValueError('Mobile DFF export requires unchanged vertex counts')
        for strip in part.strips_meta:
            offset = strip.source_vertex_offset - 32
            if offset < 0 or offset + strip.vertex_count * 6 > len(payload):
                raise ValueError('Invalid mobile vertex offset')
            for index in range(strip.vertex_count):
                vertex_index = strip.base_vertex_index + index
                vertex = vertices[vertex_index]
                original = part.verts[vertex_index]
                if all(abs(float(vertex[axis]) - original[axis]) < 0.0000001 for axis in range(3)):
                    continue
                raw = []
                for axis in range(3):
                    divisor = scale[axis] * factor
                    if not divisor or not math.isfinite(vertex[axis]):
                        raise ValueError('Invalid mobile vertex scale or position')
                    value = round((float(vertex[axis]) - translation[axis]) / divisor)
                    if not -32768 <= value <= 32767:
                        raise ValueError('Edited vertex exceeds the original mobile geometry bounds')
                    raw.append(value)
                struct.pack_into('<3h', payload, offset + index * 6, *raw)
    chunk.payload = bytes(payload)
    return chunk


def readFrames(chunk):
    sections = chunk.children()
    structure = next((item for item in sections if item.type_id == 1), None)
    if structure is None or len(structure.payload) < 4:
        raise ValueError('Missing DFF frame list')
    data = structure.payload
    count = struct.unpack_from('<I', data)[0]
    if 4 + count * 56 != len(data):
        raise ValueError('Invalid DFF frame list size')
    extensions = [item for item in sections if item.type_id == 3]
    frames = []
    skin_indices = {}
    for extension in extensions:
        for plugin in extension.children():
            if plugin.type_id == 0x11E and len(plugin.payload) >= 20:
                node_count = struct.unpack_from('<I', plugin.payload, 8)[0]
                if len(plugin.payload) != 20 + node_count * 12:
                    raise ValueError('Invalid DFF bone hierarchy table')
                for node in range(node_count):
                    bone_id, skin_index, flags = struct.unpack_from('<3I', plugin.payload, 20 + node * 12)
                    skin_indices[bone_id] = skin_index
    for index in range(count):
        values = struct.unpack_from('<12fiI', data, 4 + index * 56)
        parent = values[12]
        if parent >= count or parent < -1 or parent == index:
            raise ValueError('Invalid DFF frame parent')
        name = 'frame_%d' % index
        bone_id = None
        if index < len(extensions):
            for plugin in extensions[index].children():
                if plugin.type_id == 0x253F2FE:
                    name = plugin.payload.split(b'\0', 1)[0].decode('ascii', errors='replace') or name
                elif plugin.type_id == 0x11E and len(plugin.payload) >= 12:
                    bone_id = struct.unpack_from('<i', plugin.payload, 4)[0]
        frames.append(dict(index=index, values=values[:12], parent=parent, name=name, bone_id=bone_id, skin_index=skin_indices.get(bone_id)))
    for frame in frames:
        seen = {frame['index']}
        parent = frame['parent']
        while parent >= 0:
            if parent in seen:
                raise ValueError('DFF frame hierarchy contains a cycle')
            seen.add(parent)
            parent = frames[parent]['parent']
    return frames


def readDff(data, source='MOBILE'):
    roots = readMobileDffChunks(data) if source == "MOBILE" else readChunks(data)
    clumps = []
    for root in roots:
        if root.type_id != 0x10:
            raise ValueError('Expected a DFF clump')
        sections = root.children()
        frame_list = next((item for item in sections if item.type_id == 0xE), None)
        frames = readFrames(frame_list) if frame_list else []
        geometry_list = next((item for item in sections if item.type_id == 0x1A), None)
        shared_geometry = [item for item in geometry_list.children() if item.type_id == 0xF] if geometry_list else []
        atomics = []
        for section in sections:
            if section.type_id != 0x14:
                continue
            children = section.children()
            structure = next((item for item in children if item.type_id == 1), None)
            if structure is None or len(structure.payload) < 16:
                raise ValueError('Invalid DFF atomic')
            frame_index, geometry_index, flags, unused = struct.unpack_from('<4I', structure.payload)
            if frame_index >= len(frames):
                raise ValueError('DFF atomic references a missing frame')
            geometry = next((item for item in children if item.type_id == 0xF), None)
            if geometry is None:
                if geometry_index >= len(shared_geometry):
                    raise ValueError('DFF atomic references a missing geometry')
                geometry = shared_geometry[geometry_index]
            if geometry.version == 0xF00D:
                if source != 'MOBILE':
                    raise ValueError('Select LCS Mobile for this Leeds geometry; prototype handling is separate')
                decoded, material_sections = readLeedsGeometry(geometry)
                parts = [dict(vertices=part.verts, faces=part.faces, uvs=part.uvs,
                              colors=part.vertex_colors, normals=part.normals,
                              material=part.material_id, source=part) for part in decoded.parts]
            else:
                decoded = readGeometry(geometry)
                material_sections = decoded['sections']
                for extension in material_sections:
                    if extension.type_id == 3 and any(plugin.type_id == 0x116 for plugin in extension.children()):
                        raise ValueError('This standard RenderWare skin layout is not implemented yet; no static substitute was imported')
                if not decoded['morphs'] or not decoded['morphs'][0]['vertices']:
                    raise ValueError('DFF has no vertex positions')
                parts = [dict(vertices=decoded['morphs'][0]['vertices'], faces=decoded['faces'],
                              uvs=decoded['uvs'][0] if decoded['uvs'] else [],
                              colors=decoded['colors'], normals=decoded['morphs'][0]['normals'],
                              material=0, face_materials=decoded['materials'])]
            atomics.append(dict(chunk=section, children=children, geometry=geometry,
                                frame=frame_index, parts=parts, materials=readMaterialNames(material_sections),
                                shared=geometry_list is not None and geometry in shared_geometry))
        clumps.append(dict(root=root, sections=sections, frames=frames, atomics=atomics,
                           geometry_list=geometry_list, shared_geometry=shared_geometry))
    return clumps


def writeDff(clumps, rebuild_sizes=False):
    for clump in clumps:
        if clump['geometry_list']:
            children = clump['geometry_list'].children()
            geometries = iter(clump['shared_geometry'])
            for index, child in enumerate(children):
                if child.type_id == 0xF:
                    children[index] = next(geometries)
            clump['geometry_list'].payload = b''.join(child.toBytes() for child in children)
        for atomic in clump['atomics']:
            atomic['chunk'].payload = b''.join(child.toBytes() for child in atomic['children'])
            if rebuild_sizes:
                atomic['chunk'].declared_size = len(atomic['chunk'].payload)
                atomic['chunk'].original_size = len(atomic['chunk'].payload)
        clump['root'].payload = b''.join(section.toBytes() for section in clump['sections'])
        if rebuild_sizes:
            clump['root'].declared_size = len(clump['root'].payload)
            clump['root'].original_size = len(clump['root'].payload)
    return b''.join(clump['root'].toBytes() + getattr(clump['root'], 'trailing_bytes', b'') for clump in clumps)


def replaceLeedsAttributes(chunk, attributes):
    from ..leedsLib import native_mdl
    geometry, sections = readLeedsGeometry(chunk)
    if len(attributes) != len(geometry.parts):
        raise ValueError('Mobile geometry part count changed')
    payload = bytearray(chunk.payload)
    for part, edited in zip(geometry.parts, attributes):
        uvs = edited.get('uvs')
        weights = edited.get('weights')
        for strip in part.strips_meta:
            for index in range(strip.vertex_count):
                vertex_index = strip.base_vertex_index + index
                if uvs is not None:
                    original = part.uvs[vertex_index]
                    current = uvs[vertex_index]
                    if any(abs(current[axis] - original[axis]) > 0.000001 for axis in range(2)):
                        offset = strip.source_uv_offset - 32 + index * 2
                        if not strip.source_uv_offset or offset < 0 or offset + 2 > len(payload):
                            raise ValueError('Missing mobile UV stream')
                        encoded = []
                        for axis in range(2):
                            scale = part.uv_scale[axis]
                            if not scale or not math.isfinite(current[axis]):
                                raise ValueError('Invalid UV value or scale')
                            value = round(current[axis] * 127.5 / scale)
                            if not 0 <= value <= 255:
                                raise ValueError('UV exceeds the original mobile material range')
                            encoded.append(value)
                        struct.pack_into('<2B', payload, offset, *encoded)
                if weights is not None:
                    influences = [(int(bone), float(weight)) for bone, weight in weights[vertex_index] if weight > 0.0]
                    original = [(int(bone), float(weight)) for bone, weight in zip(strip.skin_indices[index], strip.skin_weights[index]) if weight > 0.0]
                    original_totals = {}
                    for bone, weight in original:
                        original_totals[bone] = original_totals.get(bone, 0.0) + weight
                    edited_totals = dict(influences)
                    if set(original_totals) == set(edited_totals) and all(abs(original_totals[bone] - edited_totals[bone]) <= 0.000001 for bone in original_totals):
                        continue
                    if not strip.source_skin_offset:
                        if influences:
                            raise ValueError('This mobile geometry has no skin stream')
                        continue
                    if not influences or len(influences) > 4:
                        raise ValueError('Each mobile skinned vertex needs one to four bone weights')
                    total = sum(weight for bone, weight in influences)
                    influences = [(bone, weight / total) for bone, weight in influences]
                    words = [native_mdl._encode_ps2_ped_skin_word(bone, weight) for bone, weight in influences]
                    words.extend([0] * (4 - len(words)))
                    offset = strip.source_skin_offset - 32 + index * 16
                    if offset < 0 or offset + 16 > len(payload):
                        raise ValueError('Invalid mobile skin stream')
                    struct.pack_into('<4I', payload, offset, *words)
        material = edited.get('material')
        if material is not None and material != part.material_id:
            offset = part.raw_part_header_offset - 32 + 0x22
            if not 0 <= material < len(readMaterialNames(sections)):
                raise ValueError('Invalid mobile material index')
            struct.pack_into('<H', payload, offset, material)
    chunk.payload = bytes(payload)
    return chunk
