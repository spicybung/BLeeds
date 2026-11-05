# BLeeds - Scripts for working with R* Leeds formats in Blender
# Author: spicybung

import json
import math

import bpy
from bpy.props import BoolProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup, UIList
from mathutils import Matrix

from ..ops.anim_importer import findSelectedArmature, iterActionCurves


def animationViewerArmature(context):
    chosen = context.scene.bleeds_animation_viewer.armature
    if chosen is not None and chosen.type == 'ARMATURE':
        return chosen
    return findSelectedArmature(context)


def animationArmaturePoll(self, obj):
    return obj.type == 'ARMATURE'


def animationSlotMatchesRig(action, rig, slot=None):
    paths = {bone.path_from_id() for bone in rig.pose.bones}
    for curve in iterActionCurves(action, slot):
        path = curve.data_path
        if path.startswith('pose.bones[') and path.rsplit('.', 1)[0] in paths:
            return True
    return False


def animationActionSlot(action, rig):
    # Newer Blender actions can have more than one target. Pick the slot for this rig.
    if rig is None or not getattr(action, 'is_action_layered', False):
        return None
    for slot in action.slots:
        if slot.target_id_type == 'OBJECT' and animationSlotMatchesRig(action, rig, slot):
            return slot
    return None


def animationActionMatchesRig(action, rig):
    if rig is None:
        return False
    if getattr(action, 'is_action_layered', False):
        return animationActionSlot(action, rig) is not None
    return animationSlotMatchesRig(action, rig)


def animationViewerSave(context, rig):
    # Save this once, so changing clips does not overwrite the pose we need to restore.
    state = context.scene.bleeds_animation_viewer
    if state.preview_rig is not None and state.preview_rig != rig:
        animationViewerRestore(context)
    if state.preview_rig is not None:
        return
    data = rig.animation_data_create()
    if data.use_tweak_mode:
        raise ValueError('Leave NLA Tweak Mode before previewing an action')
    state.previous_action = data.action
    if data.action is not None:
        state.previous_slot = int(getattr(data, 'action_slot_handle', 0))
    state.previous_settings = json.dumps({
        'use_nla': data.use_nla,
        'blend_type': data.action_blend_type,
        'influence': data.action_influence,
        'extrapolation': data.action_extrapolation,
        'preview_range': context.scene.use_preview_range,
        'start': context.scene.frame_preview_start,
        'end': context.scene.frame_preview_end,
        'frame': context.scene.frame_current,
        'subframe': context.scene.frame_subframe,
        'fps': context.scene.render.fps,
        'fps_base': context.scene.render.fps_base,
    })
    state.previous_pose = json.dumps({
        bone.name: {
            'location': list(bone.location),
            'rotation_mode': bone.rotation_mode,
            'quaternion': list(bone.rotation_quaternion),
            'euler': list(bone.rotation_euler),
            'axis_angle': list(bone.rotation_axis_angle),
            'scale': list(bone.scale),
        } for bone in rig.pose.bones
    })
    state.preview_rig = rig


def animationViewerResetPose(rig):
    for bone in rig.pose.bones:
        bone.matrix_basis = Matrix.Identity(4)


def animationViewerRange(scene, start, end):
    scene.frame_preview_end = max(scene.frame_preview_start, end)
    scene.frame_preview_start = start
    scene.frame_preview_end = max(start, end)


def animationViewerRestore(context, scene=None):
    # Put the rig and timeline back how they were before the preview.
    scene = context.scene if scene is None else scene
    state = scene.bleeds_animation_viewer
    rig = state.preview_rig
    if rig is None:
        return
    settings = json.loads(state.previous_settings)
    poses = json.loads(state.previous_pose)
    data = rig.animation_data_create()
    if data.use_tweak_mode:
        raise ValueError('Leave NLA Tweak Mode before finishing the preview')
    data.action = state.previous_action
    if state.previous_action is not None and hasattr(data, 'action_slot_handle'):
        data.action_slot_handle = state.previous_slot
    data.use_nla = settings['use_nla']
    data.action_blend_type = settings['blend_type']
    data.action_influence = settings['influence']
    data.action_extrapolation = settings['extrapolation']
    for bone in rig.pose.bones:
        values = poses.get(bone.name)
        if values is None:
            continue
        bone.location = values['location']
        bone.rotation_mode = values['rotation_mode']
        bone.rotation_quaternion = values['quaternion']
        bone.rotation_euler = values['euler']
        bone.rotation_axis_angle = values['axis_angle']
        bone.scale = values['scale']
    scene.use_preview_range = settings['preview_range']
    animationViewerRange(scene, settings['start'], settings['end'])
    scene.render.fps = settings['fps']
    scene.render.fps_base = settings['fps_base']
    scene.frame_set(settings['frame'], subframe=settings['subframe'])
    state.preview_rig = None
    state.previous_action = None
    state.previous_settings = ''
    state.previous_pose = ''


class BLEEDS_PG_animation_viewer(PropertyGroup):
    armature: PointerProperty(name='Armature', type=bpy.types.Object, poll=animationArmaturePoll)
    compatible_only: BoolProperty(name='Matching Bones Only', default=True)
    search: StringProperty(name='Search Animations', default='')
    action_index: IntProperty(default=0, min=0)
    preview_rig: PointerProperty(type=bpy.types.Object, options={'HIDDEN'})
    previous_action: PointerProperty(type=bpy.types.Action, options={'HIDDEN'})
    previous_slot: IntProperty(default=0, options={'HIDDEN'})
    previous_settings: StringProperty(options={'HIDDEN'})
    previous_pose: StringProperty(options={'HIDDEN'})


class BLEEDS_UL_animation_actions(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index):
        rig = animationViewerArmature(context)
        active = rig.animation_data.action if rig is not None and rig.animation_data else None
        row = layout.row(align=True)
        row.enabled = rig is not None
        button = row.operator('bleeds.preview_animation', text=item.name,
                              icon='PLAY' if item == active else 'ACTION', emboss=False)
        button.action_name = item.name
        row.prop(item, 'use_fake_user', text='', emboss=False)

    def filter_items(self, context, data, property_name):
        actions = getattr(data, property_name)
        state = context.scene.bleeds_animation_viewer
        rig = animationViewerArmature(context)
        queries = [value.strip().casefold() for value in (state.search, self.filter_name) if value.strip()]
        flags = []
        for action in actions:
            visible = all(query in action.name.casefold() for query in queries)
            if state.compatible_only and rig is not None:
                visible = visible and animationActionMatchesRig(action, rig)
            flags.append(self.bitflag_filter_item if visible else 0)
        order = bpy.types.UI_UL_list.sort_items_by_name(actions, 'name')
        return flags, order


class BLEEDS_OT_preview_animation(Operator):
    bl_idname = 'bleeds.preview_animation'
    bl_label = 'Preview Animation'
    bl_description = 'Preview this action on the armature, starting at its first frame'
    bl_options = {'REGISTER', 'UNDO'}

    action_name: StringProperty()

    def execute(self, context):
        rig = animationViewerArmature(context)
        action = bpy.data.actions.get(self.action_name)
        if rig is None or action is None:
            self.report({'ERROR'}, 'Select an armature and an existing action')
            return {'CANCELLED'}
        if not animationActionMatchesRig(action, rig):
            self.report({'ERROR'}, 'This action has no bone channels matching the selected armature')
            return {'CANCELLED'}
        try:
            animationViewerSave(context, rig)
            data = rig.animation_data_create()
            data.action = None
            data.use_nla = False
            data.action_blend_type = 'REPLACE'
            data.action_influence = 1.0
            animationViewerResetPose(rig)
            action.use_fake_user = True
            data.action = action
            if getattr(action, 'is_action_layered', False):
                slot = animationActionSlot(action, rig)
                if slot is not None:
                    data.action_slot = slot
            first, last = action.frame_range
            scene = context.scene
            fps = float(action.get('bleeds_animation_fps', action.get('bleeds_anim_fps', 0)))
            if math.isfinite(fps) and fps >= 1.0:
                scene.render.fps = max(1, round(fps))
                scene.render.fps_base = scene.render.fps / fps
            scene.use_preview_range = True
            animationViewerRange(scene, math.floor(first), math.ceil(last))
            scene.frame_set(math.floor(first), subframe=first - math.floor(first))
            context.view_layer.update()
        except (ValueError, TypeError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class BLEEDS_OT_animation_rest_pose(Operator):
    bl_idname = 'bleeds.animation_rest_pose'
    bl_label = 'Rest Pose'
    bl_description = 'Temporarily detach the action and reset pose channels'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        rig = animationViewerArmature(context)
        if rig is None:
            self.report({'ERROR'}, 'Select an armature')
            return {'CANCELLED'}
        try:
            animationViewerSave(context, rig)
            rig.animation_data.action = None
            rig.animation_data.use_nla = False
            animationViewerResetPose(rig)
            context.view_layer.update()
        except (ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class BLEEDS_OT_animation_finish_preview(Operator):
    bl_idname = 'bleeds.animation_finish_preview'
    bl_label = 'Finish Preview'
    bl_description = 'Restore the action, NLA settings, pose and timeline from before the preview'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            if context.screen and context.screen.is_animation_playing:
                bpy.ops.screen.animation_cancel(restore_frame=False)
            animationViewerRestore(context)
        except (ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


class BLEEDS_OT_animation_keyframe(Operator):
    bl_idname = 'bleeds.animation_keyframe'
    bl_label = 'Jump to Keyframe'
    bl_description = 'Jump to the previous or next key in the previewed armature action'

    next: BoolProperty(default=True)

    def execute(self, context):
        rig = animationViewerArmature(context)
        action = rig.animation_data.action if rig is not None and rig.animation_data else None
        if action is None:
            self.report({'WARNING'}, 'Preview an animation first')
            return {'CANCELLED'}
        slot = animationActionSlot(action, rig)
        frames = sorted({float(point.co[0]) for curve in iterActionCurves(action, slot)
                         for point in curve.keyframe_points})
        current = context.scene.frame_current + context.scene.frame_subframe
        candidates = [frame for frame in frames if (frame > current + 0.00001 if self.next
                                                     else frame < current - 0.00001)]
        if candidates:
            frame = candidates[0] if self.next else candidates[-1]
            context.scene.frame_set(math.floor(frame), subframe=frame - math.floor(frame))
        return {'FINISHED'}


class BLEEDS_OT_animation_playback(Operator):
    bl_idname = 'bleeds.animation_playback'
    bl_label = 'Play / Pause'
    bl_description = 'Play or pause the animation within the preview frame range'

    def execute(self, context):
        if context.screen is None:
            self.report({'ERROR'}, 'Animation playback needs a Blender window')
            return {'CANCELLED'}
        if context.screen.is_animation_playing:
            bpy.ops.screen.animation_cancel(restore_frame=False)
        else:
            bpy.ops.screen.animation_play()
        return {'FINISHED'}


class VIEW3D_PT_bleeds_animation_viewer(Panel):
    bl_label = 'Animation Viewer'
    bl_idname = 'VIEW3D_PT_bleeds_animation_viewer'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'BLeeds'

    def draw(self, context):
        layout = self.layout
        state = context.scene.bleeds_animation_viewer
        rig = animationViewerArmature(context)
        row = layout.row(align=True)
        row.operator('import_scene.bleeds_manhunt_ifp', text='Import IFP', icon='IMPORT')
        row.operator('import_scene.leeds_anim', text='Import ANIM', icon='IMPORT')
        layout.prop(state, 'armature')
        if rig is None:
            layout.label(text='Select a rig, mesh or model root.', icon='INFO')
        else:
            layout.label(text=rig.name, icon='ARMATURE_DATA')
        layout.prop(state, 'search', text='', icon='VIEWZOOM')
        layout.prop(state, 'compatible_only')
        layout.template_list('BLEEDS_UL_animation_actions', '', bpy.data, 'actions',
                             state, 'action_index', rows=6)
        scene = context.scene
        active = rig.animation_data.action if rig is not None and rig.animation_data else None
        if active is not None:
            layout.label(text=active.name, icon='ACTION')
        row = layout.row(align=True)
        row.operator('screen.frame_jump', text='', icon='REW').end = False
        row.operator('bleeds.animation_keyframe', text='', icon='PREV_KEYFRAME').next = False
        row.operator('bleeds.animation_playback', text='', icon=(
            'PAUSE' if context.screen and context.screen.is_animation_playing else 'PLAY'))
        row.operator('bleeds.animation_keyframe', text='', icon='NEXT_KEYFRAME').next = True
        row.operator('screen.frame_jump', text='', icon='FF').end = True
        layout.prop(scene, 'frame_current', text='Frame')
        row = layout.row(align=True)
        row.prop(scene, 'frame_preview_start', text='Start')
        row.prop(scene, 'frame_preview_end', text='End')
        layout.prop(scene, 'use_preview_range', text='Loop Preview Range')
        row = layout.row(align=True)
        row.prop(scene.render, 'fps', text='FPS')
        row.prop(scene.render, 'fps_base', text='Base')
        row = layout.row(align=True)
        row.enabled = rig is not None
        row.operator('bleeds.animation_rest_pose', icon='ARMATURE_DATA')
        if state.preview_rig is not None:
            layout.operator('bleeds.animation_finish_preview', icon='LOOP_BACK')
        layout.operator('export_scene.leeds_anim', text='Export ANIM', icon='EXPORT')
