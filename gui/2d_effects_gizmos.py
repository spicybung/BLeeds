# BLeeds - 2D Effects viewport handles
# Author: spicybung

import math
import bpy
from mathutils import Matrix
from importlib import import_module

effects = import_module('.2d_effects', __package__)


def effectParentMatrix(obj):
    # Keep the position handle in the parent's space, including a parent inverse.
    return obj.matrix_world @ obj.matrix_basis.inverted_safe()


def effectHandleMatrix(obj, axis):
    rotation = Matrix.Rotation(math.pi / 2, 4, 'Y') if axis == 'X' else Matrix.Rotation(-math.pi / 2, 4, 'X') if axis == 'Y' else Matrix.Identity(4)
    return obj.matrix_world.normalized() @ rotation


class VIEW3D_GGT_BLeeds_2D_Effects(bpy.types.GizmoGroup):
    bl_idname = 'VIEW3D_GGT_BLeeds_2D_Effects'
    bl_label = 'BLeeds 2D Effects'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        return (getattr(context.scene, 'bleeds_effect_gizmos', True)
                and effects.isEffectObject(context.object)
                and context.object.mode == 'OBJECT')

    def setup(self, context):
        self.position = self.gizmos.new('GIZMO_GT_move_3d')
        self.position.color = (0.9, 0.9, 0.9)
        self.position.color_highlight = (1.0, 1.0, 0.4)
        self.position.alpha = 0.6
        self.position.alpha_highlight = 1.0
        self.position.scale_basis = 0.2
        self.position.use_draw_value = True
        self.handles = []
        for axis, color in (('X', (1.0, 0.35, 0.2)), ('Y', (0.3, 1.0, 0.4)), ('Z', (0.3, 0.6, 1.0))):
            handle = self.gizmos.new('GIZMO_GT_arrow_3d')
            handle.draw_style = 'BOX'
            handle.color = color
            handle.color_highlight = (1.0, 1.0, 0.4)
            handle.alpha = 0.7
            handle.alpha_highlight = 1.0
            handle.use_draw_value = True
            self.handles.append((axis, handle))
        self.refresh(context)

    def refresh(self, context):
        obj = context.object
        self.position.target_set_prop('offset', obj, 'location')
        kind = effects.effectTypeGet(obj)
        properties = ('light_outer_range', 'light_inner_range', 'light_size') if kind == 0 else ('particle_scale',) if kind == 1 else ()
        for index, (axis, handle) in enumerate(self.handles):
            handle.hide = index >= len(properties)
            if not handle.hide:
                handle.target_set_prop('offset', obj, 'bleeds_effect_' + properties[index])

    def draw_prepare(self, context):
        obj = context.object
        self.refresh(context)
        self.position.matrix_basis = effectParentMatrix(obj)
        for axis, handle in self.handles:
            handle.matrix_basis = effectHandleMatrix(obj, axis)
