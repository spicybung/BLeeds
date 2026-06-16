# BLeeds - Rockstar Games Leeds Blender IO

[![License](https://img.shields.io/badge/license-GPLv3-blue.svg)](LICENSE)

BLeeds is an IO for Blender, with scripts designed around the Leeds Engine file formats(Stories, Chinatown Wars, Manhunt 2). It is a work-in-progress reverse engineering of R* Leeds file formats.

## Supported Formats

The following is a list of file formats that are currently supported by the addon

#### File Types

- [X] Model files (.mdl, .wbl)*
  - [X] Import
  - [x] Export *
- [X] Texture Files (.chk, .xtx, .tex)*
  - [X] Import
  - [ ] Export
- [X] Collision files (.col2)*
  - [X] Import
  - [x] Export *
- [X] Map files (.wrld, .wbl)*
  - [X] Import
  - [x] Export *
- [X] Animation files
  - [X] Import *
  - [ ] Export

* all of the above are currently experimental, meaning not all files have been tested yet.

1. [Download](https://github.com/spicybung/BLeeds/archive/refs/heads/master.zip) the addon zip file from the latest master branch
2. Import the downloaded .zip file by selecting it from *(User) Preferences/Addons/Install from File*
3. Set the addon "BLeeds" to enabled
4. Import files from Import tab, export files from the Export tab
