# Manhunt IFP / ANCT

## File Format

Known files use the Manhunt animation-library format built from `ANCT`, `BLOC`, `ANPK`, `NAME`, `SEQU` and `SEQT` tagged records. Manhunt 1 and Manhunt 2 share the outer container family but use different sequence tags and frame details.

Some files are zlib wrapped. A short wrapper prefix can precede the supported short wrapper prefix, decompresses the stream, and then validates the decoded data as `ANCT` before any animation is imported.

## Container Hierarchy

```text
ANCT
  BLOC
    block name
    ANPK
      animation count / package metadata
      NAME
        animation metadata
        SEQU or SEQT track
        SEQU or SEQT track
        ...
```

The format is tag-driven. Offsets below are therefore relative to the beginning of each tagged record, not one universal file structure.

## Tags

```text
Tag   Meaning
--------------------------------------------------------------------------
ANCT  Top-level Manhunt animation container
BLOC  Named animation block
ANPK  Animation package within a block
NAME  Animation name and animation-level metadata
SEQU  Manhunt 1 sequence/track record
SEQT  Manhunt 2 sequence/track record
```

The title can be distinguished the Manhunt title from the sequence tag actually present. It does not treat `SEQU` and `SEQT` as interchangeable labels.

## Sized Names

Container/block/animation names use a 32-bit length followed by that many bytes.

```text
Offset  Size       Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b         LONG    Length               Number of bytes that follow
0x04    Length     CHAR    Name                 Name bytes; text stops at first NUL
```

Unreasonably large lengths are rejected before allocation.

## Animation Metadata after NAME

After the `NAME` tag and sized animation name, The structure contains:

```text
Order  Size  Type    Data                 Description
--------------------------------------------------------------------------
1      4b    LONG    TrackCount           Number of sequence records
2      4b    LONG    ChunkSize            Declared sequence payload/chunk size
3      4b    FLOAT   FrameTimesCount      Animation timing/count-related float
```

After all tracks, a parser reads particle-related animation tail fields and compares the measured sequence payload against the declared chunk size.

## SEQU / SEQT Track Prefix

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    CHAR    SequenceTag          "SEQU" or "SEQT"
0x04    2b    SHORT   BoneID               Signed bone identifier
0x06    1b    BYTE    FrameType            Supported values 1, 2 or 3
0x07    2b    SHORT   FrameCount           Number of keyframes
0x09    ...   ...     Timing/frames         Layout depends on FrameType
```

The structure after `FrameCount` is variable because `StartTime` can act either as an explicit fixed-time field or as the first delta word in the variable-time path.

## Timing Modes

Two timing forms are known: two timing forms:

```text
StartTime == 0
  Each applicable frame supplies a uint16 delta tick value.
  Ticks accumulate and are converted with: seconds = ticks / 2048.0

StartTime != 0
  Frames are treated as 30 Hz keys starting from:
  StartTime / 2048.0 - 1/30 second
```

For frame types 1/2, a zero word where `StartTime` would be read is rewound and interpreted as the first variable-time delta word.

## FrameType Payloads

```text
FrameType  Rotation                       Translation
--------------------------------------------------------------------------
1          Per-frame int16 XYZW          None
2          Per-frame int16 XYZW          Per-frame int16 XYZ
3          One initial int16 XYZW        Per-frame int16 XYZ
```

Quaternion components are divided by `4096.0` and normalized. Translation components are divided by `2048.0`.

For FrameType 3, the initial quaternion is stored once before the frame loop and reused for all frames in the track.

## SEQT Tail

Manhunt 2 `SEQT` includes an additional 32-bit floating-point `LastFrameTime` after the frame payload. `SEQU` does not use this tail in the current parser.

## Coordinate-System Handling

Quaternion and translation values are serialized in the game coordinate basis. Any conversion to another coordinate system is outside the binary format itself.

## Structural Validation

- validates all FourCC tags at the position where they are required;
- bounds sized strings before reading them;
- restricts supported frame types to 1, 2 and 3;
- bounds track and frame counts;
- reads every primitive through exact-length helpers so truncated records fail at the correct byte offset;
- enforces `SEQU` versus `SEQT` consistency once the title/sequence type is established;
- compares measured sequence payload bytes with the animation `ChunkSize`;
- tracks compressed source size, compression offset and decoded size for zlib-wrapped files.

## Relationship to Stories ANIM

Manhunt IFP is a different binary format from Stories `.anim`. A parsers intentionally do not share record definitions: Stories ANIM uses relocatable pointer tables and half-float frame components, while Manhunt uses tagged chunks and signed fixed-point sequence components.
