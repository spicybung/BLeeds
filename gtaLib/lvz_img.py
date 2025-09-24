# BLeeds - Scripts for working with R* Leeds (GTA Stories, Manhunt 2, etc) formats in Blender
# Author: SpicyBung
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

import os
import bpy
import zlib
import struct

from bpy.props import StringProperty
from bpy_extras.io_utils import ImportHelper

#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
#   This script is for .LVZ & .IMG respectively - formats for Stories file archives
#   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #   #
# - Script resources:
# • https://gtamods.com/wiki/IMG_archive
# • https://web.archive.org/web/20180729202923/http://gtamodding.ru/wiki/WRLD (Russian)
# • https://web.archive.org/web/20180729204205/http://gtamodding.ru/wiki/CHK (Russian - WRLD textures)
# • https://web-archive-org.translate.goog/web/20180810183857/http://gtamodding.ru/wiki/LVZ?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (English)
# • https://web-archive-org.translate.goog/web/20180807031320/http://www.gtamodding.ru/wiki/IMG?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (ditto)
# • https://web-archive-org.translate.goog/web/20180729204205/http://gtamodding.ru/wiki/CHK?_x_tr_sl=ru&_x_tr_tl=en&_x_tr_hl=en (ditto - WRLD textures)

# TODO: correctly parse Stories LVZ/IMG cuz it's boning me
