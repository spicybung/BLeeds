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
import struct
from collections import defaultdict
from dataclasses import dataclass

from .chunks import RenderWareChunk
from .dff import readLeedsGeometry


@dataclass(frozen=True)
class MobileVertex:
    position: tuple
    uv: tuple = (0.0, 0.0)
    normal: tuple = (0.0, 0.0, 1.0)
    color: tuple = (255, 255, 255, 255)
    weights: tuple = ()


def validateVertex(vertex, skinned):
    values = vertex.position + vertex.uv + vertex.normal
    if len(vertex.position) != 3 or len(vertex.uv) != 2 or len(vertex.normal) != 3 or not all(math.isfinite(value) for value in values):
        raise ValueError('Mobile DFF vertex coordinates must be finite')
    if len(vertex.color) != 4 or any(not 0 <= channel <= 255 for channel in vertex.color):
        raise ValueError('Mobile DFF vertex colors must have four byte channels')
    if skinned and not vertex.weights:
        raise ValueError('Each skinned vertex needs at least one bone weight')
    if len(vertex.weights) > 4:
        raise ValueError('Mobile DFF vertices support at most four bone weights')
    if any(not 0 <= bone <= 63 or not math.isfinite(weight) or weight <= 0.0 for bone, weight in vertex.weights):
        raise ValueError('Invalid mobile DFF skin index or bone weight')
    if len({bone for bone, weight in vertex.weights}) != len(vertex.weights):
        raise ValueError('Duplicate mobile DFF skin index on a vertex')


def buildTriangleStrips(triangles):
    vertices = []
    vertex_indices = {}
    faces = []
    directed_edges = defaultdict(list)
    for triangle in triangles:
        if len(triangle) != 3:
            raise ValueError('Mobile geometry rebuilding expects triangulated faces')
        face = []
        for vertex in triangle:
            if vertex not in vertex_indices:
                vertex_indices[vertex] = len(vertices)
                vertices.append(vertex)
            face.append(vertex_indices[vertex])
        face = tuple(face)
        if len(set(face)) != 3:
            continue
        index = len(faces)
        faces.append(face)
        for corner in range(3):
            directed_edges[(face[corner], face[(corner + 1) % 3])].append((index, face[(corner + 2) % 3]))
    remaining = set(range(len(faces)))
    strips = []
    for first_index, face in enumerate(faces):
        if first_index not in remaining:
            continue
        candidates = []
        for corner in range(3):
            strip = [face[corner], face[(corner + 1) % 3], face[(corner + 2) % 3]]
            consumed = {first_index}
            while True:
                edge = (strip[-2], strip[-1]) if len(strip) % 2 == 0 else (strip[-1], strip[-2])
                next_face = next(((index, vertex) for index, vertex in directed_edges[edge]
                                  if index in remaining and index not in consumed), None)
                if next_face is None:
                    break
                index, vertex = next_face
                consumed.add(index)
                strip.append(vertex)
            candidates.append((strip, consumed))
        strip, consumed = max(candidates, key=lambda item: len(item[1]))
        remaining.difference_update(consumed)
        strips.append([vertices[index] for index in strip])
    return strips


def splitTriangleStrip(strip, limit=70):
    if limit < 4 or limit % 2:
        raise ValueError('Mobile strip batches require an even vertex limit of at least four')
    start = 0
    while start + 2 < len(strip):
        end = min(start + limit, len(strip))
        yield strip[start:end]
        if end == len(strip):
            break
        start = end - 2


def joinTriangleStrips(strips, limit=70):
    batches = []
    current = []
    for strip in strips:
        for piece in splitTriangleStrip(strip, limit):
            if not current:
                current = list(piece)
                continue
            bridge = [current[-1], piece[0], piece[0]]
            if len(current) % 2:
                bridge.append(piece[0])
            joined = current + bridge + list(piece[1:])
            if len(joined) <= limit:
                current = joined
            else:
                batches.append(current)
                current = list(piece)
    if current:
        batches.append(current)
    return batches


def geometryBounds(vertices):
    lower = tuple(min(vertex.position[axis] for vertex in vertices) for axis in range(3))
    upper = tuple(max(vertex.position[axis] for vertex in vertices) for axis in range(3))
    center = tuple((lower[axis] + upper[axis]) * 0.5 for axis in range(3))
    radius = max(math.dist(vertex.position, center) for vertex in vertices)
    return lower, upper, center + (radius,)


def chooseGeometryScale(vertices):
    lower, upper, sphere = geometryBounds(vertices)
    factor = 0.00003051820313464149
    scale = tuple(max((upper[axis] - lower[axis]) * 0.5, 0.000001) / (28672.0 * factor) for axis in range(3))
    return scale, sphere[:3]


def encodePosition(position, scale, translation):
    factor = 0.00003051820313464149
    result = tuple(round((position[axis] - translation[axis]) / (scale[axis] * factor)) for axis in range(3))
    if any(not -32768 <= value <= 32767 for value in result):
        raise ValueError('Mobile position exceeds the rebuilt geometry scale')
    return result


def chooseUvScale(vertices):
    result = []
    for axis in range(2):
        values = [vertex.uv[axis] for vertex in vertices]
        low, high = min(values), max(values)
        if low < -0.000001 and high > 0.000001:
            raise ValueError('Mobile UV coordinates on one axis cannot span both negative and positive values in a single material part')
        extent = max(abs(low), abs(high))
        result.append((-1.0 if low < 0.0 else 1.0) * max(1.0, extent / 2.0))
    return tuple(result)


def makeMobilePacket(vertices, scale, translation, uv_scale, skinned):
    payload = bytearray()
    count = len(vertices)
    def word(value):
        payload.extend(struct.pack('<I', value))
    def align():
        payload.extend(bytes((-len(payload)) % 4))
    word(0x6C018000)
    word(0)
    word(0)
    word(count)
    word(count | 0x8000)
    word(0x20000000)
    word(0x40404040)
    word(0x30000000)
    payload.extend(bytes(16))
    word(0x79008001 | (count << 16))
    for vertex in vertices:
        payload.extend(struct.pack('<3h', *encodePosition(vertex.position, scale, translation)))
    align()
    word(0x20000000)
    word(0x50505050)
    word(0x30000000)
    payload.extend(struct.pack('<4I', 0, 0, 255, 0))
    word((0x7600C055 if skinned else 0x7600C08D) | (count << 16))
    for vertex in vertices:
        uv = tuple(round(vertex.uv[axis] * 127.5 / uv_scale[axis]) for axis in range(2))
        if any(not 0 <= value <= 255 for value in uv):
            raise ValueError('Mobile UV coordinates exceed the rebuilt UV scale')
        payload.extend(struct.pack('<2B', *uv))
    align()
    if not skinned:
        word(0x6F0080D3 | (count << 16))
        for vertex in vertices:
            red, green, blue, alpha = vertex.color
            packed = round(red * 31.0 / 255.0) | (round(green * 31.0 / 255.0) << 5) | (round(blue * 31.0 / 255.0) << 10) | (int(alpha >= 128) << 15)
            payload.extend(struct.pack('<H', packed))
        align()
    word((0x6A00802B if skinned else 0x6A008047) | (count << 16))
    for vertex in vertices:
        normal = tuple(max(-128, min(127, round(value * 128.0))) for value in vertex.normal)
        payload.extend(struct.pack('<3b', *normal))
    align()
    if skinned:
        word(0x6C00807F | (count << 16))
        for vertex in vertices:
            total = sum(weight for bone, weight in vertex.weights)
            words = []
            for bone, weight in vertex.weights:
                bits = struct.unpack('<I', struct.pack('<f', weight / total))[0] & 0xFFFFFF00
                words.append(bits | (bone * 4))
            words.extend([0] * (4 - len(words)))
            payload.extend(struct.pack('<4I', *words))
    word(0x14000006)
    payload.extend(bytes((-len(payload)) % 16))
    return struct.pack('<4I', 0x60000000 | (len(payload) // 16), 0, 0, 0) + payload


def rebuildMobileGeometry(chunk, surfaces, material_list=None):
    source, sections = readLeedsGeometry(chunk)
    surfaces = [surface for surface in surfaces if surface['triangles']]
    if not surfaces:
        raise ValueError('Mobile geometry must contain at least one triangle')
    vertices = [vertex for surface in surfaces for triangle in surface['triangles'] for vertex in triangle]
    skinned = any(vertex.weights for vertex in vertices)
    for vertex in vertices:
        validateVertex(vertex, skinned)
    scale, translation = chooseGeometryScale(vertices)
    parts = []
    for surface in surfaces:
        surface_vertices = [vertex for triangle in surface['triangles'] for vertex in triangle]
        uv_scale = chooseUvScale(surface_vertices)
        strips = joinTriangleStrips(buildTriangleStrips(surface['triangles']), limit=42 if skinned else 70)
        packet = b''.join(makeMobilePacket(strip, scale, translation, uv_scale, skinned) for strip in strips)
        vertex_count = sum(len(strip) - 2 for strip in strips)
        if vertex_count > 65535:
            raise ValueError('A mobile geometry part exceeds the 16-bit strip count')
        lower, upper, sphere = geometryBounds(surface_vertices)
        bbox = encodePosition(lower, scale, translation) + encodePosition(upper, scale, translation)
        part_index = surface.get('source_part', 0)
        flags = source.parts[part_index].geom_flags if 0 <= part_index < len(source.parts) else source.parts[0].geom_flags
        parts.append(dict(packet=packet, uv_scale=uv_scale, count=vertex_count, sphere=sphere,
                          bbox=bbox, material=surface['material'], flags=flags))
    part_count = len(parts)
    header_size = 64 + part_count * 48
    geometry_size = header_size + sum(len(part['packet']) for part in parts)
    runtime_count = sum(part['count'] + 2 for part in parts)
    if part_count > 4095 or header_size > 65535 or geometry_size > 0xFFFFF or runtime_count > 65535:
        raise ValueError('Mobile geometry exceeds its header count or size limits')
    lower, upper, sphere = geometryBounds(vertices)
    bbox = encodePosition(lower, scale, translation) + encodePosition(upper, scale, translation)
    flags = source.leeds_global_header['vertex_section_flags']
    payload = bytearray(struct.pack('<4fIIHH6h6f', *sphere, geometry_size | (part_count << 20), flags,
                                    runtime_count, header_size, *bbox, *scale, *translation))
    offset = 0
    for part in parts:
        payload.extend(struct.pack('<4f2fIIHH6h', *part['sphere'], *part['uv_scale'], part['flags'],
                                   offset, part['count'], part['material'], *part['bbox']))
        offset += len(part['packet'])
    for part in parts:
        payload.extend(part['packet'])
    if material_list is not None:
        sections = [material_list if section.type_id == 8 else section for section in sections]
    payload.extend(b''.join(section.toBytes() for section in sections))
    chunk.payload = bytes(payload)
    chunk.parsed_children = sections
    chunk.declared_size = len(chunk.payload)
    chunk.original_size = len(chunk.payload)
    rebuilt, rebuilt_sections = readLeedsGeometry(chunk)
    if len(rebuilt.parts) != part_count:
        raise ValueError('Rebuilt mobile geometry part count does not match')
    return chunk


def buildMobileMaterialList(descriptions, source_sections):
    import copy
    source_list = next((section for section in source_sections if section.type_id == 8), None)
    version = source_list.version if source_list else 0x310
    originals = []
    if source_list:
        children = source_list.children()
        structure = next((child for child in children if child.type_id == 1), None)
        material_chunks = iter(child for child in children if child.type_id == 7)
        count = struct.unpack_from('<I', structure.payload)[0]
        for index in range(count):
            reference = struct.unpack_from('<i', structure.payload, 4 + index * 4)[0]
            originals.append(next(material_chunks) if reference == -1 else originals[reference])
    result = [RenderWareChunk(1, version, struct.pack('<I', len(descriptions)) + struct.pack('<i', -1) * len(descriptions))]
    for description in descriptions:
        index = description.get('source_index', -1)
        texture_name = description.get('texture', '')
        color = tuple(max(0, min(255, round(float(value) * 255.0))) for value in description.get('color', (1.0, 1.0, 1.0, 1.0)))
        if not 0 <= index < len(originals):
            structure = RenderWareChunk(1, version, struct.pack('<I4BII3f', 0, *color, 0, bool(texture_name), 1.0, 0.0, 1.0))
            children = [structure, RenderWareChunk(3, version, b'')]
        else:
            material = copy.deepcopy(originals[index])
            children = material.children()
            structure = next(child for child in children if child.type_id == 1)
            data = bytearray(structure.payload)
            data[4:8] = bytes(color)
            struct.pack_into('<I', data, 12, bool(texture_name))
            structure.payload = bytes(data)
        texture = next((child for child in children if child.type_id == 6), None)
        if texture_name:
            name = texture_name.encode('ascii') + b'\0'
            name += bytes((-len(name)) % 4)
            if texture:
                texture_children = texture.children()
                strings = [child for child in texture_children if child.type_id == 2]
                if not strings:
                    raise ValueError('Original mobile material has no texture name string')
                strings[0].payload = name
                texture.payload = b''.join(child.toBytes() for child in texture_children)
            else:
                texture = RenderWareChunk(6, version, b''.join(child.toBytes() for child in (
                    RenderWareChunk(1, version, struct.pack('<I', 0x1106)),
                    RenderWareChunk(2, version, name), RenderWareChunk(2, version, bytes(4)),
                    RenderWareChunk(3, version, b''))))
                children.insert(1, texture)
        else:
            children = [child for child in children if child.type_id != 6]
        material = RenderWareChunk(7, version, b''.join(child.toBytes() for child in children))
        material.parsed_children = children
        result.append(material)
    material_list = RenderWareChunk(8, version, b''.join(child.toBytes() for child in result))
    material_list.parsed_children = result
    return material_list
