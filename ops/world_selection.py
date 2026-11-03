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
from ..data.data_zlib import decompress_game_dtz


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
        decompress_game_dtz(selected.read_bytes())
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
