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
import zlib
from pathlib import Path

import numpy as np

from .vif import Ps2VifStreamDecoder
from ..leedsLib.native_mobile import writeAtomic

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
    # A material slot can point back to an earlier slot instead of storing another material.
    material_list = next((section for section in sections if section.type_id == 8), None)
    if material_list is None:
        return []
    children = material_list.children()
    structure = next((child for child in children if child.type_id == 1), None)
    if structure is None or len(structure.payload) < 4:
        raise ValueError('The DFF material list is incomplete')
    count = struct.unpack_from('<I', structure.payload)[0]
    if len(structure.payload) != 4 + count * 4:
        raise ValueError('The DFF material count does not match its list')
    table = structure.payload
    materials = iter(child for child in children if child.type_id == 7)
    result = []
    for index in range(count):
        reference = struct.unpack_from('<i', table, 4 + index * 4)[0]
        if reference != -1:
            if reference < 0 or reference >= index:
                raise ValueError('The DFF refers to a missing material')
            result.append(dict(result[reference]))
            continue
        material = next(materials, None)
        if material is None:
            raise ValueError('The DFF is missing a material')
        parts = material.children()
        structure = next((section for section in parts if section.type_id == 1), None)
        color = tuple(structure.payload[4:8]) if structure and len(structure.payload) >= 8 else (255, 255, 255, 255)
        texture = next((section for section in parts if section.type_id == 6), None)
        name = ''
        if texture:
            name_chunk = next((section for section in texture.children() if section.type_id == 2), None)
            if name_chunk:
                name = name_chunk.payload.split(b'\0', 1)[0].decode('utf-8', errors='replace')
        result.append(dict(name=name, color=color))
    return result


def readDffRoots(data, source):
    # Some game files have zero padding after the model. Leave that padding alone.
    if len(data) < 12:
        raise ValueError('The DFF header is incomplete')
    version = struct.unpack_from('<I', data, 8)[0]
    if version == 0x310 and source != 'BETA':
        return readMobileDffChunks(data)
    roots = []
    offset = 0
    while offset < len(data):
        if not any(data[offset:]):
            if roots:
                roots[-1].trailing_bytes = data[offset:]
            break
        if offset + 12 > len(data):
            raise ValueError('The DFF ends inside a file header')
        size = struct.unpack_from('<I', data, offset + 4)[0]
        end = offset + 12 + size
        roots.extend(readChunks(data[offset:end]))
        offset = end
    return roots


def readGeometrySkin(sections, vertex_count):
    plugin = next((plugin for section in sections if section.type_id == 3
                   for plugin in section.children() if plugin.type_id == 0x116), None)
    if plugin is None:
        return []
    data = plugin.payload
    if len(data) < 4:
        raise ValueError('The DFF skeleton weights are incomplete')
    bone_count, used_count, maximum, padding = struct.unpack_from('<4B', data)
    offset = 4 + used_count
    required = offset + vertex_count * 20
    if bone_count == 0 or maximum > 4 or used_count > bone_count or required > len(data):
        raise ValueError('The DFF skeleton weights do not match its mesh')
    indices = [struct.unpack_from('<4B', data, offset + index * 4) for index in range(vertex_count)]
    offset += vertex_count * 4
    weights = [struct.unpack_from('<4f', data, offset + index * 16) for index in range(vertex_count)]
    result = []
    for vertex_indices, vertex_weights in zip(indices, weights):
        influences = []
        for bone, weight in zip(vertex_indices, vertex_weights):
            if not math.isfinite(weight) or weight < 0.0:
                raise ValueError('The DFF contains invalid skeleton weights')
            if weight > 0.0:
                if bone >= bone_count:
                    raise ValueError('The DFF mesh refers to a missing bone')
                influences.append((bone, weight))
        result.append(influences)
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
    # Keep frame names, parents and bone numbers together so the model can be rebuilt.
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
                    name = plugin.payload.split(b'\0', 1)[0].decode('utf-8', errors='replace') or name
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
    roots = readDffRoots(data, source)
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
            if structure is None or len(structure.payload) not in (12, 16):
                raise ValueError('The DFF model mesh header is incomplete')
            if len(structure.payload) == 12:
                frame_index, flags, unused = struct.unpack_from('<3I', structure.payload)
                geometry_index = 0
            else:
                frame_index, geometry_index, flags, unused = struct.unpack_from('<4I', structure.payload)
            if frame_index >= len(frames):
                raise ValueError('DFF atomic references a missing frame')
            geometry = next((item for item in children if item.type_id == 0xF), None)
            if geometry is None:
                if geometry_index >= len(shared_geometry):
                    raise ValueError('DFF atomic references a missing geometry')
                geometry = shared_geometry[geometry_index]
            if geometry.version == 0xF00D:
                if source == 'BETA':
                    raise ValueError('Select LCS Mobile for this Leeds geometry; prototype handling is separate')
                decoded, material_sections = readLeedsGeometry(geometry)
                parts = [dict(vertices=part.verts, faces=[face for face in part.faces if len({tuple(part.verts[index]) for index in face}) == 3], uvs=part.uvs,
                              colors=part.vertex_colors, normals=part.normals,
                              material=part.material_id, source=part) for part in decoded.parts]
            else:
                decoded = readGeometry(geometry)
                material_sections = decoded['sections']
                weights = readGeometrySkin(material_sections, decoded['vertex_count'])
                if not decoded['morphs'] or not decoded['morphs'][0]['vertices']:
                    raise ValueError('DFF has no vertex positions')
                parts = [dict(vertices=decoded['morphs'][0]['vertices'], faces=decoded['faces'], 
                              uvs=decoded['uvs'][0] if decoded['uvs'] else [], 
                              colors=decoded['colors'], normals=decoded['morphs'][0]['normals'], 
                              material=0, face_materials=decoded['materials'], weights=weights, uv_sets=decoded['uvs'])]
            atomics.append(dict(chunk=section, children=children, geometry=geometry,
                                frame=frame_index, parts=parts, materials=readMaterialNames(material_sections),
                                shared=geometry_list is not None and geometry in shared_geometry))
        clumps.append(dict(root=root, sections=sections, frames=frames, atomics=atomics,
                           geometry_list=geometry_list, shared_geometry=shared_geometry))
    if not clumps:
        raise ValueError('The file contains no DFF model')
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
                    words = [native_mdl.encodePs2PedSkinWord(bone, weight) for bone, weight in influences]
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


def unwrapResource(data):
    data = bytes(data)
    if data[:4] == b'Z2HM':
        if len(data) < 8:
            raise ValueError('Truncated MH2 compressed header')
        expected = struct.unpack_from('<I', data, 4)[0]
        max_size = 512 * 1024 * 1024
        if expected > max_size:
            raise ValueError('MH2 resource exceeds the 512 MiB decompression limit')
        decoder = zlib.decompressobj()
        data = decoder.decompress(data[8:], max_size + 1)
        if len(data) > max_size or not decoder.eof or decoder.unconsumed_tail:
            raise ValueError('MH2 compressed resource is truncated or exceeds the decompression limit')
        if expected and len(data) != expected:
            raise ValueError('MH2 decompressed size does not match its header')
    return data



class Resource:
    def __init__(self, data, magic):
        self.compressed = bytes(data[:4]) == b'Z2HM'
        self.data = unwrapResource(data)
        if len(self.data) < 48 or self.data[:4] != magic:
            raise ValueError('Expected MH2 %s container' % magic.decode('ascii'))
        self.end = self.uint(16)
        count = self.uint(20)
        self.check(self.end, count * 4, payload=False)
        if self.end < 48:
            raise ValueError('Invalid MH2 payload boundary')
        for index in range(count):
            field = self.uint(self.end + index * 4, payload=False)
            self.check(field, 4)
            target = self.uint(field)
            if target:
                self.check(target, 1)

    def check(self, offset, size, payload=True):
        end = self.end if payload else len(self.data)
        if offset < 0 or size < 0 or offset + size > end:
            raise ValueError('MH2 data outside container at 0x%X' % offset)

    def uint(self, offset, payload=True):
        if hasattr(self, 'end'):
            self.check(offset, 4, payload)
        return struct.unpack_from('<I', self.data, offset)[0]

    def values(self, fmt, offset):
        self.check(offset, struct.calcsize(fmt))
        return struct.unpack_from(fmt, self.data, offset)

    def string(self, offset, length=64):
        if not offset:
            return ''
        self.check(offset, 1)
        return self.data[offset:min(offset + length, self.end)].split(b'\0', 1)[0].decode('ascii', 'replace')

    def write(self, path, data=None):
        payload = self.data if data is None else bytes(data)
        Resource(payload, self.data[:4])
        if self.compressed:
            payload = b'Z2HM' + struct.pack('<I', len(payload)) + zlib.compress(payload, 9)
        writeAtomic(path, payload)



def readMaterials(resource, offset, count):
    if count > 65536:
        raise ValueError('Invalid MH2 material count')
    resource.check(offset, count * 12)
    materials = []
    for index in range(count):
        row = offset + index * 12
        materials.append(dict(name=resource.string(resource.uint(row), 128),
                              color=resource.values('<4B', row + 5)))
    return materials



def stripFaces(vertices, start, count):
    faces = []
    for index in range(2, count):
        a, b, c = start + index - 2, start + index - 1, start + index
        if index & 1:
            a, b = b, a
        if vertices[a] != vertices[b] and vertices[b] != vertices[c] and vertices[a] != vertices[c]:
            faces.append((a, b, c))
    return faces



def ps2Header(resource, offset):
    resource.check(offset, 64)
    packed, flags = resource.values('<2I', offset + 16)
    size, count = packed & 0xFFFFF, packed >> 20
    first = resource.values('<H', offset + 26)[0]
    if (resource.data[offset + 64:offset + 68] != b'D2SP'
            or not count or count > 4096
            or size < 80 + count * 48
            or first < 80 + count * 48 or first >= size):
        raise ValueError('Invalid MH2 PS2 geometry header at 0x%X' % offset)
    resource.check(offset, size)
    scale = resource.values('<3f', offset + 40)
    translation = resource.values('<3f', offset + 52)
    if not all(math.isfinite(value) for value in scale + translation) or flags > 255:
        raise ValueError('Invalid MH2 PS2 geometry transform')
    return size, count, first, scale, translation



def readPs2Geometry(resource, offset):
    size, count, first, scale, translation = ps2Header(resource, offset)
    parts = []
    for index in range(count):
        row = offset + 80 + index * 48
        us, vs = resource.values('<2f', row + 16)
        relative = resource.uint(row + 28)
        material = resource.values('<H', row + 34)[0]
        start = offset + first + relative
        finish = offset + size
        if index + 1 < count:
            finish = offset + first + resource.uint(row + 48 + 28)
        resource.check(start, finish - start)
        if resource.uint(start) & 0x70000000 == 0x60000000:
            start += 16
        decoder = Ps2VifStreamDecoder()
        records = decoder.feed(resource.data[start:finish], final=True)
        part = dict(vertices=[], faces=[], uvs=[], normals=[], colors=[], weights=[], material=material,
                    position_sources=[], uv_sources=[], normal_sources=[], color_sources=[], weight_sources=[],
                    uv_scales=[], uv_component_sizes=[], normal_component_sizes=[], color_formats=[],
                    weight_component_sizes=[], weight_component_counts=[], weight_palettes=[],
                    scale=scale, translation=translation, offset=offset)
        batch = {}
        def flush():
            positions = batch.get(0x79)
            if positions is None:
                batch.clear()
                return
            vertex_count = positions.num
            base = len(part['vertices'])
            resource.check(start + positions.stream_offset + 4, vertex_count * 6)
            for command, bytes_per_vertex in ((0x79, 6), (0x76, 2), (0x6A, 3), (0x6E, 4), (0x6C, 16)):
                record = batch.get(command)
                if record is not None and command != 0x6C and record.num < vertex_count:
                    raise ValueError('MH2 PS2 VIF attribute 0x%02X has too few vertices' % command)
                if record is not None and (command != 0x6C or record.num == vertex_count) and len(record.payload) < vertex_count * bytes_per_vertex:
                    raise ValueError('Truncated MH2 PS2 VIF vertex attribute 0x%02X' % command)
            for vertex_index in range(vertex_count):
                raw = struct.unpack_from('<3h', positions.payload, vertex_index * 6)
                part['vertices'].append(tuple(raw[axis] / 32768.0 * scale[axis] + translation[axis] for axis in range(3)))
                part['position_sources'].append(start + positions.stream_offset + 4 + vertex_index * 6)
                uv = batch.get(0x76)
                part['uvs'].append((uv.payload[vertex_index * 2] / 128.0 * us, uv.payload[vertex_index * 2 + 1] / 128.0 * vs) if uv else (0.0, 0.0))
                part['uv_sources'].append(start + uv.stream_offset + 4 + vertex_index * 2 if uv else None)
                part['uv_scales'].append((us, vs))
                part['uv_component_sizes'].append(1 if uv else 0)
                normal = batch.get(0x6A)
                part['normal_sources'].append(start + normal.stream_offset + 4 + vertex_index * 3 if normal else None)
                part['normal_component_sizes'].append(1 if normal else 0)
                part['normals'].append(tuple(value / 128.0 for value in struct.unpack_from('<3b', normal.payload, vertex_index * 3)) if normal else (0.0, 0.0, 1.0))
                color = batch.get(0x6E)
                part['color_sources'].append(start + color.stream_offset + 4 + vertex_index * 4 if color else None)
                part['color_formats'].append(7 if color else 0)
                rgba = struct.unpack_from('<4B', color.payload, vertex_index * 4) if color else (255, 255, 255, 128)
                part['colors'].append(tuple(rgba[:3]) + (min(255, rgba[3] * 255 // 128),))
                skin = batch.get(0x6C)
                has_skin = skin is not None and skin.num == vertex_count
                part['weight_sources'].append(start + skin.stream_offset + 4 + vertex_index * 16 if has_skin else None)
                part['weight_component_sizes'].append(4 if has_skin else 0)
                part['weight_component_counts'].append(4 if has_skin else 0)
                part['weight_palettes'].append(None)
                influences = []
                if skin and skin.num == vertex_count:
                    for word in struct.unpack_from('<4I', skin.payload, vertex_index * 16):
                        weight = struct.unpack('<f', struct.pack('<I', word & 0xFFFFFF00))[0]
                        if math.isfinite(weight) and weight > 0:
                            influences.append(((word & 255) // 4, weight))
                total = sum(weight for bone, weight in influences)
                part['weights'].append([(bone, weight / total) for bone, weight in influences] if total else [])
            part['faces'].extend(stripFaces(part['vertices'], base, vertex_count))
            batch.clear()
        for record in records:
            if record.command == 0x79:
                flush()
            if record.command in (0x79, 0x76, 0x6A, 0x6E) or record.command == 0x6C and record.num > 1:
                batch[record.command] = record
            if record.command in (0x14, 0x15, 0x17):
                flush()
        flush()
        if not part['vertices']:
            raise ValueError('MH2 PS2 geometry part has no decoded positions')
        parts.append(part)
    return parts



def pspLayout(flags):
    fields = {}
    cursor = 0
    alignment = 1
    def add(name, size, components):
        nonlocal cursor, alignment
        cursor = (cursor + size - 1) // size * size
        fields[name] = (cursor, size, components)
        cursor += size * components
        alignment = max(alignment, size)
    weight_format = (flags >> 9) & 3
    if weight_format:
        add('weights', (0, 1, 2, 4)[weight_format], ((flags >> 14) & 7) + 1)
    uv_format = flags & 3
    if uv_format:
        add('uv', (0, 1, 2, 4)[uv_format], 2)
    color_format = (flags >> 2) & 7
    if color_format:
        if color_format not in (4, 5, 6, 7):
            raise ValueError('Unsupported MH2 PSP vertex color format')
        add('color', 4 if color_format == 7 else 2, 1)
    normal_format = (flags >> 5) & 3
    if normal_format:
        add('normal', (0, 1, 2, 4)[normal_format], 3)
    position_format = (flags >> 7) & 3
    if not position_format or flags & 0x1C0000:
        raise ValueError('Unsupported MH2 PSP position or morph format')
    add('position', (0, 1, 2, 4)[position_format], 3)
    return fields, (cursor + alignment - 1) // alignment * alignment



def readPspGeometry(resource, offset, world=False):
    size, flags, strip_count = resource.values('<3I', offset)
    if not strip_count or strip_count > 4096:
        raise ValueError('Invalid MH2 PSP strip count')
    fields, stride = pspLayout(flags)
    vertex_count = resource.uint(offset + 44)
    buffer = resource.uint(offset + 64)
    if buffer < 80 + strip_count * 32 or size < buffer + vertex_count * stride:
        raise ValueError('Invalid MH2 PSP vertex buffer')
    resource.check(offset, size)
    scale = resource.values('<3f', offset + 32)
    translation = resource.values('<3f', offset + 48)
    if not all(math.isfinite(value) for value in scale + translation):
        raise ValueError('MH2 PSP geometry contains non-finite transforms')
    parts = []
    cursor = 0
    for strip in range(strip_count):
        descriptor = offset + 80 + strip * 32
        count, material = resource.values('<2H', descriptor + 16)
        if cursor + count > vertex_count:
            raise ValueError('MH2 PSP strip exceeds its declared vertex buffer')
        us = resource.values('<f', descriptor + 20)[0] or 1.0
        vs = resource.values('<f', descriptor + 24)[0] if world else us
        if not math.isfinite(us):
            raise ValueError('MH2 PSP strip contains invalid UV scale')
        if not math.isfinite(vs) or abs(vs) < 1e-30:
            vs = us
        part = dict(vertices=[], faces=[], uvs=[], normals=[], colors=[], weights=[], material=material,
                    position_sources=[], uv_sources=[], normal_sources=[], color_sources=[], weight_sources=[],
                    uv_scales=[], uv_component_sizes=[], normal_component_sizes=[], color_formats=[],
                    weight_component_sizes=[], weight_component_counts=[], weight_palettes=[],
                    scale=scale, translation=translation, offset=offset)
        for index in range(count):
            vertex = offset + buffer + (cursor + index) * stride
            resource.check(vertex, stride)
            position_offset, component_size, unused = fields['position']
            fmt = {1:'b', 2:'h', 4:'f'}[component_size]
            raw = resource.values('<3' + fmt, vertex + position_offset)
            divisor = {1:128.0, 2:32768.0, 4:1.0}[component_size]
            part['vertices'].append(tuple(raw[axis] / divisor * scale[axis] + translation[axis] for axis in range(3)))
            part['position_sources'].append(vertex + position_offset)
            part['position_size'] = component_size
            uv = (0.0, 0.0)
            part['uv_sources'].append(vertex + fields['uv'][0] if 'uv' in fields else None)
            part['uv_scales'].append((us, vs))
            part['uv_component_sizes'].append(fields['uv'][1] if 'uv' in fields else 0)
            if 'uv' in fields:
                address, width, unused = fields['uv']
                raw_uv = resource.values('<2' + {1:'B', 2:'H', 4:'f'}[width], vertex + address)
                uv_divisor = {1:128.0, 2:32768.0, 4:1.0}[width]
                uv = (raw_uv[0] / uv_divisor * us, raw_uv[1] / uv_divisor * vs)
            part['uvs'].append(uv)
            normal = (0.0, 0.0, 1.0)
            part['normal_sources'].append(vertex + fields['normal'][0] if 'normal' in fields else None)
            part['normal_component_sizes'].append(fields['normal'][1] if 'normal' in fields else 0)
            if 'normal' in fields:
                address, width, unused = fields['normal']
                normal = tuple(value / {1:128.0, 2:32768.0, 4:1.0}[width] for value in resource.values('<3' + {1:'b', 2:'h', 4:'f'}[width], vertex + address))
            part['normals'].append(normal)
            rgba = (255, 255, 255, 255)
            part['color_sources'].append(vertex + fields['color'][0] if 'color' in fields else None)
            part['color_formats'].append((flags >> 2) & 7 if 'color' in fields else 0)
            if 'color' in fields:
                address, width, unused = fields['color']
                if width == 4:
                    rgba = resource.values('<4B', vertex + address)
                else:
                    value = resource.values('<H', vertex + address)[0]
                    form = (flags >> 2) & 7
                    if form == 4:
                        rgba = ((value & 31) * 255 // 31, ((value >> 5) & 63) * 255 // 63, ((value >> 11) & 31) * 255 // 31, 255)
                    elif form == 5:
                        rgba = ((value & 31) * 255 // 31, ((value >> 5) & 31) * 255 // 31, ((value >> 10) & 31) * 255 // 31, 255 if value & 32768 else 0)
                    else:
                        rgba = tuple(((value >> shift) & 15) * 17 for shift in (0, 4, 8, 12))
            part['colors'].append(rgba)
            part['weight_sources'].append(vertex + fields['weights'][0] if 'weights' in fields else None)
            part['weight_component_sizes'].append(fields['weights'][1] if 'weights' in fields else 0)
            part['weight_component_counts'].append(fields['weights'][2] if 'weights' in fields else 0)
            part['weight_palettes'].append(tuple(resource.data[descriptor + 24:descriptor + 32]) if 'weights' in fields else None)
            influences = []
            if 'weights' in fields:
                address, width, number = fields['weights']
                if number > 8:
                    raise ValueError('MH2 PSP bone palette exceeds strip descriptor')
                raw_weights = resource.values('<' + str(number) + {1:'B', 2:'H', 4:'f'}[width], vertex + address)
                for token, weight in enumerate(raw_weights):
                    if not math.isfinite(float(weight)):
                        raise ValueError('MH2 PSP skin contains non-finite weight values')
                    if weight > 0:
                        influences.append((resource.data[descriptor + 24 + token], float(weight)))
            total = sum(weight for bone, weight in influences)
            if not math.isfinite(total):
                raise ValueError('MH2 PSP skin weights overflow')
            part['weights'].append([(bone, weight / total) for bone, weight in influences] if total else [])
        part['faces'] = stripFaces(part['vertices'], 0, count)
        parts.append(part)
        cursor += count
    if cursor != vertex_count:
        raise ValueError('MH2 PSP strip counts do not match vertex buffer')
    return parts



def boneIdFromName(name):
    mapping = {
        'bip01': 1000, 
        'root': 1000, 
        'head': 1001, 
        'l_calf': 1002, 
        'bip01_l_clavicle': 1003, 
        'l_clavicle': 1003, 
        'l_finger0': 1004, 
        'l_finger1': 1005, 
        'l_finger01': 1006, 
        'l_finger2': 1008, 
        'l_finger11': 1011, 
        'l_finger21': 1013, 
        'l_foot': 1019, 
        'l_forearm': 1020, 
        'l_hand': 1021, 
        'l_thigh': 1023, 
        'l_toe': 1024, 
        'l_toe0': 1024, 
        'l_upperarm': 1039, 
        'neck': 1040, 
        'pelvis': 1045, 
        'r_calf': 1056, 
        'bip01_r_clavicle': 1057, 
        'r_clavicle': 1057, 
        'r_finger0': 1058, 
        'r_finger1': 1059, 
        'r_finger01': 1060, 
        'r_finger2': 1062, 
        'r_finger11': 1065, 
        'r_finger21': 1067, 
        'r_foot': 1073, 
        'r_forearm': 1074, 
        'r_hand': 1075, 
        'r_thigh': 1077, 
        'r_toe': 1078, 
        'r_toe0': 1078, 
        'r_upperarm': 1093, 
        'spine': 1094, 
        'spine1': 1095, 
        'spine2': 1096, 
    }
    normalized = str(name).strip().lower().replace(" ", "_").replace("-", "_")
    if normalized.startswith("bip01_"):
        normalized = normalized[6:]
    return mapping.get(normalized)



def readModel(data, platform='AUTO'):
    resource = Resource(data, b'PMLC')
    entries = []
    entry = resource.uint(32)
    visited = set()
    while entry:
        if entry in visited:
            raise ValueError('MH2 clump entry list loops')
        visited.add(entry)
        resource.check(entry, 16)
        body = resource.uint(entry + 8)
        resource.check(body, 28)
        bones = []
        pending = [resource.uint(body)]
        seen_bones = set()
        while pending:
            bone = pending.pop()
            if not bone or bone in seen_bones:
                continue
            seen_bones.add(bone)
            resource.check(bone, 192)
            bones.append(dict(offset=bone, parent=resource.uint(bone + 8), name=resource.string(bone + 24, 40),
                              matrix=resource.values('<16f', bone + 128), identifier=None))
            pending.extend([resource.uint(bone + 4), resource.uint(bone + 16)])
        by_offset = {bone['offset']:index for index, bone in enumerate(bones)}
        bones_by_identifier = {}
        for bone_index, bone in enumerate(bones):
            identifier = boneIdFromName(bone['name'])
            if identifier is not None:
                bones_by_identifier.setdefault(identifier, []).append(bone_index)
        palette = []
        for bone in bones:
            binding = resource.uint(bone['offset'] + 20)
            if not binding:
                continue
            resource.check(binding, 24)
            number = resource.uint(binding)
            root = resource.uint(binding + 8)
            table = resource.uint(binding + 12)
            if number == 0 or number > 4096 or root not in by_offset:
                continue
            resource.check(table, number * 8)
            hierarchy_order_valid = by_offset[root] + number <= len(bones)
            for index in range(number):
                candidate = by_offset[root] + index
                identifier = resource.values('<h', table + index * 8)[0]
                target = resource.uint(table + index * 8 + 4)
                if candidate >= len(bones):
                    hierarchy_order_valid = False
                    break
                known = boneIdFromName(bones[candidate]['name'])
                if known is not None and identifier != known or target and target != bones[candidate]['offset']:
                    hierarchy_order_valid = False
                    break
            for index in range(number):
                identifier = resource.values('<h', table + index * 8)[0]
                target = resource.uint(table + index * 8 + 4)
                resolved = by_offset.get(target)
                if resolved is None and not target:
                    if hierarchy_order_valid:
                        resolved = by_offset[root] + index
                    elif index == 0 and identifier == 8889:
                        resolved = by_offset[root]
                    else:
                        matching = bones_by_identifier.get(identifier, [])
                        resolved = matching[0] if len(matching) == 1 else None
                palette.append(resolved)
                if resolved is not None:
                    bones[resolved]['identifier'] = identifier
            break
        for bone in bones:
            if bone['identifier'] is None:
                bone['identifier'] = boneIdFromName(bone['name'])
        objects = []
        current = resource.uint(body + 20)
        sentinel = body + 20
        seen_objects = set()
        while current and current != sentinel:
            if current in seen_objects:
                raise ValueError('MH2 atomic list loops')
            seen_objects.add(current)
            resource.check(current, 28)
            mesh = resource.uint(current + 12)
            resource.check(mesh, 96)
            materials = readMaterials(resource, resource.uint(mesh), resource.uint(mesh + 4))
            detected = 'PS2' if resource.data[mesh + 80:mesh + 84] == b'D2SP' else 'PSP'
            if platform != 'AUTO' and platform != detected:
                raise ValueError('Selected %s, but model contains %s geometry' % (platform, detected))
            parts = readPs2Geometry(resource, mesh + 16) if detected == 'PS2' else readPspGeometry(resource, mesh + 16)
            for part in parts:
                if part['material'] >= len(materials):
                    raise ValueError('MH2 strip refers to missing material')
                for influences in part['weights']:
                    for token, weight in influences:
                        if not math.isfinite(weight) or weight < 0.0:
                            raise ValueError('MH2 skin contains an invalid bone weight')
                        if weight == 0.0:
                            continue
                        if token < 0 or token >= len(palette) or palette[token] is None:
                            raise ValueError('MH2 skin refers to an unresolved bone palette entry')
            objects.append(dict(offset=current, parent=resource.uint(current + 8), parts=parts, materials=materials, platform=detected))
            if current == resource.uint(body + 24):
                break
            current = resource.uint(current)
        entries.append(dict(name=resource.string(resource.uint(entry + 12), 128) or (bones[0]['name'] if bones else 'Clump'), 
                            bones=bones, palette=palette, objects=objects))
        if entry == resource.uint(36):
            break
        entry = resource.uint(entry)
    if not entries:
        raise ValueError('MH2 model contains no clumps')
    return resource, entries



def readWorld(data, platform='AUTO'):
    resource = Resource(data, b'DLRW')
    materials = readMaterials(resource, resource.uint(80), resource.uint(84))
    geometry = []
    cursor = 96
    while cursor + 80 <= resource.end:
        detected = None
        if resource.uint(cursor + 4) & 0x180 == 0x100:
            try:
                parts = readPspGeometry(resource, cursor, world=True)
                size = resource.uint(cursor)
                detected = 'PSP'
            except (ValueError, struct.error, IndexError):
                pass
        if detected is None:
            try:
                size, count, first, scale, translation = ps2Header(resource, cursor)
                if resource.uint(cursor + first) & 0x70000000 != 0x60000000:
                    raise ValueError('Not a PS2 DMA geometry packet')
                parts = readPs2Geometry(resource, cursor)
                detected = 'PS2'
            except (ValueError, struct.error, IndexError):
                pass
        if detected:
            if platform != 'AUTO' and platform != detected:
                raise ValueError('Selected BSP platform does not match its geometry')
            if any(part['material'] >= len(materials) for part in parts):
                raise ValueError('MH2 BSP strip refers to missing material')
            geometry.append(dict(offset=cursor, parts=parts, platform=detected))
            cursor = (cursor + size + 3) & ~3
        else:
            cursor += 4
    return resource, materials, geometry

