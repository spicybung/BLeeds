# BLeeds - Scripts for working with R* Leeds formats in Blender
# Author: spicybung


def colorLayerDomain(layer):
    return getattr(layer, 'domain', 'CORNER')


def meshColorLayer(mesh):
    # Older Blender versions keep vertex colours in a different place.
    attributes = getattr(mesh, 'color_attributes', None)
    if attributes is not None:
        candidates = [attributes.get(name) for name in ('Color', 'Prelight', 'Col')]
        candidates.append(getattr(attributes, 'active_color', None))
    else:
        colors = getattr(mesh, 'vertex_colors', None)
        if colors is None:
            return None
        candidates = [colors.get(name) for name in ('Color', 'Prelight', 'Col')]
        candidates.append(colors.active)
    for layer in candidates:
        if layer is None:
            continue
        domain = colorLayerDomain(layer)
        if domain not in {'POINT', 'CORNER'}:
            continue
        expected = len(mesh.vertices) if domain == 'POINT' else len(mesh.loops)
        if expected and len(layer.data) == expected:
            return layer
    return None


def objectChildren(obj):
    # Blender 2.9 needs us to walk through the children ourselves.
    if obj is None:
        return []
    descendants = getattr(obj, 'children_recursive', None)
    if descendants is not None:
        return list(descendants)
    result = []
    pending = list(reversed(tuple(obj.children)))
    visited = set()
    while pending:
        child = pending.pop()
        if child in visited:
            continue
        visited.add(child)
        result.append(child)
        pending.extend(reversed(tuple(child.children)))
    return result


def setMeshLoopAttributes(mesh, vertex_uvs=None, uv_layer=None,
                          vertex_colors=None, color_layer=None,
                          colors_are_bytes=False):
    if uv_layer is None and color_layer is None:
        return

    loop_count = len(mesh.loops)
    if not loop_count:
        return

    loop_vertices = None
    numpy_module = None
    try:
        import numpy as numpy_module
        loop_vertices = numpy_module.empty(loop_count, dtype=numpy_module.int32)
        mesh.loops.foreach_get('vertex_index', loop_vertices)
    except (ImportError, AttributeError, TypeError, ValueError, RuntimeError):
        loop_vertices = None

    if uv_layer is not None and vertex_uvs:
        transferred = False
        if loop_vertices is not None:
            try:
                values = numpy_module.asarray(vertex_uvs, dtype=numpy_module.float32)
                if (len(values) and loop_vertices.min() >= 0
                        and loop_vertices.max() < len(values)):
                    uv_layer.data.foreach_set(
                        'uv', numpy_module.ascontiguousarray(values[loop_vertices]).reshape(-1)
                    )
                    transferred = True
            except (AttributeError, TypeError, ValueError, RuntimeError, IndexError):
                pass
        if not transferred:
            for loop in mesh.loops:
                vertex_index = int(loop.vertex_index)
                if 0 <= vertex_index < len(vertex_uvs):
                    uv_layer.data[loop.index].uv = vertex_uvs[vertex_index]

    if color_layer is not None and vertex_colors:
        transferred = False
        if loop_vertices is not None:
            try:
                values = numpy_module.asarray(vertex_colors, dtype=numpy_module.float32)
                if colors_are_bytes:
                    values = values * (1.0 / 255.0)
                if (len(values) and loop_vertices.min() >= 0
                        and loop_vertices.max() < len(values)):
                    color_layer.data.foreach_set(
                        'color', numpy_module.ascontiguousarray(values[loop_vertices]).reshape(-1)
                    )
                    transferred = True
            except (AttributeError, TypeError, ValueError, RuntimeError, IndexError):
                pass
        if not transferred:
            for loop in mesh.loops:
                vertex_index = int(loop.vertex_index)
                if 0 <= vertex_index < len(vertex_colors):
                    rgba = vertex_colors[vertex_index]
                    color_layer.data[loop.index].color = (
                        tuple(float(value) / 255.0 for value in rgba)
                        if colors_are_bytes else rgba
                    )


def setMeshPolygonMaterialIndices(mesh, indices):
    polygons = mesh.polygons
    count = min(len(polygons), len(indices))
    if count <= 0:
        return
    if count == len(polygons):
        try:
            import numpy as np
            polygons.foreach_set('material_index', np.asarray(indices, dtype=np.int32))
            return
        except (ImportError, AttributeError, TypeError, ValueError, RuntimeError):
            pass
    for polygon_index in range(count):
        polygons[polygon_index].material_index = int(indices[polygon_index])
