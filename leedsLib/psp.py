import math
import struct

from mathutils import Matrix, Vector

from .mdl import buildPspVertexLayout, probeStoriesResourceHeader


class PspResource:
    def __init__(self, source=None):
        self.data = bytearray(0x28)
        self.data[:4] = b"ldm\0"
        self.relocations = []
        self.texture_fields = []
        self.source_tail = b""
        self.source_tail_offset = 0
        self.source_tail_fields = []
        self.source_tail_targets = []
        self.source_texture_head = 0
        self.source_local_offset = 0
        self.source_global_offset = 0
        self.source_prefix = b""
        self.source_prefix_fields = []
        self.source_prefix_targets = []
        self.allocation = 0x10000
        if source is not None:
            self.loadSource(source)

    def loadSource(self, source):
        if not probeStoriesResourceHeader(source) or source[:4] != b"ldm\0":
            raise ValueError("The source file is not a Stories MDL")
        logical_end, local, global_table, count, texture_head = struct.unpack_from("<5I", source, 8)
        if global_table < local or (global_table - local) % 4 or local < 0x28 or global_table + count * 4 > logical_end:
            raise ValueError("Unsupported PSP MDL relocation table")
        if not logical_end <= len(source):
            raise ValueError("The source PSP MDL is truncated")
        self.data = bytearray(source[:local])
        self.source_local_offset = local
        self.source_global_offset = global_table
        self.source_prefix = bytes(source[local:global_table])
        self.allocation = struct.unpack_from("<I", source, 0x1C)[0]
        self.source_tail_offset = global_table + count * 4
        self.source_tail = bytes(source[self.source_tail_offset:logical_end])
        self.source_texture_head = texture_head
        for index in range(count):
            field = struct.unpack_from("<I", source, global_table + index * 4)[0]
            if field % 4 or field + 4 > logical_end:
                raise ValueError("Invalid PSP MDL relocation field")
            target = struct.unpack_from("<I", source, field)[0]
            if target >= logical_end:
                raise ValueError("Invalid PSP MDL pointer")
            if global_table <= target < self.source_tail_offset:
                raise ValueError("PSP MDL pointer references its relocation table")
            if local <= field < global_table:
                self.source_prefix_fields.append((field, target))
            elif field >= self.source_tail_offset:
                self.source_tail_fields.append((field, target))
            elif field < local:
                if target:
                    self.relocations.append(field)
                if target >= self.source_tail_offset:
                    self.source_tail_targets.append((field, target))
                elif local <= target < global_table:
                    self.source_prefix_targets.append((field, target))
            else:
                raise ValueError("PSP MDL relocation field overlaps its table")

    def align(self, alignment=16):
        self.data.extend(bytes((-len(self.data)) % alignment))

    def reserve(self, size, alignment=4):
        self.align(alignment)
        offset = len(self.data)
        self.data.extend(bytes(size))
        return offset

    def pointer(self, field, target):
        struct.pack_into("<I", self.data, field, int(target))
        if target:
            if field not in self.relocations:
                self.relocations.append(field)
        elif field in self.relocations:
            self.relocations.remove(field)
        self.source_tail_targets = [(old_field, value) for old_field, value in self.source_tail_targets
                                    if old_field != field]
        self.source_prefix_targets = [(old_field, value) for old_field, value in self.source_prefix_targets
                                      if old_field != field]

    def matrix(self, offset, matrix):
        values = []
        for column in range(4):
            values.extend(float(matrix[row][column]) for row in range(3))
            values.append(0.0)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("PSP frame contains a non-finite matrix")
        struct.pack_into("<16f", self.data, offset, *values)

    def string(self, text):
        value = str(text).encode("ascii", "replace") + b"\0"
        offset = len(self.data)
        self.data.extend(value)
        return offset

    def material(self, name, rgba=0xFFFFFFFF, source_offset=0):
        offset = self.reserve(16)
        if source_offset:
            self.data[offset:offset + 16] = self.data[source_offset:source_offset + 16]
            effect = struct.unpack_from("<I", self.data, offset + 12)[0]
            self.pointer(offset + 12, effect)
        else:
            struct.pack_into("<4I", self.data, offset, 0, int(rgba) & 0xFFFFFFFF, 1, 0)
        struct.pack_into('<I', self.data, offset + 4, int(rgba) & 0xFFFFFFFF)
        if name:
            self.texture_fields.append((offset, str(name)))
        return offset

    def geometry(self, strips, material_offsets, skin=0):
        geometry, native = buildPspGeometry(strips)
        offset = self.reserve(0, 16)
        self.data.extend(geometry)
        self.data.extend(native)
        table = self.reserve(len(material_offsets) * 4)
        for index, material in enumerate(material_offsets):
            self.pointer(table + index * 4, material)
        self.pointer(offset + 12, table)
        struct.pack_into("<II", self.data, offset + 16, len(material_offsets), len(material_offsets))
        self.pointer(offset + 24, skin)
        return offset

    def finish(self, texture_atomic):
        self.align(4)
        base_fields = list(dict.fromkeys(self.relocations))
        extra_count = len(self.source_tail_fields) + len(self.source_prefix_fields) if self.source_tail else 1
        new_texture_count = len(self.texture_fields)
        table_offset = len(self.data)
        global_table = table_offset + len(self.source_prefix)
        total_count = len(base_fields) + extra_count + new_texture_count
        tail_offset = global_table + total_count * 4
        tail_shift = tail_offset - self.source_tail_offset
        tail = bytearray(self.source_tail) if self.source_tail else bytearray(struct.pack("<I", texture_atomic + 0x24))
        prefix = bytearray(self.source_prefix)
        prefix_shift = table_offset - self.source_local_offset
        for field, target in self.source_tail_targets:
            struct.pack_into("<I", self.data, field, target + tail_shift)
        for field, target in self.source_prefix_targets:
            struct.pack_into("<I", self.data, field, target + prefix_shift)
        fields = base_fields[:]
        for field, target in self.source_prefix_fields:
            new_target = target + tail_shift if target >= self.source_tail_offset else target
            if self.source_local_offset <= target < self.source_global_offset:
                new_target = target + prefix_shift
            struct.pack_into("<I", prefix, field - self.source_local_offset, new_target)
            fields.append(field + prefix_shift)
        if self.source_tail:
            for field, target in self.source_tail_fields:
                new_field = field + tail_shift
                new_target = target + tail_shift if target >= self.source_tail_offset else target
                if self.source_local_offset <= target < self.source_global_offset:
                    new_target = target + prefix_shift
                struct.pack_into("<I", tail, field - self.source_tail_offset, new_target)
                fields.append(new_field)
            if self.source_local_offset <= self.source_texture_head < self.source_global_offset:
                texture_head = self.source_texture_head + prefix_shift
            else:
                texture_head = self.source_texture_head + tail_shift
        else:
            texture_head = tail_offset
            fields.append(tail_offset)
        for field, name in self.texture_fields:
            target = tail_offset + len(tail)
            tail.extend(name.encode("ascii", "replace") + b"\0")
            struct.pack_into("<I", self.data, field, target)
            fields.append(field)
        if len(fields) != total_count or len(set(fields)) != len(fields):
            raise ValueError("Duplicate PSP MDL relocation fields")
        self.data.extend(prefix)
        self.data.extend(struct.pack("<" + "I" * len(fields), *fields))
        self.data.extend(tail)
        logical_end = len(self.data)
        struct.pack_into("<6I", self.data, 4, 0, logical_end, table_offset, global_table,
                         len(fields), texture_head)
        struct.pack_into("<I", self.data, 0x1C, self.allocation)
        self.align(2048)
        result = bytes(self.data)
        validatePspResource(result)
        return result


def buildPspGeometry(strips):
    if not strips or len(strips) > 4096:
        raise ValueError("PSP geometry must contain 1 to 4096 strips")
    vertices = [vertex for strip in strips for vertex in strip['vertices']]
    if not vertices or len(vertices) > 1000000:
        raise ValueError("PSP geometry has too many vertices")
    has_skin = any(vertex['weights'] for vertex in vertices)
    has_uv = any(strip['has_uv'] for strip in strips)
    has_colors = any(strip['has_colors'] for strip in strips)
    has_normals = any(strip['has_normals'] for strip in strips)
    flags = 2 << 7
    if has_uv:
        flags |= 3
    if has_colors:
        flags |= 7 << 2
    if has_normals:
        flags |= 1 << 5
    if has_skin:
        flags |= (1 << 9) | (7 << 14)
    layout = buildPspVertexLayout(flags)
    stride = layout['stride']
    members = layout['offsets']
    minimum = [min(vertex['position'][axis] for vertex in vertices) for axis in range(3)]
    maximum = [max(vertex['position'][axis] for vertex in vertices) for axis in range(3)]
    position = [(minimum[axis] + maximum[axis]) * 0.5 for axis in range(3)]
    scale = [max((maximum[axis] - minimum[axis]) * 0.5 * 32768.0 / 32760.0, 1.0e-6)
             for axis in range(3)]
    radius = max(math.sqrt(sum((vertex['position'][axis] - position[axis]) ** 2 for axis in range(3)))
                 for vertex in vertices)
    vertex_offset = (0x48 + len(strips) * 0x30 + 15) & ~15
    native = bytearray(vertex_offset + len(vertices) * stride)
    struct.pack_into("<4I4f3fi3fiIf", native, 0, len(native), flags, len(strips), 0,
                     *position, radius, *scale, len(vertices), *position, 0, vertex_offset, 0.0)
    cursor = 0
    for strip_index, strip in enumerate(strips):
        palette = sorted({bone for vertex in strip['vertices'] for bone, weight in vertex['weights'] if weight > 0})
        if len(palette) > 8 or any(not 0 <= bone <= 255 for bone in palette):
            raise ValueError("PSP strips support at most eight skin bones")
        palette_count = len(palette)
        palette += [0] * (8 - palette_count)
        uv_values = [vertex['uv'] for vertex in strip['vertices']]
        clip = [min(uv[axis] for uv in uv_values) for axis in range(2)]
        clip += [max(uv[axis] for uv in uv_values) for axis in range(2)]
        count = len(strip['vertices'])
        if not 3 <= count <= 65537:
            raise ValueError("Invalid PSP strip vertex count")
        struct.pack_into("<IHHf2f4ff8B", native, 0x48 + strip_index * 0x30,
                         cursor * stride, count - 2, strip['material'], 0.0, 1.0, 1.0,
                         *clip, 0.0, *palette)
        for vertex in strip['vertices']:
            offset = vertex_offset + cursor * stride
            if has_skin:
                weights = dict(vertex['weights'])
                used_bones = len({bone for bone, weight in vertex['weights'] if weight > 0})
                if used_bones == 0:
                    raise ValueError("PSP skin vertex has no weights")
                values = [float(weights.get(palette[slot], 0.0)) if slot < palette_count else 0.0
                          for slot in range(8)]
                total = sum(values)
                scaled = [value * 128.0 / total for value in values]
                quantized = [int(math.floor(value)) for value in scaled]
                remaining = 128 - sum(quantized)
                order = sorted(range(8), key=lambda slot: scaled[slot] - quantized[slot], reverse=True)
                for slot in order[:remaining]:
                    quantized[slot] += 1
                struct.pack_into("<8B", native, offset + members['weights'], *quantized)
            if has_uv:
                struct.pack_into("<2f", native, offset + members['uv'], *vertex['uv'])
            if has_colors:
                struct.pack_into("<4B", native, offset + members['color'], *vertex['color'])
            if has_normals:
                normal = Vector(vertex['normal']).normalized()
                packed = [max(-128, min(127, round(float(value) * 128.0))) for value in normal]
                struct.pack_into("<3b", native, offset + members['normal'], *packed)
            packed_position = [round((vertex['position'][axis] - position[axis]) / scale[axis] * 32768.0)
                               for axis in range(3)]
            struct.pack_into("<3h", native, offset + members['position'], *packed_position)
            cursor += 1
    geometry = struct.pack("<8I", 8, 0, 1, 0, 0, 0, 0, 0)
    return geometry, bytes(native)


def validatePspResource(data):
    if len(data) % 2048 or data[:4] != b"ldm\0":
        raise ValueError("Invalid PSP MDL file")
    logical_end, local, global_table, count = struct.unpack_from("<4I", data, 8)
    if global_table < local or (global_table - local) % 4 or not 0x28 <= local <= logical_end <= len(data):
        raise ValueError("Invalid PSP MDL relocation offsets")
    if global_table + count * 4 > logical_end:
        raise ValueError("PSP MDL relocation table is truncated")
    fields = set()
    for index in range(count):
        field = struct.unpack_from("<I", data, global_table + index * 4)[0]
        if field in fields or field % 4 or not 0x20 <= field <= logical_end - 4:
            raise ValueError("Invalid PSP MDL relocation field")
        fields.add(field)
        target = struct.unpack_from("<I", data, field)[0]
        if not 0 < target < logical_end:
            raise ValueError("PSP MDL pointer is outside the resource")
    probe = probeStoriesResourceHeader(data)
    if not probe or probe['platform'] != 'PSP':
        raise ValueError("PSP MDL geometry could not be read")
    return {'logical_size': logical_end, 'pointer_count': count, 'top_level_ptr': probe['top_level_ptr']}
