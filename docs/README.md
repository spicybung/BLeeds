# File Format Documentation

## Purpose

This directory documents binary file formats used by Rockstar Leeds titles covered by this source tree. The pages are format references, not application documentation: they describe serialized structures, offsets, field meanings, relationships, platform/title differences, decoding rules, and unresolved fields without referring to a particular importer, exporter, Blender add-on, or implementation.

## Documentation rules

- **Confirmed** — the field location and structural purpose are established from files, executable analysis, or consistent serialization behavior.
- **Observed** — the value or relationship recurs in known files, but its complete engine meaning is not yet established.
- **Unknown** — the field exists, but no speculative name is assigned.
- **Reserved / Padding** — bytes are structurally present and should not be given meaning meaning without data.
- Offsets are relative to the structure being described unless stated otherwise.
- Multi-byte values are little-endian unless a section explicitly states otherwise.
- Serialized layout, runtime engine class, and gameplay usage are documented separately when they are not one-to-one concepts.

## Format references

| Document | Extension(s) | Title family | Subject |
|---|---|---|---|
| `format/MDL.md` | `.mdl` | GTA Stories | Leeds model containers, Atomic/Clump structures, geometry and PS2/PSP data paths |
| `format/ANIM.md` | `.anim` | GTA Stories | Stories animation containers, tracks and frame data |
| `format/WRLD.md` | `.wrld` | GTA Stories | World resource containers and embedded render resources |
| `format/XTX-CHK-TEX.md` | `.xtx`, `.chk`, `.tex` | Leeds titles | Texture containers and PS2/PSP raster layouts |
| `format/COL2.md` | `.col2` | GTA Stories | Leeds collision resources |
| `format/LVZ-IMG.md` | `.lvz`, `.img` | GTA Stories | Level/streaming resource tables and sector data |
| `format/WBL.md` | `.wbl` | Chinatown Wars | World-block data |
| `format/IFP.md` | `.ifp` | Manhunt | ANCT/BLOC/ANPK animation libraries |

## Structure style

Fixed structures use tables in this form:

```text
Offset  Size  Type    Data                 Description
--------------------------------------------------------------------------
0x00    4b    LONG    Example              Meaning of the field
```

Variable-length payloads, pointer traversal, packed bit fields, alignment requirements, and title/platform variants are described immediately after the fixed prefix they belong to. A fixed size is not claimed when the available data does not establish one.
