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
