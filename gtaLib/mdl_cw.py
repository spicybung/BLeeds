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

import bpy
import os
import io
import struct

from typing import List, Tuple, Dict

from bpy.props import BoolProperty, StringProperty

#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
#   This script is for Chinatown Wars .MDL/.WBLs - file formats for models/blocks   #
#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   # 
# - Script resources:
# • https://gtamods.com/wiki/Leeds_Engine (some assets point to CW being made in Unity? ports maybe?)
# • https://gtamods.com/wiki/MDL (TODO: update stub to include Chinatown Wars documentation)
# • https://web.archive.org/web/20221108130633/http://gtamodding.ru/wiki/GAME.PAK_(Chinatown_Wars)#.D0.9C.D0.BE.D0.B4.D0.B5.D0.BB.D0.B8 (*Russian*)
# • https://web.archive.org/web/20221108130633/http://gtamodding.ru/wiki/GAME.PAK_(Chinatown_Wars)?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (*English*)
# - Mod resources/cool stuff:
# • https://gtaforums.com/topic/781150-relctw-chinatown-wars-mobile-resource-explorer/  (*analyzes game.pak for mobile & partial support for psp*)
# • https://web.archive.org/web/20221005045615/https://github.com/DK22Pac/ctw-gxt-tools (*texture editor - in case the repo goes down*)


#######################################################
class read_chinatown:

    DEBUG_MODE: bool = True

    #######################################################
    @staticmethod
    def get_debug_logfile(path: str) -> str:
        b = os.path.basename(path)
        s, _ = os.path.splitext(b)
        return os.path.join(os.path.dirname(path), f"{s}_debuglog.txt")
    #######################################################
    @classmethod
    def dprint(cls, s: str, logf=None, do_print: bool = True):
        if cls.DEBUG_MODE and do_print:
            print(s)
            if logf:
                try:
                    logf.write(s + "\n"); logf.flush()
                except Exception:
                    pass
    #######################################################
    @staticmethod
    def r_u8(d, o):  
        return struct.unpack_from("<B", d, o)[0]
    #######################################################
    @staticmethod
    def r_i8(d, o):  
        return struct.unpack_from("<b", d, o)[0]
    #######################################################
    @staticmethod
    def r_u16(d, o): 
        return struct.unpack_from("<H", d, o)[0]
    #######################################################
    @staticmethod
    def r_i16(d, o): 
        return struct.unpack_from("<h", d, o)[0]
    #######################################################
    @staticmethod
    def r_u32(d, o): 
        return struct.unpack_from("<I", d, o)[0]
    #######################################################
    @staticmethod
    def r_i32(d, o): 
        return struct.unpack_from("<i", d, o)[0]
    #######################################################
    @staticmethod
    def r_f32(d, o): 
        return struct.unpack_from("<f", d, o)[0]
    #######################################################
    @classmethod
    def read_vec3_int4096(cls, d, off):
        return (cls.r_i32(d, off)/4096.0, cls.r_i32(d, off+4)/4096.0, cls.r_i32(d, off+8)/4096.0)
    #######################################################
    @classmethod
    def read_leeds_cw_transform(cls, d, off, logf=None):
        RightX = cls.r_i16(d, off)/4096.0
        RightY = cls.r_i16(d, off+2)/4096.0
        RightZ = cls.r_i16(d, off+4)/4096.0
        TopX   = cls.r_i16(d, off+6)/4096.0
        TopY   = cls.r_i16(d, off+8)/4096.0
        TopZ   = cls.r_i16(d, off+10)/4096.0
        AtX    = cls.r_i16(d, off+12)/4096.0
        AtY    = cls.r_i16(d, off+14)/4096.0
        AtZ    = cls.r_i16(d, off+16)/4096.0
        Padding= cls.r_i16(d, off+18)
        PosnX  = cls.r_i32(d, off+20)/4096.0
        PosnY  = cls.r_i32(d, off+24)/4096.0
        PosnZ  = cls.r_i32(d, off+28)/4096.0
        cls.dprint(f"    -Transform", logf)
        cls.dprint(f"      PosnX {PosnX:.6f} PosnY {PosnY:.6f} PosnZ {PosnZ:.6f}", logf)
        return {"Right": (RightX,RightY,RightZ), "Top": (TopX,TopY,TopZ), "At": (AtX,AtY,AtZ), "Pos": (PosnX,PosnY,PosnZ), "Padding": Padding}

    #######################################################
    class MaterialBank:

        def __init__(self, tex_dir: str, logf=None):
            self.dir = tex_dir
            self.logf = logf
            self.slots: List[Tuple[str, bpy.types.Material]] = []
            self.index_by_texid: Dict[int, int] = {}

        #######################################################
        def get_slot(self, tex_id: int) -> int:
            RC = read_chinatown
            if tex_id in self.index_by_texid:
                return self.index_by_texid[tex_id]
            name = f"texture{tex_id}"
            if name in bpy.data.materials:
                mat = bpy.data.materials[name]
                mat.use_nodes = True
                mat.node_tree.nodes.clear()
                RC.dprint(f"    Reuse '{name}'", self.logf)
            else:
                mat = bpy.data.materials.new(name=name)
                mat.use_nodes = True
            tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
            bsdf = mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
            out = mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
            mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
            mat.node_tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
            img_path = os.path.join(self.dir, f"{name}.png")
            if os.path.exists(img_path):
                try:
                    img = bpy.data.images.load(img_path, check_existing=True)
                    tex.image = img
                    tex.interpolation = 'Smart'
                    RC.dprint(f"      Loaded {img_path}", self.logf)
                except Exception as e:
                    RC.dprint(f"      Img fail {img_path}: {e}", self.logf)
            else:
                RC.dprint(f"      Missing {img_path}", self.logf)
            mat["CW_TexID"] = tex_id
            idx = len(self.slots)
            self.slots.append((name, mat))
            self.index_by_texid[tex_id] = idx
            return idx
        #######################################################
        def append_all_to_mesh(self, mesh: bpy.types.Mesh):
            for _, m in self.slots:
                mesh.materials.append(m)

    #######################################################
    @classmethod
    def collect_mesh_offsets_and_lights(cls, b: bytes, logf=None):
        offs = set()
        lights = []
        s_ofs = 0x28
        for s in range(4):
            if s_ofs + 12 > len(b): break
            sec = b[s_ofs:s_ofs+12]
            nInst = cls.r_i16(sec,2); nSh = cls.r_i16(sec,4); nLvl = cls.r_i16(sec,6); nLt = cls.r_i16(sec,8); nTex = cls.r_i16(sec,10)
            cls.dprint(f"\n==== SECTOR {s} @0x{s_ofs:06X} ====", logf)
            cls.dprint(f"  Inst:{nInst} Sh:{nSh} Lvl:{nLvl} Lt:{nLt} Tex:{nTex}", logf)
            p = s_ofs + 12
            p += 16 * nLvl
            base = p
            for i in range(nInst):
                e = base + 16*i
                if e + 16 > len(b): break
                mo = cls.r_u32(b, e+8)
                if mo: offs.add(mo)
            p = base + 16*nInst
            p += 20 * nSh
            lb = p
            for i in range(nLt):
                lo = lb + 20*i
                if lo + 20 > len(b): break
                X = cls.r_u32(b, lo+0)/4096.0
                Y = cls.r_u32(b, lo+4)/4096.0
                Z = cls.r_u32(b, lo+8)/4096.0
                Size = cls.r_u16(b, lo+12)/4096.0
                Id   = cls.r_u8(b, lo+14)
                R    = cls.r_u8(b, lo+16)
                G    = cls.r_u8(b, lo+17)
                C    = cls.r_u8(b, lo+18)
                lights.append((s, i, (X,Y,Z), Size, Id, (R,G,C)))
            p = lb + 20*nLt
            p += 2 * nTex
            s_ofs = p
        return offs, lights
    #######################################################
    @classmethod
    def create_lights(cls, lights, coll: bpy.types.Collection):
        for si, i, (X,Y,Z), Size, Id, (R,G,B) in lights:
            ldata = bpy.data.lights.new(name=f"CW_Light_{si}_{i}", type='POINT')
            obj = bpy.data.objects.new(name=f"CW_Light_{si}_{i}", object_data=ldata)
            coll.objects.link(obj)
            if obj.name in bpy.context.collection.objects:
                bpy.context.collection.objects.unlink(obj)
            obj.location = (X,Y,Z)
            ldata.color = (R/255.0, G/255.0, B/255.0)
            ldata.energy = max(1.0, Size*1000.0)
            ldata.shadow_soft_size = Size
            obj["CW_LightID"] = Id

    #######################################################
    @staticmethod
    def tri_strip_to_tris(n: int):
        if n < 3: return []
        f = []; flip = False
        for i in range(n-2):
            a,b,c = i,i+1,i+2
            f.append((a,c,b) if flip else (a,b,c))
            flip = not flip
        return f

    #######################################################
    @classmethod
    def register(cls): 
        pass
    #######################################################
    @classmethod
    def unregister(cls): 
        pass


#######################################################
class write_chinatown:
    dprint = read_chinatown.dprint
    get_debug_logfile = read_chinatown.get_debug_logfile
    DEBUG_MODE = read_chinatown.DEBUG_MODE

    #######################################################
    @staticmethod
    def w_u8(buf: io.BytesIO, v: int):  
        buf.write(struct.pack("<B", v & 0xFF))
    #######################################################
    @staticmethod
    def w_i8(buf: io.BytesIO, v: int):  
        buf.write(struct.pack("<b", v))
    @staticmethod
    def w_u16(buf: io.BytesIO, v: int): 
        buf.write(struct.pack("<H", v & 0xFFFF))
    #######################################################
    @staticmethod
    def w_i16(buf: io.BytesIO, v: int): 
        buf.write(struct.pack("<h", v))
    #######################################################
    @staticmethod
    def w_u32(buf: io.BytesIO, v: int): 
        buf.write(struct.pack("<I", v & 0xFFFFFFFF))
    #######################################################
    @staticmethod
    def w_i32(buf: io.BytesIO, v: int): 
        buf.write(struct.pack("<i", v))
    #######################################################
    @staticmethod
    def w_f32(buf: io.BytesIO, v: float): 
        buf.write(struct.pack("<f", float(v)))
    #######################################################
    @classmethod
    def write_leeds_cw_transform(cls, buf: io.BytesIO, t: Dict):
        i16 = lambda x: int(round(float(x)*4096.0))
        i32 = lambda x: int(round(float(x)*4096.0))
        RX,RY,RZ = t.get("Right",(1,0,0))
        TX,TY,TZ = t.get("Top",(0,1,0))
        AX,AY,AZ = t.get("At",(0,0,1))
        PX,PY,PZ = t.get("Pos",(0,0,0))
        Pad = int(t.get("Padding",0))
        cls.w_i16(buf, i16(RX)); cls.w_i16(buf, i16(RY)); cls.w_i16(buf, i16(RZ))
        cls.w_i16(buf, i16(TX)); cls.w_i16(buf, i16(TY)); cls.w_i16(buf, i16(TZ))
        cls.w_i16(buf, i16(AX)); cls.w_i16(buf, i16(AY)); cls.w_i16(buf, i16(AZ))
        cls.w_i16(buf, Pad)
        cls.w_i32(buf, i32(PX)); cls.w_i32(buf, i32(PY)); cls.w_i32(buf, i32(PZ))

    #######################################################
    @classmethod
    def write_file(cls, path: str, data: bytes):
        with open(path, "wb") as f:
            f.write(data)
    #######################################################
    @classmethod
    def write_mdl_bytes(
        cls,
        *,
        vertices_worldspace: List[Tuple[float,float,float]],
        uvs: List[Tuple[float,float]],
        parts: List[Dict],
        scaleFactor: float,
        translationFactor: float,
        base_transform_pos: Tuple[float,float,float] = (0.0,0.0,0.0),
        unknown_byte: int = 0,
        field8: int = 0,
        fieldC: int = 0
    ) -> bytes:
        if not vertices_worldspace:
            raise ValueError("no vertices")
        buf = io.BytesIO()
        minx = min(v[0] for v in vertices_worldspace); maxx = max(v[0] for v in vertices_worldspace)
        miny = min(v[1] for v in vertices_worldspace); maxy = max(v[1] for v in vertices_worldspace)
        minz = min(v[2] for v in vertices_worldspace); maxz = max(v[2] for v in vertices_worldspace)
        buf.write(b"MDL\x00")
        cls.w_i8(buf, int(unknown_byte))
        cls.w_i8(buf, int(len(parts)))
        cls.w_i16(buf, int(len(vertices_worldspace)))
        cls.w_u32(buf, int(field8))
        cls.w_u32(buf, int(fieldC))
        i32 = lambda x: int(round(float(x)*4096.0))
        for v in (minx,miny,minz,maxx,maxy,maxz): cls.w_i32(buf, i32(v))
        cls.w_f32(buf, float(translationFactor))
        cls.w_f32(buf, float(scaleFactor))
        PX,PY,PZ = base_transform_pos
        for (x,y,z),(u,v) in zip(vertices_worldspace, uvs):
            xr = int(round((x-PX)*scaleFactor)); yr = int(round((y-PY)*scaleFactor)); zr = int(round((z-PZ)*scaleFactor))
            cls.w_i16(buf, xr); cls.w_i16(buf, yr); cls.w_i16(buf, zr)
            cls.w_i16(buf, 0); cls.w_i16(buf, 0); cls.w_i16(buf, 0)
            ur = int(round((u - translationFactor*2.0)*2048.0)); vr = int(round((1.0 - v)*2048.0))
            cls.w_i16(buf, ur); cls.w_i16(buf, vr)
        for p in parts:
            cls.w_u16(buf, int(p["tex_id"]))
            cls.w_u16(buf, int(p["vertex_count"]))
            cls.w_u8(buf, int(p.get("render_flags",0)))
            cls.w_u8(buf, int(p.get("node",0)))
            cls.w_u8(buf, int(p.get("field6",0)))
            cls.w_u8(buf, int(p.get("field7",0)))
            cls.w_i32(buf, int(p.get("variance_flags",0)))
        return buf.getvalue()
    #######################################################
    @classmethod
    def write_wbl_bytes(
        cls,
        *,
        transform_header: Dict,
        sectors: List[Dict],
        textures_by_sector: List[List[int]],
        mdls: List[bytes]
    ) -> bytes:
        out = io.BytesIO()
        cls.write_leeds_cw_transform(out, transform_header)
        instance_fixups = []
        for s in range(4):
            sec = sectors[s] if s < len(sectors) else {"instances":[], "shadows":[], "levels":[], "lights":[]}
            inst = sec.get("instances", [])
            shad = sec.get("shadows", [])
            lvls = sec.get("levels", [])
            lts  = sec.get("lights", [])
            texs = textures_by_sector[s] if s < len(textures_by_sector) else []
            cls.w_u8(out, int(sec.get("Bool1",0)))
            cls.w_u8(out, int(sec.get("Bool2",0))) # what do these do?
            cls.w_i16(out, len(inst))
            cls.w_i16(out, len(shad))
            cls.w_i16(out, len(lvls))
            cls.w_i16(out, len(lts))
            cls.w_i16(out, len(texs))
            for L in lvls:
                i32 = lambda x: int(round(float(x)*4096.0))
                cls.w_i32(out, i32(L.get("X",0))); cls.w_i32(out, i32(L.get("Y",0))); cls.w_i32(out, i32(L.get("Z",0)))
                cls.w_i16(out, int(L.get("NumInstances",0))); cls.w_i16(out, int(L.get("Flags",0)))
            for I in inst:
                cls.w_i16(out, int(I.get("ID",0)))
                cls.w_i8(out,  int(I.get("RenderListID",0)))
                cls.w_i8(out,  int(I.get("BuildingSwap",0)))
                cls.w_u32(out, int(I.get("ResourceID",0)))
                pos = out.tell()
                cls.w_u32(out, 0)
                cls.w_u32(out, int(I.get("Pointer",0)))
                instance_fixups.append((pos, int(I.get("MeshRef",0))))
            for S in shad:
                if isinstance(S, (bytes, bytearray)) and len(S) == 20:
                    out.write(S)
                else:
                    i32 = lambda x: int(round(float(x)*4096.0))
                    cls.w_i32(out, i32(S.get("CenterX",0))); cls.w_i32(out, i32(S.get("CenterY",0)))
                    cls.w_f32(out, float(S.get("CenterZ",0)))
                    cls.w_i16(out, int(round(float(S.get("SizeX",0))*4096.0)))
                    cls.w_i16(out, int(round(float(S.get("SizeY",0))*4096.0)))
                    cls.w_i16(out, int(round(float(S.get("SizeZ",0))*4096.0)))
                    cls.w_i16(out, int(S.get("Unknown3",0)))
                    cls.w_u8(out,  int(S.get("Id",0))); cls.w_u8(out, int(S.get("Pad",0)))
            for L in lts:
                u32 = lambda x: int(round(max(0.0, float(x)*4096.0)))
                cls.w_u32(out, u32(L.get("X",0))); cls.w_u32(out, u32(L.get("Y",0))); cls.w_u32(out, u32(L.get("Z",0)))
                cls.w_u16(out, int(round(float(L.get("Size",0))*4096.0)) & 0xFFFF)
                cls.w_u8(out,  int(L.get("Id",0)) & 0xFF)
                cls.w_u8(out,  0)
                R,G,B = L.get("RGB",(255,255,255))
                cls.w_u8(out, R & 0xFF); cls.w_u8(out, G & 0xFF); cls.w_u8(out, B & 0xFF)
            for t in texs:
                cls.w_u16(out, int(t) & 0xFFFF)
        mdl_offsets = []
        for blob in mdls:
            mdl_offsets.append(out.tell())
            out.write(blob)
        data = bytearray(out.getvalue())
        for pos, idx in instance_fixups:
            mo = mdl_offsets[idx] if 0 <= idx < len(mdl_offsets) else 0
            struct.pack_into("<I", data, pos, mo)
        return bytes(data)

    #######################################################
    @staticmethod
    def extract_mesh_to_mdl_payload(
        obj: bpy.types.Object,
        *,
        scaleFactor: float = 64.0,
        translationFactor: float = 0.0
    ):
        if obj.type != 'MESH':
            raise TypeError("not a mesh")
        m = obj.to_mesh()
        m.calc_loop_triangles()
        verts: List[Tuple[float,float,float]] = []
        uvs: List[Tuple[float,float]] = []
        parts: List[Dict] = []
        if m.uv_layers.active:
            luv = m.uv_layers.active.data
        else:
            luv = None
        part_start = {}
        part_count = {}
        def add(loop_idx):
            vi = m.loops[loop_idx].vertex_index
            co = m.vertices[vi].co
            verts.append((co.x, co.y, co.z))
            if luv: 
                uv = luv[loop_idx].uv
                uvs.append((float(uv.x), float(uv.y)))
            else:
                uvs.append((0.0, 0.0))
        for tri in m.loop_triangles:
            mi = tri.material_index
            if mi not in part_start:
                part_start[mi] = len(verts)
                part_count[mi] = 0
            add(tri.loops[0]); add(tri.loops[1]); add(tri.loops[2])
            part_count[mi] += 3
        for mi in range(max(part_count.keys())+1 if part_count else 0):
            if mi in part_count and part_count[mi] > 0:
                parts.append({"tex_id": mi, "vertex_count": part_count[mi]})
        bpy.data.meshes.remove(m)
        return verts, uvs, parts, scaleFactor, translationFactor

    #######################################################
    @classmethod
    def register(cls): 
        pass
    #######################################################
    @classmethod
    def unregister(cls): 
        pass
