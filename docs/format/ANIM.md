# GTA Stories ANIM

## File Format

GTA Stories `.anim` stores skeletal animation data used by Liberty City Stories and Vice City Stories. The file is a relocatable container with an animation-offset table. Each animation points to a bone-track table; each bone track points to a variable-size sequence of half-float frame records.

The format treats title selection separately from the basic ANIM serialization because the core structure is shared while bone naming/ID interpretation can depend on the target game.

## Container Header

The reader requires at least `0x20` bytes.

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    CHAR    Signature            "mina"
0x04    4b    LONG    Unknown04            Preserved header field; meaning unresolved
0x08    4b    LONG    LogicalSize          Declared logical file length
0x0C    4b    Offset  RelocationTable      Relocation table file offset
0x10    4b    Offset  RelocationTableCopy  Second copy of relocation-table offset
0x14    4b    LONG    RelocationCount      Number of 32-bit relocation entries
0x18    8b    BYTE    Unknown18            Remaining fixed header bytes
```

`LogicalSize` is bounded against the physical file length. Structural validation should report the duplicated relocation-table fields when they disagree.

## Relocation Table

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
+0x00   4b    Offset  PointerFieldOffset   File offset of a relocatable pointer field
...     4b    Offset  ...                  RelocationCount entries
```

The relocation table is metadata for pointers in the serialized object graph. It is not the animation list itself.

## Animation Offset Table

The animation-offset table begins immediately after the fixed header at `0x20` in the supported files.

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
+0x00   4b    Offset  AnimationOffset      File offset of one animation record
...     4b    Offset  ...                  Additional animation offsets
```

Parsing stops on a zero entry or when the next possible fails structural bounds checks. This prevents arbitrary following data from being mistaken for another animation pointer.

## Animation Record

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    Offset  BoneTable            File offset of first bone-track record
0x04    24b   CHAR    Name                 Fixed-size ASCII animation name
0x1C    2b    SHORT   BoneCount            Number of bone-track records
0x1E    2b    SHORT   Unknown1E            Preserved 16-bit field
0x20    4b    FLOAT   TotalTime            Declared animation duration in seconds
```

Validation should verify that the bone table and all referenced frame arrays remain inside the parsed file range.

## Bone Track Record

Each record is `0x0C` bytes.

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    2b    SHORT   Flags                Track payload and bone-key interpretation flags
0x02    2b    SHORT   FrameCount           Number of frame records
0x04    4b    Offset  Frames               File offset of frame payload
0x08    4b    LONG    BoneKey              Direct bone ID or hash/key layout
```

### Track flags documented here

```text
Bit       Meaning
--------------------------------------------------------------------------
0x0001    Frame records contain rotation quaternion
0x0002    Frame records contain translation XYZ
0x0004    Frame records contain scale XYZ
0x0010    BoneKey contains a directly addressable bone-ID form
```

When `0x0010` is not present, The format keeps the full `BoneKey` and can resolve supported hash forms through the Stories bone table without discarding the original value.

## Variable Frame Record

Every frame begins with a half-float delta time. Optional fields are present according to the track flags.

```text
Order  Size  Type       Data                 Presence
--------------------------------------------------------------------------
1      8b    HALF4      RotationXYZW         if Flags & 0x0001
2      2b    HALF       DeltaTime            always
3      6b    HALF3      TranslationXYZ       if Flags & 0x0002
4      6b    HALF3      ScaleXYZ             if Flags & 0x0004
```

The byte stride is therefore:

```text
stride = 2
if rotation:    stride += 8
if translation: stride += 6
if scale:       stride += 6
```

Delta time accumulates `DeltaTime` to produce absolute key times. It checks quaternion, translation, scale and timing values for finite numeric results before constructing animation curves.

## Half-Float Encoding

ANIM uses IEEE-style 16-bit half floats for the supported frame components. The packed components expand them to 32-bit floats while preserving sign, denormal, infinity and NaN bit behavior sufficiently for validation. Non-finite transform components are rejected as malformed animation data.

## Bone Target Resolution

`BoneKey` is not reduced to a single assumed form. The format keeps:

```text
full 32-bit BoneKey
low 16 bits
hash16 interpretation
resolved direct bone ID where available
```

This is important because Stories files can be direct-ID keyed or hash keyed. Import logic resolves the target against the selected LCS/VCS skeleton rather than renaming the serialized key itself.

## Structural Validation

- `mina` signature is required.
- Every fixed and variable read is bounds checked.
- Declared logical size cannot expand reads beyond the physical file.
- Animation offset possibles must point into the valid file range.
- Bone/frame counts are bounded before allocation.
- Frame stride is derived from flags; tracks with no supported payload flags are reported.
- Delta times outside a practical range are reported.
- Non-finite rotations/translations/scales are rejected.
- Relocation table copies are compared.

## Relationship to IFP

Stories `.anim` is not the Manhunt `ANCT/BLOC/ANPK` IFP format. The format keeps the two parsers separate because their container structure, timing encoding, quaternion layout and track metadata differ.
