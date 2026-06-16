# BLeeds - Scripts for working with R* Leeds (GTA Stories, Chinatown Wars, Manhunt 2, etc) formats in Blender
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

#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
#   This script is for Stories .ANIM files and raw CAnimBlendTree data              #
#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
# - Script resources:
# • https://gtamods.com/wiki/Relocatable_chunk (pre-process)
# • https://web.archive.org/web/20180712151513/http://gtamodding.ru/wiki/ANIM (*Russian*)
# • https://web-archive-org.translate.goog/web/20180712151513/http://gtamodding.ru/wiki/ANIM?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (*English*)
# • https://github.com/aap/librwgta (*re'd RW/Leeds Engine source by The_Hero*)
# • https://github.com/aap/librwgta/blob/master/tools/storiesconv/rsl.h (ditto)
# • https://github.com/aap/librwgta/blob/master/tools/storiesconv/rslconv.cpp (ditto)
# - Mod resources/cool stuff:
# • https://libertycity.net/files/gta-liberty-city-stories/48612-yet-another-img-editor.html (GTA3xx .img: .mdls, textures, animations)
# • https://gtaforums.com/topic/838537-lcsvcs-dir-files/

import math
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from ..data.bone_data import PED_ANIM_HASH16_TO_DIRECT_ID


class AnimReadError(ValueError):
    pass

class AnimLog:
    def __init__(self, enabled: bool = False, max_lines: int = 2000):
        self.enabled = bool(enabled)
        self.max_lines = int(max_lines)
        self.lines: List[str] = []
        self.truncated = False

    def write(self, text: str) -> None:
        if not self.enabled:
            return
        if len(self.lines) >= self.max_lines:
            self.truncated = True
            return
        self.lines.append(str(text))

    def warning(self, text: str) -> None:
        self.write("WARNING: " + str(text))

    def text(self) -> str:
        if self.truncated:
            return "\n".join(self.lines + ["... log truncated ..."])
        return "\n".join(self.lines)

def requireRange(data: bytes, off: int, size: int, label: str) -> None:
    if off < 0 or size < 0 or off + size > len(data):
        raise AnimReadError(
            f"{label} read out of bounds: off=0x{off:08X}, size=0x{size:X}, file_size=0x{len(data):08X}"
        )

def readU16(data: bytes, off: int) -> int:
    requireRange(data, off, 2, "u16")
    return struct.unpack_from("<H", data, off)[0]

def readU32(data: bytes, off: int) -> int:
    requireRange(data, off, 4, "u32")
    return struct.unpack_from("<I", data, off)[0]

def readF32(data: bytes, off: int) -> float:
    requireRange(data, off, 4, "f32")
    return struct.unpack_from("<f", data, off)[0]

def halfToFloat(value: int) -> float:
    value = int(value) & 0xFFFF
    sign = value & 0x8000
    exp = (value >> 10) & 0x1F
    mant = value & 0x03FF

    if exp == 0:
        if mant == 0:
            return -0.0 if sign else 0.0
        while (mant & 0x0400) == 0:
            mant <<= 1
            exp -= 1
        mant &= 0x03FF
        exp += 1
    elif exp == 0x1F:
        bits = (sign << 16) | (0xFF << 23) | (mant << 13)
        return struct.unpack("<f", struct.pack("<I", bits))[0]

    exp = exp + (127 - 15)
    bits = (sign << 16) | (exp << 23) | (mant << 13)
    return struct.unpack("<f", struct.pack("<I", bits))[0]

def readHalf3(data: bytes, off: int) -> Tuple[float, float, float]:
    requireRange(data, off, 6, "half3")
    a, b, c = struct.unpack_from("<HHH", data, off)
    return halfToFloat(a), halfToFloat(b), halfToFloat(c)

def decodeFixedAscii(raw: bytes) -> str:
    return raw.split(b"\x00")[0].decode("ascii", errors="replace")

def isPrintableAsciiName(raw: bytes) -> bool:
    name = raw.split(b"\x00")[0]
    return bool(name) and all(0x20 <= value <= 0x7E for value in name)

def isFiniteTuple(values: Sequence[float]) -> bool:
    return all(math.isfinite(float(value)) for value in values)

@dataclass
class AnimFrame:
    rotation_xyzw: Tuple[float, float, float, float]
    delta_time: float
    absolute_time: float
    translation_xyz: Tuple[float, float, float]
    scale_xyz: Tuple[float, float, float]

@dataclass
class BoneAnim:
    table_index: int
    flags: int
    frame_count: int
    frames_off: int
    bone_key: int
    direct_bone_id: Optional[int]
    hash16: int
    low16: int
    frames: List[AnimFrame] = field(default_factory=list)

    @property
    def has_rotation(self) -> bool:
        return bool(self.flags & 0x0001)

    @property
    def has_translation(self) -> bool:
        return bool(self.flags & 0x0002)

    @property
    def has_scale(self) -> bool:
        return bool(self.flags & 0x0004)

    @property
    def has_direct_bone_id(self) -> bool:
        return bool(self.flags & 0x0010)

    def targetLabel(self) -> str:
        if self.direct_bone_id is not None:
            return f"id:{self.direct_bone_id}"
        return f"key:0x{self.bone_key:08X}"

@dataclass
class AnimEntry:
    index: int
    anim_off: int
    bone_table_off: int
    name: str
    bone_count: int
    unk0: int
    total_time: float
    bones: List[BoneAnim] = field(default_factory=list)

@dataclass
class AnimFile:
    header: bytes
    logical_file_size: int
    actual_file_size: int
    reloc_off: int
    reloc_table: List[int]
    animations: List[AnimEntry]
    log_text: str = ""

    def buildDirectBoneIdSet(self) -> List[int]:
        found = {
            bone.direct_bone_id
            for entry in self.animations
            for bone in entry.bones
            if bone.direct_bone_id is not None
        }
        return sorted(value for value in found if value is not None)

    def buildResolvedPedAnimBoneIdSet(self) -> List[int]:
        found = set()
        for entry in self.animations:
            for bone in entry.bones:
                direct_id, reason = resolvePedAnimBoneId(bone)
                if direct_id is not None:
                    found.add(int(direct_id))
        return sorted(found)

    def summaryText(self, include_bones: bool = True, max_bones_per_anim: int = 64) -> str:
        lines: List[str] = []
        lines.append(
            f"ANIM: animations={len(self.animations)}, reloc_entries={len(self.reloc_table)}, "
            f"logical_size=0x{self.logical_file_size:08X}, actual_size=0x{self.actual_file_size:08X}"
        )
        direct_ids = self.buildDirectBoneIdSet()
        resolved_ids = self.buildResolvedPedAnimBoneIdSet()
        if direct_ids:
            lines.append("Direct ped anim bone ids: " + ", ".join(str(value) for value in direct_ids))
        else:
            lines.append("Direct ped anim bone ids: none in flags; file is hash-keyed or not direct-id keyed")
        if resolved_ids:
            lines.append("Resolved ped anim bone ids: " + ", ".join(str(value) for value in resolved_ids))

        for entry in self.animations:
            direct_count = sum(1 for bone in entry.bones if bone.direct_bone_id is not None)
            hash_count = len(entry.bones) - direct_count
            lines.append(
                f"[{entry.index:02d}] {entry.name} bones={entry.bone_count} "
                f"time={entry.total_time:.6f} anim_off=0x{entry.anim_off:08X} "
                f"bone_table=0x{entry.bone_table_off:08X} direct={direct_count} hash={hash_count}"
            )
            if include_bones:
                for bone in entry.bones[:max_bones_per_anim]:
                    frame_count = len(bone.frames)
                    last_time = bone.frames[-1].absolute_time if bone.frames else 0.0
                    lines.append(
                        f"    bone[{bone.table_index:02d}] flags=0x{bone.flags:04X} "
                        f"frames={frame_count}/{bone.frame_count} off=0x{bone.frames_off:08X} "
                        f"key=0x{bone.bone_key:08X} target={formatAnimBoneTarget(bone)} last={last_time:.6f}"
                    )
                if len(entry.bones) > max_bones_per_anim:
                    lines.append(f"    ... {len(entry.bones) - max_bones_per_anim} more bones ...")
        return "\n".join(lines)

def calculateFrameStride(flags: int) -> int:
    stride = 2
    if flags & 0x0001:
        stride += 8
    if flags & 0x0002:
        stride += 6
    if flags & 0x0004:
        stride += 6
    return stride

def findAnimOffsets(data: bytes, log: AnimLog) -> List[int]:
    file_size = len(data)
    header_min = 0x20
    offsets: List[int] = []
    table_off = 0x20

    while table_off + 4 <= file_size:
        anim_off = readU32(data, table_off)
        if anim_off == 0:
            log.write(f"offset table stop: zero at 0x{table_off:08X}")
            break
        if anim_off < header_min or anim_off >= file_size:
            log.write(f"offset table stop: candidate 0x{anim_off:08X} at 0x{table_off:08X} out of range")
            break
        if anim_off + 36 > file_size:
            log.write(f"offset table stop: candidate 0x{anim_off:08X} too close to EOF")
            break

        bone_table_off = readU32(data, anim_off)
        if bone_table_off < header_min or bone_table_off >= file_size:
            log.write(f"offset table stop: candidate 0x{anim_off:08X} has bad bone table 0x{bone_table_off:08X}")
            break

        raw_name = data[anim_off + 4:anim_off + 28]
        if not isPrintableAsciiName(raw_name):
            log.write(f"offset table stop: candidate 0x{anim_off:08X} has non-printable/empty name")
            break

        offsets.append(anim_off)
        log.write(
            f"anim offset: table=0x{table_off:08X} anim=0x{anim_off:08X} "
            f"name={decodeFixedAscii(raw_name)!r} bone_table=0x{bone_table_off:08X}"
        )
        table_off += 4

    return offsets

def readAnimBytes(data: bytes, *, use_logical_size: bool = True, verbose: bool = False) -> AnimFile:
    if len(data) < 0x20:
        raise AnimReadError("File too small to be a Leeds ANIM container")
    if data[0:4] != b"mina":
        raise AnimReadError(f"Invalid ANIM magic {data[0:4]!r}; expected b'mina'")

    actual_size = len(data)
    logical_size = readU32(data, 0x08)
    reloc_off = readU32(data, 0x0C)
    reloc_off_dup = readU32(data, 0x10)
    reloc_count = readU32(data, 0x14)

    if logical_size < 0x20 or logical_size > actual_size:
        logical_size = actual_size

    parse_data = data[:logical_size] if use_logical_size else data
    log = AnimLog(enabled=verbose)

    if reloc_off != reloc_off_dup:
        log.warning(f"reloc offset duplicate mismatch: 0x{reloc_off:08X} vs 0x{reloc_off_dup:08X}")

    reloc_table: List[int] = []
    if reloc_off and reloc_count:
        for index in range(reloc_count):
            entry_off = reloc_off + index * 4
            if entry_off + 4 > len(parse_data):
                log.warning(f"reloc entry {index} at 0x{entry_off:08X} outside logical file; stopping reloc read")
                break
            reloc_table.append(readU32(parse_data, entry_off))

    anim_offsets = findAnimOffsets(parse_data, log)
    if not anim_offsets:
        raise AnimReadError("Could not find any valid CAnimBlendTree offsets after the header")

    animations: List[AnimEntry] = []
    for index, anim_off in enumerate(anim_offsets):
        bone_table_off = readU32(parse_data, anim_off + 0)
        name = decodeFixedAscii(parse_data[anim_off + 4:anim_off + 28])
        bone_count = readU16(parse_data, anim_off + 28)
        unk0 = readU16(parse_data, anim_off + 30)
        total_time = readF32(parse_data, anim_off + 32)
        if not math.isfinite(total_time) or total_time < 0.0 or total_time > 600.0:
            log.warning(f"animation {name!r} has suspicious total_time={total_time!r}")
        animations.append(
            AnimEntry(
                index=index,
                anim_off=anim_off,
                bone_table_off=bone_table_off,
                name=name,
                bone_count=bone_count,
                unk0=unk0,
                total_time=total_time,
            )
        )

    for entry in animations:
        bones: List[BoneAnim] = []
        table_off = entry.bone_table_off
        for bone_index in range(entry.bone_count):
            item_off = table_off + bone_index * 12
            if item_off + 12 > len(parse_data):
                log.warning(f"bone table for {entry.name!r} ended early at bone {bone_index}")
                break

            flags = readU16(parse_data, item_off + 0)
            frame_count = readU16(parse_data, item_off + 2)
            frames_off = readU32(parse_data, item_off + 4)
            bone_key = readU32(parse_data, item_off + 8)
            low16 = bone_key & 0xFFFF
            hash16 = (bone_key >> 16) & 0xFFFF

            if flags & 0x0010:
                direct_bone_id = low16
            elif (flags & 0x0008) and hash16 != 0 and low16 <= 0x00FF:
                direct_bone_id = low16
            else:
                direct_bone_id = None

            bones.append(
                BoneAnim(
                    table_index=bone_index,
                    flags=flags,
                    frame_count=frame_count,
                    frames_off=frames_off,
                    bone_key=bone_key,
                    direct_bone_id=direct_bone_id,
                    hash16=hash16,
                    low16=low16,
                )
            )
        entry.bones = bones

    for entry in animations:
        for bone in entry.bones:
            stride = calculateFrameStride(bone.flags)
            if stride <= 2:
                log.warning(f"{entry.name!r} bone {bone.table_index} has no rot/trans/scale flags: flags=0x{bone.flags:04X}")
            if bone.frames_off < 0x20 or bone.frames_off >= len(parse_data):
                log.warning(f"{entry.name!r} bone {bone.table_index} has bad frames_off=0x{bone.frames_off:08X}")
                continue

            absolute_time = 0.0
            frames: List[AnimFrame] = []
            cursor = bone.frames_off
            for frame_index in range(bone.frame_count):
                if cursor + stride > len(parse_data):
                    log.warning(
                        f"{entry.name!r} bone {bone.table_index} frame {frame_index} outside logical file; "
                        f"parsed {len(frames)}/{bone.frame_count}"
                    )
                    break

                pos = cursor
                rotation = (0.0, 0.0, 0.0, 1.0)
                if bone.has_rotation:
                    qx, qy, qz, qw = struct.unpack_from("<HHHH", parse_data, pos)
                    rotation = (halfToFloat(qx), halfToFloat(qy), halfToFloat(qz), halfToFloat(qw))
                    pos += 8

                delta_time = halfToFloat(readU16(parse_data, pos))
                pos += 2
                if not math.isfinite(delta_time) or delta_time < -0.001 or delta_time > 60.0:
                    log.warning(
                        f"{entry.name!r} bone {bone.table_index} frame {frame_index} suspicious delta_time={delta_time!r}"
                    )
                absolute_time += max(0.0, delta_time)

                translation = (0.0, 0.0, 0.0)
                if bone.has_translation:
                    translation = readHalf3(parse_data, pos)
                    pos += 6

                scale = (1.0, 1.0, 1.0)
                if bone.has_scale:
                    scale = readHalf3(parse_data, pos)
                    pos += 6

                if not isFiniteTuple(rotation + translation + scale):
                    log.warning(f"{entry.name!r} bone {bone.table_index} frame {frame_index} has non-finite values")

                frames.append(
                    AnimFrame(
                        rotation_xyzw=rotation,
                        delta_time=delta_time,
                        absolute_time=absolute_time,
                        translation_xyz=translation,
                        scale_xyz=scale,
                    )
                )
                cursor += stride

            bone.frames = frames

    return AnimFile(
        header=parse_data[:0x20],
        logical_file_size=logical_size,
        actual_file_size=actual_size,
        reloc_off=reloc_off,
        reloc_table=reloc_table,
        animations=animations,
        log_text=log.text(),
    )

def readAnimFile(path: str, *, use_logical_size: bool = True, verbose: bool = False) -> AnimFile:
    return readAnimBytes(Path(path).read_bytes(), use_logical_size=use_logical_size, verbose=verbose)

def resolvePedAnimBoneId(bone: BoneAnim) -> Tuple[Optional[int], str]:
    if bone.direct_bone_id is not None:
        return int(bone.direct_bone_id), "direct-id"
    if int(bone.hash16) in PED_ANIM_HASH16_TO_DIRECT_ID:
        return int(PED_ANIM_HASH16_TO_DIRECT_ID[int(bone.hash16)]), "hash16-ped-id bridge"
    return None, "unresolved"

def formatAnimBoneTarget(bone: BoneAnim) -> str:
    direct_id, reason = resolvePedAnimBoneId(bone)
    if direct_id is not None and bone.direct_bone_id is None:
        return f"key:0x{bone.bone_key:08X} hash16:0x{bone.hash16:04X} -> id:{direct_id} ({reason})"
    return bone.targetLabel()

def interpolateFloat(a: float, b: float, factor: float) -> float:
    return float(a) + (float(b) - float(a)) * float(factor)

def interpolateTuple3(a: Sequence[float], b: Sequence[float], factor: float) -> Tuple[float, float, float]:
    return (
        interpolateFloat(a[0], b[0], factor),
        interpolateFloat(a[1], b[1], factor),
        interpolateFloat(a[2], b[2], factor),
    )

def normalizeRotationXyzw(rotation_xyzw: Sequence[float]) -> Tuple[float, float, float, float]:
    x = float(rotation_xyzw[0])
    y = float(rotation_xyzw[1])
    z = float(rotation_xyzw[2])
    w = float(rotation_xyzw[3])
    magnitude = math.sqrt(x * x + y * y + z * z + w * w)
    if not math.isfinite(magnitude) or magnitude <= 0.000001:
        return 0.0, 0.0, 0.0, 1.0
    inv_magnitude = 1.0 / magnitude
    return x * inv_magnitude, y * inv_magnitude, z * inv_magnitude, w * inv_magnitude

def interpolateRotationXyzw(a: Sequence[float], b: Sequence[float], factor: float) -> Tuple[float, float, float, float]:
    ax, ay, az, aw = normalizeRotationXyzw(a)
    bx, by, bz, bw = normalizeRotationXyzw(b)
    factor = max(0.0, min(1.0, float(factor)))
    dot = ax * bx + ay * by + az * bz + aw * bw

    if dot < 0.0:
        bx = -bx
        by = -by
        bz = -bz
        bw = -bw
        dot = -dot

    if dot > 0.9995:
        return normalizeRotationXyzw((
            interpolateFloat(ax, bx, factor),
            interpolateFloat(ay, by, factor),
            interpolateFloat(az, bz, factor),
            interpolateFloat(aw, bw, factor),
        ))

    theta_0 = math.acos(max(-1.0, min(1.0, dot)))
    sin_theta_0 = math.sin(theta_0)
    if abs(sin_theta_0) <= 0.000001:
        return ax, ay, az, aw

    theta = theta_0 * factor
    sin_theta = math.sin(theta)
    scale_a = math.cos(theta) - dot * sin_theta / sin_theta_0
    scale_b = sin_theta / sin_theta_0

    return normalizeRotationXyzw((
        ax * scale_a + bx * scale_b,
        ay * scale_a + by * scale_b,
        az * scale_a + bz * scale_b,
        aw * scale_a + bw * scale_b,
    ))

def sampleBoneAnimFrameAtTime(bone: BoneAnim, time_value: float) -> Optional[AnimFrame]:
    frames = list(getattr(bone, "frames", []) or [])
    if not frames:
        return None

    time_value = float(time_value)
    if time_value <= float(frames[0].absolute_time) + 0.000001:
        first = frames[0]
        return AnimFrame(
            rotation_xyzw=tuple(first.rotation_xyzw),
            delta_time=0.0,
            absolute_time=time_value,
            translation_xyz=tuple(first.translation_xyz),
            scale_xyz=tuple(first.scale_xyz),
        )
    if time_value >= float(frames[-1].absolute_time) - 0.000001:
        last = frames[-1]
        return AnimFrame(
            rotation_xyzw=tuple(last.rotation_xyzw),
            delta_time=0.0,
            absolute_time=time_value,
            translation_xyz=tuple(last.translation_xyz),
            scale_xyz=tuple(last.scale_xyz),
        )

    prev_frame = frames[0]
    for next_frame in frames[1:]:
        if time_value <= float(next_frame.absolute_time) + 0.000001:
            span = float(next_frame.absolute_time) - float(prev_frame.absolute_time)
            if abs(span) <= 0.000001:
                factor = 0.0
            else:
                factor = (time_value - float(prev_frame.absolute_time)) / span
            factor = max(0.0, min(1.0, factor))
            return AnimFrame(
                rotation_xyzw=interpolateRotationXyzw(prev_frame.rotation_xyzw, next_frame.rotation_xyzw, factor),
                delta_time=0.0,
                absolute_time=time_value,
                translation_xyz=interpolateTuple3(prev_frame.translation_xyz, next_frame.translation_xyz, factor),
                scale_xyz=interpolateTuple3(prev_frame.scale_xyz, next_frame.scale_xyz, factor),
            )
        prev_frame = next_frame

    return frames[-1]

def buildAnimationTimeline(entry: AnimEntry, max_key_times: int = 512) -> List[float]:
    times = {0.0, max(0.0, float(entry.total_time))}
    for bone in entry.bones:
        for anim_frame in bone.frames:
            value = float(anim_frame.absolute_time)
            if math.isfinite(value) and value >= 0.0:
                times.add(round(value, 6))
    ordered = sorted(times)
    if len(ordered) <= int(max_key_times):
        return ordered

    if int(max_key_times) < 2:
        return ordered[:1]
    step = (len(ordered) - 1) / float(int(max_key_times) - 1)
    thinned = []
    for index in range(int(max_key_times)):
        source_index = int(round(float(index) * step))
        source_index = max(0, min(len(ordered) - 1, source_index))
        thinned.append(ordered[source_index])
    return sorted(set(thinned))
