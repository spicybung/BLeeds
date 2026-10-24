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

import math
import os
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path


SECTOR_SIZE = 2048


@dataclass
class MobileEntry:
    name: str
    sector: int
    sector_count: int



def writeAtomic(path, data):
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def readDirectory(data, image_size=None):
    if len(data) % 32:
        raise ValueError('Mobile DIR size must be a multiple of 32 bytes')
    entries = []
    names = set()
    intervals = []
    for offset in range(0, len(data), 32):
        sector, count, raw_name = struct.unpack_from('<II24s', data, offset)
        name = raw_name.split(b'\0', 1)[0].decode('ascii')
        if not name or '/' in name or '\\' in name or name in ('.', '..'):
            raise ValueError('Invalid DIR filename at 0x%X' % offset)
        if name.casefold() in names:
            raise ValueError('Duplicate DIR filename: ' + name)
        if not count:
            raise ValueError('Empty IMG entry: ' + name)
        end = (sector + count) * SECTOR_SIZE
        if image_size is not None and end > image_size:
            raise ValueError('IMG entry extends beyond the file: ' + name)
        names.add(name.casefold())
        intervals.append((sector, sector + count, name))
        entries.append(MobileEntry(name, sector, count))
    intervals.sort()
    for previous, current in zip(intervals, intervals[1:]):
        if current[0] < previous[1]:
            raise ValueError('Overlapping IMG entries: %s and %s' % (previous[2], current[2]))
    return entries


class MobileArchive:
    def __init__(self, image_path, directory_path=None):
        self.image_path = Path(image_path)
        if directory_path is None:
            candidates = [p for p in self.image_path.parent.iterdir()
                          if p.name.casefold() == self.image_path.with_suffix('.dir').name.casefold()]
            if len(candidates) != 1:
                raise ValueError('Select the matching mobile DIR file')
            directory_path = candidates[0]
        self.directory_path = Path(directory_path)
        self.entries = readDirectory(self.directory_path.read_bytes(), self.image_path.stat().st_size)

    def read(self, name):
        matches = [entry for entry in self.entries if entry.name.casefold() == name.casefold()]
        if not matches:
            raise KeyError(name)
        entry = matches[0]
        with self.image_path.open('rb') as stream:
            stream.seek(entry.sector * SECTOR_SIZE)
            data = stream.read(entry.sector_count * SECTOR_SIZE)
        if len(data) != entry.sector_count * SECTOR_SIZE:
            raise ValueError('Incomplete IMG entry: ' + name)
        return data

    def extract(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        for entry in self.entries:
            writeAtomic(directory / entry.name, self.read(entry.name))

    def rebuild(self, image_path, directory_path, replacements=None):
        image_path = Path(image_path)
        directory_path = Path(directory_path)
        if image_path.resolve() in (self.image_path.resolve(), self.directory_path.resolve()):
            raise ValueError('Write the rebuilt IMG to a new file')
        if directory_path.resolve() in (self.image_path.resolve(), self.directory_path.resolve(), image_path.resolve()):
            raise ValueError('Write the rebuilt DIR to a separate new file')
        replacements = replacements or {}
        known = {entry.name.casefold() for entry in self.entries}
        supplied = {name.casefold(): bytes(data) for name, data in replacements.items()}
        if len(supplied) != len(replacements) or not set(supplied).issubset(known):
            raise ValueError('Replacement names must match existing IMG entries once each')
        descriptor, temporary = tempfile.mkstemp(prefix=image_path.name + '.', dir=image_path.parent)
        table = bytearray()
        sector = 0
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                for entry in self.entries:
                    data = supplied.get(entry.name.casefold())
                    if data is None:
                        data = self.read(entry.name)
                    if not data:
                        raise ValueError('Cannot write an empty IMG entry: ' + entry.name)
                    count = (len(data) + SECTOR_SIZE - 1) // SECTOR_SIZE
                    table.extend(struct.pack('<II24s', sector, count, entry.name.encode('ascii')))
                    stream.write(data)
                    stream.write(b'\0' * (count * SECTOR_SIZE - len(data)))
                    sector += count
            readDirectory(table, sector * SECTOR_SIZE)
            os.replace(temporary, image_path)
            writeAtomic(directory_path, table)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

