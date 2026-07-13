# BLeeds - Scripts for working with R* Leeds (GTA Stories, Manhunt 2, etc) formats in Blender
# Author: spicybung
# Years: 2025 - 2026

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
from .. import stamp_bleeds_entity_type

def get_target_collection(context, path: str):
    scene_collection = context.scene.collection
    base_name = Path(path).stem if path else "COL2"
    collection_name = f"BLeeds_COL2_{base_name}"

    existing = bpy.data.collections.get(collection_name)
    if existing is not None:
        return existing

    collection = bpy.data.collections.new(collection_name)
    scene_collection.children.link(collection)
    return collection

def link_object(context, obj, target_collection=None):
    if target_collection is None:
        if hasattr(context, "collection") and context.collection is not None:
            target_collection = context.collection
        else:
            target_collection = context.scene.collection

    target_collection.objects.link(obj)
    return obj

def set_col2_common_props(obj, *, source_path: str, col_index: int, refs, base_off: int, kind: str, aabb_min, aabb_max):
    ref_list = [int(r) & 0xFFFFFFFF for r in refs]
    obj["bleeds_col2_object"] = True
    obj["bleeds_col2_shape"] = str(kind)
    obj["bleeds_col2_source_file"] = str(source_path)
    obj["bleeds_col2_col_index"] = int(col_index)
    obj["bleeds_col2_base_off"] = int(base_off)
    obj["bleeds_col2_resource_id"] = int(ref_list[0]) if ref_list else 0
    obj["bleeds_col2_resource_refs"] = ",".join(f"0x{r:08X}" for r in ref_list)
    obj["bleeds_col2_aabb_min"] = [float(aabb_min[0]), float(aabb_min[1]), float(aabb_min[2])]
    obj["bleeds_col2_aabb_max"] = [float(aabb_max[0]), float(aabb_max[1]), float(aabb_max[2])]
    stamp_bleeds_entity_type(obj, "COLLISION")

def make_wire_collision_display(obj):
    try:
        obj.display_type = "WIRE"
    except Exception:
        pass
    try:
        obj.show_wire = True
    except Exception:
        pass
    try:
        obj.show_in_front = True
    except Exception:
        pass
    return obj

def build_mesh_for_colmodel(context, name: str, verts, faces, target_collection=None):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.validate(verbose=False)
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    link_object(context, obj, target_collection=target_collection)
    return obj

def build_aabb_mesh(context, name: str, aabb_min, aabb_max, target_collection=None):
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

    obj = build_mesh_for_colmodel(context, name, verts, faces, target_collection=target_collection)
    make_wire_collision_display(obj)
    return obj

def build_colbox_objects(
    context,
    *,
    source_path: str,
    col_index: int,
    refs,
    base_off: int,
    base_name: str,
    boxes,
    target_collection=None,
):
    created = []
    for box in boxes:
        index = int(box.get("index", len(created)))
        obj = build_aabb_mesh(
            context,
            f"{base_name}_BOX_{index:03d}",
            box["aabb_min"],
            box["aabb_max"],
            target_collection=target_collection,
        )
        set_col2_common_props(
            obj,
            source_path=source_path,
            col_index=col_index,
            refs=refs,
            base_off=base_off,
            kind="BOX",
            aabb_min=box["aabb_min"],
            aabb_max=box["aabb_max"],
        )
        obj["bleeds_col2_box_index"] = index
        obj["bleeds_col2_box_offset"] = int(box.get("offset", 0))
        try:
            obj["bleeds_col2_box_trailer_hex"] = bytes(box.get("trailer", b"")).hex()
        except Exception:
            obj["bleeds_col2_box_trailer_hex"] = ""
        created.append(obj)
    return created

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
    source_path: str,
    target_collection=None,
    import_box_primitives: bool = True,
    import_empty_model_aabb: bool = True,
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
        f"Buffers         : boxes_off={col2_core.hex32(col_header['boxes_off'])} "
        f"verts_off={col2_core.hex32(verts_off)} tris_off={col2_core.hex32(tris_off)}"
    )

    boxes = col2_core.read_colmodel_boxes(
        file,
        boxes_off=col_header["boxes_off"],
        num_boxes=num_boxes,
        data_end=data_end,
        log=log,
    )
    report_lines.append(f"AABB/CBox records decoded: {len(boxes)}")

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
        else:
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

            if verts and faces:
                obj = build_mesh_for_colmodel(context, base_name, verts, faces, target_collection=target_collection)
                set_col2_common_props(
                    obj,
                    source_path=source_path,
                    col_index=col_index,
                    refs=refs,
                    base_off=base_off,
                    kind="MESH",
                    aabb_min=col_header["aabb_min"],
                    aabb_max=col_header["aabb_max"],
                )
                obj["bleeds_col2_tri_count"] = int(num_tris)
                obj["bleeds_col2_box_count"] = int(num_boxes)
                created_objects.append(obj)
                report_lines.append(f"Object created   : {obj.name}")
            else:
                report_lines.append("⚠ No mesh created (verts or faces empty).")

        if import_box_primitives and boxes:
            box_objects = build_colbox_objects(
                context,
                source_path=source_path,
                col_index=col_index,
                refs=refs,
                base_off=base_off,
                base_name=base_name,
                boxes=boxes,
                target_collection=target_collection,
            )
            created_objects.extend(box_objects)
            report_lines.append(f"AABB/CBox objects : {len(box_objects)}")
        return

    if import_box_primitives and boxes:
        report_lines.append("This CColModel has 0 triangles; building explicit AABB/CBox objects.")
        box_objects = build_colbox_objects(
            context,
            source_path=source_path,
            col_index=col_index,
            refs=refs,
            base_off=base_off,
            base_name=base_name,
            boxes=boxes,
            target_collection=target_collection,
        )
        created_objects.extend(box_objects)
        report_lines.append(f"AABB/CBox objects : {len(box_objects)}")
        return

    if import_empty_model_aabb:
        report_lines.append(
            "This CColModel has 0 triangles and no readable CBox table; building model-bounds AABB."
        )
        obj = build_aabb_mesh(
            context,
            base_name + "_AABB",
            col_header["aabb_min"],
            col_header["aabb_max"],
            target_collection=target_collection,
        )
        set_col2_common_props(
            obj,
            source_path=source_path,
            col_index=col_index,
            refs=refs,
            base_off=base_off,
            kind="AABB",
            aabb_min=col_header["aabb_min"],
            aabb_max=col_header["aabb_max"],
        )
        created_objects.append(obj)
        report_lines.append(f"AABB object      : {obj.name}")

def import_col2_file(path: str, context=None, import_box_primitives: bool = True, import_empty_model_aabb: bool = True):
    if context is None:
        context = bpy.context

    report_lines = []
    created_objects = []

    path_str = str(path)
    file_path = Path(path_str)
    if not file_path.is_file():
        raise FileNotFoundError(f"COL2 file not found: {path_str}")

    target_collection = get_target_collection(context, path_str)

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
                source_path=path_str,
                target_collection=target_collection,
                import_box_primitives=import_box_primitives,
                import_empty_model_aabb=import_empty_model_aabb,
            )

    full_report = "\n".join(report_lines)
    print(full_report)

    text_name = f"COL2_Report_{file_path.stem}"
    text_block = bpy.data.texts.get(text_name) or bpy.data.texts.new(text_name)
    text_block.clear()
    text_block.write(full_report + "\n")

    return created_objects, full_report
