# Contributing to BLeeds

BLeeds is a work-in-progress Blender I/O add-on for Rockstar Leeds Engine formats. Contributions are welcome, especially fixes backed by actual files, repeatable tests, and useful reverse-engineering notes.

This project deals with several games, platforms, revisions, and variations of the same formats. A change that fixes one file can easily break another, so please test your work properly before opening a pull request.

## Before opening an issue

Check that you are using the latest version of BLeeds from the `main` branch or the latest release.

When reporting a problem, include:

* The BLeeds version or commit you tested.
* Your Blender version.
* The game and platform the file came from.
* The exact file type being imported or exported.
* The full console output or traceback.
* A clear description of what is wrong.
* Screenshots when the problem is visual.
* Steps that reproduce the problem.

For map problems, include useful details such as the object name, resource ID, IPL ID, position, collection, or source archive when known.

Do not report an import as simply “broken” or “not working.” There needs to be enough information to reproduce and investigate it.

## Game and platform details matter

Always identify the source correctly. For example:

* Liberty City Stories: PSP or PS2
* Vice City Stories: PSP or PS2
* Chinatown Wars: PSP or another supported version
* Manhunt 2: PSP, PS2, Wii, or PC

Files with the same extension are not guaranteed to use the same structures. Do not assume that logic verified for one game or platform is valid for every other one.

Manhunt 2 beta assets currently being researched in this project should be identified as PSP assets when that is their actual source.

## Test files

Do not upload copyrighted game assets directly to the repository or attach them publicly to an issue.

You may provide:

* Small original test files that you created.
* Hex snippets containing only the bytes required to explain a structure.
* Offsets, sizes, field descriptions, hashes, and parser logs.
* Scripts that reproduce or inspect the problem.
* Checksums and exact filenames so a maintainer can identify the same file.
* Privately shared samples when necessary and legally permitted.

Keep test data as small as possible while still reproducing the issue.

## Reverse-engineering contributions

Reverse-engineering notes are useful, but separate confirmed facts from guesses.

Good notes should include:

* The game and platform.
* The filename and file type.
* Relevant offsets.
* Endianness.
* Field sizes and signedness.
* Alignment or padding rules.
* Pointer or relative-offset bases.
* Counts, strides, and terminators.
* Several examples when possible.
* What was confirmed by import, export, comparison, or game testing.

Do not copy a structure from another tool and assume it applies here. Explain how the result was verified.

Avoid broad fallback logic that silently guesses missing data. Exact parsing and clearly logged recovery paths are preferred over nearest matches, forced clones, or unrelated resource substitutions.

## Code contributions

Keep changes focused. Do not combine a parser fix, a large cleanup, UI redesign, and unrelated formatting changes in the same pull request.

Please follow the existing project layout:

* `leedsLib` contains format and data-handling code.
* `ops` contains Blender operators and import/export operations.
* `gui` contains menus, panels, and other interface code.
* `data` contains supporting data used by the add-on.

Keep format parsing separate from Blender scene creation where practical. Binary readers should return understandable data instead of directly creating Blender objects throughout the parser.

Use readable names and straightforward control flow. Avoid unnecessary abstractions, placeholder code, unexplained constants, and duplicated parsing logic.

Do not add hard-coded local paths.

Do not hide parser failures with a broad `except` block. Catch expected errors, include useful context, and let unexpected failures produce a traceback.

When adding debug output, make it useful. Include filenames, offsets, IDs, counts, or addresses needed to understand the failure. Avoid printing thousands of meaningless lines during a normal import.

## Blender compatibility

State which Blender versions you tested.

Do not use a newer Blender API without checking whether the project’s supported versions have an equivalent. Changes should not disable unrelated add-ons, modify user preferences, or leave Blender data in a partially created state after a failed import.

Operators should report failures clearly and clean up temporary objects, meshes, collections, materials, images, and handlers when appropriate.

## Import and export changes

For import changes, test more than one file whenever possible. Check:

* Geometry
* Indices and triangle winding
* Normals
* UVs
* Materials and textures
* Vertex colors or prelighting
* Skin weights and bones
* Object transforms
* Names and collections
* Collision data
* 2DFX data
* Map placement

For export changes, verify the written file instead of only checking that Blender produced one. At minimum, compare the structure against a known file or re-import the result. When possible, test the exported file in the original game or another trusted tool.

Round-trip output does not need to be byte-identical unless the format requires it, but it must preserve the data BLeeds claims to support.

## Pull requests

A pull request should explain:

* What was wrong.
* What caused it.
* What was changed.
* Which files, games, and platforms were tested.
* What remains experimental or unverified.

Include console output, screenshots, offsets, or before-and-after results when they help prove the fix.

Keep generated files, extracted game assets, caches, Blender backup files, logs, and personal test paths out of commits.

Use LF line endings.

Do not reformat unrelated files.

## Commit messages

Use a clear description of the actual change.

Examples:

* `Fix VCS PS2 MDL material parsing`
* `Add PSP ANIM track validation`
* `Correct WRLD object transforms`
* `Preserve COL2 surface properties on export`

Avoid messages such as `fix`, `update`, or `changes`.

## New format support

Before adding a new format or a major variation of an existing format, provide enough information to maintain it:

* Known header and section layout.
* Detection rules.
* Game and platform coverage.
* At least one reproducible test.
* Known limitations.
* Import or export behavior.
* Failure handling for unsupported variants.

Experimental support is fine, but it must be identified as experimental and must not pretend to support files that have not been tested.

## Documentation

Update the README, Wiki, comments, or format notes when a change affects installation, supported formats, operators, file detection, or user-visible behavior.

Documentation should describe what BLeeds actually does. Do not claim full support based on one successful test file.

## License

By contributing to BLeeds, you agree that your contribution will be distributed under the project’s GPL-3.0 license.
::: 
