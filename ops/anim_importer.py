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
import struct

from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from os import SEEK_CUR

#######################################################
class IMPORT_OT_ifp_manhunt(Operator, ImportHelper):
    bl_idname = "import_anim.ifp_manhunt"
    bl_label = "Import Manhunt IFP Animation"
    filename_ext = ".ifp"
    filter_glob: bpy.props.StringProperty(default="*.ifp", options={'HIDDEN'})

    def execute(self, context):     # Apply the animation
        path = self.filepath
        armature = context.object

        if armature is None or armature.type != 'ARMATURE':
            self.report({'ERROR'}, "Select an Armature to apply the animation.")
            return {'CANCELLED'}

        with open(path, 'rb') as f:
            def read_u8(): return struct.unpack("B", f.read(1))[0]
            def read_u16(): return struct.unpack("<H", f.read(2))[0]
            def ru32(f): return struct.unpack("<I", f.read(4))[0]
            def read_f32(): return struct.unpack("<f", f.read(4))[0]
            def read_str(length): return f.read(length).decode('latin1', errors='replace').strip('\0')

            def apply_animation(bone_map, keyframes):
                action = bpy.data.actions.new(name="ImportedIFP")
                armature.animation_data_create()
                armature.animation_data.action = action
                for bone_name, frames in keyframes.items():
                    if bone_name not in armature.pose.bones:
                        continue
                    bone = armature.pose.bones[bone_name]
                    data_path_rot = bone.path_from_id("rotation_quaternion")
                    data_path_loc = bone.path_from_id("location")

                    cr = [action.fcurves.new(data_path=data_path_rot, index=i, action_group=bone.name) for i in range(4)]
                    cl = [action.fcurves.new(data_path=data_path_loc, index=i, action_group=bone.name) for i in range(3)]

                    for frame, (quat, pos) in frames.items():
                        if quat:
                            for i, c in enumerate(cr):
                                c.keyframe_points.insert(frame, quat[i], options={'FAST'})
                        if pos:
                            for i, c in enumerate(cl):
                                c.keyframe_points.insert(frame, pos[i], options={'FAST'})

            def read_ANPK():        # MH1&2 .IFP carries ANCT+ANPK header?
                header = f.read(4)
                if header != b'ANPK':
                    self.report({'ERROR'}, "Invalid ANPK header")
                    return
                numAnimPack = ru32(f)
                bone_map = {}
                keyframes = {}

                for _ in range(numAnimPack):
                    name = f.read(4)
                    animNameLen = ru32(f)
                    animName = read_str(animNameLen)

                    numBones = ru32(f)
                    chunkSize = ru32(f)
                    frameTimeCount = read_f32()

                    for _ in range(numBones):
                        flag = f.read(4).decode('ascii', errors='ignore')
                        boneID = read_u16()
                        frameType = read_u8()
                        frames = read_u16()
                        startOffset = f.tell()
                        startTime = read_u16()

                        if frameType > 2:
                            direction_quat = struct.unpack("<4h", f.read(8))
                        elif startTime == 0:
                            f.seek(-2, SEEK_CUR)

                        bone_name = None
                        for bone in armature.pose.bones:
                            if "BoneID" in bone and bone["BoneID"] == boneID:
                                bone_name = bone.name
                                break
                        if bone_name is None:
                            skip_len = frames * ((8 if frameType < 3 else 0) + (6 if frameType > 1 else 0))
                            f.seek(skip_len, SEEK_CUR)
                            if flag == "SEQT":
                                f.read(4)
                            continue

                        keyframes[bone_name] = {}

                        for i in range(frames):
                            time = i if startTime > 0 else read_u16() / 2048.0 * 30.0
                            frame = int(startTime / 2048.0 * 30.0 - 1 + i) if startTime > 0 else int(time)

                            quat = pos = None
                            if frameType < 3:
                                q = struct.unpack("<4h", f.read(8))
                                quat = tuple(v / 4096.0 for v in q)
                            if frameType > 1:
                                t = struct.unpack("<3h", f.read(6))
                                pos = tuple(v / 2048.0 for v in t)

                            keyframes[bone_name][frame] = (quat, pos)

                        if flag == "SEQT":
                            _ = read_f32()

                    header_size = ru32(f)
                    _ = read_f32()
                    eachEntrySize = ru32(f)
                    numEntry = ru32(f)
                    for _ in range(numEntry):
                        if flag == "SEQT":
                            f.read(64 + 8 + 4 * 5 + 28 + 40)
                        elif flag == "SEQU":
                            f.read(8 + 4 * 5 + 8 + 28 + 4)

                apply_animation(bone_map, keyframes)

            magic = f.read(4)
            if magic == b'ANCT':
                numBlock = ru32(f)
                for i in range(numBlock):
                    bloc_id = f.read(4)
                    bloc_len = ru32(f)
                    bloc_name = read_str(bloc_len)
                    print(f"\n== BLOC: {bloc_name} ==")
                    read_ANPK()
            else:
                self.report({'ERROR'}, "Not a valid ANCT header")
                return {'CANCELLED'}

        return {'FINISHED'}

def menu_func_import(self, context):
    self.layout.operator(IMPORT_OT_ifp_manhunt.bl_idname, text="Manhunt IFP (.ifp)")

def register():
    bpy.utils.register_class(IMPORT_OT_ifp_manhunt)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.utils.unregister_class(IMPORT_OT_ifp_manhunt)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

if __name__ == "__main__":
    register()