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

from ..ops import mdl_importer
from ..leedsLib import mdl as mdl_core
from ..ops import tex_importer

import os
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

def resolve_export_defaults_from_root(context):
    from ..ops import mdl_exporter

    try:
        root = mdl_exporter.find_mdl_root(context)
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
    bl_description = "Import a Rockstar Leeds model from an MDL file"
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

    import_game: EnumProperty(
        name="Type",
        description="Leeds game family to import",
        items=(
            ("AUTO", "Detect from header", "Determine the game family from the MDL container structure"),
            ("LCS", "LCS", "Grand Theft Auto: Liberty City Stories"),
            ("VCS", "VCS", "Grand Theft Auto: Vice City Stories"),
            ("MH2", "MH2", "Manhunt 2"),
        ),
        default="AUTO",
        options={"HIDDEN"},
    )

    platform: EnumProperty(
        name="Platform",
        description="Platform this Stories MDL was built for",
        items=(
            ("AUTO", "Detect from header", "Determine PS2 or PSP from the Stories MDL header"),
            ("PS2", "PS2", "PlayStation 2 (Liberty City Stories / Vice City Stories)"),
            ("PSP", "PSP", "PlayStation Portable (Liberty City Stories / Vice City Stories)"),
        ),
        default="AUTO",
        options={"HIDDEN"},
    )

    mdl_type: EnumProperty(
        name="Model Type",
        description="Whether this MDL is a ped/actor or a prop",
        items=(
            ("AUTO", "Detect from structure", "Determine SimpleModel, PedModel, CutsceneModel, or VehicleModel from the MDL structure"),
            ("SIM", "SimpleModel", "Simple / prop model without bones"),
            ("PED", "PedModel / Actor", "Pedestrian / actor model with bones"),
            ("CUT", "CutsceneModel / Actor", "Cutscene / actor model with bones"),
            ("VEH", "VehModel", "Vehicle model"),
        ),
        default="AUTO",
        options={"HIDDEN"},
    )

    import_texture: BoolProperty(
        name="Import Texture",
        description="Import the same-name Leeds texture dictionary beside the MDL, including Manhunt 2 TCDT/Z2HM TEX files",
        default=False,
    )

    print_debug_log: BoolProperty(
        name="Print Debug Log",
        description="Print detailed MDL parser output to the system console and write an import log beside each imported MDL",
        default=False,
    )

    mh2_layout: EnumProperty(
        name="PMLC Structure",
        description="Manhunt 2 PMLC entry, bone, material-ID, and vertex-record structure",
        items=(
            (
                "DETECT",
                "Determine from file",
                "Validate the entry list, bone record, material-ID record, vertex stride, position offset, and UV offset against the file",
            ),
            (
                "PC_RETAIL",
                "Retail PC PMLC",
                "Prefer the retail PC PMLC structure and accept another validated structure only when the retail structure does not fit",
            ),
            (
                "PSP_BETA",
                "PSP beta / prototype PMLC",
                "Prefer the PSP beta/prototype PMLC structures and validate each table boundary before import",
            ),
        ),
        default="DETECT",
        options={"HIDDEN"},
    )

    mh2_import_armature: BoolProperty(
        name="Import Bone Hierarchy",
        description="Create the PMLC bone hierarchy and parent the imported mesh objects to it",
        default=True,
        options={"HIDDEN"},
    )

    mh2_import_materials: BoolProperty(
        name="Import Material Tables",
        description="Read PMLC material and material-ID tables and assign polygon material slots",
        default=True,
        options={"HIDDEN"},
    )

    create_armature: BoolProperty(
        name="Internal Armature Import",
        description="Internal: imports frame data as an armature when appropriate",
        default=True,
        options={"HIDDEN"},
    )

    link_to_scene: BoolProperty(
        name="Internal Collection Link",
        description="Internal: links the imported collection to the active scene",
        default=True,
        options={"HIDDEN"},
    )

    collection_name: StringProperty(
        name="Internal Collection",
        description="Internal: optional collection override",
        default="",
        maxlen=1024,
        options={"HIDDEN"},
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(self, "import_texture")
        layout.prop(self, "print_debug_log")

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
        return bool(mdl_core.is_manhunt2_pmlc_mdl(filepath))

    def execute(self, context):
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
                target_collection_name = collection_name or os.path.splitext(os.path.basename(filepath))[0]
                use_manhunt2_pc_reader = (
                    self.import_game == "MH2"
                    or (self.import_game == "AUTO" and self.isManhunt2PcContainer(filepath))
                )
                if use_manhunt2_pc_reader:
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
                        layout_mode=self.mh2_layout,
                        import_armature=self.mh2_import_armature,
                        import_materials=self.mh2_import_materials,
                        import_textures=self.import_texture,
                        preloaded_texture_images=texture_images,
                        texture_source_path=texture_path,
                        print_debug_log=self.print_debug_log,
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

                created_objects, detected = mdl_importer.import_stories_mdl_auto(
                    context=context,
                    filepath=filepath,
                    import_game=self.import_game,
                    platform=self.platform,
                    mdl_type=self.mdl_type,
                    collection_name=target_collection_name,
                    create_armature=self.create_armature,
                    link_to_scene=self.link_to_scene,
                    print_debug_log=self.print_debug_log,
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
    bl_label = "Export R* Leeds Stories MDL"
    bl_description = "Export the active Leeds model to an MDL file"
    bl_options = {"UNDO"}

    filename_ext = ".mdl"
    filter_glob: StringProperty(
        default="*.mdl",
        options={"HIDDEN"},
        maxlen=255,
    )

    export_game: EnumProperty(
        name="3D Models",
        description="Target Leeds 3D model family",
        items=(
            ("LCS", "LCS", "Grand Theft Auto: Liberty City Stories"),
            ("VCS", "VCS", "Grand Theft Auto: Vice City Stories"),
            ("MH2", "MH2", "Manhunt 2"),
        ),
        default="VCS",
    )

    mdl_type: EnumProperty(
        name="Type",
        description="Leeds MDL model class to export",
        items=(
            ("SIM", "SimpleModel", "Prop or simple Atomic model"),
            ("PED", "PedModel", "Skinned pedestrian or actor Clump"),
        ),
        default="SIM",
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
        name="Internal Quantize",
        description="Internal fixed quantization mode for Stories PS2 position encoding.",
        items=(("ROUND", "Round", "round()"),),
        default="ROUND",
        options={"HIDDEN"},
    )

    use_normals: BoolProperty(
        name="Export Normals",
        description="Include smooth vertex normals in the Stories MDL geometry stream",
        default=True,
    )

    imported_export_mode: EnumProperty(
        name="Internal PED Rebuild",
        description="Internal: imported PEDs are always rebuilt from calculated live data",
        items=(("REBUILD", "Rebuild", "Rebuild from calculated pointers, live geometry, and ped_atomic_bind basis"),),
        default="REBUILD",
        options={"HIDDEN"},
    )

    def invoke(self, context, event):
        from ..ops import mdl_exporter

        root_mdl_type, root_use_normals = resolve_export_defaults_from_root(context)
        if root_mdl_type == "PED":
            self.mdl_type = "PED"
        self.use_normals = bool(root_use_normals)

        try:
            root = mdl_exporter.find_mdl_root(context)
        except Exception:
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
        from ..ops import mdl_exporter

        root_mdl_type, root_use_normals = resolve_export_defaults_from_root(context)
        mdl_type = self.mdl_type
        use_normals = self.use_normals

        if root_mdl_type == "PED" and mdl_type == "SIM":
            mdl_type = "PED"
        if mdl_type == "PED":
            use_normals = True
        else:
            use_normals = bool(use_normals or root_use_normals)

        try:
            mdl_exporter.export_stories_mdl_ps2(
                context=context,
                filepath=self.filepath,
                mdl_type=mdl_type,
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
