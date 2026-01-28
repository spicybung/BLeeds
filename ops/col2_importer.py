# BLeeds - Scripts for working with R* Leeds (GTA Stories, Manhunt 2, etc) formats in Blender
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

from pathlib import Path

import bpy

from ..leedsLib import col2 as col2_core


def build_mesh_for_colmodel(context, name: str, verts, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.validate(verbose=False)
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)

    if hasattr(context, "collection") and context.collection is not None:
        target_collection = context.collection
    else:
        target_collection = context.scene.collection

    target_collection.objects.link(obj)
    return obj


def build_aabb_mesh(context, name: str, aabb_min, aabb_max):
    """
    Build a simple axis-aligned box from the CColModel AABB.
    This is used for CColModels that have 0 triangles (box/sphere-only).
    """
    min_x, min_y, min_z, _ = aabb_min
    max_x, max_y, max_z, _ = aabb_max

    verts = [
        (min_x, min_y, min_z),
        (max_x, min_y, min_z),
        (max_x, max_y, min_z),
        (min_x, max_y, min_z),
        (min_x, min_y, max_z),
        (max_x, min_y, max_z),
        (max_x, max_y, max_z),
        (min_x, max_y, max_z),
    ]

    faces = [
        (0, 1, 2, 3),  
        (4, 5, 6, 7),  
        (0, 1, 5, 4),  
        (1, 2, 6, 5),  
        (2, 3, 7, 6),  
        (3, 0, 4, 7),  
    ]

    return build_mesh_for_colmodel(context, name, verts, faces)


def parse_colmodel(
    file,
    header,
    col_header,
    col_index: int,
    refs,
    report_lines,
    created_objects,
    context,
    log,
):
    data_end = header["data_end"]

    base_off = col_header["base_off"]
    center_x, center_y, center_z = col_header["center"]
    radius = col_header["radius"]
    min_x, min_y, min_z, min_w = col_header["aabb_min"]
    max_x, max_y, max_z, max_w = col_header["aabb_max"]
    num_tris = col_header["numTris"]
    num_boxes = col_header["numBoxes"]
    num_spheres = col_header["numSpheres"]
    verts_off = col_header["verts_off"]
    tris_off = col_header["tris_off"]

    report_lines.append("")
    ref_desc = ", ".join(col2_core.hex32(r) for r in refs) if refs else "<unreferenced>"

    report_lines.append(f"=== CColModel #{col_index} @ {col2_core.hex32(base_off)} ===")
    report_lines.append(f"Resource IDs    : {ref_desc}")
    report_lines.append(
        f"Sphere center   : ({center_x:.6f}, {center_y:.6f}, {center_z:.6f}) "
        f"r={radius:.6f}"
    )
    report_lines.append(
        f"AABB min        : ({min_x:.6f}, {min_y:.6f}, {min_z:.6f}, w={min_w:.6f})"
    )
    report_lines.append(
        f"AABB max        : ({max_x:.6f}, {max_y:.6f}, {max_z:.6f}, w={max_w:.6f})"
    )
    report_lines.append(
        f"Counts          : boxes={num_boxes} tris={num_tris} spheres={num_spheres} "
        f"triSections={col_header['numTriSections']} lines={col_header['numLines']}"
    )
    report_lines.append(
        f"Buffers         : verts_off={col2_core.hex32(verts_off)} "
        f"tris_off={col2_core.hex32(tris_off)}"
    )

    if refs:
        base_name = f"COL2_{col_index:03d}_R{refs[0]:04X}"
    else:
        base_name = f"COL2_{col_index:03d}"

    if num_tris > 0:
        faces, max_index = col2_core.read_colmodel_triangles(
            file,
            tris_off=tris_off,
            num_tris=num_tris,
            data_end=data_end,
            log=log,
        )

        if not faces:
            report_lines.append(
                "⚠ No triangles built for this CColModel (triangle buffer empty after decode)."
            )
            return

        verts = col2_core.read_colmodel_vertices(
            file,
            verts_off=verts_off,
            required_vertices=max_index + 1,
            data_end=data_end,
            log=log,
        )

        if verts:
            max_valid = len(verts) - 1
            filtered_faces = []
            dropped = 0
            for a, b, c in faces:
                if 0 <= a <= max_valid and 0 <= b <= max_valid and 0 <= c <= max_valid:
                    filtered_faces.append((a, b, c))
                else:
                    dropped += 1
            if dropped:
                log(
                    f"[WARN] Dropped {dropped} triangles in CColModel #{col_index} "
                    f"due to out-of-range indices (len(verts)={len(verts)})."
                )
            faces = filtered_faces

        report_lines.append(f"Triangles decoded: {len(faces)}")
        report_lines.append(f"Vertices decoded : {len(verts)} (max index {max_index})")

        if not verts or not faces:
            report_lines.append("⚠ No mesh created (verts or faces empty).")
            return

        obj = build_mesh_for_colmodel(context, base_name, verts, faces)
        created_objects.append(obj)
        report_lines.append(f"Object created   : {obj.name}")
        return

    report_lines.append(
        "This CColModel has 0 triangles; building an AABB box mesh from bounding box."
    )

    obj = build_aabb_mesh(
        context,
        base_name + "_AABB",
        col_header["aabb_min"],
        col_header["aabb_max"],
    )
    created_objects.append(obj)
    report_lines.append(f"AABB object      : {obj.name}")
    return


def import_col2_file(path: str, context=None):
    """
    High-level entry point used by the IMPORT_OT in col2_ot.
    Opens the COL2 file, parses it with col2_core, builds meshes in Blender,
    and returns the list of created objects plus the textual report.
    """
    if context is None:
        context = bpy.context

    report_lines = []
    created_objects = []

    path_str = str(path)
    file_path = Path(path_str)
    if not file_path.is_file():
        raise FileNotFoundError(f"COL2 file not found: {path_str}")

    with open(path_str, "rb") as file:
        header = col2_core.parse_col2_header(file, path_str)

        file.seek(0)
        preview = col2_core.read_exact(file, min(64, col2_core.HEADER_SIZE))
        hex_dump = col2_core.hexdump_block(preview, base_off=0, width=16)

        entries, table_report = col2_core.scan_primary_resource_table(
            file,
            header=header,
            log=lambda message: report_lines.append(message),
        )

        report_lines.append("=" * 96)
        report_lines.append(f"COL2 Report: {path_str}")
        report_lines.append("=" * 96)
        report_lines.append(header["report"])
        report_lines.append("-" * 96)
        report_lines.append("Header hexdump (first bytes):")
        report_lines.append(hex_dump)
        report_lines.append("-" * 96)
        report_lines.append(table_report)
        report_lines.append("-" * 96)

        colmodels = col2_core.find_colmodels_from_entries(
            file,
            header=header,
            entries=entries,
            report_lines=report_lines,
            log=lambda message: report_lines.append(message),
        )

        model_counter = 0
        for base_off in sorted(colmodels.keys()):
            entry = colmodels[base_off]
            col_header = entry["header"]
            refs = entry["refs"]
            model_counter += 1

            parse_colmodel(
                file,
                header=header,
                col_header=col_header,
                col_index=model_counter,
                refs=refs,
                report_lines=report_lines,
                created_objects=created_objects,
                context=context,
                log=lambda message: report_lines.append(message),
            )

    full_report = "\n".join(report_lines)
    print(full_report)

    text_name = "COL2_Report"
    text_block = bpy.data.texts.get(text_name) or bpy.data.texts.new(text_name)
    text_block.clear()
    text_block.write(full_report + "\n")

    return created_objects, full_report
