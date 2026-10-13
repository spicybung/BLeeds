
import re
from pathlib import Path
from ..data.data_zlib import decompress_game_dtz


def worldArchiveStem(path):
    name = Path(path).name
    if name.lower().endswith('.img.zip'):
        name = name[:-4]
    stem = Path(name).stem
    return re.sub(r'\s*\(\d+(?:-\d+)?\)$', '', stem).casefold()


def matchingWorldImg(lvz_path):
    lvz = Path(lvz_path)
    exact = [lvz.with_suffix(suffix) for suffix in ('.img', '.IMG', '.img.zip', '.IMG.zip')]
    for candidate in exact:
        if candidate.is_file():
            return str(candidate)
    matches = sorted(child for child in lvz.parent.iterdir() if child.is_file()
                     and (child.suffix.lower() == '.img' or child.name.lower().endswith('.img.zip'))
                     and worldArchiveStem(child) == worldArchiveStem(lvz))
    return str(matches[0]) if len(matches) == 1 else ''


def resolveWorldSelection(filepath):
    selected = Path(filepath).expanduser().resolve()
    if not selected.is_file():
        raise ValueError("Selected world file does not exist: %s" % selected.name)
    extension = selected.suffix.lower()
    if extension == '.lvz':
        return [str(selected)], ''
    lvz_files = sorted(child for child in selected.parent.iterdir()
                       if child.is_file() and child.suffix.lower() == '.lvz')
    if extension == '.img':
        matches = [child for child in lvz_files if worldArchiveStem(child) == worldArchiveStem(selected)]
        if len(matches) != 1:
            raise ValueError("Put the matching same-name LVZ beside %s." % selected.name)
        return [str(matches[0])], ''
    if extension == '.dtz':
        decompress_game_dtz(selected.read_bytes())
        paired = [str(child) for child in lvz_files if matchingWorldImg(child)]
        if not paired:
            raise ValueError("GAME.DTZ needs its LVZ/IMG world files beside it. Put the matching pairs in the same folder.")
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
