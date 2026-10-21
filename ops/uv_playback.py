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

import bpy
from bpy.app.handlers import persistent

pendingScenes = set()


def sceneHasNativeUvAnimation(scene):
    for obj in scene.objects:
        for slot in obj.material_slots:
            material = slot.material
            if material is None or material.get("bleeds_uv_source") != "VCS_PS2_WORLD":
                continue
            modes = (material.get("bleeds_uv_mode_u", 0), material.get("bleeds_uv_mode_v", 0))
            if 3 in modes or not any(mode in (1, 2) for mode in modes):
                continue
            tree = material.node_tree
            offset = tree.nodes.get("Leeds UV Offset") if tree is not None else None
            if offset is not None and tree.animation_data is not None and tree.animation_data.drivers:
                return True
    return False


def startNativeUvPlayback(window):

    screen = window.screen
    if not sceneHasNativeUvAnimation(window.scene):
        return False
    viewports = [area for area in screen.areas if area.type == 'VIEW_3D']
    for area in viewports:
        if area.spaces.active.shading.type in {'SOLID', 'WIREFRAME'}:
            area.spaces.active.shading.type = 'MATERIAL'
        area.tag_redraw()
    if screen.is_animation_playing:
        return True
    area = viewports[0] if viewports else next(
        (area for area in screen.areas if area.type != 'FILE_BROWSER'), None)
    if area is None:
        return False
    region = next((region for region in area.regions if region.type == 'WINDOW'), None)
    override = dict(window=window, screen=screen, area=area, region=region)
    if hasattr(bpy.context, 'temp_override'):
        with bpy.context.temp_override(**override):
            result = bpy.ops.screen.animation_play()
    else:

        result = bpy.ops.screen.animation_play(override)
    return 'FINISHED' in result


def finishNativeUvPlaybackRequests():


    for scene_name in tuple(pendingScenes):
        scene = bpy.data.scenes.get(scene_name)
        if scene is None or not sceneHasNativeUvAnimation(scene):
            pendingScenes.discard(scene_name)
            continue
        windows = [window for window in bpy.context.window_manager.windows if window.scene == scene]
        if not windows:
            pendingScenes.discard(scene_name)
            continue
        for window in windows:
            if (any(area.type == 'FILE_BROWSER' for area in window.screen.areas)
                    and not any(area.type == 'VIEW_3D' for area in window.screen.areas)):
                continue
            try:
                if startNativeUvPlayback(window):
                    pendingScenes.discard(scene_name)
            except RuntimeError as exc:
                print("BLeeds UV playback: %s" % exc)
                pendingScenes.discard(scene_name)
    return 0.1 if pendingScenes else None


def requestNativeUvPlayback(context=None):
    if bpy.app.background:
        return False
    if context is None:
        context = bpy.context
    if context is None or not hasattr(context, "scene") or context.scene is None:
        return False
    scene = context.scene
    if not sceneHasNativeUvAnimation(scene):
        return False
    pendingScenes.add(scene.name)
    if not bpy.app.timers.is_registered(finishNativeUvPlaybackRequests):
        bpy.app.timers.register(finishNativeUvPlaybackRequests, first_interval=0.1)
    return True


@persistent
def resumeNativeUvPlaybackAfterLoad(unused):
    pendingScenes.clear()
    for window in bpy.context.window_manager.windows:
        if sceneHasNativeUvAnimation(window.scene):
            pendingScenes.add(window.scene.name)
    if pendingScenes and not bpy.app.background:
        if not bpy.app.timers.is_registered(finishNativeUvPlaybackRequests):
            bpy.app.timers.register(finishNativeUvPlaybackRequests, first_interval=0.1)


def registerNativeUvPlayback():
    if resumeNativeUvPlaybackAfterLoad not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(resumeNativeUvPlaybackAfterLoad)
    requestNativeUvPlayback()


def unregisterNativeUvPlayback():
    pendingScenes.clear()
    if bpy.app.timers.is_registered(finishNativeUvPlaybackRequests):
        bpy.app.timers.unregister(finishNativeUvPlaybackRequests)
    if resumeNativeUvPlaybackAfterLoad in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(resumeNativeUvPlaybackAfterLoad)
