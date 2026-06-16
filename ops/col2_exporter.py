from __future__ import annotations
from pathlib import Path

import bpy
from mathutils import Vector

from ..leedsLib import col2 as col2_core

def object_is_col2(obj) -> bool:
    try:
        if bool(obj.get("bleeds_col2_object", False)):
            return True
    except Exception:
        pass
    name = getattr(obj, "name", "").lower()
    return name.startswith("col2_") or "_aabb" in name or "_box_" in name

def get_objects_for_export(context, selected_only: bool):
    if selected_only:
        objects = list(getattr(context, "selected_objects", []) or [])
    else:
        objects = [obj for obj in context.scene.objects]

    export_objects = []
    for obj in objects:
        if getattr(obj, "type", None) != "MESH":
            continue
        if selected_only or object_is_col2(obj):
            export_objects.append(obj)
    return export_objects

def world_points_from_object(obj):
    points = []
    if obj.type == "MESH" and obj.data is not None:
        for vertex in obj.data.vertices:
            co = obj.matrix_world @ vertex.co
            points.append((float(co.x), float(co.y), float(co.z)))
    if not points:
        for corner in getattr(obj, "bound_box", []) or []:
            co = obj.matrix_world @ Vector(corner)
            points.append((float(co.x), float(co.y), float(co.z)))
    return points

def aabb_from_points(points):
    return col2_core.compute_aabb_from_points(points)

def get_resource_id(obj, fallback: int) -> int:
    for key in ("bleeds_col2_resource_id", "col2_resource_id", "resource_id"):
        try:
            if key in obj:
                value = int(obj[key])
                if value > 0 and value != 0xFFFFFFFF:
                    return value & 0xFFFFFFFF
        except Exception:
            pass
    return fallback & 0xFFFFFFFF

def get_box_trailer(obj):
    try:
        hex_value = obj.get("bleeds_col2_box_trailer_hex", "")
        if hex_value:
            raw = bytes.fromhex(str(hex_value))
            return raw[:16].ljust(16, b"\x00")
    except Exception:
        pass
    return None

def object_should_export_as_box(obj, force_aabb: bool = False) -> bool:
    if force_aabb:
        return True
    shape = str(obj.get("bleeds_col2_shape", "")).upper() if hasattr(obj, "get") else ""
    if shape in {"BOX", "AABB", "BOUNDS"}:
        return True
    if getattr(obj, "display_type", "") == "WIRE" and object_is_col2(obj):
        return True
    return False

def collect_mesh_faces(obj):
    verts = []
    faces = []
    if obj.type != "MESH" or obj.data is None:
        return verts, faces

    mesh = obj.data
    for vertex in mesh.vertices:
        co = obj.matrix_world @ vertex.co
        verts.append((float(co.x), float(co.y), float(co.z)))

    for poly in mesh.polygons:
        indices = list(poly.vertices)
        for tri in col2_core.triangulate_face_indices(indices):
            faces.append(tuple(int(i) for i in tri))
    return verts, faces

def build_export_models(context, selected_only: bool = True, force_selected_to_aabb: bool = False):
    objects = get_objects_for_export(context, selected_only=selected_only)
    models = []
    next_resource_id = 0x1000

    for obj in objects:
        points = world_points_from_object(obj)
        if not points:
            continue

        resource_id = get_resource_id(obj, next_resource_id)
        if resource_id == next_resource_id:
            next_resource_id += 1

        aabb_min, aabb_max = aabb_from_points(points)

        if object_should_export_as_box(obj, force_aabb=force_selected_to_aabb):
            models.append({
                "name": obj.name,
                "resource_id": resource_id,
                "aabb_min": aabb_min,
                "aabb_max": aabb_max,
                "boxes": [{
                    "aabb_min": aabb_min,
                    "aabb_max": aabb_max,
                    "trailer": get_box_trailer(obj),
                }],
                "vertices": [],
                "faces": [],
            })
            continue

        verts, faces = collect_mesh_faces(obj)
        if verts and faces:
            models.append({
                "name": obj.name,
                "resource_id": resource_id,
                "aabb_min": aabb_min,
                "aabb_max": aabb_max,
                "boxes": [],
                "vertices": verts,
                "faces": faces,
            })
        else:
            models.append({
                "name": obj.name,
                "resource_id": resource_id,
                "aabb_min": aabb_min,
                "aabb_max": aabb_max,
                "boxes": [{"aabb_min": aabb_min, "aabb_max": aabb_max, "trailer": get_box_trailer(obj)}],
                "vertices": [],
                "faces": [],
            })

    return models

def export_col2_file(path: str, context=None, selected_only: bool = True, force_selected_to_aabb: bool = False, pad_to_sector: bool = True):
    if context is None:
        context = bpy.context

    models = build_export_models(
        context,
        selected_only=selected_only,
        force_selected_to_aabb=force_selected_to_aabb,
    )
    if not models:
        raise ValueError("No mesh/AABB objects were available for COL2 export.")

    result = col2_core.write_col2_archive(
        path,
        models,
        pad_to_sector=pad_to_sector,
    )

    lines = []
    lines.append("=" * 96)
    lines.append(f"COL2 Export Report: {path}")
    lines.append("=" * 96)
    lines.append(f"Objects exported : {len(models)}")
    lines.append(f"Logical size     : 0x{result['logical_size']:08X}")
    lines.append(f"Physical size    : 0x{result['physical_size']:08X}")
    lines.append(f"Reloc table      : 0x{result['reloc_off']:08X}")
    lines.append(f"Reloc entries    : {result['reloc_count']}")
    for model, resource_id in zip(models, result["resource_ids"]):
        lines.append(
            f"  id=0x{resource_id:08X} name='{model['name']}' "
            f"verts={len(model.get('vertices', []))} faces={len(model.get('faces', []))} "
            f"boxes={len(model.get('boxes', []))}"
        )

    report = "\n".join(lines)
    print(report)

    text_name = f"COL2_Export_{Path(path).stem}"
    text_block = bpy.data.texts.get(text_name) or bpy.data.texts.new(text_name)
    text_block.clear()
    text_block.write(report + "\n")

    return result, report
