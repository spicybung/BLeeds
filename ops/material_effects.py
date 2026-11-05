# BLeeds - Leeds material transparency and material effects
# Author: spicybung

import math
import struct


def classifyTextureAlpha(rgba):
    if rgba is None:
        return 'OPAQUE'
    try:
        alphas = rgba[..., 3]
        if alphas.size == 0:
            return 'OPAQUE'
        minimum = int(alphas.min())
        maximum = int(alphas.max())
        if minimum >= 254 or maximum == 0:
            return 'OPAQUE'
        partial = (alphas > 3) & (alphas < 252)
        if partial.any():
            return 'BLEND'
        return 'CLIP'
    except (AttributeError, ValueError, TypeError):
        return 'OPAQUE'


def imageAlphaMode(image):
    if image is None:
        return 'OPAQUE'
    stored = str(image.get('bleeds_alpha_mode', image.get('blds_alpha_mode', '')))
    if stored in ('OPAQUE', 'CLIP', 'BLEND'):
        return stored
    try:
        pixels = image.pixels
        size = len(pixels)
        if size < 4:
            return 'OPAQUE'
        first = float(pixels[3])
        minimum = first
        maximum = first
        intermediate = 0
        for offset in range(3, size, 4):
            alpha = float(pixels[offset])
            if alpha < minimum:
                minimum = alpha
            if alpha > maximum:
                maximum = alpha
            if 0.015 < alpha < 0.985:
                intermediate += 1
                break
        if minimum >= 0.995 or maximum <= 0.001:
            mode = 'OPAQUE'
        elif intermediate:
            mode = 'BLEND'
        else:
            mode = 'CLIP'
        image['bleeds_alpha_mode'] = mode
        return mode
    except (TypeError, ValueError, RuntimeError, AttributeError):
        return 'OPAQUE'


def setMaterialAlpha(material, image, shader=None, texture_node=None, force=False, material_opacity=1.0):
    if material is None:
        return 'OPAQUE'
    mode = imageAlphaMode(image)
    if force:
        mode = 'BLEND'
    if material_opacity < 0.995:
        mode = 'BLEND'
    if shader is None and getattr(material, 'node_tree', None):
        shader = next((node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED'), None)
    if shader is not None:
        alpha_input = shader.inputs.get('Alpha')
        if alpha_input is not None:
            for connection in list(alpha_input.links):
                material.node_tree.links.remove(connection)
            alpha_input.default_value = min(1.0, max(0.0, float(material_opacity)))
            for node in list(material.node_tree.nodes):
                if node.name == 'BLeeds Material Alpha':
                    material.node_tree.nodes.remove(node)
            if mode != 'OPAQUE' and texture_node is not None:
                alpha_output = texture_node.outputs.get('Alpha')
                if alpha_output is not None:
                    if abs(material_opacity - 1.0) < 0.00001:
                        material.node_tree.links.new(alpha_output, alpha_input)
                    else:
                        factor = material.node_tree.nodes.new('ShaderNodeMath')
                        factor.operation = 'MULTIPLY'
                        factor.name = 'BLeeds Material Alpha'
                        factor.inputs[1].default_value = material_opacity
                        material.node_tree.links.new(alpha_output, factor.inputs[0])
                        material.node_tree.links.new(factor.outputs[0], alpha_input)
    if hasattr(material, 'blend_method'):
        material.blend_method = {'OPAQUE': 'OPAQUE', 'CLIP': 'CLIP', 'BLEND': 'BLEND'}[mode]
        if mode == 'CLIP' and hasattr(material, 'alpha_threshold'):
            material.alpha_threshold = 0.5
    elif hasattr(material, 'surface_render_method'):
        material.surface_render_method = 'DITHERED' if mode != 'OPAQUE' else 'BLENDED'
    if hasattr(material, 'shadow_method'):
        material.shadow_method = 'CLIP' if mode == 'CLIP' else 'HASHED' if mode == 'BLEND' else 'OPAQUE'
    if hasattr(material, 'show_transparent_back'):
        material.show_transparent_back = False
    material['bleeds_alpha_mode'] = mode
    material['bleeds_force_transparency'] = bool(force)
    return mode


def readExactTextureName(source, offset):
    offset = int(offset)
    if not 0 < offset < len(source):
        return ''
    end = source.find(b'\x00', offset, min(len(source), offset + 65))
    if end < offset + 1 or end > offset + 63:
        return ''
    raw = source[offset:end]
    if not all(32 <= byte <= 126 for byte in raw):
        return ''
    name = raw.decode('ascii')
    if not any(letter.isalpha() for letter in name) or '/' in name or '\\' in name:
        return ''
    return name


def readRslMatFx(source, offset):
    offset = int(offset)
    if offset <= 0 or offset + 16 > len(source) or offset % 4:
        return None
    effect_type, texture_pointer, data0, data1 = struct.unpack_from('<IIII', source, offset)
    if effect_type not in (2, 4):
        return None
    name = readExactTextureName(source, texture_pointer)
    if not name and texture_pointer + 4 < len(source) and texture_pointer > 0:
        indirect_pointer = struct.unpack_from('<I', source, texture_pointer)[0]
        name = readExactTextureName(source, indirect_pointer)
    if not name:
        return None
    result = {
        'effect_type': effect_type,
        'texture_name': name,
        'source_offset': offset,
        'texture_pointer': texture_pointer,
        'raw0': data0,
        'raw1': data1,
    }
    if effect_type == 2:
        intensity = struct.unpack_from('<f', source, offset + 8)[0]
        if not math.isfinite(intensity) or not 0.0 <= intensity <= 4.0:
            return None
        result['intensity'] = intensity
    else:
        result['blend_src'] = data0
        result['blend_dst'] = data1
    return result


def readRslMatFxStream(stream, pointer, file_length):
    pointer = int(pointer)
    if pointer <= 0 or pointer % 4 or pointer + 16 > file_length:
        return None
    saved = stream.tell()
    try:
        stream.seek(pointer)
        header = stream.read(16)
        if len(header) != 16:
            return None
        effect_type, texture_pointer, data0, data1 = struct.unpack('<IIII', header)
        if effect_type not in (2, 4) or texture_pointer <= 0:
            return None

        def readNameAt(position):
            if position <= 0 or position >= file_length:
                return ''
            stream.seek(position)
            raw = stream.read(min(64, file_length - position))
            return readExactTextureName(b'\x00' * 4 + raw, 4)

        name = readNameAt(texture_pointer)
        if not name and texture_pointer + 4 <= file_length:
            stream.seek(texture_pointer)
            raw = stream.read(4)
            if len(raw) == 4:
                indirect = struct.unpack('<I', raw)[0]
                name = readNameAt(indirect)
        if not name:
            return None
        info = dict(effect_type=effect_type, texture_name=name,
                    source_offset=pointer, texture_pointer=texture_pointer,
                    raw0=data0, raw1=data1)
        if effect_type == 2:
            intensity = struct.unpack('<f', header[8:12])[0]
            if not math.isfinite(intensity) or not 0.0 <= intensity <= 4.0:
                return None
            info['intensity'] = intensity
        else:
            info['blend_src'] = data0
            info['blend_dst'] = data1
        return info
    finally:
        stream.seek(saved)


def exactImage(name):
    if not name:
        return None
    import bpy
    wanted = str(name).casefold()
    matches = []
    for image in bpy.data.images:
        native = str(image.get('bleeds_texture_name', image.get('bleeds_txd_texture_name', image.name)))
        if native.casefold() == wanted or image.name.casefold() == wanted:
            matches.append(image)
    return matches[0] if len(matches) == 1 else None


def removeMaterialFxNodes(material):
    if not getattr(material, 'node_tree', None):
        return
    for node in list(material.node_tree.nodes):
        if node.name.startswith('BLeeds RSL '):
            material.node_tree.nodes.remove(node)


def refreshMaterialUvFx(material):
    from ..leedsLib.lvz_img import syncNativeWorldUvAnimation
    if (material.get('bleeds_uv_game_hint') == 'vcs'
            and (int(material.get('bleeds_uv_animated_nodes', 0)) > 0
                 or int(material.get('bleeds_rslmatfx_type', 0)) in (2, 4))):
        syncNativeWorldUvAnimation(material)


def rebuildMaterialFx(material):
    if material is None or not getattr(material, 'use_nodes', False) or material.node_tree is None:
        return False
    tree = material.node_tree
    nodes, links = tree.nodes, tree.links
    shader = next((node for node in nodes if node.type == 'BSDF_PRINCIPLED'), None)
    if shader is None:
        return False
    current = shader.inputs.get('Base Color')
    if current is None:
        return False
    old_link = next(iter(current.links), None)
    previous_socket = old_link.from_socket if old_link and not old_link.from_node.name.startswith('BLeeds RSL ') else None
    if previous_socket is None:
        diffuse = next((node for node in nodes if node.type == 'TEX_IMAGE' and not node.name.startswith('BLeeds RSL ') and node.image), None)
        previous_socket = diffuse.outputs.get('Color') if diffuse else None
    removeMaterialFxNodes(material)
    for link in list(current.links):
        links.remove(link)
    effect = int(material.get('bleeds_rslmatfx_type', 0))
    if effect not in (2, 4):
        if previous_socket:
            links.new(previous_socket, current)
        refreshMaterialUvFx(material)
        return False
    image_name = str(material.get('bleeds_rslmatfx_texture_name', '') or '')
    image = exactImage(image_name)
    if image is None:
        if previous_socket:
            links.new(previous_socket, current)
        material['bleeds_rslmatfx_missing_texture'] = image_name
        refreshMaterialUvFx(material)
        return False
    material['bleeds_rslmatfx_missing_texture'] = ''
    secondary = nodes.new('ShaderNodeTexImage')
    secondary.name = 'BLeeds RSL Secondary Texture'
    secondary.label = 'Environment' if effect == 2 else 'Second Texture'
    secondary.image = image
    secondary.location = (-440, -340)
    mix = nodes.new('ShaderNodeMixRGB')
    mix.name = 'BLeeds RSL Material Effect'
    mix.location = (-130, -10)
    strength = float(material.get('bleeds_rslmatfx_strength', 1.0))
    mix.inputs[0].default_value = max(0.0, min(1.0, strength))
    mix.blend_type = 'ADD' if effect == 2 else str(material.get('bleeds_rslmatfx_blend', 'MULTIPLY'))
    if previous_socket:
        links.new(previous_socket, mix.inputs[1])
    else:
        mix.inputs[1].default_value = shader.inputs['Base Color'].default_value
    links.new(secondary.outputs['Color'], mix.inputs[2])
    links.new(mix.outputs['Color'], current)
    if effect == 2:
        coordinates = nodes.new('ShaderNodeTexCoord')
        coordinates.name = 'BLeeds RSL Environment Coordinates'
        coordinates.location = (-1040, -460)
        transform = nodes.new('ShaderNodeVectorTransform')
        transform.name = 'BLeeds RSL Environment Camera Space'
        transform.vector_type = 'NORMAL'
        transform.convert_from = 'WORLD'
        transform.convert_to = 'CAMERA'
        transform.location = (-830, -460)
        mapping = nodes.new('ShaderNodeMapping')
        mapping.name = 'BLeeds RSL Environment Mapping'
        mapping.vector_type = 'POINT'
        mapping.location = (-640, -460)
        mapping.inputs['Location'].default_value = (0.5, 0.5, 0.0)
        mapping.inputs['Scale'].default_value = (-0.5, -0.5, 1.0)
        links.new(coordinates.outputs['Normal'], transform.inputs['Vector'])
        links.new(transform.outputs['Vector'], mapping.inputs['Vector'])
        links.new(mapping.outputs['Vector'], secondary.inputs['Vector'])
    else:
        uv_name = str(material.get('bleeds_rslmatfx_uv_map', '') or '')
        if uv_name:
            uv = nodes.new('ShaderNodeUVMap')
            uv.name = 'BLeeds RSL Second UV'
            uv.uv_map = uv_name
            links.new(uv.outputs['UV'], secondary.inputs['Vector'])
    refreshMaterialUvFx(material)
    return True


def updateMaterialEffect(self, context):
    rebuildMaterialFx(self)


def updateEffectTexture(self, context):
    image = getattr(self, 'bleeds_rslmatfx_image', None)
    self['bleeds_rslmatfx_texture_name'] = str(image.get('bleeds_texture_name', image.name)) if image else ''
    rebuildMaterialFx(self)


def getEffect(self):
    return int(self.get('bleeds_rslmatfx_type', 0))


def setEffect(self, value):
    self['bleeds_rslmatfx_type'] = int(value)
    rebuildMaterialFx(self)


def getStrength(self):
    return float(self.get('bleeds_rslmatfx_strength', 1.0))


def setStrength(self, value):
    self['bleeds_rslmatfx_strength'] = float(value)
    rebuildMaterialFx(self)


def getBlend(self):
    return {'MULTIPLY': 0, 'ADD': 1, 'MIX': 2}.get(str(self.get('bleeds_rslmatfx_blend', 'MULTIPLY')), 0)


def setBlend(self, value):
    self['bleeds_rslmatfx_blend'] = {0: 'MULTIPLY', 1: 'ADD', 2: 'MIX'}.get(int(value), 'MULTIPLY')
    rebuildMaterialFx(self)


def getUVMap(self):
    return str(self.get('bleeds_rslmatfx_uv_map', ''))


def setUVMap(self, value):
    self['bleeds_rslmatfx_uv_map'] = str(value)
    rebuildMaterialFx(self)


class BLEEDS_PT_rsl_matfx:
    bl_label = 'Leeds Material Effects'
    bl_idname = 'BLEEDS_PT_rsl_matfx'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'material'

    @classmethod
    def poll(cls, context):
        return getattr(context, 'material', None) is not None

    def draw(self, context):
        material = context.material
        layout = self.layout
        layout.prop(material, 'bleeds_rslmatfx_effect')
        if material.bleeds_rslmatfx_effect != 'NONE':
            if material.get('bleeds_rslmatfx_texture_name', ''):
                layout.label(text='Native texture: ' + str(material['bleeds_rslmatfx_texture_name']))
            layout.prop(material, 'bleeds_rslmatfx_image')
            layout.prop(material, 'bleeds_rslmatfx_strength')
            if material.bleeds_rslmatfx_effect == 'DUAL':
                layout.prop(material, 'bleeds_rslmatfx_blend')
                layout.prop(material, 'bleeds_rslmatfx_uv')
            if material.get('bleeds_rslmatfx_missing_texture', ''):
                layout.label(text='Missing texture: ' + material['bleeds_rslmatfx_missing_texture'], icon='ERROR')


def register():
    import bpy
    from bpy.props import EnumProperty, FloatProperty, PointerProperty, StringProperty
    panel = type('BLEEDS_PT_rsl_matfx_panel', (BLEEDS_PT_rsl_matfx, bpy.types.Panel), {'__module__': __name__})
    bpy.utils.register_class(panel)
    bpy.types.Material.bleeds_rslmatfx_effect = EnumProperty(
        name='Material Effect',
        items=[('NONE', 'None', 'No material effect', 'NONE', 0),
               ('ENV', 'Environment Map', 'Camera-space environment map', 'SHADING_RENDERED', 2),
               ('DUAL', 'Dual Texture', 'Blend a second texture', 'TEXTURE', 4)],
        get=getEffect, set=setEffect)
    bpy.types.Material.bleeds_rslmatfx_image = PointerProperty(
        name='Effect Texture', type=bpy.types.Image, update=updateEffectTexture)
    bpy.types.Material.bleeds_rslmatfx_strength = FloatProperty(
        name='Strength', min=0.0, max=1.0, get=getStrength, set=setStrength)
    bpy.types.Material.bleeds_rslmatfx_blend = EnumProperty(
        name='Blend', items=[('MULTIPLY', 'Multiply', 'Multiply colors', 'NONE', 0),
                             ('ADD', 'Add', 'Add colors', 'NONE', 1),
                             ('MIX', 'Mix', 'Mix colors', 'NONE', 2)], get=getBlend, set=setBlend)
    bpy.types.Material.bleeds_rslmatfx_uv = StringProperty(name='Second UV Map', get=getUVMap, set=setUVMap)
    register.panel = panel


def unregister():
    import bpy
    for prop in ('bleeds_rslmatfx_effect', 'bleeds_rslmatfx_image',
                 'bleeds_rslmatfx_strength', 'bleeds_rslmatfx_blend', 'bleeds_rslmatfx_uv'):
        if hasattr(bpy.types.Material, prop):
            delattr(bpy.types.Material, prop)
    panel = getattr(register, 'panel', None)
    if panel is not None:
        bpy.utils.unregister_class(panel)
        register.panel = None
