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

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
import sys
import traceback


class ImportLogWriter:
    def __init__(self, console, text_file):
        self.console = console
        self.text_file = text_file

    def write(self, value):
        if self.console is not None:
            self.console.write(value)
        if self.text_file is not None:
            self.text_file.write(value)
        return len(value)

    def flush(self):
        if self.console is not None:
            self.console.flush()
        if self.text_file is not None:
            self.text_file.flush()


def drawImportLogOptions(layout, operator):
    layout.separator()
    column = layout.column(align=True)
    column.prop(operator, "print_debug_log")
    column.prop(operator, "print_text_log")


@contextmanager
def captureImportLog(operator, filepath):
    print_debug_log = bool(getattr(operator, "print_debug_log", False))
    print_text_log = bool(getattr(operator, "print_text_log", False))
    text_file = None

    if print_text_log:
        try:
            text_file = Path(str(filepath) + ".import.txt").open("w", encoding="utf-8")
        except OSError as exc:
            operator.report({"WARNING"}, "Could not write import log: {}".format(exc))

    console = sys.stdout if print_debug_log else None
    writer = ImportLogWriter(console, text_file)
    try:
        with redirect_stdout(writer), redirect_stderr(writer):
            if print_debug_log or print_text_log:
                print("BLeeds import: {}".format(filepath))
            try:
                yield
            except BaseException:
                if print_debug_log or print_text_log:
                    traceback.print_exc()
                raise
            finally:
                if print_debug_log or print_text_log:
                    print("BLeeds import finished: {}".format(filepath))
                writer.flush()
    finally:
        if text_file is not None:
            text_file.close()


def runImport(operator, context, import_function):
    with captureImportLog(operator, operator.filepath):
        result = import_function(context)
        if operator.print_debug_log or operator.print_text_log:
            print("Import result: {}".format(", ".join(sorted(result))))
        return result

