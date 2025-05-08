import struct
from mathutils import Matrix

def read_header(f):
    data = f.read(0x28)
    header = struct.unpack("<4sIIIIIIIii", data)
    return {
        'signature': header[0].decode("ascii"),
        'version': header[1],
        'file_size': header[2],
        'data_size': header[3],
        'offset_table_start': header[4],
        'num_table_entries': header[5],
        'zero1': header[6],
        'zero2': header[7],
        'first_entry_offset': header[8],
        'last_entry_offset': header[9],
    }

def read_entry_index(f, offset):
    f.seek(offset)
    entry_index_data = f.read(16)
    entry_index = struct.unpack("<iiii", entry_index_data)
    return {
        'next_offset': entry_index[0],
        'prev_offset': entry_index[1],
        'entry_data_offset': entry_index[2],
        'zero_field': entry_index[3],
    }

def read_entry_structure(f, entry_data_offset):
    f.seek(entry_data_offset)
    data = f.read(0x1C)
    entry = struct.unpack("<7i", data)
    return {
        'root_bone_offset': entry[0],
        'unknown': entry[3],
        'first_obj_info_offset': entry[4],
        'last_obj_info_offset': entry[5],
    }

def read_object_infos(f, first_offset, last_offset):
    infos = []
    visited = set()
    offset = first_offset if first_offset != 0 else last_offset
    while offset != 0 and offset not in visited:
        visited.add(offset)
        f.seek(offset)
        data = f.read(28)
        if len(data) < 28:
            break
        values = struct.unpack("<7i", data)
        infos.append({
            'offset': offset,
            'next_offset': values[0],
            'prev_offset': values[1],
            'parent_bone_offset': values[2],
            'object_data_offset': values[3],
            'root_entry_offset': values[4],
            'zero_field': values[5],
            'unknown': values[6]
        })
        offset = values[0]
    return infos

def read_vertex_by_type(f, vtype, count, per_vertex_size):
    vertices = []
    for _ in range(count):
        if vtype == 0x52:
            data = f.read(24)
            pos = struct.unpack_from("<3f", data, 0)
            norm = struct.unpack_from("<3h", data, 12)
            color = struct.unpack_from("<4B", data, 18)
            vertices.append((pos, tuple(n / 32768.0 for n in norm), color, None))

        elif vtype == 0x152:
            data = f.read(32)
            pos = struct.unpack_from("<3f", data, 0)
            norm = struct.unpack_from("<3h", data, 12)
            color = struct.unpack_from("<4B", data, 18)
            uv = struct.unpack_from("<2f", data, 22)
            vertices.append((pos, tuple(n / 32768.0 for n in norm), color, uv))

        elif vtype == 0x115E:
            data = f.read(52)
            pos = struct.unpack_from("<3f", data, 0)
            weights = struct.unpack_from("<4f", data, 12)
            bone_ids = struct.unpack_from("<4B", data, 28)
            norm = struct.unpack_from("<3h", data, 32)
            color = struct.unpack_from("<4B", data, 38)
            uv = struct.unpack_from("<2f", data, 42)
            vertices.append((pos, tuple(n / 32768.0 for n in norm), color, uv, weights, bone_ids))

        elif vtype == 0x125E:
            data = f.read(60)
            pos = struct.unpack_from("<3f", data, 0)
            weights = struct.unpack_from("<4f", data, 12)
            bone_ids = struct.unpack_from("<4B", data, 28)
            norm = struct.unpack_from("<3h", data, 32)
            color = struct.unpack_from("<4B", data, 38)
            uv1 = struct.unpack_from("<2f", data, 42)
            uv2 = struct.unpack_from("<2f", data, 50)
            vertices.append((pos, tuple(n / 32768.0 for n in norm), color, uv1, uv2, weights, bone_ids))

        elif vtype == 0x252:
            data = f.read(40)
            pos = struct.unpack_from("<3f", data, 0)
            norm = struct.unpack_from("<3h", data, 12)
            color = struct.unpack_from("<4B", data, 18)
            uv1 = struct.unpack_from("<2f", data, 22)
            uv2 = struct.unpack_from("<2f", data, 30)
            vertices.append((pos, tuple(n / 32768.0 for n in norm), color, uv1, uv2))

        else:
            raise ValueError(f"Unknown VertexElementType: 0x{vtype:X}")
    return vertices

def read_bone_transforms(f, bone_trans_offset):
    f.seek(bone_trans_offset)
    header = f.read(8)
    if len(header) < 8:
        return []
    num_bones, data_offset = struct.unpack("<2I", header)
    f.seek(data_offset)
    transforms = []
    for _ in range(num_bones):
        raw = struct.unpack("<16f", f.read(64))
        mat = Matrix((
            (raw[0], raw[4], raw[8], raw[12]),
            (raw[1], raw[5], raw[9], raw[13]),
            (raw[2], raw[6], raw[10], raw[14]),
            (raw[3], raw[7], raw[11], raw[15]),
        ))
        mat = mat @ Matrix.Rotation(-3.14159265 / 2, 4, 'X')
        transforms.append(mat)
    return transforms
