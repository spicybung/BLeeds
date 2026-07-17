# BLeeds - Scripts for working with R* Leeds (GTA Stories, Chinatown Wars, Manhunt 2, etc) formats in Blender
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

__version__ = "1.0.10"

bl_info = {
    "name": "BLeeds",
    "author": "spicybung",
    "version": (1, 0, 10),
    "blender": (2, 90, 0),
    "location": "File > Import / Export",
    "description": "Rockstar Leeds import/export tools for Blender 2.90 and newer",
    "warning": "Work in progress",
    "category": "Import-Export",
}

import bpy
from bpy.utils import register_class, unregister_class
from bpy.props import BoolProperty, EnumProperty, FloatVectorProperty, IntProperty, StringProperty


# Blender 2.90 stores custom mesh attributes as ID properties because the
# generic Mesh.attributes API was added later.  These helpers keep the
# fallback in the package root so the add-on has no external compatibility
# module and can import under Blender 2.90's Python 3.7 runtime.
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

    # Full Gouraud shading must not use Blender's angle-based Auto Smooth.
    # Auto Smooth splits normals again at its default 30-degree threshold,
    # which makes the low-poly Stories meshes look flat even though every
    # polygon is marked smooth.
    set_mesh_auto_smooth(mesh, False)


def get_file_import_menu_type():
    return getattr(bpy.types, "TOPBAR_MT_file_import", getattr(bpy.types, "INFO_MT_file_import", None))


def get_file_export_menu_type():
    return getattr(bpy.types, "TOPBAR_MT_file_export", getattr(bpy.types, "INFO_MT_file_export", None))


def append_menu_callback(menu_type, draw_function):
    if menu_type is None or draw_function is None:
        return
    try:
        menu_type.append(draw_function)
    except Exception:
        pass


def remove_menu_callback(menu_type, draw_function):
    if menu_type is None or draw_function is None:
        return
    try:
        menu_type.remove(draw_function)
    except Exception:
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


def mesh_has_native_attributes(mesh):
    return mesh is not None and hasattr(mesh, "attributes") and getattr(mesh, "attributes", None) is not None


def get_native_mesh_attribute(mesh, name):
    if not mesh_has_native_attributes(mesh):
        return None
    try:
        return mesh.attributes.get(name)
    except Exception:
        return None


def remove_native_mesh_attribute(mesh, attribute):
    if not mesh_has_native_attributes(mesh) or attribute is None:
        return
    try:
        mesh.attributes.remove(attribute)
    except Exception:
        pass


def create_native_mesh_attribute(mesh, name, data_type, domain):
    if not mesh_has_native_attributes(mesh):
        return None
    try:
        return mesh.attributes.new(
            name=name,
            type=str(data_type or "INT").upper(),
            domain=str(domain or "POINT").upper(),
        )
    except Exception:
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
        values = self.attribute.get_values()
        if 0 <= self.index < len(values):
            return values[self.index]
        return self.attribute.default_value()

    @value.setter
    def value(self, new_value):
        values = self.attribute.get_values()
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
        return len(self.attribute.get_values())

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

    def get_values(self):
        if self.mesh is None:
            return []
        try:
            raw_values = self.mesh.get(self.value_key(), [])
        except Exception:
            raw_values = []
        try:
            return list(raw_values)
        except Exception:
            return []

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
                    cleaned_values.append(int(value))
                except Exception:
                    cleaned_values.append(0)
        try:
            self.mesh[self.value_key()] = cleaned_values
            self.mesh[self.type_key()] = self.data_type
            self.mesh[self.domain_key()] = self.domain
        except Exception:
            pass

    def ensure_length(self, count):
        values = self.get_values()
        count = max(0, int(count or 0))
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
            attribute = create_native_mesh_attribute(mesh, name, data_type_name, domain_name)
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
    "2DFX",
}


def stamp_bleeds_entity_type(obj, entity_type):
    if obj is None:
        return
    value = str(entity_type or "UNKNOWN").upper().strip()
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


def infer_bleeds_entity_type(obj):
    if obj is None:
        return "UNKNOWN"

    current = obj
    while current is not None:
        try:
            explicit = str(getattr(current, "bleeds_entity_type", "UNKNOWN") or "UNKNOWN").upper().strip()
            if explicit in _BLEEDS_ENTITY_TYPE_VALUES and explicit != "UNKNOWN":
                return explicit
        except Exception:
            pass
        try:
            explicit = str(current.get("blds_entity_type", "UNKNOWN") or "UNKNOWN").upper().strip()
            if explicit in _BLEEDS_ENTITY_TYPE_VALUES and explicit != "UNKNOWN":
                return explicit
        except Exception:
            pass
        try:
            mdl_type = getattr(current, "bleeds_mdl_type", current.get("bleeds_mdl_type", ""))
            mapped = map_mdl_type_to_entity_type(mdl_type)
            if mapped != "UNKNOWN":
                return mapped
        except Exception:
            pass
        try:
            if bool(current.get("bleeds_col2_object", False)):
                return "COLLISION"
            if str(current.get("blds_kind", "")).upper().strip() == "LEEDS_2DFX":
                return "2DFX"
            if (
                current.get("blds_kind") is not None
                or current.get("blds_res_id") is not None
                or current.get("blds_res_index") is not None
            ):
                return "OBJECT"
        except Exception:
            pass
        current = getattr(current, "parent", None)

    return "UNKNOWN"


from .gui import gui


_classes = [
    gui.IMPORT_OT_Stories_mdl,
    gui.IMPORT_SCENE_OT_leeds_anim,
    gui.DATA_PT_leeds_anim_bone_id,
    gui.IMPORT_OT_COL2,
    gui.EXPORT_OT_COL2,
    gui.IMPORT_OT_tex,
    gui.IMPORT_OT_leeds_world,
    gui.IMPORT_OT_CW_wbl,
    gui.EXPORT_OT_CW_wbl,
    gui.EXPORT_OT_MDL_Bake_LeedsScalePos,
    gui.EXPORT_PT_MDL_LeedsScalePos,
    gui.EXPORT_OT_MDL_StampSemanticAttributes,
    gui.EXPORT_PT_MDL_SemanticAttributes,
    gui.OBJECT_PT_MDL_Manhunt2Properties,
    gui.CW_InstanceProps,
    gui.OBJECT_PT_bleeds_entity_stamp,
    gui.CW_OT_LoadFromCustom,
    gui.CW_OT_SaveToCustom,
    gui.CW_MT_ExportChoice,
    gui.TOPBAR_MT_file_import_bleeds,
    gui.IMPORT_SCENE_OT_stories_lvz,
    gui.EXPORT_SCENE_OT_stories_lvz_img,
    gui.EXPORT_SCENE_OT_stories_mdl_ps2,
]

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



def unregister_lvz_img_progress_properties():
    for property_name in (
        "bleeds_lvz_img_progress", "bleeds_lvz_img_stage",
    ):
        if hasattr(bpy.types.WindowManager, property_name):
            delattr(bpy.types.WindowManager, property_name)


def register_bleeds_mdl_object_props():
    if not hasattr(bpy.types.Object, "bleeds_entity_type"):
        bpy.types.Object.bleeds_entity_type = EnumProperty(
            name="Leeds Type",
            description="BLeeds Leeds-engine asset classification",
            items=[
                ("UNKNOWN", "Unknown", "Not classified by BLeeds"),
                ("SIMPLE_MODEL", "SimpleModel", "Leeds prop or simple model"),
                ("PED_MODEL", "PedModel", "Leeds pedestrian or skinned actor model"),
                ("CUTSCENE_MODEL", "CutsceneModel", "Leeds cutscene actor model"),
                ("VEHICLE_MODEL", "VehModel", "Leeds vehicle model"),
                ("OBJECT", "World Object", "Placed Leeds world or map object"),
                ("COLLISION", "Collision", "Leeds collision object"),
                ("2DFX", "2DFX", "Leeds 2D effect helper"),
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
            name="MDL Type",
            description="Leeds MDL model class",
            items=[
                ("SIM", "SimpleModel", "Prop or simple model"),
                ("PED", "PedModel", "Pedestrian or skinned actor model"),
                ("CUT", "CutsceneModel", "Cutscene actor model"),
                ("VEH", "VehModel", "Vehicle model"),
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
    for prop_name in (
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

def register():
    register_bleeds_mdl_object_props()
    register_lvz_img_progress_properties()

    for cls in _classes:
        register_class(cls)

    bpy.types.Object.cw_instance = bpy.props.PointerProperty(
        type=gui.CW_InstanceProps
    )

    append_menu_callback(get_file_import_menu_type(), gui.cw_menu_import)
    append_menu_callback(get_file_export_menu_type(), gui.cw_menu_export)

def unregister():
    remove_menu_callback(get_file_import_menu_type(), gui.cw_menu_import)
    remove_menu_callback(get_file_export_menu_type(), gui.cw_menu_export)

    if hasattr(bpy.types.Object, "cw_instance"):
        del bpy.types.Object.cw_instance

    for cls in reversed(_classes):
        unregister_class(cls)

    unregister_bleeds_mdl_object_props()
    unregister_lvz_img_progress_properties()
