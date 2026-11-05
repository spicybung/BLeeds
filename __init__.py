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

__version__ = "1.5.3.7b"

bl_info = {
    "name": "BLeeds 1.5.3.7b",
    "author": "spicybung",
    "version": (1, 5, 3, 7),
    "blender": (2, 90, 0),
    "location": "File > Import / Export",
    "description": "Importer/Exporter for Leeds Engine & RenderWare formats",
    "category": "Import-Export",
}

import bpy
from bpy.utils import register_class, unregister_class
from bpy.props import BoolProperty, EnumProperty, FloatVectorProperty, IntProperty, PointerProperty, StringProperty


def get_blender_version():
    return tuple(getattr(bpy.app, "version", (0, 0, 0)))


def set_mesh_auto_smooth(mesh, enabled=True):
    if mesh is None:
        return
    if hasattr(mesh, "use_auto_smooth"):
        try:
            mesh.use_auto_smooth = bool(enabled)
        except Exception:
            pass


def set_mesh_gouraud_shading(mesh, enabled=True):
    if mesh is None:
        return
    smooth = bool(enabled)
    try:
        for polygon in mesh.polygons:
            polygon.use_smooth = smooth
    except Exception:
        pass


    set_mesh_auto_smooth(mesh, False)


def get_file_import_menu_type():
    return getattr(bpy.types, "TOPBAR_MT_file_import", getattr(bpy.types, "INFO_MT_file_import", None))


def get_file_export_menu_type():
    return getattr(bpy.types, "TOPBAR_MT_file_export", getattr(bpy.types, "INFO_MT_file_export", None))


def append_menu_callback(menu_type, draw_function):
    if menu_type is None:
        raise RuntimeError("BLeeds could not find Blender's File menu type")
    if draw_function is None:
        raise RuntimeError("BLeeds menu callback is missing")
    menu_type.append(draw_function)


def remove_menu_callback(menu_type, draw_function):
    if menu_type is None or draw_function is None:
        return
    try:
        menu_type.remove(draw_function)
    except (RuntimeError, ValueError):
        pass


def update_mesh_data(mesh):
    if mesh is None:
        return
    try:
        mesh.update(calc_edges=False)
        return
    except TypeError:
        pass
    except Exception:
        return
    try:
        mesh.update()
    except Exception:
        pass


def get_mesh_domain_size(mesh, domain):
    if mesh is None:
        return 0
    domain_name = str(domain or "POINT").upper().strip()
    try:
        if domain_name == "POINT":
            return len(mesh.vertices)
        if domain_name == "FACE":
            return len(mesh.polygons)
        if domain_name == "CORNER":
            return len(mesh.loops)
        if domain_name == "EDGE":
            return len(mesh.edges)
    except Exception:
        return 0
    return 0


LEGACY_MESH_ATTRIBUTES = {
    ('POINT', 'INT'): 'vertex_layers_int',
    ('POINT', 'FLOAT'): 'vertex_layers_float',
    ('FACE', 'INT'): 'polygon_layers_int',
    ('FACE', 'FLOAT'): 'polygon_layers_float',
}


def mesh_has_native_attributes(mesh):
    if mesh is None:
        return False
    return getattr(mesh, 'attributes', None) is not None or hasattr(mesh, 'vertex_layers_int')


class NativeMeshAttribute:
    def __init__(self, mesh, name):
        self.mesh = mesh
        self.name = str(name)

    @property
    def data(self):
        return self.mesh.attributes.get(self.name).data

    @property
    def data_type(self):
        return self.mesh.attributes.get(self.name).data_type

    @property
    def domain(self):
        return self.mesh.attributes.get(self.name).domain


class LegacyMeshAttribute:
    def __init__(self, mesh, name, domain, data_type, collection_name):
        self.mesh = mesh
        self.name = str(name)
        self.domain = domain
        self.data_type = data_type
        self.collection_name = collection_name

    @property
    def data(self):
        return getattr(self.mesh, self.collection_name).get(self.name).data


def get_native_mesh_attribute(mesh, name):
    if mesh is None:
        return None
    attributes = getattr(mesh, 'attributes', None)
    if attributes is not None:
        attribute = attributes.get(name)
        if attribute is not None and hasattr(attribute, 'data'):
            return NativeMeshAttribute(mesh, name)
    for (domain, data_type), collection_name in LEGACY_MESH_ATTRIBUTES.items():
        collection = getattr(mesh, collection_name, None)
        if collection is not None and collection.get(name) is not None:
            return LegacyMeshAttribute(mesh, name, domain, data_type, collection_name)
    return None


def remove_native_mesh_attribute(mesh, attribute):
    if mesh is None or attribute is None:
        return
    if isinstance(attribute, LegacyMeshAttribute):
        collection = getattr(mesh, attribute.collection_name)
        layer = collection.get(attribute.name)
    else:
        collection = getattr(mesh, 'attributes', None)
        layer = collection.get(attribute.name) if collection is not None else None
    if collection is not None and layer is not None:
        collection.remove(layer)


def create_native_mesh_attribute(mesh, name, data_type, domain):
    if mesh is None:
        return None
    data_type = str(data_type or 'INT').upper()
    domain = str(domain or 'POINT').upper()
    try:
        attributes = getattr(mesh, 'attributes', None)
        if attributes is not None:
            attributes.new(name=name, type=data_type, domain=domain)
        else:
            collection_name = LEGACY_MESH_ATTRIBUTES.get((domain, data_type))
            collection = getattr(mesh, collection_name, None) if collection_name else None
            if collection is None:
                return None
            collection.new(name=name)
        return get_native_mesh_attribute(mesh, name)
    except (AttributeError, TypeError, ValueError, RuntimeError):
        return None


def get_fallback_attribute_key(name, suffix):
    safe_name = str(name).replace("\\", "_").replace("/", "_").replace('"', "_")
    return "bleeds_mesh_attribute_{}_{}".format(safe_name, suffix)


class FallbackMeshAttributeElement:
    def __init__(self, attribute, index):
        self.attribute = attribute
        self.index = int(index)

    @property
    def value(self):
        values = self.attribute.get_stored_values()
        if 0 <= self.index < len(values):
            return values[self.index]
        return self.attribute.default_value()

    @value.setter
    def value(self, new_value):
        values = self.attribute.get_stored_values()
        if 0 <= self.index < len(values):
            try:
                if self.attribute.data_type == 'FLOAT':
                    value = float(new_value)
                else:
                    value = int(new_value) & 0xFFFFFFFF
                    if value >= 0x80000000:
                        value -= 0x100000000
                values[self.index] = value
                return
            except (TypeError, ValueError, OverflowError):
                pass
        values = list(values)
        target_length = max(len(values), self.index + 1)
        if len(values) < target_length:
            values.extend([self.attribute.default_value()] * (target_length - len(values)))
        if self.attribute.data_type == "FLOAT":
            try:
                values[self.index] = float(new_value)
            except Exception:
                values[self.index] = 0.0
        else:
            try:
                values[self.index] = int(new_value)
            except Exception:
                values[self.index] = 0
        self.attribute.set_values(values)


class FallbackMeshAttributeData:
    def __init__(self, attribute):
        self.attribute = attribute

    def __len__(self):
        return len(self.attribute.get_stored_values())

    def __getitem__(self, index):
        item_index = int(index)
        if item_index < 0:
            item_index += len(self)
        if item_index < 0 or item_index >= len(self):
            raise IndexError(item_index)
        return FallbackMeshAttributeElement(self.attribute, item_index)

    def __iter__(self):
        for item_index in range(len(self)):
            yield FallbackMeshAttributeElement(self.attribute, item_index)

    def foreach_get(self, property_name, values):
        if str(property_name) != "value":
            raise AttributeError(property_name)
        source_values = self.attribute.get_values()
        limit = min(len(source_values), len(values))
        for item_index in range(limit):
            values[item_index] = source_values[item_index]

    def foreach_set(self, property_name, values):
        if str(property_name) != "value":
            raise AttributeError(property_name)
        self.attribute.set_values(list(values))


class FallbackMeshAttribute:
    def __init__(self, mesh, name, data_type="INT", domain="POINT"):
        self.mesh = mesh
        self.name = str(name)
        self.data_type = str(data_type or "INT").upper().strip()
        self.domain = str(domain or "POINT").upper().strip()
        self.data = FallbackMeshAttributeData(self)

    def default_value(self):
        return 0.0 if self.data_type == "FLOAT" else 0

    def value_key(self):
        return get_fallback_attribute_key(self.name, "values")

    def type_key(self):
        return get_fallback_attribute_key(self.name, "type")

    def domain_key(self):
        return get_fallback_attribute_key(self.name, "domain")

    def get_stored_values(self):
        if self.mesh is None:
            return []
        try:
            values = self.mesh.get(self.value_key(), [])
            if hasattr(values, '__len__') and hasattr(values, '__getitem__') and not isinstance(values, (str, bytes)):
                return values
            return []
        except (AttributeError, TypeError, RuntimeError):
            return []

    def get_values(self):
        return list(self.get_stored_values())

    def set_values(self, values):
        if self.mesh is None:
            return
        cleaned_values = []
        if self.data_type == "FLOAT":
            for value in values:
                try:
                    cleaned_values.append(float(value))
                except Exception:
                    cleaned_values.append(0.0)
        else:
            for value in values:
                try:
                    number = int(value) & 0xFFFFFFFF
                    cleaned_values.append(number - 0x100000000 if number >= 0x80000000 else number)
                except Exception:
                    cleaned_values.append(0)
        try:
            self.mesh[self.value_key()] = cleaned_values
            self.mesh[self.type_key()] = self.data_type
            self.mesh[self.domain_key()] = self.domain
        except Exception:
            pass

    def ensure_length(self, count):
        count = max(0, int(count or 0))
        stored = self.get_stored_values()
        if (len(stored) == count and self.value_key() in self.mesh
                and self.mesh.get(self.type_key()) == self.data_type
                and self.mesh.get(self.domain_key()) == self.domain):
            return self
        values = list(stored)
        if len(values) < count:
            values.extend([self.default_value()] * (count - len(values)))
        elif len(values) > count and count > 0:
            values = values[:count]
        self.set_values(values)
        return self


def get_fallback_mesh_attribute(mesh, name):
    if mesh is None:
        return None
    value_key = get_fallback_attribute_key(name, "values")
    try:
        if value_key not in mesh:
            return None
        data_type = str(mesh.get(get_fallback_attribute_key(name, "type"), "INT") or "INT")
        domain = str(mesh.get(get_fallback_attribute_key(name, "domain"), "POINT") or "POINT")
        return FallbackMeshAttribute(mesh, name, data_type, domain).ensure_length(
            get_mesh_domain_size(mesh, domain)
        )
    except Exception:
        return None


def get_mesh_attribute(mesh, name):
    attribute = get_native_mesh_attribute(mesh, name)
    if attribute is not None:
        return attribute
    return get_fallback_mesh_attribute(mesh, name)


def remove_mesh_attribute(mesh, attribute):
    if attribute is None:
        return
    if isinstance(attribute, FallbackMeshAttribute):
        for suffix in ("values", "type", "domain"):
            key = get_fallback_attribute_key(attribute.name, suffix)
            try:
                if key in mesh:
                    del mesh[key]
            except Exception:
                pass
        return
    remove_native_mesh_attribute(mesh, attribute)


def ensure_mesh_attribute(mesh, name, data_type, domain="POINT"):
    # Use the mesh layers this Blender version actually supports.
    if mesh is None:
        return None
    data_type_name = str(data_type or "INT").upper().strip()
    domain_name = str(domain or "POINT").upper().strip()
    update_mesh_data(mesh)
    expected_count = get_mesh_domain_size(mesh, domain_name)

    if mesh_has_native_attributes(mesh):
        attribute = get_native_mesh_attribute(mesh, name)
        if attribute is not None:
            existing_domain = str(getattr(attribute, "domain", domain_name) or domain_name).upper().strip()
            existing_type = str(getattr(attribute, "data_type", data_type_name) or data_type_name).upper().strip()
            if existing_domain != domain_name or existing_type != data_type_name:
                remove_native_mesh_attribute(mesh, attribute)
                attribute = None
        if attribute is None:
            previous = get_fallback_mesh_attribute(mesh, name)
            attribute = create_native_mesh_attribute(mesh, name, data_type_name, domain_name)
            if (attribute is not None and previous is not None
                    and previous.domain == domain_name and previous.data_type == data_type_name
                    and len(attribute.data) == len(previous.data)):
                attribute.data.foreach_set('value', previous.get_values())
        if attribute is not None:
            return attribute

    return FallbackMeshAttribute(mesh, name, data_type_name, domain_name).ensure_length(expected_count)


def get_or_create_corner_color_layer(mesh, name="Col"):
    if mesh is None:
        return None
    if hasattr(mesh, "color_attributes"):
        try:
            existing = mesh.color_attributes.get(name)
            if existing is not None:
                return existing
        except Exception:
            pass
        try:
            return mesh.color_attributes.new(name=name, type="BYTE_COLOR", domain="CORNER")
        except Exception:
            pass
    if hasattr(mesh, "vertex_colors"):
        try:
            existing = mesh.vertex_colors.get(name)
            if existing is not None:
                return existing
        except Exception:
            pass
        try:
            return mesh.vertex_colors.new(name=name)
        except TypeError:
            try:
                return mesh.vertex_colors.new(name)
            except Exception:
                return None
        except Exception:
            return None
    return None


def set_active_object(context, obj):
    if obj is None:
        return
    try:
        context.view_layer.objects.active = obj
        return
    except Exception:
        pass
    try:
        bpy.context.scene.objects.active = obj
    except Exception:
        pass


def set_object_selected(obj, selected=True):
    if obj is None:
        return
    if hasattr(obj, "select_set"):
        try:
            obj.select_set(bool(selected))
            return
        except Exception:
            pass
    try:
        obj.select = bool(selected)
    except Exception:
        pass


_BLEEDS_ENTITY_TYPE_VALUES = {
    "UNKNOWN",
    "OBJECT",
    "SIMPLE_MODEL",
    "PED_MODEL",
    "CUTSCENE_MODEL",
    "VEHICLE_MODEL",
    "COLLISION",
    "2D_EFFECT",
    "2DFX",
}


def stamp_bleeds_entity_type(obj, entity_type):
    if obj is None:
        return
    value = str(entity_type or "UNKNOWN").upper().strip()
    if value in {"2D_EFFECT", "2DFX"}:
        from .ops.object_types import effectRole
        value = effectRole(obj)
    if value not in _BLEEDS_ENTITY_TYPE_VALUES:
        value = "UNKNOWN"
    try:
        obj.bleeds_entity_type = value
    except Exception:
        pass
    try:
        obj["blds_entity_type"] = value
    except Exception:
        pass


def map_mdl_type_to_entity_type(mdl_type):
    value = str(mdl_type or "").upper().strip()
    return {
        "SIM": "SIMPLE_MODEL",
        "SIMPLEMODEL": "SIMPLE_MODEL",
        "PED": "PED_MODEL",
        "PEDMODEL": "PED_MODEL",
        "CLUMP": "PED_MODEL",
        "CLUMPMODEL": "PED_MODEL",
        "CUT": "CUTSCENE_MODEL",
        "CUTSCENEMODEL": "CUTSCENE_MODEL",
        "VEH": "VEHICLE_MODEL",
        "VEHMODEL": "VEHICLE_MODEL",
        "VEHICLEMODEL": "VEHICLE_MODEL",
    }.get(value, "UNKNOWN")


def get_bleeds_type_owner(obj):
    current = obj
    while current is not None:
        try:
            explicit = str(getattr(current, "bleeds_entity_type", "UNKNOWN") or "UNKNOWN").upper().strip()
            if explicit in _BLEEDS_ENTITY_TYPE_VALUES and explicit != "UNKNOWN":
                return current
        except Exception:
            pass
        try:
            explicit = str(current.get("blds_entity_type", "UNKNOWN") or "UNKNOWN").upper().strip()
            if explicit in _BLEEDS_ENTITY_TYPE_VALUES and explicit != "UNKNOWN":
                return current
        except Exception:
            pass
        try:
            if bool(getattr(current, "bleeds_is_mdl_root", False)) or bool(current.get("bleeds_is_mdl_root", False)):
                return current
        except Exception:
            pass
        current = getattr(current, "parent", None)
    return obj


def determine_bleeds_entity_type(obj):
    if obj is None:
        return 'UNKNOWN'
    from .ops.object_types import describeObject
    info = describeObject(obj)
    role = info['role']
    if role == 'MODEL':
        return {'SimpleModel': 'SIMPLE_MODEL', 'ClumpModel': 'PED_MODEL',
                'ClumpModel (CUT)': 'CUTSCENE_MODEL', 'VehicleModel': 'VEHICLE_MODEL'}.get(
                    info['model_type'], 'OBJECT')
    return {'COLLISION': 'COLLISION', '2D_EFFECT': '2D_EFFECT', '2DFX': '2DFX', 'LIGHT': 'LIGHT',
            'EMPTY': 'EMPTY', 'ARMATURE': 'ARMATURE', 'DONT_EXPORT': 'DONT_EXPORT'}.get(role, 'UNKNOWN')


from .gui import gui


_classes = [
    gui.OBJECT_PT_BLeeds_Object,
    gui.BLEEDS_PG_animation_viewer,
    gui.BLEEDS_UL_animation_actions,
    gui.BLEEDS_OT_preview_animation,
    gui.BLEEDS_OT_animation_rest_pose,
    gui.BLEEDS_OT_animation_finish_preview,
    gui.BLEEDS_OT_animation_playback,
    gui.BLEEDS_OT_animation_keyframe,
    gui.VIEW3D_PT_bleeds_animation_viewer,
    gui.IMPORT_OT_BLeeds_MobileTxd,
    gui.EXPORT_OT_BLeeds_MobileTxd,
    gui.IMPORT_OT_BLeeds_MobileImg,
    gui.EXPORT_OT_BLeeds_MobileImg,
    gui.VIEW3D_PT_bleeds_mobile_files,
    gui.IMPORT_OT_Stories_mdl,
    gui.IMPORT_OT_BLeeds_DFF,
    gui.EXPORT_OT_BLeeds_DFF,
    gui.IMPORT_SCENE_OT_leeds_anim,
    gui.EXPORT_SCENE_OT_leeds_anim,
    gui.IMPORT_SCENE_OT_bleeds_manhunt_ifp,
    gui.DATA_PT_leeds_anim_bone_id,
    gui.IMPORT_OT_COL2,
    gui.EXPORT_OT_COL2,
    gui.IMPORT_OT_tex,
    gui.EXPORT_OT_tex,
    gui.SCENE_PT_bleeds_texture_io,
    gui.IMPORT_OT_leeds_world,
    gui.IMPORT_OT_CW_wbl,
    gui.EXPORT_OT_CW_wbl,
    gui.EXPORT_OT_MDL_Bake_LeedsScalePos,
    gui.EXPORT_PT_MDL_LeedsScalePos,
    gui.EXPORT_OT_MDL_StampSemanticAttributes,
    gui.EXPORT_PT_MDL_SemanticAttributes,
    gui.OBJECT_OT_BLeeds_SnapArmature,
    gui.OBJECT_PT_BLeeds_SnapArmature,
    gui.OBJECT_PT_MDL_Manhunt2Properties,
    gui.VIEW3D_GGT_BLeeds_2D_Effects,
    gui.OBJECT_OT_BLeeds_EffectPointLight,
    gui.OBJECT_PT_BLeeds_2D_Effects,
    gui.DATA_PT_BLeeds_2D_Effects_Light,
    gui.CW_MT_ExportChoice,
    gui.TOPBAR_MT_file_import_bleeds,
    gui.IMPORT_SCENE_OT_stories_lvz,
    gui.EXPORT_SCENE_OT_stories_lvz_img,
    gui.EXPORT_SCENE_OT_stories_mdl_ps2,
]

def register_bleeds_texture_scene_props():
    if not hasattr(bpy.types.Scene, "bleeds_texture_bit_depth"):
        bpy.types.Scene.bleeds_texture_bit_depth = EnumProperty(
            name="Bit Depth",
            description="Export indexed textures; source depths above 8 bpp are reduced to 8 bpp",
            items=[
                ("AUTO", "Auto", "Preserve imported 4 bpp; export other images at 8 bpp"),
                ("4", "4 bpp", "Quantize to a 16-color RGBA palette"),
                ("8", "8 bpp", "Quantize to a 256-color RGBA palette"),
            ],
            default="AUTO",
        )
    if not hasattr(bpy.types.Scene, "bleeds_texture_format"):
        bpy.types.Scene.bleeds_texture_format = EnumProperty(
            name="Texture Format",
            description="Leeds texture container extension",
            items=[
                ("CHK", ".chk", "Leeds CHK texture container"),
                ("XTX", ".xtx", "Leeds XTX texture container"),
                ("TEX", ".tex", "Leeds TEX texture container"),
            ],
            default="XTX",
        )
    if not hasattr(bpy.types.Scene, "bleeds_texture_platform"):
        bpy.types.Scene.bleeds_texture_platform = EnumProperty(
            name="Platform",
            description="Target Leeds texture platform",
            items=[
                ("PS2", "PS2", "PlayStation 2 texture layout"),
                ("PSP", "PSP", "PlayStation Portable texture layout"),
            ],
            default="PS2",
        )


def unregister_bleeds_texture_scene_props():
    for property_name in ("bleeds_texture_format", "bleeds_texture_platform", "bleeds_texture_bit_depth"):
        if hasattr(bpy.types.Scene, property_name):
            delattr(bpy.types.Scene, property_name)


def register_lvz_img_progress_properties():
    if not hasattr(bpy.types.WindowManager, "bleeds_lvz_img_progress"):
        bpy.types.WindowManager.bleeds_lvz_img_progress = IntProperty(
            name="LVZ + IMG Import Progress",
            description="Current LVZ + IMG import completion percentage",
            default=0,
            min=0,
            max=100,
            subtype="PERCENTAGE",
        )
    if not hasattr(bpy.types.WindowManager, "bleeds_lvz_img_stage"):
        bpy.types.WindowManager.bleeds_lvz_img_stage = StringProperty(
            name="LVZ + IMG Import Stage",
            description="Current LVZ + IMG import stage",
            default="",
        )
    if not hasattr(bpy.types.WindowManager, "bleeds_lvz_img_status"):
        bpy.types.WindowManager.bleeds_lvz_img_status = StringProperty(
            name="Leeds Stories Map Import Status",
            description="Detailed live status for the active Leeds Stories map import",
            default="",
        )


def unregister_lvz_img_progress_properties():
    for property_name in (
        "bleeds_lvz_img_progress", "bleeds_lvz_img_stage", "bleeds_lvz_img_status",
    ):
        if hasattr(bpy.types.WindowManager, property_name):
            delattr(bpy.types.WindowManager, property_name)


def register_bleeds_mdl_object_props():
    from .ops.object_types import OBJECT_TYPE_ITEMS
    gui.effects.registerEffectProperties()
    if not hasattr(bpy.types.Object, 'bleeds_object_type'):
        bpy.types.Object.bleeds_object_type = EnumProperty(
            name='Object Type', items=OBJECT_TYPE_ITEMS, default='AUTO')
    if not hasattr(bpy.types.Object, "bleeds_entity_type"):
        bpy.types.Object.bleeds_entity_type = EnumProperty(
            name="Leeds Type",
            description="BLeeds Leeds-engine asset classification",
            items=[
                ("UNKNOWN", "Unknown", "Not classified by BLeeds"),
                ("SIMPLE_MODEL", "SimpleModel", "Leeds prop or simple model"),
                ("PED_MODEL", "ClumpModel", "Leeds pedestrian or skinned actor model"),
                ("CUTSCENE_MODEL", "ClumpModel (CUT)", "Leeds cutscene actor model"),
                ("VEHICLE_MODEL", "VehicleModel", "Leeds vehicle model"),
                ("OBJECT", "World Object", "Placed Leeds world or map object"),
                ("COLLISION", "Collision", "Leeds collision object"),
                ("2D_EFFECT", "2D Effect", "Leeds 2D effect"),
                ("2DFX", "2DFX", "GTA III and GTA VC effects"),
            ],
            default="UNKNOWN",
        )

    if not hasattr(bpy.types.Object, "bleeds_is_mdl_root"):
        bpy.types.Object.bleeds_is_mdl_root = BoolProperty(
            name="BLeeds MDL Root",
            description="Marks this object as the root of an imported BLeeds MDL",
            default=False,
        )

    if not hasattr(bpy.types.Object, "bleeds_mdl_platform"):
        bpy.types.Object.bleeds_mdl_platform = EnumProperty(
            name="Platform",
            description="Leeds model platform for this MDL",
            items=[
                ("PS2", "PS2", "PlayStation 2"),
                ("PSP", "PSP", "PlayStation Portable"),
                ("PC", "PC", "Windows PC"),
            ],
            default="PS2",
        )

    if not hasattr(bpy.types.Object, "bleeds_model_game"):
        bpy.types.Object.bleeds_model_game = EnumProperty(
            name="3D Models",
            description="Leeds 3D model family",
            items=[
                ("LCS", "LCS", "Grand Theft Auto: Liberty City Stories"),
                ("VCS", "VCS", "Grand Theft Auto: Vice City Stories"),
                ("MH2", "MH2", "Manhunt 2"),
            ],
            default="VCS",
        )

    if not hasattr(bpy.types.Object, "bleeds_mdl_type"):
        bpy.types.Object.bleeds_mdl_type = EnumProperty(
            name="MDL Layout",
            description="Imported model type",
            items=[
                ("SIM", "SimpleModel", "Static/simple Leeds model serialization"),
                ("PED", "ClumpModel", "Skinned or hierarchical Leeds clump serialization"),
                ("CUT", "ClumpModel (CUT)", "Cutscene clump serialization"),
                ("VEH", "VehicleModel", "Vehicle-oriented Leeds model serialization"),
            ],
            default="SIM",
        )

    if not hasattr(bpy.types.Object, "bleeds_mdl_filepath"):
        bpy.types.Object.bleeds_mdl_filepath = StringProperty(
            name="Source File",
            description="Original MDL file path used for import",
            default="",
            subtype="FILE_PATH",
        )

    if not hasattr(bpy.types.Object, "bleeds_imported_export_mode"):
        bpy.types.Object.bleeds_imported_export_mode = EnumProperty(
            name="Internal PED Rebuild",
            description="Imported PEDs rebuild from live mesh data",
            items=[("REBUILD", "Rebuild", "Rebuild using calculated live data and ped_atomic_bind basis")],
            default="REBUILD",
        )

    if not hasattr(bpy.types.Object, "bleeds_export_use_normals"):
        bpy.types.Object.bleeds_export_use_normals = BoolProperty(
            name="Export Normals",
            description="Export normals into PS2 MDL DMA/VIF geometry streams",
            default=True,
        )

    if not hasattr(bpy.types.Object, "bleeds_export_gouraud_shading"):
        bpy.types.Object.bleeds_export_gouraud_shading = BoolProperty(
            name="Gouraud Shading",
            description="Use smooth per-vertex normals when exporting Leeds MDL geometry",
            default=True,
        )

    if not hasattr(bpy.types.Object, "bleeds_leeds_scale_base"):
        bpy.types.Object.bleeds_leeds_scale_base = FloatVectorProperty(
            name="Leeds Scale (Base)",
            description="Base in-game scale stored by the MDL",
            size=3,
            default=(1.0, 1.0, 1.0),
            subtype="XYZ",
        )

    if not hasattr(bpy.types.Object, "bleeds_leeds_pos_base"):
        bpy.types.Object.bleeds_leeds_pos_base = FloatVectorProperty(
            name="Leeds Pos (Base)",
            description="Base in-game position stored by the MDL",
            size=3,
            default=(0.0, 0.0, 0.0),
            subtype="TRANSLATION",
        )

def unregister_bleeds_mdl_object_props():
    gui.effects.unregisterEffectProperties()
    for prop_name in (
        "bleeds_object_type",
        "bleeds_entity_type",
        "bleeds_is_mdl_root",
        "bleeds_mdl_platform",
        "bleeds_model_game",
        "bleeds_mdl_type",
        "bleeds_mdl_filepath",
        "bleeds_imported_export_mode",
        "bleeds_export_use_normals",
        "bleeds_export_gouraud_shading",
        "bleeds_leeds_scale_base",
        "bleeds_leeds_pos_base",
    ):
        if hasattr(bpy.types.Object, prop_name):
            delattr(bpy.types.Object, prop_name)

def safe_register_class(cls):
    class_name = getattr(cls, "__name__", "")
    bl_idname = getattr(cls, "bl_idname", "")

    existing = getattr(bpy.types, class_name, None)
    if existing is not None and existing is not cls:
        try:
            unregister_class(existing)
        except Exception:
            pass

    if bl_idname:
        for type_name in dir(bpy.types):
            existing_type = getattr(bpy.types, type_name, None)
            if existing_type is None or existing_type is cls:
                continue
            if getattr(existing_type, "bl_idname", None) == bl_idname:
                try:
                    unregister_class(existing_type)
                except Exception:
                    pass
                break

    try:
        register_class(cls)
    except ValueError as exc:
        if "already registered" not in str(exc).lower():
            raise
        existing = getattr(bpy.types, class_name, None)
        if existing is not None:
            try:
                unregister_class(existing)
            except Exception:
                pass
        register_class(cls)


def register():
    registered_classes = []
    import_menu = get_file_import_menu_type()
    export_menu = get_file_export_menu_type()
    import_hooked = False
    export_hooked = False

    try:
        register_bleeds_mdl_object_props()
        register_bleeds_texture_scene_props()
        register_lvz_img_progress_properties()
        bpy.types.Scene.bleeds_reference_armature = PointerProperty(
            name="Reference Armature", type=bpy.types.Object, poll=gui.isArmatureObject)
        bpy.types.Scene.bleeds_reference_use_pose = BoolProperty(
            name="Use Current Pose", default=True)
        bpy.types.Scene.bleeds_reference_weights = BoolProperty(
            name="Use Reference Weights",
            description="Transfer the reference mesh weights to the target when snapping",
            default=False)
        bpy.types.Scene.bleeds_show_mdl_attributes = BoolProperty(
            name="Show Details", default=False)

        for cls in _classes:
            safe_register_class(cls)
            registered_classes.append(cls)

        bpy.types.Scene.bleeds_animation_viewer = PointerProperty(type=gui.BLEEDS_PG_animation_viewer)
        bpy.types.Material.bleeds_mh2_texture_name = StringProperty(
            name='MH2 Texture Name', description='Texture dictionary entry used by the exported MH2 PC material',
            default='')

        append_menu_callback(import_menu, gui.cw_menu_import)
        import_hooked = True
        append_menu_callback(export_menu, gui.cw_menu_export)
        export_hooked = True


        if not hasattr(bpy.types, gui.TOPBAR_MT_file_import_bleeds.bl_idname):
            raise RuntimeError("BLeeds import menu class was not registered")
        if not hasattr(bpy.types, gui.CW_MT_ExportChoice.bl_idname):
            raise RuntimeError("BLeeds export menu class was not registered")

        from .ops import uv_playback
        uv_playback.registerNativeUvPlayback()

        print("BLeeds %s registered successfully: classes=%d, import_menu=yes, export_menu=yes" % (__version__, len(registered_classes)))

    except Exception as exc:
        from .ops import uv_playback
        uv_playback.unregisterNativeUvPlayback()

        if export_hooked:
            remove_menu_callback(export_menu, gui.cw_menu_export)
        if import_hooked:
            remove_menu_callback(import_menu, gui.cw_menu_import)
        if hasattr(bpy.types.Scene, 'bleeds_animation_viewer'):
            del bpy.types.Scene.bleeds_animation_viewer
        if hasattr(bpy.types.Material, 'bleeds_mh2_texture_name'):
            del bpy.types.Material.bleeds_mh2_texture_name
        for cls in reversed(registered_classes):
            try:
                unregister_class(cls)
            except Exception:
                pass
        unregister_bleeds_mdl_object_props()
        unregister_bleeds_texture_scene_props()
        unregister_lvz_img_progress_properties()
        for prop_name in ("bleeds_reference_armature", "bleeds_reference_use_pose", "bleeds_reference_weights", "bleeds_show_mdl_attributes"):
            if hasattr(bpy.types.Scene, prop_name):
                delattr(bpy.types.Scene, prop_name)
        print("BLeeds %s registration FAILED: %s" % (__version__, exc))
        raise

def unregister():
    from .ops import uv_playback
    uv_playback.unregisterNativeUvPlayback()
    remove_menu_callback(get_file_import_menu_type(), gui.cw_menu_import)
    remove_menu_callback(get_file_export_menu_type(), gui.cw_menu_export)

    for scene in bpy.data.scenes:
        if scene.bleeds_animation_viewer.preview_rig is not None:
            try:
                gui.animationViewerRestore(bpy.context, scene=scene)
            except (ValueError, RuntimeError) as exc:
                print('BLeeds could not restore the animation preview: {}'.format(exc))
    if hasattr(bpy.types.Scene, 'bleeds_animation_viewer'):
        del bpy.types.Scene.bleeds_animation_viewer
    if hasattr(bpy.types.Material, 'bleeds_mh2_texture_name'):
        del bpy.types.Material.bleeds_mh2_texture_name

    for cls in reversed(_classes):
        unregister_class(cls)

    unregister_bleeds_mdl_object_props()
    unregister_bleeds_texture_scene_props()
    unregister_lvz_img_progress_properties()
    for prop_name in ("bleeds_reference_armature", "bleeds_reference_use_pose", "bleeds_reference_weights", "bleeds_show_mdl_attributes"):
        if hasattr(bpy.types.Scene, prop_name):
            delattr(bpy.types.Scene, prop_name)
