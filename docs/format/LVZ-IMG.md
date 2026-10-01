# GTA Stories LVZ / IMG

## File Format

GTA Stories level streaming uses `.lvz` resource data together with `.img` data. The format treats the pair as related sources: LVZ supplies master resource/group information and embedded resource descriptions, while IMG supplies sector/model data referenced or matched by those structures.

Exact table relationships should be distinguished from fallback raw-data recovery. A resource ID is not considered globally interchangeable when different sectors contain conflicting data for the same numeric ID.

## LVZ Master Header Known Fields

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    CHAR    Signature            Master/container signature
0x04    4b    LONG    Type                 Container type
0x08    4b    Offset  Global0              Global pointer/field
0x0C    4b    Offset  Global1              Global pointer/field
0x10    4b    Offset  Global1Copy          Duplicate/related global field
0x14    4b    LONG    CountLike            Count-like master field
0x18    8b    BYTE    Unknown18            Preserved fixed-header bytes
0x20    4b    Offset  ResourceTable        Master resource-table address
```

The page names only fields consumed at fixed offsets by the documented structure. Higher-level meaning remains conservative where the executable-side member name has not been established.

## Embedded 32-byte Global Headers

Known files contain several relocatable header signatures when walking LVZ resources.

### WRLD preface (`DLRW`)

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    CHAR    Signature            "DLRW"
0x04    4b    LONG    WorldType            World/container type
0x08    4b    LONG    TotalSize            Declared section size
0x0C    4b    Offset  Global0              Global pointer/field
0x10    4b    Offset  Global1              Global pointer/field
0x14    4b    LONG    GlobalCount          Count field
0x18    4b    Offset  Continuation         Continuation pointer/field
```

### Texture preface (`xet\0`)

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    CHAR    Signature            "xet\0"
0x04    4b    LONG    HeaderSize           Header-size/type field
0x08    4b    LONG    TotalSize            Declared section size
0x0C    4b    Offset  Global0              Global pointer/field
0x10    4b    Offset  Global1              Global pointer/field
0x14    4b    LONG    GlobalCount          Count field
0x18    4b    Offset  Continuation         Continuation pointer/field
```

## Master Resource Table Row Layouts

Supported LVZ files use more than one row stride. Automatic platform detection can evaluate possible strides against the table boundary and the referenced data before choosing a layout.

### 8-byte row

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    Offset  ResourcePointer      Resource/descriptor pointer possible
0x04    4b    Offset  DataPointer          DMA/data pointer possible
```

### 12-byte row

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    Offset  ResourcePointer      Resource/descriptor pointer possible
0x04    4b    Offset  DataPointer          DMA/data pointer possible
0x08    4b    LONG    ResourceID           Resource identifier
```

The row is not accepted merely because both dwords are in range. Possible pointer targets are classified and scored against known resource forms and table boundaries.

## Resource Classification

During table traversal The table can identify supported targets such as:

```text
world/global header
texture resource
material-list / model-geometry resource
supported linked child/shared resource
invalid or unsupported resource
```

Classification is structural. A pointer that merely lands on non-zero bytes is not enough to identify a model.

## PS2 Material List Detection

The LVZ reader validates material-list possibles before scanning the following VIF stream. It considers the descriptor count, descriptor byte size, supported descriptor row lengths and whether a bounded VIF/UNPACK stream follows the list.

This prevents a resource-table cursor pointing at a small wrapper/header from being mistaken for the start of material descriptors.

## Geometry / DMA / VIF

Supported PS2 LVZ geometry is decoded as a bounded DMA/VIF stream using the same PS2 packet principles as Stories MDL geometry. The important boundary difference is that LVZ resource/table data determines where the packet may end.

The reader first establishes the descriptor/material region, then lets descriptor sizes and resource boundaries constrain the VIF scan. It does not scan indefinitely for an UNPACK opcode from an arbitrary resource pointer.

## IMG Sector and Placement Resolution

The format uses IMG data to recover models and placement rows associated with LVZ world sectors. Resolution is ordered so exact local relationships win over broader searches:

```text
1. LVZ master resource relationships
2. matching/same-sector IMG tables
3. exact resource records from linked/static map blocks
4. exact child/shared records
5. remaining raw IMG model data only for still-unresolved resource IDs
```

If the same resource ID maps to different model data in different sectors, The format keeps those entries sector-local. It does not use one conflicting resource as a global replacement.

## Placements

A reader keeps row/resource context when applying placements. Exact duplicate visible placement rows can be removed as an import optimization, but rows are not merged solely because they refer to the same resource ID.

Special passes such as `LIGHTS` are kept separate from ordinary visible mesh placement because light/effect resources can have different rendering/2DFX meanings.

## Texture Resources

When modifying an LVZ texture blob, the replacement raster should only be written when:

- a matching texture resource exists;
- the material/image is marked as writable/exportable;
- the source resource range is valid;
- the newly encoded raster has the exact required byte size for the existing range.

If these constraints are not met, the texture is skipped rather than resizing/repacking unrelated LVZ data.

## Validation and Conflict Handling

Validation should check or records:

- resource-table bounds and detected row stride;
- master resource count limits;
- possible pointer validity;
- first group/table boundary;
- supported embedded global signatures;
- material descriptor dimensions/row sizes;
- presence of a valid bounded PS2 VIF stream where expected;
- duplicate placements;
- resource IDs with conflicting sector-local geometry;
- unresolved placements after exact lookup passes;
- raw IMG recovery only for IDs still unresolved.

## Relationship to WRLD and MDL

LVZ can contain structures related to world and model rendering, but an embedded LVZ geometry payload is not documented as a standalone `.mdl`. Likewise, the appearance of a `DLRW` header inside LVZ identifies a world-style section, not proof that the entire LVZ file is a `.wrld` container.
