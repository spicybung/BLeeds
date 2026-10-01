# Leeds XTX / CHK / TEX Texture Containers

## File Format

GTA Stories `.xtx` / `.chk` files are Leeds texture containers. The container stores linked texture entries. Each entry points to a platform-specific texture header, which in turn points to raster data.

PS2 and PSP use different texture-header layouts. The title can be distinguished the platform for the **container as a whole** when possible rather than independently choosing a platform for every texture.

Manhunt 2 `TCDT`/`Z2HM` TEX is a different serialized container and is documented separately at the end of this page.

## Leeds Texture Entry

The supported linked-list node occupies `0x50` bytes.

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    Offset  TextureHeader        Platform-specific texture header
0x04    4b    Offset  CollisionOrAux       Auxiliary pointer; exact meaning unresolved
0x08    4b    Offset  NextSlot             Next linked-list slot pointer
0x0C    4b    Offset  PreviousSlot         Previous linked-list slot pointer
0x10    64b   CHAR    Name                 Null-terminated ASCII texture name
```

### Slot-pointer convention

The linked-list value identifies the slot at node offset `+0x08`, not the beginning of the node. To recover the entry base:

```text
entry_base = slot_pointer - 0x08
```

This is why list validation checks node addresses and slot addresses separately.

## PSP Texture Header

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    LONG    Unknown0             Preserved PSP header field
0x04    4b    Offset  RasterData           Raster payload offset
0x08    2b    SHORT   SwizzleWidth         PSP swizzle-width field
0x0A    1b    BYTE    WidthPower           Width in pixels = 1 << WidthPower
0x0B    1b    BYTE    HeightPower          Height in pixels = 1 << HeightPower
0x0C    1b    BYTE    BitsPerPixel         Indexed/direct raster BPP value
0x0D    1b    BYTE    MipmapCount          Number of mip levels represented
0x0E    2b    SHORT   Tail                 Preserved header tail
```

The PSP path derives dimensions from powers rather than storing literal width and height.

## PS2 Texture Header

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    LONG    Reserved0            Preserved/unknown PS2 header field
0x04    4b    LONG    Reserved1            Preserved/unknown PS2 header field
0x08    4b    Offset  RasterData           Raster payload offset
0x0C    4b    LONG    Flags                Packed swizzle/mip/BPP/dimension fields
```

### Canonical PS2 packed flags

```text
Bits       Data
--------------------------------------------------------------------------
0..7       Swizzle field
8..11      Mipmap count
12..13     Unresolved bits
14..19     Bits per pixel
20..25     Height power; height = 1 << value
26..31     Width power; width = 1 << value
```

An alternate packing has also been observed in compatible files. It should be normalized to the same logical texture fields before raster decoding.

## PS2 / PSP distinction

PS2 and PSP texture headers are different structures. The platform should be known from the archive or game that supplied the texture container. If it is not known, the header fields can be checked against the file bounds and legal dimensions before decoding. A texture entry does not change platform independently of the container that contains it.

## Raster Data

The decoder handles the platform-specific operations required by supported files, including:

```text
PS2 swizzle/deswizzle
PSP swizzle/deswizzle
indexed palette/CLUT paths
supported direct-colour paths
mipmap metadata
alpha-range analysis
texture name preservation
```

Raster decoding is bounded by the next known data boundary/container size. A decoded image is not allowed to read through the following linked entry.

## Linked-List Validation

Validation should check:

- entry offsets are inside the file;
- texture-header and raster pointers are inside the file;
- `NextSlot` does not create a self-reference;
- linked-list cycles are detected;
- previous-slot relationships are internally consistent where present;
- names are non-empty and printable enough to be useful;
- `last_slot` agrees with the traversed final entry when the container supplies it;
- raster ranges are non-zero and do not exceed available bytes;
- width/height/BPP values are structurally valid for the selected platform.

## Container Forms

A raw Manhunt 2 texture container starts with `TCDT`. A `Z2HM` wrapper contains a zlib-compressed `TCDT` stream beginning after the wrapper prefix at `0x08`.

## TCDT Header

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    CHAR    Signature            "TCDT"
0x04    4b    LONG    Version              Expected value 1 in supported files
0x08    4b    LONG    FileSize             Declared decoded TCDT size
0x0C    4b    Offset  IndexTable           First index-table offset
0x10    4b    Offset  IndexTableCopy       Second index-table offset
0x14    4b    LONG    IndexCount           Number of index entries
0x18    4b    LONG    Zero1                Observed zero/reserved field
0x1C    4b    LONG    Zero2                Observed zero/reserved field
0x20    4b    LONG    TextureCount         Number of linked texture entries
0x24    4b    Offset  FirstTexture         First texture entry
0x28    4b    Offset  LastTexture          Last texture entry
0x2C    4b    LONG    Zero3                Observed zero/reserved field
```

## TCDT Texture Entry Known Fields

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    Offset  NextTexture          Next linked texture entry
0x08    32b   CHAR    Name                 Texture name
0x48    4b    LONG    Width                Width in pixels
0x4C    4b    LONG    Height               Height in pixels
0x50    4b    LONG    BitsPerPixel         Bits per pixel
0x54    4b    LONG    PitchOrLinearSize    DDS-style pitch/linear-size value
0x58    2b    SHORT   Flags                Texture flags
0x5C    1b    BYTE    MipmapCount          Mipmap count
0x60    4b    Offset  DataOffset           Texture payload offset
0x68    4b    LONG    DataSize             Texture payload length
```

The fields not listed between these offsets remain intentionally undocumented until their meanings are established by a parser or additional file analysis.
