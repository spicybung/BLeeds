# BLeeds - Shared Stories world models
# Author: spicybung
# Years: 2025 - 2026

import struct
from collections import defaultdict
from pathlib import Path


SECTOR_SIZE = 2048
MAX_SHARED_MODEL_BYTES = 16 * 1024 * 1024
MAX_SHARED_TEXTURE_BYTES = 16 * 1024 * 1024


def sharedModelDirectories(lvz_path):
    source = Path(lvz_path).expanduser()
    parent = source.parent
    roots = [parent]
    if parent.name.casefold() in ('lvz', 'img', 'models', 'stream'):
        roots.append(parent.parent)
    folders = []
    for root in roots:
        folders.append(root)
        for child_name in ('models', 'img', 'lvz', 'stream'):
            child = root / child_name
            if child.is_dir():
                folders.append(child)
    return list(dict.fromkeys(folders))


def findSharedModelArchives(lvz_path):
    archives = []
    seen = set()
    for directory in sharedModelDirectories(lvz_path):
        if not directory.is_dir():
            continue
        for entry in directory.iterdir():
            if not entry.is_file():
                continue
            name = entry.name.casefold()
            if not name.endswith('.img'):
                continue
            stem = entry.stem.casefold()
            if stem not in ('gta3ps2', 'gta3psp', 'generic', 'models', 'common'):
                continue
            try:
                key = entry.resolve()
            except OSError:
                key = entry
            if key not in seen:
                seen.add(key)
                archives.append(entry)
    return archives


def findSharedMdlFiles(lvz_path, wanted_names):
    wanted = {str(name).casefold() for name in wanted_names if name}
    found = {}
    if not wanted:
        return found
    for directory in sharedModelDirectories(lvz_path):
        if not directory.is_dir():
            continue
        for entry in directory.iterdir():
            if not entry.is_file() or entry.suffix.casefold() != '.mdl':
                continue
            name = entry.stem.casefold()
            if name in wanted and name not in found:
                found[name] = entry
    return found


def indexSharedModelArchive(data):
    records = defaultdict(list)
    start = 0
    while True:
        offset = data.find(b'ldm\x00', start)
        if offset < 0:
            break
        start = offset + 4
        if offset % SECTOR_SIZE or offset + 0x24 > len(data):
            continue
        length, local_table, global_table = struct.unpack_from('<III', data, offset + 8)
        native_id = struct.unpack_from('<I', data, offset + 0x14)[0]
        if not 0x40 <= length <= MAX_SHARED_MODEL_BYTES:
            continue
        if offset + length > len(data) or native_id > 65535:
            continue
        if not 0 < local_table <= global_table <= length + 0x10:
            continue
        records[native_id].append((offset, length))
    return records


def indexSharedTextureArchive(data, wanted_names):
    from ..leedsLib.tex import parse_container, slot_base_from_slot_ptr

    wanted = {str(name).casefold() for name in wanted_names if name}
    result = defaultdict(list)
    if not wanted:
        return result
    start = 0
    while True:
        offset = data.find(b'xet\x00', start)
        if offset < 0:
            break
        start = offset + 4
        if offset % SECTOR_SIZE or offset + 0x30 > len(data):
            continue
        length = struct.unpack_from('<I', data, offset + 8)[0]
        if not 0x60 <= length <= MAX_SHARED_TEXTURE_BYTES or offset + length > len(data):
            continue
        chunk = data[offset:offset + length]
        first_slot, last_slot = struct.unpack_from('<II', chunk, 0x28)
        if chunk[0x20] == 6:
            first_slot, last_slot = last_slot, first_slot
        if not 0 < first_slot < length:
            continue
        slot = first_slot
        visited = set()
        for _ in range(4096):
            base = slot_base_from_slot_ptr(slot)
            if base in visited:
                break
            visited.add(base)
            entry = parse_container(chunk, base)
            if entry is None:
                break
            name = str(entry.get('name', '')).casefold()
            if name in wanted:
                result[name].append((offset, length))
            slot = int(entry['prev_slot'] if chunk[0x20] == 6 else entry['next_slot'])
            if slot in (0, 0x28) or slot >= length:
                break
    return result


def readSharedModelNativeId(model_metadata):
    try:
        native_id = model_metadata.get('native_model_id', None)
        if native_id is not None:
            return int(native_id)
        raw = bytes.fromhex(model_metadata['raw_0x20'])
        if len(raw) >= 0x20:
            return int(struct.unpack_from('<H', raw, 0x1E)[0])
    except (KeyError, ValueError, TypeError, struct.error):
        pass
    return -1


def chooseSharedModelGeometry(source_name, model_name, raw_data, offsets, game_hint):
    from ..leedsLib.native_mdl import read_stories

    best = None
    best_parts = None
    best_score = -1
    for offset, length in offsets:
        try:
            data = raw_data[offset:offset + length]
            source = '%s:%s@0x%X' % (source_name, model_name, offset)
            context = read_stories(source, 'PS2', 'SIM', game=game_hint, data=data).read()
            atomic = getattr(context, 'atomic', None)
            geometry = getattr(atomic, 'ps2_geometry', None)
            parts = list(getattr(geometry, 'parts', ()) or ())
            score = sum(len(getattr(part, 'faces', ()) or ()) for part in parts)
            if score > best_score and score > 0:
                best, best_parts, best_score = context, parts, score
        except (ValueError, RuntimeError, IndexError, TypeError, struct.error):
            continue
    return best, best_parts


def buildSharedModelTemplate(model_id, metadata, parsed_context, source_path, collection):
    import bpy
    import numpy as np
    from .mdl_importer import buildStoriesGouraudPartData, get_or_create_material_for_stories
    from .. import get_or_create_corner_color_layer, set_mesh_gouraud_shading

    geometry = getattr(getattr(parsed_context, 'atomic', None), 'ps2_geometry', None)
    parts = list(getattr(geometry, 'parts', ()) or ())
    materials = list(getattr(geometry, 'materials', ()) or ())
    if not parts:
        return None

    vertices = []
    faces = []
    face_uvs = []
    face_colors = []
    polygon_material_ids = []
    material_indices = {}
    used_materials = []
    for part in parts:
        data = buildStoriesGouraudPartData(part)
        if not data.faces or not data.verts:
            continue
        material_id = int(getattr(part, 'material_id', 0))
        if material_id not in material_indices:
            material_indices[material_id] = len(used_materials)
            if 0 <= material_id < len(materials):
                used_materials.append(get_or_create_material_for_stories(
                    materials[material_id], material_id, str(source_path)))
            else:
                used_materials.append(None)
        base = len(vertices)
        vertices.extend(data.verts)
        faces.extend(tuple(base + int(v) for v in face) for face in data.faces)
        polygon_material_ids.extend([material_indices[material_id]] * len(data.faces))
        if len(data.face_uvs) == len(data.faces):
            face_uvs.extend(data.face_uvs)
        else:
            face_uvs.extend([[(0.0, 0.0)] * 3] * len(data.faces))
        if len(data.face_colors) == len(data.faces):
            face_colors.extend(data.face_colors)
        else:
            face_colors.extend([[(255, 255, 255, 255)] * 3] * len(data.faces))

    if not vertices or not faces:
        return None
    name = str(metadata.get('model_name') or ('Model_%d' % model_id))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    set_mesh_gouraud_shading(mesh, True)
    for material in used_materials:
        if material is None:
            material = bpy.data.materials.new('SharedMaterial')
        mesh.materials.append(material)
    for polygon, material_index in zip(mesh.polygons, polygon_material_ids):
        polygon.material_index = int(material_index)
    if len(face_uvs) == len(faces):
        uv_layer = mesh.uv_layers.new(name='UVMap')
        uv_array = np.asarray(face_uvs, dtype=np.float32).reshape(-1, 2)
        if uv_array.shape[0] == len(mesh.loops):
            uv_array[:, 1] = 1.0 - uv_array[:, 1]
            uv_layer.data.foreach_set('uv', uv_array.ravel())
    if len(face_colors) == len(faces):
        color_layer = get_or_create_corner_color_layer(mesh, 'Col')
        if color_layer is not None:
            colors = np.asarray(face_colors, dtype=np.float32).reshape(-1, 4)
            if colors.shape[0] == len(mesh.loops):
                colors *= 1.0 / 255.0
                color_layer.data.foreach_set('color', colors.ravel())
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.hide_viewport = True
    obj.hide_render = True
    obj['blds_kind'] = 'SHARED_STORIES_MDL'
    obj['blds_res_index'] = -1
    obj['blds_game_model_id'] = int(model_id)
    obj['blds_img_area_secondary_id'] = int(model_id)
    obj['blds_game_model_name'] = name
    obj['blds_source_shared_img_path'] = str(source_path)
    obj['blds_shared_mdl_native_id'] = readSharedModelNativeId(metadata)
    obj['blds_shared_mdl_part_count'] = len(parts)
    obj['blds_shared_mdl_faces'] = len(faces)
    return obj


def importSharedMdlTextures(raw_data, source_path, templates):
    import bpy
    from .tex_importer import decode_chk_to_blender_images, apply_images_to_imported_mdl_materials

    names = set()
    for obj in templates:
        for material in obj.data.materials:
            if material:
                name = str(material.get('bleeds_mdl_texture_name', '') or '').strip()
                if name:
                    names.add(name.casefold())
    matching = indexSharedTextureArchive(raw_data, names)
    images = []
    seen_offsets = set()
    for name in sorted(names):
        for offset, length in matching.get(name, []):
            if offset in seen_offsets:
                continue
            seen_offsets.add(offset)
            try:
                images.extend(decode_chk_to_blender_images(
                    str(source_path), platform='ps2', prefix='',
                    source_data=raw_data[offset:offset + length],
                    only_names=names))
            except (ValueError, RuntimeError, IndexError, struct.error):
                continue
    if images:
        apply_images_to_imported_mdl_materials(images, templates)
    return len(images)


def readNamedImgDirectory(archive):
    dir_path = archive.with_suffix('.dir')
    if not dir_path.is_file():
        return {}
    try:
        directory = dir_path.read_bytes()
    except OSError:
        return {}
    if not directory or len(directory) % 32:
        return {}

    import struct

    named = {}
    for position in range(0, len(directory), 32):
        entry = directory[position:position + 32]
        filename = entry[:24].split(b'\x00', 1)[0]
        try:
            filename = filename.decode('ascii').strip()
        except UnicodeDecodeError:
            continue
        if not filename.casefold().endswith('.mdl'):
            continue
        start_sector, sector_count = struct.unpack_from('<II', entry, 24)
        if not sector_count or sector_count > 8192:
            continue
        named.setdefault(Path(filename).stem.casefold(), []).append(
            (start_sector * SECTOR_SIZE, sector_count * SECTOR_SIZE))
    return named


def iterBuildSharedWorldModels(lvz_path, summary, model_ids, collection, import_textures=True, progress_callback=None):
    from .world_selection import namedWorldCategory
    from .lvz_img_importer import LVZ

    metadata_by_id = summary.get('model_meta_by_id', {}) or {}
    targets = {}
    for model_id in sorted(set(int(value) for value in model_ids)):
        metadata = metadata_by_id.get(model_id, {})
        name = str(metadata.get('model_name', '') or '').strip()
        if name and namedWorldCategory(name) in ('VEGETATION', 'GENERICS'):
            targets[model_id] = metadata

    if not targets:
        return []

    # Only an exact model filename or a named DIR entry identifies an external MDL.
    # The native_model_id in GAME.DTZ is NOT a reliable index into gta3PS2.img.
    # Comparing those numbers can select completely unrelated vehicle/ped models.
    standalone_files = findSharedMdlFiles(
        lvz_path, (metadata['model_name'] for metadata in targets.values()))
    indexed_archives = []
    for archive in findSharedModelArchives(lvz_path):
        named_entries = readNamedImgDirectory(archive)
        if named_entries:
            indexed_archives.append((archive, named_entries))

    templates = []
    completed = set()
    failures = {}
    indexed_archive_textures = defaultdict(list)
    for number, (model_id, metadata) in enumerate(targets.items(), 1):
        name = str(metadata['model_name']).strip()
        source = standalone_files.get(name.casefold())
        data = None
        data_source = None
        offsets = None

        if source is not None:
            try:
                data = source.read_bytes()
                data_source = source
                offsets = [(0, len(data))]
            except OSError as exc:
                failures[model_id] = 'Cannot read %s: %s' % (source.name, exc)
        else:
            for archive, directory in indexed_archives:
                entries = directory.get(name.casefold())
                if not entries:
                    continue
                try:
                    file_size = archive.stat().st_size
                    offsets = [entry for entry in entries
                               if entry[0] >= 0 and entry[0] + entry[1] <= file_size]
                    if offsets:
                        with archive.open('rb') as archive_file:
                            offset, length = offsets[0]
                            archive_file.seek(offset)
                            data = archive_file.read(length)
                        data_source = archive
                        offsets = [(0, len(data))]
                except OSError as exc:
                    failures[model_id] = 'Cannot read %s: %s' % (archive.name, exc)
                if offsets and data is not None:
                    break
                data = None

        if data is not None and offsets:
            # Check the file header before decoding. Never use a model from a
            # neighbouring ID, similar name, material, or arbitrary IMG offset.
            offsets = [(offset, length) for offset, length in offsets
                       if length >= 0x40 and data[offset:offset + 4] == b'ldm\x00']
            if offsets:
                try:
                    parsed, parts = chooseSharedModelGeometry(
                        data_source.name, name, data, offsets,
                        str(summary.get('game_hint', 'VCS') or 'VCS').upper())
                    if parsed is not None and parts:
                        obj = buildSharedModelTemplate(
                            model_id, metadata, parsed, data_source, collection)
                        if obj is not None:
                            templates.append(obj)
                            completed.add(model_id)
                            if import_textures and data_source.suffix.casefold() == '.img':
                                indexed_archive_textures[data_source].append(obj)
                except (ValueError, RuntimeError, IndexError, TypeError, struct.error) as exc:
                    failures[model_id] = 'Cannot decode named MDL: %s' % exc
                if model_id not in completed and model_id not in failures:
                    failures[model_id] = 'Named MDL has no readable mesh'
            else:
                failures[model_id] = 'Named file is not a valid Leeds MDL'
        elif model_id not in failures:
            failures[model_id] = 'No exact named MDL found'

        if progress_callback is not None:
            progress_callback(number, len(targets))
        if number % 3 == 0:
            yield None

    for source, objects in indexed_archive_textures.items():
        try:
            raw = source.read_bytes()
            imported_textures = importSharedMdlTextures(raw, source, objects)
            LVZ.dbg('[shared-mdl] exact IMG textures: %d from %s' % (
                imported_textures, source.name))
            del raw
        except (ValueError, RuntimeError, IndexError, OSError) as exc:
            LVZ.dbg('[shared-mdl] texture read failed for %s: %s' % (source.name, exc))
        yield None

    summary['shared_model_results'] = {
        'found': sorted(completed),
        'missing': {model_id: failures.get(model_id, 'Not found')
                    for model_id in targets if model_id not in completed},
        'searched_archives': [str(path) for path, _names in indexed_archives],
        'searched_folders': [str(path) for path in sharedModelDirectories(lvz_path)],
    }
    LVZ.dbg('[shared-mdl] exact named models=%d missing=%d (no fallback meshes)' % (
        len(completed), len(targets) - len(completed)))
    for model_id in sorted(failures):
        if model_id not in completed:
            LVZ.dbg('[shared-mdl] missing ID=%d name=%s: %s' % (
                model_id, targets[model_id].get('model_name', ''), failures[model_id]))
    return templates
