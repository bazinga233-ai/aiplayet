import argparse
import json
import shutil
import struct
from pathlib import Path
from typing import Callable


REQUIRED_BINARIES = ("ffmpeg.exe", "ffprobe.exe")


def _read_c_string(buffer: bytes, offset: int) -> str:
    end = buffer.find(b"\x00", offset)
    if end < 0:
        end = len(buffer)
    return buffer[offset:end].decode("ascii")


def read_imported_library_names(binary_path: Path) -> list[str]:
    buffer = Path(binary_path).read_bytes()
    if len(buffer) < 0x40 or buffer[:2] != b"MZ":
        return []

    pe_offset = struct.unpack_from("<I", buffer, 0x3C)[0]
    if pe_offset + 0x18 >= len(buffer) or buffer[pe_offset:pe_offset + 4] != b"PE\x00\x00":
        return []

    number_of_sections = struct.unpack_from("<H", buffer, pe_offset + 6)[0]
    optional_header_size = struct.unpack_from("<H", buffer, pe_offset + 20)[0]
    optional_header_offset = pe_offset + 24
    if optional_header_offset + optional_header_size > len(buffer):
        return []

    optional_magic = struct.unpack_from("<H", buffer, optional_header_offset)[0]
    if optional_magic == 0x10B:
        data_directory_offset = optional_header_offset + 96
    elif optional_magic == 0x20B:
        data_directory_offset = optional_header_offset + 112
    else:
        return []

    if data_directory_offset + 16 > len(buffer):
        return []

    import_directory_rva = struct.unpack_from("<I", buffer, data_directory_offset + 8)[0]
    if import_directory_rva == 0:
        return []

    section_table_offset = optional_header_offset + optional_header_size
    sections: list[tuple[int, int, int, int]] = []
    for index in range(number_of_sections):
        section_offset = section_table_offset + index * 40
        if section_offset + 40 > len(buffer):
            return []
        virtual_size = struct.unpack_from("<I", buffer, section_offset + 8)[0]
        virtual_address = struct.unpack_from("<I", buffer, section_offset + 12)[0]
        raw_size = struct.unpack_from("<I", buffer, section_offset + 16)[0]
        raw_pointer = struct.unpack_from("<I", buffer, section_offset + 20)[0]
        sections.append((virtual_address, max(virtual_size, raw_size), raw_pointer, raw_size))

    def rva_to_offset(rva: int) -> int | None:
        for virtual_address, span, raw_pointer, raw_size in sections:
            if virtual_address <= rva < virtual_address + span:
                offset = raw_pointer + (rva - virtual_address)
                if offset < len(buffer) and offset < raw_pointer + raw_size:
                    return offset
                return None
        return None

    import_directory_offset = rva_to_offset(import_directory_rva)
    if import_directory_offset is None:
        return []

    libraries: list[str] = []
    entry_offset = import_directory_offset
    while entry_offset + 20 <= len(buffer):
        original_first_thunk, time_date_stamp, forwarder_chain, name_rva, first_thunk = struct.unpack_from(
            "<IIIII",
            buffer,
            entry_offset,
        )
        if not any((original_first_thunk, time_date_stamp, forwarder_chain, name_rva, first_thunk)):
            break
        if name_rva:
            name_offset = rva_to_offset(name_rva)
            if name_offset is not None:
                libraries.append(_read_c_string(buffer, name_offset))
        entry_offset += 20
    return libraries


def collect_runtime_files(
    ffmpeg_dir: Path,
    dependency_reader: Callable[[Path], list[str]] | None = None,
) -> list[Path]:
    source_dir = Path(ffmpeg_dir).resolve()
    if not source_dir.is_dir():
        raise FileNotFoundError(f"FFmpeg runtime directory not found: {source_dir}")

    required = [source_dir / name for name in REQUIRED_BINARIES]
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Missing required FFmpeg binaries: " + ", ".join(missing)
        )

    dependency_reader = dependency_reader or read_imported_library_names
    local_dlls = {
        path.name.lower(): path
        for path in source_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".dll"
    }
    resolved_dependencies: dict[str, Path] = {}
    pending = list(required)

    while pending:
        current = pending.pop(0)
        for dependency_name in dependency_reader(current):
            candidate = local_dlls.get(dependency_name.lower())
            if candidate is None or candidate.name.lower() in resolved_dependencies:
                continue
            resolved_dependencies[candidate.name.lower()] = candidate
            pending.append(candidate)

    return required + list(resolved_dependencies.values())


def copy_runtime_files(
    ffmpeg_dir: Path,
    destination_dir: Path,
    dependency_reader: Callable[[Path], list[str]] | None = None,
) -> list[Path]:
    source_files = collect_runtime_files(
        Path(ffmpeg_dir),
        dependency_reader=dependency_reader,
    )
    target_dir = Path(destination_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    copied: list[Path] = []
    for source in source_files:
        target = target_dir / source.name
        shutil.copy2(source, target)
        copied.append(target)
    return copied


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Collect or copy FFmpeg runtime files for the Nova release bundle."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser("collect", help="Print runtime file names as JSON.")
    collect_parser.add_argument("--source", required=True)

    copy_parser = subparsers.add_parser("copy", help="Copy runtime files into a release directory.")
    copy_parser.add_argument("--source", required=True)
    copy_parser.add_argument("--destination", required=True)

    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.command == "collect":
        files = collect_runtime_files(Path(args.source))
        print(json.dumps([path.name for path in files], ensure_ascii=False))
        return 0

    copied = copy_runtime_files(Path(args.source), Path(args.destination))
    print(json.dumps([path.name for path in copied], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
