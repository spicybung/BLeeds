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


# === LCS Bone Arrays ===
commonBoneOrder = (
    "Root", "Pelvis", "Spine", "Spine1", "Neck", "Head",
    "Bip01 L Clavicle", "L UpperArm", "L Forearm", "L Hand", "L Finger", "Bip01 R Clavicle",
    "R UpperArm", "R Forearm", "R Hand", "R Finger", "L Thigh", "L Calf",
    "L Foot", "L Toe0", "R Thigh", "R Calf", "R Foot", "R Toe0"
)
kamBoneID = (
    0, 1, 2, 3, 4, 5, 31, 32, 33, 34, 35, 21, 22, 23, 24, 25, 41, 42, 43, 2000, 51, 52, 53, 2001
)
kamFrameName = (
    "Root", "Pelvis", "Spine", "Spine1", "Neck", "Head",
    "Bip01~L~Clavicle", "L~UpperArm", "L~Forearm", "L~Hand", "L~Finger", "Bip01~R~Clavicle",
    "R~UpperArm", "R~Forearm", "R~Hand", "R~Finger", "L~Thigh", "L~Calf",
    "L~Foot", "L~Toe0", "R~Thigh", "R~Calf", "R~Foot", "R~Toe0"
)
kamBoneType = (
    0, 0, 0, 2, 0, 3, 2, 0, 0, 0, 1, 0, 0, 0, 0, 1, 2, 0, 0, 1, 0, 0, 0, 1
)
kamBoneIndex = (
    "00", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23"
)

commonBoneParentsLCS = {
    "Pelvis": "Root",
    "Spine": "Pelvis",
    "Spine1": "Spine",
    "Neck": "Spine1",
    "Head": "Neck",
    "Bip01 L Clavicle": "Spine1",
    "L UpperArm": "Bip01 L Clavicle",
    "L Forearm": "L UpperArm",
    "L Hand": "L Forearm",
    "L Finger": "L Hand",
    "Bip01 R Clavicle": "Spine1",
    "R UpperArm": "Bip01 R Clavicle",
    "R Forearm": "R UpperArm",
    "R Hand": "R Forearm",
    "R Finger": "R Hand",
    "L Thigh": "Pelvis",
    "L Calf": "L Thigh",
    "L Foot": "L Calf",
    "L Toe0": "L Foot",
    "R Thigh": "Pelvis",
    "R Calf": "R Thigh",
    "R Foot": "R Calf",
    "R Toe0": "R Foot"
} # o_O
# === VCS Bone Arrays ===
commonBoneOrderVCS = (
    "root", "pelvis", "spine", "spine1", "neck", "head",
    "jaw", "bip01_l_clavicle", "l_upperarm", "l_forearm", "l_hand", "l_finger",
    "bip01_r_clavicle", "r_upperarm", "r_forearm", "r_hand", "r_finger", "l_thigh",
    "l_calf", "l_foot", "l_toe0", "r_thigh", "r_calf", "r_foot", "r_toe0"
)

commonBoneNamesVCS = (
    "Root", "Pelvis", "Spine", "Spine1", "Neck", "Head",
    "Jaw", "Bip01 L Clavicle", "L UpperArm", "L Forearm", "L Hand", "L Finger",
    "Bip01 R Clavicle", "R UpperArm", "R Forearm", "R Hand", "R Finger", "L Thigh",
    "L Calf", "L Foot", "L Toe0", "R Thigh", "R Calf", "R Foot", "R Toe0"
)

kamBoneIDVCS = (
    0, 1, 2, 3, 4, 5,
    8, 31, 32, 33, 34, 35,
    21, 22, 23, 24, 25, 41,
    42, 43, 2000, 51, 52, 53,
    2001
)

kamFrameNameVCS = (
    "Root", "Pelvis", "Spine", "Spine1", "Neck", "Head",
    "Jaw", "Bip01~L~Clavicle", "L~UpperArm", "L~Forearm", "L~Hand", "L~Finger",
    "Bip01~R~Clavicle", "R~UpperArm", "R~Forearm", "R~Hand", "R~Finger", "L~Thigh",
    "L~Calf", "L~Foot", "L~Toe0", "R~Thigh", "R~Calf", "R~Foot", "R~Toe0"
)

kamBoneTypeVCS = (
    0, 0, 0, 2, 0, 2,
    3, 2, 0, 0, 0, 1,
    0, 0, 0, 0, 1, 2,
    0, 0, 1, 0, 0, 0,
    1
)

kamBoneIndexVCS = (
    "00", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23"
)    # for compatibility with Kams Scripts(3DSMax)

commonBoneParentsVCS = {
    "pelvis": "root",
    "spine": "pelvis",
    "spine1": "spine",
    "neck": "spine1",
    "head": "neck",
    "jaw": "head",
    "bip01_l_clavicle": "spine1",
    "l_upperarm": "bip01_l_clavicle",
    "l_forearm": "l_upperarm",
    "l_hand": "l_forearm",
    "l_finger": "l_hand",
    "bip01_r_clavicle": "spine1",
    "r_upperarm": "bip01_r_clavicle",
    "r_forearm": "r_upperarm",
    "r_hand": "r_forearm",
    "r_finger": "r_hand",
    "l_thigh": "pelvis",
    "l_calf": "l_thigh",
    "l_foot": "l_calf",
    "l_toe0": "l_foot",
    "r_thigh": "pelvis",
    "r_calf": "r_thigh",
    "r_foot": "r_calf",
    "r_toe0": "r_foot"
} # o_O