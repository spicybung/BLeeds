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

import re
from pathlib import Path


def worldArchiveStem(path):
    name = Path(path).name
    if name.lower().endswith('.img.zip'):
        name = name[:-4]
    stem = Path(name).stem
    return re.sub(r'\s*\(\d+(?:-\d+)?\)$', '', stem).casefold()


def worldCompanionDirectories(path):
    parent = Path(path).parent
    directories = [parent]
    if parent.name.casefold() in ('lvz', 'img', 'models'):
        directories.append(parent.parent)
    for base in (parent, parent.parent):
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if child.is_dir() and child.name.casefold() in ('lvz', 'img', 'models'):
                directories.append(child)
                for nested in sorted(child.iterdir()):
                    if nested.is_dir() and nested.name.casefold() in ('lvz', 'img'):
                        directories.append(nested)
    return list(dict.fromkeys(directories))


def matchingWorldImg(lvz_path):
    lvz = Path(lvz_path)
    for directory in worldCompanionDirectories(lvz):
        matches = sorted(
            child for child in directory.iterdir()
            if child.is_file()
            and (child.suffix.casefold() == '.img' or child.name.casefold().endswith('.img.zip'))
            and worldArchiveStem(child) == worldArchiveStem(lvz)
        )
        exact = [child for child in matches if child.name.casefold() == lvz.stem.casefold() + '.img']
        if len(exact) == 1:
            return str(exact[0])
        if len(matches) == 1:
            return str(matches[0])
        if matches:
            raise ValueError('More than one IMG matches %s in %s' % (lvz.name, directory))
    return ''


def resolveWorldSelection(filepath):
    selected = Path(filepath).expanduser().resolve()
    if not selected.is_file():
        raise ValueError("Selected world file does not exist: %s" % selected.name)
    extension = selected.suffix.lower()
    if extension == '.lvz':
        return [str(selected)], ''
    lvz_files = sorted({
        child for directory in worldCompanionDirectories(selected)
        for child in directory.iterdir()
        if child.is_file() and child.suffix.casefold() == '.lvz'
    })
    if extension == '.img':
        matches = [child for child in lvz_files if worldArchiveStem(child) == worldArchiveStem(selected)]
        if len(matches) != 1:
            raise ValueError("No unique matching LVZ was found for %s in the world folders." % selected.name)
        return [str(matches[0])], ''
    if extension == '.dtz':
        # The importer reads and decompresses GAME.DTZ when processing the world.
        # Doing it here as well doubles the initial DTZ read and decompression.
        paired = [str(child) for child in lvz_files if matchingWorldImg(child)]
        if not paired:
            raise ValueError("No matching LVZ/IMG pairs were found beside GAME.DTZ or in its LVZ, IMG, or MODELS folders.")
        return paired, str(selected)
    raise ValueError("Choose GAME.DTZ, an LVZ, or its IMG companion.")


def iterImportWorldSelection(operator, context, filepath, **options):
    from .lvz_img_importer import iter_import_lvz_img_archive
    lvz_paths, dtz_path = resolveWorldSelection(filepath)
    for lvz_path in lvz_paths:
        result = yield from iter_import_lvz_img_archive(
            operator=operator, context=context, lvz_path=lvz_path,
            game_dtz_path=dtz_path, **options)
        if result is not None and 'CANCELLED' in result:
            return result
    return {'FINISHED'}


def namedWorldCategory(name):
    name = Path(str(name).replace('\\', '/')).stem.casefold()
    name = re.sub(r'^(?:slod|lod)[_\-]*', '', name)
    if re.match(r'^(?:vegetation|veg|tree|palm|bush|shrub|hedge|fern|plant|grass)(?:[_\-0-9]|$)', name):
        return 'VEGETATION'
    if re.match(r'^(?:generic|gen|lamppost|lampost|streetlamp|trafficlight|traffic_light|bench|bin|bollard|hydrant|phonebooth|mailbox)(?:[_\-0-9]|$)', name):
        return 'GENERICS'
    return 'UNKNOWN'


def worldObjectCategory(obj, model_name=''):
    category = str(obj.get('blds_world_category', '')).upper()
    if category in ('VEGETATION', 'GENERICS'):
        return category
    for name in (model_name, obj.get('blds_game_model_name', ''), obj.name):
        category = namedWorldCategory(name)
        if category != 'UNKNOWN':
            return category
    categories = []
    for material in getattr(getattr(obj, 'data', None), 'materials', ()):
        if material is None:
            return 'UNKNOWN'
        name = material.get('bleeds_texture_name', '') or material.name
        # Grass materials can belong to terrain, so they do not classify a mesh.
        if str(name).casefold().startswith('grass'):
            return 'UNKNOWN'
        categories.append(namedWorldCategory(name))
    if categories and len(set(categories)) == 1:
        return categories[0]
    return 'UNKNOWN'


def importDtzWorldPlacements(context, summary, records, templates, area_model_ids, sectors, collection,
                             import_vegetation=True, import_generics=True):
    from collections import defaultdict
    from .lvz_img_importer import blds_entity_matrix, blds_nearest_sector_xy_for_world_position

    candidates = defaultdict(list)
    for obj in templates:
        model_id = int(obj.get('blds_img_area_secondary_id',
                               area_model_ids.get(int(obj.get('blds_res_index', -1)), -1)))
        if model_id >= 0:
            candidates[model_id].append(obj)
    for record in records:
        if int(record.get('game_model_id', -1)) >= 0:
            candidates[int(record['game_model_id'])].append(record['object'])

    active = {(int(sector['sector_x']), int(sector['sector_y'])): int(sector['sector_index'])
              for sector in sectors}
    game = str(sectors[0].get('game_hint', 'vcs')) if sectors else 'vcs'
    placed = {(int(record.get('game_model_id', -1)),
               tuple(round(float(value), 4) for row in record['matrix_world'] for value in row))
              for record in records}
    missing = defaultdict(lambda: {'count': 0, 'reasons': set(), 'positions': []})
    imported_counts = defaultdict(int)
    count = 0
    metadata_by_id = summary.get('model_meta_by_id', {}) or {}

    for entity in summary.get('world_entities', []):
        model_id = int(entity['model_id'])
        name = str(metadata_by_id.get(model_id, {}).get('model_name', '') or '')
        category = namedWorldCategory(name)
        if category == 'UNKNOWN' and not (import_vegetation and import_generics):
            continue
        if ((category == 'VEGETATION' and not import_vegetation)
                or (category == 'GENERICS' and not import_generics)):
            continue

        position = tuple(float(value) for value in entity['position'])
        cell = blds_nearest_sector_xy_for_world_position(position[0], position[1], game)
        if active and cell not in active:
            continue
        matrix = blds_entity_matrix(entity)
        key = (model_id, tuple(round(float(value), 4) for row in matrix for value in row))
        if key in placed:
            continue

        known = candidates.get(model_id, [])
        models = [obj for obj in known if not obj.get('blds_world_baked', False)
                  and (obj.get('blds_img_area_cell_x') is None or
                       (int(obj['blds_img_area_cell_x']), int(obj['blds_img_area_cell_y']))
                       == (cell[0] // 3, cell[1] // 3))]
        reason = ''
        if not models:
            reason = 'Wrong AREA or baked geometry' if known else 'No exact model geometry found'
        elif len({obj.data.as_pointer() for obj in models}) > 1:
            reason = 'Conflicting model meshes: cannot verify which one belongs here'

        if reason:
            entry = missing[model_id]
            entry['count'] += 1
            entry['reasons'].add(reason)
            if len(entry['positions']) < 12:
                entry['positions'].append(position)
            continue

        source = models[0]
        obj = source.copy()
        obj.name = name or 'DTZ Model %d' % model_id
        collection.objects.link(obj)
        obj.parent = None
        obj.matrix_world = matrix
        obj.hide_viewport = False
        obj.hide_render = False
        obj.hide_set(False)
        obj['blds_world_category'] = category
        obj['blds_game_model_id'] = model_id
        obj['blds_dtz_placement'] = True
        obj['blds_visible_placement_instance'] = True
        obj['blds_raw_parser_base_hidden_fast_cleanup'] = False
        obj['blds_game_model_name'] = name
        records.append({'object': obj, 'res_id': int(source.get('blds_res_index', -1)),
                        'game_model_id': model_id, 'sector_index': active.get(cell, -1),
                        'matrix_world': obj.matrix_world.copy(),
                        'world_x': position[0], 'world_y': position[1], 'world_z': position[2],
                        'row_index': int(entity.get('pool_index', -1)), 'pass_name': 'DTZ'})
        placed.add(key)
        imported_counts[model_id] += 1
        count += 1

    missing_rows = {}
    for model_id, entry in missing.items():
        name = str(metadata_by_id.get(model_id, {}).get('model_name', '') or '')
        missing_rows[model_id] = {
            'name': name,
            'category': namedWorldCategory(name),
            'count': entry['count'],
            'reasons': sorted(entry['reasons']),
            'positions': list(entry['positions']),
        }

    summary['dtz_models_imported'] = count
    summary['dtz_imported_model_counts'] = dict(imported_counts)
    summary['dtz_missing_model_ids'] = sorted(missing_rows)
    summary['dtz_missing_model_rows'] = missing_rows
    return count, sorted(missing_rows)


def writeDtzMissingModelsLog(lvz_path, summary, imported_count):
    from collections import Counter

    target = Path(lvz_path).with_name(Path(lvz_path).stem + '_blds_missing_dtz_models.txt')
    missing = summary.get('dtz_missing_model_rows', {}) or {}
    imported = summary.get('dtz_imported_model_counts', {}) or {}
    shared = summary.get('shared_model_results', {}) or {}
    categories = Counter(row['category'] for row in missing.values())
    with target.open('w', encoding='utf-8', newline='\n') as output:
        output.write('BLeeds - Missing DTZ Models\n')
        output.write('LVZ: %s\n' % lvz_path)
        output.write('DTZ: %s\n' % str(summary.get('source_path', '')))
        output.write('Imported DTZ instances: %d\n' % imported_count)
        output.write('Missing model IDs: %d\n' % len(missing))
        output.write('Missing vegetation: %d\n' % categories.get('VEGETATION', 0))
        output.write('Missing generics: %d\n' % categories.get('GENERICS', 0))
        output.write('Missing other: %d\n' % categories.get('UNKNOWN', 0))
        output.write('Only matching model IDs, exact MDL filenames, and named IMG directory entries are used.\n')
        output.write('No replacement, placeholder, nearest-ID, or guessed models are imported.\n')
        output.write('\nSearched folders:\n')
        for path in shared.get('searched_folders', []):
            output.write('  %s\n' % path)
        output.write('\nModels imported from DTZ:\n')
        for model_id in sorted(imported):
            name = summary.get('model_meta_by_id', {}).get(model_id, {}).get('model_name', '')
            output.write('  %d %s: %d placements\n' % (model_id, name, imported[model_id]))
        output.write('\nMissing models:\n')
        for model_id in sorted(missing):
            row = missing[model_id]
            source_reason = shared.get('missing', {}).get(model_id, '')
            output.write('%d | %s | %s | %d placements\n' % (
                model_id, row['name'] or '(unnamed)', row['category'], row['count']))
            for reason in row['reasons']:
                output.write('  Reason: %s\n' % reason)
            if source_reason:
                output.write('  Shared MDL: %s\n' % source_reason)
            for position in row['positions']:
                output.write('  Position: %.3f, %.3f, %.3f\n' % tuple(position))
            if row['count'] > len(row['positions']):
                output.write('  Other placements: %d\n' % (row['count'] - len(row['positions'])))
        if not missing:
            output.write('None.\n')
    return str(target)
