# GTA Stories WRLD

## File Format

GTA Stories `.wrld` is a world-resource container used by the Stories level system. It contains a header, a resource table and embedded resources that can include render geometry or texture-reference style entries.

A resource-table row identifies a serialized world resource. A resource-table row does **not** inherently identify that resource as a standalone `.mdl` and does not infer a runtime `CModelInfo` subclass from its presence in WRLD.

## Main Header

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    CHAR    Signature            Commonly "DLRW" in supported world data
0x04    4b    LONG    WorldType            Container/world type field
0x08    4b    LONG    TotalSize            Declared logical container size
0x0C    4b    Offset  Global0              Global pointer/boundary field
0x10    4b    Offset  Global1              Second global pointer field
0x14    4b    LONG    GlobalCount          Global/count field
0x18    4b    Offset  Continuation         Continuation pointer/field
0x1C    4b    LONG    Reserved             Preserved unknown/reserved value
```

The header is interpreted as a relocatable/world container header. `Global0`, `Global1` and `Continuation` are kept as structural values where the exact engine-side class member has not been established.

## Extended Header

```text
Offset  Size  Type       Data                 Description
--------------------------------------------------------------------------
0x20    4b    Offset     ResourceTable        File offset of resource rows
0x24    2b    SHORT      ResourceCount        Number of resource-table rows
0x26    2b    SHORT      UnknownCount         Preserved 16-bit count/field
0x28    32b   Offset[8]  SkyOffsets           Eight world/sky-related offsets
```

The eight `SkyOffsets` are documented as an offset array because their exact per-slot engine names are not yet established consistently enough for stronger labels.

## Resource Table

Each row is `0x08` bytes.

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    LONG    ResourceID           Resource identifier used by the world container
0x04    4b    Offset  ResourceOffset       File offset of embedded resource payload
```

### Resource extent

WRLD does not need to store an explicit length in each row. Resource payload lengths can be derived by sorting valid resource offsets and using:

```text
next valid ResourceOffset - current ResourceOffset
```

For the final resource, the applicable declared/physical container boundary is used.

This means duplicate or descending offsets are significant structural problems and are reported.

## Embedded Resource Classification

The first bytes of a payload are retained before classification:

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    2b    SHORT   A16                  First 16-bit value
0x02    2b    SHORT   B16                  Second 16-bit value
0x00    4b    LONG    A32                  First 32-bit value over same bytes
0x04    4b    LONG    B32                  Second 32-bit value
```

The currently established structural distinction is:

```text
B16 == 0 and A16 != 0  -> texture-reference style resource
otherwise              -> embedded render-resource possible
```

The second class is intentionally named **render-resource possible** rather than MDL. Related geometry structures can appear in several Leeds containers without making the payload a standalone `.mdl` file.

## Geometry Resources

For supported render resources, Supported render resources contain bounded PS2 geometry streams and keeps the following information associated with each resource:

```text
resource-table index
ResourceID
ResourceOffset
computed resource length
computed resource end
decoded geometry collection
material association
source world container
```

Geometry decoding is constrained to the resource's calculated byte range so a malformed packet cannot consume the next WRLD resource.

## Resource Organization

A reader groups data by serialization rather than by guessed runtime type:

```text
<world> [World Level]
  <world> Render Resources
    <world> Resource NNN [ID ...]
      <world> Resource NNN Geometry
  <world> Collision / Auxiliary
```

Each resource can be identified by its resource index, resource ID, start/end offsets and derived length. These values provide a stable link back to the corresponding WRLD table row.

## Structural Validation

Structural validation should report:

- declared `TotalSize` disagreeing with usable file length;
- a truncated header or extended header;
- a resource table that extends beyond the file;
- resource offsets outside the file;
- payloads that would extend past EOF/container boundary;
- duplicate/aliased resource offsets;
- invalid derived resource ranges;
- geometry packet reads that cross the resource boundary.

Validation messages use the `wrld-validation` category so container errors can be separated from geometry/VIF decoding errors.

## Relationship to LVZ / IMG

WRLD and LVZ/IMG share parts of the Stories resource ecosystem, but they are not documented as the same file format. LVZ has its own master resource/group tables and can refer to data continued in IMG. WRLD is documented here only for the structures present in the `.wrld` container itself.
