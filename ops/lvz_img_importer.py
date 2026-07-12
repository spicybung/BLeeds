# BLeeds - Scripts for working with R* Leeds (GTA Stories, Chinatown Wars, Manhunt 2, etc) formats in Blender
# Author: spicybung
# Years: 2025 - 2026

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import re
import struct
import time
import zipfile
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import bpy
from mathutils import Matrix

from .. import set_mesh_auto_smooth
from ..leedsLib import lvz_img as LVZ

_ACTIVE_IMPORT_PROGRESS = None
_ACTIVE_IMPORT_UNDO_STATE = None


def draw_lvz_img_import_progress_popup(menu, context):
    layout = menu.layout
    layout.use_property_split = False
    layout.use_property_decorate = False
    window_manager = context.window_manager
    column = layout.column(align=True)
    column.prop(window_manager, "bleeds_lvz_img_progress", text="Progress", slider=True)
    stage_text = str(getattr(window_manager, "bleeds_lvz_img_stage", "") or "")
    if stage_text:
        column.label(text=stage_text)


class LvzImgImportProgress:
    def __init__(self, operator, context):
        self.operator = operator
        self.context = context
        self.window_manager = getattr(context, "window_manager", None)
        self.started = False
        self.finished = False
        self.value = -1
        self.stage = ""
        self.last_redraw_time = 0.0
        self.last_report_bucket = -1
        self.initial_object_names = set()
        self.initial_mesh_names = set()
        self.initial_material_names = set()
        self.initial_image_names = set()
        self.initial_collection_names = set()

    def capture_initial_data_blocks(self):
        try:
            self.initial_object_names = set(bpy.data.objects.keys())
        except Exception:
            self.initial_object_names = set()
        try:
            self.initial_mesh_names = set(bpy.data.meshes.keys())
        except Exception:
            self.initial_mesh_names = set()
        try:
            self.initial_material_names = set(bpy.data.materials.keys())
        except Exception:
            self.initial_material_names = set()
        try:
            self.initial_image_names = set(bpy.data.images.keys())
        except Exception:
            self.initial_image_names = set()
        try:
            self.initial_collection_names = set(bpy.data.collections.keys())
        except Exception:
            self.initial_collection_names = set()

    def remove_failed_import_data_blocks(self):
        try:
            for obj in list(bpy.data.objects):
                if obj.name not in self.initial_object_names:
                    bpy.data.objects.remove(obj, do_unlink=True)
        except Exception:
            pass
        try:
            for mesh in list(bpy.data.meshes):
                if mesh.name not in self.initial_mesh_names and mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
        except Exception:
            pass
        try:
            for material in list(bpy.data.materials):
                if material.name not in self.initial_material_names and material.users == 0:
                    bpy.data.materials.remove(material)
        except Exception:
            pass
        try:
            for image in list(bpy.data.images):
                if image.name not in self.initial_image_names and image.users == 0:
                    bpy.data.images.remove(image)
        except Exception:
            pass
        try:
            for collection in list(bpy.data.collections):
                if collection.name not in self.initial_collection_names:
                    bpy.data.collections.remove(collection)
        except Exception:
            pass

    def begin(self, stage="Reading LVZ container"):
        global _ACTIVE_IMPORT_PROGRESS
        _ACTIVE_IMPORT_PROGRESS = self
        self.started = True
        self.finished = False
        self.capture_initial_data_blocks()
        if self.window_manager is not None:
            try:
                self.window_manager.progress_begin(0, 100)
            except Exception:
                pass
            try:
                self.window_manager.bleeds_lvz_img_progress = 0
                self.window_manager.bleeds_lvz_img_stage = str(stage)
            except Exception:
                pass
            try:
                self.window_manager.popup_menu(
                    draw_lvz_img_import_progress_popup,
                    title="LVZ + IMG Import",
                    icon="TIME",
                )
            except Exception:
                pass
        try:
            self.context.window.cursor_set("WAIT")
        except Exception:
            pass
        self.update(0, stage, force=True)
        return self

    def update(self, value, stage=None, force=False):
        if self.finished:
            return
        try:
            value = max(0, min(100, int(round(float(value)))))
        except Exception:
            value = max(0, self.value)
        if not force and self.value >= 0 and value < self.value:
            value = self.value
        if stage is not None:
            self.stage = str(stage)
        changed = value != self.value
        self.value = value

        if self.window_manager is not None:
            try:
                self.window_manager.progress_update(value)
            except Exception:
                pass
            try:
                self.window_manager.bleeds_lvz_img_progress = value
                self.window_manager.bleeds_lvz_img_stage = self.stage
            except Exception:
                pass

        status_text = "BLeeds LVZ + IMG | {:d}%".format(value)
        if self.stage:
            status_text += " | " + self.stage
        try:
            self.context.workspace.status_text_set(status_text)
        except Exception:
            pass

        current_time = time.monotonic()
        should_redraw = force or (changed and current_time - self.last_redraw_time >= 0.08)
        if should_redraw:
            self.last_redraw_time = current_time
            self.redraw()

        report_bucket = value // 10
        if report_bucket != self.last_report_bucket and value not in (0, 100):
            self.last_report_bucket = report_bucket
            try:
                self.operator.report({'INFO'}, "LVZ + IMG import: {:d}% - {}".format(value, self.stage))
            except Exception:
                pass

    def update_range(self, range_start, range_end, index, total, stage):
        try:
            total = max(1, int(total))
            index = max(0, min(total, int(index)))
            fraction = float(index) / float(total)
        except Exception:
            fraction = 0.0
        value = float(range_start) + (float(range_end) - float(range_start)) * fraction
        self.update(value, stage)

    def redraw(self):
        try:
            for window in self.window_manager.windows:
                screen = getattr(window, "screen", None)
                if screen is None:
                    continue
                for area in screen.areas:
                    area.tag_redraw()
        except Exception:
            pass
        try:
            if bpy.ops.wm.redraw_timer.poll():
                bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
        except Exception:
            pass

    def finish(self, succeeded=True, message=None):
        global _ACTIVE_IMPORT_PROGRESS
        if self.finished:
            return
        self.finished = True
        final_stage = str(message or ("Import complete" if succeeded else "Import cancelled"))
        final_value = 100 if succeeded else max(0, self.value)
        if not succeeded:
            self.remove_failed_import_data_blocks()
        if self.window_manager is not None:
            try:
                self.window_manager.progress_update(final_value)
                self.window_manager.bleeds_lvz_img_progress = final_value
                self.window_manager.bleeds_lvz_img_stage = final_stage
            except Exception:
                pass
        try:
            self.context.workspace.status_text_set(None)
        except Exception:
            pass
        try:
            self.context.window.cursor_set("DEFAULT")
        except Exception:
            pass
        try:
            if self.window_manager is not None:
                self.window_manager.progress_end()
        except Exception:
            pass
        self.redraw()
        if _ACTIVE_IMPORT_PROGRESS is self:
            _ACTIVE_IMPORT_PROGRESS = None
        restore_active_import_undo_state()


def restore_active_import_undo_state():
    global _ACTIVE_IMPORT_UNDO_STATE
    state = _ACTIVE_IMPORT_UNDO_STATE
    _ACTIVE_IMPORT_UNDO_STATE = None
    if state is None:
        return
    edit_preferences, enabled = state
    try:
        edit_preferences.use_global_undo = bool(enabled)
    except Exception:
        pass


def finish_active_import_progress(context=None, succeeded=True, message=None):
    global _ACTIVE_IMPORT_PROGRESS
    progress = _ACTIVE_IMPORT_PROGRESS
    if progress is not None:
        progress.finish(succeeded=succeeded, message=message)
    else:
        if context is not None:
            try:
                context.workspace.status_text_set(None)
            except Exception:
                pass
            try:
                context.window.cursor_set("DEFAULT")
            except Exception:
                pass
    restore_active_import_undo_state()


UNPACK_BYTES = struct.pack("<I", LVZ.read_lvz.UNPACK)
IMG_MDL_SCAN_LIMIT = 0x240
IMG_MDL_MAX_IMPORT = 4096
IMPORT_IMG_MDL_PAYLOADS_BY_DEFAULT = False
IMPORT_LOD_PASSES_BY_DEFAULT = False
IMPORT_DEBUG_VERBOSE_RESOURCE_DUMPS = False
IMPORT_WRITE_DEBUG_CSVS = False
IMPORT_DEBUG_MATRIX_SET_LIMIT = 96
IMPORT_APPLY_PROGRESS_EVERY = 5000
IMPORT_STAMP_DUPLICATE_IMG_PROPS = False
IMPORT_HIDE_UNPLACED_BASES_INSTEAD_OF_DELETE = False
IMPORT_LINK_DUPLICATES_IN_HIDDEN_COLLECTION = False
IMPORT_DEFER_BASE_VISIBILITY_DURING_APPLY = False
IMPORT_KEEP_UNPLACED_BASES_VISIBLE = False
IMPORT_VERBOSE_MDL_DEBUG = False
IMPORT_MDL_DEBUG_LIMIT = 48
IMPORT_VERBOSE_RESOURCE_BUILD_LOGS = False

# Keep the BestIPLModel global IPL/model fallback path, but stop IPL fallback
# instances from inheriting 32/64/128 WRLD cell basis as object scale.
# That was the source of the big wall/slab buildings while BestIPLModel's
# candidate choice was still the least broken branch.
IPL_FALLBACK_STRIP_CELL_SCALE_ENABLED = True
IPL_FALLBACK_CELL_SCALE_MIN = 31.5
IPL_FALLBACK_CELL_SCALE_LOG_LIMIT = 96

IPL_FALLBACK_SIZE_GATE_ENABLED = True
IPL_FALLBACK_MIN_ACCEPT_RADIUS = 8.0
IPL_FALLBACK_RADIUS_MULT = 6.0
IPL_FALLBACK_REJECT_LOG_LIMIT = 96
ENABLE_IPL_MODEL_ID_FALLBACK = False
ENABLE_INTERNAL_IPL_MODEL_FALLBACK_MDLS = False
ENABLE_CONVERTER_IDE_OBJECT_ID_MAP = False
# Increase the maximum delta for neighbour alias searches.  A value of zero
# disables this fallback entirely.  Setting it to one allows the importer to
# consider the immediately preceding and following resource IDs when no
# direct match is found.  This is essential for maps where placeholder
# resource IDs point to the adjacent chunk rather than carrying their own
# payload.
# Widen the search radius for neighbour‑alias fallback.  A delta of two
# allows the importer to consider the two preceding and two following
# resource IDs when searching for a substitute model.  This is helpful
# for large maps where placeholder IDs may sit several entries away from
# their real geometry.
NEIGHBOR_ALIAS_MAX_DELTA = 2
NEIGHBOR_ALIAS_GLOBAL_MAX_DELTA = 2
NEIGHBOR_ALIAS_LOG_LIMIT = 96
NEIGHBOR_ALIAS_MAX_WORLD_RADIUS_RATIO = 8.0
NEIGHBOR_ALIAS_MIN_RADIUS_LIMIT = 40.0
NEIGHBOR_ALIAS_TINY_PLACEMENT_RADIUS = 8.0
NEIGHBOR_ALIAS_TINY_MAX_WORLD_RADIUS = 55.0
# Enable neighbour alias fallback by default.  When true, the importer will
# attempt to reuse neighbouring resource entries for placement rows that do
# not resolve through exact or IPL fallbacks.  Safety checks on object
# radius ensure that only geometrically compatible candidates are chosen.
ENABLE_NEIGHBOR_ALIAS_FALLBACK = False
# Enable aggregate piece fallback.  When true, the importer will attempt
# to reuse parts of aggregate groups (such as city blocks split into
# many subpieces) when no direct resource exists.  This helps fill in
# gaps caused by placeholder IDs that reference parts of a larger group.
ENABLE_AGGREGATE_PIECE_FALLBACK = False
ENABLE_WRLD_SUBMODEL_GROUP_ID_RECOVERY = False
ENABLE_GLOBAL_WRLD_SUBMODEL_ID_RECOVERY = False
ENABLE_FINAL_VERIFIED_RENDER_PAIR_ALIASES = False
SKIP_LIGHTS_PASS_IPL_MESH_PLACEMENTS = False
ENABLE_REFERENCE_DFF_EXACT_GEOMETRY_FOR_MISSING = False
REFERENCE_DFF_CACHE: Dict[int, object] = {}
REFERENCE_DFF_STATS_CACHE: Dict[int, dict] = {}
REFERENCE_DFF_MISS_CACHE = set()
REFERENCE_DFF_DEBUG_ROWS: List[dict] = []
REFERENCE_DFF_COMPARE_ROWS: List[dict] = []
ENABLE_VISIBLE_PLACEMENT_DEDUPLICATION = False
ENABLE_SKIP_AREA_CONTINUATION_DUPLICATE_SUBMODELS = False

# V90/V92: in Stories WRLD/LVZ placement rows, the second u16 is the
# resource/object identity.  The first u16 is only a row model/IPL hint and must
# not rename Beach1881 into Beach1280.  If the LVZ master Resource[] slot is
# empty, keep the resource ID and search the IMG continuation data for a real
# descriptor/VIF payload with matching material IDs.
ENABLE_ROW_MODEL_ID_AUTHORITATIVE_PLACEMENT = False
ROW_MODEL_ID_AUTHORITATIVE_SKIP_LIGHTS = True
ENABLE_EMPTY_RESOURCE_CONTINUES_IN_IMG = True

# V93 cleanup: remove the old guessing/recovery layers from normal import.
# The current rule is format-driven: BeachX comes from the row RES/object id;
# empty LVZ Resource[] entries are IMG-backed continuations.
CONTINUES_IN_IMG_SCAN_STRIDE = 0x10
CONTINUES_IN_IMG_MAX_LOG_ROWS = 128
CONTINUES_IN_IMG_TEXTURE_ID_DELTAS = (1, 0)
CONTINUES_IN_IMG_PROOF_CACHE: Dict[int, dict] = {}
# V97: keep the dangerous IPL/IDE/neighbor guess paths off, but restore the real
# structured exact-RES IMG table paths.  V96 disabled these as debugging bloat and
# left rows such as RES 4477/4478/4494/4495 missing even though the IMG has real
# table-backed payloads.  These three passes only build candidates keyed by the row
# RES/object id; they do not remap through IPL ids or GTA SA converter IDE names.
ENABLE_GLOBAL_EXACT_RES_FALLBACK_MDLS = True
ENABLE_NESTED_CHILD_FALLBACK_MDLS = True
ENABLE_ROW_SHARED_FALLBACK_MDLS = True


# V54 speed gate: keep object matrix/transform logging, but do not build a
# huge full-scene matrix CSV by default.  Full logging is useful for one-off
# audits, but doing it for every visible object burns time and memory.
OBJECT_MATRIX_TRANSFORM_LOG_ENABLED = False
OBJECT_MATRIX_TRANSFORM_LOG_FULL_VISIBLE = False
OBJECT_MATRIX_TRANSFORM_LOG_MAX_GENERIC_ROWS = 256
OBJECT_MATRIX_TRANSFORM_LOG_ALWAYS_RES_IDS = {1881}
OBJECT_MATRIX_TRANSFORM_LOG_TO_CSV = False
OBJECT_MATRIX_TRANSFORM_LOG_TO_BLENDER_LOG = True
OBJECT_MATRIX_TRANSFORM_LOG_BLENDER_MAX_LINES = 256

# V56 speed fix: deleting tens of thousands of raw parser base objects at the
# end causes Blender to crawl.  Hide parser bases by default instead of deleting.
RAW_PARSER_BASE_CLEANUP_MODE = "hide"  # "hide" or "delete"

# V60: keep diagnostics in Blender log only. No CSV pile by default.
DIAGNOSTIC_CSV_LOGS_ENABLED = False

# V60: geometry data prints in Blender console/log. No recovery guesses.
GEOMETRY_OBJECT_LOG_ENABLED = False
GEOMETRY_OBJECT_LOG_MAX_LINES = 2048
GEOMETRY_OBJECT_LOG_ALWAYS_RES_IDS = {1881, 1887, 1888, 4294, 5045}

# V66: resolver audit. Logs the actual row -> candidate geometry chain
# in Blender's console. No guesses are imported.
RESOLVER_AUDIT_ENABLED = False
RESOLVER_AUDIT_MAX_ROWS = 4096
RESOLVER_AUDIT_ALWAYS_RES_IDS = {1019, 1033, 1287, 1511, 1586, 1612, 1633, 1670, 1881, 1887, 1888, 1961, 2082, 4294, 5045}
RESOLVER_AUDIT_ALWAYS_IPL_IDS = {436, 437, 438, 439, 562, 825, 840, 856, 864, 892, 1280, 1281, 1285, 1322, 1479}
RESOLVER_AUDIT_CANDIDATE_LIMIT_PER_ROW = 48
# V67: target-only. Do not audit every row just because chosen_obj is None.
# The V66 log filled 512 lines on early UNDERWATER/LIGHTS rows before Beach1881.
RESOLVER_AUDIT_TARGET_ONLY = True
RESOLVER_AUDIT_TARGET_PASSES = {"NORMAL", "ROADS", "TRANSPARENT"}

# V68: actual recovery path for the pattern proven by V67:
# RES has only a tiny sparse WRLD fragment, but the row's IPL/model id has a
# rich internal LVZ+IMG model. Use that internal model with the full row matrix.
ENABLE_RICH_IPL_OVER_SPARSE_RECOVERY = False
# V71: real-new-found recovery. Never import WRLD sparse fragments as buildings.
# If the row's IPL/model id resolves to a real parsed MDL payload, use that.
# Global/area parsed MDLs are allowed again because they are actual payloads,
# but WRLD_SUBMODEL_GROUP and submodel-slice junk are always rejected.
RICH_IPL_RECOVERY_STRICT_SAME_SECTOR_OR_ROW = False
RICH_IPL_RECOVERY_ALLOWED_LABELS = {
    "exact_sector_res",
    "exact_nested_row_res",
    "exact_row_res",
    "exact_any_sector_res",
    "ipl_sector_model",
    "ipl_nested_row_model",
    "ipl_row_model",
    "ipl_global_sector_model",
    "ipl_area_model",
}
RICH_IPL_RECOVERY_REAL_MDL_KINDS = {
    "IMG_SECTOR_MDL",
    "IMG_IPL_MODEL_MDL",
    "IMG_IPL_AREA_DIRECT_MDL",
    "IMG_AREA_DIRECT_MDL",
    "MDL",
}
RICH_IPL_RECOVERY_MIN_VERTS = 160
RICH_IPL_RECOVERY_MIN_FACES = 140
RICH_IPL_RECOVERY_MIN_VERT_RATIO = 3.0
RICH_IPL_RECOVERY_MIN_FACE_RATIO = 3.0

# V72: direct row IPL recovery. The 80-byte WRLD placement row has BOTH:
#   +0x00 = IPL/model id
#   +0x02 = resource id
# Some rows have no usable RES candidate and never enter the sparse-fragment
# branch. If the IPL/model id already resolves to a real parsed MDL payload,
# place that real MDL instead of leaving the row missing.
ENABLE_REAL_IPL_FOR_MISSING_RES_ROWS = False
REAL_IPL_FOR_MISSING_ALLOWED_PASSES = {"NORMAL", "ROADS", "TRANSPARENT"}
REAL_IPL_FOR_MISSING_MIN_VERTS = 20
REAL_IPL_FOR_MISSING_MIN_FACES = 18

# V83: do not suppress sparse WRLD submodel fragments.
# The map legitimately places repeated small building pieces through row IPL/RES pairs.
# Earlier builds counted these as missing with "NOT importing bad non-LIGHTS sparse building fragment".
# That was a debug safety guess, not format truth, so it stays off for LVZ+IMG imports.
ENABLE_ROW_LOCAL_RENDER_MODEL_RECOVERY = False
ENABLE_SKIP_BAD_NONLIGHT_SPARSE_BUILDING_FRAGMENTS = False
BAD_NONLIGHT_SPARSE_MAX_VERTS = 160
BAD_NONLIGHT_SPARSE_MAX_FACES = 160
BAD_NONLIGHT_SPARSE_PASSES = {"NORMAL"}
# Last hard cases in beach are not top-level Resource[] ids and not same-sector group ranges.
# They are stable two-id placement pairs that resolve to one explicit render resource id.
# This is deliberately pair-keyed, not nearest-neighbor scanning.
FINAL_VERIFIED_RENDER_PAIR_ALIAS = {
    # V28 hard pairs proven from repeated beach placement rows.
    (407, 961): 960,
    (825, 1511): 1509,
    (1322, 1961): 1960,
    (1479, 2082): 2083,
    (82, 209): 82,
    (2536, 3239): 2536,

    # V33 converter-pack cross-check pairs. These are not sidecar placement.
    # The converter pack only gives the visible model name; the target below
    # still must exist as an actual LVZ+IMG MDL object before it is used.
    (37, 31): 37,        # beach31 uses render resource 37 in sectors 199/200.
    (496, 658): 496,     # beach658 uses render resource 496 in the LVZ+IMG pool.
    (1624, 2292): 742,   # beach2292 converter IDE/resource 742 exists in LVZ+IMG.
    (3540, 3767): 1464,  # beach3767 converter IDE/resource 1464 exists in LVZ+IMG.
    (7135, 5453): 2190,  # beach5453 converter IDE/resource 2190 exists in LVZ+IMG.
}

# Last-resort import for placement rows that still have no direct RES model.
# This uses the row's IPL/model ID as the authoritative model key and records
# every imported row in *_blds_imported_missing_mdl_report.csv.
ENABLE_FORCE_IMPORT_MISSING_IMG_MDLS = False
FORCE_IMPORT_MISSING_IMG_MDL_LOG_LIMIT = 512

# Exact-only recovery mode: do not silently fill unresolved missing rows with
# nearby substitute geometry. If the true exact IMG/IPL model cannot be found,
# the row stays missing and is reported as unresolved.
EXACT_ONLY_REAL_MISSING_MDL_RECOVERY = True
ENABLE_EXACT_IPL_RECOVERY_FOR_MISSING_ROWS = False

# V7 final-missing fallback. If the exact IPL/model-id is absent from every
# parsed resource table, clone the nearest already-imported IMG MDL and place it
# with the missing row matrix. These clones are deliberately named Beach*_... and
# marked/reported so they can be audited instead of silently hidden.
ENABLE_FINAL_MISSING_IPL_NEIGHBOR_IMPORT = False
FINAL_MISSING_IPL_NEIGHBOR_MAX_DELTA = 64
FINAL_MISSING_IPL_NEIGHBOR_LOG_LIMIT = 512
CREATE_NAMED_MISSING_MDL_COPIES = True
FORCE_MISSING_IMG_MDL_CENTER_ON_BBOX = False

# Final missing MDLs can be cloned from a nearby resource whose raw local mesh
# radius is much smaller than the IMG placement sphere.  If the row matrix does
# not already contain that scale, the copy appears as a tiny stuck model.  Fit
# only forced/final missing copies upward to the placement sphere radius.
FIT_FINAL_MISSING_MDL_TO_PLACEMENT_RADIUS = True
FIT_FINAL_MISSING_MDL_MIN_RATIO = 0.65
FIT_FINAL_MISSING_MDL_MAX_SCALE = 512.0

# Adjust the minimum and maximum aggregate group thresholds.  Some maps
# contain aggregate objects that are made up of only a handful of
# sub‑groups.  The previous minimum of 12 prevented these from being
# registered for fallback, leaving small structures unplaced.  Lower
# the minimum to one so that all aggregate groups, regardless of size,
# can contribute pieces for fallback.  Increase the maximum to a high
# value to ensure large aggregates are not excluded.  These limits
# primarily gate registration performance and do not alter safety
# checks, so widening them improves coverage without risking
# oversized substitutions.
AGGREGATE_SPLIT_MIN_GROUPS = 1
AGGREGATE_SPLIT_MAX_GROUPS = 4096
AGGREGATE_PIECE_MAX_DISTANCE_PAD = 24.0
AGGREGATE_PIECE_MIN_ACCEPT_DISTANCE = 96.0
AGGREGATE_PIECE_LOG_LIMIT = 96
AGGREGATE_GROUP_PARTS_BY_SECTOR: Dict[int, List[bpy.types.Object]] = {}
WRLD_SUBMODEL_GROUP_LOOKUP: Dict[Tuple[int, int], dict] = {}
WRLD_SUBMODEL_GROUP_GLOBAL_LOOKUP: Dict[int, dict] = {}
WRLD_SUBMODEL_GROUP_INFER_ROWS: List[dict] = []


def normalized_copy_stem(name: str) -> str:
    return re.sub(r"\s*\(\d+\)$", "", str(name or "").strip())

def read_img_from_zip(candidate: Path) -> Tuple[Optional[bytes], Optional[str]]:
    with zipfile.ZipFile(candidate, "r") as zf:
        member_name = None
        for name in zf.namelist():
            if name.lower().endswith(".img"):
                member_name = name
                break
        if member_name is None and zf.namelist():
            member_name = zf.namelist()[0]
        if member_name is None:
            return None, None
        return zf.read(member_name), candidate.name

def read_img_next_to_lvz(lvz_path: str) -> Tuple[Optional[bytes], Optional[str]]:
    lvz_p = Path(lvz_path)
    folder = lvz_p.parent
    exact_stem = lvz_p.stem
    base_stem = normalized_copy_stem(exact_stem)

    candidates: List[Path] = []
    seen = set()

    def add_candidate(candidate: Path):
        key = str(candidate).lower()
        if key in seen:
            return
        seen.add(key)
        candidates.append(candidate)

    for stem in (exact_stem, base_stem):
        if not stem:
            continue
        add_candidate(folder / f"{stem}.img")
        add_candidate(folder / f"{stem}.IMG")
        add_candidate(folder / f"{stem}.img.zip")
        add_candidate(folder / f"{stem}.IMG.zip")

    if folder.exists():
        for child in folder.iterdir():
            if not child.is_file():
                continue

            lower_name = child.name.lower()
            child_stem = None
            if lower_name.endswith(".img"):
                child_stem = child.stem
            elif lower_name.endswith(".img.zip"):
                child_stem = Path(child.stem).stem

            if child_stem is None:
                continue

            if normalized_copy_stem(child_stem).lower() == base_stem.lower():
                add_candidate(child)

    for candidate in candidates:
        if not candidate.exists():
            continue

        try:
            if candidate.name.lower().endswith(".zip"):
                img_bytes, img_name = read_img_from_zip(candidate)
                if img_bytes is not None:
                    return img_bytes, img_name
            else:
                return candidate.read_bytes(), candidate.name
        except Exception:
            continue

    if folder.exists():
        for child in folder.iterdir():
            if not child.is_file():
                continue
            if child.suffix.lower() != ".rar":
                continue
            if normalized_copy_stem(child.stem).lower() == base_stem.lower():
                return None, f"RAR archive found beside LVZ: {child.name}. Extract the .img beside the .lvz; BLeeds does not read RAR files directly."

    return None, None


def read_ide_object_id_map_next_to_lvz(lvz_path: str):
    """Read converter IDE beside LVZ.

    Stories Map Converter IDE lines look like:
        562, beach1828, beach1828, 1, 299, 0

    The first number is the converter/IPL object id. The model name suffix is
    the real beach resource id to try in LVZ/IMG.
    """
    lvz_p = Path(lvz_path)
    candidates = [
        lvz_p.with_suffix(".ide"),
        lvz_p.with_name(f"{lvz_p.stem}.ide"),
        lvz_p.with_name("beach.ide"),
        lvz_p.with_name("mainla.ide"),
    ]
    seen = set()
    paths = []
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        paths.append(c)

    ide_path = None
    for c in paths:
        try:
            if c.exists() and c.is_file():
                ide_path = c
                break
        except Exception:
            pass
    if ide_path is None:
        return {}, {}, None

    id_to_res = {}
    id_to_name = {}
    in_objs = False
    try:
        lines = ide_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        try:
            lines = ide_path.read_text(errors="replace").splitlines()
        except Exception:
            return {}, {}, str(ide_path)

    for line in lines:
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        low = raw.lower()
        if low in {"objs", "tobj"}:
            in_objs = True
            continue
        if low == "end":
            in_objs = False
            continue
        if not in_objs:
            continue
        parts = [x.strip() for x in raw.split(",")]
        if len(parts) < 2:
            continue
        try:
            obj_id = int(parts[0], 0) & 0x7FFF
        except Exception:
            continue
        model_name = parts[1].strip()
        m = re.search(r"(\d+)$", model_name)
        if not m:
            continue
        try:
            real_res = int(m.group(1), 10)
        except Exception:
            continue
        id_to_res[obj_id] = real_res
        id_to_name[obj_id] = model_name
    return id_to_res, id_to_name, str(ide_path)


def detect_lvz_img_platform(lvz_reader: LVZ.read_lvz, img_reader: Optional[LVZ.read_img]) -> str:
    if img_reader is not None:
        try:
            return img_reader.detect_platform_from_lvz_groups()
        except Exception:
            pass
    try:
        groups, _, _ = lvz_reader.parse_slave_groups_and_rescount()
        group_types = set()
        for group in groups:
            note = str(getattr(group, "note", ""))
            marker = "group_type=0x"
            if marker in note:
                part = note.split(marker, 1)[1].split()[0].strip(";,)")
                group_types.add(int(part, 16))
        nonzero = [value for value in group_types if value != 0]
        if any(value >= 0x0D for value in nonzero):
            return "PS2"
        if any(value in (0x02, 0x03) for value in nonzero):
            return "PSP"
    except Exception:
        pass
    return "PS2"

def platform_uses_ps2_swizzle(platform: str) -> bool:
    return str(platform).upper() == "PS2"

def detect_platform_from_resource_dialects(lvz_reader: LVZ.read_lvz, rows: List[Dict], fallback_platform: str) -> Tuple[str, Dict[str, int]]:
    counts: Dict[str, int] = {}
    for row in rows:
        if row.get("kind") != "MDL":
            continue
        try:
            material_list = lvz_reader.parse_mdl_material_list(
                int(row.get("res_addr", 0)),
                max_end=int(row.get("res_end", len(lvz_reader.decomp)) or len(lvz_reader.decomp)),
            )
        except Exception:
            continue
        tag = str(getattr(material_list, "format_tag", "unknown"))
        counts[tag] = counts.get(tag, 0) + 1

    psp_count = sum(value for key, value in counts.items() if key.startswith("psp_wrld"))
    ps2_count = sum(value for key, value in counts.items() if key.startswith("ps2_"))
    if psp_count > ps2_count and psp_count > 0:
        return "PSP", counts
    if ps2_count > 0:
        return "PS2", counts
    return fallback_platform, counts


def parse_stories_ipl_sidecar(ipl_path: Path) -> List[Dict]:
    rows: List[Dict] = []
    if not ipl_path or not Path(ipl_path).exists():
        return rows
    in_inst = False
    for line_number, raw_line in enumerate(Path(ipl_path).read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        low = line.lower()
        if low == "inst":
            in_inst = True
            continue
        if low == "end":
            in_inst = False
            continue
        if not in_inst:
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 12:
            continue
        try:
            inst_id = int(float(parts[0]))
            model_name = parts[1]
            match = re.search(r"(\d+)$", model_name)
            if not match:
                continue
            model_id = int(match.group(1))
            x, y, z = float(parts[2]), float(parts[3]), float(parts[4])
            sx, sy, sz = float(parts[5]), float(parts[6]), float(parts[7])
            qx, qy, qz, qw = float(parts[8]), float(parts[9]), float(parts[10]), float(parts[11])
        except Exception:
            continue
        rows.append({
            "line": line_number,
            "inst_id": inst_id,
            "model_name": model_name,
            "model_id": model_id,
            "location": (x, y, z),
            "scale": (sx, sy, sz),
            "quaternion": (qw, qx, qy, qz),
        })
    return rows


def find_stories_ipl_sidecar(lvz_path: str, stem: str) -> Optional[Path]:
    if not USE_STORIES_IPL_SIDECAR_FOR_PLACEMENT:
        return None
    lvz_p = Path(lvz_path)
    candidates = []
    if STORIES_IPL_SIDECAR_NAME_OVERRIDE:
        candidates.append(lvz_p.with_name(STORIES_IPL_SIDECAR_NAME_OVERRIDE))
    candidates.append(lvz_p.with_suffix(".ipl"))
    candidates.append(lvz_p.with_name(f"{stem}.ipl"))
    candidates.append(lvz_p.with_name(f"{stem.lower()}.ipl"))
    seen = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def get_object_model_id(obj) -> int:
    if obj is None:
        return -1
    for key in ("blds_res_index", "blds_ipl_model_id", "blds_model_id", "blds_parent_res_index"):
        try:
            value = int(obj.get(key, -1))
            if value >= 0:
                return value
        except Exception:
            pass
    name = str(getattr(obj, "name", ""))
    match = re.search(r"(?:beach|mainla|res)(\d+)", name, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except Exception:
            pass
    return -1


def choose_sidecar_base(old_obj, new_obj):
    if old_obj is None:
        return new_obj
    return choose_better_blds_candidate(old_obj, new_obj)


def build_sidecar_model_base_map(
    built_by_res: Dict[int, bpy.types.Object],
    overlay_by_sector_res: Dict[Tuple[int, int], bpy.types.Object],
    row_overlay_by_res: Dict[Tuple[int, int], bpy.types.Object],
    nested_overlay_by_res: Dict[Tuple[int, int], bpy.types.Object],
    extra_resource_objects: List[bpy.types.Object],
    ipl_overlay_by_sector_res: Dict[Tuple[int, int], bpy.types.Object],
    ipl_row_overlay_by_res: Dict[Tuple[int, int], bpy.types.Object],
    ipl_nested_overlay_by_res: Dict[Tuple[int, int], bpy.types.Object],
    ipl_extra_resource_objects: List[bpy.types.Object],
) -> Dict[int, bpy.types.Object]:
    base_by_model: Dict[int, bpy.types.Object] = {}

    def add_obj(model_id: int, obj):
        if obj is None:
            return
        try:
            model_id = int(model_id)
        except Exception:
            model_id = get_object_model_id(obj)
        if model_id < 0:
            return
        base_by_model[model_id] = choose_sidecar_base(base_by_model.get(model_id), obj)

    for model_id, obj in built_by_res.items():
        add_obj(model_id, obj)
    for (sector_index, model_id), obj in overlay_by_sector_res.items():
        add_obj(model_id, obj)
    for (row_index, model_id), obj in row_overlay_by_res.items():
        add_obj(model_id, obj)
    for (row_index, model_id), obj in nested_overlay_by_res.items():
        add_obj(model_id, obj)
    for obj in extra_resource_objects:
        add_obj(get_object_model_id(obj), obj)
    for (sector_index, model_id), obj in ipl_overlay_by_sector_res.items():
        add_obj(model_id, obj)
    for (row_index, model_id), obj in ipl_row_overlay_by_res.items():
        add_obj(model_id, obj)
    for (row_index, model_id), obj in ipl_nested_overlay_by_res.items():
        add_obj(model_id, obj)
    for obj in ipl_extra_resource_objects:
        add_obj(get_object_model_id(obj), obj)
    return base_by_model


def matrix_from_stories_ipl_row(row: Dict) -> Matrix:
    location = Vector(row.get("location", (0.0, 0.0, 0.0)))
    sx, sy, sz = row.get("scale", (1.0, 1.0, 1.0))
    quat_values = row.get("quaternion", (1.0, 0.0, 0.0, 0.0))
    quat = Quaternion(quat_values)
    try:
        quat.normalize()
    except Exception:
        quat = Quaternion((1.0, 0.0, 0.0, 0.0))
    return Matrix.LocRotScale(location, quat, Vector((float(sx), float(sy), float(sz))))


def apply_stories_ipl_sidecar_placements(
    ipl_path: Path,
    import_stem: str,
    built_by_res: Dict[int, bpy.types.Object],
    overlay_by_sector_res: Dict[Tuple[int, int], bpy.types.Object],
    extra_resource_objects: List[bpy.types.Object],
    row_overlay_by_res: Dict[Tuple[int, int], bpy.types.Object],
    nested_overlay_by_res: Dict[Tuple[int, int], bpy.types.Object],
    ipl_overlay_by_sector_res: Dict[Tuple[int, int], bpy.types.Object],
    ipl_row_overlay_by_res: Dict[Tuple[int, int], bpy.types.Object],
    ipl_nested_overlay_by_res: Dict[Tuple[int, int], bpy.types.Object],
    ipl_extra_resource_objects: List[bpy.types.Object],
) -> Tuple[int, int, int]:
    rows = parse_stories_ipl_sidecar(ipl_path)
    if not rows:
        return 0, 0, 0
    base_by_model = build_sidecar_model_base_map(
        built_by_res,
        overlay_by_sector_res or {},
        row_overlay_by_res or {},
        nested_overlay_by_res or {},
        extra_resource_objects or [],
        ipl_overlay_by_sector_res or {},
        ipl_row_overlay_by_res or {},
        ipl_nested_overlay_by_res or {},
        ipl_extra_resource_objects or [],
    )
    applied = 0
    linked = 0
    missing_rows = []
    use_count: Dict[int, int] = {}
    placed_collection = get_or_create_import_collection("BLeeds Stories IPL sidecar placers")

    for row in rows:
        model_id = int(row["model_id"])
        base_obj = base_by_model.get(model_id)
        if base_obj is None:
            missing_rows.append(row)
            continue
        index = use_count.get(model_id, 0)
        use_count[model_id] = index + 1
        obj = base_obj.copy()
        obj.data = base_obj.data
        if base_obj.animation_data is not None:
            obj.animation_data_clear()
        obj.name = f"{row['model_name']}_iplsidecar_{index:03d}"
        try:
            obj["blds_stories_ipl_sidecar"] = True
            obj["blds_sidecar_ipl_path"] = str(ipl_path)
            obj["blds_sidecar_inst_id"] = int(row["inst_id"])
            obj["blds_sidecar_model_id"] = model_id
            obj["blds_source_base_object_name"] = str(getattr(base_obj, "name", ""))
            obj["blds_visible_placement_instance"] = True
        except Exception:
            pass
        try:
            placed_collection.objects.link(obj)
        except Exception:
            try:
                bpy.context.collection.objects.link(obj)
            except Exception:
                link_object(obj)
        try:
            obj.matrix_world = matrix_from_stories_ipl_row(row)
            obj.hide_viewport = False
            obj.hide_render = False
        except Exception:
            pass
        linked += 1
        applied += 1

    base_candidates = (
        list(built_by_res.values())
        + list((overlay_by_sector_res or {}).values())
        + list((row_overlay_by_res or {}).values())
        + list((nested_overlay_by_res or {}).values())
        + list(extra_resource_objects or [])
        + list((ipl_overlay_by_sector_res or {}).values())
        + list((ipl_row_overlay_by_res or {}).values())
        + list((ipl_nested_overlay_by_res or {}).values())
        + list(ipl_extra_resource_objects or [])
        + all_aggregate_group_parts()
    )
    removed = remove_unplaced_base_objects(base_candidates, set())
    removed += purge_stale_raw_parser_bases(import_stem, reason="stories-ipl-sidecar-post-apply")

    try:
        import csv
        src_path = globals().get("_CURRENT_IMPORT_LVZ_PATH", "")
        if src_path:
            report_path = str(Path(src_path).with_suffix("")) + "_blds_stories_ipl_sidecar_report.csv"
            with open(report_path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["status", "line", "inst_id", "model_name", "model_id", "x", "y", "z", "sx", "sy", "sz", "qx", "qy", "qz", "qw"])
                for row in rows:
                    model_id = int(row["model_id"])
                    x, y, z = row["location"]
                    sx, sy, sz = row["scale"]
                    qw, qx, qy, qz = row["quaternion"]
                    status = "PLACED FROM STORIES IPL" if model_id in base_by_model else "UNRESOLVED STORIES IPL MODEL"
                    w.writerow([status, row["line"], row["inst_id"], row["model_name"], model_id, x, y, z, sx, sy, sz, qx, qy, qz, qw])
            LVZ.dbg(f"[stories-ipl] wrote sidecar placement report: {report_path}")
    except Exception as exc:
        LVZ.dbg(f"[stories-ipl] sidecar report failed: {exc}")

    if missing_rows:
        LVZ.dbg(f"[stories-ipl] unresolved sidecar model names: {len(missing_rows)}")
        for row in missing_rows[:64]:
            LVZ.dbg(f"  unresolved line={row['line']} model={row['model_name']} id={row['model_id']}")
    LVZ.dbg(f"[stories-ipl] sidecar rows={len(rows)} placed={applied} missing={len(missing_rows)} bases_deleted={removed}")
    return applied, linked, removed

def matrix_from_img_detail(detail) -> Matrix:
    origin = None
    if len(detail) > 18:
        origin = detail[18]
    return LVZ.matrix_from_16_floats_row_major_values_with_origin(detail[12], origin)


def make_missing_mdl_object_name(stem: str, detail, source_model_id: int, instance_index: int) -> str:
    try:
        requested_res_id = int(detail[0])
    except Exception:
        requested_res_id = int(source_model_id)
    return make_stories_model_name(stem, requested_res_id)


def make_stories_model_name(stem: str, model_id: int) -> str:
    clean_stem = normalized_copy_stem(stem or "beach")
    clean_stem = re.sub(r"[^A-Za-z0-9_]+", "", clean_stem)
    if not clean_stem:
        clean_stem = "beach"
    clean_stem = clean_stem[:1].upper() + clean_stem[1:]
    return f"{clean_stem}{int(model_id)}"

def _candidate_reference_dff_roots():
    roots = []
    try:
        src_path = globals().get("_CURRENT_IMPORT_LVZ_PATH", "")
        if src_path:
            p = Path(src_path).resolve()
            roots.extend([p.parent, p.parent / "beach", p.parent.parent / "beach"])
    except Exception:
        pass
    try:
        home = Path.home()
        roots.extend([home / "Desktop" / "beach", home / "Downloads" / "beach"])
    except Exception:
        pass
    out = []
    seen = set()
    for r in roots:
        try:
            key = str(r).lower()
            if key not in seen:
                seen.add(key)
                out.append(r)
        except Exception:
            pass
    return out

def _candidate_reference_dff_zips():
    zips = []
    try:
        src_path = globals().get("_CURRENT_IMPORT_LVZ_PATH", "")
        if src_path:
            p = Path(src_path).resolve()
            zips.extend(list(p.parent.glob("beach*.zip")))
            zips.extend(list(p.parent.glob("*beach*.zip")))
    except Exception:
        pass
    try:
        home = Path.home()
        zips.extend(list((home / "Desktop").glob("beach*.zip")))
        zips.extend(list((home / "Desktop").glob("*beach*.zip")))
        zips.extend(list((home / "Downloads").glob("beach*.zip")))
        zips.extend(list((home / "Downloads").glob("*beach*.zip")))
    except Exception:
        pass
    out = []
    seen = set()
    for z in zips:
        try:
            key = str(z).lower()
            if key not in seen and z.is_file():
                seen.add(key)
                out.append(z)
        except Exception:
            pass
    return out

def find_reference_dff_for_model(stem: str, model_id: int):
    model_id = int(model_id)
    stem_l = normalized_copy_stem(stem or "beach").lower()
    names = [
        f"{stem_l}{model_id}.dff",
        f"beach{model_id}.dff",
        f"mainla{model_id}.dff",
        f"lodch{model_id}.dff",
    ]
    roots_checked = []
    for root in _candidate_reference_dff_roots():
        for name in names:
            try:
                p = root / name
                roots_checked.append(str(p))
                if p.is_file():
                    try:
                        LVZ.dbg(f"[reference-dff] located RES={model_id} path={p} via root search")
                    except Exception:
                        pass
                    return p, f"reference-dff:{p}", roots_checked
            except Exception:
                pass
    zip_checked = []
    for zp in _candidate_reference_dff_zips():
        try:
            zip_checked.append(str(zp))
            with zipfile.ZipFile(zp, "r") as zf:
                lower_map = {n.lower(): n for n in zf.namelist()}
                for name in names:
                    for key in (name.lower(), f"beach/{name}".lower()):
                        member = lower_map.get(key)
                        if member:
                            cache_root = zp.parent / "_blds_ref_dff_cache"
                            cache_root.mkdir(parents=True, exist_ok=True)
                            out = cache_root / Path(member).name
                            if not out.exists() or out.stat().st_size == 0:
                                with zf.open(member) as src, open(out, "wb") as dst:
                                    dst.write(src.read())
                            try:
                                LVZ.dbg(f"[reference-dff] located RES={model_id} member={member} in zip={zp}")
                            except Exception:
                                pass
                            return out, f"reference-dff-zip:{zp.name}:{member}", roots_checked + [f"zip:{z}" for z in zip_checked]
        except Exception:
            continue
    try:
        LVZ.dbg(f"[reference-dff] not found for RES={model_id}; checked {len(roots_checked)} root candidates and {len(zip_checked)} zip files")
    except Exception:
        pass
    return None, "", roots_checked + [f"zip:{z}" for z in zip_checked]

def _rw_section_iter(data: bytes, start: int = 0, end: Optional[int] = None):
    if end is None or end > len(data):
        end = len(data)
    off = int(start)
    while off + 12 <= end:
        try:
            sid, size, ver = struct.unpack_from("<III", data, off)
        except Exception:
            break
        body = off + 12
        next_off = body + int(size)
        if size < 0 or next_off > end or next_off <= off:
            break
        yield int(sid), int(body), int(size), int(ver), int(off)
        off = next_off

def _find_rw_sections_recursive(data: bytes, want_id: int, start: int = 0, end: Optional[int] = None, depth: int = 0):
    if end is None or end > len(data):
        end = len(data)
    if depth > 16:
        return
    for sid, body, size, ver, hdr in _rw_section_iter(data, start, end):
        if sid == int(want_id):
            yield (sid, body, size, ver, hdr)
        # Container sections usually contain nested chunks. Try recursive scanning
        # regardless of section id; invalid child walks exit fast.
        if size >= 12:
            yield from _find_rw_sections_recursive(data, want_id, body, body + size, depth + 1)

def _parse_rw_geometry_struct_candidates(data: bytes, body: int, size: int):
    end = int(body) + int(size)
    out = []
    # Geometry struct sometimes has old-version surface props after the counts.
    for payload_start_extra in (16, 28):
        try:
            if body + payload_start_extra > end:
                continue
            flags, num_tri, num_vert, num_morph = struct.unpack_from("<IIII", data, body)
            flags = int(flags)
            num_tri = int(num_tri)
            num_vert = int(num_vert)
            num_morph = int(num_morph)
            if num_vert <= 0 or num_vert > 250000 or num_tri < 0 or num_tri > 500000 or num_morph <= 0 or num_morph > 8:
                continue
            # Native RenderWare geometry stores platform payloads elsewhere. The
            # converter-pack DFFs we want are PC-style non-native geometry.
            if flags & 0x01000000:
                continue
            uv_sets = (flags >> 16) & 0xFF
            if uv_sets <= 0:
                if flags & 0x80:
                    uv_sets = 2
                elif flags & 0x04:
                    uv_sets = 1
                else:
                    uv_sets = 0
            off = body + payload_start_extra
            if flags & 0x08:  # prelit vertex colors
                off += num_vert * 4
            off += num_vert * 8 * uv_sets
            tri_off = off
            off += num_tri * 8
            if off + 24 > end:
                continue
            # Only first morph target is used as the local mesh.
            sx, sy, sz, sr = struct.unpack_from("<ffff", data, off)
            off += 16
            has_pos, has_norm = struct.unpack_from("<II", data, off)
            off += 8
            if not has_pos:
                continue
            vert_off = off
            off += num_vert * 12
            if has_norm:
                off += num_vert * 12
            if off > end:
                continue
            verts = []
            bad = False
            max_abs = 0.0
            for i in range(num_vert):
                x, y, z = struct.unpack_from("<fff", data, vert_off + i * 12)
                if not (-1.0e8 < x < 1.0e8 and -1.0e8 < y < 1.0e8 and -1.0e8 < z < 1.0e8):
                    bad = True
                    break
                max_abs = max(max_abs, abs(float(x)), abs(float(y)), abs(float(z)))
                verts.append((float(x), float(y), float(z)))
            if bad or max_abs <= 0.00001:
                continue
            faces = []
            for i in range(num_tri):
                v2, v1, mat, v3 = struct.unpack_from("<HHHH", data, tri_off + i * 8)
                if v1 < num_vert and v2 < num_vert and v3 < num_vert and len({int(v1), int(v2), int(v3)}) == 3:
                    faces.append((int(v1), int(v2), int(v3)))
            if not faces:
                continue
            out.append((verts, faces, flags, uv_sets))
        except Exception:
            continue
    return out

def _parse_reference_dff_meshes_lightweight(dff_path: Path):
    data = Path(dff_path).read_bytes()
    meshes = []
    for sid, body, size, ver, hdr in _find_rw_sections_recursive(data, 0x0F):
        # Geometry chunk contains a Struct child.
        for csid, cbody, csize, cver, chdr in _rw_section_iter(data, body, body + size):
            if csid != 0x01:
                continue
            for verts, faces, flags, uv_sets in _parse_rw_geometry_struct_candidates(data, cbody, csize):
                meshes.append((verts, faces, flags, uv_sets))
            break
    return meshes

def reference_dff_proof_stats_only(stem: str, model_id: int):
    """Parse exact reference DFF for diagnostics only.  Never creates or returns a Blender object."""
    if not ENABLE_REFERENCE_DFF_EXACT_GEOMETRY_FOR_MISSING:
        return None, ""
    model_id = int(model_id)
    cached = REFERENCE_DFF_STATS_CACHE.get(model_id)
    if cached is not None:
        REFERENCE_DFF_DEBUG_ROWS.append({
            "res_id": model_id,
            "decision": "stat-cache-hit-debug-only",
            "source": str(cached.get("source", "")),
            "import_mode": "stat_only_internal_lightweight_rw_dff",
            "object_name": "",
            "verts": int(cached.get("reference_verts", 0)),
            "faces": int(cached.get("reference_faces", 0)),
        })
        return dict(cached), str(cached.get("source", "reference-dff-stat-cache"))
    dff_path, source, checked = find_reference_dff_for_model(stem, model_id)
    if not dff_path:
        REFERENCE_DFF_DEBUG_ROWS.append({
            "res_id": model_id,
            "decision": "not-found-debug-only",
            "checked": " | ".join(map(str, checked[:40])),
        })
        return None, ""
    try:
        meshes = _parse_reference_dff_meshes_lightweight(Path(dff_path))
        all_verts = []
        all_faces = []
        for verts, faces, flags, uv_sets in meshes:
            base = len(all_verts)
            all_verts.extend(verts)
            all_faces.extend([(int(a) + base, int(b) + base, int(c) + base) for a, b, c in faces])
        if not all_verts or not all_faces:
            REFERENCE_DFF_DEBUG_ROWS.append({
                "res_id": model_id,
                "decision": "stat-parse-empty-debug-only",
                "path": str(dff_path),
                "source": str(source),
                "checked": " | ".join(map(str, checked[:40])),
            })
            return None, ""
        stats = _proof_stats_from_vertices_faces(all_verts, all_faces, "reference")
        stats["source"] = str(source)
        stats["path"] = str(dff_path)
        stats["import_mode"] = "stat_only_internal_lightweight_rw_dff"
        stats["reference_mesh_count"] = int(len(meshes))
        REFERENCE_DFF_STATS_CACHE[model_id] = dict(stats)
        REFERENCE_DFF_DEBUG_ROWS.append({
            "res_id": model_id,
            "decision": "parsed-reference-dff-stats-debug-only",
            "path": str(dff_path),
            "source": str(source),
            "import_mode": "stat_only_internal_lightweight_rw_dff",
            "object_name": "",
            "verts": int(stats.get("reference_verts", 0)),
            "faces": int(stats.get("reference_faces", 0)),
            "checked": " | ".join(map(str, checked[:40])),
        })
        try:
            LVZ.dbg(
                f"[reference-dff] RES={model_id} parsed stats only "
                f"objects={len(meshes)} verts={int(stats.get('reference_verts', 0))} "
                f"faces={int(stats.get('reference_faces', 0))} source={source}"
            )
        except Exception:
            pass
        return dict(stats), str(source)
    except Exception as exc:
        REFERENCE_DFF_DEBUG_ROWS.append({
            "res_id": model_id,
            "decision": "stat-parse-failed-debug-only",
            "path": str(dff_path),
            "source": str(source),
            "import_mode": "stat_only_internal_lightweight_rw_dff",
            "checked": " | ".join(map(str, checked[:40])),
        })
        try:
            LVZ.dbg(f"[reference-dff] stat-only parse failed for RES={model_id} path={dff_path}: {exc}")
        except Exception:
            pass
        return None, ""

def _build_reference_dff_object_lightweight(stem: str, model_id: int, dff_path: Path, source: str):
    meshes = _parse_reference_dff_meshes_lightweight(dff_path)
    if not meshes:
        return None
    all_verts = []
    all_faces = []
    for verts, faces, flags, uv_sets in meshes:
        base = len(all_verts)
        all_verts.extend(verts)
        all_faces.extend([(a + base, b + base, c + base) for a, b, c in faces])
    if not all_verts or not all_faces:
        return None
    name = make_stories_model_name(stem, int(model_id))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(all_verts, [], all_faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    try:
        bpy.context.collection.objects.link(obj)
    except Exception:
        try:
            bpy.context.scene.collection.objects.link(obj)
        except Exception:
            pass
    obj.matrix_world = Matrix.Identity(4)
    try:
        obj["blds_kind"] = "REFERENCE_DFF_EXACT_MODEL"
        obj["blds_reference_dff_geometry"] = True
        obj["blds_reference_dff_source"] = str(source)
        obj["blds_reference_dff_importer"] = "internal_lightweight_rw_dff"
        obj["blds_res_index"] = int(model_id)
        obj["blds_world_baked"] = False
    except Exception:
        pass
    try:
        obj["blds_reference_dff_mesh_count"] = int(len(meshes))
        obj["blds_reference_dff_vert_count"] = int(len(all_verts))
        obj["blds_reference_dff_face_count"] = int(len(all_faces))
    except Exception:
        pass
    try:
        LVZ.dbg(
            f"[reference-dff] RES={model_id} parsed exact converter geometry internally "
            f"objects={len(meshes)} verts={len(all_verts)} faces={len(all_faces)} source={source}"
        )
    except Exception:
        pass
    return obj

def _try_registered_dff_operator(dff_path: Path):
    # Try common DFF importer operator ids, but do not require any of them.
    candidates = (
        ("import_scene", "dff"),
        ("import_scene", "dragonff_dff"),
        ("import_scene", "demonff_dff"),
        ("import_scene", "gta_dff"),
        ("import_scene", "import_dff"),
        ("import_mesh", "dff"),
        ("import_mesh", "dragonff_dff"),
        ("import_mesh", "demonff_dff"),
        ("import_mesh", "gta_dff"),
    )
    for group_name, op_name in candidates:
        try:
            group = getattr(bpy.ops, group_name)
            op = getattr(group, op_name)
        except Exception:
            continue
        try:
            before = set(bpy.data.objects)
            op(filepath=str(dff_path))
            new_objs = [o for o in bpy.data.objects if o not in before]
            mesh_objs = [o for o in new_objs if getattr(o, "type", "") == "MESH"]
            if mesh_objs:
                return mesh_objs[0], new_objs, f"{group_name}.{op_name}"
        except Exception:
            continue
    return None, [], ""

def import_reference_dff_model_base(stem: str, model_id: int):
    if not ENABLE_REFERENCE_DFF_EXACT_GEOMETRY_FOR_MISSING:
        return None, ""
    model_id = int(model_id)
    if model_id in REFERENCE_DFF_CACHE:
        REFERENCE_DFF_DEBUG_ROWS.append({"res_id": model_id, "decision": "cache-hit", "source": "reference-dff-cache"})
        return REFERENCE_DFF_CACHE[model_id], "reference-dff-cache"
    if model_id in REFERENCE_DFF_MISS_CACHE:
        REFERENCE_DFF_DEBUG_ROWS.append({"res_id": model_id, "decision": "miss-cache-skip"})
        return None, ""
    dff_path, source, checked = find_reference_dff_for_model(stem, model_id)
    if not dff_path:
        REFERENCE_DFF_MISS_CACHE.add(model_id)
        REFERENCE_DFF_DEBUG_ROWS.append({"res_id": model_id, "decision": "not-found", "checked": " | ".join(map(str, checked[:40]))})
        return None, ""

    obj = None
    new_objs = []
    operator_source = ""
    import_mode = ""
    try:
        obj, new_objs, operator_source = _try_registered_dff_operator(Path(dff_path))
    except Exception:
        obj = None
        new_objs = []
        operator_source = ""

    if obj is not None:
        source = f"{source}:operator={operator_source}"
        import_mode = f"operator:{operator_source}"
        for extra in new_objs:
            if extra is obj:
                continue
            try:
                bpy.data.objects.remove(extra, do_unlink=True)
            except Exception:
                pass
    else:
        try:
            obj = _build_reference_dff_object_lightweight(stem, model_id, Path(dff_path), source)
            if obj is not None:
                import_mode = "internal_lightweight_rw_dff"
        except Exception as exc:
            try:
                LVZ.dbg(f"[reference-dff] internal parser failed for RES={model_id} path={dff_path}: {exc}")
            except Exception:
                pass
            obj = None

    if obj is None:
        try:
            LVZ.dbg(
                f"[reference-dff] no registered DFF operator and internal parser failed for "
                f"RES={model_id} path={dff_path}; falling back to LVZ/IMG geometry"
            )
        except Exception:
            pass
        REFERENCE_DFF_DEBUG_ROWS.append({
            "res_id": model_id,
            "decision": "import-failed-fallback-lvz-img",
            "path": str(dff_path),
            "source": str(source),
            "checked": " | ".join(map(str, checked[:40])),
        })
        REFERENCE_DFF_MISS_CACHE.add(model_id)
        return None, ""

    obj.name = make_stories_model_name(stem, model_id)
    try:
        obj.data.name = obj.name
    except Exception:
        pass
    try:
        obj.matrix_world = Matrix.Identity(4)
        obj["blds_kind"] = "REFERENCE_DFF_EXACT_MODEL"
        obj["blds_reference_dff_geometry"] = True
        obj["blds_reference_dff_source"] = str(source)
        obj["blds_reference_dff_import_mode"] = str(import_mode or "unknown")
        obj["blds_res_index"] = int(model_id)
        obj["blds_world_baked"] = False
    except Exception:
        pass

    REFERENCE_DFF_CACHE[model_id] = obj
    try:
        LVZ.dbg(f"[reference-dff] RES={model_id} parsed exact converter geometry for debug/proof only {source}")
    except Exception:
        pass
    try:
        REFERENCE_DFF_DEBUG_ROWS.append({
            "res_id": model_id,
            "decision": "parsed-exact-reference-dff-debug-only",
            "path": str(dff_path),
            "source": str(source),
            "import_mode": str(import_mode or "unknown"),
            "object_name": str(getattr(obj, "name", "")),
            "verts": int(obj.get("blds_reference_dff_vert_count", 0)),
            "faces": int(obj.get("blds_reference_dff_face_count", 0)),
            "checked": " | ".join(map(str, checked[:40])),
        })
    except Exception:
        pass
    return obj, source

def make_exact_placement_object_name(stem: str, detail, source_model_id: int, instance_index: int, exact_missing: bool = False) -> str:
    try:
        requested_res_id = int(detail[0])
    except Exception:
        requested_res_id = int(source_model_id)
    return make_stories_model_name(stem, requested_res_id)


def matrix_to_report_values(matrix: Matrix):
    values = []
    try:
        for row in range(4):
            for col in range(4):
                values.append(float(matrix[row][col]))
    except Exception:
        values = [0.0] * 16
    while len(values) < 16:
        values.append(0.0)
    return values[:16]

def make_visible_placement_dedupe_key(ipl_id: int, res_id: int, pass_name: str, matrix: Matrix):
    vals = matrix_to_report_values(matrix)
    # Use the visible transform, not sector/container id. Same visible object can be repeated
    # through overlapping sector/extra containers; those should import once.
    rounded = tuple(round(float(v), 4) for v in vals[:12])
    return (int(ipl_id), int(res_id), str(pass_name), rounded)


def matrix_basis_max_scale(matrix: Matrix) -> float:
    try:
        a = matrix.to_3x3()
        return max(float(a.col[0].length), float(a.col[1].length), float(a.col[2].length))
    except Exception:
        try:
            return max(
                (float(matrix[0][0]) ** 2 + float(matrix[1][0]) ** 2 + float(matrix[2][0]) ** 2) ** 0.5,
                (float(matrix[0][1]) ** 2 + float(matrix[1][1]) ** 2 + float(matrix[2][1]) ** 2) ** 0.5,
                (float(matrix[0][2]) ** 2 + float(matrix[1][2]) ** 2 + float(matrix[2][2]) ** 2) ** 0.5,
            )
        except Exception:
            return 1.0

def matrix_basis_column_scales(matrix: Matrix) -> Tuple[float, float, float]:
    try:
        a = matrix.to_3x3()
        return (float(a.col[0].length), float(a.col[1].length), float(a.col[2].length))
    except Exception:
        try:
            return (
                (float(matrix[0][0]) ** 2 + float(matrix[1][0]) ** 2 + float(matrix[2][0]) ** 2) ** 0.5,
                (float(matrix[0][1]) ** 2 + float(matrix[1][1]) ** 2 + float(matrix[2][1]) ** 2) ** 0.5,
                (float(matrix[0][2]) ** 2 + float(matrix[1][2]) ** 2 + float(matrix[2][2]) ** 2) ** 0.5,
            )
        except Exception:
            return (1.0, 1.0, 1.0)


def matrix_has_wrld_cell_scale(matrix: Matrix) -> bool:
    sx, sy, sz = matrix_basis_column_scales(matrix)
    return max(abs(float(sx)), abs(float(sy))) >= float(IPL_FALLBACK_CELL_SCALE_MIN)


def matrix_with_wrld_cell_scale_stripped(matrix: Matrix) -> Matrix:
    fixed = matrix.copy()
    try:
        for col in range(3):
            length = (float(fixed[0][col]) ** 2 + float(fixed[1][col]) ** 2 + float(fixed[2][col]) ** 2) ** 0.5
            if length > 0.000001:
                fixed[0][col] = float(fixed[0][col]) / length
                fixed[1][col] = float(fixed[1][col]) / length
                fixed[2][col] = float(fixed[2][col]) / length
    except Exception:
        return matrix
    return fixed


def ipl_fallback_fits_detail(detail, obj):
    if not IPL_FALLBACK_SIZE_GATE_ENABLED:
        return True, "disabled"
    try:
        sr = max(0.0, float(detail[8]))
    except Exception:
        sr = 0.0
    try:
        cr = max(0.0, float(obj.get("blds_local_radius", 0.0)))
    except Exception:
        cr = 0.0

    if cr <= 0.0:
        return True, "no-object-radius"

    matrix = matrix_from_img_detail(detail)
    scale = max(0.000001, matrix_basis_max_scale(matrix))
    scaled = cr * scale
    limit = max(IPL_FALLBACK_MIN_ACCEPT_RADIUS, sr * IPL_FALLBACK_RADIUS_MULT)

    if scaled > limit:
        return False, f"scaled_radius={scaled:.3f} object_radius={cr:.3f} matrix_scale={scale:.3f} sphere_radius={sr:.3f} limit={limit:.3f}"
    return True, f"scaled_radius={scaled:.3f} sphere_radius={sr:.3f} limit={limit:.3f}"


def matrix_from_img_detail_centered_on_object(detail, obj) -> Matrix:
    matrix = matrix_from_img_detail(detail)
    try:
        cx, cy, cz, radius = object_bbox_center_radius(obj)
    except Exception:
        return matrix
    if radius <= 0.0:
        return matrix
    # Some VCS rows use IPL/model-id fallback resources whose mesh verts are not authored
    # around 0,0,0. Applying the placement matrix directly then throws big slabs/walls
    # off to the side. Center the mesh's local bounds before applying the row matrix.
    return matrix @ Matrix.Translation((-float(cx), -float(cy), -float(cz)))


def matrix_from_img_detail_radius_fit_for_object(detail, obj):
    matrix = matrix_from_img_detail(detail)
    did_fit = False
    scale_factor = 1.0
    local_radius = 0.0
    target_radius = 0.0
    world_radius = 0.0
    try:
        target_radius = float(detail[8])
    except Exception:
        target_radius = 0.0
    try:
        _, _, _, local_radius = object_bbox_center_radius(obj)
        local_radius = float(local_radius)
    except Exception:
        local_radius = 0.0
    try:
        world_radius = float(local_radius) * float(matrix_basis_max_scale(matrix))
    except Exception:
        world_radius = 0.0

    if (
        bool(FIT_FINAL_MISSING_MDL_TO_PLACEMENT_RADIUS)
        and local_radius > 0.000001
        and target_radius > 0.000001
        and world_radius > 0.000001
        and world_radius < (target_radius * float(FIT_FINAL_MISSING_MDL_MIN_RATIO))
    ):
        scale_factor = min(float(FIT_FINAL_MISSING_MDL_MAX_SCALE), target_radius / world_radius)
        if scale_factor > 1.000001:
            fitted = matrix.copy()
            for row in range(3):
                for col in range(3):
                    fitted[row][col] = float(fitted[row][col]) * float(scale_factor)
            matrix = fitted
            did_fit = True

    return matrix, did_fit, scale_factor, local_radius, target_radius, world_radius

def build_mesh_from_mdl_groups(stem: str, res_index: int, groups: List[LVZ.MDLStripGroup]):
    if not groups:
        return None, []

    vertices: List[Tuple[float, float, float]] = []
    uvs: List[Tuple[float, float]] = []
    faces: List[Tuple[int, int, int]] = []
    face_ranges: List[Tuple[int, int, int]] = []

    for group in groups:
        for strip in group.strips:
            count = min(len(strip.verts), len(strip.uvs), int(strip.count))
            if count < 3:
                continue
            base = len(vertices)
            vertices.extend(strip.verts[:count])
            uvs.extend(strip.uvs[:count])
            poly_start = len(faces)
            for i in range(count - 2):
                if i & 1:
                    faces.append((base + i + 1, base + i, base + i + 2))
                else:
                    faces.append((base + i, base + i + 1, base + i + 2))
            face_ranges.append((poly_start, count - 2, strip.material_res_index))

    if not vertices or not faces:
        return None, []

    mesh_name = f"{stem}{res_index}"
    mesh = bpy.data.meshes.new(mesh_name)
    mesh.from_pydata(vertices, [], faces)
    set_mesh_auto_smooth(mesh, True)
    mesh.validate(clean_customdata=False)
    mesh.update()

    if uvs:
        uv_layer = mesh.uv_layers.new(name="UVMap")
        uv_data = uv_layer.data
        for poly in mesh.polygons:
            loop_start = poly.loop_start
            for loop_index, vertex_index in enumerate(poly.vertices):
                if vertex_index < len(uvs):
                    uv_data[loop_start + loop_index].uv = uvs[vertex_index]

    obj = bpy.data.objects.new(mesh_name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj["blds_kind"] = "MDL"
    obj["blds_res_index"] = int(res_index)
    obj["blds_groups"] = len(groups)
    obj["blds_faces"] = len(faces)
    obj["blds_verts"] = len(vertices)
    xs = [float(v[0]) for v in vertices]
    ys = [float(v[1]) for v in vertices]
    zs = [float(v[2]) for v in vertices]
    cx = (min(xs) + max(xs)) * 0.5
    cy = (min(ys) + max(ys)) * 0.5
    cz = (min(zs) + max(zs)) * 0.5
    radius = 0.0
    for x, y, z in vertices:
        dx = float(x) - cx
        dy = float(y) - cy
        dz = float(z) - cz
        radius = max(radius, (dx * dx + dy * dy + dz * dz) ** 0.5)
    obj["blds_local_radius"] = float(radius)
    obj["blds_bbox_min"] = (float(min(xs)), float(min(ys)), float(min(zs)))
    obj["blds_bbox_max"] = (float(max(xs)), float(max(ys)), float(max(zs)))
    return obj, face_ranges


def score_mdl_groups_for_preselect(groups) -> float:
    if not groups:
        return -1.0
    group_count = 0
    vert_count = 0
    face_count = 0
    xs = []
    ys = []
    zs = []
    try:
        for group in groups:
            group_count += 1
            for strip in getattr(group, "strips", []) or []:
                count = min(len(getattr(strip, "verts", []) or []), len(getattr(strip, "uvs", []) or []), int(getattr(strip, "count", 0) or 0))
                if count < 3:
                    continue
                vert_count += count
                face_count += max(0, count - 2)
                for x, y, z in strip.verts[:count]:
                    xs.append(float(x))
                    ys.append(float(y))
                    zs.append(float(z))
    except Exception:
        return -1.0
    if vert_count <= 0 or face_count <= 0:
        return -1.0
    radius = 0.0
    if xs:
        cx = (min(xs) + max(xs)) * 0.5
        cy = (min(ys) + max(ys)) * 0.5
        cz = (min(zs) + max(zs)) * 0.5
        for x, y, z in zip(xs, ys, zs):
            dx = float(x) - cx
            dy = float(y) - cy
            dz = float(z) - cz
            radius = max(radius, (dx * dx + dy * dy + dz * dz) ** 0.5)
    return (float(face_count) * 8.0) + (float(vert_count) * 2.0) + (float(group_count) * 64.0) + min(max(float(radius), 0.0), 4096.0)

def reset_aggregate_group_parts():
    AGGREGATE_GROUP_PARTS_BY_SECTOR.clear()
    WRLD_SUBMODEL_GROUP_LOOKUP.clear()
    WRLD_SUBMODEL_GROUP_GLOBAL_LOOKUP.clear()
    WRLD_SUBMODEL_GROUP_INFER_ROWS.clear()

def all_aggregate_group_parts():
    # Only return Blender objects that were actually created lazily.
    parts = []
    for sector_parts in AGGREGATE_GROUP_PARTS_BY_SECTOR.values():
        for part in sector_parts:
            if isinstance(part, dict):
                obj = part.get("obj")
                if obj is not None:
                    parts.append(obj)
            elif part is not None:
                parts.append(part)
    return parts

def object_bbox_center_radius(obj):
    try:
        mn = obj.get("blds_bbox_min", None)
        mx = obj.get("blds_bbox_max", None)
        if mn is not None and mx is not None:
            cx = (float(mn[0]) + float(mx[0])) * 0.5
            cy = (float(mn[1]) + float(mx[1])) * 0.5
            cz = (float(mn[2]) + float(mx[2])) * 0.5
            radius = float(obj.get("blds_local_radius", 0.0))
            return (cx, cy, cz, radius)
    except Exception:
        pass
    return (0.0, 0.0, 0.0, 0.0)

def object_geometry_counts_radius(obj):
    verts = 0
    faces = 0
    radius = 0.0
    try:
        verts = int(obj.get("blds_verts", 0))
    except Exception:
        verts = 0
    try:
        faces = int(obj.get("blds_faces", 0))
    except Exception:
        faces = 0
    try:
        radius = float(obj.get("blds_local_radius", 0.0))
    except Exception:
        radius = 0.0
    try:
        mesh = getattr(obj, "data", None)
        if mesh is not None:
            if verts <= 0:
                verts = len(getattr(mesh, "vertices", []) or [])
            if faces <= 0:
                faces = len(getattr(mesh, "polygons", []) or [])
    except Exception:
        pass
    if radius <= 0.0:
        try:
            _, _, _, radius = object_bbox_center_radius(obj)
            radius = float(radius)
        except Exception:
            radius = 0.0
    return int(verts), int(faces), float(radius)


def format_blds_vec(value):
    try:
        return ",".join(f"{float(v):.6f}" for v in value)
    except Exception:
        return str(value)


def rebase_wrld_submodel_mesh_origin_to_bbox_center(obj):
    """
    Fast V54 version.

    Recovered WRLD submodel groups can carry vertices in parent/group-local
    space.  Rebase the shared mesh once, then stamp every object that uses it.
    Older V51 copied/rebased the mesh per duplicate object, which made imports
    crawl on dense maps.
    """
    try:
        mesh = getattr(obj, "data", None)

        # Object already stamped.
        if bool(obj.get("blds_wrld_submodel_origin_rebased", False)):
            try:
                parts = str(obj.get("blds_wrld_submodel_origin_offset", "0,0,0")).split(",")
                return False, float(parts[0]), float(parts[1]), float(parts[2]), float(obj.get("blds_local_radius", 0.0))
            except Exception:
                return False, 0.0, 0.0, 0.0, float(obj.get("blds_local_radius", 0.0))

        # Mesh already rebased by the first instance; do NOT copy/rebase again.
        if mesh is not None:
            try:
                if bool(mesh.get("blds_wrld_submodel_origin_rebased", False)):
                    off = str(mesh.get("blds_wrld_submodel_origin_offset", "0,0,0"))
                    parts = off.split(",")
                    radius = float(mesh.get("blds_wrld_submodel_origin_radius", obj.get("blds_local_radius", 0.0)))
                    obj["blds_wrld_submodel_origin_rebased"] = True
                    obj["blds_wrld_submodel_origin_offset"] = off
                    obj["blds_local_radius"] = float(radius)
                    try:
                        obj["blds_bbox_min"] = tuple(mesh.get("blds_wrld_submodel_rebased_bbox_min", obj.get("blds_bbox_min", (0.0, 0.0, 0.0))))
                        obj["blds_bbox_max"] = tuple(mesh.get("blds_wrld_submodel_rebased_bbox_max", obj.get("blds_bbox_max", (0.0, 0.0, 0.0))))
                    except Exception:
                        pass
                    return False, float(parts[0]), float(parts[1]), float(parts[2]), radius
            except Exception:
                pass

        cx, cy, cz, radius = object_bbox_center_radius(obj)
        cx = float(cx)
        cy = float(cy)
        cz = float(cz)
        radius = float(radius)
        if radius <= 0.000001:
            return False, cx, cy, cz, radius

        if max(abs(cx), abs(cy), abs(cz)) <= 0.000001:
            obj["blds_wrld_submodel_origin_rebased"] = False
            obj["blds_wrld_submodel_origin_offset"] = "0.000000,0.000000,0.000000"
            if mesh is not None:
                try:
                    mesh["blds_wrld_submodel_origin_rebased"] = False
                    mesh["blds_wrld_submodel_origin_offset"] = "0.000000,0.000000,0.000000"
                    mesh["blds_wrld_submodel_origin_radius"] = float(radius)
                except Exception:
                    pass
            return False, cx, cy, cz, radius

        if mesh is None or not hasattr(mesh, "vertices"):
            return False, cx, cy, cz, radius

        # Intentionally do NOT copy when mesh.users > 1.  The mesh is shared by
        # duplicates of the same recovered submodel; one shared rebase is the
        # correct and fast operation.
        for v in mesh.vertices:
            v.co.x = float(v.co.x) - cx
            v.co.y = float(v.co.y) - cy
            v.co.z = float(v.co.z) - cz
        try:
            mesh.update()
        except Exception:
            pass

        rebased_min = None
        rebased_max = None
        try:
            mn = obj.get("blds_bbox_min", None)
            mx = obj.get("blds_bbox_max", None)
            if mn is not None and mx is not None:
                rebased_min = (float(mn[0]) - cx, float(mn[1]) - cy, float(mn[2]) - cz)
                rebased_max = (float(mx[0]) - cx, float(mx[1]) - cy, float(mx[2]) - cz)
                obj["blds_bbox_min"] = rebased_min
                obj["blds_bbox_max"] = rebased_max
        except Exception:
            pass

        obj["blds_local_radius"] = float(radius)
        obj["blds_wrld_submodel_origin_rebased"] = True
        obj["blds_wrld_submodel_origin_offset"] = f"{cx:.6f},{cy:.6f},{cz:.6f}"
        try:
            mesh["blds_wrld_submodel_origin_rebased"] = True
            mesh["blds_wrld_submodel_origin_offset"] = f"{cx:.6f},{cy:.6f},{cz:.6f}"
            mesh["blds_wrld_submodel_origin_radius"] = float(radius)
            if rebased_min is not None and rebased_max is not None:
                mesh["blds_wrld_submodel_rebased_bbox_min"] = rebased_min
                mesh["blds_wrld_submodel_rebased_bbox_max"] = rebased_max
        except Exception:
            pass
        return True, cx, cy, cz, radius
    except Exception:
        return False, 0.0, 0.0, 0.0, 0.0


def should_preserve_world_baked_submodel_matrix(obj, matrix):
    """
    Some recovered WRLD submodel groups are already in world space and must keep
    identity; others are local submodel pieces like beach1881 and must receive
    the row matrix.  Decide by comparing the raw group bbox center to the row
    translation.  This prevents the old all-or-nothing V30 identity override.
    """
    try:
        cx, cy, cz, radius = object_bbox_center_radius(obj)
        tx = float(matrix[0][3])
        ty = float(matrix[1][3])
        tz = float(matrix[2][3])
        dx = float(cx) - tx
        dy = float(cy) - ty
        dz = float(cz) - tz
        dist = (dx * dx + dy * dy + dz * dz) ** 0.5
        threshold = max(384.0, min(4096.0, float(radius) * 2.0))
        obj["blds_world_baked_bbox_center"] = f"{cx:.6f},{cy:.6f},{cz:.6f}"
        obj["blds_world_baked_row_translation"] = f"{tx:.6f},{ty:.6f},{tz:.6f}"
        obj["blds_world_baked_center_to_row_distance"] = float(dist)
        obj["blds_world_baked_identity_threshold"] = float(threshold)
        return bool(dist <= threshold)
    except Exception:
        return bool(obj.get("blds_world_baked", False))

def group_bbox_center_radius(group):
    xs = []
    ys = []
    zs = []
    try:
        for strip in getattr(group, "strips", []) or []:
            for v in getattr(strip, "verts", []) or []:
                xs.append(float(v[0]))
                ys.append(float(v[1]))
                zs.append(float(v[2]))
    except Exception:
        return None
    if not xs:
        return None
    cx = (min(xs) + max(xs)) * 0.5
    cy = (min(ys) + max(ys)) * 0.5
    cz = (min(zs) + max(zs)) * 0.5
    radius = 0.0
    for x, y, z in zip(xs, ys, zs):
        dx = x - cx
        dy = y - cy
        dz = z - cz
        radius = max(radius, (dx * dx + dy * dy + dz * dz) ** 0.5)
    return (cx, cy, cz, radius, (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))

def detail_sphere_center_radius(detail):
    try:
        return (float(detail[5]), float(detail[6]), float(detail[7]), max(0.0, float(detail[8])))
    except Exception:
        return (0.0, 0.0, 0.0, 0.0)

def build_aggregate_group_part_object(stem: str, sector_index: int, parent_res_id: int, group_index: int, group, material_list, material_by_res_index):
    obj, face_ranges = build_mesh_from_mdl_groups(
        f"{stem}_sec{sector_index:04d}_agg{parent_res_id}_g",
        int(group_index),
        [group],
    )
    if obj is None:
        return None
    obj.name = f"{stem}_sec{sector_index:04d}_agg{parent_res_id}_g{group_index:03d}"
    obj.data.name = obj.name
    try:
        add_material_slots(obj, material_by_res_index, material_list, face_ranges)
    except Exception:
        pass
    obj["blds_kind"] = "IMG_AGGREGATE_GROUP_PART"
    obj["blds_world_baked"] = True
    obj["blds_aggregate_piece"] = True
    obj["blds_parent_res_index"] = int(parent_res_id)
    obj["blds_res_index"] = int(parent_res_id)
    obj["blds_img_sector_index"] = int(sector_index)
    obj["blds_group_index"] = int(group_index)
    return obj

def register_aggregate_group_parts(stem: str, sector_index: int, res_id: int, groups, material_list, material_by_res_index, origin=(0.0, 0.0, 0.0)):
    if not (ENABLE_AGGREGATE_PIECE_FALLBACK or ENABLE_WRLD_SUBMODEL_GROUP_ID_RECOVERY):
        return 0
    group_count = len(groups or [])
    if group_count < AGGREGATE_SPLIT_MIN_GROUPS:
        return 0
    if group_count > AGGREGATE_SPLIT_MAX_GROUPS:
        return 0

    parts = AGGREGATE_GROUP_PARTS_BY_SECTOR.setdefault(int(sector_index), [])
    registered = 0
    for group_index, group in enumerate(groups):
        info = group_bbox_center_radius(group)
        if info is None:
            continue
        cx, cy, cz, cr, mn, mx = info
        # Store a cheap descriptor. Do NOT create thousands of Blender objects up front.
        parts.append({
            "obj": None,
            "stem": stem,
            "sector_index": int(sector_index),
            "origin": tuple(float(v) for v in (origin or (0.0, 0.0, 0.0))),
            "parent_res_id": int(res_id),
            "group_index": int(group_index),
            "group": group,
            "material_list": material_list,
            "material_by_res_index": material_by_res_index,
            "center": (float(cx), float(cy), float(cz)),
            "radius": float(cr),
            "bbox_min": tuple(float(v) for v in mn),
            "bbox_max": tuple(float(v) for v in mx),
        })
        registered += 1
    return registered

def get_or_build_aggregate_part(part):
    if not isinstance(part, dict):
        return part
    obj = part.get("obj")
    if obj is not None:
        return obj
    obj = build_aggregate_group_part_object(
        part["stem"],
        int(part["sector_index"]),
        int(part["parent_res_id"]),
        int(part["group_index"]),
        part["group"],
        part["material_list"],
        part["material_by_res_index"],
    )
    if obj is None:
        return None
    if bool(part.get("use_origin_bake", False)):
        try:
            ox, oy, oz = part.get("origin", (0.0, 0.0, 0.0))
            for vertex in obj.data.vertices:
                vertex.co.x += float(ox)
                vertex.co.y += float(oy)
                vertex.co.z += float(oz)
            obj.data.update()
            obj["blds_aggregate_origin_baked"] = True
            obj["blds_aggregate_origin"] = f"{float(ox):.6f},{float(oy):.6f},{float(oz):.6f}"
        except Exception:
            pass
    obj["blds_bbox_min"] = part.get("bbox_min", (0.0, 0.0, 0.0))
    obj["blds_bbox_max"] = part.get("bbox_max", (0.0, 0.0, 0.0))
    obj["blds_local_radius"] = float(part.get("radius", 0.0))
    part["obj"] = obj
    return obj

def lookup_aggregate_piece_base(detail, sector_index: int):
    if not ENABLE_AGGREGATE_PIECE_FALLBACK:
        return None, None
    parts = AGGREGATE_GROUP_PARTS_BY_SECTOR.get(int(sector_index), [])
    if not parts:
        return None, None

    sx, sy, sz, sr = detail_sphere_center_radius(detail)
    best_part = None
    best_score = None
    best_dist = None
    best_radius = None
    best_mode = "raw"

    for part in parts:
        if isinstance(part, dict):
            cx, cy, cz = part.get("center", (0.0, 0.0, 0.0))
            cr = float(part.get("radius", 0.0))
            ox, oy, oz = part.get("origin", (0.0, 0.0, 0.0))
            candidate_centers = (
                ("raw", float(cx), float(cy), float(cz)),
                ("origin", float(cx) + float(ox), float(cy) + float(oy), float(cz) + float(oz)),
            )
        else:
            cx, cy, cz, cr = object_bbox_center_radius(part)
            candidate_centers = (("raw", float(cx), float(cy), float(cz)),)

        for mode, tx, ty, tz in candidate_centers:
            dx = float(tx) - sx
            dy = float(ty) - sy
            dz = float(tz) - sz
            dist = (dx * dx + dy * dy + dz * dz) ** 0.5
            radius_pad = max(AGGREGATE_PIECE_MIN_ACCEPT_DISTANCE, sr + cr + AGGREGATE_PIECE_MAX_DISTANCE_PAD)
            if dist > radius_pad:
                continue
            radius_score = abs(cr - sr) * 0.20
            # Prefer an origin-baked match over a raw local match if they tie.  This is the
            # missing IPL path for VCS beach: rows such as RES=1828 / IPL=1222..1241 live
            # as pieces inside the sector aggregate, whose group centers need the sector
            # origin before comparing to the placement sphere.
            mode_bonus = -2.0 if mode == "origin" else 0.0
            score = dist + radius_score + mode_bonus
            if best_score is None or score < best_score:
                best_score = score
                best_part = part
                best_dist = dist
                best_radius = cr
                best_mode = mode

    if best_part is None:
        return None, None

    if isinstance(best_part, dict):
        best_part["use_origin_bake"] = (best_mode == "origin")
        best_part["last_match_mode"] = str(best_mode)
    obj = get_or_build_aggregate_part(best_part)
    if obj is None:
        return None, None
    try:
        obj["blds_aggregate_match_mode"] = str(best_mode)
    except Exception:
        pass
    return obj, (best_dist, best_radius)


def cluster_sorted_ids_for_submodels(values, gap_limit=128):
    ids = sorted(set(int(v) for v in values))
    clusters = []
    current = []
    last = None
    for rid in ids:
        if last is None or rid - last <= int(gap_limit):
            current.append(rid)
        else:
            if current:
                clusters.append(current)
            current = [rid]
        last = rid
    if current:
        clusters.append(current)
    return clusters

def _register_global_wrld_submodel_part(rid: int, part: dict, group_count: int):
    if not ENABLE_GLOBAL_WRLD_SUBMODEL_ID_RECOVERY:
        return
    try:
        rid = int(rid)
    except Exception:
        return
    if rid < 0 or not isinstance(part, dict):
        return
    prev = WRLD_SUBMODEL_GROUP_GLOBAL_LOOKUP.get(rid)
    def _score(p):
        try:
            gc = int(p.get("submodel_parent_group_count", group_count))
        except Exception:
            gc = int(group_count)
        try:
            verts = len((p.get("group") or {}).get("faces", [])) if isinstance(p.get("group"), dict) else 0
        except Exception:
            verts = 0
        return (gc, verts)
    if prev is None or _score(part) > _score(prev):
        WRLD_SUBMODEL_GROUP_GLOBAL_LOOKUP[rid] = part

def is_light_placement_pass(pass_name) -> bool:
    try:
        p = str(pass_name or "").strip().upper()
    except Exception:
        p = ""
    return p == "LIGHTS" or p == "LIGHT" or p.startswith("LIGHT_")

def infer_wrld_submodel_group_lookup(details, has_direct_exact_resource):
    WRLD_SUBMODEL_GROUP_LOOKUP.clear()
    WRLD_SUBMODEL_GROUP_GLOBAL_LOOKUP.clear()
    WRLD_SUBMODEL_GROUP_INFER_ROWS.clear()
    if not ENABLE_WRLD_SUBMODEL_GROUP_ID_RECOVERY:
        return 0

    from collections import Counter
    missing_by_sector = {}
    for detail in details:
        try:
            res_id = int(detail[0])
            sector_index = int(detail[15]) if len(detail) > 15 else -1
            row_index = int(detail[19]) if len(detail) > 19 else -1
            pass_name = str(detail[14]) if len(detail) > 14 else "UNKNOWN"
        except Exception:
            continue
        if SKIP_LIGHTS_PASS_IPL_MESH_PLACEMENTS and is_light_placement_pass(pass_name):
            continue
        if has_direct_exact_resource(sector_index, row_index, res_id):
            continue
        missing_by_sector.setdefault(int(sector_index), Counter())[int(res_id)] += 1

    mapped = 0
    for sector_index, id_counts in sorted(missing_by_sector.items()):
        parts = AGGREGATE_GROUP_PARTS_BY_SECTOR.get(int(sector_index), [])
        if not parts:
            continue
        by_parent = {}
        for part in parts:
            if not isinstance(part, dict):
                continue
            parent_res = int(part.get("parent_res_id", -1))
            if parent_res < 0:
                continue
            by_parent.setdefault(parent_res, []).append(part)
        if not by_parent:
            continue
        parent_items = []
        for parent_res, parent_parts in by_parent.items():
            parent_parts.sort(key=lambda p: int(p.get("group_index", -1)))
            group_count = len(parent_parts)
            if group_count < 2:
                continue
            parent_items.append((parent_res, parent_parts, group_count))
        if not parent_items:
            continue

        # V29: recover in two guarded stages.
        # Stage 1 is the older V23 contiguous-cluster resolver. It is safer for
        # big real WRLD aggregate parents such as the 2786.. range because it
        # prefers broad aggregate group tables and does not let a sparse shortcut
        # overwrite a proven contiguous mapping.
        missing_ids = set(int(v) for v in id_counts.keys())
        used_parents = set()
        clusters = cluster_sorted_ids_for_submodels(missing_ids, gap_limit=128)
        for cluster in sorted(clusters, key=lambda c: (-(c[-1] - c[0] + 1), -len(c), c[0])):
            cluster = [int(v) for v in cluster if int(v) in missing_ids]
            if not cluster:
                continue
            start = int(cluster[0])
            span = int(cluster[-1] - cluster[0] + 1)
            best = None
            best_score = None
            for parent_res, parent_parts, group_count in parent_items:
                if int(parent_res) in used_parents:
                    continue
                if int(group_count) < int(span):
                    continue
                covered = [rid for rid in cluster if start <= rid < start + group_count]
                if not covered:
                    continue
                covered_rows = sum(int(id_counts.get(rid, 0)) for rid in covered)
                # prefer broad aggregate resources for converter-style exploded WRLD groups.
                score = (len(covered) * 1000000) + (covered_rows * 10000) + (min(int(group_count), 4096) * 100) - abs(int(group_count) - int(span))
                if best_score is None or score > best_score:
                    best_score = score
                    best = (parent_res, parent_parts, group_count, covered, covered_rows)
            if best is None:
                continue
            parent_res, parent_parts, group_count, covered, covered_rows = best
            used_parents.add(int(parent_res))
            for rid in covered:
                group_index = int(rid) - int(start)
                if 0 <= group_index < len(parent_parts):
                    part = parent_parts[group_index]
                    # Do not let a later sparse pass replace this exact contiguous mapping.
                    part["blds_submodel_id_recovery"] = True
                    part["blds_submodel_sparse_range_recovery"] = False
                    part["blds_submodel_contiguous_range_recovery"] = True
                    part["submodel_res_id"] = int(rid)
                    part["submodel_range_start"] = int(start)
                    part["submodel_parent_group_count"] = int(group_count)
                    WRLD_SUBMODEL_GROUP_LOOKUP[(int(sector_index), int(rid))] = part
                    _register_global_wrld_submodel_part(int(rid), part, int(group_count))
                    mapped += 1
            missing_ids.difference_update(set(int(v) for v in covered))
            WRLD_SUBMODEL_GROUP_INFER_ROWS.append({
                "sector_index": int(sector_index),
                "range_start": int(start),
                "range_end": int(start + group_count - 1),
                "parent_res_id": int(parent_res),
                "group_count": int(group_count),
                "covered_count": int(len(covered)),
                "covered_rows": int(covered_rows),
                "covered_ids": " ".join(str(v) for v in sorted(covered)[:96]),
                "mode": "contiguous-sector-range",
            })

        # Stage 2: guarded sparse resolver for the ids left after Stage 1.
        # This is intentionally narrower than V26/V27: it cannot overwrite the
        # safe contiguous mappings and it uses unused parents only.
        unused_ids = set(int(v) for v in missing_ids)
        used_parent_keys = set(int(v) for v in used_parents)
        while unused_ids:
            best = None
            best_score = None
            for parent_res, parent_parts, group_count in parent_items:
                parent_key = int(parent_res)
                if parent_key in used_parent_keys:
                    continue
                candidate_starts = set()
                for rid in unused_ids:
                    for g in range(int(group_count)):
                        candidate_starts.add(int(rid) - int(g))
                for range_start in candidate_starts:
                    covered = [rid for rid in unused_ids if int(range_start) <= int(rid) < int(range_start) + int(group_count)]
                    if not covered:
                        continue
                    covered_rows = sum(int(id_counts.get(rid, 0)) for rid in covered)
                    if len(covered) < 2 and covered_rows < 4:
                        continue
                    span = max(covered) - min(covered) + 1
                    density = len(covered) / max(1, span)
                    # Keep sparse recovery useful but less aggressive than V26.
                    # Require either multiple unique ids or meaningful duplicate placement rows.
                    if len(covered) < 2 and covered_rows < 8:
                        continue
                    score = (covered_rows * 1000000) + (len(covered) * 25000) + int(density * 10000) - abs(int(group_count) - int(span))
                    if best_score is None or score > best_score:
                        best_score = score
                        best = (parent_res, parent_parts, group_count, int(range_start), covered, covered_rows, score)
            if best is None:
                break
            parent_res, parent_parts, group_count, range_start, covered, covered_rows, score = best
            used_parent_keys.add(int(parent_res))
            for rid in covered:
                group_index = int(rid) - int(range_start)
                if 0 <= group_index < len(parent_parts):
                    part = parent_parts[group_index]
                    # Never overwrite a Stage-1 contiguous mapping.
                    if (int(sector_index), int(rid)) in WRLD_SUBMODEL_GROUP_LOOKUP:
                        continue
                    part["blds_submodel_id_recovery"] = True
                    part["blds_submodel_sparse_range_recovery"] = True
                    part["blds_submodel_contiguous_range_recovery"] = False
                    part["submodel_res_id"] = int(rid)
                    part["submodel_range_start"] = int(range_start)
                    part["submodel_parent_group_count"] = int(group_count)
                    WRLD_SUBMODEL_GROUP_LOOKUP[(int(sector_index), int(rid))] = part
                    _register_global_wrld_submodel_part(int(rid), part, int(group_count))
                    mapped += 1
            unused_ids.difference_update(set(int(v) for v in covered))
            WRLD_SUBMODEL_GROUP_INFER_ROWS.append({
                "sector_index": int(sector_index),
                "range_start": int(range_start),
                "range_end": int(range_start + group_count - 1),
                "parent_res_id": int(parent_res),
                "group_count": int(group_count),
                "covered_count": int(len(covered)),
                "covered_rows": int(covered_rows),
                "covered_ids": " ".join(str(v) for v in sorted(covered)[:96]),
                "mode": "guarded-sparse-sector-range",
            })
    return mapped

def get_wrld_submodel_part_descriptor_for_res_id(sector_index: int, res_id: int):
    part = WRLD_SUBMODEL_GROUP_LOOKUP.get((int(sector_index), int(res_id)))
    global_fallback = False
    if part is None and ENABLE_GLOBAL_WRLD_SUBMODEL_ID_RECOVERY:
        part = WRLD_SUBMODEL_GROUP_GLOBAL_LOOKUP.get(int(res_id))
        global_fallback = part is not None
    return part, global_fallback


def _proof_format_vec(vec):
    try:
        return ",".join(f"{float(v):.6f}" for v in vec)
    except Exception:
        return ""

def _proof_stats_from_vertices_faces(vertices, faces, prefix: str):
    out = {
        f"{prefix}_verts": int(len(vertices) if vertices is not None else 0),
        f"{prefix}_faces": int(len(faces) if faces is not None else 0),
        f"{prefix}_bbox_min": "",
        f"{prefix}_bbox_max": "",
        f"{prefix}_center": "",
        f"{prefix}_radius": 0.0,
        f"{prefix}_diag": 0.0,
        f"{prefix}_mesh_hash": "",
    }
    if not vertices:
        return out
    try:
        pts = [(float(v[0]), float(v[1]), float(v[2])) for v in vertices]
        xs = [v[0] for v in pts]
        ys = [v[1] for v in pts]
        zs = [v[2] for v in pts]
        mn = (min(xs), min(ys), min(zs))
        mx = (max(xs), max(ys), max(zs))
        center = ((mn[0] + mx[0]) * 0.5, (mn[1] + mx[1]) * 0.5, (mn[2] + mx[2]) * 0.5)
        radius = 0.0
        for x, y, z in pts:
            dx = x - center[0]
            dy = y - center[1]
            dz = z - center[2]
            radius = max(radius, (dx * dx + dy * dy + dz * dz) ** 0.5)
        diag = ((mx[0] - mn[0]) ** 2 + (mx[1] - mn[1]) ** 2 + (mx[2] - mn[2]) ** 2) ** 0.5
        h = hashlib.sha1()
        # Quantized vertex cloud + face count: stable enough to prove large
        # mismatch without requiring identical source ordering.
        h.update(f"verts={len(pts)};faces={len(faces or [])};".encode("ascii"))
        for x, y, z in sorted((round(x, 4), round(y, 4), round(z, 4)) for x, y, z in pts):
            h.update(f"{x:.4f},{y:.4f},{z:.4f};".encode("ascii"))
        out[f"{prefix}_bbox_min"] = _proof_format_vec(mn)
        out[f"{prefix}_bbox_max"] = _proof_format_vec(mx)
        out[f"{prefix}_center"] = _proof_format_vec(center)
        out[f"{prefix}_radius"] = float(radius)
        out[f"{prefix}_diag"] = float(diag)
        out[f"{prefix}_mesh_hash"] = h.hexdigest()[:16]
    except Exception:
        pass
    return out

def proof_stats_for_mesh_object(obj, prefix: str):
    try:
        mesh = getattr(obj, "data", None)
        if mesh is None:
            return _proof_stats_from_vertices_faces([], [], prefix)
        verts = [(float(v.co.x), float(v.co.y), float(v.co.z)) for v in getattr(mesh, "vertices", [])]
        faces = [tuple(int(i) for i in getattr(poly, "vertices", [])) for poly in getattr(mesh, "polygons", [])]
        return _proof_stats_from_vertices_faces(verts, faces, prefix)
    except Exception:
        return _proof_stats_from_vertices_faces([], [], prefix)

def proof_stats_for_wrld_submodel_part(part, prefix: str = "lvz"):
    verts = []
    faces = []
    if not isinstance(part, dict):
        return _proof_stats_from_vertices_faces([], [], prefix)
    group = part.get("group")
    try:
        for strip in getattr(group, "strips", []) or []:
            count = min(
                len(getattr(strip, "verts", []) or []),
                len(getattr(strip, "uvs", []) or []),
                int(getattr(strip, "count", 0) or 0),
            )
            if count < 3:
                continue
            base = len(verts)
            for x, y, z in (getattr(strip, "verts", []) or [])[:count]:
                verts.append((float(x), float(y), float(z)))
            for i in range(count - 2):
                if i & 1:
                    faces.append((base + i + 1, base + i, base + i + 2))
                else:
                    faces.append((base + i, base + i + 1, base + i + 2))
    except Exception:
        pass
    return _proof_stats_from_vertices_faces(verts, faces, prefix)

def proof_verdict_for_reference_vs_lvz(ref_stats, lvz_stats):
    try:
        rv = int(ref_stats.get("reference_verts", 0))
        rf = int(ref_stats.get("reference_faces", 0))
        lv = int(lvz_stats.get("lvz_verts", 0))
        lf = int(lvz_stats.get("lvz_faces", 0))
        found = bool(lvz_stats.get("lvz_candidate_found", False))
        if not found:
            return "PROVEN_NO_LVZ_CANDIDATE", "no LVZ/IMG submodel candidate resolved for this Beachx id"
        if lv <= 0 or lf <= 0:
            return "PROVEN_LVZ_EMPTY_GEOMETRY", f"LVZ candidate has {lv} verts and {lf} faces"
        if rv != lv or rf != lf:
            return "PROVEN_COUNT_MISMATCH", f"reference={rv}v/{rf}f LVZ={lv}v/{lf}f"
        rh = str(ref_stats.get("reference_mesh_hash", ""))
        lh = str(lvz_stats.get("lvz_mesh_hash", ""))
        rr = float(ref_stats.get("reference_radius", 0.0))
        lr = float(lvz_stats.get("lvz_radius", 0.0))
        rd = float(ref_stats.get("reference_diag", 0.0))
        ld = float(lvz_stats.get("lvz_diag", 0.0))
        radius_ratio = (rr / lr) if lr else -1.0
        diag_ratio = (rd / ld) if ld else -1.0
        if rh and lh and rh == lh:
            return "PROVEN_EXACT_QUANTIZED_HASH_MATCH", "counts and quantized vertex-cloud hash match"
        if radius_ratio > 0 and (radius_ratio < 0.75 or radius_ratio > 1.33):
            return "PROVEN_BBOX_RADIUS_MISMATCH", f"counts match but radius ratio reference/LVZ={radius_ratio:.6f}"
        if diag_ratio > 0 and (diag_ratio < 0.75 or diag_ratio > 1.33):
            return "PROVEN_BBOX_DIAG_MISMATCH", f"counts match but bbox diagonal ratio reference/LVZ={diag_ratio:.6f}"
        if rh and lh and rh != lh:
            return "PROVEN_HASH_MISMATCH", "counts close/match but quantized vertex-cloud hash differs"
        return "PROOF_INCONCLUSIVE_COUNTS_CLOSE", "counts close but no stronger proof available"
    except Exception as exc:
        return "PROOF_FAILED", str(exc)

def stats_for_wrld_submodel_part_descriptor(part):
    out = {
        "lvz_candidate_found": False,
        "lvz_parent_res_id": -1,
        "lvz_group_index": -1,
        "lvz_range_start": -1,
        "lvz_group_count": -1,
        "lvz_global_fallback": False,
        "lvz_sparse_range": False,
        "lvz_verts": 0,
        "lvz_faces": 0,
        "lvz_strips": 0,
        "lvz_material_res_ids": "",
        "lvz_bbox_min": "",
        "lvz_bbox_max": "",
        "lvz_radius": 0.0,
    }
    if not isinstance(part, dict):
        return out
    out["lvz_candidate_found"] = True
    out["lvz_parent_res_id"] = int(part.get("parent_res_id", -1))
    out["lvz_group_index"] = int(part.get("group_index", -1))
    out["lvz_range_start"] = int(part.get("submodel_range_start", -1))
    out["lvz_group_count"] = int(part.get("submodel_parent_group_count", -1))
    out["lvz_sparse_range"] = bool(part.get("blds_submodel_sparse_range_recovery", False))
    try:
        out["lvz_bbox_min"] = ",".join(f"{float(v):.6f}" for v in part.get("bbox_min", ()))
        out["lvz_bbox_max"] = ",".join(f"{float(v):.6f}" for v in part.get("bbox_max", ()))
        out["lvz_radius"] = float(part.get("radius", 0.0))
    except Exception:
        pass
    group = part.get("group")
    mats = []
    verts = 0
    faces = 0
    strips = 0
    try:
        for strip in getattr(group, "strips", []) or []:
            count = min(len(getattr(strip, "verts", []) or []), len(getattr(strip, "uvs", []) or []), int(getattr(strip, "count", 0)))
            if count < 3:
                continue
            strips += 1
            verts += int(count)
            faces += max(0, int(count) - 2)
            try:
                mats.append(int(getattr(strip, "material_res_index", -1)))
            except Exception:
                pass
    except Exception:
        pass
    out["lvz_verts"] = int(verts)
    out["lvz_faces"] = int(faces)
    out["lvz_strips"] = int(strips)
    out["lvz_material_res_ids"] = " ".join(str(v) for v in sorted(set(mats)) if int(v) >= 0)
    try:
        out.update(proof_stats_for_wrld_submodel_part(part, "lvz"))
    except Exception:
        pass
    return out

def lookup_wrld_submodel_group_by_res_id(sector_index: int, res_id: int):
    if not ENABLE_WRLD_SUBMODEL_GROUP_ID_RECOVERY:
        return None, None
    part = WRLD_SUBMODEL_GROUP_LOOKUP.get((int(sector_index), int(res_id)))
    global_fallback = False
    if part is None and ENABLE_GLOBAL_WRLD_SUBMODEL_ID_RECOVERY:
        part = WRLD_SUBMODEL_GROUP_GLOBAL_LOOKUP.get(int(res_id))
        global_fallback = part is not None
    if part is None:
        return None, None
    obj = get_or_build_aggregate_part(part)
    if obj is None:
        return None, None
    try:
        obj["blds_kind"] = "IMG_WRLD_SUBMODEL_GROUP"
        obj["blds_submodel_id_recovery"] = True
        obj["blds_submodel_global_fallback"] = bool(global_fallback)
        obj["blds_res_index"] = int(res_id)
        obj["blds_parent_res_index"] = int(part.get("parent_res_id", -1))
        obj["blds_group_index"] = int(part.get("group_index", -1))
        obj["blds_submodel_range_start"] = int(part.get("submodel_range_start", -1))
    except Exception:
        pass
    info = {
        "parent_res_id": int(part.get("parent_res_id", -1)),
        "group_index": int(part.get("group_index", -1)),
        "range_start": int(part.get("submodel_range_start", -1)),
        "group_count": int(part.get("submodel_parent_group_count", -1)),
        "global_fallback": bool(global_fallback),
        "sparse_range": bool(part.get("blds_submodel_sparse_range_recovery", False)),
    }
    return obj, info


def lookup_verified_render_pair_alias_base(
    ipl_id,
    res_id,
    sector_index,
    row_index,
    overlay_by_sector_res,
    nested_overlay_by_res,
    row_overlay_by_res,
    built_by_res,
    extra_by_res,
    overlay_by_res,
    ipl_overlay_by_sector_res,
    ipl_nested_overlay_by_res,
    ipl_row_overlay_by_res,
    ipl_extra_by_res,
    ipl_overlay_by_res,
):
    if not ENABLE_FINAL_VERIFIED_RENDER_PAIR_ALIASES:
        return None, None, None
    try:
        key = (int(ipl_id), int(res_id))
    except Exception:
        return None, None, None
    alias_id = FINAL_VERIFIED_RENDER_PAIR_ALIAS.get(key)
    if alias_id is None:
        return None, None, None
    alias_id = int(alias_id)
    sector_index = int(sector_index)
    row_index = int(row_index)
    checks = []
    checks.append(("sector-render-pair", overlay_by_sector_res.get((sector_index, alias_id))))
    if row_index >= 0:
        checks.append(("nested-render-pair", nested_overlay_by_res.get((row_index, alias_id))))
        checks.append(("row-render-pair", row_overlay_by_res.get((row_index, alias_id))))
    checks.append(("lvz-render-pair", built_by_res.get(alias_id)))
    checks.append(("area-render-pair", extra_by_res.get(alias_id)))
    checks.append(("global-render-pair", overlay_by_res.get(alias_id)))
    checks.append(("ipl-sector-render-pair", ipl_overlay_by_sector_res.get((sector_index, alias_id))))
    if row_index >= 0:
        checks.append(("ipl-nested-render-pair", ipl_nested_overlay_by_res.get((row_index, alias_id))))
        checks.append(("ipl-row-render-pair", ipl_row_overlay_by_res.get((row_index, alias_id))))
    checks.append(("ipl-area-render-pair", ipl_extra_by_res.get(alias_id)))
    checks.append(("ipl-global-render-pair", ipl_overlay_by_res.get(alias_id)))
    for source, obj in checks:
        if obj is not None:
            return obj, alias_id, source
    return None, alias_id, "alias-target-not-found"




def get_or_create_missing_lvz_material(texture_id: int):
    name = f"lvz_texres_{int(texture_id)}_missing_image"
    material = bpy.data.materials.get(name)
    if material is not None:
        return material
    material = bpy.data.materials.new(name)
    material["blds_kind"] = "TEX_PLACEHOLDER"
    material["blds_texture_res_index"] = int(texture_id)
    material["blds_missing_texture_image"] = True
    seed = (int(texture_id) * 1103515245 + 12345) & 0xFFFFFFFF
    r = 0.25 + (((seed >> 0) & 0xFF) / 255.0) * 0.55
    g = 0.25 + (((seed >> 8) & 0xFF) / 255.0) * 0.55
    b = 0.25 + (((seed >> 16) & 0xFF) / 255.0) * 0.55
    material.diffuse_color = (r, g, b, 1.0)
    return material

def add_material_slots(obj, material_by_res_index: Dict[int, bpy.types.Material], material_list: LVZ.MDLMaterialList, face_ranges):
    resid_to_slot: Dict[int, int] = {}
    slots_added = 0
    if material_list.materials:
        for material_record in material_list.materials:
            texture_id = int(material_record.texture_id)
            material = material_by_res_index.get(texture_id)
            if material is None:
                material = get_or_create_missing_lvz_material(texture_id)
            existing_slot = None
            for slot_index, existing_material in enumerate(obj.data.materials):
                if existing_material and existing_material.name == material.name:
                    existing_slot = slot_index
                    break
            if existing_slot is None:
                obj.data.materials.append(material)
                existing_slot = len(obj.data.materials) - 1
                slots_added += 1
            resid_to_slot[texture_id] = existing_slot

    if face_ranges:
        polygons = obj.data.polygons
        for poly_start, poly_count, mat_resid in face_ranges:
            if mat_resid is None or mat_resid < 0:
                continue
            slot = resid_to_slot.get(int(mat_resid))
            if slot is None:
                continue
            for poly_index in range(poly_start, poly_start + poly_count):
                if 0 <= poly_index < len(polygons):
                    polygons[poly_index].material_index = slot
    return slots_added

def img_chunk_end(img_bytes: bytes, ordered_conts: List[int], cont: int) -> int:
    img_len = len(img_bytes)
    end = img_len
    try:
        index = ordered_conts.index(cont)
        if index + 1 < len(ordered_conts):
            end = min(end, int(ordered_conts[index + 1]))
    except ValueError:
        pass
    if 0 <= cont + 4 <= img_len:
        declared = LVZ.read_u32(img_bytes, cont)
        if 0x20 <= declared <= 0x04000000:
            end = min(end, cont + declared)
    return max(cont, min(end, img_len))

def looks_like_img_mdl_payload(img_bytes: bytes, base: int, end: int) -> bool:
    if base < 0 or base + 4 > end:
        return False
    count = LVZ.read_u16(img_bytes, base + 0)
    size_bytes = LVZ.read_u16(img_bytes, base + 2)
    if count <= 0 or count > 256:
        return False
    if size_bytes < count * 22 or size_bytes > 0x4000:
        return False
    if base + 4 + size_bytes > end:
        return False

    for stream_guess in (base + 4 + (count * 22), base + 4 + size_bytes):
        cursor = stream_guess
        while cursor < end and img_bytes[cursor] == 0xAA and cursor - base < 0x1000:
            cursor += 1
        cursor = LVZ.align_down4(cursor)
        if img_bytes.find(UNPACK_BYTES, max(base, cursor - 0x10), min(end, cursor + 0x80)) >= 0:
            return True
    return False

def find_img_mdl_payload_start(img_bytes: bytes, cont: int, end: int) -> Optional[int]:
    scan_start = cont + 0x20
    scan_end = min(end, cont + IMG_MDL_SCAN_LIMIT)
    for base in range(LVZ.align_up4(scan_start), LVZ.align_down4(scan_end), 4):
        if looks_like_img_mdl_payload(img_bytes, base, end):
            return base
    return None

def collect_img_mdl_candidates(img_reader: LVZ.read_img) -> List[Dict[str, int]]:
    records = img_reader.find_top_level_container_records_from_lvz()
    img_bytes = img_reader.img_bytes
    ordered_conts = sorted(set(
        int(record["cont"]) for record in records
        if 0 <= int(record["cont"]) < len(img_bytes)
    ))

    candidates_by_cont: Dict[int, Dict[str, int]] = {}
    first_record_by_cont: Dict[int, Dict[str, int]] = {}
    for record in records:
        cont = int(record.get("cont", -1))
        if 0 <= cont < len(img_bytes) and cont not in first_record_by_cont:
            first_record_by_cont[cont] = record

    for cont in ordered_conts:
        end = img_chunk_end(img_bytes, ordered_conts, cont)
        base = find_img_mdl_payload_start(img_bytes, cont, end)
        if base is None:
            continue
        record = first_record_by_cont.get(cont, {})
        candidates_by_cont[cont] = {
            "cont": int(cont),
            "payload": int(base),
            "end": int(end),
            "group_type": int(record.get("group_type", 0)),
            "group_index": int(record.get("group_index", -1)),
            "child_index": int(record.get("child_index", -1)),
            "lvz_addr": int(record.get("lvz_addr", 0)),
            "declared_total": int(record.get("total", 0)),
        }
    return [candidates_by_cont[key] for key in sorted(candidates_by_cont)]

def build_lvz_resource_mdl_objects(lvz_reader: LVZ.read_lvz, rows: List[Dict], progress_callback=None) -> Dict[int, bpy.types.Object]:
    mdl_rows = [row for row in rows if row.get("kind") == "MDL"]
    built_by_res: Dict[int, bpy.types.Object] = {}
    if not mdl_rows:
        LVZ.dbg("— LVZ Resource MDLs — none found")
        return built_by_res

    LVZ.dbg("— LVZ Resource MDLs —")
    total_mdl_rows = len(mdl_rows)
    for mdl_debug_i, row in enumerate(mdl_rows):
        if progress_callback is not None and (mdl_debug_i % 8 == 0 or mdl_debug_i + 1 == total_mdl_rows):
            progress_callback(mdl_debug_i + 1, total_mdl_rows)
        res_index = int(row["index"])
        verbose_mdl = IMPORT_VERBOSE_MDL_DEBUG or mdl_debug_i < IMPORT_MDL_DEBUG_LIMIT
        res_addr = int(row["res_addr"])
        res_end = int(row.get("res_end", len(lvz_reader.decomp)) or len(lvz_reader.decomp))
        try:
            material_list = lvz_reader.parse_mdl_material_list(res_addr, max_end=res_end)
            if verbose_mdl:
                LVZ.dbg(
                    f"[mdl {res_index}] list: format={material_list.format_tag} row_len={material_list.row_len} "
                    f"count={material_list.count} size_bytes={material_list.size_bytes} "
                    f"bytes_read={material_list.bytes_read} aa_tail={len(material_list.aa_tail)} "
                    f"next=0x{material_list.next_off:08X} end=0x{res_end:08X}"
                )
                for material_index, material_record in enumerate(material_list.materials):
                    LVZ.dbg(
                        f"  mat[{material_index:02d}] texRES={material_record.texture_id} "
                        f"strip_size={material_record.tri_strip_size} cull={int(material_record.backface_cull)} "
                        f"us={material_record.u_scale:.4f} vs={material_record.v_scale:.4f} "
                        f"flags2=0x{material_record.flags2:04X} bbox={material_record.bbox6_i16}"
                    )
            elif mdl_debug_i == IMPORT_MDL_DEBUG_LIMIT:
                LVZ.dbg(f"[mdl] detailed LVZ MDL log capped after {IMPORT_MDL_DEBUG_LIMIT} objects")
            groups, after = lvz_reader.parse_mdl_geometry_after_list(material_list, max_end=res_end)
            if verbose_mdl:
                LVZ.dbg(f"[mdl {res_index}] batches={len(groups)} stream_end=0x{after:08X} bounded_end=0x{res_end:08X}")
            lvz_reader.assign_materials_by_strip_bytes(material_list, groups)
        except Exception as exc:
            LVZ.dbg(f"[mdl {res_index}] parse failed at 0x{res_addr:08X}: {exc}")
            continue

        obj, face_ranges = build_mesh_from_mdl_groups(lvz_reader.stem, res_index, groups)
        if obj is None:
            LVZ.dbg(f"[mdl {res_index}] no faces/verts, skipped object creation")
            continue
        slots_added = add_material_slots(obj, lvz_reader.material_by_res_index, material_list, face_ranges)

        # VCS Master WRLD Resource[] rows are 12 bytes. The third dword is a
        # resource/name identifier, not just padding. Converted IPL names like
        # beach3457 refer to that identifier, while the table slot can be a
        # completely different row number. Earlier builds keyed master MDLs only
        # by the row index, so rows whose visible id was beach#### were reported
        # missing even when the MDL existed in the master table under another
        # slot. Register both names, but never overwrite a true exact key.
        resource_id_field = row.get("resource_id_field", None)
        external_res_id = None
        try:
            if resource_id_field is not None:
                external_res_id = int(resource_id_field)
                if external_res_id < 0 or external_res_id == 0xFFFFFFFF:
                    external_res_id = None
        except Exception:
            external_res_id = None

        try:
            obj["blds_master_resource_table_index"] = int(res_index)
            if external_res_id is not None:
                obj["blds_master_resource_id_field"] = int(external_res_id)
        except Exception:
            pass

        built_by_res[res_index] = obj
        if external_res_id is not None and external_res_id != res_index:
            if external_res_id not in built_by_res:
                built_by_res[external_res_id] = obj
                try:
                    obj["blds_master_resource_alias_key"] = int(external_res_id)
                except Exception:
                    pass
                if verbose_mdl:
                    LVZ.dbg(
                        f"[mdl {res_index}] registered Master WRLD id alias beach{external_res_id} -> table row {res_index}"
                    )
            elif built_by_res.get(external_res_id) is not obj and verbose_mdl:
                LVZ.dbg(
                    f"[mdl {res_index}] skipped Master WRLD id alias beach{external_res_id}; exact key already has an object"
                )

        if verbose_mdl:
            if external_res_id is not None and external_res_id != res_index:
                LVZ.dbg(f"[mdl {res_index}] → created object '{obj.name}' as row={res_index} id=beach{external_res_id} (added {slots_added} material slots)")
            else:
                LVZ.dbg(f"[mdl {res_index}] → created object '{obj.name}' (added {slots_added} material slots)")

    unique_objects = len({id(obj) for obj in built_by_res.values()})
    alias_keys = max(0, len(built_by_res) - unique_objects)
    LVZ.dbg(f"[done] total LVZ resource MDL objects created: {unique_objects} (+{alias_keys} Master WRLD id aliases)")
    return built_by_res

def build_img_mdl_objects(stem: str, img_bytes: bytes, img_reader: LVZ.read_img, material_by_res_index: Dict[int, bpy.types.Material], source_lvz_path: str, img_name: Optional[str]) -> Dict[int, bpy.types.Object]:
    candidates = collect_img_mdl_candidates(img_reader)
    parser = LVZ.read_lvz(
        decomp_bytes=img_bytes,
        stem=stem,
        use_swizzle=False,
        debug_print=False,
    )
    parser.material_by_res_index = material_by_res_index

    built_by_cont: Dict[int, bpy.types.Object] = {}
    LVZ.dbg("— IMG MDL Containers —")
    LVZ.dbg(f"[img-mdl] payload candidates: {len(candidates)}")

    for import_index, candidate in enumerate(candidates[:IMG_MDL_MAX_IMPORT]):
        cont = int(candidate["cont"])
        payload = int(candidate["payload"])
        end = int(candidate["end"])
        try:
            material_list = parser.parse_mdl_material_list(payload, max_end=end)
            groups, after = parser.parse_mdl_geometry_after_list(material_list, max_end=end)
            parser.assign_materials_by_strip_bytes(material_list, groups)
        except Exception as exc:
            LVZ.dbg(f"[img-mdl 0x{cont:08X}] parse failed at payload=0x{payload:08X}: {exc}")
            continue

        obj, face_ranges = build_mesh_from_mdl_groups(stem, import_index, groups)
        if obj is None:
            LVZ.dbg(
                f"[img-mdl 0x{cont:08X}] no faces/verts payload=0x{payload:08X} "
                f"batches={len(groups)} end=0x{end:08X}"
            )
            continue

        slots_added = add_material_slots(obj, material_by_res_index, material_list, face_ranges)
        obj.name = f"{stem}_img_{import_index:04d}"
        obj.data.name = obj.name
        obj["blds_kind"] = "IMG_MDL"
        obj["blds_res_index"] = int(import_index)
        obj["blds_img_cont"] = cont
        obj["blds_img_payload"] = payload
        obj["blds_img_end"] = end
        obj["blds_img_group_type"] = int(candidate.get("group_type", 0))
        obj["blds_img_group_index"] = int(candidate.get("group_index", -1))
        obj["blds_img_child_index"] = int(candidate.get("child_index", -1))
        obj["blds_source_lvz_path"] = str(source_lvz_path)
        if img_name:
            obj["blds_source_img_path"] = str(Path(source_lvz_path).with_name(img_name))
        built_by_cont[cont] = obj
        LVZ.dbg(
            f"[img-mdl {import_index:04d}] cont=0x{cont:08X} payload=0x{payload:08X} "
            f"groups={len(groups)} verts={obj.get('blds_verts', 0)} faces={obj.get('blds_faces', 0)} "
            f"materials={slots_added}"
        )

    if len(candidates) > IMG_MDL_MAX_IMPORT:
        LVZ.dbg(f"[img-mdl] stopped at safety cap {IMG_MDL_MAX_IMPORT}; candidates={len(candidates)}")
    LVZ.dbg(f"[img-mdl] total IMG MDL objects created: {len(built_by_cont)}")
    return built_by_cont


def _probe_ps2_img_descriptor_for_continuation(img_bytes: bytes, off: int) -> Optional[dict]:
    """Validate one raw IMG material descriptor table and compute its exact VIF packet end."""
    try:
        n = len(img_bytes)
        off = int(off)
        if off < 0x40 or off + 8 > n or (off & 3) != 0:
            return None
        count16 = LVZ.read_u16(img_bytes, off + 0)
        size16 = LVZ.read_u16(img_bytes, off + 2)
        if not (0 < int(count16) <= 256 and 0 <= int(size16) <= 0x8000):
            return None
        layouts = []
        for tag, row_len in (("ps2_vcs", 24), ("ps2_lcs", 22)):
            try:
                expected = ((4 + (int(count16) * int(row_len)) + 15) & ~15) - 4
            except Exception:
                continue
            if int(size16) == int(expected):
                layouts.append((tag, int(row_len)))
        if not layouts:
            return None
        for tag, row_len in layouts:
            list_end = int(off) + 4 + int(size16)
            if list_end > n:
                continue
            stream = list_end
            pad = 0
            while stream < n and img_bytes[stream] == 0xAA and pad < 0x400:
                stream += 1
                pad += 1
            stream = (stream + 3) & ~3
            if stream + 4 > n:
                continue
            try:
                if LVZ.read_u32(img_bytes, stream) != LVZ.read_lvz.UNPACK:
                    continue
            except Exception:
                continue
            pos = int(off) + 4
            packet_total = 0
            tex_ids = []
            packets = []
            ok = True
            for _ in range(int(count16)):
                if pos + row_len > list_end:
                    ok = False
                    break
                if row_len == 24:
                    packet_raw = LVZ.read_u32(img_bytes, pos + 0)
                    packet_size = int(packet_raw) >> 1
                    tex_id = LVZ.read_u16(img_bytes, pos + 4)
                else:
                    tex_id = LVZ.read_u16(img_bytes, pos + 0)
                    packet_size = LVZ.read_u16(img_bytes, pos + 2) & 0x7FFF
                if packet_size <= 0 or packet_size > 0x40000:
                    ok = False
                    break
                packet_total += int(packet_size)
                packets.append(int(packet_size))
                tex_ids.append(int(tex_id) & 0xFFFF)
                pos += row_len
            if not ok or packet_total <= 0:
                continue
            packet_end = int(stream) + int(packet_total)
            if packet_end > n:
                continue
            return {
                "raw_off": int(off),
                "stream_start": int(stream),
                "packet_end": int(packet_end),
                "after": int(packet_end),
                "format_tag": str(tag),
                "row_len": int(row_len),
                "count": int(count16),
                "size16": int(size16),
                "packet_total": int(packet_total),
                "packet_sizes": packets,
                "tex_ids": set(tex_ids),
            }
    except Exception:
        return None
    return None


def scan_continues_in_img_descriptor_proofs(stem: str, img_bytes: bytes, lvz_reader: LVZ.read_lvz, wanted_res_ids, progress_callback=None) -> Dict[int, dict]:
    if not ENABLE_EMPTY_RESOURCE_CONTINUES_IN_IMG or not img_bytes:
        return {}
    try:
        wanted = {int(x) for x in (wanted_res_ids or set()) if int(x) >= 0}
    except Exception:
        wanted = set()
    if not wanted:
        return {}

    cache = CONTINUES_IN_IMG_PROOF_CACHE
    remaining = {res_id for res_id in wanted if res_id not in cache}
    if not remaining:
        return {res_id: cache[res_id] for res_id in wanted if res_id in cache}

    parser = LVZ.read_lvz(
        decomp_bytes=img_bytes,
        stem=stem,
        use_swizzle=bool(lvz_reader.use_swizzle),
        debug_print=False,
    )
    parser.material_by_res_index = lvz_reader.material_by_res_index

    probe_to_res: Dict[int, set] = {}
    for res_id in remaining:
        for delta in CONTINUES_IN_IMG_TEXTURE_ID_DELTAS:
            probe = int(res_id) + int(delta)
            if 0 <= probe <= 0xFFFF:
                probe_to_res.setdefault(int(probe), set()).add(int(res_id))

    best_by_res = {}
    n = len(img_bytes)
    stride = max(4, int(CONTINUES_IN_IMG_SCAN_STRIDE))
    off = 0
    scanned_descriptors = 0
    matched_descriptors = 0
    parser_failures = 0
    total_scan_steps = max(1, (max(0, n - 0x20) + stride - 1) // stride)
    scan_step = 0
    while off + 0x20 <= n:
        scan_step += 1
        if progress_callback is not None and (scan_step % 4096 == 0 or scan_step == total_scan_steps):
            progress_callback(scan_step, total_scan_steps)
        descriptor = _probe_ps2_img_descriptor_for_continuation(img_bytes, off)
        if descriptor is None:
            off += stride
            continue
        scanned_descriptors += 1
        tex_ids = set(int(x) for x in descriptor.get("tex_ids", set()))
        target_res_ids = set()
        for tex_id in tex_ids:
            target_res_ids.update(probe_to_res.get(int(tex_id), set()))
        if not target_res_ids:
            off += stride
            continue
        matched_descriptors += 1
        raw_off = int(descriptor["raw_off"])
        packet_end = int(descriptor["packet_end"])
        try:
            material_list = parser.parse_mdl_material_list(raw_off, max_end=packet_end)
            groups, after = parser.parse_mdl_geometry_after_list(material_list, max_end=packet_end)
            parser.assign_materials_by_strip_bytes(material_list, groups)
        except Exception:
            parser_failures += 1
            off += stride
            continue

        score = score_mdl_groups_for_preselect(groups)
        if score < 0.0:
            off += stride
            continue
        gv = 0
        gf = 0
        try:
            for group in groups:
                for strip in getattr(group, 'strips', []) or []:
                    verts = getattr(strip, 'verts', []) or []
                    uvs = getattr(strip, 'uvs', []) or []
                    try:
                        count = int(getattr(strip, 'count', len(verts)) or len(verts))
                    except Exception:
                        count = len(verts)
                    if uvs:
                        count = min(count, len(uvs))
                    gv += len(verts)
                    gf += max(0, count - 2)
        except Exception:
            pass
        if gv <= 0 or gf <= 0:
            off += stride
            continue

        for target in target_res_ids:
            tex_score_bonus = 0.0
            if int(target) + 1 in tex_ids:
                tex_score_bonus += 100000.0
            if int(target) in tex_ids:
                tex_score_bonus += 25000.0
            if tex_ids:
                nearest = min(abs(int(t) - int(target)) for t in tex_ids)
                tex_score_bonus += max(0.0, 1000.0 - float(nearest))
            final_score = float(score) + tex_score_bonus + float(gv) * 0.01 + float(gf) * 0.01 + float(descriptor.get("packet_total", 0)) * 0.001
            old = best_by_res.get(int(target))
            if old is None or final_score > float(old.get('final_score', -1.0)):
                best_by_res[int(target)] = {
                    'final_score': final_score,
                    'score': float(score),
                    'raw_off': int(raw_off),
                    'stream_start': int(descriptor.get('stream_start', -1)),
                    'after': int(after),
                    'packet_end': int(packet_end),
                    'packet_total': int(descriptor.get('packet_total', 0)),
                    'material_list': material_list,
                    'groups': groups,
                    'tex_ids': set(tex_ids),
                    'verts': int(gv),
                    'faces': int(gf),
                    'format_tag': str(descriptor.get('format_tag', '')),
                    'material_count': int(descriptor.get('count', 0)),
                }
        off += stride

    for res_id, proof in best_by_res.items():
        cache[int(res_id)] = proof
    found = {res_id: cache[res_id] for res_id in wanted if res_id in cache}
    if IMPORT_VERBOSE_RESOURCE_BUILD_LOGS:
        LVZ.dbg(
            f"[continues-img-scan] wanted={len(wanted)} scanned_descriptors={scanned_descriptors} "
            f"matched_descriptors={matched_descriptors} parser_failures={parser_failures} found={len(found)}"
        )
    return found


def build_empty_resource_continues_in_img_mdl_objects(stem: str, img_bytes: bytes, lvz_reader: LVZ.read_lvz, img_reader: LVZ.read_img, wanted_res_ids, source_lvz_path: str, img_name: Optional[str], progress_callback=None) -> Dict[Tuple[int, int], bpy.types.Object]:
    if not ENABLE_EMPTY_RESOURCE_CONTINUES_IN_IMG:
        return {}
    try:
        wanted = {int(x) for x in (wanted_res_ids or set()) if int(x) >= 0}
    except Exception:
        wanted = set()
    if not wanted:
        return {}

    proofs = scan_continues_in_img_descriptor_proofs(
        stem,
        img_bytes,
        lvz_reader,
        wanted,
        progress_callback=progress_callback,
    )
    if not proofs:
        LVZ.dbg(f"[continues-img] descriptor scan wanted={len(wanted)} created=0")
        return {}

    parser = LVZ.read_lvz(
        decomp_bytes=img_bytes,
        stem=stem,
        use_swizzle=bool(lvz_reader.use_swizzle),
        debug_print=False,
    )
    parser.material_by_res_index = lvz_reader.material_by_res_index

    out: Dict[Tuple[int, int], bpy.types.Object] = {}
    logged = 0
    sorted_proof_ids = sorted(proofs)
    total_proofs = len(sorted_proof_ids)
    for index, res_id in enumerate(sorted_proof_ids):
        if progress_callback is not None:
            progress_callback(index + 1, total_proofs)
        proof = proofs[int(res_id)]
        raw_off = int(proof.get('raw_off', -1))
        after = int(proof.get('after', -1))
        material_list = proof.get('material_list')
        groups = proof.get('groups') or []
        tex_ids = set(proof.get('tex_ids') or set())
        gv = int(proof.get('verts', 0))
        gf = int(proof.get('faces', 0))
        score = float(proof.get('score', 0.0))
        if material_list is None or not groups:
            continue
        obj, face_ranges = build_mesh_from_mdl_groups(f"{stem}_continued_img_res", int(res_id), groups)
        if obj is None:
            continue
        obj.name = f"{stem}{int(res_id)}"
        obj.data.name = obj.name
        slots_added = add_material_slots(obj, parser.material_by_res_index, material_list, face_ranges)
        obj["blds_kind"] = "IMG_CONTINUES_IN_IMG_MDL"
        obj["blds_res_index"] = int(res_id)
        obj["blds_img_continues_in_img"] = True
        obj["blds_img_continues_raw_off"] = int(raw_off)
        obj["blds_img_continues_after"] = int(after)
        obj["blds_img_continues_material_ids"] = ",".join(str(int(x)) for x in sorted(tex_ids))
        obj["blds_source_lvz_path"] = str(source_lvz_path)
        if img_name:
            obj["blds_source_img_path"] = str(Path(source_lvz_path).with_name(img_name))
        key = (-200000 - int(index), int(res_id))
        out[key] = obj
        if logged < int(CONTINUES_IN_IMG_MAX_LOG_ROWS):
            LVZ.dbg(
                f"[continues-img] RES={int(res_id)} reason=CONTINUES_IN_IMG "
                f"img={img_name or '<companion IMG>'} raw=0x{int(raw_off):08X} stream_end=0x{int(after):08X} "
                f"materials={','.join(str(int(x)) for x in sorted(tex_ids))} geom={int(gv)}v/{int(gf)}f "
                f"slots={int(slots_added)} score={float(score):.3f}"
            )
            logged += 1

    LVZ.dbg(f"[continues-img] descriptor scan wanted={len(wanted)} found={len(proofs)} created={len(out)}")
    return out

def build_sector_overlay_mdl_objects(stem: str, img_bytes: bytes, lvz_reader: LVZ.read_lvz, img_reader: LVZ.read_img, sector_records: List[Dict[str, int]], max_resource_id: int, source_lvz_path: str, img_name: Optional[str], needed_sector_res_keys=None, include_alt_12_layouts: bool = False, wanted_res_ids=None, collapse_by_res_id: bool = False, progress_callback=None) -> Dict[Tuple[int, int], bpy.types.Object]:
    parser = LVZ.read_lvz(
        decomp_bytes=img_bytes,
        stem=stem,
        use_swizzle=bool(lvz_reader.use_swizzle),
        debug_print=False,
    )
    parser.material_by_res_index = lvz_reader.material_by_res_index

    overlay_rows = img_reader.collect_sector_overlay_resources(
        sector_records,
        max_resource_id=max_resource_id,
        include_alt_12_layouts=include_alt_12_layouts,
        wanted_res_ids=wanted_res_ids,
        progress_callback=progress_callback,
    )
    if needed_sector_res_keys is not None:
        needed_sector_res_keys = set(needed_sector_res_keys)
        overlay_rows = [
            row for row in overlay_rows
            if (int(row.get("sector_index", -1)), int(row.get("res_id", -1))) in needed_sector_res_keys
        ]

    overlay_by_sector_res: Dict[Tuple[int, int], bpy.types.Object] = {}
    parsed = 0
    skipped_duplicate = 0
    skipped_non_geometry = 0
    aggregate_parts_created = 0
    preselected_by_key = {}
    preselect_input_rows = 0
    preselect_dropped_rows = 0

    if collapse_by_res_id:
        best_by_res = {}
        preselect_input_rows = len(overlay_rows)
        preselect_total = len(overlay_rows)
        for overlay_index, overlay in enumerate(overlay_rows):
            if progress_callback is not None and (
                overlay_index % 8 == 0 or overlay_index + 1 == preselect_total
            ):
                progress_callback(overlay_index + 1, max(1, preselect_total))
            try:
                res_id = int(overlay.get("res_id", -1))
                raw_off = int(overlay.get("raw_off", -1))
                sector_end = int(overlay.get("resource_end", overlay.get("sector_end", len(img_bytes))))
            except Exception:
                skipped_non_geometry += 1
                continue
            if res_id < 0 or raw_off < 0:
                skipped_non_geometry += 1
                continue
            try:
                material_list = parser.parse_mdl_material_list(raw_off, max_end=sector_end)
                groups, after = parser.parse_mdl_geometry_after_list(material_list, max_end=sector_end)
            except Exception:
                skipped_non_geometry += 1
                continue
            score = score_mdl_groups_for_preselect(groups)
            if score < 0.0:
                skipped_non_geometry += 1
                continue
            previous = best_by_res.get(res_id)
            if previous is None or score > previous[0]:
                best_by_res[res_id] = (score, overlay, material_list, groups)

        overlay_rows = []
        for score, overlay, material_list, groups in best_by_res.values():
            sector_index = int(overlay.get("sector_index", -1))
            res_id = int(overlay.get("res_id", -1))
            key = (sector_index, res_id)
            overlay_rows.append(overlay)
            preselected_by_key[key] = (material_list, groups)
        preselect_dropped_rows = max(0, preselect_input_rows - len(overlay_rows))

    LVZ.dbg("— IMG Sector Overlay Resource MDLs —")
    LVZ.dbg(f"[sector-mdl] overlay resource rows: {len(overlay_rows)}")
    if collapse_by_res_id:
        LVZ.dbg(f"[sector-mdl] fast preselect by RES: input={preselect_input_rows} kept={len(overlay_rows)} dropped={preselect_dropped_rows}")

    total_overlay_rows = len(overlay_rows)
    for overlay_index, overlay in enumerate(overlay_rows):
        if progress_callback is not None and (
            overlay_index % 8 == 0 or overlay_index + 1 == total_overlay_rows
        ):
            progress_callback(overlay_index + 1, max(1, total_overlay_rows))
        sector_index = int(overlay["sector_index"])
        res_id = int(overlay["res_id"])
        key = (sector_index, res_id)
        if key in overlay_by_sector_res:
            skipped_duplicate += 1
            continue

        raw_off = int(overlay["raw_off"])
        sector_end = int(overlay.get("resource_end", overlay["sector_end"]))
        try:
            got_preselected = preselected_by_key.get(key)
            if got_preselected is not None:
                material_list, groups = got_preselected
            else:
                material_list = parser.parse_mdl_material_list(raw_off, max_end=sector_end)
                groups, after = parser.parse_mdl_geometry_after_list(material_list, max_end=sector_end)
            parser.assign_materials_by_strip_bytes(material_list, groups)
        except Exception:
            skipped_non_geometry += 1
            continue

        obj, face_ranges = build_mesh_from_mdl_groups(f"{stem}_sec{sector_index:04d}_res", res_id, groups)
        if obj is None:
            skipped_non_geometry += 1
            continue

        obj.name = f"{stem}_sec{sector_index:04d}_res{res_id}"
        obj.data.name = obj.name
        slots_added = add_material_slots(obj, parser.material_by_res_index, material_list, face_ranges)
        aggregate_parts_created += register_aggregate_group_parts(
            stem,
            sector_index,
            res_id,
            groups,
            material_list,
            parser.material_by_res_index,
            origin=overlay.get("origin", (0.0, 0.0, 0.0)),
        )
        obj["blds_kind"] = "IMG_SECTOR_MDL"
        obj["blds_res_index"] = res_id
        obj["blds_img_sector_index"] = sector_index
        obj["blds_img_sector_x"] = int(overlay.get("sector_x", 0))
        obj["blds_img_sector_y"] = int(overlay.get("sector_y", 0))
        obj["blds_img_overlay_resource"] = True
        obj["blds_img_overlay_raw_off"] = raw_off
        obj["blds_img_overlay_raw_ptr"] = int(overlay.get("raw_ptr", 0))
        obj["blds_source_lvz_path"] = str(source_lvz_path)
        if img_name:
            obj["blds_source_img_path"] = str(Path(source_lvz_path).with_name(img_name))
        overlay_by_sector_res[key] = obj
        parsed += 1
        if IMPORT_VERBOSE_RESOURCE_BUILD_LOGS and parsed <= 64:
            LVZ.dbg(
                f"[sector-mdl] sector={sector_index} res={res_id} raw=0x{raw_off:08X} "
                f"format={material_list.format_tag} groups={len(groups)} materials={slots_added}"
            )

    LVZ.dbg(
        f"[sector-mdl] created={len(overlay_by_sector_res)} skipped_non_geometry={skipped_non_geometry} "
        f"skipped_duplicate={skipped_duplicate} aggregate_part_descriptors={aggregate_parts_created}"
    )
    return overlay_by_sector_res


def build_row_shared_mdl_objects(stem: str, img_bytes: bytes, lvz_reader: LVZ.read_lvz, img_reader: LVZ.read_img, sector_records: List[Dict[str, int]], max_resource_id: int, source_lvz_path: str, img_name: Optional[str], needed_row_res_keys=None, include_alt_12_layouts: bool = False, wanted_res_ids=None, progress_callback=None) -> Dict[Tuple[int, int], bpy.types.Object]:
    if not sector_records:
        return {}

    parser = LVZ.read_lvz(
        decomp_bytes=img_bytes,
        stem=stem,
        use_swizzle=bool(lvz_reader.use_swizzle),
        debug_print=False,
    )
    parser.material_by_res_index = lvz_reader.material_by_res_index

    # Scan every sector record, not only the first sector in each row.
    # Some VCS IMG rows use a resource that is row-shared, but the resource table
    # entry can live in any concrete sector within that row.  The old first-row
    # shortcut missed those tables and made the row-shared fallback return zero
    # useful bases for many beach/mainla placements.
    row_base_records = [
        record
        for record in sorted(sector_records, key=lambda item: (int(item.get("row_index", -1)), int(item.get("sector_index", -1))))
        if int(record.get("row_index", -1)) >= 0
    ]
    overlay_rows = img_reader.collect_sector_overlay_resources(row_base_records, max_resource_id=max_resource_id, include_alt_12_layouts=include_alt_12_layouts, wanted_res_ids=wanted_res_ids, progress_callback=progress_callback)
    if needed_row_res_keys is not None:
        needed_row_res_keys = set(needed_row_res_keys)
        overlay_rows = [row for row in overlay_rows if (int(row.get("row_index", -1)), int(row.get("res_id", -1))) in needed_row_res_keys]

    row_overlay_by_res: Dict[Tuple[int, int], bpy.types.Object] = {}
    parsed = 0
    skipped_duplicate = 0
    skipped_non_geometry = 0

    LVZ.dbg("— IMG Row Shared Resource MDLs —")
    LVZ.dbg(f"[row-mdl] row-base resource rows: {len(overlay_rows)}")

    total_overlay_rows = len(overlay_rows)
    for overlay_index, overlay in enumerate(overlay_rows):
        if progress_callback is not None and (overlay_index % 8 == 0 or overlay_index + 1 == total_overlay_rows):
            progress_callback(overlay_index + 1, total_overlay_rows)
        row_index = int(overlay.get("row_index", -1))
        res_id = int(overlay.get("res_id", -1))
        key = (row_index, res_id)
        if row_index < 0 or res_id < 0:
            skipped_non_geometry += 1
            continue
        if key in row_overlay_by_res:
            skipped_duplicate += 1
            continue

        raw_off = int(overlay.get("raw_off", -1))
        sector_end = int(overlay.get("resource_end", overlay.get("sector_end", len(img_bytes))))
        try:
            material_list = parser.parse_mdl_material_list(raw_off, max_end=sector_end)
            groups, after = parser.parse_mdl_geometry_after_list(material_list, max_end=sector_end)
            parser.assign_materials_by_strip_bytes(material_list, groups)
        except Exception:
            skipped_non_geometry += 1
            continue

        obj, face_ranges = build_mesh_from_mdl_groups(f"{stem}_row{row_index:03d}_res", res_id, groups)
        if obj is None:
            skipped_non_geometry += 1
            continue

        obj.name = f"{stem}_row{row_index:03d}_res{res_id}"
        obj.data.name = obj.name
        slots_added = add_material_slots(obj, parser.material_by_res_index, material_list, face_ranges)
        obj["blds_kind"] = "IMG_ROW_SHARED_MDL"
        obj["blds_res_index"] = res_id
        obj["blds_img_row_index"] = row_index
        obj["blds_img_row_base_sector_index"] = int(overlay.get("sector_index", -1))
        obj["blds_img_row_base_sector_x"] = int(overlay.get("sector_x", 0))
        obj["blds_img_row_base_sector_y"] = int(overlay.get("sector_y", 0))
        obj["blds_img_overlay_raw_off"] = raw_off
        obj["blds_img_overlay_raw_ptr"] = int(overlay.get("raw_ptr", 0))
        obj["blds_source_lvz_path"] = str(source_lvz_path)
        if img_name:
            obj["blds_source_img_path"] = str(Path(source_lvz_path).with_name(img_name))
        row_overlay_by_res[key] = obj
        parsed += 1
        if IMPORT_VERBOSE_RESOURCE_BUILD_LOGS and parsed <= 64:
            LVZ.dbg(
                f"[row-mdl] row={row_index} res={res_id} raw=0x{raw_off:08X} "
                f"format={material_list.format_tag} groups={len(groups)} materials={slots_added}"
            )

    LVZ.dbg(
        f"[row-mdl] created={len(row_overlay_by_res)} skipped_non_geometry={skipped_non_geometry} "
        f"skipped_duplicate={skipped_duplicate}"
    )
    return row_overlay_by_res

def build_nested_child_mdl_objects(stem: str, img_bytes: bytes, lvz_reader: LVZ.read_lvz, img_reader: LVZ.read_img, source_lvz_path: str, img_name: Optional[str], needed_row_res_keys=None, include_alt_12_layouts: bool = False, wanted_res_ids=None, progress_callback=None) -> Dict[Tuple[int, int], bpy.types.Object]:
    parser = LVZ.read_lvz(
        decomp_bytes=img_bytes,
        stem=stem,
        use_swizzle=bool(lvz_reader.use_swizzle),
        debug_print=False,
    )
    parser.material_by_res_index = lvz_reader.material_by_res_index

    needed_row_res_keys = set(needed_row_res_keys or [])
    nested_records = []
    seen_records = set()

    for index, candidate in enumerate(img_reader.find_nested_container_records_from_lvz()):
        cont = int(candidate.get("cont", -1))
        total = int(candidate.get("total", 0))
        if cont < 0 or cont >= len(img_bytes):
            continue
        if total < 0x20:
            continue

        end = min(len(img_bytes), cont + total - 0x20)
        if end <= cont + 8:
            continue

        row_index = int(candidate.get("group_index", -1))
        child_index = int(candidate.get("child_index", -1))
        key = (int(candidate.get("lvz_addr", -1)), cont, row_index, child_index)
        if key in seen_records:
            continue
        seen_records.add(key)

        nested_records.append({
            "sector_index": int(-200000 - len(nested_records)),
            "row_index": row_index,
            "sector_x": 0,
            "sector_y": 0,
            "header_addr": int(candidate.get("lvz_addr", -1)),
            "cont": cont,
            "file_size": total,
            "data_size": int(candidate.get("g0", 0)),
            "reloc_tab": int(candidate.get("g1", 0)),
            "num_relocs": int(candidate.get("gcnt", 0)),
            "end": int(end),
            "origin": (0.0, 0.0, 0.0),
            "game_hint": img_reader.detect_sector_game_hint(),
            "nested_child_container": True,
            "nested_group_index": row_index,
            "nested_child_index": child_index,
        })

    overlay_rows = img_reader.collect_sector_overlay_resources(nested_records, max_resource_id=None, include_alt_12_layouts=include_alt_12_layouts, wanted_res_ids=wanted_res_ids, progress_callback=progress_callback)
    if needed_row_res_keys:
        overlay_rows = [
            row for row in overlay_rows
            if (int(row.get("row_index", -1)), int(row.get("res_id", -1))) in needed_row_res_keys
        ]

    nested_by_row_res: Dict[Tuple[int, int], bpy.types.Object] = {}
    parsed = 0
    skipped_duplicate = 0
    skipped_non_geometry = 0

    LVZ.dbg("— IMG Nested Child Resource MDLs —")
    LVZ.dbg(f"[nested-mdl] child containers scanned: {len(nested_records)}")
    LVZ.dbg(f"[nested-mdl] matching resource rows: {len(overlay_rows)}")

    total_overlay_rows = len(overlay_rows)
    for overlay_index, overlay in enumerate(overlay_rows):
        if progress_callback is not None and (overlay_index % 8 == 0 or overlay_index + 1 == total_overlay_rows):
            progress_callback(overlay_index + 1, total_overlay_rows)
        row_index = int(overlay.get("row_index", -1))
        res_id = int(overlay.get("res_id", -1))
        raw_off = int(overlay.get("raw_off", -1))
        sector_end = int(overlay.get("resource_end", overlay.get("sector_end", len(img_bytes))))
        key = (row_index, res_id)

        if row_index < 0 or res_id < 0:
            skipped_non_geometry += 1
            continue
        if key in nested_by_row_res:
            skipped_duplicate += 1
            continue

        try:
            material_list = parser.parse_mdl_material_list(raw_off, max_end=sector_end)
            groups, after = parser.parse_mdl_geometry_after_list(material_list, max_end=sector_end)
            parser.assign_materials_by_strip_bytes(material_list, groups)
        except Exception:
            skipped_non_geometry += 1
            continue

        obj, face_ranges = build_mesh_from_mdl_groups(f"{stem}_nested_row{row_index:03d}_res", res_id, groups)
        if obj is None:
            skipped_non_geometry += 1
            continue

        obj.name = f"{stem}_nested_row{row_index:03d}_res{res_id}"
        obj.data.name = obj.name
        slots_added = add_material_slots(obj, parser.material_by_res_index, material_list, face_ranges)

        obj["blds_kind"] = "IMG_NESTED_CHILD_MDL"
        obj["blds_res_index"] = res_id
        obj["blds_img_row_index"] = row_index
        obj["blds_img_nested_child_resource"] = True
        obj["blds_img_nested_raw_off"] = raw_off
        obj["blds_img_nested_raw_ptr"] = int(overlay.get("raw_ptr", 0))
        obj["blds_img_nested_cont"] = int(overlay.get("cont", 0))
        obj["blds_source_lvz_path"] = str(source_lvz_path)
        if img_name:
            obj["blds_source_img_path"] = str(Path(source_lvz_path).with_name(img_name))

        nested_by_row_res[key] = obj
        parsed += 1

        if IMPORT_VERBOSE_RESOURCE_BUILD_LOGS and parsed <= 96:
            LVZ.dbg(
                f"[nested-mdl] row={row_index} res={res_id} raw=0x{raw_off:08X} "
                f"format={material_list.format_tag} groups={len(groups)} materials={slots_added}"
            )

    LVZ.dbg(
        f"[nested-mdl] created={len(nested_by_row_res)} skipped_non_geometry={skipped_non_geometry} "
        f"skipped_duplicate={skipped_duplicate}"
    )
    return nested_by_row_res


def build_extra_area_direct_mdl_objects(stem: str, img_bytes: bytes, lvz_reader: LVZ.read_lvz, img_reader: LVZ.read_img, extra_container_records: List[Dict[str, int]], source_lvz_path: str, img_name: Optional[str], needed_res_ids=None, include_alt_12_layouts: bool = False, wanted_res_ids=None, progress_callback=None) -> List[bpy.types.Object]:
    if not extra_container_records:
        return []

    parser = LVZ.read_lvz(
        decomp_bytes=img_bytes,
        stem=stem,
        use_swizzle=bool(lvz_reader.use_swizzle),
        debug_print=False,
    )
    parser.material_by_res_index = lvz_reader.material_by_res_index

    overlay_rows = img_reader.collect_sector_overlay_resources(extra_container_records, max_resource_id=None, include_alt_12_layouts=include_alt_12_layouts, wanted_res_ids=wanted_res_ids, progress_callback=progress_callback)
    if needed_res_ids is not None:
        needed_res_ids = set(int(value) for value in needed_res_ids)
        overlay_rows = [row for row in overlay_rows if int(row.get("res_id", -1)) in needed_res_ids]
    area_objects: List[bpy.types.Object] = []
    seen = set()
    skipped_duplicate = 0
    skipped_non_geometry = 0

    if IMPORT_VERBOSE_RESOURCE_BUILD_LOGS:
        LVZ.dbg("— IMG AREA Direct Resource MDLs —")
        LVZ.dbg(f"[area-mdl] direct AREA/resource rows: {len(overlay_rows)}")

    total_overlay_rows = len(overlay_rows)
    for overlay_index, overlay in enumerate(overlay_rows):
        if progress_callback is not None and (overlay_index % 8 == 0 or overlay_index + 1 == total_overlay_rows):
            progress_callback(overlay_index + 1, total_overlay_rows)
        sector_index = int(overlay.get("sector_index", -1))
        res_id = int(overlay.get("res_id", -1))
        raw_off = int(overlay.get("raw_off", -1))
        sector_end = int(overlay.get("resource_end", overlay.get("sector_end", len(img_bytes))))
        key = (sector_index, res_id, raw_off)
        if key in seen:
            skipped_duplicate += 1
            continue
        seen.add(key)

        try:
            material_list = parser.parse_mdl_material_list(raw_off, max_end=sector_end)
            groups, after = parser.parse_mdl_geometry_after_list(material_list, max_end=sector_end)
            parser.assign_materials_by_strip_bytes(material_list, groups)
        except Exception:
            skipped_non_geometry += 1
            continue

        obj, face_ranges = build_mesh_from_mdl_groups(f"{stem}_area{abs(sector_index):04d}_res", res_id, groups)
        if obj is None:
            skipped_non_geometry += 1
            continue

        obj.name = f"{stem}_area{abs(sector_index):04d}_res{res_id}_{len(area_objects):04d}"
        obj.data.name = obj.name
        slots_added = add_material_slots(obj, parser.material_by_res_index, material_list, face_ranges)
        obj["blds_kind"] = "IMG_AREA_DIRECT_MDL"
        obj["blds_res_index"] = res_id
        obj["blds_img_area_sector_index"] = sector_index
        obj["blds_img_area_raw_off"] = raw_off
        obj["blds_img_area_raw_ptr"] = int(overlay.get("raw_ptr", 0))
        obj["blds_img_area_cont"] = int(overlay.get("cont", 0))
        obj["blds_source_lvz_path"] = str(source_lvz_path)
        if img_name:
            obj["blds_source_img_path"] = str(Path(source_lvz_path).with_name(img_name))
        area_objects.append(obj)

        if len(area_objects) <= 64:
            LVZ.dbg(
                f"[area-mdl] direct area={sector_index} res={res_id} raw=0x{raw_off:08X} "
                f"format={material_list.format_tag} groups={len(groups)} materials={slots_added}"
            )

    LVZ.dbg(
        f"[area-mdl] created={len(area_objects)} skipped_non_geometry={skipped_non_geometry} "
        f"skipped_duplicate={skipped_duplicate}"
    )
    return area_objects



def log_overlay_resource_stats(img_reader: LVZ.read_img, label: str):
    if not IMPORT_VERBOSE_RESOURCE_BUILD_LOGS:
        return
    stats = getattr(img_reader, "last_overlay_resource_stats", {}) or {}
    if not stats:
        return
    LVZ.dbg(
        f"[overlay-table:{label}] containers={stats.get('containers', 0)} "
        f"accepted={stats.get('accepted', 0)} "
        f"8:id_ptr={stats.get('rows_8_id_ptr', 0)} "
        f"12:ptr_unused_id={stats.get('rows_12_ptr_id', 0)} "
        f"12:ptr_id_unused={stats.get('rows_12_ptr_mid_id', 0)} "
        f"12:id_unused_ptr={stats.get('rows_12_id_unused_ptr', 0)} "
        f"12:id_ptr_unused={stats.get('rows_12_id_ptr_unused', 0)} "
        f"ptrVariants={stats.get('pointer_variants', 0)} "
        f"expanded_bounds={stats.get('expanded_bounds', 0)}"
    )


def stamp_source_paths(objects_by_res: Dict[int, bpy.types.Object], lvz_path: str, img_name: Optional[str]):
    for _, obj in objects_by_res.items():
        try:
            obj["blds_source_lvz_path"] = str(lvz_path)
            if img_name:
                obj["blds_source_img_path"] = str(Path(lvz_path).with_name(img_name))
        except Exception:
            pass

def stamp_img_detail_on_object(obj: bpy.types.Object, detail, instance_index: int):
    obj["blds_img_cont"] = int(detail[1])
    obj["blds_img_rel_off"] = int(detail[2])
    obj["blds_img_ipl_raw"] = int(detail[3])
    obj["blds_img_ipl_id"] = int(detail[4])
    obj["blds_img_instance_index"] = int(instance_index)
    if len(detail) > 18:
        obj["blds_img_pass_index"] = int(detail[13])
        obj["blds_img_pass_name"] = str(detail[14])
        obj["blds_img_sector_index"] = int(detail[15])
        obj["blds_img_sector_x"] = int(detail[16])
        obj["blds_img_sector_y"] = int(detail[17])
        origin = detail[18]
        obj["blds_img_sector_origin_x"] = float(origin[0])
        obj["blds_img_sector_origin_y"] = float(origin[1])
        obj["blds_img_sector_origin_z"] = float(origin[2])
        if len(detail) > 19:
            obj["blds_img_row_index"] = int(detail[19])


def get_or_create_import_collection(collection_name: str):
    try:
        scene = bpy.context.scene
        root = scene.collection
        existing = bpy.data.collections.get(collection_name)
        if existing is None:
            existing = bpy.data.collections.new(collection_name)
        try:
            names = {child.name for child in root.children}
            if existing.name not in names:
                root.children.link(existing)
        except Exception:
            try:
                root.children.link(existing)
            except Exception:
                pass
        return existing
    except Exception:
        return None


def set_object_view_hidden(obj, hidden: bool):
    try:
        obj.hide_viewport = bool(hidden)
    except Exception:
        pass


def set_collection_view_hidden(collection, hidden: bool):
    if collection is None:
        return
    try:
        collection.hide_viewport = bool(hidden)
    except Exception:
        pass



RAW_PARSER_BASE_KIND_NAMES = {
    "LVZ_MDL",
    "IMG_MDL",
    "IMG_SECTOR_MDL",
    "IMG_GLOBAL_EXACT_RES_MDL",
    "IMG_IPL_MODEL_MDL",
    "IMG_NESTED_CHILD_MDL",
    "IMG_IPL_NESTED_MDL",
    "IMG_ROW_SHARED_MDL",
    "IMG_IPL_ROW_SHARED_MDL",
    "IMG_AREA_DIRECT_MDL",
    "IMG_IPL_AREA_DIRECT_MDL",
    "IMG_EXTRA_EXACT_SECTOR_MDL",
    "IMG_AGGREGATE_GROUP_PART",
}


def blds_object_is_visible_placement_instance(obj) -> bool:
    if obj is None:
        return False

    placement_flags = (
        "blds_visible_placement_instance",
        "blds_img_linked_duplicate",
        "blds_missing_mdl_imported",
        "blds_final_missing_mdl_imported",
        "blds_missing_nearby_clone",
        "blds_placement_instance",
    )

    for flag_name in placement_flags:
        try:
            if bool(obj.get(flag_name, False)):
                return True
        except Exception:
            pass

    name_lower = str(getattr(obj, "name", "")).lower()
    if "_ipl" in name_lower:
        return True
    if "missingmdl" in name_lower:
        return True
    if name_lower.startswith("beach1_ipl") or name_lower.startswith("mainla1_ipl"):
        return True

    return False


def blds_raw_parser_base_name_matches(name: str, import_stem: str = "") -> bool:
    raw_name = str(name or "")
    if not raw_name:
        return False

    # Blender may append .001/.002.  Strip only the automatic duplicate suffix.
    base_name = re.sub(r"\.\d{3}$", "", raw_name)
    lower = base_name.lower()

    if "_ipl" in lower or "missingmdl" in lower:
        return False

    stems = set()
    stem = str(import_stem or "").strip().lower()
    if stem:
        stems.add(stem)
        stems.add(stem + "1")

    # Keep the common maps covered even when the import stem was unavailable.
    stems.update(("beach", "beach1", "mainla", "mainla1"))

    prefix_group = "|".join(re.escape(item) for item in sorted(stems, key=len, reverse=True))
    raw_patterns = (
        rf"^(?:{prefix_group})_sec-?\d+_res\d+$",
        rf"^(?:{prefix_group})_row-?\d+_res\d+$",
        rf"^(?:{prefix_group})_nested_row-?\d+_res\d+$",
        rf"^(?:{prefix_group})_area-?\d+_res\d+(?:_\d+)?$",
        rf"^(?:{prefix_group})_img_\d+$",
        rf"^(?:{prefix_group})_agg_res\d+_g\d+$",
    )

    return any(re.match(pattern, lower) is not None for pattern in raw_patterns)


def blds_object_is_raw_parser_base(obj, import_stem: str = "") -> bool:
    if obj is None:
        return False

    if blds_object_is_visible_placement_instance(obj):
        return False

    try:
        if getattr(obj, "type", None) != "MESH":
            return False
    except Exception:
        return False

    if blds_raw_parser_base_name_matches(str(getattr(obj, "name", "")), import_stem):
        return True

    try:
        kind = str(obj.get("blds_kind", ""))
    except Exception:
        kind = ""

    if kind in RAW_PARSER_BASE_KIND_NAMES:
        return True

    return False


def purge_stale_raw_parser_bases(import_stem: str = "", reason: str = "stale") -> int:
    touched = 0
    try:
        objects = list(bpy.data.objects)
    except Exception:
        objects = []

    for obj in objects:
        if not blds_object_is_raw_parser_base(obj, import_stem):
            continue
        try:
            if RAW_PARSER_BASE_CLEANUP_MODE == "delete":
                mesh = obj.data if getattr(obj, "type", None) == "MESH" else None
                bpy.data.objects.remove(obj, do_unlink=True)
                if mesh is not None and mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
            else:
                obj.hide_viewport = True
                obj.hide_render = True
                try:
                    obj.hide_set(True)
                except Exception:
                    pass
                obj["blds_raw_parser_base_hidden_fast_cleanup"] = True
            touched += 1
        except Exception:
            try:
                obj.hide_viewport = True
                obj.hide_render = True
            except Exception:
                pass

    try:
        if touched:
            LVZ.dbg(f"[cleanup] raw parser base cleanup: mode={RAW_PARSER_BASE_CLEANUP_MODE} touched={touched} ({reason}); visible placements left alone")
    except Exception:
        pass
    return touched



def remove_unplaced_base_objects(candidate_objects, used_object_ids) -> int:
    touched = 0
    seen_ids = set()
    for obj in list(candidate_objects):
        if obj is None:
            continue
        oid = id(obj)
        if oid in seen_ids:
            continue
        seen_ids.add(oid)

        if blds_object_is_visible_placement_instance(obj):
            continue

        try:
            if RAW_PARSER_BASE_CLEANUP_MODE == "delete":
                mesh = obj.data if getattr(obj, "type", None) == 'MESH' else None
                bpy.data.objects.remove(obj, do_unlink=True)
                if mesh is not None and mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
            else:
                obj.hide_viewport = True
                obj.hide_render = True
                try:
                    obj.hide_set(True)
                except Exception:
                    pass
                obj["blds_raw_parser_base_hidden_fast_cleanup"] = True
            touched += 1
        except Exception:
            try:
                obj.hide_viewport = True
                obj.hide_render = True
            except Exception:
                pass
    return touched




def blds_mesh_quality_score(obj) -> float:
    if obj is None:
        return -1.0
    try:
        verts = float(obj.get("blds_verts", 0))
    except Exception:
        verts = 0.0
    try:
        faces = float(obj.get("blds_faces", 0))
    except Exception:
        faces = 0.0
    try:
        groups = float(obj.get("blds_groups", 0))
    except Exception:
        groups = 0.0
    try:
        radius = float(obj.get("blds_local_radius", 0.0))
    except Exception:
        radius = 0.0

    # Prefer the richest candidate for a shared IPL/model id.  VCS beach has
    # multiple sector resource-table candidates for the same model id.  Taking
    # the first one gives stripped/partial facades like beach model 562 from
    # sector 60; sector 61 has the fuller mesh.
    return (faces * 8.0) + (verts * 2.0) + (groups * 64.0) + min(max(radius, 0.0), 4096.0)


def choose_better_blds_candidate(old_obj, new_obj):
    if old_obj is None:
        return new_obj
    if new_obj is None:
        return old_obj
    old_score = blds_mesh_quality_score(old_obj)
    new_score = blds_mesh_quality_score(new_obj)
    if new_score > old_score:
        return new_obj
    return old_obj


def get_blds_object_local_radius(obj) -> float:
    if obj is None:
        return 0.0
    try:
        cached = obj.get("blds_local_radius", None)
        if cached is not None:
            return float(cached)
    except Exception:
        pass
    try:
        verts = obj.data.vertices
    except Exception:
        return 0.0
    if not verts:
        return 0.0
    xs = [float(v.co.x) for v in verts]
    ys = [float(v.co.y) for v in verts]
    zs = [float(v.co.z) for v in verts]
    cx = (min(xs) + max(xs)) * 0.5
    cy = (min(ys) + max(ys)) * 0.5
    cz = (min(zs) + max(zs)) * 0.5
    radius = 0.0
    for v in verts:
        dx = float(v.co.x) - cx
        dy = float(v.co.y) - cy
        dz = float(v.co.z) - cz
        radius = max(radius, (dx * dx + dy * dy + dz * dz) ** 0.5)
    try:
        obj["blds_local_radius"] = float(radius)
    except Exception:
        pass
    return float(radius)


def detail_expected_world_radius(detail) -> float:
    try:
        expected = abs(float(detail[8]))
    except Exception:
        expected = 0.0
    return expected


def detail_max_matrix_scale(detail) -> float:
    try:
        s0 = abs(float(detail[9]))
        s1 = abs(float(detail[10]))
        s2 = abs(float(detail[11]))
        return max(s0, s1, s2, 0.000001)
    except Exception:
        return 1.0


def neighbor_alias_candidate_is_safe(obj, detail) -> Tuple[bool, str]:
    # V18 fixed a lot of holes, but it could also alias tiny placeholder rows
    # onto a huge neighbouring chunk. That creates the giant purple/grey slabs.
    # Only accept an alias when the candidate's transformed radius is close to
    # the placement row sphere.
    expected = detail_expected_world_radius(detail)
    if expected <= 0.0:
        return True, "no_expected_radius"
    local_radius = get_blds_object_local_radius(obj)
    max_scale = detail_max_matrix_scale(detail)
    world_radius = local_radius * max_scale
    limit = max(float(NEIGHBOR_ALIAS_MIN_RADIUS_LIMIT), expected * float(NEIGHBOR_ALIAS_MAX_WORLD_RADIUS_RATIO))
    if expected <= float(NEIGHBOR_ALIAS_TINY_PLACEMENT_RADIUS):
        limit = min(limit, float(NEIGHBOR_ALIAS_TINY_MAX_WORLD_RADIUS))
    if world_radius > limit:
        return False, f"radius world={world_radius:.3f} local={local_radius:.3f} scale={max_scale:.3f} expected={expected:.3f} limit={limit:.3f}"
    return True, f"radius world={world_radius:.3f} expected={expected:.3f} limit={limit:.3f}"


def lookup_neighbor_alias_base(
    res_id: int,
    sector_index: int,
    row_index: int,
    detail,
    overlay_by_sector_res: Dict[Tuple[int, int], bpy.types.Object],
    nested_overlay_by_res: Dict[Tuple[int, int], bpy.types.Object],
    row_overlay_by_res: Dict[Tuple[int, int], bpy.types.Object],
    built_by_res: Dict[int, bpy.types.Object],
    extra_by_res: Dict[int, bpy.types.Object],
    overlay_by_res: Dict[int, bpy.types.Object],
):
    rejected = []

    def try_candidate(obj, cand_res, source, delta):
        if obj is None:
            return None
        ok, why = neighbor_alias_candidate_is_safe(obj, detail)
        if ok:
            return obj, cand_res, source, delta, rejected
        if len(rejected) < NEIGHBOR_ALIAS_LOG_LIMIT:
            rejected.append((sector_index, row_index, int(detail[4]), res_id, cand_res, source, delta, str(detail[14]) if len(detail) > 14 else "UNKNOWN", why))
        return None

    # Some VCS beach/mainland rows use placeholder/aggregate resource IDs with
    # no direct payload row. The real sector chunk can be adjacent, but it is
    # only safe to use if its size matches the placement sphere.
    for delta in range(1, int(NEIGHBOR_ALIAS_MAX_DELTA) + 1):
        for cand_res in (res_id - delta, res_id + delta):
            got = try_candidate(overlay_by_sector_res.get((sector_index, cand_res)), cand_res, "sector-neighbor", delta)
            if got is not None:
                return got

    if row_index >= 0:
        for delta in range(1, int(NEIGHBOR_ALIAS_MAX_DELTA) + 1):
            for cand_res in (res_id - delta, res_id + delta):
                got = try_candidate(nested_overlay_by_res.get((row_index, cand_res)), cand_res, "nested-row-neighbor", delta)
                if got is not None:
                    return got
                got = try_candidate(row_overlay_by_res.get((row_index, cand_res)), cand_res, "row-neighbor", delta)
                if got is not None:
                    return got

    # Last resort: global neighbouring MDL resources. Keep this radius small to
    # avoid pulling in unrelated city chunks.
    for delta in range(1, int(NEIGHBOR_ALIAS_GLOBAL_MAX_DELTA) + 1):
        for cand_res in (res_id - delta, res_id + delta):
            got = try_candidate(built_by_res.get(cand_res), cand_res, "lvz-neighbor", delta)
            if got is not None:
                return got
            got = try_candidate(extra_by_res.get(cand_res), cand_res, "area-neighbor", delta)
            if got is not None:
                return got
            got = try_candidate(overlay_by_res.get(cand_res), cand_res, "overlay-neighbor", delta)
            if got is not None:
                return got

    return None, -1, "", 0, rejected


def apply_img_instance_transforms(built_by_res: Dict[int, bpy.types.Object], details, overlay_by_sector_res: Optional[Dict[Tuple[int, int], bpy.types.Object]] = None, extra_resource_objects: Optional[List[bpy.types.Object]] = None, row_overlay_by_res: Optional[Dict[Tuple[int, int], bpy.types.Object]] = None, nested_overlay_by_res: Optional[Dict[Tuple[int, int], bpy.types.Object]] = None, ipl_overlay_by_sector_res: Optional[Dict[Tuple[int, int], bpy.types.Object]] = None, ipl_row_overlay_by_res: Optional[Dict[Tuple[int, int], bpy.types.Object]] = None, ipl_nested_overlay_by_res: Optional[Dict[Tuple[int, int], bpy.types.Object]] = None, ipl_extra_resource_objects: Optional[List[bpy.types.Object]] = None, import_stem: str = "beach", ide_ipl_to_res: Optional[Dict[int, int]] = None, ide_ipl_to_name: Optional[Dict[int, str]] = None, progress_callback=None) -> Tuple[int, int, int]:
    if not details:
        return 0, 0, 0

    overlay_by_sector_res = overlay_by_sector_res or {}
    extra_resource_objects = extra_resource_objects or []
    row_overlay_by_res = row_overlay_by_res or {}
    nested_overlay_by_res = nested_overlay_by_res or {}
    ipl_overlay_by_sector_res = ipl_overlay_by_sector_res or {}
    ipl_row_overlay_by_res = ipl_row_overlay_by_res or {}
    ipl_nested_overlay_by_res = ipl_nested_overlay_by_res or {}
    ipl_extra_resource_objects = ipl_extra_resource_objects or []
    # V75: these maps are loaded in the main importer scope.  Keep local empty
    # fallbacks so placement can never die from IDE debug/report metadata.
    ide_ipl_to_res = ide_ipl_to_res or {}
    ide_ipl_to_name = ide_ipl_to_name or {}

    overlay_by_res: Dict[int, bpy.types.Object] = {}
    continuation_by_res: Dict[int, bpy.types.Object] = {}
    for (sector_index, res_id), obj in overlay_by_sector_res.items():
        if obj is None:
            continue
        resource_id = int(res_id)
        old_obj = overlay_by_res.get(resource_id)
        overlay_by_res[resource_id] = choose_better_blds_candidate(old_obj, obj)
        try:
            is_continuation = bool(obj.get("blds_img_continues_in_img", False))
        except Exception:
            is_continuation = False
        if is_continuation:
            old_continuation = continuation_by_res.get(resource_id)
            continuation_by_res[resource_id] = choose_better_blds_candidate(old_continuation, obj)

    if continuation_by_res:
        LVZ.dbg(f"[continues-img] proven placement model pool: {len(continuation_by_res)} resource ids")

    extra_by_res: Dict[int, bpy.types.Object] = {}
    for obj in extra_resource_objects:
        if obj is None:
            continue
        try:
            res_id = int(obj.get("blds_res_index", -1))
        except Exception:
            continue
        if res_id < 0:
            continue
        old_obj = extra_by_res.get(res_id)
        extra_by_res[res_id] = choose_better_blds_candidate(old_obj, obj)

    ipl_overlay_by_res: Dict[int, bpy.types.Object] = {}
    ipl_overlay_choice_replacements = 0
    for (sector_index, model_id), obj in ipl_overlay_by_sector_res.items():
        if obj is None:
            continue
        model_id = int(model_id)
        old_obj = ipl_overlay_by_res.get(model_id)
        chosen = choose_better_blds_candidate(old_obj, obj)
        if chosen is not old_obj and old_obj is not None:
            ipl_overlay_choice_replacements += 1
        ipl_overlay_by_res[model_id] = chosen

    ipl_extra_by_res: Dict[int, bpy.types.Object] = {}
    ipl_extra_choice_replacements = 0
    for obj in ipl_extra_resource_objects:
        if obj is None:
            continue
        try:
            model_id = int(obj.get("blds_res_index", -1))
        except Exception:
            continue
        if model_id < 0:
            continue
        old_obj = ipl_extra_by_res.get(model_id)
        chosen = choose_better_blds_candidate(old_obj, obj)
        if chosen is not old_obj and old_obj is not None:
            ipl_extra_choice_replacements += 1
        ipl_extra_by_res[model_id] = chosen

    def iter_ipl_model_candidates(model_id: int, sector_index: int, row_index: int):
        model_id = int(model_id)
        ordered = []
        ordered.append((ipl_overlay_by_sector_res.get((sector_index, model_id)), "sector-ipl", 0, model_id))
        if row_index >= 0:
            ordered.append((ipl_nested_overlay_by_res.get((row_index, model_id)), "nested-ipl", 1, model_id))
            ordered.append((ipl_row_overlay_by_res.get((row_index, model_id)), "row-ipl", 2, model_id))
        ordered.append((ipl_overlay_by_res.get(model_id), "global-sector-ipl", 3, model_id))
        ordered.append((ipl_extra_by_res.get(model_id), "area-ipl", 4, model_id))
        ordered.append((built_by_res.get(model_id), "lvz-ipl", 5, model_id))
        ordered.append((overlay_by_res.get(model_id), "same-resource-ipl", 6, model_id))
        ordered.append((extra_by_res.get(model_id), "area-res", 7, model_id))
        for candidate_obj, candidate_source, rank, candidate_model_id in ordered:
            if candidate_obj is not None:
                yield candidate_obj, candidate_source, int(rank), int(candidate_model_id)

    def lookup_any_ipl_model_candidate(model_id: int, sector_index: int, row_index: int):
        best_obj = None
        best_source = None
        best_rank = 999999
        for candidate_obj, candidate_source, rank, candidate_model_id in iter_ipl_model_candidates(model_id, sector_index, row_index):
            chosen = choose_better_blds_candidate(best_obj, candidate_obj)
            if best_obj is None or chosen is candidate_obj or rank < best_rank:
                best_obj = candidate_obj
                best_source = candidate_source
                best_rank = int(rank)
        return best_obj, best_source

    resolver_audit_lines = 0

    def resolver_object_summary(label, obj):
        if obj is None:
            return f"{label}=None"
        try:
            name = str(getattr(obj, "name", ""))
        except Exception:
            name = "<no-name>"
        try:
            kind = str(obj.get("blds_kind", ""))
        except Exception:
            kind = ""
        try:
            res = int(obj.get("blds_res_index", -1))
        except Exception:
            res = -1
        try:
            sector = int(obj.get("blds_img_sector_index", obj.get("blds_img_row_base_sector_index", obj.get("blds_img_area_index", -1))))
        except Exception:
            sector = -1
        try:
            row = int(obj.get("blds_img_row_index", -1))
        except Exception:
            row = -1
        try:
            parent = int(obj.get("blds_parent_res_index", -1))
        except Exception:
            parent = -1
        try:
            group = int(obj.get("blds_group_index", -1))
        except Exception:
            group = -1
        try:
            groups = int(obj.get("blds_groups", 0))
        except Exception:
            groups = 0
        gv, gf, gr = object_geometry_counts_radius(obj)
        raw_bits = []
        for key in (
            "blds_img_overlay_raw_off", "blds_img_overlay_raw_ptr",
            "blds_img_nested_raw_off", "blds_img_nested_raw_ptr",
            "blds_img_area_raw_off", "blds_img_area_raw_ptr",
        ):
            try:
                if key in obj:
                    raw_bits.append(f"{key}=0x{int(obj.get(key, 0)):08X}")
            except Exception:
                pass
        raw_txt = " ".join(raw_bits) if raw_bits else "raw=?"
        return (
            f"{label}=name:{name}|kind:{kind}|res:{res}|sector:{sector}|row:{row}|"
            f"parent:{parent}|group:{group}|groups:{groups}|geom:{int(gv)}v/{int(gf)}f/r{float(gr):.3f}|{raw_txt}"
        )

    def resolver_pool_candidates(model_id: int, sector_index: int, row_index: int):
        model_id = int(model_id)
        sector_index = int(sector_index)
        row_index = int(row_index)
        out = []
        def add(label, obj):
            if obj is not None:
                out.append((label, obj))
        def add_model(prefix, mid):
            mid = int(mid)
            add(f"{prefix}exact_sector_res", overlay_by_sector_res.get((sector_index, mid)))
            if row_index >= 0:
                add(f"{prefix}exact_nested_row_res", nested_overlay_by_res.get((row_index, mid)))
                add(f"{prefix}exact_row_res", row_overlay_by_res.get((row_index, mid)))
            add(f"{prefix}exact_master_res", built_by_res.get(mid))
            add(f"{prefix}exact_area_res", extra_by_res.get(mid))
            add(f"{prefix}exact_any_sector_res", overlay_by_res.get(mid))
            add(f"{prefix}ipl_sector_model", ipl_overlay_by_sector_res.get((sector_index, mid)))
            if row_index >= 0:
                add(f"{prefix}ipl_nested_row_model", ipl_nested_overlay_by_res.get((row_index, mid)))
                add(f"{prefix}ipl_row_model", ipl_row_overlay_by_res.get((row_index, mid)))
            add(f"{prefix}ipl_global_sector_model", ipl_overlay_by_res.get(mid))
            add(f"{prefix}ipl_area_model", ipl_extra_by_res.get(mid))

        add_model("", model_id)
        ide_res = None
        try:
            ide_res = int(ide_ipl_to_res.get(model_id, -1))
        except Exception:
            ide_res = -1
        if ide_res is not None and ide_res >= 0 and ide_res != model_id:
            add_model(f"ide:{model_id}->{ide_res}:", ide_res)
        return out

    def find_rich_ipl_candidate_over_sparse(ipl_id: int, sector_index: int, row_index: int, sparse_verts: int, sparse_faces: int):
        if not ENABLE_RICH_IPL_OVER_SPARSE_RECOVERY:
            return None, "", "disabled"
        try:
            ipl_id = int(ipl_id)
            sparse_verts = max(1, int(sparse_verts))
            sparse_faces = max(1, int(sparse_faces))
        except Exception:
            return None, "", "bad-ids"

        best_obj = None
        best_label = ""
        best_score = -1.0
        reject_notes = []
        for label, obj in resolver_pool_candidates(ipl_id, int(sector_index), int(row_index)):
            if obj is None:
                continue
            try:
                _label_base = str(label).split(":")[-1]
                if _label_base not in RICH_IPL_RECOVERY_ALLOWED_LABELS:
                    reject_notes.append(f"{label}:label-not-allowed")
                    continue
                obj_res_id = int(obj.get("blds_res_index", -1))
                expected_res_ids = {int(ipl_id)}
                try:
                    _ide_res = int(ide_ipl_to_res.get(int(ipl_id), -1))
                    if _ide_res >= 0:
                        expected_res_ids.add(_ide_res)
                except Exception:
                    pass
                if obj_res_id not in expected_res_ids:
                    reject_notes.append(f"{label}:id-mismatch:{obj_res_id}:expected={sorted(expected_res_ids)}")
                    continue
                kind = str(obj.get("blds_kind", ""))
                if kind == "IMG_WRLD_SUBMODEL_GROUP" or bool(obj.get("blds_submodel_id_recovery", False)):
                    reject_notes.append(f"{label}:wrld-submodel-rejected")
                    continue
                if kind and kind not in RICH_IPL_RECOVERY_REAL_MDL_KINDS and not kind.startswith("IMG_"):
                    reject_notes.append(f"{label}:kind-not-real-mdl:{kind}")
                    continue
            except Exception:
                reject_notes.append(f"{label}:bad-meta")
                continue

            gv, gf, gr = object_geometry_counts_radius(obj)
            vr = float(gv) / float(sparse_verts)
            fr = float(gf) / float(sparse_faces)
            if gv < int(RICH_IPL_RECOVERY_MIN_VERTS) or gf < int(RICH_IPL_RECOVERY_MIN_FACES):
                reject_notes.append(f"{label}:too-small:{gv}v/{gf}f")
                continue
            if vr < float(RICH_IPL_RECOVERY_MIN_VERT_RATIO) and fr < float(RICH_IPL_RECOVERY_MIN_FACE_RATIO):
                reject_notes.append(f"{label}:not-richer:{gv}v/{gf}f ratio={vr:.2f}/{fr:.2f}")
                continue

            try:
                obj_sector = int(obj.get("blds_img_sector_index", obj.get("blds_img_row_base_sector_index", -999999)))
                obj_row = int(obj.get("blds_img_row_index", -999999))
            except Exception:
                obj_sector = -999999
                obj_row = -999999
            locality_bonus = 0.0
            if obj_sector == int(sector_index):
                locality_bonus += 10000000.0
            if obj_row == int(row_index) and obj_row >= 0:
                locality_bonus += 5000000.0
            _label_base_score = str(label).split(":")[-1]
            if _label_base_score.startswith("ipl_"):
                locality_bonus += 1000000.0
            if "ide:" in str(label):
                locality_bonus += 750000.0
            if "area" in str(label):
                locality_bonus += 250000.0
            score = locality_bonus + float(gv) + float(gf) + float(gr) * 100.0
            if score > best_score:
                best_score = score
                best_obj = obj
                best_label = label

        if best_obj is not None:
            gv, gf, gr = object_geometry_counts_radius(best_obj)
            return best_obj, best_label, f"rich-ipl-over-sparse:ipl={gv}v/{gf}f/r{gr:.3f}:sparse={sparse_verts}v/{sparse_faces}f:ratio={float(gv)/float(sparse_verts):.2f}/{float(gf)/float(sparse_faces):.2f}"
        return None, "", "no-rich-ipl-candidate:" + ";".join(reject_notes[:8])


    def find_real_ipl_candidate_for_missing_res(ipl_id: int, sector_index: int, row_index: int):
        if not ENABLE_REAL_IPL_FOR_MISSING_RES_ROWS:
            return None, "", "disabled"
        try:
            ipl_id = int(ipl_id)
            sector_index = int(sector_index)
            row_index = int(row_index)
        except Exception:
            return None, "", "bad-ids"

        best_obj = None
        best_label = ""
        best_score = -1.0
        reject_notes = []
        for label, obj in resolver_pool_candidates(ipl_id, sector_index, row_index):
            if obj is None:
                continue
            try:
                _label_base = str(label).split(":")[-1]
                if _label_base not in RICH_IPL_RECOVERY_ALLOWED_LABELS:
                    reject_notes.append(f"{label}:label-not-allowed")
                    continue
                obj_res_id = int(obj.get("blds_res_index", -1))
                expected_res_ids = {int(ipl_id)}
                try:
                    _ide_res = int(ide_ipl_to_res.get(int(ipl_id), -1))
                    if _ide_res >= 0:
                        expected_res_ids.add(_ide_res)
                except Exception:
                    pass
                if obj_res_id not in expected_res_ids:
                    reject_notes.append(f"{label}:id-mismatch:{obj_res_id}:expected={sorted(expected_res_ids)}")
                    continue
                kind = str(obj.get("blds_kind", ""))
                if kind == "IMG_WRLD_SUBMODEL_GROUP" or bool(obj.get("blds_submodel_id_recovery", False)):
                    reject_notes.append(f"{label}:wrld-submodel-rejected")
                    continue
                if kind and kind not in RICH_IPL_RECOVERY_REAL_MDL_KINDS and not kind.startswith("IMG_"):
                    reject_notes.append(f"{label}:kind-not-real-mdl:{kind}")
                    continue
            except Exception:
                reject_notes.append(f"{label}:bad-meta")
                continue

            gv, gf, gr = object_geometry_counts_radius(obj)
            if gv < int(REAL_IPL_FOR_MISSING_MIN_VERTS) or gf < int(REAL_IPL_FOR_MISSING_MIN_FACES):
                reject_notes.append(f"{label}:too-small:{gv}v/{gf}f")
                continue

            try:
                obj_sector = int(obj.get("blds_img_sector_index", obj.get("blds_img_row_base_sector_index", -999999)))
                obj_row = int(obj.get("blds_img_row_index", -999999))
            except Exception:
                obj_sector = -999999
                obj_row = -999999

            locality_bonus = 0.0
            if obj_sector == sector_index:
                locality_bonus += 10000000.0
            if obj_row == row_index and obj_row >= 0:
                locality_bonus += 5000000.0
            _label_base_score = str(label).split(":")[-1]
            if _label_base_score.startswith("ipl_"):
                locality_bonus += 1000000.0
            if "ide:" in str(label):
                locality_bonus += 750000.0
            if "area" in str(label):
                locality_bonus += 250000.0
            score = locality_bonus + float(gv) + float(gf) + float(gr) * 100.0
            if score > best_score:
                best_score = score
                best_obj = obj
                best_label = label

        if best_obj is not None:
            gv, gf, gr = object_geometry_counts_radius(best_obj)
            return best_obj, best_label, f"real-ipl-for-missing-res:ipl={gv}v/{gf}f/r{gr:.3f}"
        return None, "", "no-real-ipl-candidate:" + ";".join(reject_notes[:10])


    def resolver_audit_row(detail, stage, chosen_obj=None, chosen_source="", extra_note=""):
        nonlocal resolver_audit_lines
        if not RESOLVER_AUDIT_ENABLED:
            return
        if resolver_audit_lines >= int(RESOLVER_AUDIT_MAX_ROWS):
            return
        try:
            res_id_a = int(detail[0])
            cont_a = int(detail[1])
            rel_a = int(detail[2])
            ipl_raw_a = int(detail[3])
            ipl_id_a = int(detail[4])
            pass_index_a = int(detail[13])
            pass_name_a = str(detail[14])
            sector_index_a = int(detail[15])
            row_index_a = int(detail[19]) if len(detail) > 19 else -1
            row_abs_a = cont_a + rel_a
        except Exception:
            return
        stage_l = str(stage).lower()
        id_watched = bool(res_id_a in RESOLVER_AUDIT_ALWAYS_RES_IDS or ipl_id_a in RESOLVER_AUDIT_ALWAYS_IPL_IDS)
        pass_watched = bool(pass_name_a in RESOLVER_AUDIT_TARGET_PASSES)
        if RESOLVER_AUDIT_TARGET_ONLY:
            should = bool(id_watched or ("fragment" in stage_l and pass_watched))
        else:
            should = bool(id_watched or chosen_obj is None or "missing" in stage_l or "fragment" in stage_l)
        if not should:
            return
        try:
            sphere = f"{float(detail[5]):.3f},{float(detail[6]):.3f},{float(detail[7]):.3f},r{float(detail[8]):.3f}"
        except Exception:
            sphere = "?"
        try:
            raw_scale = f"{float(detail[9]):.3f},{float(detail[10]):.3f},{float(detail[11]):.3f}"
        except Exception:
            raw_scale = "?"
        LVZ.dbg(
            f"[resolver] stage={stage} RES={res_id_a} IPL={ipl_id_a} IPLraw=0x{ipl_raw_a:04X} "
            f"sector={sector_index_a} row={row_index_a} pass={pass_name_a}/{pass_index_a} "
            f"rowAbs=0x{row_abs_a:08X} contIMG=0x{cont_a:08X} rel=0x{rel_a:08X} "
            f"sphere={sphere} rowMatrixScale={raw_scale} chosenSource={chosen_source or ''} note={extra_note or ''}"
        )
        resolver_audit_lines += 1
        for field_name, model_id in (("RES", res_id_a), ("IPL", ipl_id_a)):
            shown = 0
            candidates = resolver_pool_candidates(model_id, sector_index_a, row_index_a)
            if not candidates:
                LVZ.dbg(f"[resolver]   {field_name}={model_id} candidates: NONE")
                resolver_audit_lines += 1
                continue
            for label, obj in candidates:
                if shown >= int(RESOLVER_AUDIT_CANDIDATE_LIMIT_PER_ROW):
                    LVZ.dbg(f"[resolver]   {field_name}={model_id} candidates truncated")
                    resolver_audit_lines += 1
                    break
                LVZ.dbg("[resolver]   " + resolver_object_summary(f"{field_name}:{model_id}:{label}", obj))
                resolver_audit_lines += 1
                shown += 1
                if resolver_audit_lines >= int(RESOLVER_AUDIT_MAX_ROWS):
                    return
        if chosen_obj is not None and resolver_audit_lines < int(RESOLVER_AUDIT_MAX_ROWS):
            LVZ.dbg("[resolver]   CHOSEN " + resolver_object_summary("chosen", chosen_obj))
            resolver_audit_lines += 1


    def candidate_pool_items(pool):
        for key, value in (pool or {}).items():
            if value is None:
                continue
            try:
                if isinstance(key, tuple):
                    yield int(key[-1]), value
                else:
                    yield int(key), value
            except Exception:
                continue

    def lookup_nearby_ipl_model_candidate(model_id: int, sector_index: int, row_index: int, detail, imported_family_map):
        if not ENABLE_FINAL_MISSING_IPL_NEIGHBOR_IMPORT:
            return None, None, -1, "disabled"
        model_id = int(model_id)
        best_obj = None
        best_source = None
        best_model_id = -1
        best_score = None
        best_note = ""

        def consider(candidate_id, candidate_obj, source_name, source_bias):
            nonlocal best_obj, best_source, best_model_id, best_score, best_note
            if candidate_obj is None:
                return
            try:
                candidate_id = int(candidate_id)
            except Exception:
                return
            delta = abs(candidate_id - model_id)
            if delta <= 0 or delta > int(FINAL_MISSING_IPL_NEIGHBOR_MAX_DELTA):
                return
            score = float(delta) * 100.0 + float(source_bias)
            if best_score is None or score < best_score:
                best_obj = candidate_obj
                best_source = f"{source_name}:candidate={candidate_id}:delta={delta}"
                best_model_id = candidate_id
                best_score = score
                best_note = f"nearest candidate {candidate_id} delta {delta}"
            elif score == best_score:
                chosen = choose_better_blds_candidate(best_obj, candidate_obj)
                if chosen is candidate_obj:
                    best_obj = candidate_obj
                    best_source = f"{source_name}:candidate={candidate_id}:delta={delta}"
                    best_model_id = candidate_id
                    best_score = score
                    best_note = f"nearest candidate {candidate_id} delta {delta}"

        for item in imported_family_map.get(int(detail[0]), []):
            consider(item.get("ipl_id", -1), item.get("base_obj"), "nearest-prior-missing-family", 0)

        for candidate_id, candidate_obj in candidate_pool_items({k: v for k, v in ipl_overlay_by_sector_res.items() if int(k[0]) == int(sector_index)}):
            consider(candidate_id, candidate_obj, "nearest-sector-ipl", 5)
        if row_index >= 0:
            for candidate_id, candidate_obj in candidate_pool_items({k: v for k, v in ipl_nested_overlay_by_res.items() if int(k[0]) == int(row_index)}):
                consider(candidate_id, candidate_obj, "nearest-nested-ipl", 10)
            for candidate_id, candidate_obj in candidate_pool_items({k: v for k, v in ipl_row_overlay_by_res.items() if int(k[0]) == int(row_index)}):
                consider(candidate_id, candidate_obj, "nearest-row-ipl", 15)
        for candidate_id, candidate_obj in candidate_pool_items(ipl_overlay_by_res):
            consider(candidate_id, candidate_obj, "nearest-global-sector-ipl", 25)
        for candidate_id, candidate_obj in candidate_pool_items(ipl_extra_by_res):
            consider(candidate_id, candidate_obj, "nearest-area-ipl", 30)
        for candidate_id, candidate_obj in candidate_pool_items(built_by_res):
            consider(candidate_id, candidate_obj, "nearest-lvz-ipl", 40)
        for candidate_id, candidate_obj in candidate_pool_items(overlay_by_res):
            consider(candidate_id, candidate_obj, "nearest-same-resource-ipl", 50)
        for candidate_id, candidate_obj in candidate_pool_items(extra_by_res):
            consider(candidate_id, candidate_obj, "nearest-area-res", 60)

        return best_obj, best_source, best_model_id, best_note

    object_use_count: Dict[int, int] = {}
    used_object_ids = set()
    applied = 0
    linked = 0
    skipped_missing = 0
    fallback_overlay = 0
    fallback_extra = 0
    fallback_row = 0
    fallback_nested = 0
    fallback_aggregate = 0
    fallback_ipl = 0
    fallback_neighbor = 0
    fallback_force_missing_img_mdl = 0
    fallback_final_missing_ipl_neighbor = 0
    forced_missing_img_mdl_rows = []
    final_missing_ipl_neighbor_rows = []
    imported_missing_mdl_rows = []
    imported_missing_family_map = {}
    ipl_fallback_rows = []
    ipl_rejected_rows = []
    ipl_cell_scale_fixed = 0
    ipl_cell_scale_rows = []
    neighbor_alias_rows = []
    aggregate_piece_rows = []
    missing_rows = []
    missing_rows_full = []
    apply_log_count = 0
    apply_log_suppressed = 0
    hidden_duplicate_collection = None
    hidden_duplicate_collection_was_hidden = None
    try:
        target_collection = bpy.context.scene.collection
    except Exception:
        target_collection = bpy.context.collection
    if IMPORT_LINK_DUPLICATES_IN_HIDDEN_COLLECTION:
        try:
            hidden_duplicate_collection = get_or_create_import_collection("BLeeds IMG linked placements")
            if hidden_duplicate_collection is not None:
                try:
                    hidden_duplicate_collection_was_hidden = bool(hidden_duplicate_collection.hide_viewport)
                except Exception:
                    hidden_duplicate_collection_was_hidden = None
                set_collection_view_hidden(hidden_duplicate_collection, True)
                target_collection = hidden_duplicate_collection
                LVZ.dbg("[speed] linked duplicate placements into a hidden collection, then revealed at the end")
        except Exception as exc:
            LVZ.dbg(f"[speed] hidden placement collection setup failed: {exc}")
    link_object = target_collection.objects.link
    placed_objects_to_reveal = []
    total_details = len(details)

    def has_direct_exact_resource_for_row(sector_index, row_index, res_id):
        if overlay_by_sector_res.get((int(sector_index), int(res_id))) is not None:
            return True
        if int(row_index) >= 0 and nested_overlay_by_res.get((int(row_index), int(res_id))) is not None:
            return True
        if int(row_index) >= 0 and row_overlay_by_res.get((int(row_index), int(res_id))) is not None:
            return True
        if built_by_res.get(int(res_id)) is not None:
            return True
        if extra_by_res.get(int(res_id)) is not None:
            return True
        if overlay_by_res.get(int(res_id)) is not None:
            return True
        return False

    inferred_submodel_count = infer_wrld_submodel_group_lookup(details, has_direct_exact_resource_for_row)
    if ENABLE_WRLD_SUBMODEL_GROUP_ID_RECOVERY:
        LVZ.dbg(f"[submodel] inferred WRLD aggregate group-id recoveries: {inferred_submodel_count}")
        for row in WRLD_SUBMODEL_GROUP_INFER_ROWS[:96]:
            LVZ.dbg(
                f"[submodel] sector={row['sector_index']} ids={row['range_start']}..{row['range_end']} "
                f"parent={row['parent_res_id']} groups={row['group_count']} covered={row['covered_count']} "
                f"sample={row['covered_ids']}"
            )

    fallback_wrld_submodel_group = 0
    fallback_wrld_global_submodel = 0
    fallback_verified_render_pair = 0
    verified_render_pair_rows = []
    wrld_submodel_group_rows = []
    bad_nonlight_sparse_building_rows = []
    rich_ipl_over_sparse_rows = []
    real_ipl_for_missing_res_rows = []
    skipped_lights_pass_ipl_rows = []
    matrix_decision_rows = []
    transform_proof_rows = []
    object_transform_rows = []
    object_transform_log_lines = 0
    geometry_object_log_lines = 0
    visible_placement_dedupe_seen = set()
    skipped_duplicate_visible_rows = []
    positive_sector_pair_keys = set()
    try:
        for _detail_for_pair in details:
            _sec = int(_detail_for_pair[15]) if len(_detail_for_pair) > 15 else -1
            if _sec >= 0:
                positive_sector_pair_keys.add((int(_detail_for_pair[4]), int(_detail_for_pair[0]), str(_detail_for_pair[14]) if len(_detail_for_pair) > 14 else "UNKNOWN"))
    except Exception:
        positive_sector_pair_keys = set()

    total_details = len(details)
    for detail_index, detail in enumerate(details):
        if progress_callback is not None and (detail_index % 128 == 0 or detail_index + 1 == total_details):
            progress_callback(detail_index + 1, total_details)
        used_ipl_model_fallback = False
        used_force_missing_img_mdl = False
        used_exact_missing_img_mdl = False
        used_final_missing_ipl_neighbor = False
        ipl_model_source_for_row = None
        source_model_id_for_row = -1
        final_missing_fit_note = ""
        res_id = int(detail[0])
        ipl_id = int(detail[4])
        sector_index = int(detail[15]) if len(detail) > 15 else -1
        pass_name = str(detail[14]) if len(detail) > 14 else "UNKNOWN"
        row_index = int(detail[19]) if len(detail) > 19 else -1
        resolver_audit_row(detail, "row-start")
        if SKIP_LIGHTS_PASS_IPL_MESH_PLACEMENTS and is_light_placement_pass(pass_name):
            try:
                skipped_lights_pass_ipl_rows.append((sector_index, row_index, ipl_id, res_id, pass_name, int(detail[1]), int(detail[2])))
            except Exception:
                skipped_lights_pass_ipl_rows.append((sector_index, row_index, ipl_id, res_id, pass_name, 0, 0))
            continue
        previous_missing_keys = globals().get("_PREVIOUS_MISSING_ROW_KEYS", set()) or set()
        was_missing_in_previous_import = (
            int(sector_index),
            int(row_index),
            int(ipl_id),
            int(res_id),
            str(pass_name),
        ) in previous_missing_keys
        row_model_id_for_lookup = int(ipl_id)
        use_row_model_id_for_lookup = bool(
            ENABLE_ROW_MODEL_ID_AUTHORITATIVE_PLACEMENT
            and row_model_id_for_lookup >= 0
            and (not ROW_MODEL_ID_AUTHORITATIVE_SKIP_LIGHTS or not is_light_placement_pass(pass_name))
        )
        primary_model_id = int(res_id)

        def lookup_primary_placement_model(model_id: int):
            model_id = int(model_id)
            obj = continuation_by_res.get(model_id)
            if obj is not None:
                return obj, "img_continuation_model"
            obj = overlay_by_sector_res.get((sector_index, model_id))
            if obj is not None:
                return obj, "exact_sector_model"
            if row_index >= 0:
                obj = nested_overlay_by_res.get((row_index, model_id))
                if obj is not None:
                    return obj, "exact_nested_row_model"
            if row_index >= 0:
                obj = row_overlay_by_res.get((row_index, model_id))
                if obj is not None:
                    return obj, "exact_row_model"
            obj = built_by_res.get(model_id)
            if obj is not None:
                return obj, "lvz_model"
            obj = extra_by_res.get(model_id)
            if obj is not None:
                return obj, "area_model"
            obj = overlay_by_res.get(model_id)
            if obj is not None:
                return obj, "global_sector_model"
            return None, ""

        primary_would_miss = (lookup_primary_placement_model(primary_model_id)[0] is None)
        base_obj, primary_model_source = lookup_primary_placement_model(primary_model_id)
        if base_obj is not None:
            source_model_id_for_row = int(primary_model_id)
            if int(primary_model_id) != int(res_id):
                ipl_model_source_for_row = f"row-model-id-hint-disabled:{primary_model_source}:model={int(primary_model_id)}:visible_res={int(res_id)}"
            if primary_model_source == "exact_nested_row_model":
                fallback_nested += 1
            elif primary_model_source == "exact_row_model":
                fallback_row += 1
            elif primary_model_source == "area_model":
                fallback_extra += 1
            elif primary_model_source in ("global_sector_model", "img_continuation_model"):
                fallback_overlay += 1
        # V72: if the Resource ID side is absent but the row IPL/model id has a
        # real parsed MDL payload, use the real MDL. This matches the WRLD row
        # structure: +0x00 IPL/model id, +0x02 resource id. Do this before any
        # WRLD sparse-fragment fallback so missing rows do not become fake slices.
        if (
            base_obj is None
            and ENABLE_REAL_IPL_FOR_MISSING_RES_ROWS
            and str(pass_name) in REAL_IPL_FOR_MISSING_ALLOWED_PASSES
            and not is_light_placement_pass(pass_name)
        ):
            real_ipl_obj, real_ipl_source, real_ipl_note = find_real_ipl_candidate_for_missing_res(ipl_id, sector_index, row_index)
            if real_ipl_obj is not None:
                base_obj = real_ipl_obj
                used_ipl_model_fallback = True
                used_exact_missing_img_mdl = True
                source_model_id_for_row = int(ipl_id)
                ipl_model_source_for_row = f"real-ipl-for-missing-res:{real_ipl_source}:{real_ipl_note}"
                if len(real_ipl_for_missing_res_rows) < 1024:
                    gv, gf, gr = object_geometry_counts_radius(real_ipl_obj)
                    real_ipl_for_missing_res_rows.append((
                        sector_index, row_index, pass_name, ipl_id, res_id,
                        real_ipl_source, str(getattr(real_ipl_obj, "name", "")),
                        int(gv), int(gf), float(gr), real_ipl_note,
                    ))
                LVZ.dbg(
                    f"[geometry-recovery] RES missing but row IPL/model has real parsed MDL; "
                    f"RES={res_id} IPL={ipl_id} sector={sector_index} row={row_index} pass={pass_name} "
                    f"using={getattr(real_ipl_obj, 'name', '')} source={real_ipl_source}; {real_ipl_note}; "
                    f"ideMap={ide_ipl_to_name.get(int(ipl_id), '')}->{ide_ipl_to_res.get(int(ipl_id), '')}; full row matrix scale"
                )
                resolver_audit_row(
                    detail,
                    "recovered-real-ipl-for-missing-res",
                    chosen_obj=real_ipl_obj,
                    chosen_source=ipl_model_source_for_row,
                    extra_note="RES side had no usable resource; row IPL/model side resolved to real parsed MDL",
                )

        # V53: reference DFF is completely disabled.  Do not search it, parse it,
        # create hidden proof objects, write reference CSVs, or use it for scene geometry.
        if base_obj is None and ENABLE_WRLD_SUBMODEL_GROUP_ID_RECOVERY:
            submodel_obj, submodel_info = lookup_wrld_submodel_group_by_res_id(sector_index, res_id)
            if (
                submodel_obj is not None
                and ENABLE_SKIP_BAD_NONLIGHT_SPARSE_BUILDING_FRAGMENTS
                and str(pass_name) in BAD_NONLIGHT_SPARSE_PASSES
                and not is_light_placement_pass(pass_name)
                and bool(submodel_info.get("sparse_range", False))
            ):
                try:
                    _sv, _sf, _sr = object_geometry_counts_radius(submodel_obj)
                    _raw_sx, _raw_sy, _raw_sz = matrix_basis_column_scales(matrix)
                    _cellish = matrix_has_wrld_cell_scale(matrix)
                    if int(_sv) <= int(BAD_NONLIGHT_SPARSE_MAX_VERTS) and int(_sf) <= int(BAD_NONLIGHT_SPARSE_MAX_FACES) and bool(_cellish):
                        rich_obj, rich_source, rich_note = find_rich_ipl_candidate_over_sparse(ipl_id, sector_index, row_index, int(_sv), int(_sf))
                        if rich_obj is not None:
                            base_obj = rich_obj
                            submodel_obj = None
                            used_ipl_model_fallback = True
                            used_exact_missing_img_mdl = True
                            source_model_id_for_row = int(ipl_id)
                            ipl_model_source_for_row = f"rich-ipl-over-sparse:{rich_source}:{rich_note}"
                            if len(rich_ipl_over_sparse_rows) < 512:
                                rich_ipl_over_sparse_rows.append((
                                    sector_index, row_index, pass_name, ipl_id, res_id,
                                    rich_source, str(getattr(rich_obj, "name", "")), rich_note,
                                    int(_sv), int(_sf),
                                ))
                            LVZ.dbg(
                                f"[geometry-recovery] replacing bad sparse fragment with rich internal IPL model "
                                f"RES={res_id} IPL={ipl_id} sector={sector_index} row={row_index} pass={pass_name} "
                                f"sparse={int(_sv)}v/{int(_sf)}f/r{float(_sr):.3f} "
                                f"replacement={getattr(rich_obj, 'name', '')} source={rich_source}; {rich_note}; "
                                f"REAL PARSED MDL ONLY; using full row matrix scale, not WRLD cell-scale strip"
                            )
                            resolver_audit_row(
                                detail,
                                "recovered-rich-ipl-over-sparse",
                                chosen_obj=rich_obj,
                                chosen_source=ipl_model_source_for_row,
                                extra_note=f"replaced sparse geom={int(_sv)}v/{int(_sf)}f parent={submodel_info.get('parent_res_id', -1)} group={submodel_info.get('group_index', -1)} range_start={submodel_info.get('range_start', -1)}",
                            )
                        else:
                            missing_rows.append((sector_index, row_index, ipl_id, res_id, pass_name, int(detail[1]), int(detail[2])))
                            missing_rows_full.append((sector_index, row_index, ipl_id, res_id, pass_name, int(detail[1]), int(detail[2])))
                            skipped_missing += 1
                            if len(bad_nonlight_sparse_building_rows) < 512:
                                bad_nonlight_sparse_building_rows.append((
                                    sector_index, row_index, pass_name, ipl_id, res_id,
                                    int(submodel_info.get("parent_res_id", -1)),
                                    int(submodel_info.get("group_index", -1)),
                                    int(submodel_info.get("range_start", -1)),
                                    int(_sv), int(_sf), float(_sr),
                                    float(_raw_sx), float(_raw_sy), float(_raw_sz),
                                ))
                            LVZ.dbg(
                                f"[geometry-recovery] NOT importing bad non-LIGHTS sparse building fragment "
                                f"RES={res_id} IPL={ipl_id} sector={sector_index} row={row_index} pass={pass_name} "
                                f"geom={int(_sv)}v/{int(_sf)}f/r{float(_sr):.3f} "
                                f"parent={submodel_info.get('parent_res_id', -1)} group={submodel_info.get('group_index', -1)} "
                                f"range_start={submodel_info.get('range_start', -1)} rawScale={float(_raw_sx):.3f},{float(_raw_sy):.3f},{float(_raw_sz):.3f}; "
                                f"counting as missing; {rich_note}"
                            )
                            resolver_audit_row(
                                detail,
                                "rejected-bad-sparse-building-fragment",
                                chosen_obj=submodel_obj,
                                chosen_source="WRLD_SUBMODEL_GROUP",
                                extra_note=f"geom={int(_sv)}v/{int(_sf)}f parent={submodel_info.get('parent_res_id', -1)} group={submodel_info.get('group_index', -1)} range_start={submodel_info.get('range_start', -1)}; {rich_note}",
                            )
                            continue
                except Exception as exc:
                    try:
                        LVZ.dbg(f"[geometry-recovery] bad sparse fragment guard failed RES={res_id}: {exc}")
                    except Exception:
                        pass
            if submodel_obj is not None:
                base_obj = submodel_obj
                used_exact_missing_img_mdl = True
                prefix = "wrld-submodel-group"
                if bool(submodel_info.get("global_fallback", False)):
                    prefix = "wrld-global-sparse-submodel-id" if bool(submodel_info.get("sparse_range", False)) else "wrld-global-submodel-id"
                elif bool(submodel_info.get("sparse_range", False)):
                    prefix = "wrld-sparse-submodel-range"
                ipl_model_source_for_row = (
                    f"{prefix}:parent={submodel_info.get('parent_res_id', -1)}:"
                    f"group={submodel_info.get('group_index', -1)}:start={submodel_info.get('range_start', -1)}"
                )
                source_model_id_for_row = int(res_id)
                if bool(submodel_info.get("global_fallback", False)):
                    fallback_wrld_global_submodel += 1
                else:
                    fallback_wrld_submodel_group += 1
                if bool(submodel_info.get("sparse_range", False)):
                    try:
                        _sv, _sf, _sr = object_geometry_counts_radius(base_obj)
                        LVZ.dbg(
                            f"[geometry-recovery] importing sparse WRLD submodel fragment "
                            f"RES={res_id} IPL={ipl_id} sector={sector_index} row={row_index} pass={pass_name} "
                            f"geom={int(_sv)}v/{int(_sf)}f/r{float(_sr):.3f} "
                            f"parent={submodel_info.get('parent_res_id', -1)} group={submodel_info.get('group_index', -1)} "
                            f"range_start={submodel_info.get('range_start', -1)} source={ipl_model_source_for_row}"
                        )
                    except Exception:
                        pass
                if len(wrld_submodel_group_rows) < 512:
                    wrld_submodel_group_rows.append((
                        sector_index, row_index, pass_name, ipl_id, res_id,
                        submodel_info.get('parent_res_id', -1), submodel_info.get('group_index', -1),
                        submodel_info.get('range_start', -1), str(getattr(base_obj, 'name', ''))
                    ))
        if base_obj is None and ENABLE_FINAL_VERIFIED_RENDER_PAIR_ALIASES:
            alias_obj, alias_res_id, alias_source = lookup_verified_render_pair_alias_base(
                ipl_id,
                res_id,
                sector_index,
                row_index,
                overlay_by_sector_res,
                nested_overlay_by_res,
                row_overlay_by_res,
                built_by_res,
                extra_by_res,
                overlay_by_res,
                ipl_overlay_by_sector_res,
                ipl_nested_overlay_by_res,
                ipl_row_overlay_by_res,
                ipl_extra_by_res,
                ipl_overlay_by_res,
            )
            if alias_obj is not None:
                base_obj = alias_obj
                used_exact_missing_img_mdl = True
                source_model_id_for_row = int(alias_res_id)
                ipl_model_source_for_row = (
                    f"wrld-verified-render-pair:pair={int(ipl_id)}:{int(res_id)}:"
                    f"render={int(alias_res_id)}:source={alias_source}"
                )
                fallback_verified_render_pair += 1
                if len(verified_render_pair_rows) < 128:
                    verified_render_pair_rows.append((
                        sector_index, row_index, pass_name, ipl_id, res_id, alias_res_id, alias_source,
                        str(getattr(base_obj, "name", ""))
                    ))

        if base_obj is None and ENABLE_IPL_MODEL_ID_FALLBACK:
            # Disabled for V20. The first u16 in these rows is not a safe model-resource id
            # for Stories WRLD import. It behaves like a placement/IDE remap id, while the
            # second u16 is the resource name/id visible in converted IPLs such as beach3457.
            # Using this as a fallback was the source of the wrong black slabs and fake fills.
            model_id = int(ipl_id)
            model_source = None
            base_obj = ipl_overlay_by_sector_res.get((sector_index, model_id))
            if base_obj is not None:
                model_source = "sector-ipl"
            if base_obj is None:
                base_obj = ipl_overlay_by_res.get(model_id)
                if base_obj is not None:
                    model_source = "global-sector-ipl"
            if base_obj is None and row_index >= 0:
                base_obj = ipl_nested_overlay_by_res.get((row_index, model_id))
                if base_obj is not None:
                    model_source = "nested-ipl"
            if base_obj is None and row_index >= 0:
                base_obj = ipl_row_overlay_by_res.get((row_index, model_id))
                if base_obj is not None:
                    model_source = "row-ipl"
            if base_obj is None:
                base_obj = built_by_res.get(model_id)
                if base_obj is not None:
                    model_source = "lvz-ipl"
            if base_obj is None:
                base_obj = ipl_extra_by_res.get(model_id)
                if base_obj is not None:
                    model_source = "area-ipl"
            if base_obj is None:
                base_obj = ipl_overlay_by_res.get(model_id)
                if base_obj is not None:
                    model_source = "same-resource-ipl"

            if base_obj is not None:
                fits, fit_note = ipl_fallback_fits_detail(detail, base_obj)
                if not fits:
                    if len(ipl_rejected_rows) < IPL_FALLBACK_REJECT_LOG_LIMIT:
                        ipl_rejected_rows.append((sector_index, row_index, pass_name, ipl_id, res_id, model_source, fit_note))
                    base_obj = None
                else:
                    used_ipl_model_fallback = True
                    ipl_model_source_for_row = model_source
                    fallback_ipl += 1
                    if len(ipl_fallback_rows) < 128:
                        ipl_fallback_rows.append((sector_index, row_index, pass_name, ipl_id, res_id, model_source, fit_note))

        if base_obj is None:
            base_obj, aggregate_info = lookup_aggregate_piece_base(detail, sector_index)
            if base_obj is not None:
                fallback_aggregate += 1
                if len(aggregate_piece_rows) < AGGREGATE_PIECE_LOG_LIMIT:
                    dist, agg_radius = aggregate_info or (0.0, 0.0)
                    aggregate_piece_rows.append((
                        sector_index,
                        row_index,
                        ipl_id,
                        res_id,
                        pass_name,
                        int(base_obj.get("blds_parent_res_index", -1)),
                        int(base_obj.get("blds_group_index", -1)),
                        float(dist),
                        float(agg_radius),
                    ))
        if base_obj is None and ENABLE_NEIGHBOR_ALIAS_FALLBACK:
            base_obj, alias_res_id, alias_source, alias_delta, alias_rejected = lookup_neighbor_alias_base(
                res_id,
                sector_index,
                row_index,
                detail,
                overlay_by_sector_res,
                nested_overlay_by_res,
                row_overlay_by_res,
                built_by_res,
                extra_by_res,
                overlay_by_res,
            )
            if base_obj is not None:
                fallback_neighbor += 1
                if len(neighbor_alias_rows) < NEIGHBOR_ALIAS_LOG_LIMIT:
                    neighbor_alias_rows.append((sector_index, row_index, ipl_id, res_id, alias_res_id, alias_source, alias_delta, pass_name, "accepted"))
            elif alias_rejected:
                if len(neighbor_alias_rows) < NEIGHBOR_ALIAS_LOG_LIMIT:
                    neighbor_alias_rows.extend(alias_rejected[:max(0, NEIGHBOR_ALIAS_LOG_LIMIT - len(neighbor_alias_rows))])

        if base_obj is None and ENABLE_EXACT_IPL_RECOVERY_FOR_MISSING_ROWS:
            forced_obj, forced_source = lookup_any_ipl_model_candidate(ipl_id, sector_index, row_index)
            if forced_obj is not None:
                base_obj = forced_obj
                source_model_id_for_row = int(ipl_id)
                used_ipl_model_fallback = True
                used_exact_missing_img_mdl = True
                ipl_model_source_for_row = f"exact-missing-img-mdl:{forced_source or 'unknown'}"
                fallback_force_missing_img_mdl += 1
                if len(forced_missing_img_mdl_rows) < FORCE_IMPORT_MISSING_IMG_MDL_LOG_LIMIT:
                    forced_missing_img_mdl_rows.append((
                        sector_index, row_index, pass_name, ipl_id, res_id,
                        forced_source or "unknown", str(getattr(forced_obj, "name", ""))
                    ))

        if base_obj is None:
            skipped_missing += 1
            missing_tuple = (sector_index, row_index, ipl_id, res_id, pass_name, int(detail[1]), int(detail[2]))
            missing_rows_full.append(missing_tuple)
            if len(missing_rows) < 128:
                missing_rows.append(missing_tuple)
            continue

        base_id = id(base_obj)
        instance_index = object_use_count.get(base_id, 0)
        matrix = matrix_from_img_detail(detail)
        if ENABLE_VISIBLE_PLACEMENT_DEDUPLICATION:
            try:
                # V44: dedupe/overlap filtering must apply to every visible
                # placement row, not only recovered missing/submodel rows.  The
                # broken Beach4977.### wall came from direct MDL rows repeated
                # across sector containers with the same visible transform, plus
                # AREA/IMG-continuation shifted copies when a normal positive-sector
                # copy already exists for the same model/pass.
                should_dedupe_this_row = True
                pair_key = (int(ipl_id), int(res_id), str(pass_name))
                skip_reason = ""
                if ENABLE_SKIP_AREA_CONTINUATION_DUPLICATE_SUBMODELS and int(sector_index) < 0 and pair_key in positive_sector_pair_keys:
                    skip_reason = "area_continuation_model_duplicate"
                dedupe_key = make_visible_placement_dedupe_key(ipl_id, res_id, pass_name, matrix)
                if not skip_reason and dedupe_key in visible_placement_dedupe_seen:
                    skip_reason = "duplicate_visible_transform"
                if skip_reason:
                    skipped_duplicate_visible_rows.append((sector_index, row_index, pass_name, ipl_id, res_id, str(getattr(base_obj, "name", "")), skip_reason, float(matrix[0][3]), float(matrix[1][3]), float(matrix[2][3]), str(ipl_model_source_for_row or "")))
                    continue
                visible_placement_dedupe_seen.add(dedupe_key)
            except Exception:
                pass
        missing_radius_fit_applied = False
        missing_radius_fit_scale = 1.0
        missing_radius_fit_local_radius = 0.0
        missing_radius_fit_target_radius = 0.0
        missing_radius_fit_world_radius_before = 0.0
        if used_force_missing_img_mdl and FORCE_MISSING_IMG_MDL_CENTER_ON_BBOX:
            # Older forced-missing builds centered the fallback mesh on its source
            # bounding box.  That made final missing pieces collapse into a stuck
            # clump when the mesh was already authored with the correct local
            # offset.  Keep this as an off-by-default escape hatch.
            matrix = matrix_from_img_detail_centered_on_object(detail, base_obj)
        elif used_force_missing_img_mdl or used_final_missing_ipl_neighbor:
            # Final missing rows are often cloned from a nearby IMG MDL whose
            # raw local radius is far smaller than the placement row sphere.
            # The row matrix alone can leave those visible copies tiny.  Fit the
            # row matrix basis upward to the placement radius only for these
            # forced/final-missing imports.
            (
                matrix,
                missing_radius_fit_applied,
                missing_radius_fit_scale,
                missing_radius_fit_local_radius,
                missing_radius_fit_target_radius,
                missing_radius_fit_world_radius_before,
            ) = matrix_from_img_detail_radius_fit_for_object(detail, base_obj)

        use_named_missing_copy = bool(
            CREATE_NAMED_MISSING_MDL_COPIES
            and (was_missing_in_previous_import or used_exact_missing_img_mdl or used_force_missing_img_mdl or used_final_missing_ipl_neighbor)
        )
        if source_model_id_for_row < 0:
            try:
                source_model_id_for_row = int(base_obj.get("blds_res_index", res_id))
            except Exception:
                source_model_id_for_row = int(ipl_id if used_ipl_model_fallback else res_id)

        try:
            base_kind_for_matrix = str(base_obj.get("blds_kind", ""))
            base_is_wrld_submodel_group = bool(
                base_kind_for_matrix == "IMG_WRLD_SUBMODEL_GROUP"
                or base_obj.get("blds_submodel_id_recovery", False)
                or base_obj.get("blds_aggregate_piece", False)
            )
            base_is_world_baked_for_matrix = bool(base_obj.get("blds_world_baked", False))
        except Exception:
            base_is_wrld_submodel_group = False
            base_is_world_baked_for_matrix = False
        keep_world_baked_submodel_matrix = bool(base_is_wrld_submodel_group and base_is_world_baked_for_matrix and should_preserve_world_baked_submodel_matrix(base_obj, matrix))

        # V19 speed fix: use the parsed base itself for the first exact
        # placement, then rename/transform/stamp it as a real placed object.
        # Duplicates still get copied.  This avoids creating and later deleting
        # tens of thousands of extra Blender objects, while still preventing
        # raw beach_sec###_res### parser templates from surviving at origin.
        if instance_index == 0:
            obj = base_obj
            used_object_ids.add(base_id)
        else:
            obj = base_obj.copy()
            if obj.data is not base_obj.data:
                obj.data = base_obj.data
            if base_obj.animation_data is not None:
                obj.animation_data_clear()

        if use_named_missing_copy:
            obj.name = make_exact_placement_object_name(import_stem, detail, int(source_model_id_for_row), instance_index, exact_missing=True)
            try:
                obj.data.name = obj.name
            except Exception:
                pass
            try:
                if keep_world_baked_submodel_matrix:
                    obj["blds_world_baked"] = True
                    obj["blds_missing_world_baked_matrix_override"] = False
                    obj["blds_missing_world_baked_matrix_preserved"] = True
                else:
                    obj["blds_world_baked"] = False
                    obj["blds_missing_world_baked_matrix_override"] = True
            except Exception:
                pass
        else:
            obj.name = make_exact_placement_object_name(import_stem, detail, int(source_model_id_for_row if source_model_id_for_row >= 0 else (ipl_id if used_ipl_model_fallback else res_id)), instance_index, exact_missing=False)

        try:
            obj["blds_visible_placement_instance"] = True
            obj["blds_source_base_object_name"] = str(getattr(base_obj, "name", ""))
        except Exception:
            pass

        if instance_index != 0:
            try:
                link_object(obj)
            except Exception:
                bpy.context.collection.objects.link(obj)
            linked += 1

        try:
            obj.hide_viewport = False
            obj.hide_render = False
        except Exception:
            pass

        wrld_submodel_origin_rebased_for_row = False
        wrld_submodel_origin_off_x = 0.0
        wrld_submodel_origin_off_y = 0.0
        wrld_submodel_origin_off_z = 0.0
        wrld_submodel_origin_radius = 0.0
        if (
            base_is_wrld_submodel_group
            and not keep_world_baked_submodel_matrix
            and not used_force_missing_img_mdl
            and not used_final_missing_ipl_neighbor
        ):
            (
                wrld_submodel_origin_rebased_for_row,
                wrld_submodel_origin_off_x,
                wrld_submodel_origin_off_y,
                wrld_submodel_origin_off_z,
                wrld_submodel_origin_radius,
            ) = rebase_wrld_submodel_mesh_origin_to_bbox_center(obj)
            try:
                obj["blds_wrld_submodel_origin_rebased_for_row"] = bool(wrld_submodel_origin_rebased_for_row)
            except Exception:
                pass

        force_row_matrix_for_named_missing = bool((use_named_missing_copy and not keep_world_baked_submodel_matrix) or used_force_missing_img_mdl or used_final_missing_ipl_neighbor)
        wrld_submodel_strip_cell_scale_for_this_row = bool(
            base_is_wrld_submodel_group
            and not keep_world_baked_submodel_matrix
            and not used_force_missing_img_mdl
            and not used_final_missing_ipl_neighbor
            and matrix_has_wrld_cell_scale(matrix)
        )
        matrix_mode_for_row = "row_matrix"
        if wrld_submodel_strip_cell_scale_for_this_row:
            sx, sy, sz = matrix_basis_column_scales(matrix)
            obj.matrix_world = matrix_with_wrld_cell_scale_stripped(matrix)
            obj["blds_wrld_submodel_cell_scale_stripped"] = True
            obj["blds_wrld_submodel_original_matrix_scale"] = f"{sx:.6f},{sy:.6f},{sz:.6f}"
            matrix_mode_for_row = "wrld_submodel_row_matrix_cell_scale_stripped"
            ipl_cell_scale_fixed += 1
            if len(ipl_cell_scale_rows) < int(IPL_FALLBACK_CELL_SCALE_LOG_LIMIT):
                ipl_cell_scale_rows.append((sector_index, row_index, pass_name, ipl_id, res_id, str(ipl_model_source_for_row), sx, sy, sz))
        elif force_row_matrix_for_named_missing:
            # Do not strip scale from forced/final missing MDLs.  These rows need
            # their placement-row scale, and V12 could undo that scale here,
            # leaving the visible Beach*_missingmdl copies tiny.  Recovered WRLD
            # submodel rows are handled above, before this forced-name branch,
            # because their 32/64/128 values are cell scale, not object scale.
            strip_ipl_cell_scale_for_this_row = bool(
                IPL_FALLBACK_STRIP_CELL_SCALE_ENABLED
                and used_ipl_model_fallback
                and not used_force_missing_img_mdl
                and not used_final_missing_ipl_neighbor
                and matrix_has_wrld_cell_scale(matrix)
            )
            if strip_ipl_cell_scale_for_this_row:
                sx, sy, sz = matrix_basis_column_scales(matrix)
                obj.matrix_world = matrix_with_wrld_cell_scale_stripped(matrix)
                obj["blds_ipl_cell_scale_stripped"] = True
                obj["blds_ipl_original_matrix_scale"] = f"{sx:.6f},{sy:.6f},{sz:.6f}"
                matrix_mode_for_row = "row_matrix_cell_scale_stripped"
                ipl_cell_scale_fixed += 1
                if len(ipl_cell_scale_rows) < int(IPL_FALLBACK_CELL_SCALE_LOG_LIMIT):
                    ipl_cell_scale_rows.append((sector_index, row_index, pass_name, ipl_id, res_id, str(ipl_model_source_for_row), sx, sy, sz))
            else:
                obj.matrix_world = matrix
                matrix_mode_for_row = "row_matrix_applied"
            obj["blds_missing_mdl_matrix_forced"] = True
            if used_ipl_model_fallback:
                obj["blds_ipl_alt12_exact_fix"] = True
                if str(ipl_model_source_for_row or "").startswith("rich-ipl-over-sparse:"):
                    obj["blds_rich_ipl_over_sparse_recovery"] = True
                if str(ipl_model_source_for_row or "").startswith("real-ipl-for-missing-res:"):
                    obj["blds_real_ipl_for_missing_res_recovery"] = True
                    try:
                        if int(ipl_id) in ide_ipl_to_res:
                            obj["blds_ide_mapped_resource_id"] = int(ide_ipl_to_res.get(int(ipl_id)))
                            obj["blds_ide_mapped_model_name"] = str(ide_ipl_to_name.get(int(ipl_id), ""))
                    except Exception:
                        pass
                if ipl_model_source_for_row:
                    obj["blds_ipl_model_source"] = str(ipl_model_source_for_row)
        elif bool(obj.get("blds_world_baked", False)):
            obj.matrix_world = Matrix.Identity(4)
            matrix_mode_for_row = "world_baked_identity_preserved"
        elif used_ipl_model_fallback:
            if IPL_FALLBACK_STRIP_CELL_SCALE_ENABLED and matrix_has_wrld_cell_scale(matrix):
                sx, sy, sz = matrix_basis_column_scales(matrix)
                obj.matrix_world = matrix_with_wrld_cell_scale_stripped(matrix)
                obj["blds_ipl_cell_scale_stripped"] = True
                obj["blds_ipl_original_matrix_scale"] = f"{sx:.6f},{sy:.6f},{sz:.6f}"
                matrix_mode_for_row = "row_matrix_cell_scale_stripped"
                ipl_cell_scale_fixed += 1
                if len(ipl_cell_scale_rows) < int(IPL_FALLBACK_CELL_SCALE_LOG_LIMIT):
                    ipl_cell_scale_rows.append((sector_index, row_index, pass_name, ipl_id, res_id, str(ipl_model_source_for_row), sx, sy, sz))
            else:
                obj.matrix_world = matrix
                matrix_mode_for_row = "row_matrix_applied"
            obj["blds_ipl_alt12_exact_fix"] = True
            if ipl_model_source_for_row:
                obj["blds_ipl_model_source"] = str(ipl_model_source_for_row)
        else:
            obj.matrix_world = matrix
            matrix_mode_for_row = "row_matrix_applied"
        try:
            obj["blds_matrix_mode"] = str(matrix_mode_for_row)
        except Exception:
            pass
        try:
            matrix_decision_rows.append({
                "object_name": str(getattr(obj, "name", "")),
                "requested_res_id": int(res_id),
                "ipl_id": int(ipl_id),
                "sector": int(sector_index),
                "row": int(row_index),
                "pass": str(pass_name),
                "source_model_id": int(source_model_id_for_row),
                "fallback_source": str(ipl_model_source_for_row or ""),
                "base_kind": str(base_kind_for_matrix),
                "base_world_baked": bool(base_is_world_baked_for_matrix),
                "base_wrld_submodel_group": bool(base_is_wrld_submodel_group),
                "matrix_mode": str(matrix_mode_for_row),
                "row_tx": float(matrix[0][3]),
                "row_ty": float(matrix[1][3]),
                "row_tz": float(matrix[2][3]),
                "bbox_center": str(obj.get("blds_world_baked_bbox_center", "")),
                "center_to_row_distance": float(obj.get("blds_world_baked_center_to_row_distance", -1.0)),
                "identity_threshold": float(obj.get("blds_world_baked_identity_threshold", -1.0)),
            })
        except Exception:
            pass
        try:
            raw_sx, raw_sy, raw_sz = matrix_basis_column_scales(matrix)
            app_sx, app_sy, app_sz = matrix_basis_column_scales(obj.matrix_world)
            lcx, lcy, lcz, lr = object_bbox_center_radius(obj)
            mw = obj.matrix_world
            wcx = float(mw[0][0]) * float(lcx) + float(mw[0][1]) * float(lcy) + float(mw[0][2]) * float(lcz) + float(mw[0][3])
            wcy = float(mw[1][0]) * float(lcx) + float(mw[1][1]) * float(lcy) + float(mw[1][2]) * float(lcz) + float(mw[1][3])
            wcz = float(mw[2][0]) * float(lcx) + float(mw[2][1]) * float(lcy) + float(mw[2][2]) * float(lcz) + float(mw[2][3])
            tx = float(matrix[0][3])
            ty = float(matrix[1][3])
            tz = float(matrix[2][3])
            dx = wcx - tx
            dy = wcy - ty
            dz = wcz - tz
            dist = (dx * dx + dy * dy + dz * dz) ** 0.5
            if (
                int(res_id) == 1881
                or bool(base_is_wrld_submodel_group)
                or str(matrix_mode_for_row).startswith("wrld_submodel")
                or max(abs(float(raw_sx)), abs(float(raw_sy)), abs(float(raw_sz))) >= float(IPL_FALLBACK_CELL_SCALE_MIN)
            ):
                transform_proof_rows.append({
                    "object_name": str(getattr(obj, "name", "")),
                    "res_id": int(res_id),
                    "ipl_id": int(ipl_id),
                    "sector": int(sector_index),
                    "row": int(row_index),
                    "pass": str(pass_name),
                    "base_kind": str(base_kind_for_matrix),
                    "fallback_source": str(ipl_model_source_for_row or ""),
                    "matrix_mode": str(matrix_mode_for_row),
                    "raw_sx": float(raw_sx), "raw_sy": float(raw_sy), "raw_sz": float(raw_sz),
                    "applied_sx": float(app_sx), "applied_sy": float(app_sy), "applied_sz": float(app_sz),
                    "row_tx": tx, "row_ty": ty, "row_tz": tz,
                    "applied_tx": float(obj.matrix_world[0][3]), "applied_ty": float(obj.matrix_world[1][3]), "applied_tz": float(obj.matrix_world[2][3]),
                    "local_center_x": float(lcx), "local_center_y": float(lcy), "local_center_z": float(lcz), "local_radius": float(lr),
                    "world_center_x": float(wcx), "world_center_y": float(wcy), "world_center_z": float(wcz),
                    "world_center_to_row_distance": float(dist),
                    "wrld_submodel_cell_scale_stripped": bool(obj.get("blds_wrld_submodel_cell_scale_stripped", False)),
                    "wrld_submodel_original_matrix_scale": str(obj.get("blds_wrld_submodel_original_matrix_scale", "")),
                    "wrld_submodel_origin_rebased": bool(obj.get("blds_wrld_submodel_origin_rebased", False)),
                    "wrld_submodel_origin_rebased_for_row": bool(wrld_submodel_origin_rebased_for_row),
                    "wrld_submodel_origin_offset_x": float(wrld_submodel_origin_off_x),
                    "wrld_submodel_origin_offset_y": float(wrld_submodel_origin_off_y),
                    "wrld_submodel_origin_offset_z": float(wrld_submodel_origin_off_z),
                    "wrld_submodel_origin_radius": float(wrld_submodel_origin_radius),
                })
        except Exception:
            pass
        try:
            raw_sx, raw_sy, raw_sz = matrix_basis_column_scales(matrix)
            should_log_object_transform = bool(
                OBJECT_MATRIX_TRANSFORM_LOG_ENABLED
                and (
                    OBJECT_MATRIX_TRANSFORM_LOG_FULL_VISIBLE
                    or int(res_id) in OBJECT_MATRIX_TRANSFORM_LOG_ALWAYS_RES_IDS
                    or bool(base_is_wrld_submodel_group)
                    or str(matrix_mode_for_row).startswith("wrld_submodel")
                    or bool(obj.get("blds_wrld_submodel_cell_scale_stripped", False))
                    or bool(obj.get("blds_wrld_submodel_origin_rebased", False))
                    or max(abs(float(raw_sx)), abs(float(raw_sy)), abs(float(raw_sz))) >= float(IPL_FALLBACK_CELL_SCALE_MIN)
                    or len(object_transform_rows) < int(OBJECT_MATRIX_TRANSFORM_LOG_MAX_GENERIC_ROWS)
                )
            )
            if should_log_object_transform:
                raw_vals = matrix_to_report_values(matrix)
                applied_vals = matrix_to_report_values(obj.matrix_world)
                app_sx, app_sy, app_sz = matrix_basis_column_scales(obj.matrix_world)
                lcx, lcy, lcz, lr = object_bbox_center_radius(obj)
                mw = obj.matrix_world
                wcx = float(mw[0][0]) * float(lcx) + float(mw[0][1]) * float(lcy) + float(mw[0][2]) * float(lcz) + float(mw[0][3])
                wcy = float(mw[1][0]) * float(lcx) + float(mw[1][1]) * float(lcy) + float(mw[1][2]) * float(lcz) + float(mw[1][3])
                wcz = float(mw[2][0]) * float(lcx) + float(mw[2][1]) * float(lcy) + float(mw[2][2]) * float(lcz) + float(mw[2][3])
                tx = float(matrix[0][3])
                ty = float(matrix[1][3])
                tz = float(matrix[2][3])
                dx = wcx - tx
                dy = wcy - ty
                dz = wcz - tz
                if OBJECT_MATRIX_TRANSFORM_LOG_TO_CSV:
                    object_transform_rows.append({
                        "object_name": str(getattr(obj, "name", "")),
                        "res_id": int(res_id),
                        "ipl_id": int(ipl_id),
                        "sector": int(sector_index),
                        "row": int(row_index),
                        "pass": str(pass_name),
                        "source_model_id": int(source_model_id_for_row),
                        "base_name": str(getattr(base_obj, "name", "")),
                        "base_kind": str(base_kind_for_matrix),
                        "fallback_source": str(ipl_model_source_for_row or ""),
                        "matrix_mode": str(matrix_mode_for_row),
                        "raw_sx": float(raw_sx), "raw_sy": float(raw_sy), "raw_sz": float(raw_sz),
                        "applied_sx": float(app_sx), "applied_sy": float(app_sy), "applied_sz": float(app_sz),
                        "row_tx": tx, "row_ty": ty, "row_tz": tz,
                        "applied_tx": float(obj.matrix_world[0][3]), "applied_ty": float(obj.matrix_world[1][3]), "applied_tz": float(obj.matrix_world[2][3]),
                        "local_center_x": float(lcx), "local_center_y": float(lcy), "local_center_z": float(lcz), "local_radius": float(lr),
                        "world_center_x": float(wcx), "world_center_y": float(wcy), "world_center_z": float(wcz),
                        "world_center_to_row_distance": float((dx * dx + dy * dy + dz * dz) ** 0.5),
                        "wrld_submodel_cell_scale_stripped": bool(obj.get("blds_wrld_submodel_cell_scale_stripped", False)),
                        "wrld_submodel_origin_rebased": bool(obj.get("blds_wrld_submodel_origin_rebased", False)),
                        "wrld_submodel_origin_offset": str(obj.get("blds_wrld_submodel_origin_offset", "")),
                        "raw_m00": raw_vals[0], "raw_m01": raw_vals[1], "raw_m02": raw_vals[2], "raw_m03": raw_vals[3],
                        "raw_m10": raw_vals[4], "raw_m11": raw_vals[5], "raw_m12": raw_vals[6], "raw_m13": raw_vals[7],
                        "raw_m20": raw_vals[8], "raw_m21": raw_vals[9], "raw_m22": raw_vals[10], "raw_m23": raw_vals[11],
                        "raw_m30": raw_vals[12], "raw_m31": raw_vals[13], "raw_m32": raw_vals[14], "raw_m33": raw_vals[15],
                        "applied_m00": applied_vals[0], "applied_m01": applied_vals[1], "applied_m02": applied_vals[2], "applied_m03": applied_vals[3],
                        "applied_m10": applied_vals[4], "applied_m11": applied_vals[5], "applied_m12": applied_vals[6], "applied_m13": applied_vals[7],
                        "applied_m20": applied_vals[8], "applied_m21": applied_vals[9], "applied_m22": applied_vals[10], "applied_m23": applied_vals[11],
                        "applied_m30": applied_vals[12], "applied_m31": applied_vals[13], "applied_m32": applied_vals[14], "applied_m33": applied_vals[15],
                    })
                if OBJECT_MATRIX_TRANSFORM_LOG_TO_BLENDER_LOG and object_transform_log_lines < int(OBJECT_MATRIX_TRANSFORM_LOG_BLENDER_MAX_LINES):
                    LVZ.dbg(
                        f"[matrix-log] object={getattr(obj, 'name', '')} RES={int(res_id)} IPL={int(ipl_id)} "
                        f"sector={int(sector_index)} row={int(row_index)} pass={pass_name} mode={matrix_mode_for_row} "
                        f"base={base_kind_for_matrix} src={int(source_model_id_for_row)} fallback={ipl_model_source_for_row or ''} "
                        f"rawScale={float(raw_sx):.6f},{float(raw_sy):.6f},{float(raw_sz):.6f} "
                        f"appliedScale={float(app_sx):.6f},{float(app_sy):.6f},{float(app_sz):.6f} "
                        f"rowT={tx:.6f},{ty:.6f},{tz:.6f} "
                        f"appliedT={float(obj.matrix_world[0][3]):.6f},{float(obj.matrix_world[1][3]):.6f},{float(obj.matrix_world[2][3]):.6f} "
                        f"localCenter={float(lcx):.6f},{float(lcy):.6f},{float(lcz):.6f} "
                        f"worldCenter={float(wcx):.6f},{float(wcy):.6f},{float(wcz):.6f} "
                        f"centerDist={float((dx * dx + dy * dy + dz * dz) ** 0.5):.6f} "
                        f"cellScaleStripped={bool(obj.get('blds_wrld_submodel_cell_scale_stripped', False))} "
                        f"originRebased={bool(obj.get('blds_wrld_submodel_origin_rebased', False))} "
                        f"originOffset={obj.get('blds_wrld_submodel_origin_offset', '')} "
                        f"rawM=[{raw_vals[0]:.6f},{raw_vals[1]:.6f},{raw_vals[2]:.6f},{raw_vals[3]:.6f};"
                        f"{raw_vals[4]:.6f},{raw_vals[5]:.6f},{raw_vals[6]:.6f},{raw_vals[7]:.6f};"
                        f"{raw_vals[8]:.6f},{raw_vals[9]:.6f},{raw_vals[10]:.6f},{raw_vals[11]:.6f};"
                        f"{raw_vals[12]:.6f},{raw_vals[13]:.6f},{raw_vals[14]:.6f},{raw_vals[15]:.6f}] "
                        f"appliedM=[{applied_vals[0]:.6f},{applied_vals[1]:.6f},{applied_vals[2]:.6f},{applied_vals[3]:.6f};"
                        f"{applied_vals[4]:.6f},{applied_vals[5]:.6f},{applied_vals[6]:.6f},{applied_vals[7]:.6f};"
                        f"{applied_vals[8]:.6f},{applied_vals[9]:.6f},{applied_vals[10]:.6f},{applied_vals[11]:.6f};"
                        f"{applied_vals[12]:.6f},{applied_vals[13]:.6f},{applied_vals[14]:.6f},{applied_vals[15]:.6f}]"
                    )
                    object_transform_log_lines += 1
        except Exception:
            pass
        try:
            if GEOMETRY_OBJECT_LOG_ENABLED and geometry_object_log_lines < int(GEOMETRY_OBJECT_LOG_MAX_LINES):
                gv, gf, gr = object_geometry_counts_radius(obj)
                raw_sx_g, raw_sy_g, raw_sz_g = matrix_basis_column_scales(matrix)
                applied_sx_g, applied_sy_g, applied_sz_g = matrix_basis_column_scales(obj.matrix_world)
                try:
                    lcx_g, lcy_g, lcz_g, lr_g = object_bbox_center_radius(obj)
                except Exception:
                    lcx_g, lcy_g, lcz_g, lr_g = (0.0, 0.0, 0.0, 0.0)
                should_log_geometry = bool(
                    int(res_id) in GEOMETRY_OBJECT_LOG_ALWAYS_RES_IDS
                    or bool(base_is_wrld_submodel_group)
                    or bool(used_exact_missing_img_mdl)
                    or bool(used_ipl_model_fallback)
                    or bool(obj.get("blds_wrld_submodel_cell_scale_stripped", False))
                    or bool(obj.get("blds_wrld_submodel_origin_rebased", False))
                    or geometry_object_log_lines < 256
                )
                if should_log_geometry:
                    try:
                        base_res_for_log = int(base_obj.get("blds_res_index", -1))
                    except Exception:
                        base_res_for_log = -1
                    try:
                        parent_res_for_log = int(base_obj.get("blds_parent_res_index", -1))
                    except Exception:
                        parent_res_for_log = -1
                    try:
                        group_for_log = int(base_obj.get("blds_group_index", -1))
                    except Exception:
                        group_for_log = -1
                    LVZ.dbg(
                        f"[geometry-log] object={getattr(obj, 'name', '')} RES={int(res_id)} IPL={int(ipl_id)} "
                        f"sector={int(sector_index)} row={int(row_index)} pass={pass_name} "
                        f"base={base_kind_for_matrix} baseRes={base_res_for_log} parentRes={parent_res_for_log} group={group_for_log} "
                        f"source={ipl_model_source_for_row or ''} mode={matrix_mode_for_row} "
                        f"geom={int(gv)}v/{int(gf)}f radius={float(gr):.6f} "
                        f"localCenter={float(lcx_g):.6f},{float(lcy_g):.6f},{float(lcz_g):.6f} "
                        f"bboxMin={format_blds_vec(obj.get('blds_bbox_min', ''))} bboxMax={format_blds_vec(obj.get('blds_bbox_max', ''))} "
                        f"rawScale={float(raw_sx_g):.6f},{float(raw_sy_g):.6f},{float(raw_sz_g):.6f} "
                        f"appliedScale={float(applied_sx_g):.6f},{float(applied_sy_g):.6f},{float(applied_sz_g):.6f} "
                        f"cellScaleStripped={bool(obj.get('blds_wrld_submodel_cell_scale_stripped', False))} "
                        f"originRebased={bool(obj.get('blds_wrld_submodel_origin_rebased', False))} "
                        f"originOffset={obj.get('blds_wrld_submodel_origin_offset', '')}"
                    )
                    geometry_object_log_lines += 1
        except Exception:
            pass

        resolver_audit_row(detail, "chosen-final", chosen_obj=obj, chosen_source=str(ipl_model_source_for_row or base_kind_for_matrix), extra_note=f"matrix_mode={matrix_mode_for_row}")
        if used_force_missing_img_mdl:
            try:
                obj["blds_missing_mdl_imported"] = True
                obj["blds_missing_requested_res_id"] = int(res_id)
                obj["blds_missing_requested_ipl_id"] = int(ipl_id)
                obj["blds_missing_source_model_id"] = int(source_model_id_for_row)
                obj["blds_missing_nearby_clone"] = bool(used_final_missing_ipl_neighbor)
                obj["blds_missing_fallback_source"] = str(ipl_model_source_for_row or "")
                obj["blds_missing_radius_fit_applied"] = bool(missing_radius_fit_applied)
                obj["blds_missing_radius_fit_scale"] = float(missing_radius_fit_scale)
                obj["blds_missing_local_radius"] = float(missing_radius_fit_local_radius)
                obj["blds_missing_target_radius"] = float(missing_radius_fit_target_radius)
                obj["blds_missing_world_radius_before_fit"] = float(missing_radius_fit_world_radius_before)
            except Exception:
                pass
        if instance_index == 0 or IMPORT_STAMP_DUPLICATE_IMG_PROPS:
            stamp_img_detail_on_object(obj, detail, instance_index)
        if was_missing_in_previous_import or used_exact_missing_img_mdl or used_force_missing_img_mdl or used_final_missing_ipl_neighbor:
            matrix_values = matrix_to_report_values(obj.matrix_world)
            imported_missing_mdl_rows.append({
                "requested_res_id": int(res_id),
                "ipl_id": int(ipl_id),
                "source_model_id": int(source_model_id_for_row),
                "sector": int(sector_index),
                "row": int(row_index),
                "pass": str(pass_name),
                "container": int(detail[1]),
                "rel_off": int(detail[2]),
                "object_name": str(getattr(obj, "name", "")),
                "base_name": str(getattr(base_obj, "name", "")),
                "base_kind": str(base_obj.get("blds_kind", "")) if hasattr(base_obj, "get") else "",
                "base_res_id": int(base_obj.get("blds_res_index", -1)) if hasattr(base_obj, "get") else -1,
                "fallback_source": str(ipl_model_source_for_row or ("exact-missing-img-mdl" if used_exact_missing_img_mdl else ("forced-missing-img-mdl" if used_force_missing_img_mdl else "non-ipl-fallback"))),
                "forced": bool(used_force_missing_img_mdl),
                "exact_recovery": bool(used_exact_missing_img_mdl),
                "nearby_ipl_neighbor": bool(used_final_missing_ipl_neighbor),
                "was_missing_in_previous_import": bool(was_missing_in_previous_import),
                "fit_note": str(final_missing_fit_note or ""),
                "matrix_mode": str(matrix_mode_for_row),
                "bbox_center": str(obj.get("blds_world_baked_bbox_center", "")),
                "center_to_row_distance": float(obj.get("blds_world_baked_center_to_row_distance", -1.0)),
                "identity_threshold": float(obj.get("blds_world_baked_identity_threshold", -1.0)),
                "radius_fit_applied": bool(missing_radius_fit_applied),
                "radius_fit_scale": float(missing_radius_fit_scale),
                "local_radius": float(missing_radius_fit_local_radius),
                "target_radius": float(missing_radius_fit_target_radius),
                "world_radius_before_fit": float(missing_radius_fit_world_radius_before),
                "matrix_m00": matrix_values[0], "matrix_m01": matrix_values[1], "matrix_m02": matrix_values[2], "matrix_m03": matrix_values[3],
                "matrix_m10": matrix_values[4], "matrix_m11": matrix_values[5], "matrix_m12": matrix_values[6], "matrix_m13": matrix_values[7],
                "matrix_m20": matrix_values[8], "matrix_m21": matrix_values[9], "matrix_m22": matrix_values[10], "matrix_m23": matrix_values[11],
                "matrix_m30": matrix_values[12], "matrix_m31": matrix_values[13], "matrix_m32": matrix_values[14], "matrix_m33": matrix_values[15],
            })
            imported_missing_family_map.setdefault(int(res_id), []).append({
                "ipl_id": int(ipl_id),
                "base_obj": base_obj,
                "obj": obj,
                "source": str(ipl_model_source_for_row or ""),
            })
        object_use_count[base_id] = instance_index + 1
        # Do not preserve raw parser bases.  The visible placed object is the
        # copy linked above, so the base belongs in the cleanup list.
        applied += 1

        if IMPORT_APPLY_PROGRESS_EVERY > 0 and (applied % IMPORT_APPLY_PROGRESS_EVERY) == 0:
            LVZ.dbg(f"[apply-progress] placed={applied}/{total_details} linked={linked} missing={skipped_missing}")
            if LVZ.DEBUG is not None:
                LVZ.DEBUG.flush()

        if instance_index == 0:
            if apply_log_count < 128:
                LVZ.dbg(
                    f"[apply] RES={res_id} sector={sector_index} pass={pass_name} IPL={ipl_id} "
                    f"→ object '{obj.name}' matrix_world set."
                )
                apply_log_count += 1
            else:
                apply_log_suppressed += 1

    base_candidates = (
        list(built_by_res.values())
        + list(overlay_by_sector_res.values())
        + list(row_overlay_by_res.values())
        + list(nested_overlay_by_res.values())
        + list(extra_resource_objects)
        + list(ipl_overlay_by_sector_res.values())
        + list(ipl_row_overlay_by_res.values())
        + list(ipl_nested_overlay_by_res.values())
        + list(ipl_extra_resource_objects)
        + all_aggregate_group_parts()
    )
    LVZ.dbg(f"[apply-progress] finished placement loop; raw parser bases queued for {RAW_PARSER_BASE_CLEANUP_MODE}={len(base_candidates)}")
    if LVZ.DEBUG is not None:
        LVZ.DEBUG.flush()
    removed = remove_unplaced_base_objects(base_candidates, used_object_ids)
    if IMPORT_DEFER_BASE_VISIBILITY_DURING_APPLY and placed_objects_to_reveal:
        for reveal_obj in placed_objects_to_reveal:
            set_object_view_hidden(reveal_obj, False)
    if hidden_duplicate_collection is not None:
        if hidden_duplicate_collection_was_hidden is None:
            set_collection_view_hidden(hidden_duplicate_collection, False)
        else:
            set_collection_view_hidden(hidden_duplicate_collection, hidden_duplicate_collection_was_hidden)
    if apply_log_suppressed:
        LVZ.dbg(f"[apply] matrix_world log lines suppressed: {apply_log_suppressed}")
    LVZ.dbg(f"[apply] global IPL/model best-candidate replacements: sector={ipl_overlay_choice_replacements} area={ipl_extra_choice_replacements}")
    LVZ.dbg(f"[resolver] audit lines printed: {resolver_audit_lines} / max={int(RESOLVER_AUDIT_MAX_ROWS)}")
    LVZ.dbg(f"[apply] skipped missing mesh/resource rows: {skipped_missing}")
    LVZ.dbg(f"[apply] reused nested-child resource fallback rows: {fallback_nested}")
    LVZ.dbg(f"[apply] reused IPL/model-id fallback rows (disabled in V20): {fallback_ipl} (rejected={len(ipl_rejected_rows)})")
    LVZ.dbg(f"[apply] IPL/model fallback cell-scale strips: {ipl_cell_scale_fixed}")
    for sector_index, row_index, pass_name, ipl_id, res_id, model_source, sx, sy, sz in ipl_cell_scale_rows:
        LVZ.dbg(
            f"[apply] IPL-CELL-SCALE-STRIP sector={sector_index} row={row_index} pass={pass_name} "
            f"IPL={ipl_id} RES={res_id} via {model_source} old_scale={sx:.3f},{sy:.3f},{sz:.3f}"
        )
    LVZ.dbg(f"[apply] reused aggregate-origin IPL group-piece fallback rows: {fallback_aggregate}")
    LVZ.dbg(f"[apply] skipped LIGHTS-pass IPL mesh rows: {len(skipped_lights_pass_ipl_rows)}")
    if skipped_lights_pass_ipl_rows:
        for sector_index, row_index, ipl_id, res_id, pass_name, cont, rel_off in skipped_lights_pass_ipl_rows[:96]:
            LVZ.dbg(f"  LIGHTS-SKIP sector={sector_index} row={row_index} IPL={ipl_id} RES={res_id} cont=0x{int(cont):08X} rel=0x{int(rel_off):08X}")
    _real_ipl_for_missing_res_rows_safe = locals().get("real_ipl_for_missing_res_rows", [])
    if _real_ipl_for_missing_res_rows_safe:
        LVZ.dbg(f"[geometry-recovery] real IPL/model recoveries for missing RES rows: {len(_real_ipl_for_missing_res_rows_safe)}")
        for _r in _real_ipl_for_missing_res_rows_safe[:160]:
            LVZ.dbg(
                f"[geometry-recovery] real-ipl-missing-res sector={_r[0]} row={_r[1]} pass={_r[2]} IPL={_r[3]} RES={_r[4]} "
                f"source={_r[5]} object={_r[6]} geom={_r[7]}v/{_r[8]}f/r{_r[9]:.3f} note={_r[10]}"
            )
    _rich_ipl_over_sparse_rows_safe = locals().get("rich_ipl_over_sparse_rows", [])
    if _rich_ipl_over_sparse_rows_safe:
        LVZ.dbg(f"[geometry-recovery] rich internal IPL-over-sparse recoveries: {len(_rich_ipl_over_sparse_rows_safe)}")
        for _r in _rich_ipl_over_sparse_rows_safe[:128]:
            LVZ.dbg(
                f"[geometry-recovery] rich-over-sparse sector={_r[0]} row={_r[1]} pass={_r[2]} IPL={_r[3]} RES={_r[4]} "
                f"source={_r[5]} object={_r[6]} sparse={_r[8]}v/{_r[9]}f note={_r[7]}"
            )
    if bad_nonlight_sparse_building_rows:
        LVZ.dbg(f"[geometry-recovery] bad non-LIGHTS sparse building fragments suppressed: {len(bad_nonlight_sparse_building_rows)}")
        for _r in bad_nonlight_sparse_building_rows[:128]:
            LVZ.dbg(
                f"[geometry-recovery] suppressed-fragment sector={_r[0]} row={_r[1]} pass={_r[2]} IPL={_r[3]} RES={_r[4]} "
                f"parent={_r[5]} group={_r[6]} range_start={_r[7]} geom={_r[8]}v/{_r[9]}f/r{_r[10]:.3f} "
                f"rawScale={_r[11]:.3f},{_r[12]:.3f},{_r[13]:.3f}"
            )
    LVZ.dbg(f"[apply] recovered WRLD submodel aggregate group rows: {fallback_wrld_submodel_group}")
    LVZ.dbg(f"[apply] recovered WRLD global exact submodel-id rows: {fallback_wrld_global_submodel}")
    LVZ.dbg(f"[apply] recovered WRLD verified render-pair rows: {fallback_verified_render_pair}")
    if verified_render_pair_rows:
        LVZ.dbg("[apply] WRLD verified render-pair samples:")
        for sector_index, row_index, pass_name, ipl_id, res_id, alias_res_id, alias_source, obj_name in verified_render_pair_rows[:96]:
            LVZ.dbg(f"  sector={sector_index} row={row_index} pass={pass_name} pair={ipl_id}:{res_id} -> render={alias_res_id} source={alias_source} obj={obj_name}")
    if wrld_submodel_group_rows:
        LVZ.dbg("[apply] first WRLD submodel aggregate group recoveries:")
        for sector_index, row_index, pass_name, ipl_id, res_id, parent_res, group_index, range_start, obj_name in wrld_submodel_group_rows[:96]:
            LVZ.dbg(
                f"  SUBMODEL RES={res_id} IPL={ipl_id} sector={sector_index} row={row_index} pass={pass_name} "
                f"-> parent RES={parent_res} group={group_index} range_start={range_start} object={obj_name}"
            )
    LVZ.dbg(f"[apply] reused row-shared resource fallback rows: {fallback_row}")
    LVZ.dbg(f"[apply] reused AREA/direct resource fallback rows: {fallback_extra}")
    LVZ.dbg(f"[apply] reused same-resource overlay fallback rows: {fallback_overlay}")
    LVZ.dbg(f"[apply] reused neighboring resource alias fallback rows: {fallback_neighbor}")
    LVZ.dbg(f"[apply] exact missing IMG MDL IPL/model rows imported (disabled in V20): {fallback_force_missing_img_mdl}")
    LVZ.dbg(f"[apply] final missing nearest IPL/model clone rows imported (disabled in exact-only mode): {fallback_final_missing_ipl_neighbor}")
    if forced_missing_img_mdl_rows:
        LVZ.dbg("[apply] first exact missing IMG MDL imports:")
        for sector_index, row_index, pass_name, ipl_id, res_id, forced_source, obj_name in forced_missing_img_mdl_rows:
            LVZ.dbg(
                f"  EXACT MISSING MDL {res_id} IMPORTED via IPL/model={ipl_id} source={forced_source} "
                f"sector={sector_index} row={row_index} pass={pass_name} object={obj_name}"
            )
    if final_missing_ipl_neighbor_rows:
        LVZ.dbg("[apply] first final-missing nearest IPL/model clone imports:")
        for sector_index, row_index, pass_name, ipl_id, res_id, source_model_id, source, obj_name in final_missing_ipl_neighbor_rows[:64]:
            LVZ.dbg(
                f"  FINAL MISSING MDL {res_id} IMPORTED via nearest IPL/model={source_model_id} "
                f"requested IPL={ipl_id} source={source} sector={sector_index} row={row_index} pass={pass_name} object={obj_name}"
            )
    if imported_missing_mdl_rows:
        try:
            previous_imported_count = sum(1 for row in imported_missing_mdl_rows if bool(row.get("was_missing_in_previous_import", False)))
            nearby_imported_count = sum(1 for row in imported_missing_mdl_rows if bool(row.get("nearby_ipl_neighbor", False)))
            LVZ.dbg(f"[compare] previous missing rows imported this run: {previous_imported_count}")
            LVZ.dbg(f"[compare] final missing nearby IPL/model rows imported this run: {nearby_imported_count}")
        except Exception:
            pass
        LVZ.dbg(f"[apply] imported missing MDL report rows: {len(imported_missing_mdl_rows)}")
        for report_row in imported_missing_mdl_rows[:64]:
            LVZ.dbg(
                f"  MISSING MDL {report_row['requested_res_id']} IMPORTED -> "
                f"{report_row['object_name']} via {report_row['fallback_source']} IPL={report_row['ipl_id']}"
            )
    if ipl_fallback_rows:
        LVZ.dbg("[apply] first IPL/model-id fallback rows:")
        for row in ipl_fallback_rows:
            sector_index, row_index, pass_name, ipl_id, res_id, model_source = row[:6]
            fit_note = row[6] if len(row) > 6 else ""
            LVZ.dbg(
                f"  sector={sector_index} row={row_index} pass={pass_name} "
                f"RES={res_id} -> IPL/model={ipl_id} via {model_source}; {fit_note}"
            )
    if ipl_rejected_rows:
        LVZ.dbg("[apply] first rejected IPL/model-id fallback rows:")
        for sector_index, row_index, pass_name, ipl_id, res_id, model_source, fit_note in ipl_rejected_rows:
            LVZ.dbg(
                f"  REJECT sector={sector_index} row={row_index} pass={pass_name} "
                f"RES={res_id} -> IPL/model={ipl_id} via {model_source}; {fit_note}"
            )
    if aggregate_piece_rows:
        LVZ.dbg("[apply] first aggregate group-piece fallback rows:")
        for sector_index, row_index, ipl_id, res_id, pass_name, parent_res, group_index, dist, agg_radius in aggregate_piece_rows:
            LVZ.dbg(
                f"  sector={sector_index} row={row_index} pass={pass_name} IPL={ipl_id} "
                f"RES={res_id} -> parent RES={parent_res} group={group_index} dist={dist:.3f} group_radius={agg_radius:.3f}"
            )
    if neighbor_alias_rows:
        LVZ.dbg("[apply] first neighboring alias fallback rows:")
        for row in neighbor_alias_rows:
            if len(row) >= 9:
                sector_index, row_index, ipl_id, res_id, alias_res_id, alias_source, alias_delta, pass_name, note = row[:9]
            else:
                sector_index, row_index, ipl_id, res_id, alias_res_id, alias_source, alias_delta, pass_name = row[:8]
                note = ""
            if note == "accepted":
                LVZ.dbg(
                    f"  sector={sector_index} row={row_index} pass={pass_name} IPL={ipl_id} "
                    f"RES={res_id} -> RES={alias_res_id} via {alias_source} delta={alias_delta}"
                )
            else:
                LVZ.dbg(
                    f"  REJECT sector={sector_index} row={row_index} pass={pass_name} IPL={ipl_id} "
                    f"RES={res_id} -> RES={alias_res_id} via {alias_source} delta={alias_delta}; {note}"
                )
    if missing_rows:
        LVZ.dbg("[apply] first missing placement rows:")
        for sector_index, row_index, ipl_id, res_id, pass_name, cont, rel_off in missing_rows:
            LVZ.dbg(
                f"  sector={sector_index} row={row_index} pass={pass_name} IPL={ipl_id} RES={res_id} "
                f"IMG+0x{cont:08X}+0x{rel_off:08X}"
            )
        try:
            from collections import Counter
            res_counts = Counter()
            ipl_counts = Counter()
            for sector_index, row_index, ipl_id, res_id, pass_name, cont, rel_off in missing_rows_full:
                res_counts[int(res_id)] += 1
                ipl_counts[(int(res_id), int(ipl_id))] += 1
            LVZ.dbg("[apply] final missing resource id counts:")
            for rid, count in res_counts.most_common(24):
                sample_ipls = [ipl for (rr, ipl), c in ipl_counts.items() if rr == rid][:12]
                LVZ.dbg(f"  RES={rid} count={count} sample_ipls={sample_ipls}")
        except Exception as exc:
            LVZ.dbg(f"[apply] missing summary failed: {exc}")
    if skipped_duplicate_visible_rows:
        try:
            from collections import Counter
            reason_counts = Counter(str(r[6]) for r in skipped_duplicate_visible_rows)
            LVZ.dbg(f"[dedupe] skipped duplicate visible recovered placement rows: {len(skipped_duplicate_visible_rows)}")
            for reason, count in reason_counts.most_common():
                LVZ.dbg(f"  {reason}: {count}")
            LVZ.dbg("[dedupe] duplicate recovered placement samples:")
            for sector_index, row_index, pass_name, ipl_id, res_id, base_name, reason, tx, ty, tz, fallback_source in skipped_duplicate_visible_rows[:128]:
                LVZ.dbg(
                    f"  SKIP_DUP reason={reason} object=Beach{int(res_id)} sector={sector_index} row={row_index} pass={pass_name} "
                    f"IPL={ipl_id} RES={res_id} tx={tx:.6f} ty={ty:.6f} tz={tz:.6f} base={base_name} fallback={fallback_source}"
                )
        except Exception as exc:
            LVZ.dbg(f"[dedupe] duplicate visible recovered placement summary failed: {exc}")
        try:
            import csv
            out_csv = None
            src_path = globals().get("_CURRENT_IMPORT_LVZ_PATH", "")
            if DIAGNOSTIC_CSV_LOGS_ENABLED and src_path:
                out_csv = str(Path(src_path).with_suffix("")) + "_blds_skipped_duplicate_visible_rows.csv"
            if out_csv:
                with open(out_csv, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(["sector", "row", "pass", "ipl_id", "res_id", "object_name", "reason", "matrix_tx", "matrix_ty", "matrix_tz", "fallback_source"])
                    for sector_index, row_index, pass_name, ipl_id, res_id, base_name, reason, tx, ty, tz, fallback_source in skipped_duplicate_visible_rows:
                        w.writerow([sector_index, row_index, pass_name, ipl_id, res_id, f"Beach{int(res_id)}", reason, tx, ty, tz, fallback_source])
                LVZ.dbg(f"[dedupe] wrote skipped duplicate visible rows CSV: {out_csv}")
        except Exception as exc:
            LVZ.dbg(f"[dedupe] skipped duplicate visible rows CSV failed: {exc}")
    if matrix_decision_rows:
        try:
            from collections import Counter
            mode_counts = Counter(str(r.get("matrix_mode", "")) for r in matrix_decision_rows)
            LVZ.dbg("[matrix] placement matrix mode counts:")
            for mode, count in mode_counts.most_common():
                LVZ.dbg(f"  {mode}: {count}")
            LVZ.dbg("[matrix] row-matrix-applied samples:")
            shown = 0
            for r in matrix_decision_rows:
                if not str(r.get("matrix_mode", "")).startswith("row_matrix"):
                    continue
                if shown >= 128:
                    break
                LVZ.dbg(
                    f"  ROW_MATRIX object={r.get('object_name','')} sector={r.get('sector')} row={r.get('row')} pass={r.get('pass')} "
                    f"IPL={r.get('ipl_id')} RES={r.get('requested_res_id')} src={r.get('source_model_id')} "
                    f"tx={float(r.get('row_tx',0.0)):.6f} ty={float(r.get('row_ty',0.0)):.6f} tz={float(r.get('row_tz',0.0)):.6f} "
                    f"base={r.get('base_kind','')} dist={float(r.get('center_to_row_distance',-1.0)):.3f} threshold={float(r.get('identity_threshold',-1.0)):.3f} "
                    f"fallback={r.get('fallback_source','')}"
                )
                shown += 1
        except Exception as exc:
            LVZ.dbg(f"[matrix] placement matrix decision summary failed: {exc}")
        try:
            import csv
            out_csv = None
            src_path = globals().get("_CURRENT_IMPORT_LVZ_PATH", "")
            if DIAGNOSTIC_CSV_LOGS_ENABLED and IMPORT_WRITE_DEBUG_CSVS and src_path:
                out_csv = str(Path(src_path).with_suffix("")) + "_blds_matrix_decisions.csv"
            if out_csv:
                with open(out_csv, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow([
                        "object_name", "sector", "row", "pass", "ipl_id", "res_id", "source_model_id",
                        "matrix_mode", "base_kind", "base_world_baked", "base_wrld_submodel_group",
                        "row_tx", "row_ty", "row_tz", "bbox_center", "center_to_row_distance", "identity_threshold",
                        "fallback_source"
                    ])
                    for r in matrix_decision_rows:
                        w.writerow([
                            r.get("object_name", ""), r.get("sector", -1), r.get("row", -1), r.get("pass", ""),
                            r.get("ipl_id", -1), r.get("requested_res_id", -1), r.get("source_model_id", -1),
                            r.get("matrix_mode", ""), r.get("base_kind", ""), r.get("base_world_baked", False),
                            r.get("base_wrld_submodel_group", False), r.get("row_tx", 0.0), r.get("row_ty", 0.0), r.get("row_tz", 0.0),
                            r.get("bbox_center", ""), r.get("center_to_row_distance", -1.0), r.get("identity_threshold", -1.0),
                            r.get("fallback_source", "")
                        ])
                LVZ.dbg(f"[matrix] wrote placement matrix decision CSV: {out_csv}")
        except Exception as exc:
            LVZ.dbg(f"[matrix] placement matrix decision CSV failed: {exc}")
    if DIAGNOSTIC_CSV_LOGS_ENABLED and transform_proof_rows:
        try:
            import csv
            out_csv = None
            src_path = globals().get("_CURRENT_IMPORT_LVZ_PATH", "")
            if src_path:
                out_csv = str(Path(src_path).with_suffix("")) + "_blds_transform_proof.csv"
            if out_csv:
                from collections import Counter
                proof_counts = Counter(str(r.get("matrix_mode", "")) for r in transform_proof_rows)
                LVZ.dbg("[transform-proof] matrix modes:")
                for mode, count in proof_counts.most_common():
                    LVZ.dbg(f"  {mode}: {count}")
                with open(out_csv, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow([
                        "object_name", "res_id", "ipl_id", "sector", "row", "pass", "base_kind", "fallback_source", "matrix_mode",
                        "raw_sx", "raw_sy", "raw_sz", "applied_sx", "applied_sy", "applied_sz",
                        "row_tx", "row_ty", "row_tz", "applied_tx", "applied_ty", "applied_tz",
                        "local_center_x", "local_center_y", "local_center_z", "local_radius",
                        "world_center_x", "world_center_y", "world_center_z", "world_center_to_row_distance",
                        "wrld_submodel_cell_scale_stripped", "wrld_submodel_original_matrix_scale",
                        "wrld_submodel_origin_rebased", "wrld_submodel_origin_rebased_for_row",
                        "wrld_submodel_origin_offset_x", "wrld_submodel_origin_offset_y", "wrld_submodel_origin_offset_z",
                        "wrld_submodel_origin_radius"
                    ])
                    for r in transform_proof_rows:
                        w.writerow([
                            r.get("object_name", ""), r.get("res_id", -1), r.get("ipl_id", -1), r.get("sector", -1), r.get("row", -1), r.get("pass", ""),
                            r.get("base_kind", ""), r.get("fallback_source", ""), r.get("matrix_mode", ""),
                            r.get("raw_sx", 0.0), r.get("raw_sy", 0.0), r.get("raw_sz", 0.0),
                            r.get("applied_sx", 0.0), r.get("applied_sy", 0.0), r.get("applied_sz", 0.0),
                            r.get("row_tx", 0.0), r.get("row_ty", 0.0), r.get("row_tz", 0.0),
                            r.get("applied_tx", 0.0), r.get("applied_ty", 0.0), r.get("applied_tz", 0.0),
                            r.get("local_center_x", 0.0), r.get("local_center_y", 0.0), r.get("local_center_z", 0.0), r.get("local_radius", 0.0),
                            r.get("world_center_x", 0.0), r.get("world_center_y", 0.0), r.get("world_center_z", 0.0),
                            r.get("world_center_to_row_distance", -1.0),
                            r.get("wrld_submodel_cell_scale_stripped", False), r.get("wrld_submodel_original_matrix_scale", ""),
                            r.get("wrld_submodel_origin_rebased", False), r.get("wrld_submodel_origin_rebased_for_row", False),
                            r.get("wrld_submodel_origin_offset_x", 0.0), r.get("wrld_submodel_origin_offset_y", 0.0),
                            r.get("wrld_submodel_origin_offset_z", 0.0), r.get("wrld_submodel_origin_radius", 0.0)
                        ])
                LVZ.dbg(f"[transform-proof] wrote transform proof CSV: {out_csv}")
        except Exception as exc:
            LVZ.dbg(f"[transform-proof] CSV failed: {exc}")
    if DIAGNOSTIC_CSV_LOGS_ENABLED and OBJECT_MATRIX_TRANSFORM_LOG_TO_CSV and object_transform_rows:
        try:
            import csv
            out_csv = None
            src_path = globals().get("_CURRENT_IMPORT_LVZ_PATH", "")
            if src_path:
                out_csv = str(Path(src_path).with_suffix("")) + "_blds_object_matrices_transforms.csv"
            if out_csv:
                headers = [
                    "object_name", "res_id", "ipl_id", "sector", "row", "pass", "source_model_id",
                    "base_name", "base_kind", "fallback_source", "matrix_mode",
                    "raw_sx", "raw_sy", "raw_sz", "applied_sx", "applied_sy", "applied_sz",
                    "row_tx", "row_ty", "row_tz", "applied_tx", "applied_ty", "applied_tz",
                    "local_center_x", "local_center_y", "local_center_z", "local_radius",
                    "world_center_x", "world_center_y", "world_center_z", "world_center_to_row_distance",
                    "wrld_submodel_cell_scale_stripped", "wrld_submodel_origin_rebased", "wrld_submodel_origin_offset",
                    "raw_m00", "raw_m01", "raw_m02", "raw_m03",
                    "raw_m10", "raw_m11", "raw_m12", "raw_m13",
                    "raw_m20", "raw_m21", "raw_m22", "raw_m23",
                    "raw_m30", "raw_m31", "raw_m32", "raw_m33",
                    "applied_m00", "applied_m01", "applied_m02", "applied_m03",
                    "applied_m10", "applied_m11", "applied_m12", "applied_m13",
                    "applied_m20", "applied_m21", "applied_m22", "applied_m23",
                    "applied_m30", "applied_m31", "applied_m32", "applied_m33",
                ]
                with open(out_csv, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
                    w.writeheader()
                    for r in object_transform_rows:
                        w.writerow(r)
                LVZ.dbg(f"[matrix-log] wrote object matrices/transforms CSV: {out_csv}")
                LVZ.dbg(f"[matrix-log] rows={len(object_transform_rows)} full_visible={bool(OBJECT_MATRIX_TRANSFORM_LOG_FULL_VISIBLE)} max_generic={int(OBJECT_MATRIX_TRANSFORM_LOG_MAX_GENERIC_ROWS)}")
                shown = 0
                for r in object_transform_rows:
                    if int(r.get("res_id", -1)) != 1881 and shown >= 8:
                        continue
                    LVZ.dbg(
                        f"[matrix-log] object={r.get('object_name','')} RES={r.get('res_id')} IPL={r.get('ipl_id')} "
                        f"mode={r.get('matrix_mode','')} rawScale={float(r.get('raw_sx',0.0)):.6f},{float(r.get('raw_sy',0.0)):.6f},{float(r.get('raw_sz',0.0)):.6f} "
                        f"appliedScale={float(r.get('applied_sx',0.0)):.6f},{float(r.get('applied_sy',0.0)):.6f},{float(r.get('applied_sz',0.0)):.6f} "
                        f"rowT={float(r.get('row_tx',0.0)):.6f},{float(r.get('row_ty',0.0)):.6f},{float(r.get('row_tz',0.0)):.6f} "
                        f"appliedT={float(r.get('applied_tx',0.0)):.6f},{float(r.get('applied_ty',0.0)):.6f},{float(r.get('applied_tz',0.0)):.6f} "
                        f"worldCenterDist={float(r.get('world_center_to_row_distance',-1.0)):.6f}"
                    )
                    shown += 1
                    if shown >= 32:
                        break
        except Exception as exc:
            LVZ.dbg(f"[matrix-log] object matrices/transforms CSV failed: {exc}")
    if DIAGNOSTIC_CSV_LOGS_ENABLED and missing_rows_full:
        try:
            import csv
            out_csv = None
            src_path = globals().get("_CURRENT_IMPORT_LVZ_PATH", "")
            if src_path:
                out_csv = str(Path(src_path).with_suffix("")) + "_blds_missing_rows.csv"
            if out_csv:
                with open(out_csv, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(["sector", "row", "ipl_id", "res_id", "pass", "container", "rel_off"] )
                    for sector_index, row_index, ipl_id, res_id, pass_name, cont, rel_off in missing_rows_full:
                        w.writerow([sector_index, row_index, ipl_id, res_id, pass_name, f"0x{cont:08X}", f"0x{rel_off:08X}"])
                LVZ.dbg(f"[apply] wrote missing placement CSV: {out_csv}")
        except Exception as exc:
            LVZ.dbg(f"[apply] missing placement CSV failed: {exc}")
    if DIAGNOSTIC_CSV_LOGS_ENABLED and missing_rows_full:
        try:
            import csv
            out_csv = None
            src_path = globals().get("_CURRENT_IMPORT_LVZ_PATH", "")
            if src_path:
                out_csv = str(Path(src_path).with_suffix("")) + "_blds_exact_unresolved_missing_rows.csv"
            if out_csv:
                with open(out_csv, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(["status", "sector", "row", "ipl_id", "res_id", "pass", "container", "rel_off"])
                    for sector_index, row_index, ipl_id, res_id, pass_name, cont, rel_off in missing_rows_full:
                        w.writerow(["UNRESOLVED EXACT MISSING MDL", sector_index, row_index, ipl_id, res_id, pass_name, f"0x{cont:08X}", f"0x{rel_off:08X}"])
                LVZ.dbg(f"[apply] wrote exact unresolved missing CSV: {out_csv}")
        except Exception as exc:
            LVZ.dbg(f"[apply] exact unresolved missing CSV failed: {exc}")
    if DIAGNOSTIC_CSV_LOGS_ENABLED and imported_missing_mdl_rows:
        try:
            import csv
            out_csv = None
            src_path = globals().get("_CURRENT_IMPORT_LVZ_PATH", "")
            if src_path:
                out_csv = str(Path(src_path).with_suffix("")) + "_blds_imported_missing_mdl_report.csv"
            if out_csv:
                with open(out_csv, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow([
                        "status", "sector", "row", "pass", "missing_res_id", "imported_ipl_model_id",
                        "source_model_id", "fallback_source", "forced", "nearby_ipl_neighbor", "exact_recovery", "was_missing_in_previous_import", "fit_note",
                        "imported_object", "base_object", "base_kind", "base_res_id", "container", "rel_off",
                        "matrix_mode", "matrix_tx", "matrix_ty", "matrix_tz",
                        "bbox_center", "center_to_row_distance", "identity_threshold",
                        "m00", "m01", "m02", "m03", "m10", "m11", "m12", "m13",
                        "m20", "m21", "m22", "m23", "m30", "m31", "m32", "m33"
                    ])
                    for report_row in imported_missing_mdl_rows:
                        matrix_values = [
                            report_row.get("matrix_m00", 0.0), report_row.get("matrix_m01", 0.0), report_row.get("matrix_m02", 0.0), report_row.get("matrix_m03", 0.0),
                            report_row.get("matrix_m10", 0.0), report_row.get("matrix_m11", 0.0), report_row.get("matrix_m12", 0.0), report_row.get("matrix_m13", 0.0),
                            report_row.get("matrix_m20", 0.0), report_row.get("matrix_m21", 0.0), report_row.get("matrix_m22", 0.0), report_row.get("matrix_m23", 0.0),
                            report_row.get("matrix_m30", 0.0), report_row.get("matrix_m31", 0.0), report_row.get("matrix_m32", 0.0), report_row.get("matrix_m33", 0.0),
                        ]
                        w.writerow([
                            "REFERENCE DFF EXACT GEOMETRY IMPORTED" if str(report_row.get("fallback_source", "")).startswith("reference-dff") else ("WRLD VERIFIED RENDER PAIR IMPORTED" if str(report_row.get("fallback_source", "")).startswith("wrld-verified-render-pair") else ("WRLD GLOBAL SPARSE SUBMODEL ID IMPORTED" if str(report_row.get("fallback_source", "")).startswith("wrld-global-sparse-submodel-id") else ("WRLD GLOBAL SUBMODEL ID IMPORTED" if str(report_row.get("fallback_source", "")).startswith("wrld-global-submodel-id") else ("WRLD SPARSE SUBMODEL RANGE IMPORTED" if str(report_row.get("fallback_source", "")).startswith("wrld-sparse-submodel-range") else ("WRLD SUBMODEL GROUP IMPORTED" if str(report_row.get("fallback_source", "")).startswith("wrld-submodel-group") else ("EXACT MISSING MDL IMPORTED" if not report_row.get("nearby_ipl_neighbor", False) else "HEURISTIC MISSING MDL IMPORTED")))))),
                            report_row["sector"],
                            report_row["row"],
                            report_row["pass"],
                            report_row["requested_res_id"],
                            report_row["ipl_id"],
                            report_row.get("source_model_id", report_row["ipl_id"]),
                            report_row["fallback_source"],
                            report_row["forced"],
                            report_row.get("nearby_ipl_neighbor", False),
                            report_row.get("exact_recovery", False),
                            report_row.get("was_missing_in_previous_import", False),
                            report_row.get("fit_note", ""),
                            report_row["object_name"],
                            report_row["base_name"],
                            report_row["base_kind"],
                            report_row["base_res_id"],
                            f"0x{int(report_row['container']):08X}",
                            f"0x{int(report_row['rel_off']):08X}",
                            report_row.get("matrix_mode", ""),
                            matrix_values[3],
                            matrix_values[7],
                            matrix_values[11],
                            report_row.get("bbox_center", ""),
                            report_row.get("center_to_row_distance", -1.0),
                            report_row.get("identity_threshold", -1.0),
                        ] + matrix_values[:16])
                LVZ.dbg(f"[apply] wrote imported missing MDL report CSV: {out_csv}")
        except Exception as exc:
            LVZ.dbg(f"[apply] imported missing MDL report CSV failed: {exc}")
    LVZ.dbg(f"[apply] raw parser base cleanup: mode={RAW_PARSER_BASE_CLEANUP_MODE} touched={removed} (visible placements left alone)")
    return applied, linked, removed


def find_details_missing_primary_resources(built_by_res: Dict[int, bpy.types.Object], details, overlay_by_sector_res: Dict[Tuple[int, int], bpy.types.Object]):
    overlay_by_res = {}
    for (sector_index, res_id), obj in (overlay_by_sector_res or {}).items():
        if obj is None:
            continue
        overlay_by_res.setdefault(int(res_id), obj)

    missing = []
    for detail in details or []:
        try:
            res_id = int(detail[0])
            sector_index = int(detail[15]) if len(detail) > 15 else -1
        except Exception:
            continue
        if overlay_by_sector_res.get((sector_index, res_id)) is not None:
            continue
        if built_by_res.get(res_id) is not None:
            continue
        if overlay_by_res.get(res_id) is not None:
            continue
        missing.append(detail)
    return missing




def blds_safe_u32(data: bytes, off: int, default: int = 0) -> int:
    try:
        if off < 0 or off + 4 > len(data):
            return default
        return struct.unpack_from("<I", data, off)[0]
    except Exception:
        return default


def blds_safe_f32(data: bytes, off: int, default: float = 0.0) -> float:
    try:
        if off < 0 or off + 4 > len(data):
            return default
        value = struct.unpack_from("<f", data, off)[0]
        if value != value or abs(float(value)) > 100000000.0:
            return default
        return float(value)
    except Exception:
        return default


def blds_2dfx_entry_probe(data: bytes, off: int) -> Dict[str, object]:
    raw = data[off:off + 48]
    x = blds_safe_f32(data, off + 0)
    y = blds_safe_f32(data, off + 4)
    z = blds_safe_f32(data, off + 8)
    effect_at_0 = blds_safe_u32(data, off + 0)
    effect_at_12 = blds_safe_u32(data, off + 12)
    plausible_pos = all(abs(v) < 65536.0 for v in (x, y, z))
    plausible_effect = (0 <= int(effect_at_0) <= 64) or (0 <= int(effect_at_12) <= 64)
    return {
        "x": x,
        "y": y,
        "z": z,
        "effect_at_0": int(effect_at_0),
        "effect_at_12": int(effect_at_12),
        "plausible": bool(plausible_pos or plausible_effect),
        "hex16": raw[:16].hex(),
    }


def blds_try_wrld_2dfx_table(data: bytes, logical_base: int, physical_base: int, logical_end: int, source_kind: str, source_name: str, source_index: int) -> Optional[Dict[str, object]]:
    # WRLD docs give +0x328 count and +0x32C pointer relative to the WRLD file.
    # For IMG slave data, BLeeds sector containers point at WRLD+0x20, so logical_base can be cont-0x20
    # while physical_base remains the real byte base used for bounds checks.
    count_off = int(logical_base) + 0x328
    ptr_off = int(logical_base) + 0x32C
    if count_off < 0 or ptr_off < 0 or ptr_off + 4 > len(data):
        return None
    count = blds_safe_u32(data, count_off)
    ptr = blds_safe_u32(data, ptr_off)
    result = {
        "source_kind": source_kind,
        "source_name": source_name,
        "source_index": int(source_index),
        "logical_base": int(logical_base),
        "physical_base": int(physical_base),
        "count_off": int(count_off),
        "ptr_off": int(ptr_off),
        "count": int(count),
        "ptr": int(ptr),
        "table_abs": -1,
        "valid": False,
        "reason": "",
        "sample": [],
    }
    if count == 0 and ptr == 0:
        result["reason"] = "zero"
        return result
    if count > 20000:
        result["reason"] = "count_too_large"
        return result
    if ptr == 0:
        result["reason"] = "null_ptr"
        return result

    table_abs = int(logical_base) + int(ptr)
    result["table_abs"] = int(table_abs)
    table_end = table_abs + int(count) * 48
    bound_end = min(len(data), int(logical_end))
    if table_abs < int(physical_base) or table_end > bound_end:
        result["reason"] = "table_oob"
        return result

    sample = []
    plausible = 0
    for i in range(min(int(count), 8)):
        probe = blds_2dfx_entry_probe(data, table_abs + i * 48)
        sample.append(probe)
        if probe.get("plausible"):
            plausible += 1
    result["sample"] = sample
    # Do not reject just because the entry layout is not fully understood yet; this is a raw table diagnostic.
    result["valid"] = True
    result["reason"] = f"raw_table; plausible_sample={plausible}/{len(sample)}"
    return result


def blds_collect_raw_wrld_2dfx_tables(lvz_reader: LVZ.read_lvz, img_reader: Optional[LVZ.read_img], img_bytes: Optional[bytes], sector_records: List[Dict[str, int]], extra_container_records: List[Dict[str, int]], lvz_path: str) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    lvz_data = lvz_reader.decomp

    master_hit = blds_try_wrld_2dfx_table(lvz_data, 0, 0, len(lvz_data), "LVZ_MASTER", Path(lvz_path).name, 0)
    if master_hit is not None and int(master_hit.get("count", 0)) != 0:
        rows.append(master_hit)

    try:
        groups, _, _ = lvz_reader.parse_slave_groups_and_rescount()
    except Exception:
        groups = []
    for group in groups:
        try:
            total = int(group.total)
            addr = int(group.addr)
            lvz_hit = blds_try_wrld_2dfx_table(lvz_data, addr, addr, min(len(lvz_data), addr + max(total, 0)), "LVZ_GROUP_HEADER", f"sg{int(group.index):03d}", int(group.index))
            if lvz_hit is not None and int(lvz_hit.get("count", 0)) != 0:
                rows.append(lvz_hit)
        except Exception:
            continue

    if img_reader is not None and img_bytes is not None:
        all_records = []
        seen = set()
        for source, records in (("IMG_SECTOR", sector_records or []), ("IMG_EXTRA", extra_container_records or [])):
            for record in records:
                cont = int(record.get("cont", -1))
                header_addr = int(record.get("header_addr", -1))
                key = (source, cont, header_addr)
                if key in seen:
                    continue
                seen.add(key)
                all_records.append((source, record))
        for source, record in all_records:
            try:
                cont = int(record.get("cont", -1))
                file_size = int(record.get("file_size", 0))
                if cont <= 0 or cont >= len(img_bytes) or file_size <= 0:
                    continue
                logical_base = cont - 0x20
                physical_base = cont
                logical_end = min(len(img_bytes), logical_base + file_size)
                index = int(record.get("sector_index", -1))
                name = f"sector={index} xy={int(record.get('sector_x', 0))},{int(record.get('sector_y', 0))} cont=0x{cont:08X}"
                hit = blds_try_wrld_2dfx_table(img_bytes, logical_base, physical_base, logical_end, source, name, index)
                if hit is not None and int(hit.get("count", 0)) != 0:
                    rows.append(hit)
            except Exception:
                continue
    return rows


def blds_count_lights_pass_rows(img_reader: Optional[LVZ.read_img], img_bytes: Optional[bytes], sector_records: List[Dict[str, int]], extra_container_records: List[Dict[str, int]], max_resource_id: int) -> Dict[str, int]:
    stats = {"candidate": 0, "valid": 0, "sector_containers": 0, "extra_containers": 0}
    if img_reader is None or img_bytes is None:
        return stats
    def consume(records, is_extra=False):
        for record in records or []:
            spans = img_reader.extra_container_instance_spans(record) if is_extra else img_reader.sector_instance_spans(record)
            has_lights = False
            for _pass_index, pass_name, start, stop, _ptrs in spans:
                if str(pass_name) != "LIGHTS":
                    continue
                has_lights = True
                off = int(start)
                while off + 0x50 <= int(stop):
                    stats["candidate"] += 1
                    try:
                        if LVZ.looks_like_img_instance_row(img_bytes, off, max_resource_id=max_resource_id):
                            stats["valid"] += 1
                    except Exception:
                        pass
                    off += 0x50
            if has_lights:
                stats["extra_containers" if is_extra else "sector_containers"] += 1
    consume(sector_records or [], False)
    consume(extra_container_records or [], True)
    return stats


def blds_log_raw_2dfx_diagnostics(lvz_reader: LVZ.read_lvz, img_reader: Optional[LVZ.read_img], img_bytes: Optional[bytes], sector_records: List[Dict[str, int]], extra_container_records: List[Dict[str, int]], lvz_path: str, max_resource_id: int):
    try:
        tables = blds_collect_raw_wrld_2dfx_tables(lvz_reader, img_reader, img_bytes, sector_records, extra_container_records, lvz_path)
        lights_stats = blds_count_lights_pass_rows(img_reader, img_bytes, sector_records, extra_container_records, max_resource_id)
        valid_tables = [row for row in tables if bool(row.get("valid"))]
        entry_total = sum(int(row.get("count", 0)) for row in valid_tables)
        LVZ.dbg(f"[2dfx] WRLD raw table scan: candidates={len(tables)} valid_tables={len(valid_tables)} entries={entry_total}")
        LVZ.dbg(
            f"[2dfx] LIGHTS pass rows are NOT treated as 2DFX tables: "
            f"candidate_rows={lights_stats.get('candidate', 0)} valid_instance_like_rows={lights_stats.get('valid', 0)} "
            f"sector_containers={lights_stats.get('sector_containers', 0)} extra_containers={lights_stats.get('extra_containers', 0)}"
        )
        for row in tables[:64]:
            sample = row.get("sample") or []
            sample_text = ""
            if sample:
                p = sample[0]
                sample_text = (
                    f" sample0_xyz=({float(p.get('x', 0.0)):.3f},{float(p.get('y', 0.0)):.3f},{float(p.get('z', 0.0)):.3f})"
                    f" effect0={int(p.get('effect_at_0', 0))} effect12={int(p.get('effect_at_12', 0))} hex16={p.get('hex16', '')}"
                )
            LVZ.dbg(
                f"[2dfx] {row.get('source_kind')} {row.get('source_name')} "
                f"count={int(row.get('count', 0))} ptr=0x{int(row.get('ptr', 0)):08X} "
                f"count@0x{int(row.get('count_off', 0)):08X} ptr@0x{int(row.get('ptr_off', 0)):08X} "
                f"table=0x{int(row.get('table_abs', -1)):08X} valid={bool(row.get('valid'))} reason={row.get('reason', '')}{sample_text}"
            )
        if not DIAGNOSTIC_CSV_LOGS_ENABLED:
            return
        out_csv = str(Path(lvz_path).with_suffix("")) + "_blds_2dfx_tables.csv"
        try:
            import csv
            with open(out_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["source_kind", "source_name", "source_index", "count", "ptr", "count_off", "ptr_off", "table_abs", "valid", "reason", "sample0_x", "sample0_y", "sample0_z", "sample0_effect_at_0", "sample0_effect_at_12", "sample0_hex16"])
                for row in tables:
                    sample = row.get("sample") or []
                    p = sample[0] if sample else {}
                    w.writerow([
                        row.get("source_kind", ""), row.get("source_name", ""), row.get("source_index", ""), int(row.get("count", 0)), f"0x{int(row.get('ptr', 0)):08X}",
                        f"0x{int(row.get('count_off', 0)):08X}", f"0x{int(row.get('ptr_off', 0)):08X}", f"0x{int(row.get('table_abs', -1)):08X}", bool(row.get("valid")), row.get("reason", ""),
                        p.get("x", ""), p.get("y", ""), p.get("z", ""), p.get("effect_at_0", ""), p.get("effect_at_12", ""), p.get("hex16", ""),
                    ])
            LVZ.dbg(f"[2dfx] wrote raw 2DFX table CSV: {out_csv}")
        except Exception as exc:
            LVZ.dbg(f"[2dfx] CSV write failed: {exc}")
    except Exception as exc:
        LVZ.dbg(f"[2dfx] raw table diagnostics failed: {exc}")


def import_lvz_img_archive(operator, context, lvz_path: str, csv_dedup_res_ids: bool = True, apply_img_transforms: bool = True, debug_print: bool = False, write_debug_log: bool = True, import_img_container_mdls: bool = False):
    # LVZ+IMG imports are long and can crash/cancel near the end while debugging.
    # Always leave a live log beside the LVZ so the last useful lines are not lost.
    write_debug_log = True
    if not lvz_path:
        operator.report({'ERROR'}, "No LVZ selected.")
        return {'CANCELLED'}

    progress = LvzImgImportProgress(operator, context).begin("Reading LVZ container")
    progress.update(1, "Reading LVZ container", force=True)

    stem = Path(lvz_path).stem
    globals()["_CURRENT_IMPORT_STEM"] = stem
    log_path = str(Path(lvz_path).with_suffix("")) + "_blds_import.log" if write_debug_log else None
    LVZ.DEBUG = LVZ.DebugOut(debug_print, write_debug_log, log_path)
    LVZ.dbg(f"[log] live import log: {LVZ.DEBUG.file_path if LVZ.DEBUG is not None else log_path}")
    globals()["_CURRENT_IMPORT_LVZ_PATH"] = lvz_path

    # Remove raw parser bases left by earlier test imports before this pass starts.
    # These are source/template meshes such as beach_sec0199_res51 with identity
    # transforms.  They are not real map placements and will otherwise keep showing
    # up in dirty Blender scenes even after the new importer is fixed.
    purge_stale_raw_parser_bases(stem, reason="pre-import")

    previous_missing_keys = set()
    previous_missing_path = str(Path(lvz_path).with_suffix("")) + "_blds_missing_rows.csv"
    try:
        import csv
        if Path(previous_missing_path).exists():
            with open(previous_missing_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        previous_missing_keys.add((
                            int(row.get("sector", -1)),
                            int(row.get("row", -1)),
                            int(row.get("ipl_id", -1)),
                            int(row.get("res_id", -1)),
                            str(row.get("pass", "UNKNOWN")),
                        ))
                    except Exception:
                        continue
        LVZ.dbg(f"[compare] previous missing rows loaded: {len(previous_missing_keys)} from {previous_missing_path}")
    except Exception as exc:
        LVZ.dbg(f"[compare] previous missing row load failed: {exc}")
    globals()["_PREVIOUS_MISSING_ROW_KEYS"] = previous_missing_keys
    reset_aggregate_group_parts()
    REFERENCE_DFF_CACHE.clear()
    REFERENCE_DFF_MISS_CACHE.clear()
    REFERENCE_DFF_STATS_CACHE.clear()
    REFERENCE_DFF_DEBUG_ROWS.clear()
    REFERENCE_DFF_COMPARE_ROWS.clear()
    CONTINUES_IN_IMG_PROOF_CACHE.clear()

    t0 = time.time()
    lvz_bytes_in = Path(lvz_path).read_bytes()
    decomp, was_cmp = LVZ.safe_decompress(lvz_bytes_in)
    progress.update(4, "Decoding LVZ container")

    LVZ.dbg("===== LVZ Walk + IMG Match/Apply =====")
    LVZ.dbg("Patch: LVZ_IMG_CONTINUES_IN_IMG_EXACT_RESOURCE_TABLE_RECOVERY_V97")
    old_global_undo = None
    try:
        global _ACTIVE_IMPORT_UNDO_STATE
        edit_preferences = bpy.context.preferences.edit
        old_global_undo = bool(edit_preferences.use_global_undo)
        _ACTIVE_IMPORT_UNDO_STATE = (edit_preferences, old_global_undo)
        if old_global_undo:
            edit_preferences.use_global_undo = False
            LVZ.dbg("[speed] disabled Blender global undo during LVZ+IMG import")
    except Exception as exc:
        LVZ.dbg(f"[speed] could not disable Blender global undo: {exc}")

    def restore_global_undo():
        nonlocal old_global_undo
        global _ACTIVE_IMPORT_UNDO_STATE
        if old_global_undo is None:
            restore_active_import_undo_state()
            return
        try:
            bpy.context.preferences.edit.use_global_undo = bool(old_global_undo)
            LVZ.dbg("[speed] restored Blender global undo setting")
        except Exception as exc:
            LVZ.dbg(f"[speed] could not restore Blender global undo: {exc}")
        old_global_undo = None
        _ACTIVE_IMPORT_UNDO_STATE = None

    LVZ.dbg("[mode] reference DFF disabled: no Beachx DFF search, no reference geometry override, no reference proof CSV; LVZ+IMG only")
    LVZ.dbg("[mode] V94 LVZ+IMG resource-id import active: row RES/object id is authoritative; EMPTY Resource[] rows are resolved as IMG continuations with raw IMG offsets; converter IDE maps and IPL/model remaps disabled")
    LVZ.dbg("[mode] V21 fix: Master WRLD 12-byte table slot != visible beach#### id; row third-dword aliases are registered as exact MDLs")
    LVZ.dbg("[mode] 2DFX diagnostics: only +0x328/+0x32C WRLD tables are scanned for effects; LIGHTS pass IPL mesh rows are allowed as visible mesh placements")
    LVZ.dbg("[mode] AREA/triggered rows use real pass names and inferred sector origins")
    LVZ.dbg(f"[mode] loose IMG container debug MDLs: {'on' if import_img_container_mdls else 'off'}")
    LVZ.dbg(f"LVZ: {lvz_path}")
    LVZ.dbg(f"[io] LVZ bytes in: {len(lvz_bytes_in)}  decomp: {len(decomp)} ({'compressed' if was_cmp else 'raw'})")
    ide_ipl_to_res = {}
    ide_ipl_to_name = {}
    ide_path_used = None
    if ENABLE_CONVERTER_IDE_OBJECT_ID_MAP:
        ide_ipl_to_res, ide_ipl_to_name, ide_path_used = read_ide_object_id_map_next_to_lvz(lvz_path)
        if ide_path_used:
            LVZ.dbg(f"[ide] converter IDE map loaded: {ide_path_used} entries={len(ide_ipl_to_res)}")
            for _k in sorted(list(ide_ipl_to_res.keys()))[:8]:
                LVZ.dbg(f"[ide] sample id {_k} -> {ide_ipl_to_name.get(_k, '')} / res {ide_ipl_to_res.get(_k)}")
        else:
            LVZ.dbg("[ide] no converter IDE beside LVZ; raw WRLD ids only")
    else:
        LVZ.dbg("[ide] converter IDE map disabled; GTA SA converter .ide names are ignored for LVZ+IMG placement")
    LVZ.dbg("")

    lvz = LVZ.read_lvz(
        decomp_bytes=decomp,
        stem=stem,
        use_swizzle=True,
        debug_print=debug_print,
    )

    progress.update(6, "Parsing LVZ headers")
    try:
        master = lvz.parse_master_header()
        groups_hdr, res_count, _ = lvz.parse_slave_groups_and_rescount()
    except Exception as exc:
        restore_global_undo()
        progress.finish(succeeded=False, message="LVZ header parse failed")
        operator.report({'ERROR'}, f"Failed to parse LVZ: {exc}")
        if LVZ.DEBUG is not None:
            LVZ.DEBUG.flush()
        return {'CANCELLED'}

    progress.update(9, "Reading companion IMG")
    img_bytes, img_name = None, None
    try:
        img_bytes, img_name = read_img_next_to_lvz(lvz_path)
        if img_bytes:
            LVZ.dbg(f"— IMG Read — source: {img_name} bytes={len(img_bytes)}")
        elif img_name:
            LVZ.dbg(f"[img] {img_name}")
        else:
            LVZ.dbg("[img] IMG not found next to LVZ; IMG-based features will be skipped")
    except Exception as exc:
        LVZ.dbg(f"[img] failed to read IMG: {exc}")

    needs_img = any(int(group.cont) not in (0, 0xFFFFFFFF) for group in groups_hdr)
    if img_bytes is None and needs_img:
        operator.report(
            {'WARNING'},
            "This LVZ references companion IMG world data. Missing or unmatched IMG data will leave holes in the imported map."
        )

    img = LVZ.read_img(img_bytes=img_bytes, lvz_bytes=decomp) if img_bytes else None
    platform = detect_lvz_img_platform(lvz, img)
    use_swizzle = platform_uses_ps2_swizzle(platform)
    lvz.use_swizzle = use_swizzle
    LVZ.dbg(f"[platform] auto-detected {platform}; texture swizzle={'PS2' if use_swizzle else 'PSP/no-PS2-swizzle'}")
    LVZ.dbg(f"[img] importing LOD/SUPERLOD passes: {IMPORT_LOD_PASSES_BY_DEFAULT}")
    LVZ.dbg("")

    LVZ.dbg("— Slave Group Table —")
    LVZ.dbg(f"  groups: {len(groups_hdr)}")
    for group in groups_hdr:
        LVZ.dbg(
            f"  [sg {group.index:03d}] LVZ+0x{group.addr:08X} tag='{group.tag}' "
            f"size={group.total} gcnt={group.gcnt} contIMG=0x{group.cont:08X} — {group.note}"
        )
    LVZ.dbg(f"  resource count: {res_count}")
    if img is not None:
        parent_records = img.find_parent_container_records_from_lvz()
        nested_records = img.find_nested_container_records_from_lvz()
        LVZ.dbg(f"  parent IMG container records: {len(parent_records)}")
        LVZ.dbg(f"  nested DLRW preface records: {len(nested_records)} (diagnostic, not used as IMG row roots)")
        LVZ.dbg(f"  unique parent IMG container bases: {len(set(record['cont'] for record in parent_records))}")
    LVZ.dbg("")

    progress.update(13, "Reading LVZ resource table")
    rows = lvz.walk_master_resource_table(master.res_table_addr, res_count)
    platform_from_resources, resource_dialects = detect_platform_from_resource_dialects(lvz, rows, platform)
    if platform_from_resources != platform or resource_dialects:
        platform = platform_from_resources
        use_swizzle = platform_uses_ps2_swizzle(platform)
        lvz.use_swizzle = use_swizzle
        dialect_text = ", ".join(f"{key}:{value}" for key, value in sorted(resource_dialects.items())) if resource_dialects else "none"
        LVZ.dbg(f"[platform] resource dialects: {dialect_text}; final platform={platform}; texture swizzle={'PS2' if use_swizzle else 'PSP/no-PS2-swizzle'}")
        LVZ.dbg("")
    LVZ.dbg("[policy] V97: RES/object id is authoritative; EMPTY Resource[] means CONTINUES_IN_IMG when descriptor proof exists.")
    LVZ.dbg("[policy] exact resource-table IMG recovery is enabled; IPL/IDE/neighbor/reference-DFF/rich-over-sparse guessing remains disabled.")
    master_empty_res_ids = {int(row['index']) for row in rows if str(row.get('kind', '')).upper() == 'EMPTY'}
    if img_bytes and master_empty_res_ids and ENABLE_EMPTY_RESOURCE_CONTINUES_IN_IMG:
        proof_count_before = len(CONTINUES_IN_IMG_PROOF_CACHE)
        scan_continues_in_img_descriptor_proofs(
            stem,
            img_bytes,
            lvz,
            master_empty_res_ids,
            progress_callback=lambda index, total: progress.update_range(14, 18, index, total, "Scanning IMG continuation descriptors"),
        )
        proof_count_after = len(CONTINUES_IN_IMG_PROOF_CACHE)
        LVZ.dbg(
            f"[continues-img] proof scan: empty_resource_ids={len(master_empty_res_ids)} "
            f"proven={proof_count_after} new={proof_count_after - proof_count_before}"
        )
    master_dump_continues_proofs = CONTINUES_IN_IMG_PROOF_CACHE
    LVZ.dbg("— Master Resource Table (first 300) —")
    for row in rows[:min(len(rows), 300)]:
        a16, b16 = row["peek_u16"]
        a32, b32 = row["peek_u32"]
        extra = []
        display_kind = str(row["kind"])
        if row["kind"] == "EMPTY" and ENABLE_EMPTY_RESOURCE_CONTINUES_IN_IMG:
            proof = master_dump_continues_proofs.get(int(row["index"])) if 'master_dump_continues_proofs' in locals() else None
            if proof:
                display_kind = "CONTINUES_IN_IMG"
                _tex = ",".join(str(int(x)) for x in sorted(proof.get('tex_ids') or []))
                extra.append(f"img_raw=0x{int(proof.get('raw_off', -1)):08X}")
                extra.append(f"img_end=0x{int(proof.get('after', -1)):08X}")
                extra.append(f"geom={int(proof.get('verts', 0))}v/{int(proof.get('faces', 0))}f")
                if _tex:
                    extra.append(f"materials={_tex}")
            else:
                display_kind = "EMPTY_IMG_CONTINUATION_CANDIDATE"
                extra.append("img_raw=not_proven_yet")
        if row["kind"] == "UNK_FAC0" and "unk_fac0" in row:
            extra.append(f"unk_fac0={row['unk_fac0']}")
        if row["kind"] == "EMPTY" and "empty_reason" in row and not ENABLE_EMPTY_RESOURCE_CONTINUES_IN_IMG:
            extra.append(f"reason={row['empty_reason']}")
        if row["kind"] == "TEX_REF":
            extra.append(f"ref_addr=0x{row['ref_addr']:08X}")
            extra.append(f"RES(index)={row['index']}")
            if "embedded_res_id" in row and row["embedded_res_id"] is not None:
                extra.append(f"embedded=0x{row['embedded_res_id']:08X}")
        LVZ.dbg(
            f"[res {row['index']:5d}] table@0x{row['table_off']:08X} → res@0x{row['res_addr']:08X} "
            f"kind={display_kind} u16,u16=({a16},{b16}) "
            f"u32,u32=(0x{(a32 if a32 is not None else 0):08X},0x{(b32 if b32 is not None else 0):08X}) "
            f"{' '.join(extra)}"
        )
    LVZ.dbg("")

    progress.update(18, "Decoding LVZ textures")
    lvz.decode_textures(
        rows,
        progress_callback=lambda index, total: progress.update_range(18, 22, index, total, "Decoding LVZ textures"),
    )

    progress.update(22, "Reading IMG placement tables")
    transforms_by_res: Dict[int, Matrix] = {}
    details = []
    sector_records = []
    extra_container_records = []
    if img is not None:
        sector_records = img.find_sector_container_records_from_lvz()
        extra_container_records = img.find_extra_container_records_from_lvz(sector_records)
        LVZ.dbg(f"[img] sector row directories: {len(img.find_sector_row_directories_from_lvz())}")
        LVZ.dbg(f"[img] concrete sector headers: {len(sector_records)}")
        LVZ.dbg(f"[img] extra AREA/triggered candidate containers: {len(extra_container_records)}")
        blds_log_raw_2dfx_diagnostics(lvz, img, img_bytes, sector_records, extra_container_records, lvz_path, int(res_count))
        sector_details = img.enumerate_sector_details(
            max_resource_id=res_count,
            include_lod=IMPORT_LOD_PASSES_BY_DEFAULT,
            dedupe_visible=True,
            progress_callback=lambda index, total: progress.update_range(22, 26, index, total, "Reading IMG sector placements"),
        )
        extra_details = img.enumerate_extra_container_details(
            extra_container_records,
            max_resource_id=res_count,
            include_lod=IMPORT_LOD_PASSES_BY_DEFAULT,
            progress_callback=lambda index, total: progress.update_range(26, 28, index, total, "Reading IMG AREA placements"),
        )
        details = img.merge_instance_details(sector_details, extra_details)
        stats = getattr(img, "last_sector_walk_stats", {}) or {}
        extra_stats = getattr(img, "last_extra_container_walk_stats", {}) or {}
        LVZ.dbg(
            f"[img] sector rows candidate={stats.get('candidate_rows', 0)} valid={stats.get('valid_rows', 0)} "
            f"kept={stats.get('kept_rows', 0)} skipped_lod={stats.get('skipped_lod_rows', 0)} "
            f"skipped_dupes={stats.get('skipped_duplicate_rows', 0)}"
        )
        LVZ.dbg(
            f"[img] extra rows candidate={extra_stats.get('candidate_rows', 0)} valid={extra_stats.get('valid_rows', 0)} "
            f"kept={extra_stats.get('kept_rows', 0)} skipped_lod={extra_stats.get('skipped_lod_rows', 0)} "
            f"origin_fixed_containers={extra_stats.get('nonzero_origin_containers', 0)}"
        )
        if IMPORT_DEBUG_VERBOSE_RESOURCE_DUMPS:
            transforms_by_res = img.build_sector_transforms_map_and_log(details, enable_unique_log=True)
        else:
            transforms_by_res = img.build_sector_transforms_map_and_log(details, enable_unique_log=False)

        if IMPORT_WRITE_DEBUG_CSVS:
            all_rows = img.write_sector_csvs(lvz_path, details, enable_unique=csv_dedup_res_ids)
        else:
            all_rows = [(int(d[1]), int(d[2]), int(d[3]), int(d[4]), int(d[0])) for d in details]

        LVZ.dbg(f"[img] IMG placement rows kept after pass filtering: {len(all_rows)}")
        if IMPORT_DEBUG_VERBOSE_RESOURCE_DUMPS:
            LVZ.dbg("— FILTERED VISIBLE RESOURCE IDs (IMG walk order) —")
            for i, (cont, rel_off, ipl_raw, ipl_id, res_id) in enumerate(all_rows[:200]):
                LVZ.dbg(f"{i:04d}: {res_id}")
            if len(all_rows) > 200:
                LVZ.dbg(f"[img] resource-id log truncated at 200 / {len(all_rows)} rows")
        else:
            LVZ.dbg("[img] resource-id dump skipped for fast import")
    else:
        LVZ.dbg("[img] IMG rows not enumerated because IMG is missing")

    LVZ.dbg("[progress] building LVZ resource MDLs")
    if LVZ.DEBUG is not None:
        LVZ.DEBUG.flush()
    built_by_res = build_lvz_resource_mdl_objects(
        lvz,
        rows,
        progress_callback=lambda index, total: progress.update_range(28, 40, index, total, "Building LVZ model resources"),
    )
    stamp_source_paths(built_by_res, lvz_path, img_name)

    built_by_cont: Dict[int, bpy.types.Object] = {}
    do_img_container_mdls = bool(import_img_container_mdls and IMPORT_IMG_MDL_PAYLOADS_BY_DEFAULT)
    if img is not None and do_img_container_mdls:
        LVZ.dbg("[img-mdl] loose LVZ-referenced IMG container MDL debug parse enabled")
        built_by_cont = build_img_mdl_objects(stem, img_bytes, img, lvz.material_by_res_index, lvz_path, img_name)
    elif img is not None:
        LVZ.dbg("[img-mdl] loose IMG container debug parse disabled; structured IMG resource-table MDLs are still parsed and placed below")

    overlay_by_sector_res: Dict[Tuple[int, int], bpy.types.Object] = {}
    row_overlay_by_res: Dict[Tuple[int, int], bpy.types.Object] = {}
    nested_overlay_by_res: Dict[Tuple[int, int], bpy.types.Object] = {}
    ipl_overlay_by_sector_res: Dict[Tuple[int, int], bpy.types.Object] = {}
    ipl_row_overlay_by_res: Dict[Tuple[int, int], bpy.types.Object] = {}
    ipl_nested_overlay_by_res: Dict[Tuple[int, int], bpy.types.Object] = {}
    area_direct_objects: List[bpy.types.Object] = []
    ipl_area_direct_objects: List[bpy.types.Object] = []
    if img is not None and sector_records:
        needed_sector_res_keys = {(int(detail[15]), int(detail[0])) for detail in details if len(detail) > 15}
        LVZ.dbg("[progress] building same-sector IMG resource MDLs")
        if LVZ.DEBUG is not None:
            LVZ.DEBUG.flush()
        overlay_by_sector_res = build_sector_overlay_mdl_objects(
            stem,
            img_bytes,
            lvz,
            img,
            sector_records,
            int(res_count),
            lvz_path,
            img_name,
            needed_sector_res_keys=needed_sector_res_keys,
            # Include alternate 1/2 resource layouts during the same‑sector
            # overlay pass.  Without this, many sector‑local resources in the
            # alternate tables are skipped entirely, leaving large holes.
            include_alt_12_layouts=True,
            progress_callback=lambda index, total: progress.update_range(41, 52, index, total, "Building exact IMG resource models"),
        )
        log_overlay_resource_stats(img, "sector")

        # Build exact overlays for AREA/triggered containers too.  Extra-container
        # placement rows use IMG-continuation sector indexes such as -100006, but the old
        # same-sector overlay pass only scanned normal sector_records.  That meant
        # a valid model sitting in the same AREA container was invisible to the
        # primary resolver and was only considered later through weak global
        # fallbacks.  Keying these by their real IMG-continuation sector index lets
        # apply_img_instance_transforms resolve them directly.
        needed_extra_sector_res_keys = {
            (int(detail[15]), int(detail[0]))
            for detail in details
            if len(detail) > 15 and int(detail[15]) < 0
        }
        if extra_container_records and needed_extra_sector_res_keys:
            progress.update(53, "Building AREA resource models")
            LVZ.dbg("[progress] building exact AREA/triggered IMG resource MDLs")
            if LVZ.DEBUG is not None:
                LVZ.DEBUG.flush()
            extra_exact_overlay_by_sector_res = build_sector_overlay_mdl_objects(
                stem,
                img_bytes,
                lvz,
                img,
                extra_container_records,
                None,
                lvz_path,
                img_name,
                needed_sector_res_keys=needed_extra_sector_res_keys,
                include_alt_12_layouts=True,
                progress_callback=lambda index, total: progress.update_range(53, 58, index, total, "Building AREA resource models"),
            )
            merged_extra_exact = 0
            for key, obj in extra_exact_overlay_by_sector_res.items():
                if key in overlay_by_sector_res:
                    continue
                try:
                    obj["blds_kind"] = "IMG_EXTRA_EXACT_SECTOR_MDL"
                    obj["blds_img_extra_exact_res_fallback"] = True
                except Exception:
                    pass
                overlay_by_sector_res[key] = obj
                merged_extra_exact += 1
            LVZ.dbg(f"[fast] exact AREA/triggered resource MDLs merged: {merged_extra_exact}")
            log_overlay_resource_stats(img, "extra-exact-sector")

        missing_after_primary = find_details_missing_primary_resources(built_by_res, details, overlay_by_sector_res)
        needed_deep_row_res_keys = {
            (int(detail[19]), int(detail[0]))
            for detail in missing_after_primary
            if len(detail) > 19 and int(detail[19]) >= 0
        }
        needed_deep_res_ids = {int(detail[0]) for detail in missing_after_primary}
        empty_resource_res_ids = set()
        try:
            for detail in details:
                rid = int(detail[0])
                if rid < 0:
                    continue
                row = lvz.resource_rows_by_index.get(rid) if hasattr(lvz, "resource_rows_by_index") else None
                if row is not None and str(row.get("kind", "")).upper() == "EMPTY":
                    empty_resource_res_ids.add(rid)
        except Exception:
            empty_resource_res_ids = set()
        continues_img_wanted_res_ids = set(needed_deep_res_ids) | set(empty_resource_res_ids)

        # For the rows that still miss by the normal resource-id field, also try the masked
        # IPL/model id field as a sector resource id. In VCS beach, this is what rows like
        # RES=1828 / IPL=1222..1241 need.
        needed_ipl_sector_keys = {
            (int(detail[15]), int(detail[4]))
            for detail in missing_after_primary
            if len(detail) > 15 and int(detail[15]) >= 0 and int(detail[4]) >= 0
        }
        needed_ipl_row_res_keys = {
            (int(detail[19]), int(detail[4]))
            for detail in missing_after_primary
            if len(detail) > 19 and int(detail[19]) >= 0 and int(detail[4]) >= 0
        }
        needed_ipl_res_ids = {int(detail[4]) for detail in missing_after_primary if int(detail[4]) >= 0}

        LVZ.dbg(
            f"[fast] deep fallback keys after LVZ+sector+same-resource pass: "
            f"details={len(missing_after_primary)} row/res={len(needed_deep_row_res_keys)} res={len(needed_deep_res_ids)} "
            f"ipl-sector={len(needed_ipl_sector_keys)} ipl-row/res={len(needed_ipl_row_res_keys)} ipl-res={len(needed_ipl_res_ids)}"
        )

        if continues_img_wanted_res_ids and ENABLE_EMPTY_RESOURCE_CONTINUES_IN_IMG:
            progress.update(58, "Resolving IMG continuation resources")
            LVZ.dbg(f"[progress] building empty-resource CONTINUES-IN-IMG descriptor MDLs wanted={len(continues_img_wanted_res_ids)}")
            if LVZ.DEBUG is not None:
                LVZ.DEBUG.flush()
            continued_img_overlay_by_sector_res = build_empty_resource_continues_in_img_mdl_objects(
                stem,
                img_bytes,
                lvz,
                img,
                continues_img_wanted_res_ids,
                lvz_path,
                img_name,
                progress_callback=lambda index, total: progress.update_range(58, 62, index, total, "Resolving IMG continuation resources"),
            )
            merged_continued_img = 0
            for key, obj in continued_img_overlay_by_sector_res.items():
                if key in overlay_by_sector_res:
                    continue
                overlay_by_sector_res[key] = obj
                merged_continued_img += 1
            LVZ.dbg(f"[fast] empty-resource CONTINUES-IN-IMG MDLs merged: {merged_continued_img}")

        if needed_deep_res_ids and ENABLE_GLOBAL_EXACT_RES_FALLBACK_MDLS:
            # Some VCS sectors do not carry the model payload in the same sector container
            # even though the placement row's normal resource id is correct. Build one
            # best global exact-res candidate per missing resource id before falling back
            # to the more dangerous IPL/model-id interpretation.
            progress.update(62, "Building global exact-resource models")
            LVZ.dbg("[progress] exact-res IMG fallback MDLs")
            if LVZ.DEBUG is not None:
                LVZ.DEBUG.flush()
            global_exact_overlay_by_sector_res = build_sector_overlay_mdl_objects(
                stem,
                img_bytes,
                lvz,
                img,
                sector_records,
                int(res_count),
                lvz_path,
                img_name,
                needed_sector_res_keys=None,
                # Some resource tables use the alternate 1/2 layout even when the
                # model ID appears to point into the primary table.  Enabling
                # alt‑layout collection here allows those MDLs to be picked up
                # during the global exact fallback pass.  Without this the
                # importer will leave many placement rows missing.  It is safe
                # to enable because collapse_by_res_id ensures that only one
                # instance per resource ID is kept.
                include_alt_12_layouts=True,
                wanted_res_ids=needed_deep_res_ids,
                collapse_by_res_id=True,
                progress_callback=lambda index, total: progress.update_range(62, 67, index, total, "Building global exact-resource models"),
            )
            merged_global_exact = 0
            for key, obj in global_exact_overlay_by_sector_res.items():
                if key in overlay_by_sector_res:
                    continue
                try:
                    obj["blds_kind"] = "IMG_GLOBAL_EXACT_RES_MDL"
                    obj["blds_img_global_exact_res_fallback"] = True
                except Exception:
                    pass
                overlay_by_sector_res[key] = obj
                merged_global_exact += 1
            LVZ.dbg(f"[fast] global exact resource fallback MDLs merged: {merged_global_exact}")
            log_overlay_resource_stats(img, "global-exact-res")
        elif needed_deep_res_ids:
            LVZ.dbg(f"[cleanup] global exact-res IMG recovery had no build request; unresolved exact RES ids={len(needed_deep_res_ids)}")

        if needed_ipl_res_ids and ENABLE_INTERNAL_IPL_MODEL_FALLBACK_MDLS:
            # Build exact IPL/model-id resources globally, not only in the same sector.
            # beach rows like RES=1828 / IPL=1222..1241 reference model IDs that are
            # stored in other sector resource tables, so same-sector filtering leaves
            # the building half-missing and forces bad AREA/nested fallbacks.
            LVZ.dbg("[progress] building global IPL/model fallback MDLs")
            if LVZ.DEBUG is not None:
                LVZ.DEBUG.flush()
            ipl_overlay_by_sector_res = build_sector_overlay_mdl_objects(
                stem,
                img_bytes,
                lvz,
                img,
                sector_records,
                int(res_count),
                lvz_path,
                img_name,
                needed_sector_res_keys=None,
                include_alt_12_layouts=True,
                wanted_res_ids=needed_ipl_res_ids,
                collapse_by_res_id=True,
            )
            for obj in ipl_overlay_by_sector_res.values():
                try:
                    obj["blds_kind"] = "IMG_IPL_MODEL_MDL"
                    obj["blds_img_ipl_model_fallback"] = True
                except Exception:
                    pass
            log_overlay_resource_stats(img, "ipl-sector")

        if ENABLE_NESTED_CHILD_FALLBACK_MDLS:
            progress.update(67, "Building nested exact-resource models")
            LVZ.dbg("[progress] building nested-child fallback MDLs")
            if LVZ.DEBUG is not None:
                LVZ.DEBUG.flush()
            nested_overlay_by_res = build_nested_child_mdl_objects(
                stem,
                img_bytes,
                lvz,
                img,
                lvz_path,
                img_name,
                needed_row_res_keys=needed_deep_row_res_keys,
                include_alt_12_layouts=True,
                wanted_res_ids=needed_deep_res_ids,
                progress_callback=lambda index, total: progress.update_range(67, 71, index, total, "Building nested exact-resource models"),
            )
            log_overlay_resource_stats(img, "nested")
        elif needed_deep_row_res_keys or needed_deep_res_ids:
            LVZ.dbg(f"[cleanup] nested-child exact RES recovery had no build request; row-keys={len(needed_deep_row_res_keys)} res={len(needed_deep_res_ids)}")
        if needed_ipl_row_res_keys and ENABLE_INTERNAL_IPL_MODEL_FALLBACK_MDLS:
            ipl_nested_overlay_by_res = build_nested_child_mdl_objects(
                stem,
                img_bytes,
                lvz,
                img,
                lvz_path,
                img_name,
                needed_row_res_keys=needed_ipl_row_res_keys,
                include_alt_12_layouts=True,
                wanted_res_ids=needed_ipl_res_ids,
            )
            for obj in ipl_nested_overlay_by_res.values():
                try:
                    obj["blds_kind"] = "IMG_IPL_NESTED_MDL"
                    obj["blds_img_ipl_model_fallback"] = True
                except Exception:
                    pass
            log_overlay_resource_stats(img, "ipl-nested")
        if ENABLE_ROW_SHARED_FALLBACK_MDLS:
            progress.update(71, "Building row-shared exact-resource models")
            LVZ.dbg("[progress] building row-shared fallback MDLs")
            if LVZ.DEBUG is not None:
                LVZ.DEBUG.flush()
            row_overlay_by_res = build_row_shared_mdl_objects(
                stem,
                img_bytes,
                lvz,
                img,
                sector_records,
                int(res_count),
                lvz_path,
                img_name,
                needed_row_res_keys=needed_deep_row_res_keys,
                include_alt_12_layouts=True,
                wanted_res_ids=needed_deep_res_ids,
                progress_callback=lambda index, total: progress.update_range(71, 75, index, total, "Building row-shared exact-resource models"),
            )
            log_overlay_resource_stats(img, "row")
        elif needed_deep_row_res_keys or needed_deep_res_ids:
            LVZ.dbg(f"[cleanup] row-shared exact RES recovery had no build request; row-keys={len(needed_deep_row_res_keys)} res={len(needed_deep_res_ids)}")
        if needed_ipl_row_res_keys and ENABLE_INTERNAL_IPL_MODEL_FALLBACK_MDLS:
            ipl_row_overlay_by_res = build_row_shared_mdl_objects(
                stem,
                img_bytes,
                lvz,
                img,
                sector_records,
                int(res_count),
                lvz_path,
                img_name,
                needed_row_res_keys=needed_ipl_row_res_keys,
                include_alt_12_layouts=True,
                wanted_res_ids=needed_ipl_res_ids,
            )
            for obj in ipl_row_overlay_by_res.values():
                try:
                    obj["blds_kind"] = "IMG_IPL_ROW_SHARED_MDL"
                    obj["blds_img_ipl_model_fallback"] = True
                except Exception:
                    pass
            log_overlay_resource_stats(img, "ipl-row")
        progress.update(75, "Building AREA direct-resource models")
        LVZ.dbg("[progress] building structured AREA IMG resource MDLs")
        if LVZ.DEBUG is not None:
            LVZ.DEBUG.flush()
        area_direct_objects = build_extra_area_direct_mdl_objects(
            stem,
            img_bytes,
            lvz,
            img,
            extra_container_records,
            lvz_path,
            img_name,
            needed_res_ids=needed_deep_res_ids,
            # Enable alternate layout resource search for extra/AREA containers.
            include_alt_12_layouts=True,
            wanted_res_ids=needed_deep_res_ids,
            progress_callback=lambda index, total: progress.update_range(75, 79, index, total, "Building AREA direct-resource models"),
        )
        log_overlay_resource_stats(img, "area")
        if needed_ipl_res_ids and ENABLE_INTERNAL_IPL_MODEL_FALLBACK_MDLS:
            LVZ.dbg("[progress] building IPL AREA/direct fallback MDLs")
            if LVZ.DEBUG is not None:
                LVZ.DEBUG.flush()
            ipl_area_direct_objects = build_extra_area_direct_mdl_objects(
                stem,
                img_bytes,
                lvz,
                img,
                extra_container_records,
                lvz_path,
                img_name,
                needed_res_ids=needed_ipl_res_ids,
                include_alt_12_layouts=True,
                wanted_res_ids=needed_ipl_res_ids,
            )
            for obj in ipl_area_direct_objects:
                try:
                    obj["blds_kind"] = "IMG_IPL_AREA_DIRECT_MDL"
                    obj["blds_img_ipl_model_fallback"] = True
                except Exception:
                    pass
            log_overlay_resource_stats(img, "ipl-area")

    linked_instances = 0
    removed_unplaced = 0
    sidecar_ipl_path = None  # V18: do not use external beach.ipl sidecars; fix internal master/slave WRLD placement only.
    if False and apply_img_transforms and sidecar_ipl_path is not None:
        try:
            LVZ.dbg(f"[progress] applying Stories Map Converter IPL sidecar placements: {sidecar_ipl_path}")
            if LVZ.DEBUG is not None:
                LVZ.DEBUG.flush()
            applied, linked_instances, removed_unplaced = apply_stories_ipl_sidecar_placements(
                sidecar_ipl_path,
                stem,
                built_by_res,
                overlay_by_sector_res,
                area_direct_objects,
                row_overlay_by_res,
                nested_overlay_by_res,
                ipl_overlay_by_sector_res,
                ipl_row_overlay_by_res,
                ipl_nested_overlay_by_res,
                ipl_area_direct_objects,
            )
            LVZ.dbg(f"[apply] Stories IPL sidecar placement rows applied: {applied}")
            LVZ.dbg(f"[apply] Stories IPL sidecar linked placement objects created: {linked_instances}")
        except Exception as exc:
            LVZ.dbg(f"[apply] Stories IPL sidecar placement pass failed: {exc}")
    elif apply_img_transforms and details:
        try:
            progress.update(80, "Placing IMG instances")
            LVZ.dbg("[progress] applying IMG placement transforms / linked duplicates")
            if LVZ.DEBUG is not None:
                LVZ.DEBUG.flush()
            applied, linked_instances, removed_unplaced = apply_img_instance_transforms(
                built_by_res,
                details,
                overlay_by_sector_res,
                area_direct_objects,
                row_overlay_by_res,
                nested_overlay_by_res,
                ipl_overlay_by_sector_res,
                ipl_row_overlay_by_res,
                ipl_nested_overlay_by_res,
                ipl_area_direct_objects,
                stem,
                ide_ipl_to_res,
                ide_ipl_to_name,
                progress_callback=lambda index, total: progress.update_range(80, 98, index, total, "Placing IMG instances"),
            )
            removed_unplaced += purge_stale_raw_parser_bases(stem, reason="post-apply")
            LVZ.dbg(f"[apply] IMG placement rows applied: {applied}")
            LVZ.dbg(f"[apply] linked duplicate placement objects created: {linked_instances}")
        except Exception as exc:
            LVZ.dbg(f"[apply] IMG placement transform pass failed: {exc}")
    elif apply_img_transforms:
        LVZ.dbg("[apply] no IMG transforms available to apply")

    progress.update(99, "Finalizing imported objects", force=True)
    elapsed = time.time() - t0
    LVZ.dbg(f"[summary] LVZ-table MDL resource objects parsed: {len(built_by_res)}")
    LVZ.dbg(f"[summary] IMG sector overlay MDL objects parsed: {len(overlay_by_sector_res)}")
    LVZ.dbg(f"[summary] IMG global IPL/model sector MDLs parsed: {len(ipl_overlay_by_sector_res)}")
    LVZ.dbg(f"[summary] IMG nested-child fallback MDL bases parsed: {len(nested_overlay_by_res)}")
    LVZ.dbg(f"[summary] IMG IPL/model nested fallback MDLs parsed: {len(ipl_nested_overlay_by_res)}")
    LVZ.dbg(f"[summary] IMG row-shared fallback MDL bases parsed: {len(row_overlay_by_res)}")
    LVZ.dbg(f"[summary] IMG IPL/model row fallback MDLs parsed: {len(ipl_row_overlay_by_res)}")
    LVZ.dbg(f"[summary] IMG AREA/direct fallback MDL bases parsed: {len(area_direct_objects)}")
    LVZ.dbg(f"[summary] IMG IPL/model AREA fallback MDLs parsed: {len(ipl_area_direct_objects)}")
    LVZ.dbg(f"[summary] deleted unplaced resource objects: {removed_unplaced}")
    LVZ.dbg(f"[summary] linked IMG placement duplicates: {linked_instances}")
    LVZ.dbg(f"[summary] IMG-container MDL objects: {len(built_by_cont)}")
    try:
        if DIAGNOSTIC_CSV_LOGS_ENABLED and REFERENCE_DFF_DEBUG_ROWS:
            from collections import Counter
            ref_counts = Counter(str(r.get("decision", "")) for r in REFERENCE_DFF_DEBUG_ROWS)
            LVZ.dbg("[reference-dff] decisions:")
            for k, v in ref_counts.most_common():
                LVZ.dbg(f"  {k}: {v}")
            out_csv = str(Path(lvz_path).with_suffix("")) + "_blds_reference_dff_decisions.csv"
            import csv
            with open(out_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["res_id","decision","path","source","import_mode","object_name","verts","faces","checked"])
                for r in REFERENCE_DFF_DEBUG_ROWS:
                    w.writerow([
                        r.get("res_id", -1), r.get("decision", ""), r.get("path", ""), r.get("source", ""),
                        r.get("import_mode", ""), r.get("object_name", ""), r.get("verts", 0), r.get("faces", 0), r.get("checked", "")
                    ])
            LVZ.dbg(f"[reference-dff] wrote debug CSV: {out_csv}")
    except Exception as exc:
        LVZ.dbg(f"[reference-dff] debug CSV failed: {exc}")
    try:
        if DIAGNOSTIC_CSV_LOGS_ENABLED and REFERENCE_DFF_COMPARE_ROWS:
            from collections import Counter
            cmp_counts = Counter(str(r.get("comparison_verdict", "")) for r in REFERENCE_DFF_COMPARE_ROWS)
            proof_counts = Counter(str(r.get("proof_verdict", "")) for r in REFERENCE_DFF_COMPARE_ROWS)
            LVZ.dbg("[reference-dff-compare] verdicts:")
            for k, v in cmp_counts.most_common():
                LVZ.dbg(f"  {k}: {v}")
            LVZ.dbg("[reference-dff-proof] verdicts:")
            for k, v in proof_counts.most_common():
                LVZ.dbg(f"  {k}: {v}")
            cmp_csv = str(Path(lvz_path).with_suffix("")) + "_blds_reference_vs_lvz_geometry_compare.csv"
            import csv
            fieldnames = [
                "sector", "row", "pass", "ipl_id", "res_id", "reference_source", "reference_object",
                "reference_verts", "reference_faces", "reference_import_mode",
                "reference_bbox_min", "reference_bbox_max", "reference_center", "reference_radius", "reference_diag", "reference_mesh_hash",
                "lvz_candidate_found", "lvz_parent_res_id", "lvz_group_index", "lvz_range_start", "lvz_group_count",
                "lvz_global_fallback", "lvz_sparse_range", "lvz_verts", "lvz_faces", "lvz_strips", "lvz_material_res_ids",
                "lvz_bbox_min", "lvz_bbox_max", "lvz_center", "lvz_radius", "lvz_diag", "lvz_mesh_hash",
                "verts_ratio_ref_over_lvz", "faces_ratio_ref_over_lvz", "radius_ratio_ref_over_lvz", "diag_ratio_ref_over_lvz",
                "comparison_verdict", "proof_verdict", "proof_reason",
            ]
            with open(cmp_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                w.writeheader()
                for r in REFERENCE_DFF_COMPARE_ROWS:
                    w.writerow(r)
            LVZ.dbg(f"[reference-dff-compare] wrote geometry comparison CSV: {cmp_csv}")
        else:
            LVZ.dbg("[reference-dff-compare] no reference-vs-LVZ rows captured")
    except Exception as exc:
        LVZ.dbg(f"[reference-dff-compare] CSV failed: {exc}")
    LVZ.dbg(f"[total] finished in {elapsed:.3f} seconds")

    restore_global_undo()
    if LVZ.DEBUG is not None:
        try:
            LVZ.DEBUG.close()
        except Exception:
            LVZ.DEBUG.flush()
    operator.report({'INFO'}, f"Imported LVZ+IMG: {len(details)} visible placements, {linked_instances} linked duplicates, {len(overlay_by_sector_res)} sector MDLs, {len(ipl_overlay_by_sector_res)} IPL fallback MDLs, {len(nested_overlay_by_res)} nested-child MDLs, {len(row_overlay_by_res)} row-shared MDLs, {len(area_direct_objects)} AREA/direct fallback MDLs, {removed_unplaced} unplaced resources removed ({platform}).")
    progress.finish(succeeded=True, message="Import complete")
    return {'FINISHED'}
