# BLeeds - Scripts for working with R* Leeds formats in Blender
# Author: spicybung

from pathlib import PureWindowsPath

MODEL_TYPES = {
    'SIM': 'SimpleModel', 'SIMPLE': 'SimpleModel', 'SIMPLEMODEL': 'SimpleModel',
    'PED': 'ClumpModel', 'PEDMODEL': 'ClumpModel', 'CLUMP': 'ClumpModel', 'CLUMPMODEL': 'ClumpModel',
    'CUT': 'ClumpModel (CUT)', 'CUTSCENEMODEL': 'ClumpModel (CUT)',
    'VEH': 'VehicleModel', 'VEHMODEL': 'VehicleModel', 'VEHICLEMODEL': 'VehicleModel',
}

OBJECT_TYPE_ITEMS = (
    ('AUTO', 'Auto', 'Identify the object from its Blender type and imported file data'),
    ('EMPTY', 'Empty', 'A hierarchy frame or helper without model geometry'),
    ('DONT_EXPORT', "Don't Export", 'Exclude this object and its children from export'),
    ('MODEL', 'Model', 'Render model geometry'),
    ('COLLISION', 'Collision', 'Collision geometry'),
    ('LIGHT', 'Light', 'A light object'),
    ('2D_EFFECT', '2D Effect', 'A Leeds 2D effect helper'),
    ('ARMATURE', 'Armature', 'A model skeleton'),
)


def storedObjectValue(obj, name, default=None):
    # An untouched Blender default should not label an object as an imported model.
    if obj is None:
        return default
    try:
        value = obj.get(name)
    except (AttributeError, TypeError):
        return default
    if isinstance(value, str):
        return value
    try:
        if obj.is_property_set(name):
            return getattr(obj, name)
    except (AttributeError, TypeError):
        pass
    return default if value is None else value


def objectAncestors(obj):
    seen = set()
    while obj is not None and obj not in seen:
        seen.add(obj)
        yield obj
        obj = obj.parent


def isObjectExportable(obj):
    # Don't Export also applies to everything below this object.
    return all(str(storedObjectValue(owner, 'bleeds_object_type', 'AUTO')) != 'DONT_EXPORT'
               for owner in objectAncestors(obj))


def isModelMesh(obj):
    return obj.type == 'MESH' and isObjectExportable(obj) and objectRole(obj) == 'MODEL'


def importedModelOwner(obj):
    # A custom mesh can belong to the model through its armature, without being parented.
    owners = list(objectAncestors(obj))
    for modifier in getattr(obj, 'modifiers', ()):
        if modifier.type == 'ARMATURE' and modifier.object is not None:
            owners.extend(owner for owner in objectAncestors(modifier.object) if owner not in owners)
    for owner in reversed(owners):
        if (storedObjectValue(owner, 'bleeds_is_mdl_root', False)
                or owner.get('bleeds_dff_source') is not None
                or owner.get('bleeds_mh2_native_text') is not None):
            return owner
    for owner in owners:
        if any(storedObjectValue(owner, name) is not None for name in (
            'bleeds_mdl_type', 'bleeds_mh2_model_class', 'bleeds_mdl_filepath', 'bleeds_dff_profile')):
            return owner
    return None


def detectedObjectRole(obj):
    entity = str(storedObjectValue(obj, 'blds_entity_type', '')).upper()
    kind = str(storedObjectValue(obj, 'blds_kind', '')).upper()
    if obj.get('bleeds_col2_object', False) or entity == 'COLLISION' or 'COLLISION' in kind:
        return 'COLLISION'
    if kind in {'LEEDS_2D_EFFECT', 'LEEDS_2DFX'} or entity in {'2D_EFFECT', '2DFX'} or obj.get('blds_2dfx_effect_type') is not None:
        return effectRole(obj)
    if obj.type == 'LIGHT':
        return 'LIGHT'
    if obj.type == 'ARMATURE':
        return 'ARMATURE'
    if storedObjectValue(obj, 'bleeds_is_mdl_root', False) or obj.get('bleeds_dff_source') is not None:
        return 'MODEL'
    if obj.type == 'MESH':
        return 'MODEL'
    return 'EMPTY' if obj.type == 'EMPTY' else obj.type


def objectRole(obj):
    chosen = str(storedObjectValue(obj, 'bleeds_object_type', 'AUTO'))
    if chosen in {'2DFX', '2D_EFFECT'}:
        return effectRole(obj)
    return detectedObjectRole(obj) if chosen == 'AUTO' else chosen


def importedSourceCollection(obj):
    import bpy

    pending = list(obj.users_collection)
    visited = set()
    while pending:
        collection = pending.pop(0)
        if collection in visited:
            continue
        visited.add(collection)
        if collection.get('blds_source_lvz_path') or collection.get('blds_source_img_path'):
            return collection
        pending.extend(parent for parent in bpy.data.collections
                       if collection.name in parent.children and parent not in visited)
    return None


def describeObject(obj):
    owner = importedModelOwner(obj)
    owners = [obj] + ([owner] if owner is not None and owner != obj else [])
    values = {'role': objectRole(obj), 'detected_role': detectedObjectRole(obj), 'owner': owner,
              'model_type': '', 'game': '', 'platform': '', 'file_type': '', 'source': '', 'format': '', 'structure': '', 'version': ''}
    for current in owners:
        if not values['model_type']:
            for name in ('bleeds_mh2_model_class', 'bleeds_mdl_type'):
                layout = str(storedObjectValue(current, name, '')).upper()
                if layout in MODEL_TYPES:
                    values['model_type'] = MODEL_TYPES[layout]
                    break
        if not values['game']:
            values['game'] = str(storedObjectValue(current, 'bleeds_model_game', '') or
                                 current.get('blds_2dfx_game', '') or '')
        if not values['platform']:
            values['platform'] = str(current.get('bleeds_mh2_platform', '') or
                                     storedObjectValue(current, 'bleeds_mdl_platform', '') or '')
        if not values['source']:
            for name in ('bleeds_mdl_filepath', 'bleeds_mh2_path', 'bleeds_dff_path',
                         'blds_2dfx_source_path', 'blds_source_path', 'bleeds_col2_source_file'):
                source = storedObjectValue(current, name, '')
                if source:
                    values['source'] = str(source)
                    break
        if current.get('bleeds_dff_source') is not None or current.get('bleeds_dff_part') is not None:
            values['file_type'] = 'DFF'
        elif storedObjectValue(current, 'bleeds_is_mdl_root', False):
            values['file_type'] = 'MDL'
    if not values['source']:
        collection = importedSourceCollection(obj)
        if collection is not None:
            values['source'] = str(collection.get('blds_source_lvz_path', '') or collection.get('blds_source_img_path', ''))
            if not values['platform']:
                values['platform'] = str(collection.get('blds_platform', ''))
    if values['source']:
        suffix = PureWindowsPath(values['source']).suffix.lstrip('.').upper()
        if suffix:
            values['file_type'] = suffix
    if values['role'] == 'COLLISION' and obj.get('bleeds_col2_object', False):
        values['file_type'] = 'COL2'
    if values['file_type'] == 'DFF':
        values['model_type'] = values['model_type'] or 'Clump'
        profile = str(owner.get('bleeds_dff_profile', '')) if owner else ''
        values['format'] = {'MOBILE': 'LCS Mobile', 'BETA': 'LCS Prototype'}.get(profile, 'RenderWare')
        if profile == 'MOBILE':
            values['platform'] = 'Mobile'
        values['structure'] = ('Clump' if obj == owner else 'Geometry' if obj.type == 'MESH'
                               else 'Skeleton' if obj.type == 'ARMATURE' else 'Frame')
        version = int(owner.get('bleeds_dff_version', 0)) if owner else 0
        if version:
            version = ((((version >> 14) & 0x3FF00) + 0x30000) | ((version >> 16) & 0x3F)) if version & 0xFFFF0000 else version << 8
            values['version'] = '%d.%d.%d.%d' % ((version >> 16) & 15, (version >> 12) & 15, (version >> 8) & 15, version & 255)
    values['exportable'] = isObjectExportable(obj)
    return values


def effectRole(obj):
    game = str(obj.get('blds_2dfx_game', '') or storedObjectValue(obj, 'bleeds_model_game', '')).upper().replace(' ', '')
    return '2DFX' if game in {'III', 'GTAIII', 'GTA3', 'VC', 'GTAVC'} else '2D_EFFECT'
