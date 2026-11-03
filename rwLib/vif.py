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
from typing import Dict, List, Tuple

def decodeVifNum(raw_num: int) -> int:
    value = int(raw_num) & 0xFF
    return 256 if value == 0 else value

@dataclass
class Ps2VifCommandRecord:
    stream_offset: int
    word: int
    command: int
    num: int
    immediate: int
    payload: bytes = b""
    source_vector_count: int = 0
    destination: int = 0

@dataclass
class Ps2VifDecoderState:
    cycle_length: int = 1
    write_length: int = 1
    mode: int = 0
    mask: int = 0
    row: Tuple[int, int, int, int] = (0, 0, 0, 0)
    column: Tuple[int, int, int, int] = (0, 0, 0, 0)

class Ps2VifStreamDecoder:
    def __init__(self):
        self.state = Ps2VifDecoderState()
        self.buffer = bytearray()
        self.stream_offset = 0
        self.vu_memory: Dict[int, List[int]] = {}

    def reset(self) -> None:
        self.state = Ps2VifDecoderState()
        self.buffer.clear()
        self.stream_offset = 0
        self.vu_memory.clear()

    def unpackSourceVectorCount(self, num: int) -> int:
        count = int(num)
        cycle_length = int(self.state.cycle_length)
        write_length = int(self.state.write_length)

        if count <= 0:
            return 0
        if write_length <= cycle_length:
            return count
        if cycle_length <= 0:
            return 0

        complete_cycles, remainder = divmod(count, write_length)
        return (complete_cycles * cycle_length) + min(remainder, cycle_length)

    def unpackPayloadSize(self, command: int, num: int) -> Tuple[int, int]:
        command = int(command) & 0x7F
        if command == 0x77:
            return 0, 0

        format_value = command & 0x0F
        vector_size = (format_value >> 2) + 1
        component_format = format_value & 0x03

        if component_format == 0:
            component_size = 4
            packed_vector_size = vector_size * component_size
        elif component_format == 1:
            component_size = 2
            packed_vector_size = vector_size * component_size
        elif component_format == 2:
            component_size = 1
            packed_vector_size = vector_size * component_size
        elif vector_size == 4:
            packed_vector_size = 2
        else:
            return 0, 0

        source_vector_count = self.unpackSourceVectorCount(num)
        payload_size = source_vector_count * packed_vector_size
        payload_size = (payload_size + 3) & ~3
        return payload_size, source_vector_count

    def commandPayloadSize(self, command: int, num: int, immediate: int) -> Tuple[int, int]:
        command = int(command) & 0x7F
        if command == 0x20:
            return 4, 0
        if command in (0x30, 0x31):
            return 16, 0
        if command == 0x4A:
            return decodeVifNum(num) * 8, 0
        if command in (0x50, 0x51):
            return (int(immediate) & 0xFFFF) * 16, 0
        if 0x60 <= command <= 0x7F:
            return self.unpackPayloadSize(command, decodeVifNum(num))
        return 0, 0

    def decodeScalar(self, payload: bytes, offset: int, size: int, unsigned: bool) -> int:
        if offset < 0 or offset + size > len(payload):
            return 0
        if size == 1:
            return int(payload[offset]) if unsigned else int(struct.unpack_from("<b", payload, offset)[0])
        if size == 2:
            fmt = "<H" if unsigned else "<h"
            return int(struct.unpack_from(fmt, payload, offset)[0])
        if size == 4:
            fmt = "<I" if unsigned else "<i"
            return int(struct.unpack_from(fmt, payload, offset)[0])
        return 0

    def decodeUnpackVectors(self, record: Ps2VifCommandRecord) -> List[Tuple[int, int, int, int]]:
        command = int(record.command) & 0x7F
        if command < 0x60 or command > 0x7F:
            return []

        count = int(record.source_vector_count)
        if command == 0x77:
            return []

        format_value = command & 0x0F
        vector_size = (format_value >> 2) + 1
        component_format = format_value & 0x03
        unsigned = bool(int(record.immediate) & 0x4000)
        vectors: List[Tuple[int, int, int, int]] = []

        if component_format == 3:
            if vector_size != 4:
                return []
            available_count = min(count, len(record.payload) // 2)
            packed_values = struct.iter_unpack("<H", record.payload[:available_count * 2])
            for (packed,) in packed_values:
                vectors.append((
                    (packed & 0x001F) << 3,
                    (packed & 0x03E0) >> 2,
                    (packed & 0x7C00) >> 7,
                    (packed & 0x8000) >> 8,
                ))
            return vectors

        component_size = (4, 2, 1)[component_format]
        packed_vector_size = vector_size * component_size
        payload_absolute_offset = int(record.stream_offset) + 4
        payload = record.payload

        if len(payload) >= count * packed_vector_size:
            component_code = (
                ("I" if unsigned else "i") if component_size == 4 else
                ("H" if unsigned else "h") if component_size == 2 else
                ("B" if unsigned else "b")
            )
            fmt = "<" + component_code * vector_size
            unpacked = struct.iter_unpack(fmt, payload[:count * packed_vector_size])
            if vector_size == 1:
                return [(a, a, a, a) for (a,) in unpacked]
            if vector_size == 2:
                return [(a, b, a, b) for a, b in unpacked]
            if vector_size == 4:
                return list(unpacked)
            for vector_index, (a, b, c) in enumerate(unpacked):
                vector_offset = vector_index * packed_vector_size
                fourth_offset = vector_offset + (3 * component_size)
                vector_absolute_offset = payload_absolute_offset + vector_offset
                same_qword = (vector_absolute_offset // 16) == (
                    (payload_absolute_offset + fourth_offset) // 16
                )
                fourth = self.decodeScalar(payload, fourth_offset, component_size, unsigned) if same_qword else 0
                vectors.append((a, b, c, fourth))
            return vectors

        for vector_index in range(count):
            vector_offset = vector_index * packed_vector_size
            components = [
                self.decodeScalar(
                    record.payload,
                    vector_offset + (component_index * component_size),
                    component_size,
                    unsigned,
                )
                for component_index in range(vector_size)
            ]

            if vector_size == 1:
                lanes = (components[0], components[0], components[0], components[0])
            elif vector_size == 2:
                lanes = (components[0], components[1], components[0], components[1])
            elif vector_size == 3:
                fourth_offset = vector_offset + (3 * component_size)
                fourth_absolute_offset = payload_absolute_offset + fourth_offset
                vector_absolute_offset = payload_absolute_offset + vector_offset
                same_qword = (vector_absolute_offset // 16) == (fourth_absolute_offset // 16)
                fourth = self.decodeScalar(
                    record.payload, fourth_offset, component_size, unsigned
                ) if same_qword else 0
                lanes = (components[0], components[1], components[2], fourth)
            else:
                lanes = (components[0], components[1], components[2], components[3])
            vectors.append(tuple(int(value) for value in lanes))

        return vectors

    def applyUnpackMode(self, value: int, lane: int) -> int:
        mode = int(self.state.mode) & 0x03
        row_value = int(self.state.row[lane])
        if mode == 1:
            return int(value) + row_value
        if mode == 2:
            result = int(value) + row_value
            row_values = list(self.state.row)
            row_values[lane] = result & 0xFFFFFFFF
            self.state.row = tuple(row_values)
            return result
        if mode == 3:
            row_values = list(self.state.row)
            row_values[lane] = int(value) & 0xFFFFFFFF
            self.state.row = tuple(row_values)
            return int(value)
        return int(value)

    def executeUnpack(self, record: Ps2VifCommandRecord) -> None:
        command = int(record.command) & 0x7F
        if command < 0x60 or command > 0x7F:
            return

        source_vectors = self.decodeUnpackVectors(record)
        base_destination = int(record.destination) & 0x3FF
        write_count = int(record.num)
        use_mask = bool(command & 0x10)
        is_v45 = (command & 0x0F) == 0x0F
        cycle_length = int(self.state.cycle_length)
        write_length = max(1, int(self.state.write_length))
        source_index = 0

        for write_index in range(write_count):
            cycle_position = write_index % write_length
            has_source = command != 0x77
            if write_length > cycle_length:
                has_source = has_source and cycle_position < cycle_length

            if write_length <= cycle_length:
                cycle_group = write_index // write_length
                destination_offset = (cycle_group * cycle_length) + cycle_position
            else:
                destination_offset = write_index

            destination = (base_destination + destination_offset) & 0x3FF
            old_lanes = list(self.vu_memory.get(destination, [0, 0, 0, 0]))
            data_lanes = source_vectors[source_index] if has_source and source_index < len(source_vectors) else None
            if has_source:
                source_index += 1

            mask_cycle = min(cycle_position, 3)
            column_value = int(self.state.column[mask_cycle])
            new_lanes = list(old_lanes)
            for lane in range(4):
                selector = (
                    (int(self.state.mask) >> ((mask_cycle * 8) + (lane * 2))) & 0x03
                ) if use_mask else 0
                if selector == 0:
                    if data_lanes is not None:
                        new_lanes[lane] = int(data_lanes[lane]) if is_v45 else self.applyUnpackMode(int(data_lanes[lane]), lane)
                elif selector == 1:
                    new_lanes[lane] = int(self.state.row[lane])
                elif selector == 2:
                    new_lanes[lane] = column_value
            self.vu_memory[destination] = [int(value) & 0xFFFFFFFF for value in new_lanes]

    def applyCommandState(self, record: Ps2VifCommandRecord) -> None:
        command = int(record.command) & 0x7F
        if command == 0x01:
            raw_cycle_length = int(record.immediate) & 0xFF
            raw_write_length = (int(record.immediate) >> 8) & 0xFF
            self.state.cycle_length = raw_cycle_length
            self.state.write_length = 256 if raw_write_length == 0 else raw_write_length
        elif command == 0x05:
            self.state.mode = int(record.immediate) & 0x03
        elif command == 0x20 and len(record.payload) >= 4:
            self.state.mask = struct.unpack_from("<I", record.payload, 0)[0]
        elif command == 0x30 and len(record.payload) >= 16:
            self.state.row = tuple(struct.unpack_from("<4I", record.payload, 0))
        elif command == 0x31 and len(record.payload) >= 16:
            self.state.column = tuple(struct.unpack_from("<4I", record.payload, 0))
        elif 0x60 <= command <= 0x7F:
            self.executeUnpack(record)

    def feed(self, data: bytes, final: bool = False) -> List[Ps2VifCommandRecord]:
        self.buffer.extend(bytes(data or b""))
        records: List[Ps2VifCommandRecord] = []

        while len(self.buffer) >= 4:
            word = struct.unpack_from("<I", self.buffer, 0)[0]
            command = (word >> 24) & 0x7F
            num = decodeVifNum((word >> 16) & 0xFF) if 0x60 <= command <= 0x7F else ((word >> 16) & 0xFF)
            immediate = word & 0xFFFF
            payload_size, source_vector_count = self.commandPayloadSize(command, num, immediate)
            total_size = 4 + payload_size
            if len(self.buffer) < total_size:
                break

            payload = bytes(self.buffer[4:total_size])
            record = Ps2VifCommandRecord(
                stream_offset=int(self.stream_offset),
                word=int(word),
                command=int(command),
                num=int(num),
                immediate=int(immediate),
                payload=payload,
                source_vector_count=int(source_vector_count),
                destination=int(immediate & 0x3FF) if 0x60 <= command <= 0x7F else 0,
            )
            records.append(record)
            self.applyCommandState(record)

            del self.buffer[:total_size]
            self.stream_offset += total_size

        if final and self.buffer:
            raise ValueError(
                f"Incomplete VIF command or payload at stream offset 0x{self.stream_offset:X}: "
                f"{len(self.buffer)} trailing bytes"
            )

        return records
