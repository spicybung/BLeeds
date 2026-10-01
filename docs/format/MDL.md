# GTA Stories MDL

## File Format

GTA Stories `.mdl` is a relocatable Leeds model container used by **Liberty City Stories** and **Vice City Stories**. Known files contain multiple serialized MDL layouts: PS2 Atomic/simple resources, PS2 Clump/ped/actor resources, and PSP geometry paths.

An MDL contains more than mesh vertices. Depending on the serialized layout it can contain relocation information, Atomic/Clump links, frame hierarchy records, geometry descriptors, materials, texture-name references, skin/hierarchy data, and platform-specific geometry streams.

The following concepts must remain separate:

```text
serialized MDL layout
        !=
model usage (world prop, ped, actor, cutscene object, vehicle, etc.)
        !=
runtime CBaseModelInfo subclass
```

A cutscene model is therefore not automatically a unique MDL class, and an Atomic-form file is not automatically proof of one particular runtime `CBaseModelInfo` subclass.

## Endianness and Addressing

- Header integers and pointers are little-endian.
- MDL pointers used by the supported Stories layouts are file-relative offsets after relocation preprocessing.
- The logical file length can be smaller than the physical file because PS2 resources can be sector padded.
- Readers should bound pointer reads against the logical/physical file range and does not treat trailing sector padding as another structure.

## Common Relocatable Container Header Prefix

The first `0x20` bytes are shared by the currently supported Stories MDL layouts.

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    CHAR    Signature            "ldm\0"; little-endian form of MDL marker
0x04    4b    LONG    Reserved             Shrink/reserved field used by the relocatable container
0x08    4b    LONG    FileLength           Logical MDL length before optional sector padding
0x0C    4b    Offset  LocalTable           Local relocation/root-table field
0x10    4b    Offset  GlobalTable          File offset of relocation pointer-field list
0x14    4b    LONG    RelocationCount      Number of relocation entries in GlobalTable
0x18    4b    Offset  Pointer2             Layout-dependent pointer field
0x1C    4b    LONG    AllocatedMemory      Engine allocation/version-related field
```

### Relocation table

`GlobalTable` addresses an array of 32-bit file offsets. Each entry identifies a pointer field that belongs to the relocatable object graph.

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
+0x00   4b    Offset  PointerFieldOffset   File offset of one relocatable pointer field
...     4b    Offset  ...                  RelocationCount entries
```

The format treats the table as relocation metadata, not as a model/object table. Invalid relocation entries are rejected rather than followed as object pointers.

## PS2 Simple / Prop Container Header

The one known PS2 simple/prop layout uses a `0x24`-byte top-level header.

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    CHAR    Signature            "ldm\0"
0x04    4b    LONG    Reserved             Reserved/shrink field
0x08    4b    LONG    FileLength           Logical MDL size
0x0C    4b    Offset  LocalTable           Local relocation/string-table-related field
0x10    4b    Offset  GlobalTable          Relocation pointer-field list
0x14    4b    LONG    RelocationCount      Number of entries in GlobalTable
0x18    4b    Offset  PointerBeforeTexture Layout-dependent pointer preceding final texture relocation
0x1C    4b    LONG    AllocatedMemory      Engine allocation field
0x20    4b    Offset  TopLevelAtomic       File offset of top-level Atomic-form model record
```

The one known PS2 simple layout lays the resource out in this broad order:

```text
MDL relocatable header
helper / secondary Atomic data
identity matrices / transform data
primary Atomic/simple model node
texture-name pointer data
geometry preamble
Leeds global geometry header
part descriptors / material information
DMA/VIF geometry stream
relocation table and referenced strings as required by the writer
```

This is one observed serialized ordering. Pointer/relocation fields remain controlling when traversing arbitrary files.

## PS2 Clump / Ped / Actor Container Header

The current PS2 clump/ped writer uses a `0x34`-byte top-level header.

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    CHAR    Signature            "ldm\0"
0x04    4b    LONG    Reserved             Reserved/shrink field
0x08    4b    LONG    FileLength           Logical MDL size
0x0C    4b    Offset  LocalTable           Local relocation/root field
0x10    4b    Offset  GlobalTable          Relocation pointer-field list
0x14    4b    LONG    RelocationCount      Number of relocation pointer fields
0x18    4b    Offset  Pointer2             Mirrors LocalTable in current PED exports
0x1C    4b    LONG    AllocatedMemory      Engine allocation field
0x20    4b    Offset  StructureOrFlags     Clump/ped layout pointer slot; exact engine name unresolved
0x24    4b    Offset  TopLevelClump        File offset of top-level Clump record
0x28    4b    Offset  ExtraPointer0        Source-driven helper/material pointer
0x2C    4b    Offset  ExtraPointer1        Source-driven helper/material pointer
0x30    4b    Offset  ExtraPointer2        Source-driven helper/material pointer
```

The extra pointer slots are preserved as structural fields. They are not renamed to specific engine classes until their target meanings are established across both Stories titles.

## Atomic Record

The structure contains the supported Atomic record as a fixed prefix beginning at the Atomic address. The linked-list node begins at `Atomic + 0x1C`.

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    LONG    SectionTypeID        Top-level/Atomic section identifier
0x04    4b    Offset  Frame                Frame record used by this Atomic
0x08    4b    Offset  FrameCycleNext       Next link in frame-associated list
0x0C    4b    Offset  FrameCyclePrev       Previous link in frame-associated list
0x10    4b    LONG    Unknown10            Unknown Atomic field
0x14    4b    Offset  Geometry             Geometry object/descriptor
0x18    4b    Offset  Clump                Owning Clump, zero where layout does not use one
0x1C    4b    Offset  ClumpCycleNext       Next Atomic-list link; points to list link, not record base
0x20    4b    Offset  ClumpCyclePrev       Previous Atomic-list link
0x24    4b    Offset  RenderCallback       Render callback/function-related field
0x28    2b    SHORT   ModelInfoID          Signed model-info-related ID stored by the resource
0x2A    2b    SHORT   VisibilityIDFlags    Visibility/ID flags field
0x2C    4b    Offset  Hierarchy            Skin/hierarchy pointer when present
0x30    4b    LONG    Tail                 Observed tail field; exact purpose unresolved
```

### Atomic linked-list traversal

For Clump models, Traversal follows the Atomic list through the link at `+0x1C`. A non-zero link points to another **list-link field**, so the next Atomic base is calculated as:

```text
next_atomic_base = clump_cycle_next - 0x1C
```

This distinction matters: interpreting the list-link pointer as an Atomic base shifts every subsequent field by `0x1C` and produces invalid frame/geometry pointers.

## Top-level Atomic Section Identifiers

The following top-level identifiers have been observed for Atomic-form records:

```text
Value       Title / platform association   Serialized section
--------------------------------------------------------------------------
0x01050001  LCS                            Atomic form
0x01000001  LCS                            Atomic form
0x0004AA01  VCS                            Atomic form
0x0000AA01  VCS                            Atomic form
0x00041601  VCS PSP                        Atomic form
0x01F40400  VCS PSP                        Atomic form
```

These are **serialized section identifiers**, not `CBaseModelInfo` type IDs.

A PSP Clump identifier can be shared between Stories titles. The shared identifier therefore does not by itself select VCS bone metadata from that identifier alone. Explicit game selection and frame-name data are used where the serialized identifier is not title-unique.

## Frame / Hierarchy Records

Stories actor and ped models reference frame records containing local transforms and hierarchy links. The format exposes the following relationships from supported files:

```text
Frame
  local matrix
  child pointer
  sibling pointer
  parent/root relationship
  global/world matrix where supplied by the resource
  frame tag / bone-related fields
  frame name pointer where present
```

For the documented PS2 frame layout, important offsets include:

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x04    4b    Offset  ParentOrRootLink     Hierarchy relationship used during frame traversal
0x10    64b   MATRIX  LocalMatrix          4x4 local transform matrix
0x50    64b   MATRIX  GlobalMatrix         Imported global/world matrix when present and valid
0x90    4b    Offset  Child                Child frame link used by supported hierarchy path
0x94    4b    Offset  Sibling              Sibling frame link used by supported hierarchy path
0x98    4b    LONG    FrameTag             Frame/bone tag field on applicable title/layout
0x9C    4b    LONG    Field9C              Preserved hierarchy field; exact meaning unresolved
0xA0    4b    LONG    FieldA0              Preserved hierarchy field; exact meaning unresolved
0xA4    4b    Offset  Name                 Frame-name pointer in one supported layout
0xA8    4b    Offset  NameAlt              Alternate frame-name pointer in another supported layout
```

The `0xA4` versus `0xA8` name location is layout-dependent and must be selected according to the established title/platform layout rather than assumed globally.

## Leeds Global Geometry Header

The global PS2 geometry prefix precedes the part/strip stream used by the current decoder.

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    16b   FLOAT4  BoundingSphere       Sphere center XYZ and radius
0x10    4b    LONG    SizeMaterialPacked   Low 20 bits: geometry size; upper 12 bits: material count
0x14    4b    LONG    VertexSectionFlags   Geometry/vertex-section flags
0x18    2b    SHORT   TotalVertexCount     Total vertex count represented by the geometry
0x1A    2b    SHORT   FirstStripOffset     Relative offset to first strip/part stream
0x1C    12b   SHORT6  BoundingBox          Six signed 16-bit bounding values
```

### Packed size/material field

The packed field separates `SizeMaterialPacked` as:

```text
geometry_size  = SizeMaterialPacked & 0x000FFFFF
material_count = SizeMaterialPacked >> 20
```

The geometry-size component is used as a stream boundary; the material count controls material descriptor processing. Treating the full word as one byte count would overrun into following resource data.

## PS2 Geometry Parts

A decoded geometry can contain multiple parts. The structure preserves, per part:

```text
part source offset
material ID
bounding sphere
signed 16-bit bounds
geometry flags
UV scale
strip vertex-count hint
triangle-strip metadata
vertex positions
normals
UVs
vertex/loop colors
skin indices and weights where present
```

Part boundaries are derived from validated descriptors and DMA/VIF packet limits. They are not inferred solely from the first triangle count.

## Materials

The format keeps a Stories material descriptor with these established values:

```text
Data                 Description
--------------------------------------------------------------------------
Offset               Source material descriptor address
Texture              Referenced texture name
RGBA                 Packed material colour
Specular             Floating-point specular value
```

Texture identity is resolved from the resource's texture-name references. Material slots are kept separate from geometry part indices so that several strips/parts can refer to the same material.

## PS2 DMA / VIF Geometry Stream

PS2 vertex payloads are packetized DMA/VIF data, not a flat interleaved vertex buffer. The current decoder maintains VIF state across commands and handles the commands required by supported Stories geometry.

### VIF command word

```text
Bits       Data
--------------------------------------------------------------------------
0..15      Immediate value
16..23     NUM field (UNPACK uses PS2 NUM meanings)
24..30     Command
31         IRQ bit
```

### VIF State Required by the Geometry Stream

```text
Command / family   Purpose in current decoder
--------------------------------------------------------------------------
STCYCL              Sets write/cycle lengths for subsequent UNPACK writes
STMOD               Sets VIF unpack arithmetic mode
STMASK              Supplies per-lane mask selectors
STROW               Supplies ROW replacement/addition values
STCOL               Supplies COL replacement values
UNPACK 0x60..0x7F   Writes decoded vector data to emulated VU memory
0x77                 Reserved/masked V3-style path used by Stories packets; consumes no source payload
MSCAL-family         Marks execution boundary used by the packet/geometry path
```

UNPACK interpretation depends on destination QW address, vector component format, signed/unsigned conversion, VIF cycle state, masks, ROW/COL state, and the V3-16/V3-8 source-alignment behavior of the PS2 VIF unit.

### Ped / Skin Strip Packet Prefix

Supported PED DMA/VIF strips contain a state/setup sequence before the vertex vectors. Validation should check important words rather than accepting any byte stream as vertex data.

```text
Relative  Size  Data                         Description
--------------------------------------------------------------------------
+0x00     4b    0x6C018000                   Expected strip/setup marker
+0x04     4b    Zero                         Expected zero in validated PED path
+0x08     4b    Zero                         Expected zero in validated PED path
+0x0C     4b    Count0                       Strip vertex/source count in low byte
+0x10     4b    Count1/flags                 Matching count plus expected control bit
+0x14     4b    STMASK command               VIF mask command
+0x18     4b    0x40404040                   Initial mask value in validated path
+0x1C     4b    STROW command                VIF row command
+0x20     16b   ROW[4]                       Four row words
```

Later packet sections supply position, UV, normal and skin data through UNPACK commands. Validation should verify command class, vector count and expected destination/control values before treating them as a known PED packet.

## Triangle Strips

PS2 geometry is reconstructed from strip-order vertices. Strip winding alternates for each emitted triangle. Degenerate/ADC-controlled vertices are handled as strip state rather than being converted blindly into ordinary indexed triangles.

Per-strip serialized/derived metadata includes:

```text
base vertex index
vertex count
decoded DMA vertex count
source packet offset
VIF destination
ADC flags
VIF command summary
batch index
overlap vertex count
whether the strip continues a previous strip
skin indices / weights / raw skin words
```

Strip continuation and skin batching are significant because they affect correct triangle and skin reconstruction after the serialized strip stream is expanded.

## PSP Geometry

PSP Stories MDL geometry does not use the PS2 DMA/VIF geometry stream. After the material list, the geometry record contains 12 bytes preceding a fixed `0x48`-byte PSP geometry header, followed by one `0x30`-byte mesh record for each strip and then the packed vertex buffer.

The offsets below are relative to the start of the `0x48`-byte PSP geometry header.

### PSP Geometry Header (`0x48` bytes)

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    LONG    Size                 Size from this header through geometry data
0x04    4b    LONG    VertexType           Packed PSP vertex-format flags
0x08    4b    LONG    StripCount           Number of 0x30-byte mesh/strip records
0x0C    4b    LONG    Unknown0             Unknown
0x10    16b   FLOAT4  Bounds               Four floating-point bounds values
0x20    4b    FLOAT   ScaleX               Position scale X
0x24    4b    FLOAT   ScaleY               Position scale Y
0x28    4b    FLOAT   ScaleZ               Position scale Z
0x2C    4b    LONG    VertexCount          Total packed vertices in all strips
0x30    4b    FLOAT   PositionX            Position/bias X
0x34    4b    FLOAT   PositionY            Position/bias Y
0x38    4b    FLOAT   PositionZ            Position/bias Z
0x3C    4b    LONG    Unknown1             Unknown
0x40    4b    Offset  VertexDataOffset     Vertex buffer offset relative to this header
0x44    4b    FLOAT   Unknown2             Unknown floating-point field
```

The vertex buffer begins at:

```text
vertex_buffer = psp_geometry_header + VertexDataOffset
geometry_end  = psp_geometry_header + Size
```

`VertexCount * VertexStride` must fit between those two addresses. `StripCount` also gives the number of mesh records immediately following the header.

### PSP VertexType bit fields

`VertexType` determines which members are present in each packed vertex and how large they are.

```text
Bits    Mask       Data
--------------------------------------------------------------------------
0..1    0x000003   UV format
2..4    0x00001C   Colour format
5..6    0x000060   Normal format
7..8    0x000180   Position format
9..10   0x000600   Weight format
11..12  0x001800   Index format
14..16  0x01C000   Weight count minus one
```

Members are written in this order:

```text
weights -> UV -> colour -> normal -> position
```

Each member begins on a 2-byte boundary. The final vertex stride is also rounded to a 2-byte boundary.

Known member encodings are:

```text
Member      Format  Stored data
--------------------------------------------------------------------------
Weights     0       absent
Weights     1       U8 values, weight = value / 128.0
Weights     2       U16 values, weight = value / 32768.0
Weights     3       FLOAT values

UV          0       absent
UV          1       2 x U8
UV          2       2 x 16-bit values
UV          3       2 x FLOAT

Colour      0       absent
Colour      4       16-bit packed colour
Colour      5       RGBA5551
Colour      6       16-bit packed colour
Colour      7       32-bit packed colour

Normal      0       absent
Normal      1       3 x S8
Normal      2       3 x S16
Normal      3       3 x FLOAT

Position    1       3 x S8
Position    2       3 x S16
Position    3       3 x FLOAT
```

Stories files currently known to use this path include VertexType values `0x120`, `0x121`, `0x115`, `0x114`, `0x0A1`, and `0x1C321`. These values are complete packed vertex declarations, not MDL type IDs.

### PSP Mesh / Strip Record (`0x30` bytes)

One record is present for each strip declared by `StripCount`.

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    Offset  VertexOffset         Byte offset into the geometry vertex buffer
0x04    2b    SHORT   TriangleCount        Triangle count for this strip
0x06    2b    SHORT   MaterialID           Material index
0x08    4b    FLOAT   Unknown0             Unknown
0x0C    4b    FLOAT   UVScaleU             U scale used by this strip
0x10    4b    FLOAT   UVScaleV             V scale used by this strip
0x14    16b   FLOAT4  Unknown1             Four unknown floating-point values
0x24    4b    FLOAT   Unknown2             Unknown
0x28    8b    BYTE8   BoneMap              Eight local skin-palette bone indices
```

A strip contains `TriangleCount + 2` vertices. Its packed vertex bytes therefore occupy:

```text
VertexOffset .. VertexOffset + (TriangleCount + 2) * VertexStride
```

The sum of `TriangleCount + 2` across all mesh records should equal the geometry header's `VertexCount`.

### PSP skin data

When weights are present, the vertex contains only weight values. The corresponding bone numbers come from the mesh record's eight-byte `BoneMap`. Weight slot 0 uses `BoneMap[0]`, slot 1 uses `BoneMap[1]`, and so on. Zero weights are ignored; remaining weights may be normalized after decoding.

The bone map belongs to the individual mesh/strip. It is not a file-wide bone table.

### PSP triangle strips

PSP mesh records describe triangle strips rather than independent triangle triplets. For a strip containing vertices `v0, v1, v2, v3...`, triangle winding alternates as the strip advances. Degenerate triangles must be discarded without destroying the strip sequence.

## LCS and VCS identifiers

Title-specific identifiers may distinguish LCS from VCS, but an identifier shared by both games cannot do so by itself. Shared PSP Clump data must therefore be interpreted together with other title-specific data in the file or with the known source title. Bone-name tables are game data, not part of the PSP geometry header described above.

## Runtime Model-Info Note

The Stories executable can reference serialized resources through different runtime model-info subclasses. Known runtime classes include `CSimpleModelInfo`, `CTimeModelInfo`, `CWeaponModelInfo`, `CPedModelInfo` and `CVehicleModelInfo`, but those names do not define the complete MDL byte layout.

For example:

```text
simple/prop serialized MDL  ---> may be consumed through simple-model runtime metadata
actor/ped serialized MDL    ---> may be consumed through ped/clump-oriented runtime metadata
cutscene usage              ---> describes use, not a unique serialized class
```

Serialized layout, game/platform and usage should be recorded separately. serialized layout, game/platform and usage separately.

## Structural Validation

A reader rejects or reports structural problems including:

- bad or unsupported MDL signature;
- logical file size outside the physical file;
- pointer/structure reads outside the logical file;
- invalid Atomic addresses;
- unsupported top-level section identifiers;
- malformed Atomic linked-list traversal;
- inconsistent title-specific identifiers;
- invalid geometry size/material packing;
- malformed or truncated DMA/VIF streams;
- unsupported VIF command payload lengths;
- inconsistent PED strip setup/count fields;
- invalid hierarchy/frame pointers;
- non-finite decoded transform or geometry values.

## Unresolved Fields

Several fields remain deliberately named `Unknown`, `Reserved`, `StructureOrFlags`, or `ExtraPointerN`. Those names should only be tightened when the same meaning is demonstrated across representative LCS and VCS files or from corresponding executable code. The documentation must not promote a one-file observation into a universal format rule.


## Prototype PSP MDL variant

Some early Liberty City Stories assets retain the `ldm\0` Leeds container while using a PSP-oriented geometry payload and an older LCS top-level identifier. BLeeds treats this as a serialized-format variant rather than as a separate file extension. Import remains automatic.

A prototype sample is recognized structurally by the relocatable Leeds header, the `0x00010000` allocation field at offset `0x1C`, a valid top-level pointer at `0x20`, and a PSP vertex-format block found inside the logical file length. The legacy LCS Atomic identifiers `0x01050001` / `0x01000001` therefore do not by themselves imply PS2 geometry.

The prototype PSP geometry reader does not assume that the retail material wrapper precedes the vertex-format header. It locates and validates the PSP geometry header directly, then decodes the payload with the same PSP vertex-format rules used by later Stories assets.
