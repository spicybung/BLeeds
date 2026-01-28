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

import re
from typing import List, Optional, Tuple

import bpy
import bmesh
import math
from mathutils import Vector, Matrix


from ..leedsLib import mdl as mdl_lib


def natural_sort_key(name: str) -> List[object]:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def find_mdl_root_from_object(obj: bpy.types.Object) -> Optional[bpy.types.Object]:
    cur = obj
    while cur is not None:
        if getattr(cur, "bleeds_is_mdl_root", False):
            return cur
        if cur.type == "EMPTY" and cur.name.upper().endswith("_ROOT"):
            return cur
        cur = cur.parent
    return None


def find_mdl_root(context: bpy.types.Context) -> bpy.types.Object:
    candidates: List[bpy.types.Object] = []
    if context.active_object is not None:
        candidates.append(context.active_object)
    candidates.extend([o for o in context.selected_objects if o not in candidates])

    for obj in candidates:
        root = find_mdl_root_from_object(obj)
        if root is not None:
            return root

    raise RuntimeError(
        "Couldn't find an MDL ROOT. Select the imported ROOT empty (bleeds_is_mdl_root) "
        "or select any child mesh under it."
    )


def gather_mesh_parts(context: bpy.types.Context, root: bpy.types.Object) -> List[bpy.types.Object]:
    selected_under_root: List[bpy.types.Object] = []
    for obj in context.selected_objects:
        if obj.type != "MESH":
            continue
        cur = obj
        while cur is not None:
            if cur == root:
                selected_under_root.append(obj)
                break
            cur = cur.parent

    if selected_under_root:
        meshes = selected_under_root
    else:
        meshes = [o for o in root.children_recursive if o.type == "MESH"]

    meshes.sort(key=lambda o: natural_sort_key(o.name))
    return meshes


def resolve_texture_name(mat) -> str:
    """
    Prefer Image Texture node image name, else material name.
    Strips extensions.
    """
    if mat is None:
        return "default"

    if hasattr(mat, "use_nodes") and mat.use_nodes and mat.node_tree:
        for node in mat.node_tree.nodes:
            if node.type == "TEX_IMAGE" and getattr(node, "image", None):
                name = node.image.name
                name = name.rsplit(".", 1)[0]
                return name

    return mat.name.rsplit(".", 1)[0]


def collect_material_names_in_slot_order(mesh_obj) -> list[str]:
    """
    Returns names per material slot, preserving order (no accidental duplication).
    """
    names = []
    for slot in getattr(mesh_obj, "material_slots", []):
        mat = slot.material
        names.append(resolve_texture_name(mat))
    return names


def stitch_strips_into_one(strip: List[mdl_lib.Ps2Vertex], next_strip: List[mdl_lib.Ps2Vertex]) -> None:
    """
    Stitch two triangle strips into one by inserting degenerate vertices.
    This is the same parity-safe approach used in your standalone exporter.
    """
    if not strip:
        strip.extend(next_strip)
        return
    if not next_strip:
        return

    last = strip[-1]
    next_first = next_strip[0]

    strip.append(last)
    strip.append(next_first)

    strip.extend(next_strip)

    if (len(strip) % 2) == 1:
        strip.append(next_first)


def build_strip_vertices_world(
    context: bpy.types.Context,
    mesh_obj: bpy.types.Object,
    *,
    use_normals: bool = True,
) -> List[mdl_lib.Ps2Vertex]:
    """
    Convert the mesh into ONE stitched triangle strip list in WORLD space.

    Fixes the old behavior where we built a 3‑vert "strip" per triangle and
    degenerate‑stitched them all together (which creates massive vertex repetition).

    This function remains available for backwards compatibility but is no longer
    used by the Stories PS2 export when "Export Normals" is enabled.  See
    ``build_simple_vertices_world()`` for the simplified export path used to
    faithfully reproduce retail MDLs.  ``build_strip_vertices_world()``
    attempts to greedily build a single triangle strip covering the whole
    mesh, inserting degenerate vertices where necessary to stitch strips.
    Although this yields the correct surface, it can generate large numbers
    of vertices when seams (distinct UVs, normals or colours) are present.
    """
    def clamp_u8(x: int) -> int:
        if x < 0:
            return 0
        if x > 255:
            return 255
        return x

    def round_key_f(x: float, places: int = 6) -> float:
        return float(round(float(x), places))
    
    def round_key_pos(v: Vector, places: int = 6) -> tuple[float, float, float]:
        return (
            float(round(float(v.x), places)),
            float(round(float(v.y), places)),
            float(round(float(v.z), places)),
        )

    def make_corner_signature(
        wp: Vector,
        u: float,
        vv: float,
        nx: float,
        ny: float,
        nz: float,
        ri: int,
        gi: int,
        bi: int,
        ai: int,
    ) -> tuple:
        px, py, pz = round_key_pos(wp, 6)
        return (
            px, py, pz,
            round_key_f(u), round_key_f(vv),
            round_key_f(nx), round_key_f(ny), round_key_f(nz),
            int(ri), int(gi), int(bi), int(ai),
        )


    def get_active_vcol_layer(mesh: bpy.types.Mesh):
        if hasattr(mesh, "color_attributes"):
            ca = getattr(mesh, "color_attributes", None)
            if ca and getattr(ca, "active", None):
                return ca.active.data
        vc = getattr(mesh, "vertex_colors", None)
        if vc and getattr(vc, "active", None):
            return vc.active.data
        return None

    def stitch_key_strips_into_one(strip_keys: List[tuple], next_keys: List[tuple]) -> None:
        """
        Same stitching rule as stitch_strips_into_one(), but for KEY lists
        (so we can stitch before converting keys -> Ps2Vertex objects).
        """
        if not strip_keys:
            strip_keys.extend(next_keys)
            return
        if not next_keys:
            return

        last = strip_keys[-1]
        nxt0 = next_keys[0]

        strip_keys.append(last)
        strip_keys.append(nxt0)

        strip_keys.extend(next_keys)

        if (len(strip_keys) % 2) == 1:
            strip_keys.append(nxt0)

    def build_directed_edge_map(tris_keys: List[tuple]) -> dict:
        """
        directed_edge[(a,b)] -> list of (tri_index, c)
        where (a,b,c) is the triangle corner order.
        """
        directed = {}
        for ti, (a, b, c) in enumerate(tris_keys):
            directed.setdefault((a, b), []).append((ti, c))
            directed.setdefault((b, c), []).append((ti, a))
            directed.setdefault((c, a), []).append((ti, b))
        return directed

    def rotate_tri(a, b, c, rot: int):
        if rot == 0:
            return (a, b, c)
        if rot == 1:
            return (b, c, a)
        return (c, a, b)

    def try_build_strip_from_seed(
        seed_tri_index: int,
        rot: int,
        tris_keys: List[tuple],
        directed_edges: dict,
        unused_set: set,
    ) -> (List[tuple], set):
        """
        Greedy strip grow.
        Uses parity to decide whether we need (prev,last) or (last,prev) directed edge.
        This avoids the 'triangle-per-strip + degenerates' explosion.
        """
        a, b, c = tris_keys[seed_tri_index]
        a, b, c = rotate_tri(a, b, c, rot)

        strip = [a, b, c]
        used = {seed_tri_index}

        while True:
            next_tri_index = len(strip) - 2
            if (next_tri_index % 2) == 0:
                edge = (strip[-2], strip[-1])
            else:
                edge = (strip[-1], strip[-2])

            candidates = directed_edges.get(edge)
            if not candidates:
                break

            picked = None
            for (ti, opp) in candidates:
                if ti in used:
                    continue
                if ti not in unused_set:
                    continue
                if opp == strip[-1] or opp == strip[-2]:
                    continue
                picked = (ti, opp)
                break

            if picked is None:
                break

            ti, opp = picked
            used.add(ti)
            strip.append(opp)

        return strip, used

    depsgraph = context.evaluated_depsgraph_get()
    obj_eval = mesh_obj.evaluated_get(depsgraph)
    mesh_eval = obj_eval.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    try:
        mesh_eval.calc_loop_triangles()
        mesh_eval.calc_normals_split()

        uv_layer = mesh_eval.uv_layers.active.data if (mesh_eval.uv_layers.active) else None
        vcol_layer = get_active_vcol_layer(mesh_eval)

        world_mtx: Matrix = mesh_obj.matrix_world.copy()
        normal_mtx: Matrix = world_mtx.to_3x3()

        key_to_vertex: dict = {}

        def get_corner_key(loop_index: int, vert_index: int) -> tuple:
            v = mesh_eval.vertices[vert_index]
            wp = world_mtx @ v.co

            if uv_layer is not None:
                uv = uv_layer[loop_index].uv
                u = float(uv.x)
                vv = float(uv.y)
            else:
                u, vv = 0.0, 0.0

            if use_normals:
                n = mesh_eval.loops[loop_index].normal
                nw = (normal_mtx @ n).normalized()
                nx, ny, nz = float(nw.x), float(nw.y), float(nw.z)
            else:
                nx, ny, nz = 0.0, 0.0, 1.0

            if vcol_layer is not None:
                col = getattr(vcol_layer[loop_index], "color", None)
                if col is None:
                    r, g, b, a = 1.0, 1.0, 1.0, 1.0
                else:
                    r = float(col[0]); g = float(col[1]); b = float(col[2])
                    a = float(col[3]) if (len(col) >= 4) else 1.0
            else:
                r, g, b, a = 1.0, 1.0, 1.0, 1.0

            ri = clamp_u8(int(round(r * 255.0)))
            gi = clamp_u8(int(round(g * 255.0)))
            bi = clamp_u8(int(round(b * 255.0)))
            ai = clamp_u8(int(round(a * 255.0)))

            key = make_corner_signature(wp, u, vv, nx, ny, nz, ri, gi, bi, ai)

            if key not in key_to_vertex:
                key_to_vertex[key] = mdl_lib.Ps2Vertex(
                    x=float(wp.x), y=float(wp.y), z=float(wp.z),
                    u=float(u), v=float(vv),
                    nx=float(nx), ny=float(ny), nz=float(nz),
                    r=int(ri), g=int(gi), b=int(bi), a=int(ai),
                )

            return key


        tris_keys: List[tuple] = []
        for tri in mesh_eval.loop_triangles:
            loops = tri.loops
            verts = tri.vertices
            k0 = get_corner_key(int(loops[0]), int(verts[0]))
            k1 = get_corner_key(int(loops[1]), int(verts[1]))
            k2 = get_corner_key(int(loops[2]), int(verts[2]))
            tris_keys.append((k0, k1, k2))

        tris_keys: List[tuple] = []
        skipped_degenerate = 0

        for tri in mesh_eval.loop_triangles:
            loops = tri.loops
            verts = tri.vertices

            k0 = get_corner_key(int(loops[0]), int(verts[0]))
            k1 = get_corner_key(int(loops[1]), int(verts[1]))
            k2 = get_corner_key(int(loops[2]), int(verts[2]))

            if (k0 == k1) or (k1 == k2) or (k2 == k0):
                skipped_degenerate += 1
                continue

            tris_keys.append((k0, k1, k2))

        print(f"[BLeeds] loop_tris={len(mesh_eval.loop_triangles)} usable_tris={len(tris_keys)} skipped_degenerate={skipped_degenerate} unique_keys={len(key_to_vertex)}")


        if not tris_keys:
            return []

        directed_edges = build_directed_edge_map(tris_keys)

        unused = set(range(len(tris_keys)))
        built_strips_keys: List[List[tuple]] = []

        while unused:
            seed = next(iter(unused))

            best_strip = None
            best_used = None

            for rot in (0, 1, 2):
                strip_keys, used_tris = try_build_strip_from_seed(
                    seed_tri_index=seed,
                    rot=rot,
                    tris_keys=tris_keys,
                    directed_edges=directed_edges,
                    unused_set=unused,
                )
                if best_strip is None or (len(strip_keys) > len(best_strip)):
                    best_strip = strip_keys
                    best_used = used_tris

            if best_strip is None or best_used is None:
                a, b, c = tris_keys[seed]
                best_strip = [a, b, c]
                best_used = {seed}

            unused.difference_update(best_used)
            built_strips_keys.append(best_strip)

        stitched_keys: List[tuple] = []
        for s in built_strips_keys:
            stitch_key_strips_into_one(stitched_keys, s)

        out: List[mdl_lib.Ps2Vertex] = []
        for k in stitched_keys:
            out.append(key_to_vertex[k])

        return out
    finally:
        obj_eval.to_mesh_clear()


def build_simple_vertices_world(
    context: bpy.types.Context,
    mesh_obj: bpy.types.Object,
    *,
    use_normals: bool = True,
) -> List[mdl_lib.Ps2Vertex]:
    """
    Construct a simple vertex list from a mesh without attempting to build a
    triangle strip.  The returned list contains exactly one ``Ps2Vertex`` per
    vertex in the evaluated mesh.  UV coordinates and normals are taken from
    the first loop referencing each vertex; if a vertex has no UVs or
    normals, sensible defaults are used (0 for UVs and (0,0,1) for normals).

    This function is used by the Stories PS2 exporter when ``Export Normals``
    is enabled via the MDL root object.  By preserving the original vertex
    order and avoiding the greedy strip builder, we eliminate the massive
    vertex duplication that can occur when stitching strips with seams.  The
    caller should still pass the resulting list to
    ``mdl_lib.build_ps2_dma_for_strip()`` which will emit the position,
    texcoord and (optionally) normal streams in the correct order.

    :param context: Blender context used to retrieve the evaluated depsgraph.
    :param mesh_obj: The mesh object to convert.
    :param use_normals: Whether normals should be included.  When False, the
      normal components of the returned Ps2Vertex records are all set to
      (0, 0, 1).
    :return: A list of ``Ps2Vertex`` objects ordered by vertex index.
    """
    def clamp_u8(x: int) -> int:
        if x < 0:
            return 0
        if x > 255:
            return 255
        return x

    def get_active_vcol_layer(mesh: bpy.types.Mesh):
        if hasattr(mesh, "color_attributes"):
            ca = getattr(mesh, "color_attributes", None)
            if ca and getattr(ca, "active", None):
                return ca.active.data
        vc = getattr(mesh, "vertex_colors", None)
        if vc and getattr(vc, "active", None):
            return vc.active.data
        return None

    depsgraph = context.evaluated_depsgraph_get()
    obj_eval = mesh_obj.evaluated_get(depsgraph)
    mesh_eval = obj_eval.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    try:
        mesh_eval.calc_normals_split()

        uv_layer = mesh_eval.uv_layers.active.data if (mesh_eval.uv_layers.active) else None
        vcol_layer = get_active_vcol_layer(mesh_eval)

        loops_by_vertex = {}
        for li, loop in enumerate(mesh_eval.loops):
            vi = int(loop.vertex_index)
            if vi not in loops_by_vertex:
                loops_by_vertex[vi] = li

        world_mtx: Matrix = mesh_obj.matrix_world.copy()
        normal_mtx: Matrix = world_mtx.to_3x3()

        out: List[mdl_lib.Ps2Vertex] = []

        imported_normals = None
        try:
            imported_normals = getattr(mesh_obj, "bleeds_imported_normals", None)
            if not imported_normals and isinstance(mesh_obj, bpy.types.Object):
                imported_normals = mesh_obj.get("bleeds_imported_normals")
            if imported_normals:
                imported_normals = [
                    (float(n[0]), float(n[1]), float(n[2])) for n in imported_normals
                ]
        except Exception:
            imported_normals = None

        for vi, vert in enumerate(mesh_eval.vertices):
            wp = world_mtx @ vert.co

            u = 0.0
            vv = 0.0
            nx = 0.0
            ny = 0.0
            nz = 1.0
            ri = 255
            gi = 255
            bi = 255
            ai = 255

            loop_index = loops_by_vertex.get(vi)
            if loop_index is not None:
                if uv_layer is not None:
                    try:
                        uv = uv_layer[loop_index].uv
                        u = float(uv.x)
                        vv = float(uv.y)
                    except Exception:
                        u, vv = 0.0, 0.0

                if use_normals:
                    if imported_normals and vi < len(imported_normals):
                        try:
                            nx, ny, nz = imported_normals[vi]
                        except Exception:
                            nx, ny, nz = 0.0, 0.0, 1.0
                    else:
                        try:
                            n = mesh_eval.loops[loop_index].normal
                            nw = (normal_mtx @ n).normalized()
                            nx, ny, nz = float(nw.x), float(nw.y), float(nw.z)
                        except Exception:
                            nx, ny, nz = 0.0, 0.0, 1.0

                if vcol_layer is not None:
                    try:
                        col = getattr(vcol_layer[loop_index], "color", None)
                        if col is not None:
                            r = float(col[0]); g = float(col[1]); b = float(col[2])
                            a = float(col[3]) if (len(col) >= 4) else 1.0
                            ri = clamp_u8(int(round(r * 255.0)))
                            gi = clamp_u8(int(round(g * 255.0)))
                            bi = clamp_u8(int(round(b * 255.0)))
                            ai = clamp_u8(int(round(a * 255.0)))
                    except Exception:
                        pass

            out.append(mdl_lib.Ps2Vertex(
                x=float(wp.x), y=float(wp.y), z=float(wp.z),
                u=float(u), v=float(vv),
                nx=float(nx), ny=float(ny), nz=float(nz),
                r=int(ri), g=int(gi), b=int(bi), a=int(ai),
            ))

        return out
    finally:
        try:
            obj_eval.to_mesh_clear()
        except Exception:
            pass


def export_stories_mdl_ps2(
    context: bpy.types.Context,
    filepath: str,
    *,
    mdl_type: str = "SIM",
    max_batch_verts: int = 0,
    rounding_mode: str = "ROUND",
    use_normals: bool = True,
) -> None:
    root = find_mdl_root(context)
    meshes = gather_mesh_parts(context, root)

    if not meshes:
        raise RuntimeError("No mesh parts found under ROOT. Nothing to export.")

    scale_pos = mdl_lib.compute_effective_scale_pos(root)
    if scale_pos is None:
        raise RuntimeError(
            "ROOT doesn't have valid Leeds Scale/Pos.\n"
            "Make sure the ROOT empty has MDL Base (In-Game) values set "
            "(bleeds_leeds_scale_base / bleeds_leeds_pos_base)."
        )

    dma_packets: List[bytearray] = []
    texture_names: List[str] = []
    part_material_names: List[str] = []
    ps2_max_strip_verts = getattr(mdl_lib, "PS2_MAX_TRISTRIP_VERTS", 70)

    root_cache = {}
    try:
        if hasattr(root, "bleeds_mdl_atomic_hash_key"):
            root_cache["hash_key"] = int(root.bleeds_mdl_atomic_hash_key)
        if hasattr(root, "bleeds_mdl_material_names"):
            root_cache["material_names"] = list(root.bleeds_mdl_material_names)
        if hasattr(root, "bleeds_mdl_material_vcols"):
            root_cache["material_vcols"] = list(root.bleeds_mdl_material_vcols)
        if hasattr(root, "bleeds_mdl_bounds"):
            root_cache["bounds"] = tuple(float(x) for x in root.bleeds_mdl_bounds)
        if hasattr(root, "bleeds_mdl_unknown_geom_ints"):
            root_cache["unknown_geom_ints"] = [int(x) for x in root.bleeds_mdl_unknown_geom_ints]
        if hasattr(root, "bleeds_mdl_geom_block"):
            try:
                root_cache["geom_block"] = bytes.fromhex(str(root.bleeds_mdl_geom_block))
            except Exception:
                root_cache["geom_block"] = None
        if hasattr(root, "bleeds_mdl_part_batch_verts"):
            root_cache["part_batch_verts"] = [int(x) for x in root.bleeds_mdl_part_batch_verts]
    except Exception:
        try:
            if "bleeds_mdl_atomic_hash_key" in root:
                root_cache["hash_key"] = int(root["bleeds_mdl_atomic_hash_key"])
            if "bleeds_mdl_material_names" in root:
                root_cache["material_names"] = list(root["bleeds_mdl_material_names"])
            if "bleeds_mdl_material_vcols" in root:
                root_cache["material_vcols"] = [int(v) for v in root["bleeds_mdl_material_vcols"]]
            if "bleeds_mdl_bounds" in root:
                b = root["bleeds_mdl_bounds"]
                root_cache["bounds"] = (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
            if "bleeds_mdl_unknown_geom_ints" in root:
                root_cache["unknown_geom_ints"] = [int(x) for x in root["bleeds_mdl_unknown_geom_ints"]]
            if "bleeds_mdl_geom_block" in root:
                try:
                    root_cache["geom_block"] = bytes.fromhex(str(root["bleeds_mdl_geom_block"]))
                except Exception:
                    root_cache["geom_block"] = None
            if "bleeds_mdl_part_batch_verts" in root:
                root_cache["part_batch_verts"] = [int(x) for x in root["bleeds_mdl_part_batch_verts"]]
        except Exception:
            pass


    try:
        override_normals = None
        if root is not None:
            if hasattr(root, "bleeds_export_use_normals"):
                override_normals = bool(root.bleeds_export_use_normals)
            elif "bleeds_export_use_normals" in root:
                override_normals = bool(root["bleeds_export_use_normals"])
        if override_normals is not None:
            use_normals = override_normals
    except Exception:
        pass


    for mesh_obj in meshes:
        if use_normals:
            strip = build_simple_vertices_world(context, mesh_obj, use_normals=True)
        else:
            strip = build_strip_vertices_world(context, mesh_obj, use_normals=False)
        if not strip:
            continue

        if "material_names" in root_cache and len(root_cache["material_names"]) == len(meshes):
            base_mat_name = str(root_cache["material_names"][len(texture_names)])
        else:
            slot_names = collect_material_names_in_slot_order(mesh_obj)
            if slot_names:
                base_mat_name = str(slot_names[0])
            else:
                base_mat_name = str(mesh_obj.name)

        texture_names.append(base_mat_name)

        sub_strips = mdl_lib.split_ps2_tristrip_vertices(
            strip,
            max_verts=int(ps2_max_strip_verts),
            overlap=2,
        )

        for sub in sub_strips:
            per_part_max = len(sub)

            dma, _ = mdl_lib.build_ps2_dma_for_strip(
                sub,
                use_normals=use_normals,
                max_batch_verts=per_part_max,
                scale_pos_override=scale_pos,
                rounding_mode=rounding_mode,
            )
            dma_packets.append(dma)
            part_material_names.append(base_mat_name)
    if not dma_packets:
        raise RuntimeError("All selected/child meshes were empty (no triangles). Nothing to export.")

    mdl_type_u = (mdl_type or "SIM").upper().strip()
    if mdl_type_u == "PED":
        mdl_lib.write_simplemodel_ps2_ped_mdl(
            filepath,
            scale_pos=scale_pos,
            dma_packets=dma_packets,
            material_names=part_material_names,
        )
    else:
        kwargs = {}
        if "hash_key" in root_cache:
            kwargs["atomic_hash_key"] = int(root_cache["hash_key"])
        if "material_vcols" in root_cache and root_cache["material_vcols"]:
            vcols = list(root_cache["material_vcols"])
            if len(vcols) < len(texture_names):
                vcols.extend([vcols[-1]] * (len(texture_names) - len(vcols)))
            kwargs["material_vcols"] = vcols
        if "bounds" in root_cache:
            kwargs["bounds"] = tuple(float(x) for x in root_cache["bounds"])
        if "unknown_geom_ints" in root_cache:
            kwargs["unknown_geom_ints"] = [int(x) for x in root_cache["unknown_geom_ints"]]
        if "geom_block" in root_cache and root_cache["geom_block"]:
            kwargs["geom_block_override"] = root_cache["geom_block"]
        mdl_lib.write_simplemodel_ps2_prop_mdl(
            filepath,
            scale_pos=scale_pos,
            dma_packets=dma_packets,
            material_names=texture_names,
            **kwargs,
        )
