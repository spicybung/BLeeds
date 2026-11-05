# BLeeds - Scripts for working with R* Leeds formats in Blender
# Author: spicybung

import struct
from dataclasses import dataclass

import numpy as np

from .chunks import RenderWareChunk, readChunks
from ..leedsLib.native_mobile import writeAtomic


@dataclass
class PcTexture:
    name: str
    width: int
    height: int
    depth: int
    mip_count: int
    platform: str
    format: str
    native: object
    structure: object
    levels: list
    raster_format: int
    d3d_format: int
    palette: object = None


def color565(value):
    return ((value >> 11) * 255 // 31, ((value >> 5) & 63) * 255 // 63, (value & 31) * 255 // 31, 255)


def decodeDxt(data, width, height, compression):
    # The last colour block can extend past the image. Trim it to the actual size.
    block_size = 8 if compression == 1 else 16
    columns, rows = (width + 3) // 4, (height + 3) // 4
    if len(data) != columns * rows * block_size:
        raise ValueError('The compressed texture size does not match its dimensions')
    result = np.empty((rows * 4, columns * 4, 4), dtype=np.uint8)
    for row in range(rows):
        for column in range(columns):
            offset = (row * columns + column) * block_size
            color_offset = offset if compression == 1 else offset + 8
            first, second, selectors = struct.unpack_from('<HHI', data, color_offset)
            a, b = color565(first), color565(second)
            if first > second or compression != 1:
                colors = (a, b, tuple((2 * a[i] + b[i]) // 3 for i in range(4)), tuple((a[i] + 2 * b[i]) // 3 for i in range(4)))
            else:
                colors = (a, b, tuple((a[i] + b[i]) // 2 for i in range(4)), (0, 0, 0, 0))
            block = np.asarray([colors[(selectors >> (index * 2)) & 3] for index in range(16)], dtype=np.uint8)
            if compression in (2, 3):
                alpha = int.from_bytes(data[offset:offset + 8], 'little')
                block[:, 3] = [(alpha >> (index * 4) & 15) * 17 for index in range(16)]
            elif compression in (4, 5):
                low, high = data[offset:offset + 2]
                if low > high:
                    alpha_values = [low, high] + [((7 - index) * low + index * high) // 7 for index in range(1, 7)]
                else:
                    alpha_values = [low, high] + [((5 - index) * low + index * high) // 5 for index in range(1, 5)] + [0, 255]
                selectors_alpha = int.from_bytes(data[offset + 2:offset + 8], 'little')
                block[:, 3] = [alpha_values[(selectors_alpha >> (index * 3)) & 7] for index in range(16)]
            if compression in (2, 4):
                alpha = block[:, 3].astype(np.float32)
                divisor = np.maximum(alpha, 1.0)[:, None]
                block[:, :3] = np.rint(np.minimum(block[:, :3].astype(np.float32) * 255.0 / divisor, 255.0)).astype(np.uint8)
            result[row * 4:row * 4 + 4, column * 4:column * 4 + 4] = block.reshape(4, 4, 4)
    return result[:height, :width].copy()


class PcTextureDictionary:
    def __init__(self, data):
        self.data = bytes(data)
        if len(data) < 12:
            raise ValueError('The texture dictionary header is incomplete')
        size = struct.unpack_from('<I', data, 4)[0]
        if size + 12 > len(data) or any(data[size + 12:]):
            raise ValueError('The texture dictionary size does not match its file')
        self.padding = data[size + 12:]
        roots = readChunks(data[:size + 12])
        if len(roots) != 1 or roots[0].type_id != 0x16:
            raise ValueError('Expected a RenderWare texture dictionary')
        self.root = roots[0]
        self.sections = self.root.children()
        structure = next((child for child in self.sections if child.type_id == 1), None)
        if structure is None or len(structure.payload) != 4:
            raise ValueError('The texture dictionary header is incomplete')
        count = struct.unpack_from('<H', structure.payload)[0]
        natives = [child for child in self.sections if child.type_id == 0x15]
        if count != len(natives):
            raise ValueError('The texture count does not match the dictionary')
        self.textures = []
        for native in natives:
            children = native.children()
            native.parsed_children = children
            structure = next((child for child in children if child.type_id == 1), None)
            if structure is None or len(structure.payload) < 88:
                raise ValueError('A texture header is incomplete')
            payload = structure.payload
            platform = struct.unpack_from('<I', payload)[0]
            if platform not in (8, 9):
                raise ValueError('This texture dictionary contains an unsupported platform')
            name = payload[8:40].split(b'\0', 1)[0].decode('utf-8', errors='replace')
            raster, d3d, width, height, depth, levels, raster_type, flags = struct.unpack_from('<IIHH4B', payload, 72)
            if not 0 < width <= 8192 or not 0 < height <= 8192 or width * height > 16777216 or not 0 < levels <= 14:
                raise ValueError('Invalid texture size or number of image levels')
            compression = flags if platform == 8 else ((d3d >> 24) - ord('0') if d3d & 0xFFFFFF == int.from_bytes(b'DXT', 'little') else 0)
            if compression not in (0, 1, 2, 3, 4, 5):
                raise ValueError('This texture compression is not supported')
            offset = 88
            palette = None
            if raster & 0x6000:
                palette_count = 32 if raster & 0x4000 else 256
                end = offset + palette_count * 4
                if end > len(payload):
                    raise ValueError('The texture palette is incomplete')
                palette = np.frombuffer(payload[offset:end], dtype=np.uint8).reshape(-1, 4).copy()
                offset = end
            image_levels = []
            for level in range(levels):
                if offset + 4 > len(payload):
                    raise ValueError('The texture ends before all its image levels')
                size = struct.unpack_from('<I', payload, offset)[0]
                offset += 4
                if offset + size > len(payload):
                    raise ValueError('A texture image level is incomplete')
                image_levels.append(payload[offset:offset + size])
                offset += size
            if offset != len(payload):
                raise ValueError('Unexpected data at the end of a texture')
            texture = PcTexture(name, width, height, depth, levels, 'PC', 'DXT%d' % compression if compression else '%d-bit' % depth,
                                native, structure, image_levels, raster, d3d, palette)
            texture.compression = compression
            self.textures.append(texture)

    def pixels(self, texture, level=0):
        if not 0 <= level < texture.mip_count:
            raise ValueError('Choose an image level contained in this texture')
        width, height = max(1, texture.width >> level), max(1, texture.height >> level)
        data = texture.levels[level]
        if texture.compression:
            return decodeDxt(data, width, height, texture.compression)
        count = width * height
        if texture.palette is not None:
            if texture.depth == 4:
                values = np.frombuffer(data, dtype=np.uint8)
                indices = np.empty(len(values) * 2, dtype=np.uint8)
                indices[0::2], indices[1::2] = values & 15, values >> 4
                indices = indices[:count]
            else:
                indices = np.frombuffer(data, dtype=np.uint8, count=count)
            if len(indices) != count or np.any(indices >= len(texture.palette)):
                raise ValueError('The texture palette does not contain every colour used')
            return texture.palette[indices].reshape(height, width, 4).copy()
        if texture.depth in (24, 32):
            channels = texture.depth // 8
            if len(data) != count * channels:
                raise ValueError('The texture byte count does not match its dimensions')
            source = np.frombuffer(data, dtype=np.uint8).reshape(height, width, channels)
            result = np.full((height, width, 4), 255, dtype=np.uint8)
            result[:, :, :3] = source[:, :, 2::-1]
            if channels == 4 and (texture.raster_format & 0xF00) == 0x500:
                result[:, :, 3] = source[:, :, 3]
            return result
        if texture.depth == 16:
            if len(data) != count * 2:
                raise ValueError('The texture byte count does not match its dimensions')
            packed = np.frombuffer(data, dtype='<u2').astype(np.uint32)
            raster = texture.raster_format & 0xF00
            if raster == 0x200:
                red, green, blue, alpha = (packed >> 11) * 255 // 31, ((packed >> 5) & 63) * 255 // 63, (packed & 31) * 255 // 31, np.full(count, 255)
            elif raster == 0x300:
                red, green, blue, alpha = ((packed >> 8) & 15) * 17, ((packed >> 4) & 15) * 17, (packed & 15) * 17, (packed >> 12) * 17
            elif raster in (0x100, 0xA00):
                red, green, blue = ((packed >> 10) & 31) * 255 // 31, ((packed >> 5) & 31) * 255 // 31, (packed & 31) * 255 // 31
                alpha = (packed >> 15) * 255 if raster == 0x100 else np.full(count, 255)
            else:
                raise ValueError('This 16-bit texture colour format is not supported')
            return np.stack((red, green, blue, alpha), axis=1).astype(np.uint8).reshape(height, width, 4)
        raise ValueError('This texture colour format is not supported')

    def replacePixels(self, name, pixels):
        matches = [texture for texture in self.textures if texture.name.casefold() == name.casefold()]
        if len(matches) != 1:
            raise ValueError('The texture name is missing or appears more than once: ' + name)
        texture = matches[0]
        pixels = np.asarray(pixels, dtype=np.uint8)
        if pixels.shape != (texture.height, texture.width, 4):
            raise ValueError('Keep the original texture width and height')
        if np.array_equal(pixels, self.pixels(texture)):
            return
        # Edited images are saved losslessly; untouched compressed images retain their original bytes.
        payload = bytearray(texture.structure.payload[:88])
        raster = (texture.raster_format & ~0x6F00) | 0x500
        struct.pack_into('<II', payload, 72, raster, 21 if struct.unpack_from('<I', payload)[0] == 9 else 1)
        payload[84] = 32
        payload[87] = 1 if struct.unpack_from('<I', payload)[0] == 9 else 0
        encoded_levels = []
        for level in range(texture.mip_count):
            width, height = max(1, texture.width >> level), max(1, texture.height >> level)
            image = pixels[(np.arange(height) * texture.height // height)[:, None],
                           (np.arange(width) * texture.width // width)[None, :]]
            encoded = image[:, :, [2, 1, 0, 3]].tobytes()
            payload.extend(struct.pack('<I', len(encoded)))
            payload.extend(encoded)
            encoded_levels.append(encoded)
        texture.structure.payload = bytes(payload)
        texture.native.payload = b''.join(child.toBytes() for child in texture.native.children())
        self.root.payload = b''.join(child.toBytes() for child in self.sections)
        self.data = self.root.toBytes() + self.padding
        texture.depth, texture.format, texture.compression = 32, '32-bit', 0
        texture.raster_format, texture.d3d_format, texture.palette = raster, 21, None
        texture.levels = encoded_levels

    def write(self, path):
        writeAtomic(path, self.data)
