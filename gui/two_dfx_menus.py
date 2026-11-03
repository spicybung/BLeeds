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

import bpy


def is2dfxObject(obj):
    if obj is None:
        return False
    try:
        if str(obj.get("blds_kind", "")).upper().strip() == "LEEDS_2DFX":
            return True
        if str(obj.get("blds_entity_type", "")).upper().strip() == "2DFX":
            return True
        return obj.get("blds_2dfx_effect_type") is not None
    except Exception:
        return False


def getEffectValue(obj, name, default=None):
    try:
        return obj.get("blds_2dfx_" + name, default)
    except Exception:
        return default


def drawEffectText(box, label, value, *, hide_empty=False):
    if hide_empty and (value is None or value == ""):
        return
    row = box.row(align=True)
    row.label(text=str(label))
    row.label(text=str(value if value is not None else "Unknown"))


def drawEffectNumber(box, label, value, digits=4):
    try:
        if isinstance(value, float):
            value = ("{:0." + str(int(digits)) + "f}").format(value).rstrip("0").rstrip(".")
    except Exception:
        pass
    drawEffectText(box, label, value)


def drawEffectVector(box, label, values):
    try:
        text = "X {:.4f}   Y {:.4f}   Z {:.4f}".format(
            float(values[0]), float(values[1]), float(values[2])
        )
    except Exception:
        text = "Unknown"
    drawEffectText(box, label, text)


def formatEffectHex(value):
    try:
        return "0x{:08X}".format(int(value) & 0xFFFFFFFF)
    except Exception:
        return "Unknown"


class OBJECT_PT_BLeeds_2DFX(bpy.types.Panel):
    bl_idname = "OBJECT_PT_BLeeds_2DFX"
    bl_label = "BLeeds - 2D Effects"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"

    @classmethod
    def poll(cls, context):
        return is2dfxObject(getattr(context, "object", None))

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = False
        layout.use_property_decorate = False
        obj = context.object

        effect_type = int(getEffectValue(obj, "effect_type", -1))
        effect_name = str(getEffectValue(obj, "effect_type_name", "UNKNOWN")).replace("_", " ").title()

        heading = layout.box()
        row = heading.row(align=True)
        row.label(text=effect_name, icon="LIGHT" if effect_type == 0 else "EMPTY_AXIS")
        row.label(text="Effect {}".format(getEffectValue(obj, "global_index", "?")))
        drawEffectText(heading, "Source", getEffectValue(obj, "source", "GAME.DTZ"))
        drawEffectText(heading, "Game", getEffectValue(obj, "game", "Stories"))
        source_path = getEffectValue(obj, "source_path", "")
        if source_path:
            drawEffectText(heading, "File", source_path)

        transform = layout.box()
        transform.label(text="Position")
        drawEffectVector(transform, "Local Position", (
            getEffectValue(obj, "native_x", 0.0), getEffectValue(obj, "native_y", 0.0), getEffectValue(obj, "native_z", 0.0)
        ))
        drawEffectVector(transform, "World Position", (
            getEffectValue(obj, "world_x", obj.location.x),
            getEffectValue(obj, "world_y", obj.location.y),
            getEffectValue(obj, "world_z", obj.location.z),
        ))

        appearance = layout.box()
        appearance.label(text="Colour")
        rgba = tuple(int(getEffectValue(obj, "color_" + channel, 0)) for channel in "rgba")
        drawEffectText(appearance, "RGBA", "{}  {}  {}  {}".format(*rgba))
        drawEffectText(appearance, "Hex", "#{:02X}{:02X}{:02X}{:02X}".format(*[max(0, min(255, value)) for value in rgba]))

        details = layout.box()
        if effect_type == 0:
            details.label(text="Light Properties", icon="LIGHT_POINT")
            for label, key in (
                ("Distance", "light_distance"),
                ("Outer Range", "light_outer_range"),
                ("Size", "light_size"),
                ("Inner Range", "light_inner_range"),
            ):
                drawEffectNumber(details, label, getEffectValue(obj, key, 0.0))
            for label, key in (
                ("Flash", "light_flash"),
                ("Wet Weather", "light_wet"),
                ("Flare", "light_flare"),
                ("Shadow Intensity", "light_shadow_intensity"),
            ):
                drawEffectText(details, label, getEffectValue(obj, key, 0))
            drawEffectText(details, "Flags", formatEffectHex(getEffectValue(obj, "light_flags", 0)))
            drawEffectText(details, "Corona Texture", formatEffectHex(getEffectValue(obj, "light_corona_texture_ptr", 0)))
            drawEffectText(details, "Shadow Texture", formatEffectHex(getEffectValue(obj, "light_shadow_texture_ptr", 0)))
        elif effect_type == 1:
            details.label(text="Particle Properties", icon="PARTICLES")
            drawEffectText(details, "Subtype", getEffectValue(obj, "particle_subtype", "Unknown"))
            drawEffectNumber(details, "Scale", getEffectValue(obj, "particle_scale", 0.0))
            drawEffectVector(details, "Direction", (
                getEffectValue(obj, "direction_x", 0.0), getEffectValue(obj, "direction_y", 0.0), getEffectValue(obj, "direction_z", 0.0)
            ))
        elif effect_type == 2:
            details.label(text="Attractor Properties", icon="FORCE_FORCE")
            drawEffectText(details, "Subtype", getEffectValue(obj, "attractor_subtype", "Unknown"))
            drawEffectText(details, "Probability", getEffectValue(obj, "attractor_probability", "Unknown"))
            drawEffectVector(details, "Direction", (
                getEffectValue(obj, "attractor_direction_x", 0.0),
                getEffectValue(obj, "attractor_direction_y", 0.0),
                getEffectValue(obj, "attractor_direction_z", 0.0),
            ))
        elif effect_type == 3:
            details.label(text="Ped Behaviour Properties", icon="ARMATURE_DATA")
            drawEffectText(details, "Subtype", getEffectValue(obj, "ped_subtype", "Unknown"))
            drawEffectVector(details, "Direction", (
                getEffectValue(obj, "ped_direction_x", 0.0),
                getEffectValue(obj, "ped_direction_y", 0.0),
                getEffectValue(obj, "ped_direction_z", 0.0),
            ))
            drawEffectVector(details, "Rotation", (
                getEffectValue(obj, "ped_rotation_x", 0.0),
                getEffectValue(obj, "ped_rotation_y", 0.0),
                getEffectValue(obj, "ped_rotation_z", 0.0),
            ))
        else:
            details.label(text="Unknown 2DFX type {}".format(effect_type), icon="QUESTION")

        layout.prop(context.scene, "bleeds_show_mdl_attributes")
        if context.scene.bleeds_show_mdl_attributes:
            identity = layout.box()
            identity.label(text="Model")
            drawEffectText(identity, "Game Model", getEffectValue(obj, "game_model_id", getEffectValue(obj, "model_id", "Unknown")))
            model_hash = getEffectValue(obj, "model_hash", None)
            if model_hash is not None:
                drawEffectText(identity, "Model Hash", formatEffectHex(model_hash))
            drawEffectText(identity, "Model Effect", getEffectValue(obj, "model_effect_index", "Unknown"))
            drawEffectText(identity, "Entity", "{} {}".format(
                getEffectValue(obj, "entity_pool_name", "Unknown"),
                getEffectValue(obj, "entity_pool_index", "?"),
            ))
            drawEffectText(identity, "Parent Object", getEffectValue(obj, "parent_object", ""), hide_empty=True)
            drawEffectText(identity, "Resource ID", getEffectValue(obj, "visible_res_id", "Unknown"))
            drawEffectText(identity, "Placement ID", getEffectValue(obj, "row_link_id", "Unknown"))
            sector_x = getEffectValue(obj, "entity_sector_x", None)
            sector_y = getEffectValue(obj, "entity_sector_y", None)
            if sector_x is not None and sector_y is not None:
                drawEffectText(identity, "Map Sector", "{}, {}".format(sector_x, sector_y))

            diagnostics = layout.box()
            diagnostics.label(text="Record")
            drawEffectText(diagnostics, "Table Index", getEffectValue(obj, "global_index", "Unknown"))
            drawEffectText(diagnostics, "File Offset", formatEffectHex(getEffectValue(obj, "entry_off", 0)))
            drawEffectText(diagnostics, "Mapping", getEffectValue(obj, "mapping_basis", "Unknown"))


class DATA_PT_BLeeds_2DFX_Light(bpy.types.Panel):

    bl_idname = "DATA_PT_BLeeds_2DFX_Light"
    bl_label = "BLeeds - 2D Effects"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        obj = getattr(context, "object", None)
        return obj is not None and getattr(obj, "type", "") == "LIGHT" and is2dfxObject(obj)

    def draw(self, context):
        OBJECT_PT_BLeeds_2DFX.draw(self, context)
