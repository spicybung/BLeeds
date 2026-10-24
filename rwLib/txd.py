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

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..leedsLib.native_mobile import writeAtomic


@dataclass
class MobileTexture:
    name: str
    width: int
    height: int
    depth: int
    mip_count: int
    flags: int
    pixel_offset: int
    pixel_size: int
    palette_offset: int
    palette_size: int


def readHeader(data, offset, expected=None):
    if offset < 0 or offset + 12 > len(data):
        raise ValueError('Incomplete TXD chunk header')
    kind, size, version = struct.unpack_from('<3I', data, offset)
    if expected is not None and kind != expected:
        raise ValueError('Unexpected TXD chunk at 0x%X' % offset)
    if offset + 12 + size > len(data):
        raise ValueError('TXD chunk extends beyond the file')
    return kind, size, version


class MobileTxd:
    def __init__(self, data):
        self.data = bytes(data)
        data = self.data
        readHeader(data, 0, 0x16)
        _, size, version = readHeader(data, 12, 1)
        if size != 4:
            raise ValueError('Invalid mobile TXD dictionary header')
        count = struct.unpack_from('<H', data, 24)[0]
        cursor = 28
        self.textures = []
        for index in range(count):
            readHeader(data, cursor, 0x15)
            cursor += 12
            _, size, version = readHeader(data, cursor, 1)
            platform = data[cursor + 12:cursor + 16]
            if size != 8 or platform not in (b'PSP\0', b'PS2\0'):
                raise ValueError('Unsupported mobile TXD raster platform')
            cursor += 12 + size
            strings = []
            for string_index in range(2):
                _, size, version = readHeader(data, cursor, 2)
                strings.append(data[cursor + 12:cursor + 12 + size].split(b'\0', 1)[0].decode('ascii'))
                cursor += 12 + size
            readHeader(data, cursor, 1)
            cursor += 12
            _, size, version = readHeader(data, cursor, 1)
            if platform == b'PS2\0':
                if size != 64:
                    raise ValueError('Unsupported mobile PS2 raster header')
                width, height, depth = struct.unpack_from('<3I', data, cursor + 12)
                cursor += 12 + size
                _, raster_size, version = readHeader(data, cursor, 1)
                pixel_offset = cursor + 12
                uploads = readGifImages(data, pixel_offset, raster_size)
                palette_bytes = 1024 if depth == 8 else 96
                if depth not in (4, 8) or len(uploads) < 2 or uploads[-1][1] < palette_bytes:
                    raise ValueError('Unsupported mobile PS2 texture depth or upload layout')
                texture = MobileTexture(strings[0], width, height, depth, len(uploads) - 1,
                                        0, pixel_offset, raster_size, uploads[-1][0], palette_bytes)
                texture.platform = 'PS2'
                texture.uploads = uploads[:-1]
                self.textures.append(texture)
                cursor = pixel_offset + raster_size
                _, size, version = readHeader(data, cursor, 3)
                cursor += 12 + size
                continue
            if size != 20:
                raise ValueError('Unsupported mobile raster header')
            width, height, depth, mip_count, flags = struct.unpack_from('<5I', data, cursor + 12)
            if not 0 < width <= 8192 or not 0 < height <= 8192 or depth not in (4, 8, 32) or not 0 < mip_count <= 14:
                raise ValueError('Invalid mobile texture dimensions, depth, or mip count')
            cursor += 32
            _, raster_size, version = readHeader(data, cursor, 1)
            pixel_offset = cursor + 12
            palette_size = (1 << depth) * 4 if depth in (4, 8) else 0
            pixel_size = sum(max(1, width >> level) * max(1, height >> level) * depth // 8
                             for level in range(mip_count))
            allowed_sizes = (pixel_size + palette_size, pixel_size + 4) if depth == 32 else (pixel_size + palette_size,)
            if raster_size not in allowed_sizes:
                raise ValueError('Mobile raster byte count does not match its mipmaps and palette')
            self.textures.append(MobileTexture(strings[0], width, height, depth, mip_count, flags,
                                               pixel_offset, pixel_size, pixel_offset + pixel_size, palette_size))
            cursor = pixel_offset + raster_size
            _, size, version = readHeader(data, cursor, 3)
            cursor += 12 + size
        _, size, version = readHeader(data, cursor, 3)
        cursor += 12 + size
        if any(data[cursor:]):
            raise ValueError('Unexpected data after the mobile TXD dictionary')

    def pixels(self, texture, level=0):
        if not 0 <= level < texture.mip_count:
            raise ValueError('Invalid mobile texture mip level')
        if getattr(texture, 'platform', '') == 'PS2':
            return self.ps2Pixels(texture, level)
        if texture.flags:
            raise ValueError('Unsupported mobile texture layout flags: 0x%X' % texture.flags)
        offset = texture.pixel_offset
        for previous in range(level):
            offset += max(1, texture.width >> previous) * max(1, texture.height >> previous) * texture.depth // 8
        width = max(1, texture.width >> level)
        height = max(1, texture.height >> level)
        count = width * height
        if texture.depth == 32:
            return np.frombuffer(self.data, dtype=np.uint8, count=count * 4, offset=offset).reshape(height, width, 4).copy()
        if texture.depth == 8:
            indices = np.frombuffer(self.data, dtype=np.uint8, count=count, offset=offset)
        else:
            packed = np.frombuffer(self.data, dtype=np.uint8, count=(count + 1) // 2, offset=offset)
            indices = np.empty(len(packed) * 2, dtype=np.uint8)
            indices[0::2] = packed & 15
            indices[1::2] = packed >> 4
            indices = indices[:count]
        palette = np.frombuffer(self.data, dtype=np.uint8, count=texture.palette_size,
                                offset=texture.palette_offset).reshape(-1, 4)
        return palette[indices].reshape(height, width, 4).copy()

    def replacePixels(self, name, pixels):
        matches = [texture for texture in self.textures if texture.name.casefold() == name.casefold()]
        if len(matches) != 1:
            raise ValueError('Texture name must identify exactly one entry')
        texture = matches[0]
        if getattr(texture, 'platform', '') == 'PS2':
            return self.replacePs2Pixels(texture, pixels)
        if texture.flags:
            raise ValueError('Unsupported mobile texture layout flags')
        pixels = np.asarray(pixels, dtype=np.uint8)
        if pixels.shape != (texture.height, texture.width, 4):
            raise ValueError('Replacement image dimensions must match the mobile texture')
        if np.array_equal(pixels, self.pixels(texture)):
            return
        output = bytearray(self.data)
        palette = None
        if texture.depth in (4, 8):
            colors, counts = np.unique(pixels.reshape(-1, 4), axis=0, return_counts=True)
            colors = colors[np.argsort(-counts, kind='stable')[:1 << texture.depth]]
            palette = np.zeros((1 << texture.depth, 4), dtype=np.uint8)
            palette[:len(colors)] = colors
            output[texture.palette_offset:texture.palette_offset + texture.palette_size] = palette.tobytes()
        offset = texture.pixel_offset
        for level in range(texture.mip_count):
            width, height = max(1, texture.width >> level), max(1, texture.height >> level)
            rows = (np.arange(height) * texture.height // height)
            columns = (np.arange(width) * texture.width // width)
            mip = pixels[rows[:, None], columns[None, :]].reshape(-1, 4)
            if palette is None:
                encoded = mip.tobytes()
            else:
                indices = np.empty(len(mip), dtype=np.uint8)
                for start in range(0, len(mip), 4096):
                    difference = mip[start:start + 4096, None, :].astype(np.int32) - palette[None, :, :].astype(np.int32)
                    indices[start:start + 4096] = np.argmin(np.sum(difference * difference, axis=2), axis=1)
                if texture.depth == 4:
                    if len(indices) % 2:
                        indices = np.append(indices, np.uint8(0))
                    encoded = (indices[0::2] | (indices[1::2] << 4)).tobytes()
                else:
                    encoded = indices.tobytes()
            output[offset:offset + len(encoded)] = encoded
            offset += len(encoded)
        if len(output) != len(self.data):
            raise ValueError('Replacement changed the mobile texture data size')
        self.data = bytes(output)

    def write(self, path):
        writeAtomic(path, self.data)

    def ps2Pixels(self, texture, level):
        from ..leedsLib.tex import unswizzle_ps2_indices, convert_clut_ps2
        offset, size = texture.uploads[level]
        width, height = max(1, texture.width >> level), max(1, texture.height >> level)
        if size * 8 // texture.depth < width * height:
            raise ValueError('Incomplete mobile PS2 mipmap upload')
        indices = np.frombuffer(self.data, dtype=np.uint8, count=size, offset=offset)
        if texture.depth == 4:
            unpacked = np.empty(len(indices) * 2, dtype=np.uint8)
            unpacked[0::2] = indices & 15
            unpacked[1::2] = indices >> 4
            indices = unpacked
        indices = unswizzle_ps2_indices(indices, width, height)
        convert_clut_ps2(indices)
        palette = np.frombuffer(self.data, dtype=np.uint8, count=texture.palette_size,
                                offset=texture.palette_offset).reshape(-1, 4).copy()
        palette[:, 3] = np.minimum(palette[:, 3].astype(np.uint16) * 255 // 128, 255)
        return palette[indices].reshape(height, width, 4)

    def replacePs2Pixels(self, texture, pixels):
        from ..leedsLib.tex import swizzle_ps2, convert_clut_ps2
        pixels = np.asarray(pixels, dtype=np.uint8)
        if pixels.shape != (texture.height, texture.width, 4):
            raise ValueError('Replacement dimensions must match the mobile PS2 texture')
        if np.array_equal(pixels, self.ps2Pixels(texture, 0)):
            return
        colors, counts = np.unique(pixels.reshape(-1, 4), axis=0, return_counts=True)
        color_count = 1 << texture.depth
        colors = colors[np.argsort(-counts, kind='stable')[:color_count]]
        palette = np.zeros((color_count, 4), dtype=np.uint8)
        palette[:len(colors)] = colors
        stored_palette = palette.copy()
        stored_palette[:, 3] = np.rint(stored_palette[:, 3].astype(np.float32) * 128.0 / 255.0).astype(np.uint8)
        output = bytearray(self.data)
        if texture.depth == 4:
            slots = np.arange(16, dtype=np.uint8)
            convert_clut_ps2(slots)
            expanded = np.frombuffer(output[texture.palette_offset:texture.palette_offset + texture.palette_size], dtype=np.uint8).copy().reshape(-1, 4)
            expanded[slots] = stored_palette
            stored_palette = expanded
        output[texture.palette_offset:texture.palette_offset + texture.palette_size] = stored_palette.tobytes()
        for level, (offset, size) in enumerate(texture.uploads):
            width, height = max(1, texture.width >> level), max(1, texture.height >> level)
            rows = np.arange(height) * texture.height // height
            columns = np.arange(width) * texture.width // width
            mip = pixels[rows[:, None], columns[None, :]].reshape(-1, 4)
            indices = np.empty(len(mip), dtype=np.uint8)
            for start in range(0, len(mip), 4096):
                difference = mip[start:start + 4096, None, :].astype(np.int32) - palette[None, :, :].astype(np.int32)
                indices[start:start + 4096] = np.argmin(np.sum(difference * difference, axis=2), axis=1)
            if texture.depth == 8:
                convert_clut_ps2(indices)
            encoded = bytearray(output[offset:offset + size])
            if texture.depth == 4:
                packed = np.frombuffer(bytes(encoded), dtype=np.uint8)
                unpacked = np.empty(len(packed) * 2, dtype=np.uint8)
                unpacked[0::2] = packed & 15
                unpacked[1::2] = packed >> 4
                encoded = bytearray(unpacked)
            log_width = (width - 1).bit_length()
            for y in range(height):
                for x in range(width):
                    encoded[swizzle_ps2(x, y, log_width) % len(encoded)] = int(indices[y * width + x])
            if texture.depth == 4:
                unpacked = np.frombuffer(bytes(encoded), dtype=np.uint8)
                encoded = (unpacked[0::2] | (unpacked[1::2] << 4)).tobytes()
            output[offset:offset + size] = encoded
        self.data = bytes(output)


def readGifImages(data, offset, size):
    end = offset + size
    uploads = []
    while offset < end:
        if offset + 16 > end:
            raise ValueError('Incomplete mobile GIF tag')
        low, high = struct.unpack_from('<QQ', data, offset)
        count = low & 0x7FFF
        mode = (low >> 58) & 3
        registers = (low >> 60) & 15 or 16
        offset += 16
        if mode == 0:
            length = count * registers * 16
        elif mode == 1:
            length = ((count * registers + 1) // 2) * 16
        elif mode == 2:
            length = count * 16
            uploads.append((offset, length))
        else:
            raise ValueError('Unsupported mobile GIF tag mode')
        if offset + length > end:
            raise ValueError('Mobile GIF upload extends beyond the raster')
        offset += length
    return uploads
