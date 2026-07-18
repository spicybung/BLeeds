# BLeeds - readable GAME.DTZ 2DFX inspection

import bpy


def _is_2dfx_object(obj):
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


def _value(obj, name, default=None):
    try:
        return obj.get("blds_2dfx_" + name, default)
    except Exception:
        return default


def _text(box, label, value, *, hide_empty=False):
    if hide_empty and (value is None or value == ""):
        return
    row = box.row(align=True)
    row.label(text=str(label))
    row.label(text=str(value if value is not None else "Unknown"))


def _number(box, label, value, digits=4):
    try:
        if isinstance(value, float):
            value = ("{:0." + str(int(digits)) + "f}").format(value).rstrip("0").rstrip(".")
    except Exception:
        pass
    _text(box, label, value)


def _vector(box, label, values):
    try:
        text = "X {:.4f}   Y {:.4f}   Z {:.4f}".format(
            float(values[0]), float(values[1]), float(values[2])
        )
    except Exception:
        text = "Unknown"
    _text(box, label, text)


def _hex(value):
    try:
        return "0x{:08X}".format(int(value) & 0xFFFFFFFF)
    except Exception:
        return "Unknown"


class OBJECT_PT_BLeeds_2DFX(bpy.types.Panel):
    bl_idname = "OBJECT_PT_BLeeds_2DFX"
    bl_label = "BLeeds - 2DFX"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"

    @classmethod
    def poll(cls, context):
        return _is_2dfx_object(getattr(context, "object", None))

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = False
        layout.use_property_decorate = False
        obj = context.object

        effect_type = int(_value(obj, "effect_type", -1))
        effect_name = str(_value(obj, "effect_type_name", "UNKNOWN")).replace("_", " ").title()

        heading = layout.box()
        row = heading.row(align=True)
        row.label(text=effect_name, icon="LIGHT" if effect_type == 0 else "EMPTY_AXIS")
        row.label(text="Effect {}".format(_value(obj, "global_index", "?")))
        _text(heading, "Source", _value(obj, "source", "GAME.DTZ"))
        _text(heading, "Game", _value(obj, "game", "Stories"))
        source_path = _value(obj, "source_path", "")
        if source_path:
            _text(heading, "File", source_path)

        identity = layout.box()
        identity.label(text="Identity and Ownership")
        _text(identity, "Game Model", _value(obj, "game_model_id", _value(obj, "model_id", "Unknown")))
        model_hash = _value(obj, "model_hash", None)
        if model_hash is not None:
            _text(identity, "Model Hash", _hex(model_hash))
        _text(identity, "Model Effect", _value(obj, "model_effect_index", "Unknown"))
        _text(identity, "Entity", "{} {}".format(
            _value(obj, "entity_pool_name", "Unknown"),
            _value(obj, "entity_pool_index", "?"),
        ))
        _text(identity, "Parent Object", _value(obj, "parent_object", ""), hide_empty=True)
        _text(identity, "Visible RES", _value(obj, "visible_res_id", "Unknown"))
        _text(identity, "Row Link", _value(obj, "row_link_id", "Unknown"))
        sector_x = _value(obj, "entity_sector_x", None)
        sector_y = _value(obj, "entity_sector_y", None)
        if sector_x is not None and sector_y is not None:
            _text(identity, "Map Sector", "{}, {}".format(sector_x, sector_y))

        transform = layout.box()
        transform.label(text="Position")
        _vector(transform, "Model Space", (
            _value(obj, "native_x", 0.0), _value(obj, "native_y", 0.0), _value(obj, "native_z", 0.0)
        ))
        _vector(transform, "World Space", (
            _value(obj, "world_x", obj.location.x),
            _value(obj, "world_y", obj.location.y),
            _value(obj, "world_z", obj.location.z),
        ))

        appearance = layout.box()
        appearance.label(text="Colour")
        rgba = tuple(int(_value(obj, "color_" + channel, 0)) for channel in "rgba")
        _text(appearance, "RGBA", "{}  {}  {}  {}".format(*rgba))
        _text(appearance, "Hex", "#{:02X}{:02X}{:02X}{:02X}".format(*[max(0, min(255, value)) for value in rgba]))

        details = layout.box()
        if effect_type == 0:
            details.label(text="Light Properties", icon="LIGHT_POINT")
            for label, key in (
                ("Distance", "light_distance"),
                ("Outer Range", "light_outer_range"),
                ("Size", "light_size"),
                ("Inner Range", "light_inner_range"),
            ):
                _number(details, label, _value(obj, key, 0.0))
            for label, key in (
                ("Flash", "light_flash"),
                ("Wet Weather", "light_wet"),
                ("Flare", "light_flare"),
                ("Shadow Intensity", "light_shadow_intensity"),
            ):
                _text(details, label, _value(obj, key, 0))
            _text(details, "Flags", _hex(_value(obj, "light_flags", 0)))
            _text(details, "Corona Texture", _hex(_value(obj, "light_corona_texture_ptr", 0)))
            _text(details, "Shadow Texture", _hex(_value(obj, "light_shadow_texture_ptr", 0)))
        elif effect_type == 1:
            details.label(text="Particle Properties", icon="PARTICLES")
            _text(details, "Subtype", _value(obj, "particle_subtype", "Unknown"))
            _number(details, "Scale", _value(obj, "particle_scale", 0.0))
            _vector(details, "Direction", (
                _value(obj, "direction_x", 0.0), _value(obj, "direction_y", 0.0), _value(obj, "direction_z", 0.0)
            ))
        elif effect_type == 2:
            details.label(text="Attractor Properties", icon="FORCE_FORCE")
            _text(details, "Subtype", _value(obj, "attractor_subtype", "Unknown"))
            _text(details, "Probability", _value(obj, "attractor_probability", "Unknown"))
            _vector(details, "Direction", (
                _value(obj, "attractor_direction_x", 0.0),
                _value(obj, "attractor_direction_y", 0.0),
                _value(obj, "attractor_direction_z", 0.0),
            ))
        elif effect_type == 3:
            details.label(text="Ped Behaviour Properties", icon="ARMATURE_DATA")
            _text(details, "Subtype", _value(obj, "ped_subtype", "Unknown"))
            _vector(details, "Direction", (
                _value(obj, "ped_direction_x", 0.0),
                _value(obj, "ped_direction_y", 0.0),
                _value(obj, "ped_direction_z", 0.0),
            ))
            _vector(details, "Rotation", (
                _value(obj, "ped_rotation_x", 0.0),
                _value(obj, "ped_rotation_y", 0.0),
                _value(obj, "ped_rotation_z", 0.0),
            ))
        else:
            details.label(text="Unknown 2DFX type {}".format(effect_type), icon="QUESTION")

        diagnostics = layout.box()
        diagnostics.label(text="Record")
        _text(diagnostics, "Table Index", _value(obj, "global_index", "Unknown"))
        _text(diagnostics, "File Offset", _hex(_value(obj, "entry_off", 0)))
        _text(diagnostics, "Mapping", _value(obj, "mapping_basis", "Unknown"))


class DATA_PT_BLeeds_2DFX_Light(bpy.types.Panel):
    """Show the exact GAME.DTZ entry beside Blender's native Point settings."""
    bl_idname = "DATA_PT_BLeeds_2DFX_Light"
    bl_label = "BLeeds - 2DFX"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        obj = getattr(context, "object", None)
        return obj is not None and getattr(obj, "type", "") == "LIGHT" and _is_2dfx_object(obj)

    def draw(self, context):
        OBJECT_PT_BLeeds_2DFX.draw(self, context)
