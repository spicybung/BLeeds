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

from bpy.types import Menu

class CW_MT_ExportChoice(Menu):
    bl_idname = "CW_MT_ExportChoice"
    bl_label = "BLeeds"

    def draw(self, context):
        layout = self.layout
        layout.operator("export_scene.leeds_anim", text="R* Leeds: Animation (.anim)")
        layout.operator(
            "export_scene.bleeds_stories_mdl",
            text="R* Leeds: Model (.mdl)",
        )
        layout.operator(
            "export_scene.leeds_tex",
            text="R* Leeds: Texture Dictionary (.chk, .xtx, .tex)",
        )
        layout.operator(
            "export_scene.bleeds_dff",
            text="R* Studios: DFF (.dff)",
        )
        layout.operator(
            "export_scene.leeds_lvz_img",
            text="R* Leeds: LeVelZlib IMG Archive (.lvz + .img)",
        )
        layout.operator(
            "export_scene.col2_leeds",
            text="R* Leeds: Collision Archive (.col2)",
        )
        layout.operator(
            "export_scene.cw_wbl",
            text="R* Leeds: Worldblock (.wbl)",
        )

class TOPBAR_MT_file_import_bleeds(Menu):
    bl_idname = "TOPBAR_MT_file_import_bleeds"
    bl_label = "BLeeds"

    def draw(self, context):
        layout = self.layout
        layout.operator(
            "import_scene.bleeds_dff",
            text="R* Studios: DFF (.dff)",
        )
        layout.operator("import_scene.bleeds_mobile_txd", text="R* Studios: Texture Dictionary (.txd)")
        layout.operator(
            "import_scene.bleeds_manhunt_ifp",
            text="R* Studios: IFP (.ifp)",
        )
        layout.operator(
            "import_scene.bleeds_stories_mdl",
            text="R* Leeds: Model (.mdl)",
        )
        layout.operator(
            "import_scene.leeds_anim",
            text="R* Leeds: Animation (.anim)",
        )
        layout.operator(
            "import_scene.col2_leeds",
            text="R* Leeds: Collision Archive (.col2)",
        )
        layout.operator(
            "import_scene.leeds_tex",
            text="R* Leeds: Texture Dictionary (.chk, .xtx, .tex)",
        )
        layout.operator(
            "import_scene.leeds_lvz_img",
            text="R* Leeds: World (.dtz, .lvz + .img)",
        )
        layout.operator(
            "import_scene.leeds_world",
            text="R* Leeds: World Level (.wrld, .bsp)",
        )
        layout.operator(
            "import_scene.cw_wbl",
            text="R* Leeds: Worldblock (.wbl)",
        )

def cw_menu_import(self, context):
    self.layout.menu(TOPBAR_MT_file_import_bleeds.bl_idname)

def cw_menu_export(self, context):
    self.layout.menu(CW_MT_ExportChoice.bl_idname)
