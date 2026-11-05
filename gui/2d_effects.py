# BLeeds - 2D Effects
# Author: spicybung

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, StringProperty
from ..ops.object_types import objectRole, effectRole

EFFECT_TYPES = (('0', 'Light', ''), ('1', 'Particle', ''), ('2', 'Attractor', ''), ('3', 'Pedestrian', ''))
EFFECT_NAMES = ('LIGHT', 'PARTICLE', 'ATTRACTOR', 'PED_BEHAVIOUR')
FIELDS = {
    0: (('light_distance', 'Draw Distance', 'FLOAT'), ('light_outer_range', 'Outer Range', 'FLOAT'),
        ('light_size', 'Size', 'FLOAT'), ('light_inner_range', 'Inner Range', 'FLOAT'),
        ('light_flash', 'Flash', 'BYTE'), ('light_wet', 'Wet Weather', 'BYTE'),
        ('light_flare', 'Flare', 'BYTE'), ('light_shadow_intensity', 'Shadow Intensity', 'BYTE')),
    1: (('particle_subtype', 'Particle Type', 'INT'), ('particle_scale', 'Scale', 'FLOAT')),
    2: (('attractor_subtype', 'Attractor Type', 'BYTE'), ('attractor_probability', 'Probability', 'BYTE')),
    3: (('ped_subtype', 'Pedestrian Type', 'BYTE'),),
}
VECTORS = {'direction': ('Direction', ('direction_x', 'direction_y', 'direction_z')),
           'attractor_direction': ('Direction', ('attractor_direction_x', 'attractor_direction_y', 'attractor_direction_z')),
           'ped_direction': ('Direction', ('ped_direction_x', 'ped_direction_y', 'ped_direction_z')),
           'ped_rotation': ('Rotation', ('ped_rotation_x', 'ped_rotation_y', 'ped_rotation_z'))}
PROPERTY_NAMES = []


def isEffectObject(obj):
    return obj is not None and objectRole(obj) in {'2D_EFFECT', '2DFX'}


def syncEffectLight(obj):
    if int(obj.get('blds_2dfx_effect_type', 0)) != 0:
        return
    light = obj if obj.type == 'LIGHT' else next((child for child in obj.children if child.type == 'LIGHT' and child.get('bleeds_effect_preview_light')), None)
    if light is None:
        return
    data = light.data
    data.type = 'POINT'
    data.color = tuple(float(obj.get('blds_2dfx_color_' + channel, 255)) / 255.0 for channel in 'rgb')
    data.shadow_soft_size = max(0.0, float(obj.get('blds_2dfx_light_size', 0.1)))
    distance = float(obj.get('blds_2dfx_light_distance', 0.0))
    if hasattr(data, 'use_custom_distance'):
        data.use_custom_distance = distance > 0.0
        data.cutoff_distance = max(0.001, distance)


def effectTypeGet(obj):
    return int(obj.get('blds_2dfx_effect_type', 0))


def effectTypeSet(obj, value):
    obj['blds_2dfx_effect_type'] = int(value)
    obj['blds_2dfx_effect_type_name'] = EFFECT_NAMES[int(value)]
    obj['blds_kind'] = 'LEEDS_2D_EFFECT'
    obj['blds_entity_type'] = effectRole(obj)
    syncEffectLight(obj)


def scalarProperty(key, label, kind):
    # Write to the stored effect fields so imported values and edits stay together.
    def get(obj):
        value = obj.get('blds_2dfx_' + key, 1.0 if key == 'particle_scale' else 0)
        return int(value) if kind in {'BYTE', 'INT'} else float(value)
    def set(obj, value):
        obj['blds_2dfx_' + key] = value
        syncEffectLight(obj)
    if kind == 'INT':
        return IntProperty(name=label, get=get, set=set)
    if kind == 'BYTE':
        return IntProperty(name=label, min=0, max=255, get=get, set=set)
    return FloatProperty(name=label, min=0.0, get=get, set=set)


def vectorProperty(label, keys):
    def get(obj):
        return tuple(float(obj.get('blds_2dfx_' + key, 0.0)) for key in keys)
    def set(obj, values):
        for key, value in zip(keys, values):
            obj['blds_2dfx_' + key] = float(value)
    return FloatVectorProperty(name=label, size=3, get=get, set=set)


def colorGet(obj):
    return tuple(float(obj.get('blds_2dfx_color_' + channel, 255)) / 255.0 for channel in 'rgba')


def colorSet(obj, values):
    for channel, value in zip('rgba', values):
        obj['blds_2dfx_color_' + channel] = max(0, min(255, round(value * 255.0)))
    syncEffectLight(obj)


def registerEffectProperties():
    bpy.types.Scene.bleeds_effect_gizmos = BoolProperty(name='Effect Gizmos', default=True)
    properties = {'bleeds_effect_type': EnumProperty(name='Effect', items=EFFECT_TYPES, get=effectTypeGet, set=effectTypeSet),
                  'bleeds_effect_color': FloatVectorProperty(name='Color', size=4, subtype='COLOR', min=0.0, max=1.0, get=colorGet, set=colorSet),
                  'bleeds_effect_flags': scalarProperty('light_flags', 'Flags', 'BYTE')}
    for fields in FIELDS.values():
        for key, label, kind in fields:
            properties['bleeds_effect_' + key] = scalarProperty(key, label, kind)
    for key, (label, keys) in VECTORS.items():
        properties['bleeds_effect_' + key] = vectorProperty(label, keys)
    for name, prop in properties.items():
        setattr(bpy.types.Object, name, prop)
        if name not in PROPERTY_NAMES:
            PROPERTY_NAMES.append(name)


def unregisterEffectProperties():
    if hasattr(bpy.types.Scene, 'bleeds_effect_gizmos'):
        del bpy.types.Scene.bleeds_effect_gizmos
    for name in PROPERTY_NAMES:
        if hasattr(bpy.types.Object, name):
            delattr(bpy.types.Object, name)
    PROPERTY_NAMES.clear()


class OBJECT_OT_BLeeds_EffectPointLight(bpy.types.Operator):
    bl_idname = 'object.bleeds_effect_point_light'
    bl_label = 'Use Point Light'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return isEffectObject(context.object) and context.object.type in {'EMPTY', 'LIGHT'}

    def execute(self, context):
        obj = context.object
        if obj.type == 'EMPTY':
            # Keep the old transform as a frame, including any animation or constraints.
            name = obj.name
            light = bpy.data.objects.new(name + ' Light', bpy.data.lights.new(name + ' Light', 'POINT'))
            for collection in obj.users_collection or (context.scene.collection,):
                collection.objects.link(light)
            light.parent = obj
            for key, value in list(obj.items()):
                if key.startswith('blds_2dfx_') or key in {'blds_kind', 'blds_entity_type'}:
                    light[key] = value
                    del obj[key]
            light.bleeds_object_type = '2D_EFFECT'
            obj.bleeds_object_type = 'EMPTY'
            obj['blds_kind'] = 'FRAME'
            obj['blds_entity_type'] = 'OBJECT'
            obj.name = name + ' Frame'
            light.name = name
            obj.select_set(False)
            light.select_set(True)
            context.view_layer.objects.active = light
            obj = light
        obj.bleeds_effect_type = '0'
        syncEffectLight(obj)
        return {'FINISHED'}


class OBJECT_PT_BLeeds_2D_Effects(bpy.types.Panel):
    bl_idname = 'OBJECT_PT_BLeeds_2D_Effects'
    bl_label = '2D Effects'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_parent_id = 'OBJECT_PT_BLeeds_Object'
    bl_context = 'object'

    @classmethod
    def poll(cls, context):
        return isEffectObject(getattr(context, 'object', None))

    def draw(self, context):
        layout = self.layout
        obj = context.object
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(context.scene, 'bleeds_effect_gizmos')
        layout.prop(obj, 'bleeds_effect_type')
        kind = effectTypeGet(obj)
        layout.prop(obj, 'location', text='Position')
        layout.prop(obj, 'bleeds_effect_color')
        for key, label, field_type in FIELDS.get(kind, ()):
            layout.prop(obj, 'bleeds_effect_' + key)
        if kind in (1, 2, 3):
            key = {1: 'direction', 2: 'attractor_direction', 3: 'ped_direction'}[kind]
            layout.prop(obj, 'bleeds_effect_' + key)
        if kind == 3:
            layout.prop(obj, 'bleeds_effect_ped_rotation')
        if kind == 0:
            layout.prop(obj, 'bleeds_effect_flags')
            if obj.type == 'EMPTY':
                layout.operator('object.bleeds_effect_point_light', icon='LIGHT_POINT')
            elif obj.type == 'LIGHT':
                layout.prop(obj.data, 'energy', text='Preview Brightness')
        if context.scene.bleeds_show_mdl_attributes:
            for key, label in (('effect_type', 'Type Number'), ('global_index', 'Table Index'), ('game_model_id', 'Game Model'), ('source_path', 'Source File')):
                value = obj.get('blds_2dfx_' + key)
                if value is not None:
                    row = layout.row()
                    row.label(text=label)
                    row.label(text=str(value))


class DATA_PT_BLeeds_2D_Effects_Light(bpy.types.Panel):
    bl_idname = 'DATA_PT_BLeeds_2D_Effects_Light'
    bl_label = 'BLeeds - 2D Effects'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'data'

    @classmethod
    def poll(cls, context):
        return isEffectObject(context.object) and context.object.type == 'LIGHT'

    def draw(self, context):
        OBJECT_PT_BLeeds_2D_Effects.draw(self, context)
