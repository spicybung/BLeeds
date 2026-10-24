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

from pathlib import Path

import bpy
from bpy.props import StringProperty
from bpy.types import Operator, Panel
from bpy_extras.io_utils import ImportHelper, ExportHelper

from ..leedsLib.native_mobile import MobileArchive
from ..ops.native_mobile import importTextures
from ..rwLib.txd import MobileTxd


class IMPORT_OT_BLeeds_MobileTxd(Operator, ImportHelper):
    bl_idname = 'import_scene.bleeds_mobile_txd'
    bl_label = 'Open Textures'
    bl_options = {'UNDO'}
    filename_ext = '.txd'
    filter_glob: StringProperty(default='*.txd;*.TXD', options={'HIDDEN'})

    def execute(self, context):
        try:
            images = importTextures(self.filepath)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, 'Loaded %d textures' % len(images))
        return {'FINISHED'}


class EXPORT_OT_BLeeds_MobileTxd(Operator, ExportHelper):
    bl_idname = 'export_scene.bleeds_mobile_txd'
    bl_label = 'Save Textures'
    filename_ext = '.txd'
    filter_glob: StringProperty(default='*.txd', options={'HIDDEN'})
    source: StringProperty(name='Original Texture File', subtype='FILE_PATH')

    def draw(self, context):
        self.layout.prop(self, 'source')

    def execute(self, context):
        import numpy as np
        try:
            source = str(Path(bpy.path.abspath(self.source)).resolve())
            dictionary = MobileTxd(Path(source).read_bytes())
            matched = 0
            for image in bpy.data.images:
                if image.get('bleeds_mobile_txd') != source:
                    continue
                width, height = image.size
                pixels = np.empty(width * height * 4, dtype=np.float32)
                image.pixels.foreach_get(pixels)
                pixels = np.rint(np.clip(pixels.reshape(height, width, 4)[::-1], 0.0, 1.0) * 255.0).astype(np.uint8)
                dictionary.replacePixels(image['bleeds_mobile_texture'], pixels)
                matched += 1
            if not matched:
                raise ValueError('No imported images match the original TXD')
            dictionary.write(self.filepath)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, 'Saved %d textures' % matched)
        return {'FINISHED'}


class IMPORT_OT_BLeeds_MobileImg(Operator, ImportHelper):
    bl_idname = 'import_scene.bleeds_mobile_img'
    bl_label = 'Extract Files'
    filename_ext = '.img'
    filter_glob: StringProperty(default='*.img;*.IMG', options={'HIDDEN'})
    directory_file: StringProperty(name='File List', description='Optional .dir file; leave blank to use the matching file beside the archive', subtype='FILE_PATH')
    output_directory: StringProperty(name='Extract To', subtype='DIR_PATH')

    def draw(self, context):
        self.layout.prop(self, 'directory_file')
        self.layout.prop(self, 'output_directory')

    def execute(self, context):
        try:
            if not self.output_directory:
                raise ValueError('Choose a folder for the extracted files')
            archive = MobileArchive(self.filepath, self.directory_file or None)
            archive.extract(bpy.path.abspath(self.output_directory))
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, 'Extracted %d files' % len(archive.entries))
        return {'FINISHED'}


class EXPORT_OT_BLeeds_MobileImg(Operator, ExportHelper):
    bl_idname = 'export_scene.bleeds_mobile_img'
    bl_label = 'Save Archive'
    filename_ext = '.img'
    filter_glob: StringProperty(default='*.img', options={'HIDDEN'})
    source: StringProperty(name='Original Archive', subtype='FILE_PATH')
    directory_file: StringProperty(name='File List', description='Optional .dir file; leave blank to use the matching file beside the archive', subtype='FILE_PATH')
    replacement_directory: StringProperty(name='Edited Files', subtype='DIR_PATH')

    def draw(self, context):
        for property_name in ('source', 'directory_file', 'replacement_directory'):
            self.layout.prop(self, property_name)

    def execute(self, context):
        try:
            archive = MobileArchive(bpy.path.abspath(self.source), bpy.path.abspath(self.directory_file) if self.directory_file else None)
            replacements = {}
            if self.replacement_directory:
                directory = Path(bpy.path.abspath(self.replacement_directory))
                known = {entry.name.casefold(): entry.name for entry in archive.entries}
                for file in directory.iterdir():
                    if file.is_file():
                        if file.name.casefold() not in known:
                            raise ValueError('Replacement is not in the source IMG: ' + file.name)
                        replacements[known[file.name.casefold()]] = file.read_bytes()
            archive.rebuild(self.filepath, str(Path(self.filepath).with_suffix('.dir')), replacements)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, 'Saved archive with %d edited files' % len(replacements))
        return {'FINISHED'}


class VIEW3D_PT_bleeds_mobile_files(Panel):
    bl_label = 'LCS Mobile'
    bl_idname = 'VIEW3D_PT_bleeds_mobile_files'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'BLeeds'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        textures = layout.box()
        textures.label(text='Textures')
        textures.operator('import_scene.bleeds_mobile_txd', text='Open Textures')
        textures.operator('export_scene.bleeds_mobile_txd', text='Save Textures')

        archive = layout.box()
        archive.label(text='Archive')
        archive.operator('import_scene.bleeds_mobile_img', text='Extract Files')
        archive.operator('export_scene.bleeds_mobile_img', text='Save Archive')
