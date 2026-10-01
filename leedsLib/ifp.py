# BLeeds - Scripts for working with R* Leeds (GTA Stories, Chinatown Wars, Manhunt 2, etc) formats in Blender
# Author: spicybung
# Years: 2025 - 2026
# SPDX-License-Identifier: GPL-3.0-or-later

"""Manhunt ANCT/SEQU/SEQT IFP parser.

BLeeds 1.2.0 keeps Manhunt IFP separate from GTA Stories ``.anim`` files.
The parser is intentionally independent from Blender so files can be validated
outside Blender and before any rig is modified.

Manhunt 2 SEQT quaternions are stored as signed int16 XYZW values originating
from 3ds Max row-vector local transforms.  The parser preserves those source
values; Blender-space conversion is performed by ``ops.ifp_importer``.
"""

import io
import math
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


class ManhuntIfpReadError(ValueError):
    pass


@dataclass
class ManhuntIfpFrame:
    time: float
    rotation_xyzw: Tuple[float, float, float, float]
    translation_xyz: Tuple[float, float, float]


@dataclass
class ManhuntIfpTrack:
    bone_id: int
    frame_type: int
    sequence_flag: str
    start_time: int
    frames: List[ManhuntIfpFrame] = field(default_factory=list)
    initial_rotation_xyzw: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    last_frame_time: Optional[float] = None

    @property
    def has_rotation(self) -> bool:
        return True

    @property
    def has_translation(self) -> bool:
        return self.frame_type > 1


@dataclass
class ManhuntIfpAnimation:
    index: int
    block_name: str
    name: str
    chunk_size: int
    frame_times_count: float
    tracks: List[ManhuntIfpTrack] = field(default_factory=list)
    particle_header_size: int = 0
    particle_unknown: float = 0.0
    particle_entry_size: int = 0
    particle_entry_count: int = 0
    sequence_payload_bytes: int = 0
    chunk_size_matches: bool = True

    @property
    def total_time(self) -> float:
        maximum = 0.0
        for track in self.tracks:
            if track.frames:
                maximum = max(maximum, float(track.frames[-1].time))
            if track.last_frame_time is not None and math.isfinite(float(track.last_frame_time)):
                maximum = max(maximum, float(track.last_frame_time))
        return maximum


@dataclass
class ManhuntIfpBlock:
    name: str
    animations: List[ManhuntIfpAnimation] = field(default_factory=list)


@dataclass
class ManhuntIfpFile:
    game: str
    container: str
    blocks: List[ManhuntIfpBlock]
    animations: List[ManhuntIfpAnimation]
    compressed: bool = False
    compression_offset: int = 0
    source_size: int = 0
    decoded_size: int = 0

    def summaryText(self, include_tracks: bool = True, max_tracks_per_animation: int = 96) -> str:
        lines = [
            "Manhunt IFP: game={} container={} blocks={} animations={} compressed={} source_size={} decoded_size={}".format(
                self.game,
                self.container,
                len(self.blocks),
                len(self.animations),
                bool(self.compressed),
                int(self.source_size),
                int(self.decoded_size),
            )
        ]
        for animation in self.animations:
            lines.append(
                "[{0:03d}] {1} block={2!r} tracks={3} time={4:.6f} chunk={5} payload={6} chunk_match={7}".format(
                    animation.index,
                    animation.name,
                    animation.block_name,
                    len(animation.tracks),
                    animation.total_time,
                    animation.chunk_size,
                    animation.sequence_payload_bytes,
                    animation.chunk_size_matches,
                )
            )
            if include_tracks:
                for track in animation.tracks[:max_tracks_per_animation]:
                    first_time = track.frames[0].time if track.frames else 0.0
                    last_time = track.frames[-1].time if track.frames else 0.0
                    lines.append(
                        "    BoneID={0} {1} type={2} frames={3} start={4} time=({5:.6f},{6:.6f}) translation={7}".format(
                            track.bone_id,
                            track.sequence_flag,
                            track.frame_type,
                            len(track.frames),
                            track.start_time,
                            first_time,
                            last_time,
                            track.has_translation,
                        )
                    )
                if len(animation.tracks) > max_tracks_per_animation:
                    lines.append("    ... {} more tracks ...".format(len(animation.tracks) - max_tracks_per_animation))
        return "\n".join(lines)


def readExact(stream, size: int, label: str) -> bytes:
    data = stream.read(int(size))
    if len(data) != int(size):
        raise ManhuntIfpReadError(
            "{} is truncated at 0x{:X}: wanted {} byte(s), got {}".format(
                label, stream.tell() - len(data), size, len(data)
            )
        )
    return data


def readU32(stream) -> int:
    return struct.unpack("<I", readExact(stream, 4, "uint32"))[0]


def readU16(stream) -> int:
    return struct.unpack("<H", readExact(stream, 2, "uint16"))[0]


def readI16(stream) -> int:
    return struct.unpack("<h", readExact(stream, 2, "int16"))[0]


def readF32(stream) -> float:
    return struct.unpack("<f", readExact(stream, 4, "float32"))[0]


def readFourCC(stream) -> str:
    raw = readExact(stream, 4, "FourCC")
    return raw.decode("ascii", errors="replace")


def readSizedName(stream, label: str) -> str:
    length = readU32(stream)
    if length > 1024 * 1024:
        raise ManhuntIfpReadError("Unreasonable {} length {}".format(label, length))
    return readExact(stream, length, label).split(b"\x00", 1)[0].decode("latin1", errors="replace")


def normalizeSourceQuaternion(values) -> Tuple[float, float, float, float]:
    x, y, z, w = (float(value) / 4096.0 for value in values)
    magnitude = math.sqrt(x * x + y * y + z * z + w * w)
    if not math.isfinite(magnitude) or magnitude <= 0.000001:
        return (0.0, 0.0, 0.0, 1.0)
    inverse = 1.0 / magnitude
    return (x * inverse, y * inverse, z * inverse, w * inverse)


def readManhuntTrack(stream, expected_sequence: Optional[str] = None) -> ManhuntIfpTrack:
    sequence_offset = stream.tell()
    sequence_flag = readFourCC(stream)
    if sequence_flag not in ("SEQU", "SEQT"):
        raise ManhuntIfpReadError(
            "Expected SEQU/SEQT at 0x{:X}, got {!r}".format(sequence_offset, sequence_flag)
        )
    if expected_sequence and sequence_flag != expected_sequence:
        raise ManhuntIfpReadError(
            "Expected {} tracks, found {} at 0x{:X}".format(expected_sequence, sequence_flag, sequence_offset)
        )

    bone_id = readI16(stream)
    frame_type = struct.unpack("<B", readExact(stream, 1, "frame type"))[0]
    frame_count = readU16(stream)
    if frame_type not in (1, 2, 3):
        raise ManhuntIfpReadError(
            "Unsupported Manhunt frame type {} for BoneID {}".format(frame_type, bone_id)
        )
    if frame_count > 1_000_000:
        raise ManhuntIfpReadError(
            "Unreasonable frame count {} for BoneID {}".format(frame_count, bone_id)
        )

    start_time_offset = stream.tell()
    start_time = readU16(stream)
    if frame_type < 3 and start_time == 0:
        # For variable-time frame type 1/2, the zero we just read is the first
        # delta word, not a separate StartTime field.
        stream.seek(start_time_offset)
        start_time = 0

    initial_rotation = (0.0, 0.0, 0.0, 1.0)
    if frame_type > 2:
        initial_rotation = normalizeSourceQuaternion(tuple(readI16(stream) for _ in range(4)))

    frames: List[ManhuntIfpFrame] = []
    accumulated_ticks = 0
    for frame_index in range(frame_count):
        if start_time == 0:
            if frame_type == 3 and frame_index == 0:
                time_value = 0.0
            else:
                accumulated_ticks += readU16(stream)
                time_value = accumulated_ticks / 2048.0
        else:
            time_value = start_time / 2048.0 - 1.0 / 30.0 + frame_index / 30.0

        if frame_type < 3:
            rotation = normalizeSourceQuaternion(tuple(readI16(stream) for _ in range(4)))
        else:
            rotation = initial_rotation

        if frame_type > 1:
            translation = tuple(readI16(stream) / 2048.0 for _ in range(3))
        else:
            translation = (0.0, 0.0, 0.0)

        frames.append(
            ManhuntIfpFrame(
                time=float(time_value),
                rotation_xyzw=tuple(float(value) for value in rotation),
                translation_xyz=tuple(float(value) for value in translation),
            )
        )

    last_frame_time = readF32(stream) if sequence_flag == "SEQT" else None
    return ManhuntIfpTrack(
        bone_id=int(bone_id),
        frame_type=int(frame_type),
        sequence_flag=sequence_flag,
        start_time=int(start_time),
        frames=frames,
        initial_rotation_xyzw=initial_rotation,
        last_frame_time=last_frame_time,
    )


def readManhuntAnimation(stream, index: int, block_name: str, expected_sequence: Optional[str]) -> ManhuntIfpAnimation:
    tag_offset = stream.tell()
    tag = readFourCC(stream)
    if tag != "NAME":
        raise ManhuntIfpReadError(
            "Expected NAME at 0x{:X}, got {!r}".format(tag_offset, tag)
        )

    name = readSizedName(stream, "animation name")
    track_count = readU32(stream)
    chunk_size = readU32(stream)
    frame_times_count = readF32(stream)
    if track_count > 100_000:
        raise ManhuntIfpReadError(
            "Unreasonable track count {} in {!r}".format(track_count, name)
        )

    tracks_start = stream.tell()
    tracks = [readManhuntTrack(stream, expected_sequence=expected_sequence) for _ in range(track_count)]
    tracks_end = stream.tell()

    structural_bytes = 0
    for track in tracks:
        structural_bytes += 9
        if track.sequence_flag == "SEQT":
            structural_bytes += 4
    measured_payload_size = (tracks_end - tracks_start) - structural_bytes

    particle_header_size = readU32(stream)
    particle_unknown = readF32(stream)
    particle_entry_size = readU32(stream)
    particle_entry_count = readU32(stream)
    if particle_entry_count > 1_000_000:
        raise ManhuntIfpReadError(
            "Unreasonable particle-entry count {} in {!r}".format(particle_entry_count, name)
        )
    particle_bytes = int(particle_entry_size) * int(particle_entry_count)
    if particle_bytes > 512 * 1024 * 1024:
        raise ManhuntIfpReadError(
            "Unreasonable particle block size {} in {!r}".format(particle_bytes, name)
        )
    if particle_bytes:
        readExact(stream, particle_bytes, "particle/effect entries")

    return ManhuntIfpAnimation(
        index=int(index),
        block_name=block_name,
        name=name,
        chunk_size=int(chunk_size),
        frame_times_count=float(frame_times_count),
        tracks=tracks,
        particle_header_size=int(particle_header_size),
        particle_unknown=float(particle_unknown),
        particle_entry_size=int(particle_entry_size),
        particle_entry_count=int(particle_entry_count),
        sequence_payload_bytes=int(measured_payload_size),
        chunk_size_matches=int(chunk_size) == int(measured_payload_size),
    )


def decodeManhuntIfpBlob(raw: bytes):
    if raw.startswith(b"ANCT"):
        return raw, False, 0

    probe_offsets = (0, 4, 8, 12, 16, 20, 24, 32)
    for offset in probe_offsets:
        if offset >= len(raw):
            continue
        try:
            decoded = zlib.decompress(raw[offset:])
        except Exception:
            decoded = None
        if decoded and decoded.startswith(b"ANCT"):
            return decoded, True, offset

    # Some platform/archive variants place a short header before a zlib stream.
    # Search only the beginning so a random compressed payload inside a file is
    # not mistaken for the container itself.
    upper = min(len(raw) - 2, 128)
    for offset in range(max(0, upper)):
        cmf = raw[offset]
        flg = raw[offset + 1]
        if (cmf & 0x0F) != 8 or ((cmf << 8) + flg) % 31 != 0:
            continue
        try:
            decoded = zlib.decompress(raw[offset:])
        except Exception:
            continue
        if decoded.startswith(b"ANCT"):
            return decoded, True, offset

    raise ManhuntIfpReadError("File is not an ANCT Manhunt IFP and no supported zlib-wrapped ANCT stream was found")


def readManhuntIfpBytes(raw: bytes, expected_game: str = "AUTO") -> ManhuntIfpFile:
    decoded, compressed, compression_offset = decodeManhuntIfpBlob(raw)
    stream = io.BytesIO(decoded)
    if readFourCC(stream) != "ANCT":
        raise ManhuntIfpReadError("Decoded container does not start with ANCT")

    block_count = readU32(stream)
    if block_count > 100_000:
        raise ManhuntIfpReadError("Unreasonable BLOC count {}".format(block_count))

    requested = str(expected_game or "AUTO").strip().upper()
    expected_sequence = None
    if requested in ("MH1", "MANHUNT", "MANHUNT_1"):
        expected_sequence = "SEQU"
    elif requested in ("MH2", "MANHUNT_2"):
        expected_sequence = "SEQT"

    blocks: List[ManhuntIfpBlock] = []
    animations: List[ManhuntIfpAnimation] = []
    seen_sequences = set()
    for _ in range(block_count):
        tag_offset = stream.tell()
        tag = readFourCC(stream)
        if tag != "BLOC":
            raise ManhuntIfpReadError(
                "Expected BLOC at 0x{:X}, got {!r}".format(tag_offset, tag)
            )
        block_name = readSizedName(stream, "block name")
        anpk_offset = stream.tell()
        anpk = readFourCC(stream)
        if anpk != "ANPK":
            raise ManhuntIfpReadError(
                "Expected ANPK at 0x{:X}, got {!r}".format(anpk_offset, anpk)
            )
        animation_count = readU32(stream)
        if animation_count > 1_000_000:
            raise ManhuntIfpReadError(
                "Unreasonable animation count {} in block {!r}".format(animation_count, block_name)
            )
        block_animations = []
        for _animation_index in range(animation_count):
            animation = readManhuntAnimation(
                stream,
                index=len(animations),
                block_name=block_name,
                expected_sequence=expected_sequence,
            )
            for track in animation.tracks:
                seen_sequences.add(track.sequence_flag)
            block_animations.append(animation)
            animations.append(animation)
        blocks.append(ManhuntIfpBlock(name=block_name, animations=block_animations))

    if seen_sequences == {"SEQT"}:
        game = "MANHUNT_2"
    elif seen_sequences == {"SEQU"}:
        game = "MANHUNT_1"
    elif "SEQT" in seen_sequences:
        game = "MANHUNT_2"
    elif "SEQU" in seen_sequences:
        game = "MANHUNT_1"
    else:
        game = "MANHUNT"

    if expected_sequence and seen_sequences and seen_sequences != {expected_sequence}:
        raise ManhuntIfpReadError(
            "Requested {} but parsed sequence types {}".format(requested, sorted(seen_sequences))
        )

    return ManhuntIfpFile(
        game=game,
        container="ANCT",
        blocks=blocks,
        animations=animations,
        compressed=bool(compressed),
        compression_offset=int(compression_offset),
        source_size=len(raw),
        decoded_size=len(decoded),
    )


def readManhuntIfpFile(path, expected_game: str = "AUTO") -> ManhuntIfpFile:
    return readManhuntIfpBytes(Path(path).read_bytes(), expected_game=expected_game)
