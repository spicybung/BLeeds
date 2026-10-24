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

from ..leedsLib.native_mobile import writeAtomic

@dataclass
class RenderWareChunk:
    type_id: int
    version: int
    payload: bytes

    def toBytes(self):
        size = getattr(self, 'declared_size', len(self.payload)) + len(self.payload) - getattr(self, 'original_size', len(self.payload))
        return struct.pack('<III', self.type_id, size, self.version) + self.payload

    def children(self):
        return self.parsed_children if hasattr(self, "parsed_children") else readChunks(self.payload)


def readChunks(data):
    chunks = []
    offset = 0
    while offset < len(data):
        if len(data) - offset < 12:
            raise ValueError('Incomplete RenderWare chunk header at 0x%X' % offset)
        type_id, size, version = struct.unpack_from('<III', data, offset)
        end = offset + 12 + size
        if end > len(data):
            raise ValueError('RenderWare chunk at 0x%X extends beyond the file' % offset)
        chunks.append(RenderWareChunk(type_id, version, bytes(data[offset + 12:end])))
        offset = end
    return chunks


def readMobileAsset(path):
    chunks = readChunks(Path(path).read_bytes())
    if not chunks or any(chunk.type_id not in (0x10, 0x16) for chunk in chunks):
        raise ValueError('Expected a mobile DFF clump or TXD texture dictionary')
    return chunks


def writeMobileAsset(path, chunks):
    data = b''.join(chunk.toBytes() for chunk in chunks)
    readChunks(data)
    writeAtomic(path, data)



def readMobileDffChunks(data):
    def parse(offset, expected=None):
        if offset + 12 > len(data):
            raise ValueError('Incomplete mobile DFF chunk header')
        type_id, declared_size, version = struct.unpack_from('<III', data, offset)
        if expected is not None and type_id != expected:
            raise ValueError('Unexpected mobile DFF chunk at 0x%X' % offset)
        start = offset + 12
        cursor = start
        children = []
        def child(kind=None):
            nonlocal cursor
            item, cursor = parse(cursor, kind)
            children.append(item)
            return item
        if type_id == 0x10:
            structure = child(1)
            count = struct.unpack_from('<I', structure.payload)[0]
            child(0xE)
            if cursor + 4 <= len(data) and struct.unpack_from('<I', data, cursor)[0] == 0x1A:
                child(0x1A)
            for index in range(count):
                child(0x14)
            child(3)
        elif type_id == 0xE:
            structure = child(1)
            count = struct.unpack_from('<I', structure.payload)[0]
            if count > 100000:
                raise ValueError('Invalid mobile frame count')
            for index in range(count):
                child(3)
        elif type_id == 0x1A:
            structure = child(1)
            count = struct.unpack_from('<I', structure.payload)[0]
            for index in range(count):
                child(0xF)
        elif type_id == 0x14:
            child(1)
            if cursor + 4 <= len(data) and struct.unpack_from('<I', data, cursor)[0] == 0xF:
                child(0xF)
            child(3)
        elif type_id == 0xF and version == 0xF00D:
            if cursor + 64 > len(data):
                raise ValueError('Incomplete Leeds geometry header')
            packed = struct.unpack_from('<I', data, cursor + 16)[0]
            geometry_size = packed & 0xFFFFF
            if geometry_size < 64 or cursor + geometry_size > len(data):
                raise ValueError('Invalid Leeds geometry size')
            cursor += geometry_size
            child(8)
            child(3)
        elif type_id == 8:
            structure = child(1)
            if len(structure.payload) < 4:
                raise ValueError('Incomplete material list')
            count = struct.unpack_from('<I', structure.payload)[0]
            if len(structure.payload) != 4 + count * 4:
                raise ValueError('Invalid mobile material list')
            for index in range(count):
                reference = struct.unpack_from('<i', structure.payload, 4 + index * 4)[0]
                if reference == -1:
                    child(7)
                elif reference < 0 or reference >= index:
                    raise ValueError('Invalid shared material index')
        elif type_id == 7:
            structure = child(1)
            if len(structure.payload) < 16:
                raise ValueError('Incomplete material structure')
            if struct.unpack_from('<I', structure.payload, 12)[0]:
                child(6)
            child(3)
        elif type_id == 3:
            declared_end = start + declared_size
            while cursor < declared_end:
                child()
        elif type_id == 0x120:
            cursor = start + declared_size + 4
            if cursor > len(data):
                raise ValueError('Incomplete mobile material effect')
        elif type_id == 6:
            child(1)
            child(2)
            child(2)
            child(3)
        else:
            cursor = start + declared_size
            if cursor > len(data):
                raise ValueError('Mobile DFF chunk extends beyond the file')
        item = RenderWareChunk(type_id, version, bytes(data[start:cursor]))
        item.declared_size = declared_size
        item.original_size = len(item.payload)
        if children:
            item.parsed_children = children
        return item, cursor
    roots = []
    cursor = 0
    while cursor < len(data):
        if not any(data[cursor:]):
            if roots:
                roots[-1].trailing_bytes = data[cursor:]
            break
        root, cursor = parse(cursor, 0x10)
        roots.append(root)
    return roots
