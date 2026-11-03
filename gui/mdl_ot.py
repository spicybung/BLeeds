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

from ..ops import mdl_importer
from ..leedsLib import native_mdl as mdl_core
from ..ops import tex_importer

import os
import traceback
import bpy
from bpy.types import Operator, OperatorFileListElement
from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.props import (
    IntProperty,

    StringProperty,
    BoolProperty,
    EnumProperty,
    CollectionProperty,
)
from . import drawImportLogOptions, runImport

def resolve_export_defaults_from_root(context):
    from ..ops import native_ps2_mdl as mdl_exporter

    try:
        root = mdl_exporter.find_mdl_root(context, create_if_missing=False)
    except Exception:
        return ("SIM", False)

    mdl_type = "SIM"
    use_normals = False

    try:
        if hasattr(root, "bleeds_mdl_type"):
            mdl_type = str(root.bleeds_mdl_type or "SIM")
        elif "bleeds_mdl_type" in root:
            mdl_type = str(root.get("bleeds_mdl_type", "SIM"))
    except Exception:
        mdl_type = "SIM"

    mdl_type_u = mdl_type.upper().strip()
    if mdl_type_u in ("PED", "CUT"):
        mdl_type = "PED"
        use_normals = True

    try:
        if hasattr(root, "bleeds_export_use_normals"):
            use_normals = bool(use_normals or root.bleeds_export_use_normals)
        elif "bleeds_export_use_normals" in root:
            use_normals = bool(use_normals or root.get("bleeds_export_use_normals", False))
    except Exception:
        pass

    return (mdl_type if mdl_type in {"SIM", "PED"} else "SIM", bool(use_normals))

class IMPORT_OT_Stories_mdl(Operator, ImportHelper):
    bl_idname = "import_scene.bleeds_stories_mdl"
    bl_label = "Import Leeds MDL"
    bl_description = "Import Rockstar Leeds .MDL"
    bl_options = {"PRESET", "UNDO"}

    filename_ext = ".mdl"
    filter_glob: StringProperty(
        default="*.mdl",
        options={"HIDDEN"},
        maxlen=255,
    )

    files: CollectionProperty(
        name="Selected MDL files",
        type=OperatorFileListElement,
        options={"HIDDEN"},
    )

    directory: StringProperty(
        name="Directory",
        subtype="DIR_PATH",
        options={"HIDDEN"},
    )

    import_texture: BoolProperty(
        name="Import Textures",
        description="Import the matching texture file beside the model",
        default=False,
    )

    print_debug_log: BoolProperty(
        name="Print Debug Log",
        description="Print MDL import details in Blender's system console",
        default=False,
    )
    print_text_log: BoolProperty(
        name="Print Text Log",
        description="Save MDL import details to a text file beside the model",
        default=False,
    )

    mh2_import_armature: BoolProperty(
        name="Import Armature",
        description="Create the skeleton and vertex groups",
        default=True,
    )

    mh2_import_materials: BoolProperty(
        name="Import Materials",
        description="Create the native material slots",
        default=True,
    )

    create_armature: BoolProperty(
        name="Import Armature",
        description="Create an armature for a skinned model",
        default=True,
        options={"HIDDEN"},
    )

    link_to_scene: BoolProperty(
        name="Link Collection",
        description="Link the imported collection to the active scene",
        default=True,
        options={"HIDDEN"},
    )

    collection_name: StringProperty(
        name="Collection",
        description="Collection for imported objects",
        default="",
        maxlen=1024,
        options={"HIDDEN"},
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        filepath = str(getattr(self, "filepath", "") or "")
        if filepath and self.isManhunt2PcContainer(filepath):
            layout.prop(self, "mh2_import_armature")
            layout.prop(self, "mh2_import_materials")
        else:
            layout.prop(self, "create_armature")

        layout.prop(self, "import_texture")
        drawImportLogOptions(layout, self)

    inspected_filepath: StringProperty(
        name="Inspected File",
        default="",
        options={"HIDDEN"},
    )

    def check(self, context):
        filepath = str(getattr(self, "filepath", "") or "")
        if not filepath or not os.path.isfile(filepath):
            return False

        inspected = str(getattr(self, "inspected_filepath", "") or "")
        if os.path.normcase(os.path.normpath(filepath)) == os.path.normcase(os.path.normpath(inspected)):
            return False

        self.inspected_filepath = filepath
        return True

    def gatherImportFilepaths(self):
        paths = []
        directory = str(getattr(self, "directory", "") or "")

        try:
            selected_files = list(getattr(self, "files", []) or [])
        except Exception:
            selected_files = []

        if selected_files and directory:
            for item in selected_files:
                name = str(getattr(item, "name", "") or "")
                if name:
                    paths.append(os.path.join(directory, name))

        filepath = str(getattr(self, "filepath", "") or "")
        if not paths and filepath:
            if os.path.isdir(filepath):
                for name in sorted(os.listdir(filepath)):
                    if name.lower().endswith(".mdl"):
                        paths.append(os.path.join(filepath, name))
            else:
                paths.append(filepath)

        clean_paths = []
        seen = set()
        for path in paths:
            if not path:
                continue
            norm = os.path.normpath(path)
            key = os.path.normcase(norm)
            if key in seen:
                continue
            seen.add(key)
            clean_paths.append(norm)
        return clean_paths

    def isManhunt2PcContainer(self, filepath):
        try:
            with open(filepath, "rb") as source:
                header = source.read(8)
            return len(header) == 8 and header[:4] in {b"PMLC", b"Z2HM"}
        except OSError:
            return False

    def execute(self, context):
        return runImport(self, context, self.executeImport)

    def executeImport(self, context):
        filepaths = self.gatherImportFilepaths()
        collection_name = self.collection_name

        if not filepaths:
            self.report({"ERROR"}, "No MDL files selected.")
            return {"CANCELLED"}

        missing_paths = [path for path in filepaths if not os.path.isfile(path)]
        if missing_paths:
            self.report({"ERROR"}, f"Selected path is not an MDL file: {missing_paths[0]}")
            return {"CANCELLED"}

        imported_count = 0
        failed = []
        all_created_objects = []

        for filepath in filepaths:
            try:
                target_collection_name = collection_name or os.path.basename(filepath)
                is_mh2_container = self.isManhunt2PcContainer(filepath)
                if is_mh2_container:
                    from ..ops.mdl_importer import mh2ImportCleanup
                    from ..rwLib.dff import readModel
                    from pathlib import Path

                    model_bytes = Path(filepath).read_bytes()
                    detected_platform = "PC"
                    try:
                        _resource, entries = readModel(model_bytes, platform="AUTO")
                        native_platforms = {
                            obj["platform"] for entry in entries for obj in entry["objects"]
                        }
                        if native_platforms:
                            if len(native_platforms) != 1:
                                raise ValueError("MH2 model mixes PS2 and PSP geometry")
                            detected_platform = native_platforms.pop()
                    except ValueError as exc:
                        if "mixes PS2 and PSP" in str(exc):
                            raise
                        detected_platform = "PC"

                    if detected_platform in {"PS2", "PSP"}:
                        from ..ops.mdl_importer import importModel
                        imported_objects = importModel(
                            context,
                            filepath,
                            platform=detected_platform,
                            import_textures=self.import_texture,
                            model_type="AUTO",
                            import_armature=self.mh2_import_armature,
                            import_materials=self.mh2_import_materials,
                        )
                        all_created_objects.extend(imported_objects)
                        imported_count += 1
                        continue
                    with mh2ImportCleanup():
                        texture_path = None
                        texture_images = []
                        if self.import_texture:
                            texture_path, texture_images, _matched, _missing = tex_importer.import_mh2_sidecar_texture_for_mdl(
                                filepath,
                                imported_objects=None,
                            )

                        imported_objects = mdl_core.import_mh2(
                            path=filepath,
                            context=context,
                            collection_name=target_collection_name,
                            layout_mode='DETECT',
                            import_armature=self.mh2_import_armature,
                            import_materials=self.mh2_import_materials,
                            import_textures=self.import_texture,
                            preloaded_texture_images=texture_images,
                            texture_source_path=texture_path,
                            print_debug_log=self.print_debug_log or self.print_text_log,
                            model_type="AUTO",
                        )
                    if self.import_texture:
                        loaded_materials = set()
                        for imported_object in imported_objects or []:
                            if imported_object is None or getattr(imported_object, "type", None) != "MESH":
                                continue
                            for material in list(getattr(imported_object.data, "materials", []) or []):
                                if material is None:
                                    continue
                                try:
                                    if bool(material.get("bleeds_mh2_texture_loaded", False)):
                                        loaded_materials.add(material.name)
                                except Exception:
                                    pass
                        if texture_path is None:
                            self.report({"WARNING"}, "No same-name Manhunt 2 TEX file found beside: {}".format(os.path.basename(filepath)))
                        else:
                            self.report(
                                {"INFO"},
                                "{}: imported {} MH2 texture image(s), {} material(s) matched.".format(
                                    os.path.basename(filepath),
                                    len(texture_images),
                                    len(loaded_materials),
                                ),
                            )

                    all_created_objects.extend(imported_objects or [])
                    imported_count += 1
                    continue

                created_objects, detected = mdl_importer.import_stories_mdl_detected(
                    context=context,
                    filepath=filepath,
                    import_game="AUTO",
                    platform="AUTO",
                    mdl_type="AUTO",
                    collection_name=target_collection_name,
                    create_armature=self.create_armature,
                    link_to_scene=self.link_to_scene,
                    print_debug_log=self.print_debug_log or self.print_text_log,
                )

                if self.import_texture:
                    texture_platform = "ps2"
                    if str(detected.get("platform", "PS2")).upper().strip() == "PSP":
                        texture_platform = "psp"
                    texture_path, texture_images, texture_matched, _texture_missing = tex_importer.import_sidecar_texture_for_mdl(
                        mdl_path=filepath,
                        imported_objects=created_objects,
                        platform=texture_platform,
                    )
                    if texture_path is None:
                        self.report({"WARNING"}, f"No same-name Leeds texture dictionary found beside: {os.path.basename(filepath)}")
                    elif not texture_images:
                        self.report({"WARNING"}, f"No textures decoded from: {texture_path}")
                    else:
                        self.report({"INFO"}, f"{os.path.basename(filepath)}: imported {len(texture_images)} texture images, {texture_matched} materials matched.")

                all_created_objects.extend(created_objects)
                imported_count += 1

            except Exception as exc:
                failed.append((filepath, str(exc)))
                print("MDL import failed: {}: {}".format(filepath, exc))
                traceback.print_exc()

        print("MDL import results: {} imported, {} failed".format(imported_count, len(failed)))

        if all_created_objects:
            try:
                bpy.ops.object.select_all(action="DESELECT")
            except Exception:
                pass
            for obj in all_created_objects:
                try:
                    obj.select_set(True)
                except Exception:
                    pass
            try:
                context.view_layer.objects.active = all_created_objects[-1]
            except Exception:
                pass

        if imported_count:
            from ..ops.uv_playback import requestNativeUvPlayback
            requestNativeUvPlayback(context)

        if failed:
            first_path, first_error = failed[0]
            if imported_count > 0:
                self.report({"WARNING"}, f"Imported {imported_count} MDL(s), failed {len(failed)}. First failure: {os.path.basename(first_path)}: {first_error}")
                return {"FINISHED"}
            self.report({"ERROR"}, f"Failed to import MDL: {os.path.basename(first_path)}: {first_error}")
            return {"CANCELLED"}

        self.report({"INFO"}, f"Imported {imported_count} MDL(s).")
        return {"FINISHED"}

class EXPORT_SCENE_OT_stories_mdl_ps2(bpy.types.Operator, ExportHelper):
    bl_idname = "export_scene.bleeds_stories_mdl"
    bl_label = "Export R* Leeds MDL"
    bl_description = "Export Rockstar Leeds .MDL"
    bl_options = {"UNDO"}

    filename_ext = ".mdl"
    filter_glob: StringProperty(
        default="*.mdl",
        options={"HIDDEN"},
        maxlen=255,
    )

    platform: EnumProperty(
        name="Platform",
        description="Stories model target",
        items=(
            ("PS2", "PlayStation 2", "Export a PlayStation 2 Stories MDL"),
            ("PSP", "PlayStation Portable", "Export a PSP Stories MDL"),
        ),
        default="PS2",
    )

    export_game: EnumProperty(
        name="Game",
        description="Target Leeds 3D model family",
        items=(
            ("LCS", "LCS", "Grand Theft Auto: Liberty City Stories"),
            ("VCS", "VCS", "Grand Theft Auto: Vice City Stories"),
            ("MH2", "MH2", "Manhunt 2"),
        ),
        default="VCS",
    )

    mh2_source_root: StringProperty(
        name="Source Model",
        default="",
        options={"HIDDEN"},
    )

    mh2_platform: EnumProperty(
        name="Platform",
        description="Manhunt 2 platform",
        items=(
            ("PC", "PC", "Manhunt 2 Windows PC"),
            ("PS2", "PS2", "Manhunt 2 PlayStation 2"),
            ("PSP", "PSP", "Manhunt 2 PlayStation Portable"),
        ),
        default="PC",
    )

    mh2_model_type: EnumProperty(
        name="Model Format",
        description="Manhunt 2 model class",
        items=(
            ("SIM", "SimpleModel", "Static model"),
            ("PED", "ClumpModel", "Skinned or hierarchical model"),
            ("CUT", "ClumpModel (CUT)", "Cutscene model"),
        ),
        default="PED",
    )

    mdl_type: EnumProperty(
        name="Model Format",
        description="Type of model to export",
        items=(
            ("SIMPLE", "SimpleModel", "Static/simple Leeds model"),
            ("CLUMP", "ClumpModel", "Skinned or hierarchical Leeds clump model"),
            ("CUT", "ClumpModel (CUT)", "Cutscene clump model"),
            ("VEH", "VehicleModel", "Vehicle-oriented Leeds clump model"),
        ),
        default="SIMPLE",
    )

    max_batch_verts: IntProperty(
        name="Max Batch Verts",
        description=(
            "Maximum vertices per VIF segment.  When set to 0, the exporter "
            "automatically chooses an appropriate size based on the mesh."
        ),
        default=0,
        min=0,
        max=255,
        options={"HIDDEN"},
    )

    rounding_mode: EnumProperty(
        name="Rounding",
        description="Round positions to PS2 integer coordinates",
        items=(("ROUND", "Round", "round()"),),
        default="ROUND",
        options={"HIDDEN"},
    )

    use_normals: BoolProperty(
        name="Export Normals",
        description="Include smooth vertex normals in the Stories MDL geometry stream",
        default=True,
    )

    simple_model_info_id: StringProperty(
        name="Model Info ID",
        description=(
            "Use the imported model ID, or enter a replacement ID"
        ),
        default="",
    )

    simple_atomic_hash_key: StringProperty(
        name="Atomic Hash",
        description=(
            "Use the imported Atomic hash, or enter a replacement hash"
        ),
        default="",
    )

    imported_export_mode: EnumProperty(
        name="Rebuild Imported Model",
        description="Export the current geometry and skin weights",
        items=(("REBUILD", "Rebuild", "Use the current geometry and skin weights"),),
        default="REBUILD",
        options={"HIDDEN"},
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        col = layout.column(align=True)
        col.prop(self, "export_game")
        if self.export_game == "MH2":
            col.prop(self, "mh2_platform")
            col.prop(self, "mh2_model_type")
            return
        col.prop(self, "platform")
        col.prop(self, "mdl_type")
        col.prop(self, "use_normals")
        if self.mdl_type == "SIMPLE":
            col.prop(self, "simple_model_info_id")
            col.prop(self, "simple_atomic_hash_key")

    def invoke(self, context, event):
        from ..ops import native_ps2_mdl as mdl_exporter

        root_mdl_type, root_use_normals = resolve_export_defaults_from_root(context)
        if root_mdl_type == "PED":
            self.mdl_type = "CLUMP"
        self.use_normals = bool(root_use_normals)

        self.mh2_source_root = ''
        root = None
        from ..ops.mdl_exporter import findMh2Root, normalizeMh2ArmatureNames
        try:
            root = findMh2Root(context)
        except ValueError:
            root = None

        if root is not None:
            normalizeMh2ArmatureNames(root)
            self.export_game = 'MH2'
            self.mh2_source_root = root.name
        else:
            try:
                root = mdl_exporter.find_mdl_root(context, create_if_missing=False)
            except (RuntimeError, ValueError):
                root = None

        try:
            if root is not None:
                if hasattr(root, "bleeds_model_game"):
                    self.export_game = str(root.bleeds_model_game or self.export_game)
                elif "bleeds_model_game" in root:
                    self.export_game = str(root.get("bleeds_model_game", self.export_game))
        except Exception:
            pass

        try:
            if root is not None:
                if self.export_game == "MH2":
                    imported_type = str(root.get("bleeds_mh2_model_class", root.get("bleeds_mdl_type", "PED")) or "PED").upper()
                    self.mh2_model_type = imported_type if imported_type in {"SIM", "CUT", "PED"} else "PED"
                    source_platform = str(root.get("bleeds_mh2_platform", root.get("bleeds_mdl_platform", "PC")) or "PC").upper()
                    if source_platform in {"PC", "PS2", "PSP"}:
                        self.mh2_platform = source_platform
                model_info_value = None
                hash_value = None
                if hasattr(root, "bleeds_mdl_model_info_id"):
                    model_info_value = int(root.bleeds_mdl_model_info_id)
                elif "bleeds_mdl_model_info_id" in root:
                    model_info_value = int(root["bleeds_mdl_model_info_id"])
                if hasattr(root, "bleeds_mdl_atomic_hash_key"):
                    hash_value = int(root.bleeds_mdl_atomic_hash_key)
                elif "bleeds_mdl_atomic_hash_key" in root:
                    hash_value = int(root["bleeds_mdl_atomic_hash_key"])
                if model_info_value is not None and 0 <= model_info_value <= 0xFFFF:
                    self.simple_model_info_id = f"0x{model_info_value:X}"
                if hash_value is not None:
                    hash_value &= 0xFFFFFFFF
                if hash_value is not None and 0 <= hash_value <= 0xFFFFFFFF:
                    self.simple_atomic_hash_key = f"0x{hash_value:X}"
        except Exception:
            pass

        try:
            if root is not None:
                if hasattr(root, "bleeds_mdl_platform"):
                    self.platform = str(root.bleeds_mdl_platform or self.platform)
                elif "bleeds_mdl_platform" in root:
                    self.platform = str(root.get("bleeds_mdl_platform", self.platform))
        except Exception:
            pass

        try:
            if root is not None:
                if hasattr(root, "bleeds_imported_export_mode"):
                    self.imported_export_mode = str(root.bleeds_imported_export_mode or self.imported_export_mode)
                elif "bleeds_imported_export_mode" in root:
                    self.imported_export_mode = str(root.get("bleeds_imported_export_mode", self.imported_export_mode))
        except Exception:
            pass

        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def filepathUsesManhunt2PcContainer(self, filepath):
        try:
            with open(filepath, "rb") as input_file:
                return input_file.read(4) == b"PMLC"
        except Exception:
            return False

    def execute(self, context):
        if self.export_game == "MH2":
            try:
                from ..ops.mdl_exporter import exportMh2Model, findMh2Root, validateMh2ExportType
                root = findMh2Root(context, self.mh2_source_root or None)
                validateMh2ExportType(root, self.mh2_model_type)
                source_platform = str(root.get('bleeds_mh2_platform', root.get('bleeds_mdl_platform', 'PC')) or 'PC').upper()
                if source_platform != self.mh2_platform:
                    raise ValueError(f'This model contains {source_platform} data, not {self.mh2_platform} data')
                if self.mh2_platform == 'PC':
                    from ..ops.mdl_exporter import exportMh2RebuiltModel
                    part_count, vertex_count, face_count = exportMh2RebuiltModel(root, self.filepath)
                    self.report({"INFO"}, f"Exported MH2 PC MDL: {part_count} meshes, {vertex_count} vertices, {face_count} triangles")
                    return {"FINISHED"}
                part_count, vertex_count, changed_count = exportMh2Model(context, self.filepath, root=root)
            except Exception as exc:
                traceback.print_exc()
                self.report({"ERROR"}, f"Export MH2 MDL failed: {exc}")
                return {"CANCELLED"}
            self.report({"INFO"}, f"Exported MH2 MDL: {part_count} parts, {vertex_count} vertices ({changed_count} changed)")
            return {"FINISHED"}

        from ..ops import native_ps2_mdl as mdl_exporter

        root_mdl_type, root_use_normals = resolve_export_defaults_from_root(context)
        requested_model_format = str(self.mdl_type or "SIMPLE").upper().strip()
        if requested_model_format == "VEH" and self.platform == "PS2":
            self.report({"ERROR"}, "PS2 VehicleModel writing is not implemented; refusing to emit a SimpleModel with the wrong format")
            return {"CANCELLED"}
        internal_mdl_type = "PED" if requested_model_format in {"CLUMP", "CUT"} else "SIM"
        use_normals = self.use_normals

        if requested_model_format in {"CLUMP", "CUT"}:
            use_normals = True
        else:
            use_normals = bool(use_normals or root_use_normals)

        try:
            root = mdl_exporter.find_mdl_root(context, create_if_missing=True)
            if root is not None:
                try:
                    root.bleeds_mdl_platform = self.platform
                except Exception:
                    pass
                try:
                    root["bleeds_mdl_platform"] = self.platform
                except Exception:
                    pass
                semantic_type = {
                    "SIMPLE": "SIM",
                    "CLUMP": "PED",
                    "CUT": "CUT",
                    "VEH": "VEH",
                }.get(requested_model_format, "SIM")
                try:
                    root.bleeds_mdl_type = semantic_type
                except Exception:
                    pass
                try:
                    root["bleeds_mdl_type"] = semantic_type
                    root["bleeds_export_model_format"] = requested_model_format
                    root["bleeds_model_game"] = self.export_game
                except Exception:
                    pass

            if requested_model_format == "SIMPLE":
                def parse_runtime_integer(text, field_name, maximum):
                    value_text = str(text or "").strip()
                    if not value_text:
                        return None
                    try:
                        value = int(value_text, 0)
                    except Exception as exc:
                        raise RuntimeError(f"{field_name} must be a decimal value or 0x-prefixed hexadecimal value.") from exc
                    if value < 0 or value > maximum:
                        raise RuntimeError(f"{field_name} is outside the valid range 0..0x{maximum:X}.")
                    return value

                explicit_model_info_id = parse_runtime_integer(self.simple_model_info_id, "Model Info ID", 0xFFFF)
                explicit_hash_key = parse_runtime_integer(self.simple_atomic_hash_key, "Atomic Hash", 0xFFFFFFFF)

                existing_model_info_id = None
                if root is not None:
                    try:
                        if hasattr(root, "bleeds_mdl_model_info_id"):
                            existing_model_info_id = int(root.bleeds_mdl_model_info_id)
                        elif "bleeds_mdl_model_info_id" in root:
                            existing_model_info_id = int(root["bleeds_mdl_model_info_id"])
                    except Exception:
                        existing_model_info_id = None


                if explicit_model_info_id is not None:
                    root["bleeds_mdl_model_info_id"] = int(explicit_model_info_id)
                elif existing_model_info_id is None or existing_model_info_id < 0 or existing_model_info_id > 0xFFFF:
                    root["bleeds_mdl_model_info_id"] = -1

                if explicit_hash_key is not None:
                    root["bleeds_mdl_atomic_hash_key"] = int(explicit_hash_key) if explicit_hash_key <= 0x7FFFFFFF else int(explicit_hash_key) - 0x100000000
                else:
                    existing_hash = None
                    try:
                        if hasattr(root, "bleeds_mdl_atomic_hash_key"):
                            existing_hash = int(root.bleeds_mdl_atomic_hash_key)
                        elif "bleeds_mdl_atomic_hash_key" in root:
                            existing_hash = int(root["bleeds_mdl_atomic_hash_key"])
                    except Exception:
                        existing_hash = None
                    if existing_hash is None:
                        root["bleeds_mdl_atomic_hash_key"] = 0

            export_function = mdl_exporter.export_stories_mdl_psp if self.platform == "PSP" else mdl_exporter.export_stories_mdl_ps2
            export_function(
                context=context,
                filepath=self.filepath,
                mdl_type=semantic_type if self.platform == "PSP" else internal_mdl_type,
                max_batch_verts=self.max_batch_verts,
                rounding_mode=self.rounding_mode,
                use_normals=use_normals,
                imported_export_mode="REBUILD",
                export_game=self.export_game,
            )
        except Exception as exc:
            self.report({"ERROR"}, f"Export Stories MDL failed: {exc}")
            return {"CANCELLED"}

        self.report({"INFO"}, f"Exported Stories MDL: {self.filepath}")
        return {"FINISHED"}
