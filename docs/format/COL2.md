# GTA Stories COL2

## File Format

GTA Stories `.col2` contains Leeds collision resources. It is distinct from the RenderWare-era COL2 structure used by other GTA branches, so The format keeps a dedicated Stories parser and writer.

A file contains a relocatable-style top-level header, a resource table, and one or more collision-model headers. Each model header references compressed vertices, triangles, boxes and optional additional collision arrays.

## Container Header

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    CHAR    Signature            "2loc"
0x04    4b    LONG    Unknown04            Preserved header field
0x08    4b    LONG    FileSize             Declared file size; physical size used when zero
0x0C    4b    Offset  DirectoryOffset1     Mirrored directory/data-boundary field
0x10    4b    Offset  DirectoryOffset2     Second mirrored directory field
0x14    4b    LONG    EntryHint            Expected/initial resource-entry count hint
0x18    4b    LONG    Reserved0            Preserved unknown/reserved value
0x1C    4b    LONG    Reserved1            Preserved unknown/reserved value
```

`EntryHint` should not be assumed to be `EntryHint` is a hard table length. It walks valid rows until a recognized terminator/boundary and uses the hint as a structural check.

## Resource Table

The primary table begins at file offset `0x20`.

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    LONG    ResourceID           Collision resource identifier
0x04    4b    Offset  CollisionHeader      File offset of collision model header
```

Accepted terminators are:

```text
ResourceID = 0xFFFFFFFF, CollisionHeader = 0
ResourceID = 0,          CollisionHeader = 0
```

## Collision Model Header

The fixed header is `0x60` bytes.

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    16b   FLOAT4  BoundingSphere       Center XYZ and radius
0x10    16b   FLOAT4  BoundsMin            Minimum XYZ plus stored W
0x20    16b   FLOAT4  BoundsMax            Maximum XYZ plus stored W
0x30    2b    SHORT   SphereCount          Number of collision spheres
0x32    2b    SHORT   BoxCount             Number of collision boxes
0x34    2b    SHORT   TriangleCount        Number of triangle records
0x36    1b    BYTE    LineCount            Number of line records
0x37    1b    BYTE    TriangleSectionCount Number of triangle-section records
0x38    1b    BYTE    CollisionStoreID     Collision-store identifier
0x39    1b    BYTE    Unknown39            Preserved byte
0x3A    1b    BYTE    Unknown3A            Preserved byte
0x3B    1b    BYTE    Unknown3B            Preserved byte
0x3C    4b    Offset  Spheres              Sphere array
0x40    4b    Offset  Lines                Line array
0x44    4b    Offset  Boxes                Box array
0x48    4b    Offset  TriangleSections     Triangle-section array
0x4C    4b    Offset  Vertices             Compressed vertex array
0x50    4b    Offset  Triangles            Triangle array
0x54    4b    LONG    Unknown54            Preserved 32-bit field
0x58    4b    LONG    Padding0             Zero in observed generated files
0x5C    4b    LONG    Padding1             Zero in observed generated files
```

All array pointers are checked against the data boundary associated with the resource before the array is read.

## Compressed Vertex

Each collision vertex is three signed 16-bit components.

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    2b    SHORT   X                    Signed compressed X component
0x02    2b    SHORT   Y                    Signed compressed Y component
0x04    2b    SHORT   Z                    Signed compressed Z component
```

A parser expands the packed components into the coordinate scale expected by the Stories collision path.

## Triangle Record

Each triangle is `0x08` bytes.

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    2b    SHORT   VertexAOffset        Byte offset into the 6-byte vertex array
0x02    2b    SHORT   VertexBOffset        Byte offset into the 6-byte vertex array
0x04    2b    SHORT   VertexCOffset        Byte offset into the 6-byte vertex array
0x06    1b    BYTE    Surface              Surface/material ID byte
0x07    1b    BYTE    Padding              Preserved padding/unknown byte
```

The first three fields are **byte offsets**, not direct vertex indices. The byte offsets convert them to indices relative to the 6-byte compressed-vertex stride.

## Collision Box Record

The documented structure identifies box records through two FLOAT4 bounds vectors:

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    16b   FLOAT4  BoundsMin            Minimum XYZ + W
0x10    16b   FLOAT4  BoundsMax            Maximum XYZ + W
```

Box parsing stops when values are non-finite, minimum exceeds maximum, coordinates are structurally unreasonable, or the next record would cross the resource boundary. These checks prevent following data from being consumed as additional boxes when the stored count/pointer is damaged.

## Array Boundary Rules

The usable resource end is calculated the usable end of each collision resource from the surrounding container/table information. Every array reader receives that end explicitly. As a result, a bad `Triangles`, `Vertices` or `Boxes` pointer cannot legally read into the next resource even if a count is large.

## Structural Validation

- requires the Stories `2loc` signature;
- validates declared file size against available bytes;
- validates resource table rows and terminators;
- verifies each collision header fits entirely in its resource range;
- rejects non-finite sphere/bounds values;
- bounds counts and pointers before array allocation;
- verifies triangle byte offsets resolve to available compressed vertices;
- stops malformed box arrays using geometric and file-boundary checks;
- reports suspicious table lengths relative to `EntryHint`.

## Writer Notes

A COL2 writer emits the same dedicated Stories layout documented above. It does not write a RenderWare COL2 and does not relabel unknown header bytes merely to match names from another GTA branch.
