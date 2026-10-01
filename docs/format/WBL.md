# Chinatown Wars WBL

## File Format

The format uses `.wbl` for Chinatown Wars world-block data. The documented structure knows several recurring binary structures, especially the Leeds fixed-point transform, but the complete WBL object graph is still being mapped.

This page therefore distinguishes the structures that are actually fixed in code from higher-level WBL sections whose field meanings are not yet stable enough to publish as a finished binary description.

## Numeric Conventions

The current Chinatown Wars reader uses little-endian signed integers and a fixed-point scale of `4096` for transforms.

```text
float_value = stored_integer / 4096.0
```

## Leeds CW Transform

The transform is exactly `0x20` bytes in the documented structure.

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    2b    SHORT   RightX               Basis vector component /4096
0x02    2b    SHORT   RightY               Basis vector component /4096
0x04    2b    SHORT   RightZ               Basis vector component /4096
0x06    2b    SHORT   TopX                 Basis vector component /4096
0x08    2b    SHORT   TopY                 Basis vector component /4096
0x0A    2b    SHORT   TopZ                 Basis vector component /4096
0x0C    2b    SHORT   AtX                  Basis vector component /4096
0x0E    2b    SHORT   AtY                  Basis vector component /4096
0x10    2b    SHORT   AtZ                  Basis vector component /4096
0x12    2b    SHORT   Padding              Preserved padding/unknown value
0x14    4b    LONG    PositionX            Signed fixed-point position /4096
0x18    4b    LONG    PositionY            Signed fixed-point position /4096
0x1C    4b    LONG    PositionZ            Signed fixed-point position /4096
```

The first nine values form the three orientation basis vectors. Position uses 32-bit components so world coordinates have greater range than the 16-bit orientation values.

## Triangle Strips

Triangle strips are reconstructed by emitting one triangle for each three-vertex window and alternating winding:

```text
triangle 0: v0, v1, v2
triangle 1: v1, v3, v2  (reversed winding)
triangle 2: v2, v3, v4
...
```

Degenerate index triples are skipped. The alternating winding is part of triangle-strip topology and must not be replaced by a constant `(i, i+1, i+2)` order.

## Material / Texture IDs

Serialized texture IDs identify material/texture references. Names such as `texture<ID>` are external naming conventions and are not stored literally by the format.

External raster files may be associated with these numeric texture IDs by surrounding game/tool data; such filenames are not part of the WBL serialization.

## Current Documentation Boundary

The broader WBL parser still contains structures that are recognized through traversal and consistency checks but whose complete field names have not been proven. Those structures remain undocumented here rather than receiving guessed C++-style names.

When additional WBL structures become stable, they should be added using the same format as the transform above:

1. exact structure base and size;
2. fixed field offsets;
3. numeric encoding;
4. pointer/index interpretation;
5. traversal rule;
6. validation rule;
7. unresolved bytes explicitly marked `Unknown`.

This page should not be expanded by copying Stories WRLD or MDL names into Chinatown Wars data merely because two structures perform a similar high-level job.
