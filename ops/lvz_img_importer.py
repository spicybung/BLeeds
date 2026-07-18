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
import math
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import bpy
from mathutils import Matrix, Vector

try:
    import numpy as np
except Exception:
    np = None

from .. import set_mesh_auto_smooth, stamp_bleeds_entity_type
from ..leedsLib import lvz_img as LVZ

_ACTIVE_IMPORT_PROGRESS = None
_ACTIVE_IMPORT_UNDO_STATE = None
_ACTIVE_IMPORT_ROOT_COLLECTION = None
_ACTIVE_IMPORT_OBJECTS_COLLECTION = None
_ACTIVE_IMPORT_LINKED_COLLECTION = None
_ACTIVE_IMPORT_2DFX_COLLECTION = None
_CURRENT_PLACED_OBJECT_RECORDS = []


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
    status_text = str(getattr(window_manager, "bleeds_lvz_img_status", "") or "")
    if status_text and status_text != stage_text:
        column.label(text=status_text)


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
        self.redraw_interval = 0.25
        self.last_report_bucket = -1
        self.started_at = time.perf_counter()
        self.last_console_time = 0.0
        self.map_current = 0
        self.map_total = 0
        self.model_current = 0
        self.model_total = 0
        self.cached_current = 0
        self.cached_total = 0
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
        self.started_at = time.perf_counter()
        self.capture_initial_data_blocks()
        if self.window_manager is not None:
            try:
                self.window_manager.progress_begin(0, 100)
            except Exception:
                pass
            try:
                self.window_manager.bleeds_lvz_img_progress = 0
                self.window_manager.bleeds_lvz_img_stage = str(stage)
                self.window_manager.bleeds_lvz_img_status = "Leeds Stories map import | starting"
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
        new_stage = self.stage if stage is None else str(stage)
        changed = value != self.value
        stage_changed = new_stage != self.stage
        if not force and not changed and not stage_changed:
            return
        self.stage = new_stage
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

        status_text = self.build_status_text(value)
        try:
            self.window_manager.bleeds_lvz_img_status = status_text
        except Exception:
            pass
        try:
            self.context.workspace.status_text_set(status_text)
        except Exception:
            pass
        try:
            if self.context.area is not None:
                self.context.area.header_text_set(status_text)
        except Exception:
            pass

        current_time = time.monotonic()
        should_redraw = force or (changed and current_time - self.last_redraw_time >= self.redraw_interval)
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

        now = time.perf_counter()
        if force or now - self.last_console_time >= 1.0:
            print(status_text, flush=True)
            self.last_console_time = now

    @staticmethod
    def format_duration(seconds):
        seconds = max(0, int(math.ceil(float(seconds))))
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return "{}:{:02d}:{:02d}".format(hours, minutes, seconds)
        return "{:02d}:{:02d}".format(minutes, seconds)

    def configure_map_plan(self, total_placements, total_models, total_cached):
        self.map_total = max(0, int(total_placements))
        self.model_total = max(0, int(total_models))
        self.cached_total = max(0, int(total_cached))
        self.map_current = 0
        self.model_current = 0
        self.cached_current = 0

    def update_map(self, current, total, placed, models, cached, detail="Placing IMG instances"):
        self.map_total = max(0, int(total))
        self.map_current = max(0, min(self.map_total, int(current)))
        self.model_current = max(0, min(self.model_total, int(models)))
        self.cached_current = max(0, min(self.cached_total, int(cached)))
        self.update_range(80, 98, self.map_current, max(1, self.map_total), detail)

    def build_status_text(self, value):
        elapsed = max(0.0, time.perf_counter() - self.started_at)
        elapsed_text = self.format_duration(elapsed)
        if self.map_total > 0 and self.map_current > 0:
            remaining = max(0, self.map_total - self.map_current)
            eta_seconds = (elapsed / float(self.map_current)) * float(remaining)
            eta_text = self.format_duration(eta_seconds)
        else:
            eta_text = "--:--"

        if self.map_total > 0:
            percent = (float(self.map_current) / float(self.map_total)) * 100.0
            text = (
                "Leeds Stories map import {}/{} ({:.1f}%) | models {}/{} | "
                "cached {}/{} | elapsed {} | ETA {}"
            ).format(
                self.map_current,
                self.map_total,
                percent,
                self.model_current,
                self.model_total,
                self.cached_current,
                self.cached_total,
                elapsed_text,
                eta_text,
            )
        else:
            text = "Leeds Stories map import | {}% | elapsed {} | ETA {}".format(
                int(value), elapsed_text, eta_text
            )
        if self.stage:
            text += " | " + self.stage
        return text

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
        if self.window_manager is None:
            return
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
            self.context.view_layer.update()
        except Exception:
            pass
        try:
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
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
                self.window_manager.bleeds_lvz_img_status = final_stage
            except Exception:
                pass
        try:
            self.context.workspace.status_text_set(None)
        except Exception:
            pass
        try:
            if self.context.area is not None:
                self.context.area.header_text_set(None)
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
IMPORT_LINK_DUPLICATES_IN_HIDDEN_COLLECTION = True
IMPORT_DEFER_BASE_VISIBILITY_DURING_APPLY = False
IMPORT_KEEP_UNPLACED_BASES_VISIBLE = False
IMPORT_VERBOSE_MDL_DEBUG = False
IMPORT_MDL_DEBUG_LIMIT = 48
IMPORT_VERBOSE_RESOURCE_BUILD_LOGS = False

# Keep the legacy ROWLINK fallback structures compiled, but the path is disabled
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
# Keep several exact-RES raw IMG descriptor variants.  A texture-number match
# alone is not enough to identify geometry; the row's own sphere and 4x4 matrix
# select the matching variant during placement.
CONTINUES_IN_IMG_MAX_VARIANTS_PER_RES = 6
CONTINUES_IN_IMG_MAX_FIT_DETAILS_PER_RES = 24
CONTINUES_IN_IMG_MAX_PLACEMENT_FIT_SCORE = 5.0
CONTINUES_IN_IMG_PROOF_CACHE: Dict[int, List[dict]] = {}
# Exact WRLD submodels are normalized model data.  Their 16/32/64/128 basis is
# the real model transform, not a scale value to discard.  Preserve it and
# compensate any bbox-center origin rebase in matrix space.
PRESERVE_EXACT_WRLD_SUBMODEL_ROW_MATRIX = True
# A same-RES WRLD submodel can be a small aggregate slice rather than the full
# object represented by the placement row.  Only in that case, scan for more
# exact-RES IMG variants and compare them using the row sphere/matrix.  This is
# still strict RES matching; the internal ROWLINK never substitutes geometry.
EXACT_WRLD_SUBMODEL_RAW_VARIANT_MIN_RADIUS_RATIO = 0.42
EXACT_WRLD_SUBMODEL_RAW_VARIANT_MAX_RADIUS_RATIO = 2.75
EXACT_WRLD_SUBMODEL_RAW_VARIANT_MIN_TARGET_RADIUS = 4.0
EXACT_WRLD_SUBMODEL_RAW_VARIANT_SPARSE_FACE_LIMIT = 18
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
OBJECT_MATRIX_TRANSFORM_LOG_ALWAYS_RES_IDS = {1179, 1725, 1881, 1887, 1989, 2184, 3528}
OBJECT_MATRIX_TRANSFORM_LOG_TO_CSV = False
OBJECT_MATRIX_TRANSFORM_LOG_TO_BLENDER_LOG = True
OBJECT_MATRIX_TRANSFORM_LOG_BLENDER_MAX_LINES = 256

# V56 speed fix: deleting tens of thousands of raw parser base objects at the
# end causes Blender to crawl.  Hide parser bases by default instead of deleting.
RAW_PARSER_BASE_CLEANUP_MODE = "hide"  # "hide" or "delete"

# V60: keep diagnostics in Blender log only. No CSV pile by default.
DIAGNOSTIC_CSV_LOGS_ENABLED = False

# 1.0.21 identity/2DFX rule. The first placement u16 is an internal ROWLINK
# and the second is the streamed geometry RES. GAME.DTZ ownership comes from the
# matching master AreaInfo -> AERA AreaResource.secondaryId row. GAME.DTZ effect
# positions are native model-space units: the streamed row basis contains an
# additional per-axis geometry-normalization scale and must be normalized before
# it is applied to C2dEffect positions. Split opaque/transparent resources that
# share one runtime model placement emit one helper set, not duplicate sets.
PLACEMENT_RES_TXT_REPORT_ENABLED = True
CREATE_GAME_DTZ_2DFX_HELPERS = True
PLACEMENT_RES_REPORT_EFFECT_LIMIT = 8
PLACEMENT_RES_REPORT_CANDIDATE_LIMIT = 24
PLACEMENT_RES_REPORT_TARGET_IDS = {1179, 1725, 1881, 1887, 1989, 2184, 3528}
_CURRENT_PLACEMENT_REPORT_ROWS = {}

# V60: geometry data prints in Blender console/log. No recovery guesses.
GEOMETRY_OBJECT_LOG_ENABLED = False
GEOMETRY_OBJECT_LOG_MAX_LINES = 2048
GEOMETRY_OBJECT_LOG_ALWAYS_RES_IDS = {1179, 1725, 1881, 1887, 1888, 1989, 2184, 3528, 4294, 5045}

# V66: resolver audit. Logs the actual row -> candidate geometry chain
# in Blender's console. No guesses are imported.
RESOLVER_AUDIT_ENABLED = False
RESOLVER_AUDIT_MAX_ROWS = 4096
RESOLVER_AUDIT_ALWAYS_RES_IDS = {1019, 1033, 1179, 1287, 1511, 1586, 1612, 1633, 1670, 1725, 1881, 1887, 1888, 1961, 1989, 2082, 2184, 3528, 4294, 5045}
RESOLVER_AUDIT_ALWAYS_IPL_IDS = {436, 437, 438, 439, 562, 825, 840, 856, 864, 892, 1280, 1281, 1285, 1322, 1479}
RESOLVER_AUDIT_CANDIDATE_LIMIT_PER_ROW = 48
# V67: target-only. Do not audit every row just because chosen_obj is None.
# The V66 log filled 512 lines on early UNDERWATER/LIGHTS rows before Beach1881.
RESOLVER_AUDIT_TARGET_ONLY = True
RESOLVER_AUDIT_TARGET_PASSES = {"NORMAL", "ROADS", "TRANSPARENT"}

# V68: actual recovery path for the pattern proven by V67:
# RES has only a tiny sparse WRLD fragment. Legacy code once treated ROWLINK as a
# rich internal LVZ+IMG model. Use that internal model with the full row matrix.
ENABLE_RICH_IPL_OVER_SPARSE_RECOVERY = False
# V71: real-new-found recovery. Never import WRLD sparse fragments as buildings.
# This legacy ROWLINK-as-model path is disabled; GAME_MODEL identity is handled separately.
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
#   +0x00 = internal ROWLINK (not the GTA IDE model id)
#   +0x02 = resource id
# Some rows have no usable RES candidate and never enter the sparse-fragment
# branch. The legacy ROWLINK-as-model interpretation is disabled;
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
# Legacy disabled path that treated ROWLINK as an authoritative model key and records
# every imported row in *_blds_imported_missing_mdl_report.csv.
ENABLE_FORCE_IMPORT_MISSING_IMG_MDLS = False
FORCE_IMPORT_MISSING_IMG_MDL_LOG_LIMIT = 512

# Exact-only recovery mode: do not silently fill unresolved missing rows with
# nearby substitute geometry. If the true exact IMG/IPL model cannot be found,
# the row stays missing and is reported as unresolved.
EXACT_ONLY_REAL_MISSING_MDL_RECOVERY = True
ENABLE_EXACT_IPL_RECOVERY_FOR_MISSING_ROWS = False

# Legacy V7 fallback. If the exact ROWLINK-as-model value is absent from every
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


def find_stories_companion_file(lvz_path: str, extension: str, stem: str = "", explicit_path: str = "") -> Optional[Path]:
    """Find an IDE/IPL companion without confusing copy suffixes with identity.

    Exact names are preferred. Blender/browser copies such as beach(1).ide and
    beach (2).ipl are accepted when their normalized stem matches the LVZ stem.
    An explicit path selected with the separate BLeeds picker always wins.
    """
    ext = str(extension or "").lower().lstrip(".")
    if not ext:
        return None

    selected = str(explicit_path or "").strip()
    if selected:
        candidate = Path(selected).expanduser()
        try:
            if candidate.exists() and candidate.is_file() and candidate.suffix.lower() == "." + ext:
                return candidate
        except Exception:
            pass

    lvz_p = Path(lvz_path)
    folder = lvz_p.parent
    exact_stem = str(stem or lvz_p.stem or "")
    base_stem = normalized_copy_stem(exact_stem)
    ordered: List[Path] = []
    seen = set()

    def add(candidate: Path):
        key = str(candidate).lower()
        if key in seen:
            return
        seen.add(key)
        ordered.append(candidate)

    for candidate_stem in (exact_stem, base_stem):
        if candidate_stem:
            add(folder / (candidate_stem + "." + ext))
    if base_stem:
        add(folder / (base_stem.lower() + "." + ext))

    for candidate in ordered:
        try:
            if candidate.exists() and candidate.is_file():
                return candidate
        except Exception:
            pass

    copy_variants: List[Path] = []
    try:
        for child in folder.iterdir():
            if not child.is_file() or child.suffix.lower() != "." + ext:
                continue
            if normalized_copy_stem(child.stem).lower() == base_stem.lower():
                copy_variants.append(child)
    except Exception:
        copy_variants = []

    # Deterministic choice: lower copy number/name first. Exact files already won.
    copy_variants.sort(key=lambda item: item.name.lower())
    return copy_variants[0] if copy_variants else None

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


def read_ide_object_id_map_next_to_lvz(lvz_path: str, explicit_path: str = "", stem: str = ""):
    """Read converter IDE beside LVZ.

    Stories Map Converter IDE lines look like:
        562, beach1828, beach1828, 1, 299, 0

    The first number is the converter/IPL object id. The model name suffix is
    the real beach resource id to try in LVZ/IMG.
    """
    ide_path = find_stories_companion_file(
        lvz_path, "ide", stem=stem or Path(lvz_path).stem, explicit_path=explicit_path
    )
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



def build_ide_res_to_model_id_map(id_to_res: Dict[int, int], id_to_name: Dict[int, str], stem: str):
    """Build the exact reverse identity map: streamed/name RES -> GTA IDE model id.

    The IDE object id is not the streamed row's first u16. Prefer the exact map
    prefix (for example beach1887) and reject ambiguous competing non-LOD names.
    """
    stem_low = str(stem or "").lower()
    choices: Dict[int, List[Tuple[int, str, int]]] = {}
    for model_id, res_id in (id_to_res or {}).items():
        try:
            model_id = int(model_id)
            res_id = int(res_id)
        except Exception:
            continue
        name = str((id_to_name or {}).get(model_id, ""))
        low = name.lower()
        exact_name = bool(stem_low and low == f"{stem_low}{res_id}")
        is_lod = low.startswith("lod") or "_lod" in low
        score = 0
        if exact_name:
            score += 100
        if not is_lod:
            score += 20
        if low.startswith(stem_low) and stem_low:
            score += 10
        choices.setdefault(res_id, []).append((score, name, model_id))

    res_to_model: Dict[int, int] = {}
    res_to_name: Dict[int, str] = {}
    ambiguous: Dict[int, List[Tuple[int, str, int]]] = {}
    for res_id, values in choices.items():
        ordered = sorted(values, key=lambda item: (-int(item[0]), int(item[2]), str(item[1]).lower()))
        if not ordered:
            continue
        best_score = int(ordered[0][0])
        best = [item for item in ordered if int(item[0]) == best_score]
        if len(best) > 1 and len({int(item[2]) for item in best}) > 1:
            ambiguous[int(res_id)] = best
            continue
        res_to_model[int(res_id)] = int(ordered[0][2])
        res_to_name[int(res_id)] = str(ordered[0][1])
    return res_to_model, res_to_name, ambiguous


def find_stories_identity_ipl_next_to_lvz(lvz_path: str, stem: str, explicit_path: str = "") -> Optional[Path]:
    """Find an IPL only for exact identity/coordinate verification, never placement."""
    return find_stories_companion_file(
        lvz_path, "ipl", stem=stem or Path(lvz_path).stem, explicit_path=explicit_path
    )


def build_stories_placement_identity_map(details, lvz_path: str, stem: str,
                                         ide_id_to_res: Dict[int, int],
                                         ide_id_to_name: Dict[int, str],
                                         ide_res_to_model: Dict[int, int],
                                         ide_res_to_name: Dict[int, str],
                                         explicit_ipl_path: str = ""):
    """Match internal placement rows to sidecar IPL rows by RES/name and position.

    Returns exact identity metadata keyed by the internal source-row key. The IPL
    is never used to move an object or provide geometry. It only proves that, for
    example, RES 1887 at the Beach1887 position is GTA model id 587 while the
    internal row-link value is 1281.
    """
    result: Dict[Tuple[int, int, int, int], Dict[str, object]] = {}
    ipl_path = find_stories_identity_ipl_next_to_lvz(lvz_path, stem, explicit_path=explicit_ipl_path)
    rows = parse_stories_ipl_sidecar(ipl_path) if ipl_path is not None else []
    by_res: Dict[int, List[Dict[str, object]]] = {}
    for item in rows:
        try:
            res_id = int(item.get("model_id", -1))
            game_model_id = int(item.get("inst_id", -1))
        except Exception:
            continue
        if res_id < 0 or game_model_id < 0:
            continue
        # Require the IDE to agree with both the model id and the name suffix.
        if int((ide_id_to_res or {}).get(game_model_id, -1)) != res_id:
            continue
        by_res.setdefault(res_id, []).append(item)

    matched = 0
    fallback = 0
    unmatched = 0
    for detail in details or []:
        key = blds_placement_report_key(detail)
        if key is None:
            continue
        res_id = int(detail[0])
        row_link_id = int(detail[4])
        identity = {
            "res_id": res_id,
            "row_link_id": row_link_id,
            "game_model_id": int((ide_res_to_model or {}).get(res_id, -1)),
            "model_name": str((ide_res_to_name or {}).get(res_id, "")),
            "source": "IDE_NAME" if res_id in (ide_res_to_model or {}) else "UNRESOLVED",
            "position_error": None,
        }
        candidates = by_res.get(res_id, [])
        if candidates:
            try:
                matrix = matrix_from_img_detail(detail)
                world = (float(matrix[0][3]), float(matrix[1][3]), float(matrix[2][3]))
                ranked = []
                for item in candidates:
                    pos = item.get("location", (0.0, 0.0, 0.0))
                    dx = world[0] - float(pos[0])
                    dy = world[1] - float(pos[1])
                    dz = world[2] - float(pos[2])
                    distance = math.sqrt(dx * dx + dy * dy + dz * dz)
                    ranked.append((distance, item))
                ranked.sort(key=lambda pair: pair[0])
                if ranked and float(ranked[0][0]) <= 0.25:
                    distance, item = ranked[0]
                    identity.update({
                        "game_model_id": int(item.get("inst_id", -1)),
                        "model_name": str(item.get("model_name", "")),
                        "source": "IDE+IPL_POSITION",
                        "position_error": float(distance),
                        "ipl_line": int(item.get("line", -1)),
                    })
                    matched += 1
                elif identity["game_model_id"] >= 0:
                    fallback += 1
                else:
                    unmatched += 1
            except Exception:
                if identity["game_model_id"] >= 0:
                    fallback += 1
                else:
                    unmatched += 1
        elif identity["game_model_id"] >= 0:
            fallback += 1
        else:
            unmatched += 1
        result[key] = identity
    return result, {
        "ipl_path": str(ipl_path) if ipl_path is not None else "",
        "sidecar_rows": len(rows),
        "matched_by_position": int(matched),
        "ide_name_fallback": int(fallback),
        "unresolved": int(unmatched),
    }


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

    if progress_callback is not None:
        try:
            progress_callback(total_details, total_details, applied, len(used_object_ids), linked)
        except TypeError:
            progress_callback(total_details, total_details)

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
    # Legacy fallback resources can have mesh verts that are not authored
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
    target_collection = globals().get("_ACTIVE_IMPORT_OBJECTS_COLLECTION")
    try:
        (target_collection or bpy.context.scene.collection).objects.link(obj)
    except Exception:
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


def mdl_groups_geometry_signature(material_list, groups):
    """Stable geometry identity used to reject conflicting generic RES matches."""
    vert_count = 0
    face_count = 0
    xs = []
    ys = []
    zs = []
    try:
        for group in groups or []:
            for strip in getattr(group, "strips", []) or []:
                verts = getattr(strip, "verts", []) or []
                uvs = getattr(strip, "uvs", []) or []
                try:
                    count = int(getattr(strip, "count", len(verts)) or len(verts))
                except Exception:
                    count = len(verts)
                count = min(count, len(verts))
                if uvs:
                    count = min(count, len(uvs))
                if count <= 0:
                    continue
                vert_count += count
                face_count += max(0, count - 2)
                for x, y, z in verts[:count]:
                    xs.append(float(x))
                    ys.append(float(y))
                    zs.append(float(z))
    except Exception:
        return None
    if vert_count <= 0 or face_count <= 0 or not xs:
        return None
    material_ids = []
    try:
        for material in getattr(material_list, "materials", []) or []:
            material_ids.append(int(getattr(material, "texture_id", -1)))
    except Exception:
        material_ids = []
    bounds = (
        round(min(xs), 4), round(min(ys), 4), round(min(zs), 4),
        round(max(xs), 4), round(max(ys), 4), round(max(zs), 4),
    )
    return (int(vert_count), int(face_count), tuple(material_ids), bounds)


def blds_object_geometry_signature(obj):
    if obj is None:
        return None
    try:
        verts = int(obj.get("blds_verts", 0))
        faces = int(obj.get("blds_faces", 0))
        bbox_min = obj.get("blds_bbox_min", None)
        bbox_max = obj.get("blds_bbox_max", None)
        if verts <= 0 or faces <= 0 or bbox_min is None or bbox_max is None:
            return None
        material_names = ()
        try:
            material_names = tuple(
                str(getattr(material, "name", ""))
                for material in getattr(getattr(obj, "data", None), "materials", [])
            )
        except Exception:
            material_names = ()
        return (
            verts,
            faces,
            round(float(bbox_min[0]), 4), round(float(bbox_min[1]), 4), round(float(bbox_min[2]), 4),
            round(float(bbox_max[0]), 4), round(float(bbox_max[1]), 4), round(float(bbox_max[2]), 4),
            material_names,
        )
    except Exception:
        return None


def build_unambiguous_resource_object_map(objects):
    """Return one object per RES only when every parsed candidate has the same mesh."""
    candidates = {}
    for obj in objects or []:
        if obj is None:
            continue
        try:
            res_id = int(obj.get("blds_res_index", -1))
        except Exception:
            continue
        if res_id < 0:
            continue
        candidates.setdefault(res_id, []).append(obj)
    result = {}
    ambiguous = set()
    for res_id, values in candidates.items():
        signatures = {blds_object_geometry_signature(obj) for obj in values}
        signatures.discard(None)
        if len(signatures) > 1:
            ambiguous.add(int(res_id))
            continue
        chosen = None
        for obj in values:
            chosen = choose_better_blds_candidate(chosen, obj)
        if chosen is not None:
            result[int(res_id)] = chosen
    return result, ambiguous



def build_resource_object_candidate_map(objects):
    """Group exact resource-table models by resource ID and unique geometry."""
    grouped = {}
    for obj in objects or []:
        if obj is None:
            continue
        try:
            res_id = int(obj.get("blds_res_index", -1))
        except Exception:
            continue
        if res_id < 0:
            continue
        signature = blds_object_geometry_signature(obj)
        if signature is None:
            signature = ("unknown",)
        by_signature = grouped.setdefault(res_id, {})
        previous = by_signature.get(signature)
        by_signature[signature] = choose_better_blds_candidate(previous, obj)
    return {
        int(res_id): [obj for obj in by_signature.values() if obj is not None]
        for res_id, by_signature in grouped.items()
    }


def placement_bbox_fit(bbox_min, bbox_max, detail):
    """Compare local bounds transformed by a row matrix with its stored sphere."""
    if bbox_min is None or bbox_max is None or detail is None:
        return None
    try:
        x0, y0, z0 = float(bbox_min[0]), float(bbox_min[1]), float(bbox_min[2])
        x1, y1, z1 = float(bbox_max[0]), float(bbox_max[1]), float(bbox_max[2])
        m = detail[12]
        origin = detail[18] if len(detail) > 18 else (0.0, 0.0, 0.0)
        ox = float(origin[0]) if len(origin) > 0 else 0.0
        oy = float(origin[1]) if len(origin) > 1 else 0.0
        oz = float(origin[2]) if len(origin) > 2 else 0.0

        transformed = []
        for x in (x0, x1):
            for y in (y0, y1):
                for z in (z0, z1):
                    transformed.append((
                        float(m[0]) * x + float(m[4]) * y + float(m[8]) * z + float(m[12]) + ox,
                        float(m[1]) * x + float(m[5]) * y + float(m[9]) * z + float(m[13]) + oy,
                        float(m[2]) * x + float(m[6]) * y + float(m[10]) * z + float(m[14]) + oz,
                    ))

        wx0 = min(point[0] for point in transformed)
        wy0 = min(point[1] for point in transformed)
        wz0 = min(point[2] for point in transformed)
        wx1 = max(point[0] for point in transformed)
        wy1 = max(point[1] for point in transformed)
        wz1 = max(point[2] for point in transformed)
        center = ((wx0 + wx1) * 0.5, (wy0 + wy1) * 0.5, (wz0 + wz1) * 0.5)
        radius = max(
            math.sqrt(
                (point[0] - center[0]) ** 2
                + (point[1] - center[1]) ** 2
                + (point[2] - center[2]) ** 2
            )
            for point in transformed
        )

        target = (float(detail[5]), float(detail[6]), float(detail[7]))
        target_radius = max(abs(float(detail[8])), 0.0001)
        center_error = math.sqrt(
            (center[0] - target[0]) ** 2
            + (center[1] - target[1]) ** 2
            + (center[2] - target[2]) ** 2
        )
        radius_ratio = max(radius / target_radius, 0.000001)
        score = (center_error / target_radius) + abs(math.log(radius_ratio))
        if not math.isfinite(score):
            return None
        return float(score), float(center_error), float(radius_ratio), center, float(radius)
    except Exception:
        return None


def placement_candidate_fit(obj, detail):
    """Compare an exact model candidate with the row's world-space bounding sphere."""
    if obj is None or detail is None:
        return None
    try:
        return placement_bbox_fit(
            obj.get("blds_bbox_min", None),
            obj.get("blds_bbox_max", None),
            detail,
        )
    except Exception:
        return None


def exact_candidate_needs_raw_variant(obj, detail):
    """Return True only when an exact WRLD submodel looks like an incomplete slice."""
    if obj is None or detail is None:
        return False
    try:
        kind = str(obj.get("blds_kind", ""))
    except Exception:
        kind = ""
    if kind != "IMG_WRLD_SUBMODEL_GROUP":
        return False
    try:
        target_radius = abs(float(detail[8]))
    except Exception:
        target_radius = 0.0
    if target_radius < float(EXACT_WRLD_SUBMODEL_RAW_VARIANT_MIN_TARGET_RADIUS):
        return False
    fit = placement_candidate_fit(obj, detail)
    if fit is not None:
        ratio = float(fit[2])
        if (
            ratio < float(EXACT_WRLD_SUBMODEL_RAW_VARIANT_MIN_RADIUS_RATIO)
            or ratio > float(EXACT_WRLD_SUBMODEL_RAW_VARIANT_MAX_RADIUS_RATIO)
        ):
            return True
    try:
        _verts, faces, _radius = object_geometry_counts_radius(obj)
    except Exception:
        faces = 0
    return bool(
        int(faces) <= int(EXACT_WRLD_SUBMODEL_RAW_VARIANT_SPARSE_FACE_LIMIT)
        and target_radius >= 8.0
    )


def choose_exact_resource_candidate(candidates, detail, max_fit_score=5.0):
    """Choose among exact table-backed variants using the placement row's own bounds."""
    unique = []
    seen = set()
    for item in candidates or []:
        if isinstance(item, tuple):
            obj = item[0]
            source = item[1] if len(item) > 1 else "exact_model"
            source_rank = int(item[2]) if len(item) > 2 else 0
        else:
            obj = item
            source = "exact_model"
            source_rank = 0
        if obj is None:
            continue
        signature = blds_object_geometry_signature(obj)
        key = signature if signature is not None else ("object", id(obj))
        if key in seen:
            continue
        seen.add(key)
        unique.append((obj, str(source), int(source_rank)))
    if not unique:
        return None, "", None, 0

    ranked = []
    for obj, source, source_rank in unique:
        fit = placement_candidate_fit(obj, detail)
        if fit is None:
            continue
        ranked.append((
            float(fit[0]),
            int(source_rank),
            -float(blds_mesh_quality_score(obj)),
            str(getattr(obj, "name", "")),
            obj,
            source,
            fit,
        ))
    if not ranked:
        chosen = None
        chosen_source = ""
        chosen_rank = 999999
        for obj, source, source_rank in unique:
            if chosen is None or source_rank < chosen_rank:
                chosen = obj
                chosen_source = source
                chosen_rank = source_rank
            elif source_rank == chosen_rank:
                chosen = choose_better_blds_candidate(chosen, obj)
                if chosen is obj:
                    chosen_source = source
        return chosen, chosen_source, None, len(unique)

    ranked.sort(key=lambda item: item[:4])
    best = ranked[0]
    if max_fit_score is not None and float(best[0]) > float(max_fit_score):
        return None, "", best[6], len(unique)
    return best[4], best[5], best[6], len(unique)


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
            # missing IPL path for VCS beach: rows such as RES=1828 / ROWLINK=1222..1241 live
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


def scan_continues_in_img_descriptor_proofs(stem: str, img_bytes: bytes, lvz_reader: LVZ.read_lvz, wanted_res_ids, placement_details=None, progress_callback=None) -> Dict[int, List[dict]]:
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
        return {res_id: list(cache.get(res_id) or []) for res_id in wanted if cache.get(res_id)}

    parser = LVZ.read_lvz(
        decomp_bytes=img_bytes,
        stem=stem,
        use_swizzle=bool(lvz_reader.use_swizzle),
        debug_print=False,
    )
    parser.material_by_res_index = lvz_reader.material_by_res_index

    details_by_res: Dict[int, List[object]] = {}
    for detail in placement_details or []:
        try:
            res_id = int(detail[0])
        except Exception:
            continue
        if res_id not in remaining:
            continue
        values = details_by_res.setdefault(res_id, [])
        if len(values) < int(CONTINUES_IN_IMG_MAX_FIT_DETAILS_PER_RES):
            values.append(detail)

    probe_to_res: Dict[int, set] = {}
    for res_id in remaining:
        for delta in CONTINUES_IN_IMG_TEXTURE_ID_DELTAS:
            probe = int(res_id) + int(delta)
            if 0 <= probe <= 0xFFFF:
                probe_to_res.setdefault(int(probe), set()).add(int(res_id))

    candidates_by_res: Dict[int, List[dict]] = {}
    n = len(img_bytes)
    stride = max(4, int(CONTINUES_IN_IMG_SCAN_STRIDE))
    scanned_descriptors = 0
    matched_descriptors = 0
    parser_failures = 0

    def candidate_descriptor_offsets():
        # Filter descriptor headers in vectorized chunks before invoking the
        # strict parser; a 200+ MB IMG otherwise requires millions of calls.
        if np is None:
            total = max(1, (max(0, n - 0x20) + stride - 1) // stride)
            step = 0
            off = 0
            while off + 0x20 <= n:
                step += 1
                if progress_callback is not None and (step % 65536 == 0 or step == total):
                    progress_callback(step, total)
                count16 = LVZ.read_u16(img_bytes, off)
                size16 = LVZ.read_u16(img_bytes, off + 2)
                if 0 < count16 <= 256 and size16 <= 0x8000:
                    expected24 = ((4 + count16 * 24 + 15) & ~15) - 4
                    expected22 = ((4 + count16 * 22 + 15) & ~15) - 4
                    if size16 == expected24 or size16 == expected22:
                        yield off
                off += stride
            return

        chunk_bytes = 8 * 1024 * 1024
        chunk_count = max(1, (n + chunk_bytes - 1) // chunk_bytes)
        for chunk_index, chunk_start in enumerate(range(0, n, chunk_bytes)):
            aligned_start = ((int(chunk_start) + stride - 1) // stride) * stride
            chunk_end = min(n, int(chunk_start) + chunk_bytes)
            if aligned_start + 4 > chunk_end:
                if progress_callback is not None:
                    progress_callback(chunk_index + 1, chunk_count)
                continue
            item_count = 1 + ((chunk_end - aligned_start - 4) // stride)
            words = np.ndarray(
                shape=(int(item_count),),
                dtype=np.dtype('<u4'),
                buffer=img_bytes,
                offset=int(aligned_start),
                strides=(int(stride),),
            )
            counts = words & np.uint32(0xFFFF)
            sizes = words >> np.uint32(16)
            expected24 = ((np.uint32(4) + counts * np.uint32(24) + np.uint32(15)) & np.uint32(0xFFFFFFF0)) - np.uint32(4)
            expected22 = ((np.uint32(4) + counts * np.uint32(22) + np.uint32(15)) & np.uint32(0xFFFFFFF0)) - np.uint32(4)
            mask = (counts > 0) & (counts <= 256) & (sizes <= 0x8000) & ((sizes == expected24) | (sizes == expected22))
            for relative_index in np.flatnonzero(mask):
                yield int(aligned_start + int(relative_index) * stride)
            if progress_callback is not None:
                progress_callback(chunk_index + 1, chunk_count)

    def register_candidate(target: int, candidate: dict):
        target = int(target)
        values = candidates_by_res.setdefault(target, [])
        raw_key = (int(candidate.get('raw_off', -1)), int(candidate.get('packet_end', -1)))
        replaced = False
        for index, old in enumerate(values):
            old_key = (int(old.get('raw_off', -1)), int(old.get('packet_end', -1)))
            if old_key == raw_key:
                if tuple(candidate.get('rank_key', ())) < tuple(old.get('rank_key', ())):
                    values[index] = candidate
                replaced = True
                break
        if not replaced:
            values.append(candidate)
        values.sort(key=lambda row: tuple(row.get('rank_key', (999999.0, 999999.0, 0.0))))
        del values[max(1, int(CONTINUES_IN_IMG_MAX_VARIANTS_PER_RES)):]

    for off in candidate_descriptor_offsets():
        descriptor = _probe_ps2_img_descriptor_for_continuation(img_bytes, off)
        if descriptor is None:
            continue
        scanned_descriptors += 1
        tex_ids = set(int(x) for x in descriptor.get("tex_ids", set()))
        target_res_ids = set()
        for tex_id in tex_ids:
            target_res_ids.update(probe_to_res.get(int(tex_id), set()))
        if not target_res_ids:
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
            continue

        score = score_mdl_groups_for_preselect(groups)
        if score < 0.0:
            continue
        gv = 0
        gf = 0
        xs = []
        ys = []
        zs = []
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
                    for x, y, z in verts:
                        xs.append(float(x))
                        ys.append(float(y))
                        zs.append(float(z))
        except Exception:
            pass
        if gv <= 0 or gf <= 0 or not xs:
            continue
        bbox_min = (min(xs), min(ys), min(zs))
        bbox_max = (max(xs), max(ys), max(zs))

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

            fit_values = []
            for detail in details_by_res.get(int(target), []):
                fit = placement_bbox_fit(bbox_min, bbox_max, detail)
                if fit is not None:
                    fit_values.append(float(fit[0]))
            best_fit = min(fit_values) if fit_values else None
            # Placement fit is authoritative. Descriptor richness only breaks
            # ties or ranks candidates when no row fit is available.
            if best_fit is None:
                rank_key = (1.0, 999999.0, -float(final_score))
            else:
                rank_key = (0.0, float(best_fit), -float(final_score))
            register_candidate(int(target), {
                'rank_key': rank_key,
                'placement_fit': best_fit,
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
                'bbox_min': bbox_min,
                'bbox_max': bbox_max,
                'format_tag': str(descriptor.get('format_tag', '')),
                'material_count': int(descriptor.get('count', 0)),
            })

    for res_id in remaining:
        cache[int(res_id)] = list(candidates_by_res.get(int(res_id), []))
    found = {res_id: list(cache.get(res_id) or []) for res_id in wanted if cache.get(res_id)}
    if IMPORT_VERBOSE_RESOURCE_BUILD_LOGS:
        LVZ.dbg(
            f"[continues-img-scan] wanted={len(wanted)} scanned_descriptors={scanned_descriptors} "
            f"matched_descriptors={matched_descriptors} parser_failures={parser_failures} "
            f"found_ids={len(found)} retained_variants={sum(len(v) for v in found.values())}"
        )
    return found


def build_empty_resource_continues_in_img_mdl_objects(stem: str, img_bytes: bytes, lvz_reader: LVZ.read_lvz, img_reader: LVZ.read_img, wanted_res_ids, source_lvz_path: str, img_name: Optional[str], placement_details=None, progress_callback=None) -> Dict[Tuple[int, int], bpy.types.Object]:
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
        placement_details=placement_details,
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
    flat_proofs = []
    for res_id in sorted(proofs):
        for variant_index, proof in enumerate(proofs[int(res_id)]):
            flat_proofs.append((int(res_id), int(variant_index), proof))
    total_proofs = len(flat_proofs)
    for global_index, (res_id, variant_index, proof) in enumerate(flat_proofs):
        if progress_callback is not None:
            progress_callback(global_index + 1, max(1, total_proofs))
        raw_off = int(proof.get('raw_off', -1))
        after = int(proof.get('after', -1))
        material_list = proof.get('material_list')
        groups = proof.get('groups') or []
        tex_ids = set(proof.get('tex_ids') or set())
        gv = int(proof.get('verts', 0))
        gf = int(proof.get('faces', 0))
        score = float(proof.get('score', 0.0))
        final_score = float(proof.get('final_score', score))
        placement_fit = proof.get('placement_fit', None)
        if material_list is None or not groups:
            continue
        obj, face_ranges = build_mesh_from_mdl_groups(f"{stem}_continued_img_res", int(res_id), groups)
        if obj is None:
            continue
        obj.name = f"{stem}{int(res_id)}__raw{int(variant_index):02d}"
        obj.data.name = obj.name
        slots_added = add_material_slots(obj, parser.material_by_res_index, material_list, face_ranges)
        obj["blds_kind"] = "IMG_CONTINUES_IN_IMG_MDL"
        obj["blds_res_index"] = int(res_id)
        obj["blds_img_continues_in_img"] = True
        obj["blds_img_continues_variant_index"] = int(variant_index)
        obj["blds_img_continues_raw_off"] = int(raw_off)
        obj["blds_img_continues_after"] = int(after)
        obj["blds_img_continues_final_score"] = float(final_score)
        if placement_fit is not None:
            obj["blds_img_continues_best_scan_fit"] = float(placement_fit)
        obj["blds_img_continues_material_ids"] = ",".join(str(int(x)) for x in sorted(tex_ids))
        obj["blds_source_lvz_path"] = str(source_lvz_path)
        if img_name:
            obj["blds_source_img_path"] = str(Path(source_lvz_path).with_name(img_name))
        key = (-200000 - int(global_index), int(res_id))
        out[key] = obj
        if logged < int(CONTINUES_IN_IMG_MAX_LOG_ROWS):
            fit_text = "none" if placement_fit is None else f"{float(placement_fit):.3f}"
            LVZ.dbg(
                f"[continues-img] RES={int(res_id)} variant={int(variant_index)} reason=CONTINUES_IN_IMG "
                f"img={img_name or '<companion IMG>'} raw=0x{int(raw_off):08X} stream_end=0x{int(after):08X} "
                f"materials={','.join(str(int(x)) for x in sorted(tex_ids))} geom={int(gv)}v/{int(gf)}f "
                f"slots={int(slots_added)} score={float(score):.3f} placementFit={fit_text}"
            )
            logged += 1

    LVZ.dbg(
        f"[continues-img] descriptor scan wanted={len(wanted)} "
        f"found_ids={len(proofs)} variants={len(flat_proofs)} created={len(out)}"
    )
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
        # Keep one representative for every distinct exact geometry variant.
        # Several sectors can legitimately store different models under the same
        # resource ID; the placement row's world-space sphere chooses the correct
        # variant later instead of discarding the whole resource ID.
        best_by_res_signature = {}
        signatures_by_res = {}
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
            signature = mdl_groups_geometry_signature(material_list, groups)
            if signature is None:
                skipped_non_geometry += 1
                continue
            signatures_by_res.setdefault(res_id, set()).add(signature)
            candidate_key = (int(res_id), signature)
            previous = best_by_res_signature.get(candidate_key)
            if previous is None or score > previous[0]:
                best_by_res_signature[candidate_key] = (score, overlay, material_list, groups)

        variant_res_ids = {
            int(res_id) for res_id, signatures in signatures_by_res.items()
            if len(signatures) > 1
        }
        try:
            img_reader.last_ambiguous_overlay_res_ids = set(variant_res_ids)
        except Exception:
            pass
        overlay_rows = []
        for score, overlay, material_list, groups in best_by_res_signature.values():
            sector_index = int(overlay.get("sector_index", -1))
            res_id = int(overlay.get("res_id", -1))
            key = (sector_index, res_id)
            # Resource tables normally contain one entry per ID in each sector.
            # Keep the richer object only if malformed duplicate rows share a key.
            existing = preselected_by_key.get(key)
            if existing is not None:
                existing_score = score_mdl_groups_for_preselect(existing[1])
                if existing_score >= score:
                    continue
                try:
                    old_index = next(
                        index for index, row in enumerate(overlay_rows)
                        if (int(row.get("sector_index", -1)), int(row.get("res_id", -1))) == key
                    )
                    overlay_rows.pop(old_index)
                except Exception:
                    pass
            overlay_rows.append(overlay)
            preselected_by_key[key] = (material_list, groups)
        preselect_dropped_rows = max(0, preselect_input_rows - len(overlay_rows))
        if variant_res_ids:
            LVZ.dbg(f"[exact-models] resource IDs with multiple exact variants retained: {len(variant_res_ids)}")

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



def build_official_area_resource_mdl_objects(stem: str, img_bytes: bytes,
                                             lvz_reader: LVZ.read_lvz,
                                             img_reader: LVZ.read_img,
                                             source_lvz_path: str,
                                             img_name: Optional[str],
                                             needed_res_ids=None,
                                             progress_callback=None) -> List[bpy.types.Object]:
    """Build exact models from the master AreaInfo[] -> AERA AreaResource[] path."""
    area_records = img_reader.find_area_info_records_from_lvz()
    if not area_records:
        LVZ.dbg("[area-resource] no proven master AreaInfo/AERA table found")
        return []

    wanted = None
    if needed_res_ids is not None:
        wanted = {int(value) for value in needed_res_ids if int(value) >= 0}
    rows = img_reader.collect_area_resources(
        area_records,
        wanted_res_ids=wanted,
        max_resource_id=getattr(lvz_reader, "master_resource_count", None) or None,
        progress_callback=progress_callback,
    )

    parser = LVZ.read_lvz(
        decomp_bytes=img_bytes,
        stem=stem,
        use_swizzle=bool(lvz_reader.use_swizzle),
        debug_print=False,
    )
    parser.material_by_res_index = lvz_reader.material_by_res_index

    objects: List[bpy.types.Object] = []
    seen = set()
    skipped_non_geometry = 0
    total_rows = len(rows)
    for row_number, row in enumerate(rows):
        if progress_callback is not None and (row_number % 8 == 0 or row_number + 1 == total_rows):
            try:
                progress_callback(row_number + 1, total_rows)
            except Exception:
                pass
        area_index = int(row.get("area_index", -1))
        resource_index = int(row.get("resource_index", -1))
        res_id = int(row.get("res_id", -1))
        raw_off = int(row.get("raw_off", -1))
        resource_end = int(row.get("resource_end", len(img_bytes)))
        key = (area_index, res_id, raw_off)
        if key in seen:
            continue
        seen.add(key)

        try:
            material_list = parser.parse_mdl_material_list(raw_off, max_end=resource_end)
            groups, _after = parser.parse_mdl_geometry_after_list(material_list, max_end=resource_end)
            parser.assign_materials_by_strip_bytes(material_list, groups)
        except Exception as exc:
            skipped_non_geometry += 1
            if IMPORT_VERBOSE_RESOURCE_BUILD_LOGS:
                LVZ.dbg(
                    f"[area-resource] parse failed area={area_index} row={resource_index} "
                    f"RES={res_id} raw=0x{raw_off:08X}: {exc}"
                )
            continue

        obj, face_ranges = build_mesh_from_mdl_groups(
            f"{stem}_aera{area_index:03d}_res", res_id, groups
        )
        if obj is None:
            skipped_non_geometry += 1
            continue

        obj.name = f"{stem}_aera{area_index:03d}_res{res_id}_{len(objects):04d}"
        obj.data.name = obj.name
        slots_added = add_material_slots(
            obj, parser.material_by_res_index, material_list, face_ranges
        )
        obj["blds_kind"] = "IMG_AERA_RESOURCE_MDL"
        obj["blds_type"] = "OBJECT"
        obj["blds_res_index"] = int(res_id)
        obj["blds_img_area_index"] = int(area_index)
        obj["blds_img_area_cell_x"] = int(row.get("area_cell_x", 0))
        obj["blds_img_area_cell_y"] = int(row.get("area_cell_y", 0))
        obj["blds_img_area_resource_index"] = int(resource_index)
        obj["blds_img_area_secondary_id"] = int(row.get("secondary_id", -1))
        obj["blds_img_area_resource_row_off"] = int(row.get("resource_row_off", -1))
        obj["blds_img_area_raw_ptr"] = int(row.get("raw_ptr", 0))
        obj["blds_img_area_raw_off"] = int(raw_off)
        obj["blds_img_area_resource_end"] = int(resource_end)
        obj["blds_img_area_cont"] = int(row.get("cont", 0))
        obj["blds_source_lvz_path"] = str(source_lvz_path)
        if img_name:
            obj["blds_source_img_path"] = str(Path(source_lvz_path).with_name(img_name))
        objects.append(obj)

        if res_id in (1179, 1725, 1802, 1828, 1881, 1887, 1989, 2184, 3528) or len(objects) <= 16:
            LVZ.dbg(
                f"[area-resource] exact RES={res_id} area={area_index} row={resource_index} "
                f"raw=0x{raw_off:08X} format={material_list.format_tag} "
                f"groups={len(groups)} materials={slots_added} object={obj.name}"
            )

    stats = getattr(img_reader, "last_area_resource_stats", {}) or {}
    LVZ.dbg(
        f"[area-resource] master AERA areas={len(area_records)} rows={stats.get('rows', 0)} "
        f"wanted_rows={stats.get('wanted_rows', 0)} descriptor_rows={stats.get('accepted', 0)} "
        f"models={len(objects)} skipped_non_geometry={skipped_non_geometry}"
    )
    return objects

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


def get_or_create_import_collection(collection_name: str, parent_collection=None):
    """Get/create one collection and link it under the requested parent only."""
    try:
        parent = parent_collection or bpy.context.scene.collection
        existing = bpy.data.collections.get(collection_name)
        if existing is None:
            existing = bpy.data.collections.new(collection_name)
        try:
            if existing.name not in {child.name for child in parent.children}:
                parent.children.link(existing)
        except Exception:
            try:
                parent.children.link(existing)
            except Exception:
                pass
        return existing
    except Exception:
        return None


def blds_clear_collection_tree_objects(collection):
    if collection is None:
        return
    try:
        for child in list(collection.children):
            blds_clear_collection_tree_objects(child)
    except Exception:
        pass
    try:
        for obj in list(collection.objects):
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except Exception:
                pass
    except Exception:
        pass


def blds_remove_legacy_import_collections():
    """Remove collection names created by pre-1.0.21 LVZ imports.

    Those collections were global rather than tied to one LVZ+IMG pair, so
    leaving them in the scene makes a corrected import appear to have duplicate
    or detached effects. Only exact BLeeds-owned legacy names are touched.
    """
    for collection_name in ("BLeeds Leeds 2DFX", "BLeeds IMG linked placements"):
        try:
            collection = bpy.data.collections.get(collection_name)
        except Exception:
            collection = None
        if collection is None:
            continue
        blds_clear_collection_tree_objects(collection)
        try:
            bpy.data.collections.remove(collection, do_unlink=True)
            LVZ.dbg(f"[collections] removed legacy global collection: {collection_name}")
        except Exception:
            try:
                for owner in list(bpy.data.collections):
                    try:
                        if collection.name in {child.name for child in owner.children}:
                            owner.children.unlink(collection)
                    except Exception:
                        pass
                try:
                    if collection.name in {child.name for child in bpy.context.scene.collection.children}:
                        bpy.context.scene.collection.children.unlink(collection)
                except Exception:
                    pass
                bpy.data.collections.remove(collection)
            except Exception:
                pass


def blds_import_pair_base_name(lvz_path: str, img_name: Optional[str]) -> str:
    lvz_stem = normalized_copy_stem(Path(lvz_path).stem).strip() or Path(lvz_path).stem
    img_stem = normalized_copy_stem(Path(img_name).stem).strip() if img_name else ""
    if img_stem and img_stem.lower() != lvz_stem.lower():
        return f"{lvz_stem} + {img_stem}"
    return lvz_stem


def blds_prepare_import_collection_tree(lvz_path: str, img_name: Optional[str]):
    """Create one source-named hierarchy for the LVZ+IMG pair.

    Example:
        beach [LVZ+IMG]
          beach Objects
          beach Linked Placements
          beach 2DFX
    """
    global _ACTIVE_IMPORT_ROOT_COLLECTION
    global _ACTIVE_IMPORT_OBJECTS_COLLECTION
    global _ACTIVE_IMPORT_LINKED_COLLECTION
    global _ACTIVE_IMPORT_2DFX_COLLECTION

    blds_remove_legacy_import_collections()
    base = blds_import_pair_base_name(lvz_path, img_name)
    root_name = f"{base} [LVZ+IMG]"
    scene_root = bpy.context.scene.collection
    root = get_or_create_import_collection(root_name, scene_root)
    objects = get_or_create_import_collection(f"{base} Objects", root)
    linked = get_or_create_import_collection(f"{base} Linked Placements", root)
    effects = get_or_create_import_collection(f"{base} 2DFX", root)

    # A fresh import replaces only BLeeds-owned children for this exact pair.
    for collection in (objects, linked, effects):
        blds_clear_collection_tree_objects(collection)
    try:
        root["blds_kind"] = "LVZ_IMG_IMPORT_ROOT"
        root["blds_source_lvz_path"] = str(lvz_path)
        root["blds_source_img_path"] = str(Path(lvz_path).with_name(img_name)) if img_name else ""
        root["blds_import_pair_name"] = str(base)
        objects["blds_kind"] = "LVZ_IMG_OBJECTS_COLLECTION"
        linked["blds_kind"] = "LVZ_IMG_LINKED_COLLECTION"
        effects["blds_kind"] = "LVZ_IMG_2DFX_COLLECTION"
    except Exception:
        pass

    _ACTIVE_IMPORT_ROOT_COLLECTION = root
    _ACTIVE_IMPORT_OBJECTS_COLLECTION = objects
    _ACTIVE_IMPORT_LINKED_COLLECTION = linked
    _ACTIVE_IMPORT_2DFX_COLLECTION = effects
    return root, objects, linked, effects


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

    # Legacy helper for a shared internal ROWLINK value. VCS beach has
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



def blds_placement_report_key(detail):
    try:
        return (int(detail[1]), int(detail[2]), int(detail[3]), int(detail[0]))
    except Exception:
        return None


def blds_make_placement_report_row(detail, index: int = -1) -> Dict[str, object]:
    row: Dict[str, object] = {
        "index": int(index),
        "status": "NOT_PROCESSED",
        "status_reason": "",
    }
    try:
        matrix = tuple(float(value) for value in detail[12])
        origin = detail[18] if len(detail) > 18 else (0.0, 0.0, 0.0)
        origin = (float(origin[0]), float(origin[1]), float(origin[2]))
        row.update({
            "res_id": int(detail[0]),
            "container": int(detail[1]),
            "rel_off": int(detail[2]),
            "abs_off": int(detail[1]) + int(detail[2]),
            "row_link_raw": int(detail[3]),
            "row_link_id": int(detail[4]),
            "row_link_high_bit": bool(int(detail[3]) & 0x8000),
            # Compatibility aliases for older scripts; UI/report labels no longer call this IPL.
            "ipl_raw": int(detail[3]),
            "ipl_id": int(detail[4]),
            "ipl_high_bit": bool(int(detail[3]) & 0x8000),
            "sphere_x": float(detail[5]),
            "sphere_y": float(detail[6]),
            "sphere_z": float(detail[7]),
            "sphere_radius": float(detail[8]),
            "basis_scale_x": float(detail[9]),
            "basis_scale_y": float(detail[10]),
            "basis_scale_z": float(detail[11]),
            "matrix": matrix,
            "pass_index": int(detail[13]),
            "pass_name": str(detail[14]),
            "sector_index": int(detail[15]),
            "sector_x": int(detail[16]),
            "sector_y": int(detail[17]),
            "sector_origin": origin,
            "sector_row_index": int(detail[19]) if len(detail) > 19 else -1,
            "row_translation_x": float(matrix[12]),
            "row_translation_y": float(matrix[13]),
            "row_translation_z": float(matrix[14]),
            "world_translation_x": float(matrix[12]) + origin[0],
            "world_translation_y": float(matrix[13]) + origin[1],
            "world_translation_z": float(matrix[14]) + origin[2],
        })
    except Exception as exc:
        row["parse_error"] = str(exc)
    return row


def blds_report_object_prop(obj, key: str, default=None):
    try:
        return obj.get(key, default)
    except Exception:
        return default


def blds_report_mark_status(report_row: Optional[Dict[str, object]], status: str, reason: str = ""):
    if report_row is None:
        return
    report_row["status"] = str(status)
    report_row["status_reason"] = str(reason or "")


def blds_report_mark_placed(report_row: Optional[Dict[str, object]], obj, base_obj, source_model_id: int,
                            source_label: str, matrix_mode: str, instance_index: int):
    if report_row is None:
        return
    report_row["status"] = "PLACED"
    report_row["status_reason"] = ""
    report_row["object_name"] = str(getattr(obj, "name", ""))
    report_row["base_object_name"] = str(getattr(base_obj, "name", ""))
    report_row["source_model_id"] = int(source_model_id)
    report_row["selected_source"] = str(source_label or "exact-res")
    report_row["matrix_mode"] = str(matrix_mode or "")
    report_row["instance_index"] = int(instance_index)
    try:
        report_row["base_kind"] = str(blds_report_object_prop(base_obj, "blds_kind", ""))
        report_row["base_res_id"] = int(blds_report_object_prop(base_obj, "blds_res_index", -1))
        report_row["base_parent_res_id"] = int(blds_report_object_prop(base_obj, "blds_parent_res_index", -1))
        report_row["base_group_index"] = int(blds_report_object_prop(base_obj, "blds_group_index", -1))
        report_row["base_continues_in_img"] = bool(blds_report_object_prop(base_obj, "blds_img_continues_in_img", False))
        for prop_name in (
            "blds_img_raw_off", "blds_raw_off", "blds_resource_row_off",
            "blds_img_resource_row_off", "blds_img_cont", "blds_img_rel_off",
            "blds_img_sector_index", "blds_img_row_index",
        ):
            value = blds_report_object_prop(base_obj, prop_name, None)
            if value is not None:
                report_row["base_" + prop_name] = value
        gv, gf, gr = object_geometry_counts_radius(obj)
        report_row["geometry_vertices"] = int(gv)
        report_row["geometry_faces"] = int(gf)
        report_row["geometry_radius"] = float(gr)
    except Exception as exc:
        report_row["placed_metadata_error"] = str(exc)
    try:
        matrix_values = matrix_to_report_values(obj.matrix_world)
        report_row["applied_matrix"] = tuple(float(value) for value in matrix_values)
    except Exception:
        pass


def blds_2dfx_effect_type_name(effect_type: int) -> str:
    return {0: "LIGHT", 1: "PARTICLE", 2: "ATTRACTOR", 3: "PED_BEHAVIOUR"}.get(int(effect_type), "UNKNOWN")


def blds_format_dtz_model_meta(model_id: int, model_meta_by_id: Dict[int, Dict[str, object]]) -> str:
    meta = model_meta_by_id.get(int(model_id))
    if not meta:
        return "NO_MODEL_INFO"
    return (
        f"ptr=0x{int(meta.get('model_pointer_raw', 0)):08X} "
        f"info=0x{int(meta.get('model_info_abs', 0)):08X} "
        f"type={int(meta.get('model_type', -1))} "
        f"num2dfx={int(meta.get('num_effects', 0))} "
        f"first2dfx={int(meta.get('effect_index', -1))} "
        f"raw20={str(meta.get('raw_0x20', ''))}"
    )


def blds_write_placement_res_report(lvz_path: str, details, report_rows_by_key: Dict[Tuple[int, int, int, int], Dict[str, object]],
                                    model_2dfx_by_id: Optional[Dict[int, List[Dict[str, object]]]] = None,
                                    model_2dfx_summary: Optional[Dict[str, object]] = None,
                                    placement_identity_by_key: Optional[Dict[Tuple[int, int, int, int], Dict[str, object]]] = None,
                                    identity_summary: Optional[Dict[str, object]] = None) -> str:
    if not PLACEMENT_RES_TXT_REPORT_ENABLED or not lvz_path:
        return ""
    model_2dfx_by_id = model_2dfx_by_id or {}
    model_2dfx_summary = model_2dfx_summary or {}
    placement_identity_by_key = placement_identity_by_key or {}
    identity_summary = identity_summary or {}
    model_meta_by_id = model_2dfx_summary.get("model_meta_by_id", {}) or {}
    out_path = str(Path(lvz_path).with_suffix("")) + "_blds_placement_res_report.txt"

    ordered_rows = []
    for index, detail in enumerate(details or []):
        key = blds_placement_report_key(detail)
        row = report_rows_by_key.get(key)
        if row is None:
            row = blds_make_placement_report_row(detail, index=index)
        else:
            row["index"] = int(index)
        identity = placement_identity_by_key.get(key, {}) or {}
        row["game_model_id"] = int(identity.get("game_model_id", -1))
        row["model_name"] = str(identity.get("model_name", ""))
        row["identity_source"] = str(identity.get("source", "UNRESOLVED"))
        row["identity_area_index"] = int(identity.get("area_index", -1))
        row["identity_area_resource_index"] = int(identity.get("area_resource_index", -1))
        row["identity_area_resource_row_off"] = int(identity.get("area_resource_row_off", -1))
        row["identity_area_resource_raw_off"] = int(identity.get("area_resource_raw_off", -1))
        ordered_rows.append(row)

    from collections import Counter, defaultdict
    status_counts = Counter(str(row.get("status", "UNKNOWN")) for row in ordered_rows)
    pair_rows = defaultdict(list)
    res_rows = defaultdict(list)
    rowlink_rows = defaultdict(list)
    for row in ordered_rows:
        res_id = int(row.get("res_id", -1))
        rowlink = int(row.get("ipl_id", -1))
        pair_rows[(res_id, rowlink)].append(row)
        res_rows[res_id].append(row)
        rowlink_rows[rowlink].append(row)

    target_ids = set(int(value) for value in PLACEMENT_RES_REPORT_TARGET_IDS)
    target_ids.update(
        int(row.get("res_id", -1))
        for row in ordered_rows
        if str(row.get("status", "")) == "MISSING"
    )

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("BLeeds 1.0.21 exact RES / GAME.DTZ entity-pool 2DFX / source collection report\n")
        f.write("=" * 78 + "\n")
        f.write(f"LVZ: {lvz_path}\n")
        f.write(f"Placement rows retained: {len(ordered_rows)}\n")
        f.write("Status counts: " + ", ".join(f"{key}={value}" for key, value in sorted(status_counts.items())) + "\n")
        f.write(f"Unique RES ids: {len(res_rows)}\n")
        f.write(f"Unique internal ROWLINK ids: {len(rowlink_rows)}\n")
        f.write(f"Unique RES/ROWLINK pairs: {len(pair_rows)}\n")
        f.write(f"Master AERA chunks: {int(identity_summary.get('areas', 0))}\n")
        f.write(f"AERA RES secondary mappings used for geometry metadata: {int(identity_summary.get('mapped_res_ids', 0))}\n")
        f.write(f"Placement rows carrying AERA secondary metadata: {int(identity_summary.get('matched_rows', 0))}\n")
        f.write(f"Placement rows without AERA secondary metadata: {int(identity_summary.get('unresolved', 0))}\n")
        f.write(f"AERA conflicting RES secondary values rejected: {int(identity_summary.get('conflicting_res_ids', 0))}\n")
        f.write(f"GAME.DTZ: {model_2dfx_summary.get('source_path', '') or 'none'}\n")
        f.write(f"GAME.DTZ status: {model_2dfx_summary.get('status', 'not parsed')}\n")
        f.write(f"GAME.DTZ model infos: {int(model_2dfx_summary.get('ide_count', 0))}\n")
        f.write(f"GAME.DTZ global C2dEffect rows: {int(model_2dfx_summary.get('effect_count', 0))}\n")
        effect_type_counts = model_2dfx_summary.get("effect_type_counts", {}) or {}
        f.write(
            "GAME.DTZ effect types: "
            f"LIGHT={int(effect_type_counts.get(0, 0))}, "
            f"PARTICLE={int(effect_type_counts.get(1, 0))}, "
            f"ATTRACTOR={int(effect_type_counts.get(2, 0))}, "
            f"PED_BEHAVIOUR={int(effect_type_counts.get(3, 0))}\n"
        )
        f.write("2DFX Blender helpers: {}\n".format(
            "ENABLED" if bool(model_2dfx_summary.get("helpers_enabled", False)) else "DISABLED FOR THIS IMPORT"
        ))
        f.write("2DFX ownership: allocated GAME.DTZ BUILDING/TREADABLE/DUMMY CEntity.modelIndex\n")
        f.write("2DFX position transform: CEntity world matrix × native C2dEffect model-space position\n")
        pool_stats = model_2dfx_summary.get("entity_pool_stats", {}) or {}
        for pool_name in ("BUILDING", "TREADABLE", "DUMMY"):
            stats = pool_stats.get(pool_name, {}) or {}
            f.write(
                f"GAME.DTZ {pool_name} pool: size={int(stats.get('size', 0))} "
                f"allocated={int(stats.get('allocated', 0))} "
                f"instances_with_effects={int(stats.get('with_effects', 0))} "
                f"effect_helpers_global={int(stats.get('effect_rows', 0))}\n"
            )
        f.write(f"GAME.DTZ allocated entity instances with effects: {int(model_2dfx_summary.get('entity_instances_with_effects', 0))}\n")
        f.write(f"GAME.DTZ entity effect helpers before level filtering: {int(model_2dfx_summary.get('entity_effect_rows', 0))}\n")
        f.write(f"Current LVZ concrete sector cells: {int(model_2dfx_summary.get('active_sector_cells', 0))}\n")
        f.write(f"2DFX entity instances selected for this LVZ: {int(model_2dfx_summary.get('entity_instances_selected', 0))}\n")
        f.write(f"2DFX entity instances attached to matching map objects: {int(model_2dfx_summary.get('entity_instances_attached', 0))}\n")
        f.write(f"2DFX independent entity instances kept in the map 2DFX collection: {int(model_2dfx_summary.get('entity_instances_unattached', 0))}\n")
        f.write(f"2DFX helpers imported: {int(model_2dfx_summary.get('effects_imported', 0))}\n")
        f.write(f"2DFX selected entity instances by pool: {model_2dfx_summary.get('entity_selected_by_pool', {}) or {}}\n")
        f.write(f"2DFX selection reasons: {model_2dfx_summary.get('entity_selected_by_reason', {}) or {}}\n")
        f.write(f"2DFX imported helpers by pool: {model_2dfx_summary.get('entity_imported_helpers_by_pool', {}) or {}}\n")
        f.write("Collection ownership: one source-named LVZ+IMG root with Objects, Linked Placements, and 2DFX children.\n")
        f.write("Visible geometry ownership: exact streamed RES only\n")
        f.write("ROWLINK is diagnostic placement data only; it is never geometry or 2DFX identity.\n\n")

        f.write("FIELD MEANINGS\n")
        f.write("- RES: exact streamed geometry/resource id from placement row +0x02.\n")
        f.write("- ROWLINK: internal placement row link from +0x00; not an IDE/model id.\n")
        f.write("- AERA_SECONDARY: secondary value from the exact AERA resource row; retained as geometry metadata.\n")
        f.write("- 2DFX GAME_MODEL: authoritative model index read from GAME.DTZ CEntity.modelIndex.\n")
        f.write("- 2DFX entity pool/index: actual BUILDING, TREADABLE, or DUMMY instance that owns the effects.\n")
        f.write("- selected geometry: exact-RES candidate actually placed, or MISSING.\n\n")

        f.write("WATCHED / MISSING RES IDS\n")
        f.write("-" * 78 + "\n")
        for res_id in sorted(value for value in target_ids if value >= 0):
            rows = res_rows.get(res_id, [])
            if not rows:
                f.write(f"RES={res_id}: NO RETAINED PLACEMENT ROW\n")
                continue
            statuses = Counter(str(row.get("status", "UNKNOWN")) for row in rows)
            rowlinks = Counter(int(row.get("ipl_id", -1)) for row in rows)
            game_models = Counter(int(row.get("game_model_id", -1)) for row in rows)
            f.write(
                f"RES={res_id}: rows={len(rows)} statuses={dict(sorted(statuses.items()))} "
                f"ROWLINK={dict(sorted(rowlinks.items()))} AERA_SECONDARY={dict(sorted(game_models.items()))}\n"
            )
            for row in rows:
                f.write(
                    f"  index={int(row.get('index', -1))} status={row.get('status', '')} "
                    f"ROWLINK={int(row.get('ipl_id', -1))} AERA_SECONDARY={int(row.get('game_model_id', -1))} "
                    f"pass={row.get('pass_name', '')} sector={int(row.get('sector_index', -1))} "
                    f"world=({float(row.get('world_translation_x', 0.0)):.6f},"
                    f"{float(row.get('world_translation_y', 0.0)):.6f},"
                    f"{float(row.get('world_translation_z', 0.0)):.6f}) "
                    f"source={row.get('selected_source', '') or '-'} object={row.get('object_name', '') or '-'} "
                    f"reason={row.get('status_reason', '')}\n"
                )
        f.write("\n")

        f.write("RES / ROWLINK / AERA_SECONDARY SUMMARY\n")
        f.write("-" * 78 + "\n")
        for (res_id, rowlink), rows in sorted(pair_rows.items()):
            statuses = Counter(str(row.get("status", "UNKNOWN")) for row in rows)
            passes = Counter(str(row.get("pass_name", "UNKNOWN")) for row in rows)
            game_model_id = int(rows[0].get("game_model_id", -1))
            f.write(
                f"RES={res_id} ROWLINK={rowlink} AERA_SECONDARY={game_model_id} rows={len(rows)} "
                f"statuses={dict(sorted(statuses.items()))} passes={dict(sorted(passes.items()))} "
                f"AERA_secondary_DTZ_range_diagnostic={len(model_2dfx_by_id.get(game_model_id, []))}\n"
            )
        f.write("\n")

        f.write("ALL PLACEMENT ROWS\n")
        f.write("=" * 78 + "\n")
        for row in ordered_rows:
            res_id = int(row.get("res_id", -1))
            rowlink = int(row.get("ipl_id", -1))
            game_model_id = int(row.get("game_model_id", -1))
            f.write(
                f"[{int(row.get('index', -1)):05d}] {row.get('status', 'UNKNOWN')} "
                f"RES={res_id} ROWLINK={rowlink} "
                f"ROWLINKraw=0x{int(row.get('row_link_raw', row.get('ipl_raw', 0))):04X} "
                f"highbit={int(bool(row.get('row_link_high_bit', row.get('ipl_high_bit', False))))} "
                f"AERA_SECONDARY={game_model_id}\n"
            )
            f.write(
                f"  placement: sector={int(row.get('sector_index', -1))} "
                f"sectorXY=({int(row.get('sector_x', 0))},{int(row.get('sector_y', 0))}) "
                f"sectorRow={int(row.get('sector_row_index', -1))} "
                f"pass={row.get('pass_name', '')}/{int(row.get('pass_index', -1))}\n"
            )
            f.write(
                f"  offsets: contIMG=0x{int(row.get('container', 0)):08X} "
                f"rel=0x{int(row.get('rel_off', 0)):08X} abs=0x{int(row.get('abs_off', 0)):08X}\n"
            )
            f.write(
                f"  sphere: ({float(row.get('sphere_x', 0.0)):.9f}, {float(row.get('sphere_y', 0.0)):.9f}, "
                f"{float(row.get('sphere_z', 0.0)):.9f}, r={float(row.get('sphere_radius', 0.0)):.9f})\n"
            )
            f.write(
                f"  basisScale: ({float(row.get('basis_scale_x', 0.0)):.9f}, "
                f"{float(row.get('basis_scale_y', 0.0)):.9f}, {float(row.get('basis_scale_z', 0.0)):.9f})\n"
            )
            origin = row.get("sector_origin", (0.0, 0.0, 0.0))
            f.write(f"  sectorOrigin: ({float(origin[0]):.9f}, {float(origin[1]):.9f}, {float(origin[2]):.9f})\n")
            f.write(
                f"  rowTranslation: ({float(row.get('row_translation_x', 0.0)):.9f}, "
                f"{float(row.get('row_translation_y', 0.0)):.9f}, {float(row.get('row_translation_z', 0.0)):.9f})\n"
            )
            f.write(
                f"  worldTranslation: ({float(row.get('world_translation_x', 0.0)):.9f}, "
                f"{float(row.get('world_translation_y', 0.0)):.9f}, {float(row.get('world_translation_z', 0.0)):.9f})\n"
            )
            matrix = tuple(row.get("matrix", ()))
            if len(matrix) == 16:
                f.write("  rowMatrix:\n")
                for matrix_row in range(4):
                    values = matrix[matrix_row * 4:(matrix_row + 1) * 4]
                    f.write("    " + " ".join(f"{float(value): .9f}" for value in values) + "\n")
            f.write(
                f"  identity: source={row.get('identity_source', '') or 'UNRESOLVED'} "
                f"AERA_SECONDARY={game_model_id} "
                f"AERA_area={int(row.get('identity_area_index', -1))} "
                f"AERA_resource={int(row.get('identity_area_resource_index', -1))} "
                f"AERA_row=0x{int(row.get('identity_area_resource_row_off', -1)) & 0xFFFFFFFF:08X} "
                f"AERA_payload=0x{int(row.get('identity_area_resource_raw_off', -1)) & 0xFFFFFFFF:08X}\n"
            )
            f.write(
                f"  selectedGeometry: object={row.get('object_name', '') or '-'} "
                f"base={row.get('base_object_name', '') or '-'} kind={row.get('base_kind', '') or '-'} "
                f"baseRES={int(row.get('base_res_id', -1))} sourceModel={int(row.get('source_model_id', -1))} "
                f"source={row.get('selected_source', '') or '-'} matrixMode={row.get('matrix_mode', '') or '-'}\n"
            )
            f.write(
                f"  geometry: vertices={int(row.get('geometry_vertices', 0))} faces={int(row.get('geometry_faces', 0))} "
                f"radius={float(row.get('geometry_radius', 0.0)):.9f} "
                f"parentRES={int(row.get('base_parent_res_id', -1))} group={int(row.get('base_group_index', -1))} "
                f"continuesIMG={int(bool(row.get('base_continues_in_img', False)))}\n"
            )
            candidate_rows = row.get("exact_candidates", []) or []
            f.write(
                f"  exactCandidatePool: captured={len(candidate_rows)} "
                f"total={int(row.get('exact_candidate_total', len(candidate_rows)))}\n"
            )
            for candidate in candidate_rows:
                fit_score = candidate.get("fit_score", None)
                fit_text = "no-fit"
                if fit_score is not None:
                    fit_text = (
                        f"score={float(fit_score):.9f} "
                        f"centerError={float(candidate.get('fit_center_error', 0.0)):.9f} "
                        f"radiusRatio={float(candidate.get('fit_radius_ratio', 0.0)):.9f}"
                    )
                f.write(
                    f"    candidate source={candidate.get('source', '')} rank={int(candidate.get('rank', -1))} "
                    f"name={candidate.get('name', '') or '-'} kind={candidate.get('kind', '') or '-'} "
                    f"RES={int(candidate.get('res_id', -1))} parentRES={int(candidate.get('parent_res_id', -1))} "
                    f"group={int(candidate.get('group_index', -1))} continuesIMG={int(bool(candidate.get('continues_img', False)))} "
                    f"geom={int(candidate.get('vertices', 0))}v/{int(candidate.get('faces', 0))}f/"
                    f"r{float(candidate.get('radius', 0.0)):.9f} {fit_text}\n"
                )
            if row.get("status_reason"):
                f.write(f"  statusReason: {row.get('status_reason')}\n")
            f.write(
                f"  GAME.DTZ diagnostic range at AERA_SECONDARY={game_model_id}: "
                f"{blds_format_dtz_model_meta(game_model_id, model_meta_by_id)}\n"
            )
            effects = model_2dfx_by_id.get(game_model_id, [])
            f.write(f"  GAME.DTZ effect rows at this diagnostic AERA secondary: {len(effects)}\n")
            for effect in effects[:int(PLACEMENT_RES_REPORT_EFFECT_LIMIT)]:
                f.write(
                    f"    effect global={int(effect.get('global_index', -1))} "
                    f"modelLocal={int(effect.get('model_effect_index', -1))} "
                    f"type={int(effect.get('effect_type', -1))}/"
                    f"{blds_2dfx_effect_type_name(int(effect.get('effect_type', -1)))} "
                    f"local=({float(effect.get('x', 0.0)):.9f}, {float(effect.get('y', 0.0)):.9f}, "
                    f"{float(effect.get('z', 0.0)):.9f}) rgba=({int(effect.get('r', 0))},"
                    f"{int(effect.get('g', 0))},{int(effect.get('b', 0))},{int(effect.get('a', 0))}) "
                    f"raw={str(effect.get('raw_hex', ''))}\n"
                )
            if len(effects) > int(PLACEMENT_RES_REPORT_EFFECT_LIMIT):
                f.write(f"    ... {len(effects) - int(PLACEMENT_RES_REPORT_EFFECT_LIMIT)} more effect rows\n")
            f.write("\n")

    LVZ.dbg(f"[placement-report] wrote exact RES/AERA-secondary/entity-2DFX report: {out_path}")
    LVZ.dbg(f"[placement-report] rows={len(ordered_rows)} statuses={dict(sorted(status_counts.items()))}")
    return out_path

def apply_img_instance_transforms(built_by_res: Dict[int, bpy.types.Object], details, overlay_by_sector_res: Optional[Dict[Tuple[int, int], bpy.types.Object]] = None, extra_resource_objects: Optional[List[bpy.types.Object]] = None, row_overlay_by_res: Optional[Dict[Tuple[int, int], bpy.types.Object]] = None, nested_overlay_by_res: Optional[Dict[Tuple[int, int], bpy.types.Object]] = None, ipl_overlay_by_sector_res: Optional[Dict[Tuple[int, int], bpy.types.Object]] = None, ipl_row_overlay_by_res: Optional[Dict[Tuple[int, int], bpy.types.Object]] = None, ipl_nested_overlay_by_res: Optional[Dict[Tuple[int, int], bpy.types.Object]] = None, ipl_extra_resource_objects: Optional[List[bpy.types.Object]] = None, import_stem: str = "beach", ide_ipl_to_res: Optional[Dict[int, int]] = None, ide_ipl_to_name: Optional[Dict[int, str]] = None, ide_res_to_model_id: Optional[Dict[int, int]] = None, ide_res_to_name: Optional[Dict[int, str]] = None, placement_identity_by_key: Optional[Dict[Tuple[int, int, int, int], Dict[str, object]]] = None, progress_callback=None, model_2dfx_by_game_model_id: Optional[Dict[int, List[Dict[str, object]]]] = None, model_2dfx_summary: Optional[Dict[str, object]] = None, model_2dfx_collection=None, create_game_dtz_2dfx_helpers: bool = True) -> Tuple[int, int, int]:
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
    ide_res_to_model_id = ide_res_to_model_id or {}
    ide_res_to_name = ide_res_to_name or {}
    placement_identity_by_key = placement_identity_by_key or {}
    model_2dfx_by_game_model_id = model_2dfx_by_game_model_id or {}
    model_2dfx_summary = model_2dfx_summary if model_2dfx_summary is not None else {}
    placement_report_rows = globals().get("_CURRENT_PLACEMENT_REPORT_ROWS", {}) or {}

    exact_overlay_candidates = []
    continuation_candidates = []
    for (sector_index, res_id), obj in overlay_by_sector_res.items():
        if obj is None:
            continue
        resource_id = int(res_id)
        try:
            is_continuation = bool(obj.get("blds_img_continues_in_img", False))
        except Exception:
            is_continuation = False
        if is_continuation:
            continuation_candidates.append(obj)
            continue
        exact_overlay_candidates.append(obj)

    overlay_candidates_by_res = build_resource_object_candidate_map(exact_overlay_candidates)
    overlay_by_res = {}
    overlay_variant_res_ids = set()
    for resource_id, candidates in overlay_candidates_by_res.items():
        if len(candidates) > 1:
            overlay_variant_res_ids.add(int(resource_id))
        chosen = None
        for candidate in candidates:
            chosen = choose_better_blds_candidate(chosen, candidate)
        if chosen is not None:
            overlay_by_res[int(resource_id)] = chosen
    if overlay_variant_res_ids:
        LVZ.dbg(f"[exact-models] static resource IDs with placement-selected variants: {len(overlay_variant_res_ids)}")
    continuation_candidates_by_res = build_resource_object_candidate_map(continuation_candidates)
    if continuation_candidates_by_res:
        LVZ.dbg(
            f"[raw-img-models] placement-selected pool: {len(continuation_candidates_by_res)} resource ids, "
            f"{sum(len(values) for values in continuation_candidates_by_res.values())} exact-RES variants"
        )

    extra_candidates_by_res = build_resource_object_candidate_map(extra_resource_objects)
    extra_by_res = {}
    extra_variant_res_ids = set()
    for resource_id, candidates in extra_candidates_by_res.items():
        if len(candidates) > 1:
            extra_variant_res_ids.add(int(resource_id))
        chosen = None
        for candidate in candidates:
            chosen = choose_better_blds_candidate(chosen, candidate)
        if chosen is not None:
            extra_by_res[int(resource_id)] = chosen
    if extra_variant_res_ids:
        LVZ.dbg(f"[exact-models] linked resource IDs with placement-selected variants: {len(extra_variant_res_ids)}")

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
            f"[resolver] stage={stage} RES={res_id_a} ROWLINK={ipl_id_a} IPLraw=0x{ipl_raw_a:04X} "
            f"sector={sector_index_a} row={row_index_a} pass={pass_name_a}/{pass_index_a} "
            f"rowAbs=0x{row_abs_a:08X} contIMG=0x{cont_a:08X} rel=0x{rel_a:08X} "
            f"sphere={sphere} rowMatrixScale={raw_scale} chosenSource={chosen_source or ''} note={extra_note or ''}"
        )
        resolver_audit_lines += 1
        for field_name, model_id in (("RES", res_id_a), ("ROWLINK_DIAGNOSTIC", ipl_id_a)):
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
    placement_variant_choices = 0
    placement_variant_rejections = 0
    placement_variant_max_score = 0.0
    placement_source_counts = {}
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
            hidden_duplicate_collection = globals().get("_ACTIVE_IMPORT_LINKED_COLLECTION")
            if hidden_duplicate_collection is None:
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
        if extra_candidates_by_res.get(int(res_id)):
            return True
        if overlay_candidates_by_res.get(int(res_id)):
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

    # Build one runtime-placement group per AERA model-info/ROWLINK/transform.
    # Several streamed RES pieces can form one opaque/transparent model.  They
    # all point at the same CBaseModelInfo and must not duplicate its effects.
    two_dfx_split_res_by_placement = {}
    if create_game_dtz_2dfx_helpers and model_2dfx_by_game_model_id:
        for effect_detail in details:
            effect_identity = placement_identity_by_key.get(blds_placement_report_key(effect_detail), {}) or {}
            effect_model_id = int(effect_identity.get("game_model_id", -1))
            if effect_model_id < 0 or effect_model_id not in model_2dfx_by_game_model_id:
                continue
            effect_key = blds_2dfx_placement_key(effect_model_id, effect_detail)
            two_dfx_split_res_by_placement.setdefault(effect_key, set()).add(int(effect_detail[0]))
    created_2dfx_placement_keys = {}
    model_2dfx_summary.setdefault("candidate_rows_with_effects", 0)
    model_2dfx_summary.setdefault("duplicate_split_rows_suppressed", 0)
    model_2dfx_summary.setdefault("effects_suppressed_duplicate", 0)

    total_details = len(details)
    for detail_index, detail in enumerate(details):
        if progress_callback is not None and (detail_index % 128 == 0 or detail_index + 1 == total_details):
            try:
                progress_callback(
                    detail_index + 1,
                    total_details,
                    applied,
                    len(used_object_ids),
                    linked,
                )
            except TypeError:
                progress_callback(detail_index + 1, total_details)
        used_ipl_model_fallback = False
        used_force_missing_img_mdl = False
        used_exact_missing_img_mdl = False
        used_final_missing_ipl_neighbor = False
        ipl_model_source_for_row = None
        source_model_id_for_row = -1
        final_missing_fit_note = ""
        res_id = int(detail[0])
        # detail[4] is an internal row-link/index, not a GTA IDE model id.
        ipl_id = int(detail[4])
        identity = placement_identity_by_key.get(blds_placement_report_key(detail), {}) or {}
        game_model_id = int(identity.get("game_model_id", -1))
        game_model_name = str(identity.get("model_name", ""))
        sector_index = int(detail[15]) if len(detail) > 15 else -1
        pass_name = str(detail[14]) if len(detail) > 14 else "UNKNOWN"
        row_index = int(detail[19]) if len(detail) > 19 else -1
        placement_report_row = placement_report_rows.get(blds_placement_report_key(detail))
        resolver_audit_row(detail, "row-start")
        if SKIP_LIGHTS_PASS_IPL_MESH_PLACEMENTS and is_light_placement_pass(pass_name):
            try:
                skipped_lights_pass_ipl_rows.append((sector_index, row_index, ipl_id, res_id, pass_name, int(detail[1]), int(detail[2])))
            except Exception:
                skipped_lights_pass_ipl_rows.append((sector_index, row_index, ipl_id, res_id, pass_name, 0, 0))
            blds_report_mark_status(placement_report_row, "SKIPPED_LIGHTS_POLICY", "LIGHTS placement mesh skipped by policy")
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
            nonlocal placement_variant_choices, placement_variant_rejections, placement_variant_max_score
            model_id = int(model_id)
            exact_candidates = []

            def add_candidate(candidate, source, rank):
                if candidate is None:
                    return
                try:
                    if bool(candidate.get("blds_img_continues_in_img", False)):
                        return
                except Exception:
                    pass
                exact_candidates.append((candidate, str(source), int(rank)))

            # Master AreaInfo -> AERA rows are the authoritative exact payload
            # source for streamed map resources.  Select a fitting AERA payload
            # first so an empty/incomplete same-RES WRLD placeholder cannot hide
            # it from placement.  This remains exact-RES only; no ROWLINK or
            # GAME_MODEL geometry alias is involved.
            aera_candidates = []
            for candidate in extra_candidates_by_res.get(model_id, []):
                try:
                    if str(candidate.get("blds_kind", "")) == "IMG_AERA_RESOURCE_MDL":
                        aera_candidates.append((candidate, "official_aera_model", 0))
                except Exception:
                    continue
            aera_obj, aera_source, aera_fit, aera_count = choose_exact_resource_candidate(
                aera_candidates,
                detail,
                max_fit_score=CONTINUES_IN_IMG_MAX_PLACEMENT_FIT_SCORE,
            )
            if aera_obj is not None:
                if int(model_id) in (1725, 1881, 1887, 1989, 2184, 3528):
                    try:
                        LVZ.dbg(
                            f"[aera-placement] selected RES={int(model_id)} object={getattr(aera_obj, 'name', '')} "
                            f"fit={float(aera_fit[0]) if aera_fit is not None else -1.0:.6f} "
                            f"sector={int(sector_index)} row={int(row_index)} pass={str(pass_name)}"
                        )
                    except Exception:
                        pass
                return aera_obj, aera_source

            # Every candidate below is keyed by the placement row's RES ID.
            # Rank only breaks ties; the row sphere/matrix is the authority.
            add_candidate(overlay_by_sector_res.get((sector_index, model_id)), "exact_sector_model", 0)
            if row_index >= 0:
                add_candidate(nested_overlay_by_res.get((row_index, model_id)), "exact_nested_row_model", 1)
                add_candidate(row_overlay_by_res.get((row_index, model_id)), "exact_row_model", 2)
            add_candidate(built_by_res.get(model_id), "lvz_model", 3)
            for candidate in extra_candidates_by_res.get(model_id, []):
                try:
                    if str(candidate.get("blds_kind", "")) == "IMG_AERA_RESOURCE_MDL":
                        continue
                except Exception:
                    pass
                add_candidate(candidate, "area_model", 4)
            for candidate in overlay_candidates_by_res.get(model_id, []):
                add_candidate(candidate, "global_sector_model", 5)

            # Raw continuation candidates are also exact RES variants.  They are
            # generated only for unresolved rows or suspicious aggregate slices.
            for candidate in continuation_candidates_by_res.get(model_id, []):
                exact_candidates.append((candidate, "img_continuation_model", 6))

            if placement_report_row is not None:
                candidate_rows = []
                candidate_seen = set()
                for candidate_obj, candidate_source, candidate_rank in exact_candidates:
                    if candidate_obj is None:
                        continue
                    try:
                        candidate_signature = blds_object_geometry_signature(candidate_obj)
                        candidate_key = candidate_signature if candidate_signature is not None else ("object", id(candidate_obj))
                    except Exception:
                        candidate_key = ("object", id(candidate_obj))
                    if candidate_key in candidate_seen:
                        continue
                    candidate_seen.add(candidate_key)
                    try:
                        candidate_fit = placement_candidate_fit(candidate_obj, detail)
                    except Exception:
                        candidate_fit = None
                    try:
                        candidate_verts, candidate_faces, candidate_radius = object_geometry_counts_radius(candidate_obj)
                    except Exception:
                        candidate_verts, candidate_faces, candidate_radius = 0, 0, 0.0
                    candidate_rows.append({
                        "name": str(getattr(candidate_obj, "name", "")),
                        "source": str(candidate_source),
                        "rank": int(candidate_rank),
                        "kind": str(blds_report_object_prop(candidate_obj, "blds_kind", "")),
                        "res_id": int(blds_report_object_prop(candidate_obj, "blds_res_index", -1)),
                        "parent_res_id": int(blds_report_object_prop(candidate_obj, "blds_parent_res_index", -1)),
                        "group_index": int(blds_report_object_prop(candidate_obj, "blds_group_index", -1)),
                        "continues_img": bool(blds_report_object_prop(candidate_obj, "blds_img_continues_in_img", False)),
                        "vertices": int(candidate_verts),
                        "faces": int(candidate_faces),
                        "radius": float(candidate_radius),
                        "fit_score": None if candidate_fit is None else float(candidate_fit[0]),
                        "fit_center_error": None if candidate_fit is None else float(candidate_fit[1]),
                        "fit_radius_ratio": None if candidate_fit is None else float(candidate_fit[2]),
                    })
                    if len(candidate_rows) >= int(PLACEMENT_RES_REPORT_CANDIDATE_LIMIT):
                        break
                placement_report_row["exact_candidates"] = candidate_rows
                placement_report_row["exact_candidate_total"] = len(candidate_seen)

            obj, source, fit, candidate_count = choose_exact_resource_candidate(
                exact_candidates,
                detail,
                max_fit_score=CONTINUES_IN_IMG_MAX_PLACEMENT_FIT_SCORE,
            )
            if candidate_count > 1:
                if obj is not None:
                    placement_variant_choices += 1
                    if fit is not None:
                        placement_variant_max_score = max(placement_variant_max_score, float(fit[0]))
                else:
                    placement_variant_rejections += 1
            elif candidate_count == 1 and obj is None:
                placement_variant_rejections += 1
            if obj is not None:
                return obj, source

            # A fit failure must not create a new hole when an exact structured
            # RES model already existed in the normal LVZ/IMG tables.  Raw IMG
            # guesses remain rejectable, but the best same-RES structured model
            # is retained as the conservative fallback.  This restores the old
            # static-model coverage without ever substituting an IPL/other RES.
            structured_candidates = [
                item for item in exact_candidates
                if len(item) < 2 or str(item[1]) != "img_continuation_model"
            ]
            structured_obj, structured_source, structured_fit, _structured_count = choose_exact_resource_candidate(
                structured_candidates,
                detail,
                max_fit_score=None,
            )
            if structured_obj is not None:
                try:
                    structured_obj["blds_exact_structured_fit_fallback"] = True
                    if structured_fit is not None:
                        structured_obj["blds_exact_structured_fit_score"] = float(structured_fit[0])
                except Exception:
                    pass
                return structured_obj, str(structured_source) + "_fit_fallback"
            return None, ""

        base_obj, primary_model_source = lookup_primary_placement_model(primary_model_id)
        primary_would_miss = base_obj is None
        if base_obj is not None:
            placement_source_counts[primary_model_source] = placement_source_counts.get(primary_model_source, 0) + 1
            source_model_id_for_row = int(primary_model_id)
            if int(primary_model_id) != int(res_id):
                ipl_model_source_for_row = f"row-model-id-hint-disabled:{primary_model_source}:model={int(primary_model_id)}:visible_res={int(res_id)}"
            if primary_model_source == "exact_nested_row_model":
                fallback_nested += 1
            elif primary_model_source == "exact_row_model":
                fallback_row += 1
            elif primary_model_source in ("official_aera_model", "area_model"):
                fallback_extra += 1
            elif primary_model_source in ("global_sector_model", "img_continuation_model"):
                fallback_overlay += 1
        # GAME_MODEL is identity/2DFX metadata only. It is never a streamed
        # geometry resource key. Visible geometry remains exact RES-only.

        # Legacy V72 path: if RES was absent, ROWLINK was once treated as though it had a
        # real parsed MDL payload, use the real MDL. This matches the WRLD row
        # structure: +0x00 ROWLINK, +0x02 RES. This path remains disabled; do not run before
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
                    f"[geometry-recovery] LEGACY ROWLINK-as-model path used; "
                    f"RES={res_id} ROWLINK={ipl_id} sector={sector_index} row={row_index} pass={pass_name} "
                    f"using={getattr(real_ipl_obj, 'name', '')} source={real_ipl_source}; {real_ipl_note}; "
                    f"ideMap={ide_ipl_to_name.get(int(ipl_id), '')}->{ide_ipl_to_res.get(int(ipl_id), '')}; full row matrix scale"
                )
                resolver_audit_row(
                    detail,
                    "recovered-real-ipl-for-missing-res",
                    chosen_obj=real_ipl_obj,
                    chosen_source=ipl_model_source_for_row,
                    extra_note="RES side had no usable resource; legacy ROWLINK-as-model side resolved (should remain disabled)",
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
                                f"RES={res_id} ROWLINK={ipl_id} sector={sector_index} row={row_index} pass={pass_name} "
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
                                f"RES={res_id} ROWLINK={ipl_id} sector={sector_index} row={row_index} pass={pass_name} "
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
                            blds_report_mark_status(placement_report_row, "MISSING", "rejected bad sparse WRLD fragment; no proven exact full model")
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
                            f"RES={res_id} ROWLINK={ipl_id} sector={sector_index} row={row_index} pass={pass_name} "
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
            blds_report_mark_status(placement_report_row, "MISSING", "no proven exact RES geometry candidate")
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
                    blds_report_mark_status(placement_report_row, "SKIPPED_DUPLICATE", skip_reason)
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
                fallback_collection = globals().get("_ACTIVE_IMPORT_LINKED_COLLECTION") or globals().get("_ACTIVE_IMPORT_OBJECTS_COLLECTION") or bpy.context.collection
                fallback_collection.objects.link(obj)
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
        if (
            PRESERVE_EXACT_WRLD_SUBMODEL_ROW_MATRIX
            and base_is_wrld_submodel_group
            and not keep_world_baked_submodel_matrix
            and not used_force_missing_img_mdl
            and not used_final_missing_ipl_neighbor
        ):
            adjusted_matrix = matrix.copy()
            if wrld_submodel_origin_rebased_for_row:
                try:
                    adjusted_matrix = matrix @ Matrix.Translation(Vector((
                        float(wrld_submodel_origin_off_x),
                        float(wrld_submodel_origin_off_y),
                        float(wrld_submodel_origin_off_z),
                    )))
                except Exception:
                    adjusted_matrix = matrix.copy()
            obj.matrix_world = adjusted_matrix
            sx, sy, sz = matrix_basis_column_scales(matrix)
            obj["blds_wrld_submodel_cell_scale_stripped"] = False
            obj["blds_wrld_submodel_original_matrix_scale"] = f"{sx:.6f},{sy:.6f},{sz:.6f}"
            obj["blds_wrld_submodel_full_matrix_preserved"] = True
            obj["blds_wrld_submodel_rebase_compensated"] = bool(wrld_submodel_origin_rebased_for_row)
            matrix_mode_for_row = "wrld_submodel_row_matrix_full_rebase_compensated"
        elif wrld_submodel_strip_cell_scale_for_this_row:
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
            # submodel rows are handled above, before this forced-name branch;
            # their full normalized-model matrix is preserved and rebase-compensated.
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

        stamp_bleeds_entity_type(obj, "OBJECT")
        try:
            obj["blds_res_id"] = int(res_id)
            obj["blds_row_link_id"] = int(ipl_id)
            obj["blds_row_link_raw"] = int(detail[3])
            obj["blds_ipl_id"] = int(ipl_id)  # compatibility alias only
            obj["blds_aera_secondary_id"] = int(game_model_id)
            obj["blds_aera_secondary_name"] = str(game_model_name)
            # Compatibility alias for older scenes/reports.  Entity-owned 2DFX
            # stamps overwrite this only after an actual CEntity match.
            obj["blds_game_model_id"] = int(game_model_id)
            obj["blds_game_model_name"] = str(game_model_name)
            obj["blds_identity_source"] = str(identity.get("source", ""))
            obj["blds_identity_area_index"] = int(identity.get("area_index", -1))
            obj["blds_identity_area_resource_index"] = int(identity.get("area_resource_index", -1))
            obj["blds_identity_area_resource_row_off"] = int(identity.get("area_resource_row_off", -1))
            obj["blds_identity_area_payload_off"] = int(identity.get("area_resource_raw_off", -1))
        except Exception:
            pass

        try:
            globals().setdefault("_CURRENT_PLACED_OBJECT_RECORDS", []).append({
                "object": obj,
                "res_id": int(res_id),
                "row_link_id": int(ipl_id),
                "game_model_id": int(game_model_id),
                "sector_index": int(sector_index),
                "row_index": int(row_index),
                "pass_name": str(pass_name),
                "matrix_world": obj.matrix_world.copy(),
                "world_x": float(obj.matrix_world[0][3]),
                "world_y": float(obj.matrix_world[1][3]),
                "world_z": float(obj.matrix_world[2][3]),
            })
        except Exception:
            pass

        # Do not create or stamp 2DFX from streamed placement rows.  The
        # authoritative effect instances are imported after geometry placement
        # from GAME.DTZ BUILDING/TREADABLE/DUMMY CEntity pools.  AERA secondary
        # values remain placement metadata only.
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
        if DIAGNOSTIC_CSV_LOGS_ENABLED:
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
                        f"[matrix-log] object={getattr(obj, 'name', '')} RES={int(res_id)} ROWLINK={int(ipl_id)} "
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
                        f"[geometry-log] object={getattr(obj, 'name', '')} RES={int(res_id)} ROWLINK={int(ipl_id)} "
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
        blds_report_mark_placed(
            placement_report_row, obj, base_obj, int(source_model_id_for_row),
            str(ipl_model_source_for_row or "exact-res"), str(matrix_mode_for_row), int(instance_index),
        )
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
                    f"[apply] RES={res_id} sector={sector_index} pass={pass_name} ROWLINK={ipl_id} "
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
        set_collection_view_hidden(hidden_duplicate_collection, False)
    if apply_log_suppressed:
        LVZ.dbg(f"[apply] matrix_world log lines suppressed: {apply_log_suppressed}")
    LVZ.dbg(f"[apply] legacy ROWLINK best-candidate replacements (disabled): sector={ipl_overlay_choice_replacements} area={ipl_extra_choice_replacements}")
    LVZ.dbg(f"[resolver] audit lines printed: {resolver_audit_lines} / max={int(RESOLVER_AUDIT_MAX_ROWS)}")
    if placement_source_counts:
        source_labels = (
            ("exact_sector_model", "matching sector"),
            ("exact_nested_row_model", "linked child table"),
            ("exact_row_model", "shared row table"),
            ("lvz_model", "Master LVZ"),
            ("official_aera_model", "master AERA exact resource"),
            ("area_model", "linked AREA/Triggered model data"),
            ("global_sector_model", "other static map blocks"),
            ("img_continuation_model", "remaining raw IMG data"),
        )
        source_text = ", ".join(
            f"{label}={int(placement_source_counts.get(key, 0))}"
            for key, label in source_labels
            if placement_source_counts.get(key, 0)
        )
        if source_text:
            LVZ.dbg(f"Placement model sources: {source_text}")
    if placement_variant_choices:
        LVZ.dbg(
            f"Exact model variants selected using placement bounds: {placement_variant_choices} "
            f"(highest accepted match score {placement_variant_max_score:.3f})"
        )
    if placement_variant_rejections:
        LVZ.dbg(
            f"Exact model candidates rejected because their size or position did not match the placement row: "
            f"{placement_variant_rejections}"
        )
    LVZ.dbg(f"[apply] skipped missing mesh/resource rows: {skipped_missing}")
    beach1887_missing_count = sum(
        1 for row in missing_rows_full
        if len(row) >= 4 and int(row[3]) == 1887
    )
    if beach1887_missing_count:
        LVZ.dbg(
            f"[exact-res] Beach1887 remains unresolved in {int(beach1887_missing_count)} placement rows: "
            "no fitting exact RES=1887 AERA/WRLD candidate reached placement. "
            "Cross-ID ROWLINK geometry remains disabled; inspect the preceding [aera-placement] lines."
        )
    LVZ.dbg(f"[apply] reused nested-child resource fallback rows: {fallback_nested}")
    LVZ.dbg(f"[apply] legacy ROWLINK-as-model fallback rows (must remain zero): {fallback_ipl} (rejected={len(ipl_rejected_rows)})")
    LVZ.dbg(f"[apply] legacy ROWLINK fallback cell-scale strips: {ipl_cell_scale_fixed}")
    for sector_index, row_index, pass_name, ipl_id, res_id, model_source, sx, sy, sz in ipl_cell_scale_rows:
        LVZ.dbg(
            f"[apply] IPL-CELL-SCALE-STRIP sector={sector_index} row={row_index} pass={pass_name} "
            f"IPL={ipl_id} RES={res_id} via {model_source} old_scale={sx:.3f},{sy:.3f},{sz:.3f}"
        )
    LVZ.dbg(f"[apply] reused aggregate-origin IPL group-piece fallback rows: {fallback_aggregate}")
    if skipped_lights_pass_ipl_rows:
        LVZ.dbg(f"[apply] skipped LIGHTS-pass IPL mesh rows: {len(skipped_lights_pass_ipl_rows)}")
        for sector_index, row_index, ipl_id, res_id, pass_name, cont, rel_off in skipped_lights_pass_ipl_rows[:96]:
            LVZ.dbg(f"  LIGHTS-SKIP sector={sector_index} row={row_index} ROWLINK={ipl_id} RES={res_id} cont=0x{int(cont):08X} rel=0x{int(rel_off):08X}")
    _real_ipl_for_missing_res_rows_safe = locals().get("real_ipl_for_missing_res_rows", [])
    if _real_ipl_for_missing_res_rows_safe:
        LVZ.dbg(f"[geometry-recovery] legacy ROWLINK-as-model recoveries for missing RES rows: {len(_real_ipl_for_missing_res_rows_safe)}")
        for _r in _real_ipl_for_missing_res_rows_safe[:160]:
            LVZ.dbg(
                f"[geometry-recovery] real-ipl-missing-res sector={_r[0]} row={_r[1]} pass={_r[2]} ROWLINK={_r[3]} RES={_r[4]} "
                f"source={_r[5]} object={_r[6]} geom={_r[7]}v/{_r[8]}f/r{_r[9]:.3f} note={_r[10]}"
            )
    _rich_ipl_over_sparse_rows_safe = locals().get("rich_ipl_over_sparse_rows", [])
    if _rich_ipl_over_sparse_rows_safe:
        LVZ.dbg(f"[geometry-recovery] rich internal IPL-over-sparse recoveries: {len(_rich_ipl_over_sparse_rows_safe)}")
        for _r in _rich_ipl_over_sparse_rows_safe[:128]:
            LVZ.dbg(
                f"[geometry-recovery] rich-over-sparse sector={_r[0]} row={_r[1]} pass={_r[2]} ROWLINK={_r[3]} RES={_r[4]} "
                f"source={_r[5]} object={_r[6]} sparse={_r[8]}v/{_r[9]}f note={_r[7]}"
            )
    if bad_nonlight_sparse_building_rows:
        LVZ.dbg(f"[geometry-recovery] bad non-LIGHTS sparse building fragments suppressed: {len(bad_nonlight_sparse_building_rows)}")
        for _r in bad_nonlight_sparse_building_rows[:128]:
            LVZ.dbg(
                f"[geometry-recovery] suppressed-fragment sector={_r[0]} row={_r[1]} pass={_r[2]} ROWLINK={_r[3]} RES={_r[4]} "
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
                f"  SUBMODEL RES={res_id} ROWLINK={ipl_id} sector={sector_index} row={row_index} pass={pass_name} "
                f"-> parent RES={parent_res} group={group_index} range_start={range_start} object={obj_name}"
            )
    LVZ.dbg(f"[apply] reused row-shared resource fallback rows: {fallback_row}")
    LVZ.dbg(f"[apply] reused AREA/direct resource fallback rows: {fallback_extra}")
    LVZ.dbg(f"[apply] reused same-resource overlay fallback rows: {fallback_overlay}")
    LVZ.dbg(f"[apply] reused neighboring resource alias fallback rows: {fallback_neighbor}")
    LVZ.dbg(f"[apply] legacy ROWLINK-as-model rows imported (must remain zero): {fallback_force_missing_img_mdl}")
    LVZ.dbg(f"[apply] final missing nearest legacy ROWLINK clone rows (must remain zero): {fallback_final_missing_ipl_neighbor}")
    if forced_missing_img_mdl_rows:
        LVZ.dbg("[apply] first exact missing IMG MDL imports:")
        for sector_index, row_index, pass_name, ipl_id, res_id, forced_source, obj_name in forced_missing_img_mdl_rows:
            LVZ.dbg(
                f"  EXACT MISSING MDL {res_id} IMPORTED via legacy ROWLINK={ipl_id} source={forced_source} "
                f"sector={sector_index} row={row_index} pass={pass_name} object={obj_name}"
            )
    if final_missing_ipl_neighbor_rows:
        LVZ.dbg("[apply] first final-missing nearest legacy ROWLINK clone imports:")
        for sector_index, row_index, pass_name, ipl_id, res_id, source_model_id, source, obj_name in final_missing_ipl_neighbor_rows[:64]:
            LVZ.dbg(
                f"  FINAL MISSING MDL {res_id} IMPORTED via nearest legacy ROWLINK={source_model_id} "
                f"requested ROWLINK={ipl_id} source={source} sector={sector_index} row={row_index} pass={pass_name} object={obj_name}"
            )
    if imported_missing_mdl_rows:
        try:
            previous_imported_count = sum(1 for row in imported_missing_mdl_rows if bool(row.get("was_missing_in_previous_import", False)))
            nearby_imported_count = sum(1 for row in imported_missing_mdl_rows if bool(row.get("nearby_ipl_neighbor", False)))
            LVZ.dbg(f"[compare] previous missing rows imported this run: {previous_imported_count}")
            LVZ.dbg(f"[compare] legacy nearby ROWLINK/model rows imported this run: {nearby_imported_count}")
        except Exception:
            pass
        LVZ.dbg(f"[apply] imported missing MDL report rows: {len(imported_missing_mdl_rows)}")
        for report_row in imported_missing_mdl_rows[:64]:
            LVZ.dbg(
                f"  MISSING MDL {report_row['requested_res_id']} IMPORTED -> "
                f"{report_row['object_name']} via {report_row['fallback_source']} ROWLINK={report_row['ipl_id']}"
            )
    if ipl_fallback_rows:
        LVZ.dbg("[apply] first legacy ROWLINK-as-model fallback rows:")
        for row in ipl_fallback_rows:
            sector_index, row_index, pass_name, ipl_id, res_id, model_source = row[:6]
            fit_note = row[6] if len(row) > 6 else ""
            LVZ.dbg(
                f"  sector={sector_index} row={row_index} pass={pass_name} "
                f"RES={res_id} -> legacy ROWLINK={ipl_id} via {model_source}; {fit_note}"
            )
    if ipl_rejected_rows:
        LVZ.dbg("[apply] first rejected legacy ROWLINK-as-model fallback rows:")
        for sector_index, row_index, pass_name, ipl_id, res_id, model_source, fit_note in ipl_rejected_rows:
            LVZ.dbg(
                f"  REJECT sector={sector_index} row={row_index} pass={pass_name} "
                f"RES={res_id} -> legacy ROWLINK={ipl_id} via {model_source}; {fit_note}"
            )
    if aggregate_piece_rows:
        LVZ.dbg("[apply] first aggregate group-piece fallback rows:")
        for sector_index, row_index, ipl_id, res_id, pass_name, parent_res, group_index, dist, agg_radius in aggregate_piece_rows:
            LVZ.dbg(
                f"  sector={sector_index} row={row_index} pass={pass_name} ROWLINK={ipl_id} "
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
                    f"  sector={sector_index} row={row_index} pass={pass_name} ROWLINK={ipl_id} "
                    f"RES={res_id} -> RES={alias_res_id} via {alias_source} delta={alias_delta}"
                )
            else:
                LVZ.dbg(
                    f"  REJECT sector={sector_index} row={row_index} pass={pass_name} ROWLINK={ipl_id} "
                    f"RES={res_id} -> RES={alias_res_id} via {alias_source} delta={alias_delta}; {note}"
                )
    if missing_rows:
        LVZ.dbg("[apply] first missing placement rows:")
        for sector_index, row_index, ipl_id, res_id, pass_name, cont, rel_off in missing_rows:
            LVZ.dbg(
                f"  sector={sector_index} row={row_index} pass={pass_name} ROWLINK={ipl_id} RES={res_id} "
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
                        f"[matrix-log] object={r.get('object_name','')} RES={r.get('res_id')} ROWLINK={r.get('ipl_id')} "
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


def blds_safe_i16(data: bytes, off: int, default: int = -1) -> int:
    try:
        if off < 0 or off + 2 > len(data):
            return default
        return struct.unpack_from("<h", data, off)[0]
    except Exception:
        return default


BLDS_2DFX_EFFECT_TYPE_NAMES = {
    0: "LIGHT",
    1: "PARTICLE",
    2: "ATTRACTOR",
    3: "PED_BEHAVIOUR",
}


def blds_2dfx_effect_type_name(effect_type: int) -> str:
    return BLDS_2DFX_EFFECT_TYPE_NAMES.get(int(effect_type), "UNKNOWN")


def blds_resolve_dtz_offset(data: bytes, raw_offset: int, min_size: int = 1) -> int:
    """Validate one exact file-relative GAME.DTZ pointer.

    Decompressed GTAG/GATG resource-image pointers are already file-relative
    offsets.  Do not try neighbouring +/-0x20 interpretations: accepting a
    shifted pointer can silently associate a different model-info/effect row.
    """
    raw_offset = int(raw_offset)
    min_size = max(1, int(min_size))
    if raw_offset < 0 or raw_offset + min_size > len(data):
        return -1
    return raw_offset


def blds_decode_dtz_2dfx_entry(data: bytes, off: int, index: int, table_abs: int) -> Optional[Dict[str, object]]:
    """Decode one 64-byte Leeds C2dEffect row from the global GAME.DTZ table."""
    try:
        if off < 0 or off + 0x40 > len(data):
            return None
        raw = bytes(data[off:off + 0x40])
        x, y, z, pos_w = struct.unpack_from("<4f", raw, 0x00)
        if not all(math.isfinite(float(value)) and abs(float(value)) < 1000000.0 for value in (x, y, z, pos_w)):
            return None
        effect_type = int(raw[0x14])
        if effect_type < 0 or effect_type > 3:
            return None
        entry: Dict[str, object] = {
            "index": int(index),
            "global_index": int(index),
            "entry_off": int(off),
            "table_abs": int(table_abs),
            "x": float(x),
            "y": float(y),
            "z": float(z),
            "position_w": float(pos_w),
            "r": int(raw[0x10]),
            "g": int(raw[0x11]),
            "b": int(raw[0x12]),
            "a": int(raw[0x13]),
            "effect_type": int(effect_type),
            "effect_type_name": blds_2dfx_effect_type_name(effect_type),
            "raw_hex": raw.hex(),
            "payload_hex": raw[0x18:].hex(),
        }
        if effect_type == 0:
            distance, outer_range, size, inner_range = struct.unpack_from("<4f", raw, 0x18)
            entry.update({
                "light_distance": float(distance),
                "light_outer_range": float(outer_range),
                "light_size": float(size),
                "light_inner_range": float(inner_range),
                "light_flash": int(raw[0x28]),
                "light_wet": int(raw[0x29]),
                "light_flare": int(raw[0x2A]),
                "light_shadow_intensity": int(raw[0x2B]),
                "light_flags": int(raw[0x2C]),
                "light_corona_texture_ptr": int(struct.unpack_from("<I", raw, 0x30)[0]),
                "light_shadow_texture_ptr": int(struct.unpack_from("<I", raw, 0x34)[0]),
            })
        elif effect_type == 1:
            subtype = int(struct.unpack_from("<i", raw, 0x18)[0])
            dx, dy, dz = struct.unpack_from("<3f", raw, 0x1C)
            entry.update({
                "particle_subtype": subtype,
                "direction_x": float(dx),
                "direction_y": float(dy),
                "direction_z": float(dz),
                "particle_scale": float(struct.unpack_from("<f", raw, 0x28)[0]),
            })
        elif effect_type == 2:
            dx, dy, dz = struct.unpack_from("<3f", raw, 0x18)
            entry.update({
                "attractor_direction_x": float(dx),
                "attractor_direction_y": float(dy),
                "attractor_direction_z": float(dz),
                "attractor_subtype": int(raw[0x24]),
                "attractor_probability": int(raw[0x25]),
            })
        elif effect_type == 3:
            dx, dy, dz = struct.unpack_from("<3f", raw, 0x18)
            rx, ry, rz = struct.unpack_from("<3f", raw, 0x24)
            entry.update({
                "ped_direction_x": float(dx),
                "ped_direction_y": float(dy),
                "ped_direction_z": float(dz),
                "ped_rotation_x": float(rx),
                "ped_rotation_y": float(ry),
                "ped_rotation_z": float(rz),
                "ped_subtype": int(raw[0x30]),
            })
        return entry
    except Exception:
        return None


def blds_parse_game_dtz_2dfx_bytes(data: bytes, wanted_model_ids=None) -> Tuple[Dict[int, List[Dict[str, object]]], Dict[str, object]]:
    """Parse exact model-id to C2dEffect associations from decompressed GAME.DTZ."""
    summary: Dict[str, object] = {
        "status": "unparsed",
        "ide_count": 0,
        "effect_count": 0,
        "models_with_effects": 0,
        "entries_available": 0,
        "rejected_model_refs": 0,
        "malformed_effect_rows": 0,
        "effect_type_counts": {0: 0, 1: 0, 2: 0, 3: 0},
        "effects_imported": 0,
        "instances_with_effects": 0,
        "model_meta_by_id": {},
    }
    mapping: Dict[int, List[Dict[str, object]]] = {}
    if not data or len(data) < 0x5C:
        summary["status"] = "header_too_small"
        return mapping, summary
    signature = bytes(data[:4])
    if signature not in (b"GATG", b"GTAG"):
        summary["status"] = "bad_signature"
        summary["signature_hex"] = signature.hex()
        return mapping, summary

    ide_count = int(blds_safe_u32(data, 0x38, 0))
    ide_ptr_raw = int(blds_safe_u32(data, 0x3C, 0))
    effect_count = int(blds_safe_u32(data, 0x54, 0))
    effect_ptr_raw = int(blds_safe_u32(data, 0x58, 0))
    summary.update({
        "signature": signature.decode("ascii", errors="replace"),
        "ide_count": ide_count,
        "ide_pointer_raw": ide_ptr_raw,
        "effect_count": effect_count,
        "effect_pointer_raw": effect_ptr_raw,
    })
    if ide_count <= 0 or ide_count > 200000:
        summary["status"] = "ide_count_out_of_range"
        return mapping, summary
    if effect_count < 0 or effect_count > 100000:
        summary["status"] = "effect_count_out_of_range"
        return mapping, summary

    ide_table = blds_resolve_dtz_offset(data, ide_ptr_raw, ide_count * 4)
    effect_table = blds_resolve_dtz_offset(data, effect_ptr_raw, max(1, effect_count * 0x40)) if effect_count else -1
    summary["ide_table_abs"] = ide_table
    summary["effect_table_abs"] = effect_table
    if ide_table < 0:
        summary["status"] = "ide_pointer_out_of_bounds"
        return mapping, summary
    if effect_count and effect_table < 0:
        summary["status"] = "effect_pointer_out_of_bounds"
        return mapping, summary

    effects: List[Optional[Dict[str, object]]] = []
    malformed = 0
    for effect_index in range(effect_count):
        entry = blds_decode_dtz_2dfx_entry(data, effect_table + effect_index * 0x40, effect_index, effect_table)
        effects.append(entry)
        if entry is None:
            malformed += 1
    summary["malformed_effect_rows"] = malformed
    effect_type_counts = {0: 0, 1: 0, 2: 0, 3: 0}
    for effect in effects:
        if effect is None:
            continue
        effect_type = int(effect.get("effect_type", -1))
        if effect_type in effect_type_counts:
            effect_type_counts[effect_type] += 1
    summary["effect_type_counts"] = effect_type_counts

    wanted = None
    if wanted_model_ids is not None:
        wanted = set()
        for value in wanted_model_ids:
            try:
                model_id = int(value)
            except Exception:
                continue
            if 0 <= model_id < ide_count:
                wanted.add(model_id)
        model_ids = sorted(wanted)
    else:
        model_ids = range(ide_count)

    rejected = 0
    entry_total = 0
    model_meta_by_id: Dict[int, Dict[str, object]] = {}
    for model_id in model_ids:
        model_ptr_raw = int(blds_safe_u32(data, ide_table + int(model_id) * 4, 0))
        if model_ptr_raw == 0:
            continue
        model_info = blds_resolve_dtz_offset(data, model_ptr_raw, 0x1A)
        if model_info < 0:
            rejected += 1
            continue
        try:
            model_hash = int(blds_safe_u32(data, model_info + 0x08, 0))
            model_type = int(data[model_info + 0x10])
            num_effects = int(data[model_info + 0x11])
            effect_index = int(blds_safe_i16(data, model_info + 0x18, -1))
            model_meta_by_id[int(model_id)] = {
                "model_id": int(model_id),
                "model_hash": int(model_hash),
                "model_hash_hex": f"0x{int(model_hash):08X}",
                "model_pointer_raw": int(model_ptr_raw),
                "model_info_abs": int(model_info),
                "model_type": int(model_type),
                "num_effects": int(num_effects),
                "effect_index": int(effect_index),
                "raw_0x20": bytes(data[model_info:model_info + 0x20]).hex(),
            }
        except Exception:
            rejected += 1
            continue
        if num_effects <= 0 or effect_index < 0:
            continue
        if effect_index + num_effects > effect_count:
            rejected += 1
            continue
        model_entries: List[Dict[str, object]] = []
        for global_index in range(effect_index, effect_index + num_effects):
            entry = effects[global_index] if 0 <= global_index < len(effects) else None
            if entry is None:
                continue
            copied = dict(entry)
            copied["model_id"] = int(model_id)
            copied["model_hash"] = int(model_hash)
            copied["model_hash_hex"] = f"0x{int(model_hash):08X}"
            copied["model_type"] = int(model_type)
            copied["model_info_abs"] = int(model_info)
            copied["model_effect_index"] = int(global_index - effect_index)
            model_entries.append(copied)
        if model_entries:
            mapping[int(model_id)] = model_entries
            entry_total += len(model_entries)

    summary["models_with_effects"] = len(mapping)
    summary["entries_available"] = entry_total
    summary["model_meta_by_id"] = model_meta_by_id
    summary["rejected_model_refs"] = rejected
    effect_entities, entity_pool_stats = blds_parse_game_dtz_entity_pools(data, mapping, ide_count)
    summary["effect_entities"] = effect_entities
    summary["entity_pool_stats"] = entity_pool_stats
    summary["entity_instances_with_effects"] = len(effect_entities)
    summary["entity_effect_rows"] = sum(int(entity.get("effect_count", 0)) for entity in effect_entities)
    summary["status"] = "ok"
    return mapping, summary



def blds_parse_game_dtz_entity_pools(data: bytes, model_effects: Dict[int, List[Dict[str, object]]], ide_count: int):
    """Read allocated CEntity rows from ResourceImage pools.

    ResourceImage owns building/treadable/dummy pools at file offsets 0x24,
    0x28 and 0x2C after the 0x20 relocatable-image header.  CEntity.modelIndex
    is the authoritative CBaseModelInfo index for an actual world instance.
    """
    pools = (("BUILDING", 0x24), ("TREADABLE", 0x28), ("DUMMY", 0x2C))
    entities = []
    pool_stats = {}
    for pool_name, header_off in pools:
        pool_ptr = int(blds_safe_u32(data, header_off, 0))
        pool_abs = blds_resolve_dtz_offset(data, pool_ptr, 0x20)
        stats = {"pool_pointer": pool_ptr, "size": 0, "allocated": 0, "with_effects": 0, "effect_rows": 0}
        pool_stats[pool_name] = stats
        if pool_abs < 0:
            continue
        try:
            items_ptr, flags_ptr = struct.unpack_from("<II", data, pool_abs)
            size = int(struct.unpack_from("<i", data, pool_abs + 0x08)[0])
        except Exception:
            continue
        stats["size"] = size
        if size < 0 or size > 200000:
            continue
        items_abs = blds_resolve_dtz_offset(data, int(items_ptr), max(1, size * 0x60))
        flags_abs = blds_resolve_dtz_offset(data, int(flags_ptr), max(1, size))
        if items_abs < 0 or flags_abs < 0:
            continue
        for entity_index in range(size):
            try:
                pool_flag = int(data[flags_abs + entity_index])
                if pool_flag & 0x80:
                    continue
                stats["allocated"] += 1
                entity_off = items_abs + entity_index * 0x60
                model_id = int(struct.unpack_from("<h", data, entity_off + 0x56)[0])
                model_id2 = int(struct.unpack_from("<h", data, entity_off + 0x58)[0])
                if model_id < 0 or model_id >= int(ide_count):
                    continue
                entries = model_effects.get(model_id, [])
                if not entries:
                    continue
                values = struct.unpack_from("<16f", data, entity_off)
                # RslMatrix layout is right/up/at/pos with one flag dword after
                # each XYZ vector. Ignore those W slots because they may contain
                # flags or NaN bit patterns rather than floats.
                right = (float(values[0]), float(values[1]), float(values[2]))
                up = (float(values[4]), float(values[5]), float(values[6]))
                at = (float(values[8]), float(values[9]), float(values[10]))
                pos = (float(values[12]), float(values[13]), float(values[14]))
                finite = all(math.isfinite(value) for value in right + up + at + pos)
                if not finite:
                    continue
                stats["with_effects"] += 1
                stats["effect_rows"] += len(entries)
                entities.append({
                    "pool_name": pool_name,
                    "pool_index": int(entity_index),
                    "pool_flag": int(pool_flag),
                    "entity_abs": int(entity_off),
                    "model_id": int(model_id),
                    "model_id2": int(model_id2),
                    "level": int(data[entity_off + 0x5A]),
                    "area": int(data[entity_off + 0x5B]),
                    "right": right,
                    "up": up,
                    "at": at,
                    "position": pos,
                    "effect_count": len(entries),
                })
            except Exception:
                continue
    return entities, pool_stats


def blds_entity_matrix(entity: Dict[str, object]) -> Matrix:
    right = entity.get("right", (1.0, 0.0, 0.0))
    up = entity.get("up", (0.0, 1.0, 0.0))
    at = entity.get("at", (0.0, 0.0, 1.0))
    pos = entity.get("position", (0.0, 0.0, 0.0))
    return Matrix((
        (float(right[0]), float(up[0]), float(at[0]), float(pos[0])),
        (float(right[1]), float(up[1]), float(at[1]), float(pos[1])),
        (float(right[2]), float(up[2]), float(at[2]), float(pos[2])),
        (0.0, 0.0, 0.0, 1.0),
    ))


def blds_nearest_sector_xy_for_world_position(x: float, y: float, game_hint: str = "vcs"):
    game = str(game_hint or "vcs").lower()
    if game == "lcs":
        xinc, yinc, xstart, ystart = 100.0, 86.6, -2000.0, -2000.0
    else:
        xinc, yinc, xstart, ystart = 125.0, 108.25, -2400.0, -2000.0
    row_guess = int(math.floor((float(y) - (ystart + yinc * 0.5)) / yinc))
    best = None
    for sector_y in range(row_guess - 2, row_guess + 4):
        xbase = xstart + xinc * 0.5 - ((sector_y & 1) * xinc * 0.5)
        col_guess = int(math.floor((float(x) - xbase) / xinc))
        for sector_x in range(col_guess - 2, col_guess + 4):
            cx = xbase + xinc * sector_x
            cy = ystart + yinc * 0.5 + yinc * sector_y
            dx = float(x) - cx
            dy = float(y) - cy
            distance2 = dx * dx + dy * dy
            if best is None or distance2 < best[0]:
                best = (distance2, int(sector_x), int(sector_y))
    return (best[1], best[2]) if best is not None else (0, 0)


def blds_build_placed_object_spatial_index(records, bucket_size: float = 8.0):
    buckets = {}
    for record in records or []:
        try:
            key = (int(math.floor(float(record["world_x"]) / bucket_size)), int(math.floor(float(record["world_y"]) / bucket_size)))
            buckets.setdefault(key, []).append(record)
        except Exception:
            continue
    return buckets


def blds_find_parent_for_game_entity(entity, spatial_index, bucket_size: float = 8.0, max_distance: float = 4.0):
    try:
        x, y, z = entity.get("position", (0.0, 0.0, 0.0))
        model_id = int(entity.get("model_id", -1))
        bx = int(math.floor(float(x) / bucket_size))
        by = int(math.floor(float(y) / bucket_size))
    except Exception:
        return None
    best = None
    for ox in (-1, 0, 1):
        for oy in (-1, 0, 1):
            for record in spatial_index.get((bx + ox, by + oy), []):
                try:
                    dx = float(record["world_x"]) - float(x)
                    dy = float(record["world_y"]) - float(y)
                    dz = float(record["world_z"]) - float(z)
                    distance = math.sqrt(dx * dx + dy * dy + dz * dz)
                    same_model = int(record.get("game_model_id", -1)) == model_id
                    if not same_model and distance > 0.35:
                        continue
                    if distance > max_distance:
                        continue
                    score = distance + (0.0 if same_model else 100.0)
                    if str(record.get("pass_name", "")).upper() == "LIGHTS":
                        score += 25.0
                    if best is None or score < best[0]:
                        best = (score, record)
                except Exception:
                    continue
    return best[1] if best is not None else None


def blds_import_game_entity_2dfx_helpers(collection, import_stem: str, model_effects, summary, sector_records, placed_records):
    """Import authoritative entity-owned 2DFX for the current LVZ sector grid."""
    if collection is None or not model_effects:
        return 0
    entities = list(summary.get("effect_entities", []) or [])
    active_cells = {
        (int(record.get("sector_x", 0)), int(record.get("sector_y", 0)))
        for record in (sector_records or [])
    }
    game_hint = str((sector_records or [{}])[0].get("game_hint", "vcs")) if sector_records else "vcs"
    spatial_index = blds_build_placed_object_spatial_index(placed_records)
    selected = []
    seen = set()
    selected_by_pool = {}
    selected_by_reason = {}
    for entity in entities:
        try:
            x, y, z = entity.get("position", (0.0, 0.0, 0.0))
            sector_xy = blds_nearest_sector_xy_for_world_position(x, y, game_hint)
            parent_record = blds_find_parent_for_game_entity(entity, spatial_index)
            selection_reason = "ENTITY_ORIGIN_CELL" if (not active_cells or sector_xy in active_cells) else ""
            # A model origin may sit just outside the final concrete sector while
            # one or more of its native 2DFX points cross into it. Test the actual
            # transformed effect positions before rejecting the entity.
            if active_cells and not selection_reason and parent_record is None:
                try:
                    entity_matrix = blds_entity_matrix(entity)
                    model_entries = model_effects.get(int(entity.get("model_id", -1)), [])
                    for model_entry in model_entries:
                        local_effect = Vector((
                            float(model_entry.get("x", 0.0)),
                            float(model_entry.get("y", 0.0)),
                            float(model_entry.get("z", 0.0)),
                        ))
                        effect_world = entity_matrix @ local_effect
                        effect_cell = blds_nearest_sector_xy_for_world_position(effect_world.x, effect_world.y, game_hint)
                        if effect_cell in active_cells:
                            selection_reason = "EFFECT_POINT_CELL"
                            break
                except Exception:
                    pass
            if parent_record is not None:
                selection_reason = "MATCHED_MAP_OBJECT"
            if active_cells and not selection_reason:
                continue
            entity["selection_reason"] = str(selection_reason or "NO_ACTIVE_CELL_FILTER")
            key = (
                str(entity.get("pool_name", "")), int(entity.get("pool_index", -1)), int(entity.get("model_id", -1)),
                round(float(x), 5), round(float(y), 5), round(float(z), 5),
            )
            if key in seen:
                continue
            seen.add(key)
            selected.append((entity, sector_xy, parent_record))
            pool_name = str(entity.get("pool_name", "UNKNOWN"))
            selected_by_pool[pool_name] = int(selected_by_pool.get(pool_name, 0)) + 1
            reason_name = str(entity.get("selection_reason", "UNKNOWN"))
            selected_by_reason[reason_name] = int(selected_by_reason.get(reason_name, 0)) + 1
        except Exception:
            continue

    made = 0
    attached_instances = 0
    unattached_instances = 0
    imported_helpers_by_pool = {}
    for entity, sector_xy, parent_record in selected:
        model_id = int(entity.get("model_id", -1))
        entries = model_effects.get(model_id, [])
        if not entries:
            continue
        parent_obj = parent_record.get("object") if parent_record else None
        visible_res = int(parent_record.get("res_id", -1)) if parent_record else -1
        row_link = int(parent_record.get("row_link_id", -1)) if parent_record else -1
        sector_index = int(parent_record.get("sector_index", -1)) if parent_record else -1
        row_index = int(parent_record.get("row_index", -1)) if parent_record else -1
        pass_name = str(parent_record.get("pass_name", "GAME_ENTITY")) if parent_record else "GAME_ENTITY"
        matrix = blds_entity_matrix(entity)
        count = blds_create_placed_model_2dfx_helpers(
            collection,
            parent_obj,
            import_stem,
            visible_res_id=visible_res,
            game_model_id=model_id,
            placement_ipl_id=row_link,
            entries=entries,
            sector_index=sector_index,
            row_index=row_index,
            pass_name=pass_name,
            instance_index=int(entity.get("pool_index", 0)),
            placement_matrix=matrix,
            split_res_ids=[visible_res] if visible_res >= 0 else [],
            source_path=str(summary.get("source_path", "")),
            native_entity_matrix=True,
            mapping_basis="GAME_DTZ_CENTITY_MODEL_INDEX",
            entity_pool_name=str(entity.get("pool_name", "")),
            entity_pool_index=int(entity.get("pool_index", -1)),
            entity_sector_xy=sector_xy,
            parent_to_placed=True,
        )
        if count:
            made += count
            pool_name = str(entity.get("pool_name", "UNKNOWN"))
            imported_helpers_by_pool[pool_name] = int(imported_helpers_by_pool.get(pool_name, 0)) + int(count)
            if parent_obj is not None:
                attached_instances += 1
                try:
                    blds_attach_model_2dfx_metadata(
                        parent_obj, visible_res, model_id, row_link, entries, summary,
                        mapping_basis="GAME_DTZ_CENTITY_MODEL_INDEX",
                        transform_mode="GAME_DTZ_CENTITY_NATIVE_WORLD_MATRIX",
                    )
                except Exception:
                    pass
            else:
                unattached_instances += 1

    summary["entity_instances_selected"] = len(selected)
    summary["entity_instances_attached"] = attached_instances
    summary["entity_instances_unattached"] = unattached_instances
    summary["entity_selected_by_pool"] = dict(selected_by_pool)
    summary["entity_selected_by_reason"] = dict(selected_by_reason)
    summary["entity_imported_helpers_by_pool"] = dict(imported_helpers_by_pool)
    summary["active_sector_cells"] = len(active_cells)
    summary["effects_imported"] = made
    summary["instances_with_effects"] = attached_instances + unattached_instances
    summary["identity_basis"] = "GAME_DTZ_CENTITY_MODEL_INDEX"
    LVZ.dbg(
        f"[2dfx-entity] pool_instances={len(entities)} selected_in_lvz_grid={len(selected)} "
        f"attached={attached_instances} unattached={unattached_instances} helpers={made} "
        f"active_sector_cells={len(active_cells)} reasons={dict(selected_by_reason)}"
    )
    return made

def blds_find_game_dtz(lvz_path: str, explicit_path: str = "") -> str:
    candidates: List[Path] = []
    if explicit_path:
        try:
            resolved = bpy.path.abspath(explicit_path)
        except Exception:
            resolved = explicit_path
        candidates.append(Path(resolved))
    try:
        parent = Path(lvz_path).resolve().parent
    except Exception:
        parent = Path(lvz_path).parent
    try:
        children = [child for child in parent.iterdir() if child.is_file()]
        for child in children:
            if child.name.lower() == "game.dtz":
                candidates.append(child)
        # Browser/download copy suffixes are accepted silently; no extra file
        # selector is exposed.  Exact GAME.DTZ remains first priority.
        for child in children:
            if child.suffix.lower() != ".dtz":
                continue
            if normalized_copy_stem(child.stem).lower() == "game":
                candidates.append(child)
    except Exception:
        pass
    seen = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve()).lower()
        except Exception:
            key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            if candidate.is_file():
                return str(candidate)
        except Exception:
            continue
    return ""


def blds_parse_game_dtz_2dfx(lvz_path: str, explicit_path: str = "", wanted_model_ids=None) -> Tuple[Dict[int, List[Dict[str, object]]], Dict[str, object]]:
    source_path = blds_find_game_dtz(lvz_path, explicit_path)
    if not source_path:
        return {}, {
            "status": "not_found",
            "source_path": "",
            "compressed": False,
            "ide_count": 0,
            "effect_count": 0,
            "models_with_effects": 0,
            "entries_available": 0,
            "rejected_model_refs": 0,
            "malformed_effect_rows": 0,
            "effect_type_counts": {0: 0, 1: 0, 2: 0, 3: 0},
            "effects_imported": 0,
            "instances_with_effects": 0,
        }
    try:
        raw = Path(source_path).read_bytes()
        data, was_compressed = LVZ.safe_decompress(raw)
        mapping, summary = blds_parse_game_dtz_2dfx_bytes(data, wanted_model_ids=wanted_model_ids)
        summary["source_path"] = str(source_path)
        summary["compressed"] = bool(was_compressed)
        summary["input_bytes"] = len(raw)
        summary["decompressed_bytes"] = len(data)
        return mapping, summary
    except Exception as exc:
        return {}, {
            "status": "read_failed",
            "source_path": str(source_path),
            "error": str(exc),
            "compressed": False,
            "ide_count": 0,
            "effect_count": 0,
            "models_with_effects": 0,
            "entries_available": 0,
            "rejected_model_refs": 0,
            "malformed_effect_rows": 0,
            "effect_type_counts": {0: 0, 1: 0, 2: 0, 3: 0},
            "effects_imported": 0,
            "instances_with_effects": 0,
        }


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


def blds_2dfx_placement_key(game_model_id: int, detail) -> Tuple:
    """Return one runtime-placement key shared by split streamed resources.

    Opaque/transparent/underwater pieces of one model carry different RES ids but
    the same AERA model-info id, ROWLINK, row basis and world translation.  2DFX
    belongs to the runtime model placement, so those pieces must share one helper
    set.
    """
    try:
        values = detail[12]
        origin = detail[18] if len(detail) > 18 else (0.0, 0.0, 0.0)
        tx = float(values[12]) + float(origin[0])
        ty = float(values[13]) + float(origin[1])
        tz = float(values[14]) + float(origin[2])
        basis = tuple(round(float(values[index]), 6) for index in range(12))
        return (
            int(game_model_id),
            int(detail[4]),
            round(tx, 5), round(ty, 5), round(tz, 5),
            basis,
        )
    except Exception:
        return (int(game_model_id), int(id(detail)))


def blds_2dfx_native_model_matrix(placement_matrix: Matrix) -> Tuple[Matrix, Tuple[float, float, float]]:
    """Remove streamed-geometry quantization scale from a placement matrix.

    AERA/WRLD mesh vertices are normalized around roughly [-1, 1].  The three
    placement-basis column lengths expand that normalized geometry back to world
    size.  C2dEffect.position is already stored in native model units, so applying
    those lengths again multiplies positions by values such as 16/32/64/128 and
    scatters helpers hundreds or thousands of metres away.

    Keep the exact placement translation and handed basis directions, but make
    every basis column unit length before transforming GAME.DTZ positions.
    """
    result = Matrix.Identity(4)
    scales = []
    for column_index in range(3):
        column = Vector((
            float(placement_matrix[0][column_index]),
            float(placement_matrix[1][column_index]),
            float(placement_matrix[2][column_index]),
        ))
        length = float(column.length)
        scales.append(length)
        if math.isfinite(length) and length > 1.0e-10:
            column /= length
        else:
            column = Vector((
                1.0 if column_index == 0 else 0.0,
                1.0 if column_index == 1 else 0.0,
                1.0 if column_index == 2 else 0.0,
            ))
        result[0][column_index] = float(column.x)
        result[1][column_index] = float(column.y)
        result[2][column_index] = float(column.z)
    result[0][3] = float(placement_matrix[0][3])
    result[1][3] = float(placement_matrix[1][3])
    result[2][3] = float(placement_matrix[2][3])
    result[3][0] = 0.0
    result[3][1] = 0.0
    result[3][2] = 0.0
    result[3][3] = 1.0
    return result, (float(scales[0]), float(scales[1]), float(scales[2]))


def blds_2dfx_entry_native_direction(entry: Dict[str, object]) -> Optional[Vector]:
    effect_type = int(entry.get("effect_type", -1))
    prefix = None
    if effect_type == 1:
        prefix = "direction"
    elif effect_type == 2:
        prefix = "attractor_direction"
    elif effect_type == 3:
        prefix = "ped_direction"
    if prefix is None:
        return None
    try:
        direction = Vector((
            float(entry.get(prefix + "_x", 0.0)),
            float(entry.get(prefix + "_y", 0.0)),
            float(entry.get(prefix + "_z", 0.0)),
        ))
        if not all(math.isfinite(float(value)) for value in direction):
            return None
        return direction
    except Exception:
        return None


def blds_clear_model_2dfx_collection(collection):
    if collection is None:
        return
    try:
        for obj in list(collection.objects):
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except Exception:
                pass
    except Exception:
        pass


def blds_attach_model_2dfx_metadata(obj, visible_res_id: int, game_model_id: int, placement_ipl_id: int, entries: List[Dict[str, object]], summary: Optional[Dict[str, object]] = None, mapping_basis: str = "MASTER_AERA_SECONDARY_ID", transform_mode: str = "GAME_DTZ_NATIVE_MODEL_SPACE_SCALE_STRIPPED_BASIS"):
    """Attach namespaced Leeds metadata without touching another add-on's RNA."""
    if obj is None or not entries:
        return
    try:
        obj["blds_2dfx_count"] = int(len(entries))
        obj["blds_2dfx_source"] = "GAME.DTZ"
        obj["blds_2dfx_visible_res_id"] = int(visible_res_id)
        obj["blds_2dfx_game_model_id"] = int(game_model_id)
        obj["blds_2dfx_model_id"] = int(game_model_id)
        obj["blds_2dfx_placement_ipl_id"] = int(placement_ipl_id)  # compatibility alias
        obj["blds_2dfx_row_link_id"] = int(placement_ipl_id)
        obj["blds_2dfx_mapping_basis"] = str(mapping_basis)
        obj["blds_2dfx_transform_mode"] = str(transform_mode)
        obj["blds_2dfx_json"] = json.dumps(entries, separators=(",", ":"), sort_keys=True)
        if summary:
            obj["blds_2dfx_source_path"] = str(summary.get("source_path", ""))
            obj["blds_2dfx_game_dtz_effect_count"] = int(summary.get("effect_count", 0))
    except Exception:
        pass


def blds_create_placed_model_2dfx_helpers(collection, placed_obj, import_stem: str, visible_res_id: int, game_model_id: int, placement_ipl_id: int, entries: List[Dict[str, object]], sector_index: int, row_index: int, pass_name: str, instance_index: int, placement_matrix: Matrix, split_res_ids=None, source_path: str = "", native_entity_matrix: bool = False, mapping_basis: str = "MASTER_AERA_SECONDARY_ID", entity_pool_name: str = "", entity_pool_index: int = -1, entity_sector_xy=None, parent_to_placed: bool = False) -> int:
    """Create one plain BLeeds helper set for one runtime model placement.

    ``C2dEffect.position`` is native model-space data.  The streamed geometry
    object matrix contains a second, implicit normalization scale used to expand
    quantized AERA/WRLD vertices.  The helper transform therefore uses the same
    translation and basis directions with those column lengths stripped.

    No DemonFF RNA is written.
    """
    if collection is None or not entries:
        return 0
    try:
        if native_entity_matrix:
            native_matrix = placement_matrix.copy()
            stream_scales = (1.0, 1.0, 1.0)
        else:
            native_matrix, stream_scales = blds_2dfx_native_model_matrix(placement_matrix)
    except Exception as exc:
        LVZ.dbg(
            f"[2dfx-model] native placement matrix failed for RES={int(visible_res_id)} "
            f"GAME_MODEL={int(game_model_id)} ROWLINK={int(placement_ipl_id)}: {exc}"
        )
        return 0

    split_res_ids = sorted({int(value) for value in (split_res_ids or [visible_res_id]) if int(value) >= 0})
    split_res_text = ",".join(str(value) for value in split_res_ids)
    rotation3 = native_matrix.to_3x3()
    made = 0
    for entry in entries:
        try:
            effect_type = int(entry.get("effect_type", -1))
            global_index = int(entry.get("global_index", entry.get("index", 0)))
            local = Vector((
                float(entry.get("x", 0.0)),
                float(entry.get("y", 0.0)),
                float(entry.get("z", 0.0)),
            ))
            world = native_matrix @ local
            if placed_obj is not None:
                owner_token = str(getattr(placed_obj, "name", "")) or f"{import_stem}{int(visible_res_id)}"
            elif int(visible_res_id) >= 0:
                owner_token = f"{import_stem}{int(visible_res_id)}"
            else:
                owner_token = f"{import_stem}_{str(entity_pool_name or 'ENTITY').lower()}{int(entity_pool_index):04d}"
            helper = bpy.data.objects.new(
                f"{owner_token}_2DFX_g{int(game_model_id)}_"
                f"r{int(placement_ipl_id)}_{int(instance_index):03d}_{global_index:04d}",
                None,
            )
            helper.empty_display_type = 'SPHERE' if effect_type == 0 else 'ARROWS'
            helper.empty_display_size = 0.25
            # Keep display helpers unscaled. Light spheres need only a world
            # position; directional effect arrows receive their own direction
            # rotation below. All source basis data is retained as metadata.
            helper_matrix = Matrix.Identity(4)
            helper_matrix[0][3] = float(world.x)
            helper_matrix[1][3] = float(world.y)
            helper_matrix[2][3] = float(world.z)
            helper.matrix_world = helper_matrix
            helper["blds_kind"] = "LEEDS_2DFX"
            helper["blds_2dfx_source"] = "GAME.DTZ"
            helper["blds_2dfx_source_path"] = str(source_path or "")
            helper["blds_2dfx_parent_object"] = str(getattr(placed_obj, "name", "")) if placed_obj is not None else ""
            helper["blds_2dfx_attached_to_object"] = bool(placed_obj is not None)
            helper["blds_2dfx_visible_res_id"] = int(visible_res_id)
            helper["blds_2dfx_split_res_ids"] = str(split_res_text)
            helper["blds_2dfx_game_model_id"] = int(game_model_id)
            helper["blds_2dfx_model_id"] = int(game_model_id)
            helper["blds_2dfx_placement_ipl_id"] = int(placement_ipl_id)  # compatibility alias
            helper["blds_2dfx_row_link_id"] = int(placement_ipl_id)
            helper["blds_2dfx_mapping_basis"] = str(mapping_basis)
            helper["blds_2dfx_transform_mode"] = "GAME_DTZ_CENTITY_NATIVE_WORLD_MATRIX" if native_entity_matrix else "GAME_DTZ_NATIVE_MODEL_SPACE_SCALE_STRIPPED_BASIS"
            helper["blds_2dfx_entity_pool_name"] = str(entity_pool_name or "")
            helper["blds_2dfx_entity_pool_index"] = int(entity_pool_index)
            try:
                helper["blds_2dfx_collection_name"] = str(collection.name)
                root_collection = globals().get("_ACTIVE_IMPORT_ROOT_COLLECTION")
                helper["blds_import_root_collection"] = str(root_collection.name) if root_collection is not None else ""
            except Exception:
                pass
            if entity_sector_xy is not None:
                helper["blds_2dfx_entity_sector_x"] = int(entity_sector_xy[0])
                helper["blds_2dfx_entity_sector_y"] = int(entity_sector_xy[1])
            helper["blds_2dfx_stream_basis_scale_x"] = float(stream_scales[0])
            helper["blds_2dfx_stream_basis_scale_y"] = float(stream_scales[1])
            helper["blds_2dfx_stream_basis_scale_z"] = float(stream_scales[2])
            helper["blds_2dfx_native_x"] = float(local.x)
            helper["blds_2dfx_native_y"] = float(local.y)
            helper["blds_2dfx_native_z"] = float(local.z)
            helper["blds_2dfx_world_x"] = float(world.x)
            helper["blds_2dfx_world_y"] = float(world.y)
            helper["blds_2dfx_world_z"] = float(world.z)
            helper["blds_2dfx_effect_type"] = effect_type
            helper["blds_2dfx_effect_type_name"] = blds_2dfx_effect_type_name(effect_type)
            helper["blds_2dfx_global_index"] = global_index
            helper["blds_2dfx_model_effect_index"] = int(entry.get("model_effect_index", -1))
            helper["blds_2dfx_color_r"] = int(entry.get("r", 0))
            helper["blds_2dfx_color_g"] = int(entry.get("g", 0))
            helper["blds_2dfx_color_b"] = int(entry.get("b", 0))
            helper["blds_2dfx_color_a"] = int(entry.get("a", 0))
            helper["blds_2dfx_raw_hex"] = str(entry.get("raw_hex", ""))
            helper["blds_img_sector_index"] = int(sector_index)
            helper["blds_img_row_index"] = int(row_index)
            helper["blds_img_pass_name"] = str(pass_name)
            helper["blds_img_instance_index"] = int(instance_index)

            native_direction = blds_2dfx_entry_native_direction(entry)
            if native_direction is not None:
                world_direction = rotation3 @ native_direction
                helper["blds_2dfx_native_direction_x"] = float(native_direction.x)
                helper["blds_2dfx_native_direction_y"] = float(native_direction.y)
                helper["blds_2dfx_native_direction_z"] = float(native_direction.z)
                helper["blds_2dfx_world_direction_x"] = float(world_direction.x)
                helper["blds_2dfx_world_direction_y"] = float(world_direction.y)
                helper["blds_2dfx_world_direction_z"] = float(world_direction.z)
                try:
                    if float(world_direction.length) > 1.0e-10:
                        arrow_matrix = world_direction.normalized().to_track_quat('Z', 'Y').to_matrix().to_4x4()
                        arrow_matrix[0][3] = float(world.x)
                        arrow_matrix[1][3] = float(world.y)
                        arrow_matrix[2][3] = float(world.z)
                        helper.matrix_world = arrow_matrix
                        helper["blds_2dfx_arrow_orientation"] = "WORLD_DIRECTION"
                except Exception:
                    pass

            for key, value in entry.items():
                if key in {"raw_hex", "payload_hex", "x", "y", "z", "r", "g", "b", "a", "effect_type", "global_index", "index", "model_id"}:
                    continue
                if isinstance(value, (int, float, str, bool)):
                    try:
                        helper["blds_2dfx_" + str(key)] = value
                    except Exception:
                        pass
            stamp_bleeds_entity_type(helper, "2DFX")
            collection.objects.link(helper)
            if parent_to_placed and placed_obj is not None:
                try:
                    world_matrix = helper.matrix_world.copy()
                    helper.parent = placed_obj
                    helper.matrix_world = world_matrix
                except Exception:
                    pass
            made += 1
        except Exception as exc:
            LVZ.dbg(
                f"[2dfx-model] helper creation failed for RES={int(visible_res_id)} "
                f"GAME_MODEL={int(game_model_id)} ROWLINK={int(placement_ipl_id)}: {exc}"
            )
    return made

def import_lvz_img_archive(operator, context, lvz_path: str, csv_dedup_res_ids: bool = True, apply_img_transforms: bool = True, debug_print: bool = False, write_debug_log: bool = True, game_dtz_path: str = "", import_game_dtz_2dfx: bool = True):
    # LVZ+IMG imports are long and can crash/cancel near the end while debugging.
    # Always leave a live log beside the LVZ so the last useful lines are not lost.
    write_debug_log = True
    if not lvz_path:
        operator.report({'ERROR'}, "No LVZ selected.")
        return {'CANCELLED'}

    progress = LvzImgImportProgress(operator, context).begin("Reading LVZ container")
    progress.update(1, "Reading LVZ container", force=True)

    stem = normalized_copy_stem(Path(lvz_path).stem) or Path(lvz_path).stem
    globals()["_CURRENT_IMPORT_STEM"] = stem
    globals()["_CURRENT_PLACED_OBJECT_RECORDS"] = []
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
    create_game_dtz_2dfx_helpers = bool(CREATE_GAME_DTZ_2DFX_HELPERS and import_game_dtz_2dfx)
    lvz_bytes_in = Path(lvz_path).read_bytes()
    decomp, was_cmp = LVZ.safe_decompress(lvz_bytes_in)
    progress.update(4, "Decoding LVZ container")

    LVZ.dbg("===== LVZ + IMG Import =====")
    LVZ.dbg("Patch: LVZ_IMG_GAME_ENTITY_2DFX_COLLECTIONS_V121")
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

    LVZ.dbg(f"LVZ: {lvz_path}")
    LVZ.dbg(f"[io] LVZ bytes in: {len(lvz_bytes_in)}  decomp: {len(decomp)} ({'compressed' if was_cmp else 'raw'})")
    LVZ.dbg("Retail LVZ+IMG import: no .DIR used. IMG resources are reconstructed from LVZ chunk headers and exact WRLD/AERA resource tables.")
    # Converter IDE/IPL sidecars are not part of the LVZ/IMG placement path.
    # Keep compatibility maps empty; authoritative GAME_MODEL identity is read
    # from master AreaInfo -> AERA AreaResource.secondaryId below.
    ide_ipl_to_res = {}
    ide_ipl_to_name = {}
    ide_res_to_model_id = {}
    ide_res_to_name = {}
    ide_ambiguous_res = {}
    ide_path_used = None
    LVZ.dbg("[identity] converter IDE/IPL identity disabled; master AERA secondaryId is authoritative")
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

    try:
        import_root_collection, import_objects_collection, import_linked_collection, import_2dfx_collection = blds_prepare_import_collection_tree(lvz_path, img_name)
        LVZ.dbg(f"[collections] root={import_root_collection.name if import_root_collection else 'none'} objects={import_objects_collection.name if import_objects_collection else 'none'} linked={import_linked_collection.name if import_linked_collection else 'none'} 2dfx={import_2dfx_collection.name if import_2dfx_collection else 'none'}")
    except Exception as exc:
        import_root_collection = import_objects_collection = import_linked_collection = import_2dfx_collection = None
        LVZ.dbg(f"[collections] source-named hierarchy setup failed: {exc}")

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
    # IMG-only model recovery is intentionally delayed until every exact WRLD
    # resource table has been checked.  This prevents texture-number matches
    # from replacing a real same-sector, master, linked, or AREA model.

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
        sector_details = img.enumerate_sector_details(
            max_resource_id=res_count,
            include_lod=IMPORT_LOD_PASSES_BY_DEFAULT,
            dedupe_visible=True,
            progress_callback=lambda index, total: progress.update_range(22, 26, index, total, "Reading IMG sector placements"),
        )
        # Only concrete sector IPL tables place static map objects.  The broader
        # parent/nested container scan is useful for finding exact model data,
        # but its rows include triggered/auxiliary data and do not form another
        # static IPL.  Importing those rows created the shifted beach and sand
        # copies far outside the real map.
        extra_details = []
        LVZ.dbg(
            "Triggered and AREA blocks are used to find model data only; their rows are not added as extra static map placements."
        )
        details = img.merge_instance_details(sector_details)
        merge_stats = getattr(img, "last_merge_instance_stats", {}) or {}
        stats = getattr(img, "last_sector_walk_stats", {}) or {}
        extra_stats = {}
        exact_duplicate_rows = (
            int(stats.get("skipped_duplicate_rows", 0))
            + int(extra_stats.get("skipped_duplicate_rows", 0))
            + int(merge_stats.get("duplicate_visible_rows", 0))
            + int(merge_stats.get("duplicate_source_rows", 0))
        )
        LVZ.dbg(
            f"[speed] exact duplicate visible placement rows removed: "
            f"{exact_duplicate_rows}; duplicate source rows removed: 0; "
            f"retained={merge_stats.get('kept_rows', len(details))}"
        )
        lights_kept = sum(1 for detail in details if len(detail) > 14 and str(detail[14]).upper() == "LIGHTS")
        LVZ.dbg(f"[img] LIGHTS mesh placements kept: {lights_kept}")
        try:
            from collections import Counter
            pass_counts = Counter(str(detail[14]).upper() for detail in details if len(detail) > 14)
            pass_order = ("UNDERWATER", "ROADS", "NORMAL", "NOZWRITE", "LIGHTS", "TRANSPARENT")
            pass_text = ", ".join(f"{name}={int(pass_counts.get(name, 0))}" for name in pass_order if pass_counts.get(name, 0))
            if pass_text:
                LVZ.dbg(f"Placements by render pass: {pass_text}")
        except Exception:
            pass
        LVZ.dbg(
            f"[img] sector rows candidate={stats.get('candidate_rows', 0)} valid={stats.get('valid_rows', 0)} "
            f"kept={stats.get('kept_rows', 0)} skipped_lod={stats.get('skipped_lod_rows', 0)} "
            f"skipped_dupes={stats.get('skipped_duplicate_rows', 0)}"
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

    # Resolve GAME.DTZ model-info ownership from the authoritative AERA row:
    #   AreaResource.id1 = streamed RES
    #   AreaResource.id2 = CBaseModelInfo / GAME.DTZ model-info index
    # detail[4] remains ROWLINK and is never used as model identity.
    placement_identity_by_key = {}
    area_model_info_by_res = {}
    area_model_info_provenance = {}
    area_model_info_conflicts = {}
    area_records_for_identity = []
    if img is not None:
        try:
            area_records_for_identity = img.find_area_info_records_from_lvz()
            visible_res_ids = {
                int(detail[0]) for detail in (details or [])
                if detail and int(detail[0]) >= 0
            }
            area_model_info_by_res, area_model_info_provenance, area_model_info_conflicts = img.build_area_model_info_map(
                area_records=area_records_for_identity,
                wanted_res_ids=visible_res_ids,
                max_resource_id=int(res_count),
            )
        except Exception as exc:
            LVZ.dbg(f"[identity] master AERA RES->GAME_MODEL parse failed: {exc}")
            area_model_info_by_res = {}
            area_model_info_provenance = {}
            area_model_info_conflicts = {}

    matched_identity_rows = 0
    for detail in details or []:
        key = blds_placement_report_key(detail)
        res_id = int(detail[0])
        game_model_id = int(area_model_info_by_res.get(res_id, -1))
        provenance = area_model_info_provenance.get(res_id, {}) or {}
        if game_model_id >= 0:
            matched_identity_rows += 1
        placement_identity_by_key[key] = {
            "game_model_id": game_model_id,
            "model_name": "",
            "source": "MASTER_AERA_SECONDARY_ID" if game_model_id >= 0 else "UNRESOLVED",
            "position_error": None,
            "ipl_line": -1,
            "area_index": int(provenance.get("area_index", -1)),
            "area_resource_index": int(provenance.get("resource_index", -1)),
            "area_resource_row_off": int(provenance.get("resource_row_off", -1)),
            "area_resource_raw_off": int(provenance.get("raw_off", -1)),
        }

    area_identity_stats = getattr(img, "last_area_model_info_stats", {}) if img is not None else {}
    identity_summary = {
        "source": "MASTER_AERA_SECONDARY_ID",
        "areas": len(area_records_for_identity),
        "mapped_res_ids": len(area_model_info_by_res),
        "matched_rows": int(matched_identity_rows),
        "unresolved": max(0, len(details or []) - int(matched_identity_rows)),
        "conflicting_res_ids": len(area_model_info_conflicts),
        "aera_rows": int((area_identity_stats or {}).get("rows", 0)),
        "valid_pointer_rows": int((area_identity_stats or {}).get("valid_pointer_rows", 0)),
        # Compatibility fields retained for old report readers.  No sidecar or
        # position-based identity is used.
        "ipl_path": "",
        "matched_by_position": 0,
        "ide_name_fallback": 0,
    }
    LVZ.dbg(
        f"[identity] master AERA RES->GAME_MODEL areas={len(area_records_for_identity)} "
        f"mapped_res={len(area_model_info_by_res)} matched_rows={int(matched_identity_rows)} "
        f"unresolved={int(identity_summary.get('unresolved', 0))} conflicts={len(area_model_info_conflicts)}"
    )

    progress.update(27, "Reading model 2DFX metadata")
    model_2dfx_by_game_model_id, two_dfx_summary = blds_parse_game_dtz_2dfx(
        lvz_path,
        explicit_path=game_dtz_path,
        wanted_model_ids=None,
    )
    two_dfx_summary["helpers_enabled"] = bool(create_game_dtz_2dfx_helpers)
    two_dfx_summary["identity_basis"] = "GAME_DTZ_CENTITY_MODEL_INDEX"
    two_dfx_summary["identity_matches"] = int(matched_identity_rows)
    two_dfx_summary["area_model_info_mapped_res_ids"] = len(area_model_info_by_res)
    two_dfx_summary["area_model_info_conflicting_res_ids"] = len(area_model_info_conflicts)
    model_2dfx_collection = globals().get("_ACTIVE_IMPORT_2DFX_COLLECTION")
    if model_2dfx_collection is not None:
        blds_clear_model_2dfx_collection(model_2dfx_collection)
    if create_game_dtz_2dfx_helpers and model_2dfx_collection is None:
        model_2dfx_collection = get_or_create_import_collection(f"{stem} 2DFX", globals().get("_ACTIVE_IMPORT_ROOT_COLLECTION"))
    if str(two_dfx_summary.get("status", "")) == "not_found":
        LVZ.dbg(
            "[2dfx-model] no GAME.DTZ found beside the LVZ; allocated world entity pools and "
            "global C2dEffect rows are unavailable. LIGHTS mesh rows remain separate. "
            "A placement/RES report will still be written."
        )
    elif str(two_dfx_summary.get("status", "")) != "ok":
        LVZ.dbg(
            f"[2dfx-model] GAME.DTZ parse failed status={two_dfx_summary.get('status', '')} "
            f"source={two_dfx_summary.get('source_path', '')} error={two_dfx_summary.get('error', '')}"
        )
    else:
        LVZ.dbg(
            f"[2dfx-model] GAME.DTZ source={two_dfx_summary.get('source_path', '')} "
            f"model_infos={int(two_dfx_summary.get('ide_count', 0))} "
            f"global_effects={int(two_dfx_summary.get('effect_count', 0))} "
            f"GAME_MODEL_ids_with_effects={int(two_dfx_summary.get('models_with_effects', 0))} "
            f"entries_available={int(two_dfx_summary.get('entries_available', 0))} "
            f"malformed_rows={int(two_dfx_summary.get('malformed_effect_rows', 0))}"
        )
        effect_type_counts = two_dfx_summary.get("effect_type_counts", {}) or {}
        LVZ.dbg(
            f"[2dfx-model] global effect types: "
            f"light={int(effect_type_counts.get(0, 0))} "
            f"particle={int(effect_type_counts.get(1, 0))} "
            f"attractor={int(effect_type_counts.get(2, 0))} "
            f"ped_behaviour={int(effect_type_counts.get(3, 0))}"
        )
        LVZ.dbg(
            "[2dfx-model] helper creation {} for this import; ownership=allocated GAME.DTZ CEntity.modelIndex; "
            "transform=CEntity world matrix x native C2dEffect position; entity instances are level-grid filtered"
            .format("ENABLED" if create_game_dtz_2dfx_helpers else "DISABLED")
        )
        beach3528_rows = []
        for detail in details or []:
            try:
                if int(detail[0]) == 3528:
                    identity = placement_identity_by_key.get(blds_placement_report_key(detail), {}) or {}
                    beach3528_rows.append((
                        int(identity.get("game_model_id", -1)), int(detail[4]),
                        int(detail[15]) if len(detail) > 15 else -1,
                        int(detail[19]) if len(detail) > 19 else -1,
                        str(detail[14]) if len(detail) > 14 else "UNKNOWN",
                    ))
            except Exception:
                continue
        if beach3528_rows:
            seen_beach3528 = set()
            for game_model_id, row_link_id, sector_index, row_index, pass_name in beach3528_rows:
                key = (game_model_id, row_link_id, sector_index, row_index, pass_name)
                if key in seen_beach3528:
                    continue
                seen_beach3528.add(key)
                count = len(model_2dfx_by_game_model_id.get(int(game_model_id), [])) if game_model_id >= 0 else 0
                LVZ.dbg(
                    f"[2dfx-model] Beach3528 GAME_MODEL={int(game_model_id)} ROWLINK={int(row_link_id)} "
                    f"RES=3528 effects={int(count)} sector={int(sector_index)} row={int(row_index)} pass={str(pass_name)}"
                )
        else:
            LVZ.dbg("[2dfx-model] Beach3528 has no visible placement row in this LVZ/IMG import")
    lights_stats = blds_count_lights_pass_rows(
        img, img_bytes, sector_records, extra_container_records, int(res_count)
    )
    LVZ.dbg(
        f"[2dfx-model] LIGHTS remains a mesh pass: candidate_rows={lights_stats.get('candidate', 0)} "
        f"valid_rows={lights_stats.get('valid', 0)}"
    )

    LVZ.dbg("[progress] building LVZ resource MDLs")
    if LVZ.DEBUG is not None:
        LVZ.DEBUG.flush()
    built_by_res = build_lvz_resource_mdl_objects(
        lvz,
        rows,
        progress_callback=lambda index, total: progress.update_range(28, 40, index, total, "Building LVZ model resources"),
    )
    LVZ.dbg(f"LVZ models built: {len(built_by_res)}")
    stamp_source_paths(built_by_res, lvz_path, img_name)

    built_by_cont: Dict[int, bpy.types.Object] = {}
    if img is not None:
        LVZ.dbg("[img-mdl] structured IMG resource-table models are parsed below")

    overlay_by_sector_res: Dict[Tuple[int, int], bpy.types.Object] = {}
    row_overlay_by_res: Dict[Tuple[int, int], bpy.types.Object] = {}
    nested_overlay_by_res: Dict[Tuple[int, int], bpy.types.Object] = {}
    ipl_overlay_by_sector_res: Dict[Tuple[int, int], bpy.types.Object] = {}
    ipl_row_overlay_by_res: Dict[Tuple[int, int], bpy.types.Object] = {}
    ipl_nested_overlay_by_res: Dict[Tuple[int, int], bpy.types.Object] = {}
    area_direct_objects: List[bpy.types.Object] = []
    official_area_resource_count = 0
    ipl_area_direct_objects: List[bpy.types.Object] = []
    ambiguous_global_res_ids = set()
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
            # Slave WRLD resource rows are 8 bytes: resource ID + resource offset.
            # Twelve-byte interpretations belong to unrelated data and can attach
            # the wrong geometry to a real placement ID.
            include_alt_12_layouts=False,
            progress_callback=lambda index, total: progress.update_range(41, 52, index, total, "Building exact IMG resource models"),
        )
        log_overlay_resource_stats(img, "sector")
        LVZ.dbg(f"IMG models built for static map blocks: {len(overlay_by_sector_res)}")

        missing_after_primary = find_details_missing_primary_resources(built_by_res, details, overlay_by_sector_res)
        needed_deep_row_res_keys = {
            (int(detail[19]), int(detail[0]))
            for detail in missing_after_primary
            if len(detail) > 19 and int(detail[19]) >= 0
        }
        needed_deep_res_ids = {int(detail[0]) for detail in missing_after_primary}
        # detail[4] is ROWLINK only. Old row-link/IPL fallback sets stay empty.
        needed_ipl_sector_keys = set()
        needed_ipl_row_res_keys = set()
        needed_ipl_res_ids = set()

        LVZ.dbg(
            f"[model-lookup] after LVZ and same-sector IMG: "
            f"details={len(missing_after_primary)} row/res={len(needed_deep_row_res_keys)} res={len(needed_deep_res_ids)}"
        )

        # Official VCS Area resources are not Sector overlays.  The master LVZ
        # AreaInfo[] rows point to AERA chunks whose entries are
        #   s16 RES, s16 secondaryId, u32 chunk-relative payload pointer.
        # Parse this authoritative path before any broad/global recovery.
        progress.update(60, "Building exact AERA resource models")
        LVZ.dbg("[progress] building exact models from master AreaInfo/AERA resources")
        if LVZ.DEBUG is not None:
            LVZ.DEBUG.flush()
        # Build authoritative AERA payloads for every visible placement RES, not
        # only rows that appear absent in the early LVZ/same-sector existence
        # check.  A same-RES placeholder or incomplete WRLD slice can exist and
        # still be unusable for the row; filtering AERA by mere object existence
        # was why exact resources such as Beach1887 remained missing even though
        # their real payload was present in the IMG AERA table.
        visible_placement_res_ids = {
            int(detail[0]) for detail in details
            if detail and int(detail[0]) >= 0
        }
        area_direct_objects = build_official_area_resource_mdl_objects(
            stem,
            img_bytes,
            lvz,
            img,
            lvz_path,
            img_name,
            needed_res_ids=visible_placement_res_ids,
            progress_callback=lambda index, total: progress.update_range(60, 62, index, total, "Building exact AERA resource models"),
        )
        official_area_resource_count = len(area_direct_objects)
        _aera_watch = build_resource_object_candidate_map(area_direct_objects)
        for _watch_res in (1725, 1881, 1887, 1989, 2184, 3528):
            _watch_candidates = _aera_watch.get(int(_watch_res), [])
            if _watch_candidates:
                LVZ.dbg(
                    f"[aera-placement] exact RES={int(_watch_res)} candidates={len(_watch_candidates)} "
                    f"objects={','.join(str(getattr(obj, 'name', '')) for obj in _watch_candidates[:4])}"
                )
            else:
                LVZ.dbg(f"[aera-placement] exact RES={int(_watch_res)} has no parsed AERA geometry candidate")

        if needed_deep_res_ids and ENABLE_GLOBAL_EXACT_RES_FALLBACK_MDLS:
            # Some VCS sectors do not carry the model payload in the same sector container
            # even though the placement row's normal resource id is correct. Build one
            # best global exact-res candidate per missing resource id before falling back
            # to the more dangerous legacy ROWLINK-as-model interpretation.
            progress.update(62, "Building global exact-resource models")
            LVZ.dbg("[progress] building exact IMG resource models from other map blocks")
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
                # Use the documented 8-byte Slave WRLD resource table only.
                include_alt_12_layouts=False,
                wanted_res_ids=needed_deep_res_ids,
                collapse_by_res_id=True,
                progress_callback=lambda index, total: progress.update_range(62, 67, index, total, "Building global exact-resource models"),
            )
            ambiguous_global_res_ids = set(getattr(img, "last_ambiguous_overlay_res_ids", set()) or set())
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
            LVZ.dbg(f"[exact-models] other map blocks added: {merged_global_exact}")
            log_overlay_resource_stats(img, "global-exact-res")
        elif needed_deep_res_ids:
            LVZ.dbg(f"[cleanup] global exact-res IMG recovery had no build request; unresolved exact RES ids={len(needed_deep_res_ids)}")

        if needed_ipl_res_ids and ENABLE_INTERNAL_IPL_MODEL_FALLBACK_MDLS:
            # Legacy disabled path: build ROWLINK-keyed resources globally, not only in the same sector.
            # beach rows like RES=1828 / ROWLINK=1222..1241 reference model IDs that are
            # stored in other sector resource tables, so same-sector filtering leaves
            # the building half-missing and forces bad AREA/nested fallbacks.
            LVZ.dbg("[progress] building legacy ROWLINK fallback MDLs")
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
                include_alt_12_layouts=False,
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
            LVZ.dbg("[progress] building exact models from child resource records")
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
                include_alt_12_layouts=False,
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
                include_alt_12_layouts=False,
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
            LVZ.dbg("[progress] building exact models from shared resource records")
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
                include_alt_12_layouts=False,
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
                include_alt_12_layouts=False,
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
        LVZ.dbg("[progress] building exact models from linked AREA records")
        if LVZ.DEBUG is not None:
            LVZ.DEBUG.flush()
        legacy_area_direct_objects = build_extra_area_direct_mdl_objects(
            stem,
            img_bytes,
            lvz,
            img,
            extra_container_records,
            lvz_path,
            img_name,
            needed_res_ids=needed_deep_res_ids,
            # Triggered/auxiliary WRLD containers still use Sector-style rows.
            # Keep these separate from the official AERA AreaResource parser.
            include_alt_12_layouts=False,
            wanted_res_ids=needed_deep_res_ids,
            progress_callback=lambda index, total: progress.update_range(75, 79, index, total, "Building linked auxiliary resource models"),
        )
        area_direct_objects.extend(legacy_area_direct_objects)
        log_overlay_resource_stats(img, "linked-auxiliary")
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
                include_alt_12_layouts=False,
                wanted_res_ids=needed_ipl_res_ids,
            )
            for obj in ipl_area_direct_objects:
                try:
                    obj["blds_kind"] = "IMG_IPL_AREA_DIRECT_MDL"
                    obj["blds_img_ipl_model_fallback"] = True
                except Exception:
                    pass
            log_overlay_resource_stats(img, "ipl-area")

        additional_exact_img_models = (
            len(nested_overlay_by_res)
            + len(row_overlay_by_res)
            + len(area_direct_objects)
        )
        LVZ.dbg(f"Additional exact IMG models built: {additional_exact_img_models}")

        # WRLD placement rows use the second u16 as the resource ID.  Resolve
        # that ID from exact tables first: same Slave WRLD, row-linked records,
        # Master WRLD, linked/AREA records, then another exact Slave table.
        exact_overlay_objects = []
        for (_candidate_sector, _candidate_res_id), candidate_obj in overlay_by_sector_res.items():
            if candidate_obj is None:
                continue
            try:
                if bool(candidate_obj.get("blds_img_continues_in_img", False)):
                    continue
            except Exception:
                pass
            exact_overlay_objects.append(candidate_obj)
        exact_global_candidates_by_res = build_resource_object_candidate_map(exact_overlay_objects)
        exact_area_candidates_by_res = build_resource_object_candidate_map(area_direct_objects)

        # Promote a fitting authoritative AERA payload into the concrete
        # placement sector/RES lookup before the unresolved scan and before the
        # Blender instance loop.  This makes placement deterministic: when the
        # master AERA table contains exact RES geometry that fits the row, the
        # row cannot later fall through to MISSING merely because another
        # generic lookup pool was empty or contained an incomplete placeholder.
        aera_promoted_rows = 0
        aera_promoted_res_ids = set()
        for _detail in details:
            try:
                _res_id = int(_detail[0])
                _sector_index = int(_detail[15]) if len(_detail) > 15 else -1
            except Exception:
                continue
            _aera_pool = [
                (_candidate, "official_aera_model", 0)
                for _candidate in exact_area_candidates_by_res.get(_res_id, [])
                if _candidate is not None
            ]
            _aera_obj, _aera_source, _aera_fit, _aera_count = choose_exact_resource_candidate(
                _aera_pool,
                _detail,
                max_fit_score=CONTINUES_IN_IMG_MAX_PLACEMENT_FIT_SCORE,
            )
            if _aera_obj is None:
                continue
            overlay_by_sector_res[(_sector_index, _res_id)] = _aera_obj
            try:
                _aera_obj["blds_aera_authoritative_placement"] = True
                _aera_obj["blds_aera_authoritative_fit"] = float(_aera_fit[0]) if _aera_fit is not None else -1.0
            except Exception:
                pass
            aera_promoted_rows += 1
            aera_promoted_res_ids.add(_res_id)
        LVZ.dbg(
            f"[aera-placement] promoted exact AERA payloads into placement lookup: "
            f"rows={aera_promoted_rows} resource_ids={len(aera_promoted_res_ids)}"
        )

        exact_variant_ids = {
            int(resource_id)
            for resource_id in set(exact_global_candidates_by_res) | set(exact_area_candidates_by_res)
            if len(exact_global_candidates_by_res.get(resource_id, []))
            + len(exact_area_candidates_by_res.get(resource_id, [])) > 1
        }
        if exact_variant_ids:
            LVZ.dbg(
                f"Resource IDs with multiple exact models will be matched to each placement row: "
                f"{len(exact_variant_ids)}"
            )

        unresolved_details = []
        suspicious_exact_slice_details = []
        exact_fit_rejected_before_raw = 0
        for detail in details:
            resource_id = int(detail[0])
            sector_index = int(detail[15]) if len(detail) > 15 else -1
            row_index = int(detail[19]) if len(detail) > 19 else -1
            candidates = []

            def add_exact(candidate, source, rank):
                if candidate is None:
                    return
                try:
                    if bool(candidate.get("blds_img_continues_in_img", False)):
                        return
                except Exception:
                    pass
                candidates.append((candidate, str(source), int(rank)))

            add_exact(overlay_by_sector_res.get((sector_index, resource_id)), "exact_sector_model", 0)
            if row_index >= 0:
                add_exact(nested_overlay_by_res.get((row_index, resource_id)), "exact_nested_row_model", 1)
                add_exact(row_overlay_by_res.get((row_index, resource_id)), "exact_row_model", 2)
            add_exact(built_by_res.get(resource_id), "lvz_model", 3)
            for candidate in exact_area_candidates_by_res.get(resource_id, []):
                add_exact(candidate, "area_model", 4)
            for candidate in exact_global_candidates_by_res.get(resource_id, []):
                add_exact(candidate, "global_sector_model", 5)

            chosen, _source, _fit, candidate_count = choose_exact_resource_candidate(
                candidates,
                detail,
                max_fit_score=CONTINUES_IN_IMG_MAX_PLACEMENT_FIT_SCORE,
            )
            if chosen is None:
                unresolved_details.append(detail)
                if candidate_count:
                    exact_fit_rejected_before_raw += 1
            elif exact_candidate_needs_raw_variant(chosen, detail):
                suspicious_exact_slice_details.append(detail)

        def raw_detail_key(detail):
            try:
                return (
                    int(detail[0]), int(detail[4]), int(detail[15]), int(detail[19]),
                    str(detail[14]), int(detail[1]), int(detail[2]),
                )
            except Exception:
                return id(detail)

        raw_scan_details = []
        raw_seen = set()
        raw_input_details = list(unresolved_details) + list(suspicious_exact_slice_details)
        for detail in raw_input_details:
            key = raw_detail_key(detail)
            if key in raw_seen:
                continue
            raw_seen.add(key)
            raw_scan_details.append(detail)

        unresolved_res_ids = {int(detail[0]) for detail in unresolved_details if int(detail[0]) >= 0}
        suspicious_res_ids = {int(detail[0]) for detail in suspicious_exact_slice_details if int(detail[0]) >= 0}
        LVZ.dbg(
            f"[exact-resolution] unresolved placements={len(unresolved_details)} "
            f"resource_ids={len(unresolved_res_ids)} suspicious_exact_slices={len(suspicious_exact_slice_details)} "
            f"suspicious_resource_ids={len(suspicious_res_ids)}"
        )
        if exact_fit_rejected_before_raw:
            LVZ.dbg(
                f"Exact table models that did not match their placement bounds and will be checked in raw IMG data: "
                f"{exact_fit_rejected_before_raw}"
            )
        if suspicious_exact_slice_details:
            LVZ.dbg(
                f"Exact WRLD submodel slices that are too small/large for their own row bounds and will be "
                f"compared with raw exact-RES IMG variants: {len(suspicious_exact_slice_details)}"
            )

        # Raw IMG scanning is limited to unresolved rows and same-RES WRLD
        # aggregate slices whose transformed bounds do not cover their row.
        raw_scan_res_ids = {int(detail[0]) for detail in raw_scan_details if int(detail[0]) >= 0}
        if raw_scan_res_ids and ENABLE_EMPTY_RESOURCE_CONTINUES_IN_IMG:
            progress.update(79, "Checking remaining IMG model data")
            LVZ.dbg(f"[progress] checking raw IMG model data for {len(raw_scan_res_ids)} exact resource IDs")
            if LVZ.DEBUG is not None:
                LVZ.DEBUG.flush()
            continued_img_overlay_by_sector_res = build_empty_resource_continues_in_img_mdl_objects(
                stem,
                img_bytes,
                lvz,
                img,
                raw_scan_res_ids,
                lvz_path,
                img_name,
                placement_details=raw_scan_details,
                progress_callback=lambda index, total: progress.update_range(79, 80, index, total, "Checking remaining IMG model data"),
            )
            merged_continued_img = 0
            for key, obj in continued_img_overlay_by_sector_res.items():
                if key in overlay_by_sector_res:
                    continue
                overlay_by_sector_res[key] = obj
                merged_continued_img += 1
            LVZ.dbg(f"[raw-img-models] recovered={merged_continued_img} requested={len(raw_scan_res_ids)}")

    linked_instances = 0
    removed_unplaced = 0
    sidecar_ipl_path = None  # V18: do not use external beach.ipl sidecars; fix internal master/slave WRLD placement only.
    placement_report_rows = {}
    for placement_index, placement_detail in enumerate(details or []):
        placement_key = blds_placement_report_key(placement_detail)
        if placement_key is not None:
            placement_report_rows[placement_key] = blds_make_placement_report_row(placement_detail, index=placement_index)
    globals()["_CURRENT_PLACEMENT_REPORT_ROWS"] = placement_report_rows

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
            planned_model_keys = {
                (int(detail[15]) if len(detail) > 15 else -1, int(detail[0]))
                for detail in details
            }
            planned_model_total = len(planned_model_keys)
            planned_cached_total = max(0, len(details) - planned_model_total)
            progress.configure_map_plan(len(details), planned_model_total, planned_cached_total)
            progress.update(80, "Placing IMG instances")
            LVZ.dbg(
                "Leeds Stories map import plan: {} placements, {} exact sector/RES models, {} cached placements".format(
                    len(details), planned_model_total, planned_cached_total
                )
            )
            LVZ.dbg("[progress] applying IMG placement transforms / linked duplicates")
            if LVZ.DEBUG is not None:
                LVZ.DEBUG.flush()

            def update_placement_progress(index, total, placed=0, models=0, cached=0):
                progress.update_map(
                    index,
                    total,
                    placed,
                    models,
                    cached,
                    "Placing IMG instances",
                )

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
                ide_res_to_model_id,
                ide_res_to_name,
                placement_identity_by_key,
                progress_callback=update_placement_progress,
                model_2dfx_by_game_model_id=model_2dfx_by_game_model_id,
                model_2dfx_summary=two_dfx_summary,
                model_2dfx_collection=model_2dfx_collection,
                create_game_dtz_2dfx_helpers=False,
            )
            if create_game_dtz_2dfx_helpers and str(two_dfx_summary.get("status", "")) == "ok":
                progress.update(98, "Placing GAME.DTZ 2DFX")
                blds_import_game_entity_2dfx_helpers(
                    model_2dfx_collection,
                    stem,
                    model_2dfx_by_game_model_id,
                    two_dfx_summary,
                    sector_records,
                    globals().get("_CURRENT_PLACED_OBJECT_RECORDS", []),
                )
            removed_unplaced += purge_stale_raw_parser_bases(stem, reason="post-apply")
            LVZ.dbg(f"[apply] IMG placement rows applied: {applied}")
            LVZ.dbg(f"[apply] linked duplicate placement objects created: {linked_instances}")
        except Exception as exc:
            LVZ.dbg(f"[apply] IMG placement transform pass failed: {exc}")
    elif apply_img_transforms:
        LVZ.dbg("[apply] no IMG transforms available to apply")

    try:
        blds_write_placement_res_report(
            lvz_path, details, placement_report_rows,
            model_2dfx_by_id=model_2dfx_by_game_model_id,
            model_2dfx_summary=two_dfx_summary,
            placement_identity_by_key=placement_identity_by_key,
            identity_summary=identity_summary,
        )
    except Exception as exc:
        LVZ.dbg(f"[placement-report] failed: {exc}")

    progress.update(99, "Finalizing imported objects", force=True)
    elapsed = time.time() - t0
    placed_records = list(globals().get("_CURRENT_PLACED_OBJECT_RECORDS", []) or [])
    resolved_sector_resources = set()
    for placed_record in placed_records:
        try:
            resolved_sector_resources.add((
                int(placed_record.get("sector_index", -1)),
                int(placed_record.get("res_id", -1)),
            ))
        except Exception:
            continue
    parsed_sector_count = len(sector_records)
    parsed_placement_count = len(details)
    parsed_real_mesh_count = len(resolved_sector_resources)
    LVZ.dbg(f"Parsed sectors: {parsed_sector_count}")
    LVZ.dbg(f"Parsed visible placements: {parsed_placement_count}")
    LVZ.dbg(f"Parsed real mesh resources: {parsed_real_mesh_count}")
    LVZ.dbg("Identity fields remain separate: RES=streamed geometry, ROWLINK=placement link, GAME_MODEL=CBaseModelInfo/AERA secondary identity.")
    if import_root_collection is not None:
        try:
            import_root_collection["blds_archive_mode"] = "RETAIL_LVZ_IMG_NO_DIR"
            import_root_collection["blds_platform"] = str(platform)
            import_root_collection["blds_parsed_sectors"] = int(parsed_sector_count)
            import_root_collection["blds_parsed_visible_placements"] = int(parsed_placement_count)
            import_root_collection["blds_parsed_real_mesh_resources"] = int(parsed_real_mesh_count)
            import_root_collection["blds_source_lvz_path"] = str(lvz_path)
            import_root_collection["blds_source_img_path"] = str(img_name or "")
            import_root_collection["blds_identity_contract"] = "RES_STREAMED_GEOMETRY;ROWLINK_PLACEMENT_LINK;GAME_MODEL_AERA_SECONDARY"
        except Exception as exc:
            LVZ.dbg(f"[collections] import summary metadata failed: {exc}")
    LVZ.dbg(f"[summary] LVZ-table MDL resource objects parsed: {len(built_by_res)}")
    LVZ.dbg(f"[summary] IMG sector overlay MDL objects parsed: {len(overlay_by_sector_res)}")
    LVZ.dbg(f"[summary] IMG legacy ROWLINK fallback sector MDLs parsed: {len(ipl_overlay_by_sector_res)}")
    LVZ.dbg(f"[summary] IMG child-record exact models parsed: {len(nested_overlay_by_res)}")
    LVZ.dbg(f"[summary] IMG legacy ROWLINK nested fallback MDLs parsed: {len(ipl_nested_overlay_by_res)}")
    LVZ.dbg(f"[summary] IMG shared-record exact models parsed: {len(row_overlay_by_res)}")
    LVZ.dbg(f"[summary] IMG legacy ROWLINK row fallback MDLs parsed: {len(ipl_row_overlay_by_res)}")
    LVZ.dbg(f"[summary] IMG master AERA exact models parsed: {official_area_resource_count}")
    LVZ.dbg(f"[summary] IMG all linked/AREA exact models parsed: {len(area_direct_objects)}")
    LVZ.dbg(f"[summary] IMG legacy ROWLINK AREA fallback MDLs parsed: {len(ipl_area_direct_objects)}")
    LVZ.dbg(f"[summary] deleted unplaced resource objects: {removed_unplaced}")
    LVZ.dbg(f"[summary] linked IMG placement duplicates: {linked_instances}")
    LVZ.dbg(f"[summary] IMG-container MDL objects: {len(built_by_cont)}")
    LVZ.dbg(
        f"[summary] Leeds entity 2DFX source={two_dfx_summary.get('source_path', '') or 'none'} "
        f"model_infos={int(two_dfx_summary.get('ide_count', 0))} "
        f"global_effect_rows={int(two_dfx_summary.get('effect_count', 0))} "
        f"global_effect_entities={int(two_dfx_summary.get('entity_instances_with_effects', 0))} "
        f"global_entity_helpers={int(two_dfx_summary.get('entity_effect_rows', 0))} "
        f"selected_entities={int(two_dfx_summary.get('entity_instances_selected', 0))} "
        f"attached_entities={int(two_dfx_summary.get('entity_instances_attached', 0))} "
        f"independent_entities={int(two_dfx_summary.get('entity_instances_unattached', 0))} "
        f"placed_helpers={int(two_dfx_summary.get('effects_imported', 0))} "
        f"active_sector_cells={int(two_dfx_summary.get('active_sector_cells', 0))} "
        f"mapping=GAME_DTZ_CENTITY_MODEL_INDEX "
        f"transform=CENTITY_NATIVE_WORLD_MATRIX "
        f"helpers_enabled={bool(create_game_dtz_2dfx_helpers)}"
    )
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
    operator.report({'INFO'}, f"Imported LVZ+IMG: {len(details)} map placements, {linked_instances} linked copies, {len(built_by_res)} LVZ models, {len(overlay_by_sector_res)} IMG models, {int(two_dfx_summary.get('effects_imported', 0))} model 2DFX helpers, {removed_unplaced} unused model bases cleaned up ({platform}).")
    progress.finish(succeeded=True, message="Import complete")
    return {'FINISHED'}
