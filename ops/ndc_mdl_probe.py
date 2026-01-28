# BLeeds - R* Leeds texture reader for CHK/XTX/TEX
# Author: spicybung
# Years: 2025 -
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import struct
import sys
from pathlib import Path


def read_u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def main(path: Path) -> None:
    data = path.read_bytes()
    print(f"File: {path} ({len(data)} bytes)")

    sig = data[:4]
    shrink, file_len, local_num, global_num, num_entries, ptr2, alloc = struct.unpack_from(
        "<6I", data, 4
    )
    ptr_after = read_u32(data, 0x20)
    print(
        f"Header: sig={sig!r} shrink=0x{shrink:X} file_len=0x{file_len:X} "
        f"local=0x{local_num:X} global=0x{global_num:X} num_entries=0x{num_entries:X} "
        f"ptr2=0x{ptr2:X} alloc=0x{alloc:X} ptr_after=0x{ptr_after:X}"
    )

    atomic_off = ptr_after
    atomic = struct.unpack_from("<IIIIIIIIIIIIIIII", data, atomic_off)
    labels = [
        "vtable",
        "frame_ptr",
        "prev1",
        "prev2",
        "AAAA",
        "geom_ptr",
        "reserved",
        "clump_ptr",
        "link_ptr",
        "render_cb",
        "model_info_id",
        "vis_id_flag",
        "hierarchy_ptr",
        "material_ptr",
        "reserved2",
        "tail",
    ]
    print(f"Atomic@0x{atomic_off:X}:")
    for name, val in zip(labels, atomic):
        print(f"  {name:13} = 0x{val:08X}")

    geom_ptr = atomic[5]
    geom_base = geom_ptr
    unk0, unk1, unk2, mat_list_ptr, mat_count, unk_addr, res0, res1 = struct.unpack_from(
        "<IIIIIIII", data, geom_base
    )
    print(
        f"Geometry@0x{geom_base:X}: unk0={unk0} unk1={unk1} unk2={unk2} "
        f"mat_list_ptr=0x{mat_list_ptr:X} mat_count={mat_count} "
        f"unk_addr=0x{unk_addr:X} res0=0x{res0:X} res1=0x{res1:X}"
    )

    scales_off = geom_base + 20 + 13 * 4
    xs, ys, zs, tx, ty, tz = struct.unpack_from("<ffffff", data, scales_off)
    print(
        f"Scales@0x{scales_off:X}: xScale={xs} yScale={ys} zScale={zs} "
        f"tx={tx} ty={ty} tz={tz}"
    )

    mat_ptr = read_u32(data, mat_list_ptr)
    tex_ptr, rgba, unk, spec_ptr = struct.unpack_from("<IIII", data, mat_ptr)
    print(
        f"Material@0x{mat_ptr:X}: tex_ptr=0x{tex_ptr:X} rgba=0x{rgba:08X} "
        f"unk=0x{unk:X} spec_ptr=0x{spec_ptr:X}"
    )

    vif_seek = data.find(b"\x00\x80\x01\x6C")  
    print(f"First VIF marker at 0x{vif_seek:X}" if vif_seek >= 0 else "No VIF marker found")

    ptr_table = local_num
    if ptr_table < len(data):
        count = read_u32(data, ptr_table)
        ptrs = [read_u32(data, ptr_table + 4 + 4 * i) for i in range(min(count, 16))]
        print(f"Pointer table@0x{ptr_table:X}: count={count} first16={ptrs}")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("!LCS/ndc_moneypile.mdl")
    main(target)
