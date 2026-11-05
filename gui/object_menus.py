# BLeeds - Scripts for working with R* Leeds formats in Blender
# Author: spicybung

from pathlib import PureWindowsPath

import bpy
from ..ops.object_types import describeObject

ROLE_LABELS = {'EMPTY': 'Empty', 'MODEL': 'Model', 'COLLISION': 'Collision', 'LIGHT': 'Light',
               '2DFX': '2DFX', '2D_EFFECT': '2D Effect', 'ARMATURE': 'Armature', 'DONT_EXPORT': "Don't Export"}
ROLE_ICONS = {'EMPTY': 'EMPTY_AXIS', 'MODEL': 'MESH_DATA', 'COLLISION': 'MESH_ICOSPHERE',
              'LIGHT': 'LIGHT', '2DFX': 'LIGHT_POINT', '2D_EFFECT': 'LIGHT_POINT', 'ARMATURE': 'ARMATURE_DATA',
              'DONT_EXPORT': 'HIDE_ON'}


def drawObjectDescription(layout, label, value):
    if value is None or value == '':
        return
    row = layout.row(align=True)
    row.label(text=label)
    row.label(text=str(value))


class OBJECT_PT_BLeeds_Object(bpy.types.Panel):
    bl_idname = 'OBJECT_PT_BLeeds_Object'
    bl_label = 'BLeeds'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'object'
    bl_order = -100

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        obj = context.object
        info = describeObject(obj)
        layout.prop(obj, 'bleeds_object_type', text='Type')
        role = info['role']
        layout.label(text=ROLE_LABELS.get(role, role.replace('_', ' ').title()),
                     icon=ROLE_ICONS.get(role, 'OBJECT_DATA'))
        drawObjectDescription(layout, 'Model Type', info['model_type'])
        drawObjectDescription(layout, 'File Type', info['file_type'])
        drawObjectDescription(layout, 'Game', info['game'])
        drawObjectDescription(layout, 'Platform', info['platform'])
        drawObjectDescription(layout, 'Format', info['format'])
        drawObjectDescription(layout, 'Part Type', info['structure'])
        owner = info['owner']
        if owner is not None and owner != obj:
            drawObjectDescription(layout, 'Model', owner.name)
        if info['source']:
            drawObjectDescription(layout, 'File', PureWindowsPath(info['source']).name)
        if obj.get('blds_2dfx_effect_type') is not None:
            effect = str(obj.get('blds_2dfx_effect_type_name', '2D Effect')).replace('_', ' ').title()
            drawObjectDescription(layout, '2D Effect', effect)
        if info['file_type']:
            layout.prop(context.scene, 'bleeds_show_mdl_attributes', text='File Details')
        if context.scene.bleeds_show_mdl_attributes and info['file_type'] == 'DFF':
            details = layout.column(align=True)
            drawObjectDescription(details, 'RenderWare Version', info['version'])
            if owner is not None:
                drawObjectDescription(details, 'Frames in File', owner.get('bleeds_dff_frame_count'))
                drawObjectDescription(details, 'Meshes in File', owner.get('bleeds_dff_mesh_count'))
                drawObjectDescription(details, 'Bones in File', owner.get('bleeds_dff_bone_count'))
            drawObjectDescription(details, 'Frame', obj.get('bleeds_dff_frame_name'))
            if obj.type == 'MESH':
                drawObjectDescription(details, 'Vertices', len(obj.data.vertices))
                drawObjectDescription(details, 'Faces', len(obj.data.polygons))
                drawObjectDescription(details, 'Materials', len(obj.data.materials))
                drawObjectDescription(details, 'UV Maps', len(obj.data.uv_layers))
                drawObjectDescription(details, 'Skeleton Weights', 'Yes' if any(vertex.groups for vertex in obj.data.vertices) else 'No')
        if not info['exportable']:
            layout.label(text="Excluded from export" if role == 'DONT_EXPORT' else 'Parent is excluded from export',
                         icon='HIDE_ON')
