# BLeeds - Scripts for working with R* Leeds (GTA Stories, Chinatown Wars, Manhunt 2, etc) formats in Blender
# Author: spicybung
# Years: 2025 - 

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

import time
from pathlib import Path
from typing import Dict
import zipfile

import bpy
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, BoolProperty
from mathutils import Matrix

from ..leedsLib import lvz_img as LVZ


class IMPORT_SCENE_OT_stories_lvz(Operator, ImportHelper):
    """Import a Rockstar Leeds LevelZlib & IMG Archive"""
    bl_idname = "import_scene.leeds_lvz_img"
    bl_label = "Import LVZ + IMG"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ".lvz"

    use_swizzle: BoolProperty(
        name="PS2 swizzle",
        default=True
    )
    csv_dedup_res_ids: BoolProperty(
        name="CSV unique + log detailed blocks",
        default=True
    )
    apply_img_transforms: BoolProperty(
        name="Apply IMG transforms to MDL objects",
        default=True
    )
    debug_print: BoolProperty(
        name="Debug print",
        default=True
    )
    write_debug_log: BoolProperty(
        name="Write debug log next to LVZ",
        default=True
    )

    filter_glob: StringProperty(
        default="*.lvz;*.LVZ",
        options={'HIDDEN'},
        maxlen=255,
    )

    def execute(self, context):
        lvz_path = self.filepath
        if not lvz_path:
            self.report({'ERROR'}, "No LVZ selected.")
            return {'CANCELLED'}

        stem = Path(lvz_path).stem
        log_path = (
            str(Path(lvz_path).with_suffix("")) + "_blds_import.log"
            if self.write_debug_log else None
        )

        LVZ.DEBUG = LVZ.DebugOut(self.debug_print, self.write_debug_log, log_path)

        t0 = time.time()
        lvz_bytes_in = Path(lvz_path).read_bytes()
        decomp, was_cmp = LVZ.safe_decompress(lvz_bytes_in)

        LVZ.dbg("===== LVZ Walk + IMG Match/Apply =====")
        LVZ.dbg(f"LVZ: {lvz_path}")
        LVZ.dbg(
            f"[io] LVZ bytes in: {len(lvz_bytes_in)}  decomp: {len(decomp)} "
            f"({ 'compressed' if was_cmp else 'raw' })"
        )
        LVZ.dbg("")

        lvz = LVZ.read_lvz(
            decomp_bytes=decomp,
            stem=stem,
            use_swizzle=self.use_swizzle,
            debug_print=self.debug_print
        )
        try:
            mast = lvz.parse_master_header()
            groups_hdr, res_count, _ = lvz.parse_slave_groups_and_rescount()
        except Exception as e:
            self.report({'ERROR'}, f"Failed to parse LVZ: {e}")
            return {'CANCELLED'}

        LVZ.dbg("— Slave Group Table —")
        LVZ.dbg(f"  groups: {len(groups_hdr)}")
        for g in groups_hdr:
            LVZ.dbg(
                f"  [sg {g.index:03d}] LVZ+0x{g.addr:08X} tag='{g.tag}' "
                f"size={g.total} gcnt={g.gcnt} contIMG=0x{g.cont:08X} — {g.note}"
            )
        LVZ.dbg(f"  resource count: {res_count}")
        LVZ.dbg("")

        rows = lvz.walk_master_resource_table(mast.res_table_addr, res_count)
        LVZ.dbg("— Master Resource Table (first 300) —")
        for r in rows[:min(len(rows), 300)]:
            a16, b16 = r["peek_u16"]
            a32, b32 = r["peek_u32"]
            extra = []
            if r["kind"] == "UNK_FAC0" and "unk_fac0" in r:
                extra.append(f"unk_fac0={r['unk_fac0']}")
            if r["kind"] == "EMPTY" and "empty_reason" in r:
                extra.append(f"reason={r['empty_reason']}")
            if r["kind"] == "TEX_REF":
                extra.append(f"ref_addr=0x{r['ref_addr']:08X}")
                extra.append(f"RES(index)={r['index']}")
                if "embedded_res_id" in r and r["embedded_res_id"] is not None:
                    extra.append(f"embedded=0x{r['embedded_res_id']:08X}")
            LVZ.dbg(
                f"[res {r['index']:5d}] table@0x{r['table_off']:08X} "
                f"→ res@0x{r['res_addr']:08X} "
                f"kind={r['kind']} "
                f"u16,u16=({a16},{b16}) "
                f"u32,u32=("
                f"0x{(a32 if a32 is not None else 0):08X},"
                f"0x{(b32 if b32 is not None else 0):08X}) "
                f"{' '.join(extra)}"
            )
        LVZ.dbg("")

        img_bytes = None
        img_name = None
        try:
            lvz_p = Path(lvz_path)
            cands = [
                lvz_p.with_suffix(".IMG"),
                lvz_p.with_suffix(".img"),
                lvz_p.with_suffix(".img.zip"),
            ]
            for cand in cands:
                if cand.exists():
                    if cand.suffix.lower() == ".zip":
                        with zipfile.ZipFile(cand, "r") as zf:
                            nm = None
                            for nm0 in zf.namelist():
                                if nm0.lower().endswith(".img"):
                                    nm = nm0
                                    break
                            if nm is None and zf.namelist():
                                nm = zf.namelist()[0]
                            img_bytes = zf.read(nm)
                            img_name = str(cand.name)
                    else:
                        img_bytes = cand.read_bytes()
                        img_name = cand.name
                    break
            if img_bytes:
                LVZ.dbg(
                    f"— IMG Read — source: {img_name} bytes={len(img_bytes)}"
                )
            else:
                LVZ.dbg(
                    "[img] IMG not found next to LVZ; IMG-based features will be skipped"
                )
        except Exception as eimg:
            LVZ.dbg(f"[img] failed to read IMG: {eimg}")

        lvz.decode_textures(rows)

        transforms_by_res: Dict[int, Matrix] = {}
        if img_bytes:
            img = LVZ.read_img(img_bytes=img_bytes, lvz_bytes=decomp)
            conts = img.find_conts()
            LVZ.dbg(
                f"[img] DLRW prefaces in LVZ → conts: {len(conts)} "
                f"(includes master=0)"
            )
            all_rows = img.enumerate_all_rows(conts)
            details = img.enumerate_details(conts)
            transforms_by_res = img.build_transforms_map_and_log(
                details,
                enable_unique_log=self.csv_dedup_res_ids
            )
            LVZ.dbg(f"[img] total IMG rows walked: {len(all_rows)}")
            LVZ.dbg("— ALL RESOURCE IDs (IMG walk order) —")
            for i, (cont, rel_off, ipl_raw, ipl_id, res_id) in enumerate(all_rows):
                LVZ.dbg(f"{i:04d}: {res_id}")

            if self.csv_dedup_res_ids:
                seen = set()
                unique_rows = []
                for row in all_rows:
                    rid = row[4]
                    if rid not in seen:
                        seen.add(rid)
                        unique_rows.append(row)
            else:
                unique_rows = []

            img.write_csvs(
                lvz_path,
                all_rows,
                unique_rows,
                enable_unique=self.csv_dedup_res_ids,
            )
        else:
            LVZ.dbg("[img] IMG rows not enumerated because IMG is missing")

        built_by_res = lvz.build_mdl_objects(rows)

        if self.apply_img_transforms and transforms_by_res:
            applied = 0
            for res_id, M in transforms_by_res.items():
                obj = built_by_res.get(res_id)
                if obj is None:
                    continue
                try:
                    obj.matrix_world = M
                    applied += 1
                    LVZ.dbg(
                        f"[apply] RES={res_id} → object '{obj.name}' matrix_world set."
                    )
                except Exception as e:
                    LVZ.dbg(
                        f"[apply] RES={res_id} failed for object '{obj.name}': {e}"
                    )
            LVZ.dbg(f"[apply] transforms applied: {applied}")

        t1 = time.time()
        LVZ.dbg(f"[total] finished in {t1 - t0:.3f} seconds")

        if LVZ.DEBUG is not None:
            LVZ.DEBUG.flush()

        return {'FINISHED'}
