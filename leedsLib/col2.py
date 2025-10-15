# BLeeds - Scripts for working with R* Leeds (GTA Stories, Chinatown Wars, Manhunt 2, etc) formats in Blender
# Author: spicybung
# Years: 2025 - 

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import bpy
import struct

from bpy_extras.io_utils import ImportHelper
from bpy.props import BoolProperty, StringProperty, IntProperty
from bpy.types import Operator
from mathutils import Vector

#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
#   This script is for .COL2 - the file format for GTA Stories collisions           #
#   NOTE: Leeds Engine Collision 2 differs from Rockstars Renderware Col2 format    #
#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #


#######################################################
HEADER_SIZE = 32
SENTINEL = 0xFFFFFFFF

#######################################################
def read_exact(f, n):
    b = f.read(n)
    if not b or len(b) < n:
        raise EOFError(f"Expected %d bytes, got %d" % (n, 0 if not b else len(b)))
    return b
#######################################################
def read_u32(f):
    return struct.unpack("<I", read_exact(f, 4))[0]
#######################################################
def read_i32(f):
    return struct.unpack("<i", read_exact(f, 4))[0]
#######################################################
def read_u16(f):
    return struct.unpack("<H", read_exact(f, 2))[0]
#######################################################
def read_i16(f):
    return struct.unpack("<h", read_exact(f, 2))[0]
#######################################################
def read_f32(f):
    return struct.unpack("<f", read_exact(f, 4))[0]
#######################################################
def hex32(v):
    return f"0x{v:08X}"
#######################################################
def ascii_print(sig_bytes):
    return "".join(chr(b) if 32 <= b <= 126 else "." for b in sig_bytes)
#######################################################
def hexdump_block(b, base_off=0, width=16):
    lines = []
    for i in range(0, len(b), width):
        chunk = b[i:i+width]
        hex_part = " ".join(f"{x:02X}" for x in chunk)
        asc_part = "".join(chr(x) if 32 <= x <= 126 else "." for x in chunk)
        lines.append(f"{base_off+i:08X}  {hex_part:<{width*3}}  {asc_part}")
    return "\n".join(lines)
#######################################################
def lerp(a, b, t):
    return a + (b - a) * t
#######################################################
def dequant_i16_axis(q, amin, amax):
    u = (q + 32768) / 65536.0
    return lerp(amin, amax, u)

#######################################################
def parse_col2_header(f):
    f.seek(0)
    hdr = read_exact(f, HEADER_SIZE)

    sig_bytes = hdr[0:4]
    sig_ascii  = ascii_print(sig_bytes)
    reserved04 = struct.unpack_from("<I", hdr, 0x04)[0]
    file_size  = struct.unpack_from("<I", hdr, 0x08)[0]
    dir_off_1  = struct.unpack_from("<I", hdr, 0x0C)[0]
    dir_off_2  = struct.unpack_from("<I", hdr, 0x10)[0]
    dir_count  = struct.unpack_from("<I", hdr, 0x14)[0]
    reserved18 = struct.unpack_from("<I", hdr, 0x18)[0]
    reserved1C = struct.unpack_from("<I", hdr, 0x1C)[0]

    rep = []
    rep.append("=== COL2 Header ===")
    rep.append(f"Signature               : {sig_ascii!r} (bytes: {' '.join(f'{b:02X}' for b in sig_bytes)})")
    rep.append(f"Reserved @0x04          : {hex32(reserved04)}")
    rep.append(f"File Size               : {file_size} ({hex32(file_size)})")
    rep.append(f"Resource Dir Offset #1  : {dir_off_1} ({hex32(dir_off_1)})")
    rep.append(f"Resource Dir Offset #2  : {dir_off_2} ({hex32(dir_off_2)})")
    rep.append(f"Offsets Match?          : {'SAME' if dir_off_1 == dir_off_2 else 'DIFF'}")
    rep.append(f"Resource Entry Count    : {dir_count} ({hex32(dir_count)})")
    rep.append(f"Reserved @0x18          : {hex32(reserved18)}")
    rep.append(f"Reserved @0x1C          : {hex32(reserved1C)}")

    notes = []
    if sig_bytes != b"2loc":
        notes.append("Signature is not '2loc' (expected 32 6C 6F 63).")
    if file_size < HEADER_SIZE:
        notes.append("File size smaller than header size.")
    if dir_off_1 >= file_size:
        notes.append("Resource directory offset is outside file bounds.")
    if dir_off_1 != dir_off_2:
        notes.append("Resource directory offsets do not match.")
    if reserved04 != 0 or reserved18 != 0 or reserved1C != 0:
        notes.append("Reserved fields not zero (observed non-zero).")

    if notes:
        rep.append("--- Notes ---")
        rep.extend(notes)

    return {
        "raw": hdr,
        "sig": sig_bytes,
        "sig_ascii": sig_ascii,
        "file_size": file_size,
        "dir_off": dir_off_1,
        "dir_off_dup": dir_off_2,
        "dir_count": dir_count,
        "reserved04": reserved04,
        "reserved18": reserved18,
        "reserved1C": reserved1C,
        "report": "\n".join(rep),
    }
#######################################################
def scan_resource_table(f, start_off, file_size, stop_on_sentinel=True, max_entries_hint=None):
    entries = []
    lines = []

    idx = 0
    lines.append("=== Resource Table ===")
    lines.append(f"Start offset            : {start_off} ({hex32(start_off)})")
    lines.append(f"Stop on sentinel        : {stop_on_sentinel} (0xFFFFFFFF)")
    if max_entries_hint is not None:
        lines.append(f"Max entries (hint)      : {max_entries_hint}")

    f.seek(start_off, 0)
    while True:
        here = f.tell()
        if here + 8 > file_size:
            lines.append(f"Reached end of file at {hex32(here)}; stopping.")
            break

        pair_bytes = f.read(8)
        if not pair_bytes or len(pair_bytes) < 8:
            lines.append("Short read in resource table; stopping.")
            break

        rid, roff = struct.unpack("<II", pair_bytes)

        # Sentinel
        if stop_on_sentinel and (rid == SENTINEL or roff == SENTINEL):
            lines.append(f"[{idx:04d}]  id={hex32(rid)}, off={hex32(roff)}  ← sentinel; stopping.")
            break

        off_note = ""
        if roff >= file_size:
            off_note = "  [warn: offset outside file]"
        lines.append(f"[{idx:04d}]  id={hex32(rid)}, off={hex32(roff)}{off_note}")

        entries.append((rid, roff))
        idx += 1

        if (max_entries_hint is not None) and (idx >= max_entries_hint):
            lines.append(f"Reached max entries hint ({max_entries_hint}); stopping.")
            break

    return entries, "\n".join(lines)

#######################################################
def read_sector_common(f, base, file_size):
    f.seek(base)
    cx = read_f32(f); cy = read_f32(f); cz = read_f32(f); cr = read_f32(f)
    minx = read_f32(f); miny = read_f32(f); minz = read_f32(f); wmin = read_f32(f)
    maxx = read_f32(f); maxy = read_f32(f); maxz = read_f32(f); wmax = read_f32(f)

    unk_off = base + 0x30
    unk24 = b""
    if unk_off + 24 <= file_size:
        f.seek(unk_off)
        unk24 = read_exact(f, 24)

    offs_off = base + 0x48
    if offs_off + 12 <= file_size:
        f.seek(offs_off)
        next_rel = read_u32(f)
        vbuf_rel = read_u32(f)
        ibuf_rel = read_u32(f)
    else:
        next_rel = vbuf_rel = ibuf_rel = 0

    next_abs = base + next_rel if next_rel else 0
    vbuf_abs = base + vbuf_rel if vbuf_rel else 0
    ibuf_abs = base + ibuf_rel if ibuf_rel else 0

    return {
        "sphere": (cx, cy, cz, cr),
        "aabb_min": (minx, miny, minz, wmin),
        "aabb_max": (maxx, maxy, maxz, wmax),
        "unk24": unk24,
        "next_rel": next_rel, "vbuf_rel": vbuf_rel, "ibuf_rel": ibuf_rel,
        "next_abs": next_abs, "vbuf_abs": vbuf_abs, "ibuf_abs": ibuf_abs,
    }
#######################################################
def parse_vertex_buffer_as_i16_xyz(f, vbuf_abs, next_abs, file_size, aabb_min, aabb_max, log):
    if vbuf_abs == 0 or vbuf_abs >= file_size:
        return []

    limit = next_abs if (next_abs and next_abs < file_size) else file_size

    f.seek(vbuf_abs)
    try:
        num_vertices = read_u32(f)
    except Exception:
        return []

    bytes_needed = 4 + num_vertices * 6
    if vbuf_abs + bytes_needed > limit or num_vertices > 500000:
        log(f"⚠ Vertex count {num_vertices} looks implausible at {hex32(vbuf_abs)}; falling back to scan until limit.")
        f.seek(vbuf_abs + 4)
        verts = []
        while f.tell() + 6 <= limit and len(verts) < 50000:
            xi = read_i16(f); yi = read_i16(f); zi = read_i16(f)
            x = dequant_i16_axis(xi, aabb_min[0], aabb_max[0])
            y = dequant_i16_axis(yi, aabb_min[1], aabb_max[1])
            z = dequant_i16_axis(zi, aabb_min[2], aabb_max[2])
            verts.append(Vector((x, y, z)))
        return verts

    verts = []
    for _ in range(num_vertices):
        xi = read_i16(f); yi = read_i16(f); zi = read_i16(f)
        x = dequant_i16_axis(xi, aabb_min[0], aabb_max[0])
        y = dequant_i16_axis(yi, aabb_min[1], aabb_max[1])
        z = dequant_i16_axis(zi, aabb_min[2], aabb_max[2])
        verts.append(Vector((x, y, z)))
    return verts
#######################################################
def parse_index_buffer_as_u16_tris(f, ibuf_abs, next_abs, file_size, log):
    if ibuf_abs == 0 or ibuf_abs >= file_size:
        return []

    limit = next_abs if (next_abs and next_abs < file_size) else file_size

    f.seek(ibuf_abs)
    try:
        num_indices = read_u32(f)
    except Exception:
        return []

    bytes_needed = 4 + num_indices * 2
    if (num_indices % 3) != 0 or ibuf_abs + bytes_needed > limit or num_indices > 1500000:
        log(f"⚠ Index count {num_indices} looks implausible at {hex32(ibuf_abs)}; falling back to scan until limit.")
        f.seek(ibuf_abs + 4)
        raw = []
        while f.tell() + 2 <= limit and len(raw) < 900000:
            raw.append(read_u16(f))
        cut = (len(raw) // 3) * 3
        raw = raw[:cut]
        faces = [(raw[i], raw[i+1], raw[i+2]) for i in range(0, cut, 3)]
        return faces

    faces = []
    for i in range(0, num_indices, 3):
        a = read_u16(f); b = read_u16(f); c = read_u16(f)
        faces.append((a, b, c))
    return faces
#######################################################
def parse_sector_and_optionally_build_mesh(f, base, file_size, sector_index, build_meshes, name_mode, put_in_collection, report_lines, created_objects, log):
    info = read_sector_common(f, base, file_size)

    cx, cy, cz, cr = info["sphere"]
    minx, miny, minz, wmin = info["aabb_min"]
    maxx, maxy, maxz, wmax = info["aabb_max"]
    unk24 = info["unk24"]
    next_abs = info["next_abs"]
    vbuf_abs = info["vbuf_abs"]
    ibuf_abs = info["ibuf_abs"]

    report_lines.append(f"=== Sector @ {base} ({hex32(base)}) #{sector_index} ===")
    report_lines.append(f"Sphere c=({cx:.6f},{cy:.6f},{cz:.6f}) r={cr:.6f}")
    report_lines.append(f"AABB min=({minx:.6f},{miny:.6f},{minz:.6f}) max=({maxx:.6f},{maxy:.6f},{maxz:.6f})")
    if unk24:
        u0,u1,u2,u3,u4,u5 = struct.unpack_from("<6I", unk24, 0)
        report_lines.append(f"Unknown[24] @ +0x30: {unk24.hex(' ')}")
        report_lines.append(f"  as_u32: {[hex32(u) for u in (u0,u1,u2,u3,u4,u5)]}")
    else:
        report_lines.append("Unknown[24] @ +0x30: (unreadable / EOF)")

    report_lines.append("Offsets @ +0x48:")
    report_lines.append(f"  next_rel={hex32(info['next_rel'])} → abs {hex32(next_abs) if next_abs else '0x00000000'}")
    report_lines.append(f"  vbuf_rel={hex32(info['vbuf_rel'])} → abs {hex32(vbuf_abs) if vbuf_abs else '0x00000000'}")
    report_lines.append(f"  ibuf_rel={hex32(info['ibuf_rel'])} → abs {hex32(ibuf_abs) if ibuf_abs else '0x00000000'}")

    # If not building meshes, we are done for this sector
    if not build_meshes:
        return next_abs

    aabb_min = (minx, miny, minz)
    aabb_max = (maxx, maxy, maxz)

    verts = parse_vertex_buffer_as_i16_xyz(f, vbuf_abs, next_abs, file_size, aabb_min, aabb_max, log)
    faces = parse_index_buffer_as_u16_tris(f, ibuf_abs, next_abs, file_size, log)

    report_lines.append(f"VertexBuffer parsed: {len(verts)} vertex/positions")
    report_lines.append(f"IndexBuffer parsed:  {len(faces)*3} indices → {len(faces)} triangles")

    if not verts or not faces:
        report_lines.append("⚠ No mesh built (empty verts or faces).")
        return next_abs

    # Create mesh in Blender
    if name_mode == 'ID':
        obj_name = f"COL2_Sector_{sector_index:04d}"
    else:
        obj_name = f"COL2_{hex32(base)}"

    mesh = bpy.data.meshes.new(obj_name)
    mesh.from_pydata(verts, [], faces)
    mesh.validate(verbose=False)
    mesh.update()

    obj = bpy.data.objects.new(obj_name, mesh)
    bpy.context.collection.objects.link(obj)

    if put_in_collection:
        coll_name = "COL2_Sectors"
        coll = bpy.data.collections.get(coll_name)
        if coll is None:
            coll = bpy.data.collections.new(coll_name)
            bpy.context.scene.collection.children.link(coll)
        if obj.name in bpy.context.collection.objects:
            bpy.context.collection.objects.unlink(obj)
        if obj.name not in coll.objects:
            coll.objects.link(obj)

    mat = bpy.data.materials.get("COL2_Sector")
    if mat is None:
        mat = bpy.data.materials.new("COL2_Sector")
        mat.diffuse_color = (0.8, 0.9, 1.0, 1.0)
    if len(obj.data.materials) == 0:
        obj.data.materials.append(mat)

    created_objects.append(obj)
    report_lines.append(f"✔ Built mesh object '{obj_name}' with {len(verts)} verts, {len(faces)} faces.")
    return next_abs
#######################################################
class ImportCOL2Operator(Operator, ImportHelper):
    """Import R* Leeds COL2 (header + table + sector meshes)."""
    bl_idname = "import_scene.col2_leeds"
    bl_label = "Import R* Leeds COL2"
    bl_options = {'PRESET', 'UNDO'}

    filename_ext = ".col2"
    filter_glob: StringProperty(default="*.col2;*.COL2", options={'HIDDEN'})

    build_meshes: BoolProperty(
        name="Build Collision Meshes",
        description="Create Blender mesh objects for each parsed sector",
        default=True
    )
    name_mode: bpy.props.EnumProperty(
        name="Object Naming",
        description="Choose how created objects are named",
        items=[
            ('ID', "Sequential IDs", "COL2_Sector_0000, 0001, ..."),
            ('ADDR', "By Address", "COL2_0x00ABCDEF, ..."),
        ],
        default='ID'
    )
    per_sector_collection: BoolProperty(
        name="Put In 'COL2_Sectors' Collection",
        description="Link created objects into a dedicated collection",
        default=True
    )
    max_sectors: IntProperty(
        name="Max Sectors (0 = no cap)",
        description="Safety limit to stop after N sectors",
        default=0, min=0, soft_max=100000
    )
    #######################################################
    def execute(self, context):
        path = self.filepath
        report_lines = []
        created_objects = []

        try:
            with open(path, "rb") as f:
                header = parse_col2_header(f)
                file_size = header["file_size"]
                dir_off   = header["dir_off"]

                # Header hexdump
                f.seek(0)
                preview = read_exact(f, min(64, HEADER_SIZE))
                hex_dump = hexdump_block(preview, base_off=0, width=16)

                # Resource table
                f.seek(dir_off)
                entries, table_report = scan_resource_table(
                    f,
                    start_off=dir_off,
                    file_size=file_size,
                    stop_on_sentinel=True,
                    max_entries_hint=None
                )
            with open(path, "rb") as f2:
                report_lines.append("="*96)
                report_lines.append(f"COL2 Report: {path}")
                report_lines.append("="*96)
                report_lines.append(header["report"])
                report_lines.append("-"*96)
                report_lines.append("Header hexdump (first bytes):")
                report_lines.append(hex_dump)
                report_lines.append("-"*96)
                report_lines.append(table_report)
                report_lines.append("-"*96)

                sector_counter = 0
                for idx, (rid, roff) in enumerate(entries):
                    if roff >= file_size:
                        report_lines.append(f"[WARN] Entry[{idx}] offset {hex32(roff)} outside file; skipping.")
                        continue

                    sector_counter += 1
                    next_abs = parse_sector_and_optionally_build_mesh(
                        f2,
                        base=roff,
                        file_size=file_size,
                        sector_index=sector_counter,
                        build_meshes=self.build_meshes,
                        name_mode=self.name_mode,
                        put_in_collection=self.per_sector_collection,
                        report_lines=report_lines,
                        created_objects=created_objects,
                        log=lambda m: report_lines.append(m)
                    )

                    if self.max_sectors and sector_counter >= self.max_sectors:
                        report_lines.append(f"Hit max_sectors={self.max_sectors}; stopping.")
                        break

            print("\n".join(report_lines))

            text_name = "COL2_Report"
            txt = bpy.data.texts.get(text_name) or bpy.data.texts.new(text_name)
            txt.clear()
            txt.write("\n".join(report_lines) + "\n")

            self.report({'INFO'}, f"COL2 parsed. Entries: {len(entries)} | Sectors parsed: {sector_counter} | Objects: {len(created_objects)}")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed: {e}")
            return {'CANCELLED'}

#######################################################
def menu_func_import(self, context):
    self.layout.operator(ImportCOL2Operator.bl_idname, text="R* Leeds: Collision2 (.col2)")

classes = (
    ImportCOL2Operator,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
