# BLeeds - World texture ownership
# Author: spicybung

import struct
import hashlib
from array import array
from ..leedsLib import lvz_img as LVZ


def ownerResourceRows(data, base, end, table, count, area=False):
    if not (0 <= base < end <= len(data) and base <= table and 0 < count <= 4096 and table + count * 8 <= end):
        return []
    entries = []
    for index in range(count):
        row = table + index * 8
        resource = struct.unpack_from('<h' if area else '<i', data, row)[0]
        pointer = struct.unpack_from('<I', data, row + 4)[0]
        start = base + pointer - (0 if area else 0x20)
        if resource >= 0 and pointer >= 0x20 and base <= start < end and start % 4 == 0:
            entries.append((resource, start))
    # Every allocation bounds the previous one, including models and other non-textures.
    starts = sorted({start for resource, start in entries})
    boundaries = dict(zip(starts, starts[1:] + [end]))
    return [(resource, start, boundaries[start]) for resource, start in entries]


def worldTextureBlob(data, start, end, base, area, game_hint):
    lcs_header = str(game_hint).casefold() == 'lcs' and data[start:start + 4] != b'\xcc' * 4
    header_size = 8 if lcs_header else 16
    if not (0 <= base <= start and start + header_size <= end <= len(data)):
        return None
    if lcs_header:
        pointer, raster_flags = struct.unpack_from('<II', data, start)
        width_half, format_flags = 0, 0
        if pointer == 0:
            return None
    else:
        magic, width_half, format_flags, pointer, raster_flags = struct.unpack_from('<IHHII', data, start)
        if magic != 0xCCCCCCCC or format_flags & 0xFF not in (0x25, 0x45) or format_flags & 0xC000 != 0xC000:
            return None
    log_width = raster_flags & 0x3F
    log_height = (raster_flags >> 6) & 0x3F
    depth = (raster_flags >> 12) & 0x3F
    mipmaps = (raster_flags >> 20) & 0x0F
    if not (1 <= log_width <= 11 and 1 <= log_height <= 11 and depth in (4, 8, 32) and mipmaps <= 8):
        return None
    width, height = 1 << log_width, 1 << log_height
    if not lcs_header and depth == 4 and width_half and width not in (width_half, width_half * 2):
        return None
    payload_size = 0
    for level in range(max(1, mipmaps)):
        payload_size += (max(1, width >> level) * max(1, height >> level) * depth + 7) // 8
    palette_size = 64 if depth == 4 else 1024 if depth == 8 else 0
    payload_size += palette_size
    # Sector pointers still include the WRLD header that is absent from the IMG.
    if pointer:
        if not area and pointer < 0x20:
            return None
        raster = base + pointer - (0 if area else 0x20)
    else:
        raster = start + header_size
    minimum_raster = base if lcs_header else start + header_size
    if raster < minimum_raster or raster + payload_size > end or raster % 4:
        return None
    # The common decoder expects the raster immediately after a 16-byte header.
    header = struct.pack('<IHHII', 0xCCCCCCCC, width_half, format_flags, 16, raster_flags)
    return header + data[raster:raster + payload_size], raster, header_size


def worldLegacyAreaTextureBlob(data, start, end):
    if not (0 <= start < end <= len(data)) or not 64 < end - start <= 32 * 1024 * 1024:
        return None
    index_bytes = end - start - 64
    pixel_count = index_bytes * 2
    dimensions = (16, 32, 64, 128, 256, 512, 1024)
    matches = [(width, pixel_count // width) for width in dimensions
               if pixel_count % width == 0 and pixel_count // width in dimensions]
    if not matches:
        return None
    width, height = min(matches, key=lambda size: abs(size[0] - size[1]))
    raster = data[start:start + min(index_bytes, 4096)]
    if all(value in (0x00, 0xAA, 0xCC, 0xFF) for value in raster) and len(set(raster)) <= 1:
        return None
    palette = struct.unpack_from('<16I', data, end - 64)
    meaningful = sum(value not in (0x00000000, 0xAAAAAAAA, 0xCCCCCCCC, 0xFFFFFFFF) for value in palette)
    varied = sum(value != palette[0] for value in palette)
    if meaningful < 2 or varied < 2:
        return None
    # These AREA rows contain just the indexed image and its 16-colour palette.
    raster_flags = ((width.bit_length() - 1) | ((height.bit_length() - 1) << 6)
                    | (4 << 12) | (1 << 20) | (1 << 24))
    header = struct.pack('<IHHII', 0xCCCCCCCC, width // 2, 0xC045, 16, raster_flags)
    return header + data[start:end], start, 0


def decodeWorldOwner(data, rows, stem, use_swizzle, game_hint, decode_pixels, base=0, area=False, force_alpha=False):
    normalized = bytearray()
    textures = []
    locations = {}
    for resource, start, end in rows:
        texture = worldTextureBlob(data, start, end, base, area, game_hint)
        if texture is None and area and str(game_hint).casefold() == 'lcs':
            texture = worldLegacyAreaTextureBlob(data, start, end)
        if texture is None:
            continue
        blob, raster, header_size = texture
        normalized_start = len(normalized)
        normalized.extend(blob)
        textures.append(dict(index=resource, res_id=resource, kind='TEX',
                             res_addr=normalized_start, res_end=len(normalized)))
        locations[resource] = (start, end, raster, header_size)
    parser = LVZ.read_lvz(bytes(normalized), stem, use_swizzle, False,
                          force_texture_alpha=bool(force_alpha))
    parser.master_game_hint = game_hint
    parser.decode_textures(textures, decode_pixels=decode_pixels)
    for resource, material in parser.material_by_res_index.items():
        material['blds_missing_texture_image'] = not any(node.type == 'TEX_IMAGE' and node.image is not None for node in material.node_tree.nodes) if material.node_tree else True
        targets = [material]
        if material.node_tree:
            targets.extend(node.image for node in material.node_tree.nodes if node.type == 'TEX_IMAGE' and node.image)
        start, end, raster, header_size = locations[resource]
        for target in targets:
            target['blds_texture_stored_in_img'] = True
            target['blds_kind'] = 'IMG_TEX'
            target['blds_img_texture_owner_offset'] = int(base)
            target['blds_img_texture_header_offset'] = int(start)
            target['blds_img_texture_raster_offset'] = int(raster)
            target['blds_img_texture_allocation_end'] = int(end)
            target['blds_lvz_ref_addr'] = int(start)
            target['blds_lvz_texture_blob_len'] = int(end - start)
            target['blds_lvz_texture_header_len'] = int(header_size)
            target['blds_img_texture_legacy_raw'] = header_size == 0
    return parser.material_by_res_index


def importWorldTextureOwners(lvz, img, sectors, decode_pixels=True):
    data = img.img_bytes
    result = {'sector': {}, 'area': {}, 'cell': {}, 'sector_cells': {}, 'shared': {}, 'owner': {}, 'extra': {}}
    for sector in sectors:
        base = int(sector['cont'])
        end = min(len(data), int(sector.get('end', len(data))))
        if base < 0 or base + 8 > end:
            continue
        pointer, count = struct.unpack_from('<IH', data, base)
        rows = ownerResourceRows(data, base, end, base + pointer - 0x20, count)
        materials = decodeWorldOwner(data, rows, lvz.stem + '_sector%d_' % sector['sector_index'], lvz.use_swizzle, lvz.master_game_hint, decode_pixels, base=base, force_alpha=lvz.force_texture_alpha)
        result['sector'][int(sector['sector_index'])] = materials
        result['owner'][base] = materials
        result['sector_cells'][int(sector['sector_index'])] = (int(sector['sector_x']) // 3, int(sector['sector_y']) // 3)
    for area in img.find_area_info_records_from_lvz():
        rows = ownerResourceRows(data, int(area['file_offset']), min(len(data), int(area['data_end'])), int(area['resource_table_off']), int(area['num_resources']), True)
        materials = decodeWorldOwner(data, rows, lvz.stem + '_area%d_' % area['area_index'], lvz.use_swizzle, lvz.master_game_hint, decode_pixels, base=int(area['file_offset']), area=True, force_alpha=lvz.force_texture_alpha)
        result['area'][int(area['area_index'])] = materials
        result['owner'][int(area['file_offset'])] = materials
        result['cell'].setdefault((int(area['cell_x']), int(area['cell_y'])), []).append(materials)
    by_resource = {}
    for group in ('sector', 'area'):
        for materials in result[group].values():
            for resource, material in materials.items():
                by_resource.setdefault(resource, []).append(material)
    for resource, materials in by_resource.items():
        if len(materials) > 1 and worldMaterialsMatch(materials):
            result['shared'][resource] = materials[0]
    return result


def worldObjectTextureOwner(obj):
    for field in ('blds_img_texture_owner', 'blds_img_area_cont', 'blds_img_nested_cont'):
        value = obj.get(field)
        if value is not None and int(value) >= 0:
            return int(value)
    return None


def importWorldExtraTextures(lvz, img, owners, records, extra_records, decode_pixels=True):
    owner_maps = owners.setdefault('owner', {})
    extra_maps = owners.setdefault('extra', {})
    needed = {worldObjectTextureOwner(record['object']) for record in records}
    needed.discard(None)
    needed.difference_update(owner_maps)
    if not needed:
        return 0
    descriptors = {int(record['cont']): record for record in extra_records if int(record.get('cont', -1)) in needed}
    if needed.difference(descriptors):
        for record in img.find_parent_container_records_from_lvz() + img.find_nested_container_records_from_lvz():
            base = int(record.get('cont', -1))
            if base in needed and base not in descriptors:
                descriptors[base] = record
    data = img.img_bytes
    added = 0
    for base in sorted(needed):
        record = descriptors.get(base)
        if record is None:
            continue
        end = min(len(data), int(record.get('end', len(data))))
        if base < 0 or base + 8 > end:
            continue
        pointer, count = struct.unpack_from('<IH', data, base)
        rows = ownerResourceRows(data, base, end, base + pointer - 0x20, count)
        materials = decodeWorldOwner(data, rows, lvz.stem + '_owner%x_' % base,
                                     lvz.use_swizzle, lvz.master_game_hint, decode_pixels, base=base,
                                     force_alpha=lvz.force_texture_alpha)
        owner_maps[base] = materials
        extra_maps[base] = materials
        added += len(materials)
        # A newly found local image can invalidate an otherwise identical set of copies.
        shared = owners.get('shared', {})
        for resource, material in materials.items():
            if resource in shared and not worldMaterialsMatch([shared[resource], material]):
                shared.pop(resource)
    return added


def worldMaterialsMatch(materials):
    signature = None
    for material in materials:
        if material.get('blds_missing_texture_image') or not material.node_tree:
            return False
        images = [node.image for node in material.node_tree.nodes if node.type == 'TEX_IMAGE' and node.image]
        if len(images) != 1:
            return False
        image = images[0]
        pixels = array('f', [0.0]) * len(image.pixels)
        image.pixels.foreach_get(pixels)
        current = (
            tuple(image.size),
            hashlib.sha256(pixels.tobytes()).digest(),
            int(image.get('bleeds_texture_native_format_flags',
                          image.get('blds_lvz_texture_flags',
                                    material.get('blds_lvz_texture_flags', 0)))),
            str(image.get('bleeds_uv_game_hint', material.get('bleeds_uv_game_hint', ''))),
            int(material.get('bleeds_rslmatfx_type', 0)),
            str(material.get('bleeds_rslmatfx_texture_name', '')),
            str(material.get('bleeds_rslmatfx_blend', '')),
        )
        if signature is not None and current != signature:
            return False
        signature = current
    return signature is not None


def resolveWorldMaterial(resource, obj, record, owners, master):
    owner = owners.get('owner', {}).get(worldObjectTextureOwner(obj), {})
    if resource in owner:
        return owner[resource]
    area = owners['area'].get(int(obj.get('blds_img_area_index', -1)), {})
    source_sector = owners['sector'].get(int(obj.get('blds_img_sector_index', -1)), {})
    sector = owners['sector'].get(int(record.get('sector_index', -1)), {})
    if resource in area:
        return area[resource]
    if resource in source_sector:
        return source_sector[resource]
    if resource in sector:
        return sector[resource]
    if obj.get('blds_img_area_cell_x') is not None:
        cell = (int(obj['blds_img_area_cell_x']), int(obj['blds_img_area_cell_y']))
    elif obj.get('blds_img_sector_x') is not None:
        cell = (int(obj['blds_img_sector_x']) // 3, int(obj['blds_img_sector_y']) // 3)
    else:
        cell = owners.get('sector_cells', {}).get(int(record.get('sector_index', -1)))
    candidates = [mapping[resource] for mapping in owners['cell'].get(cell, ()) if resource in mapping]
    if candidates:
        # A conflicting cell binding is missing data, not permission to use another area's image.
        if len({item.as_pointer() for item in candidates}) == 1 or worldMaterialsMatch(candidates):
            return candidates[0]
        return None
    return master.get(resource) or owners.get('shared', {}).get(resource)


def bindWorldMaterials(records, owners, master):
    missing = set()
    assigned = 0
    variants = {}
    for record in records:
        obj = record['object']
        for slot in obj.material_slots:
            original = slot.material
            if original is None:
                continue
            resource = int(original.get('blds_texture_res_index', original.get('blds_res_index', -1)))
            if resource < 0:
                if original.get('blds_kind') == 'WORLD_UNTEXTURED' and obj.data.vertex_colors.get('Col') is not None:
                    culling = bool(obj.get('blds_material_culling', {}).get('65535', original.use_backface_culling))
                    key = (original.as_pointer(), culling, True)
                    if key not in variants:
                        variants[key] = worldMaterialVariant(original, culling, True)
                    slot.link = 'OBJECT'
                    slot.material = variants[key]
                continue
            material = resolveWorldMaterial(resource, obj, record, owners, master)
            if material is not None:
                # Linked geometry can need a different local texture in each streamed sector.
                culling = bool(obj.get('blds_material_culling', {}).get(str(resource), material.use_backface_culling))
                has_colors = obj.data.vertex_colors.get('Col') is not None
                if has_colors or material.use_backface_culling != culling:
                    key = (material.as_pointer(), culling, has_colors)
                    if key not in variants:
                        variants[key] = worldMaterialVariant(material, culling, has_colors)
                    material = variants[key]
                slot.link = 'OBJECT'
                slot.material = material
                assigned += 1
            if material is None or material.get('blds_kind') == 'TEX_PLACEHOLDER' or material.get('blds_missing_texture_image'):
                missing.add(resource)
    return assigned, sorted(missing)


def worldMaterialVariant(material, culling, vertex_colors):
    result = material.copy()
    result.use_backface_culling = culling
    if (int(result.get('bleeds_uv_animated_nodes', 0)) > 0
            or result.get('bleeds_uv_source') == 'VCS_PS2_WORLD'):
        from ..leedsLib.lvz_img import syncNativeWorldUvAnimation
        syncNativeWorldUvAnimation(result)
    if not vertex_colors or not result.use_nodes or result.node_tree is None:
        return result
    nodes, links = result.node_tree.nodes, result.node_tree.links
    shader = next((node for node in nodes if node.type == 'BSDF_PRINCIPLED'), None)
    if shader is None:
        return result
    color = nodes.new('ShaderNodeVertexColor')
    color.layer_name = 'Col'
    color.label = 'Map Lighting'
    multiply = nodes.new('ShaderNodeMixRGB')
    multiply.blend_type = 'MULTIPLY'
    multiply.inputs[0].default_value = 1.0
    previous = next(iter(shader.inputs['Base Color'].links), None)
    if previous:
        links.new(previous.from_socket, multiply.inputs[1])
    else:
        multiply.inputs[1].default_value = shader.inputs['Base Color'].default_value
    links.new(color.outputs['Color'], multiply.inputs[2])
    links.new(multiply.outputs['Color'], shader.inputs['Base Color'])
    # Native world vertex colors provide prelighting. Texture/material state
    # controls alpha; multiplying a 1-bit prelight alpha made entire buildings invisible.
    return result
