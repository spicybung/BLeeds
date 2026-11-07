
# Finally, an I/O for the GTA Stories games, and more!

[![License](https://img.shields.io/badge/license-GPLv3-blue.svg)](LICENSE)

**BLeeds** is a Blender importer/exporter for Rockstar Leeds games such as Liberty City Stories, Vice City Stories, Grand Theft Auto: Chinatown Wars, as well as Manhunt 2. Work on this project has been done via extensive reverse engineering of R* Leeds file formats over a significant length of time.

## Supported Formats

The following is a list of file formats that are currently supported by the addon.

#### File Types

- [x] Model files (.mdl, .dff)*
  - [x] Import
  - [x] Export
- [x] Texture files (.chk, .xtx, .tex)*
  - [x] Import
  - [x] Export
- [x] Collision files (.col2)*
  - [x] Import
  - [x] Export
- [x] Animation files (.anim, .ifp)*
  - [x] Import
  - [x] Export
- [x] Map files (.wrld, .wbl, .bsp)*
  - [x] Import
  - [x] Export
- [x] IMG archives (.img + .lvz)*
  - [x] Import
  - [ ] Export

*All of the above are currently experimental, meaning not all files have been tested yet.*

## How to Use

1. [Download](https://github.com/spicybung/BLeeds/releases/latest) the addon ZIP file from the latest release.
2. Install the downloaded ZIP file through Blender's **Edit > Preferences > Add-ons > Install from Disk** (or **Install from File** in older Blender versions).
3. Enable the **BLeeds** addon.
4. Import files from the **Import** menu, or export files from the **Export** menu.

## Contributing

Contributions are welcome! If you have suggestions, bug reports, or want to contribute code, please check out the [Contributing Guidelines](CONTRIBUTING.md).

## Documentation

For documentation, visit the [BLeeds Wiki](https://github.com/spicybung/BLeeds/wiki).

## License

This project is licensed under the GPL 3.0 License. See the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Special thanks to the Blender community and contributors for their open-source efforts.
- The GTA modding community, for the inspiration years ago.
- The GTA Mods Wiki & GTAModding Wiki (RIP) for being a huge, considerate help in figuring things such as data structures out.
- Daniil Sayanov, for his great help, knowledge of R* Leeds formats, as well as inspiration and motivation.
- MAJESTIC_R3 for his Stories Map Converter program, which was surprisingly helpful in decoding file formats on its own.
- Guard3 for his work on G3DTZ, which was helpful in decoding the .DTZ format.
- Last, but not least, The_Hero (aap) for his incredible knowledge and previous Leeds reverse engineering efforts. He has been invaluable to the community.
