#!/usr/bin/env python3
"""Summarize PNG headers and chunks without exposing chunk contents."""

import argparse
from collections import Counter
from pathlib import Path
import stat
import struct
import sys
import zlib


SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_BYTES = 128 * 1024 * 1024
READ_SIZE = 64 * 1024
COLOR_TYPES = {0: "grayscale", 2: "truecolor", 3: "indexed color", 4: "grayscale with alpha", 6: "truecolor with alpha"}
ALLOWED_DEPTHS = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
METADATA_MARKERS = {"eXIf", "tEXt", "zTXt", "iTXt", "tIME"}


class PngError(ValueError):
    pass


def read_exact(stream, size, description):
    data = bytearray()
    while len(data) < size:
        part = stream.read(size - len(data))
        if not part:
            raise PngError(f"truncated {description}")
        data.extend(part)
    return bytes(data)


def inspect(path):
    source = Path(path)
    file_stat = source.stat()
    if not stat.S_ISREG(file_stat.st_mode):
        raise PngError("input must be a regular file")
    if file_stat.st_size > MAX_BYTES:
        raise PngError("input exceeds the 128 MiB limit")

    counts = Counter()
    width = height = depth = color = interlace = None
    idat_bytes = offset = 0
    with source.open("rb") as stream:
        if read_exact(stream, len(SIGNATURE), "PNG signature") != SIGNATURE:
            raise PngError("invalid PNG signature")
        offset = len(SIGNATURE)

        while offset < file_stat.st_size:
            if file_stat.st_size - offset < 12:
                raise PngError("truncated chunk header")
            length = struct.unpack(">I", read_exact(stream, 4, "chunk length"))[0]
            kind = read_exact(stream, 4, "chunk type")
            if any(not (65 <= byte <= 90 or 97 <= byte <= 122) for byte in kind):
                raise PngError("chunk type must contain four ASCII letters")
            if length + 4 > file_stat.st_size - offset - 8:
                raise PngError("chunk length exceeds the remaining file")
            if not counts and kind != b"IHDR":
                raise PngError("IHDR must be the first chunk")
            if kind == b"IHDR" and (counts or length != 13):
                raise PngError("PNG must contain one 13-byte IHDR as its first chunk")
            if kind == b"IEND" and length != 0:
                raise PngError("IEND must have an empty data field")

            name = kind.decode("ascii")
            counts[name] += 1
            checksum = zlib.crc32(kind)
            header = bytearray() if kind == b"IHDR" else None
            remaining = length
            while remaining:
                block = stream.read(min(remaining, READ_SIZE))
                if not block:
                    raise PngError(f"truncated {name} chunk data")
                remaining -= len(block)
                checksum = zlib.crc32(block, checksum)
                if header is not None:
                    header.extend(block)
            expected = struct.unpack(">I", read_exact(stream, 4, f"{name} CRC"))[0]
            if checksum != expected:
                raise PngError(f"invalid CRC in {name} chunk")

            if header is not None:
                width, height, depth, color, compression, filter_method, interlace = struct.unpack(">IIBBBBB", header)
                if not 1 <= width <= 0x7FFFFFFF or not 1 <= height <= 0x7FFFFFFF:
                    raise PngError("image dimensions are outside the PNG range")
                if color not in ALLOWED_DEPTHS or depth not in ALLOWED_DEPTHS[color]:
                    raise PngError("invalid color type and bit-depth combination")
                if compression != 0 or filter_method != 0 or interlace not in (0, 1):
                    raise PngError("unsupported IHDR method")
            if kind == b"IDAT":
                idat_bytes += length

            offset += 12 + length
            if kind == b"IEND":
                if offset != file_stat.st_size:
                    raise PngError("unexpected bytes after IEND")
                break

    if "IHDR" not in counts or "IEND" not in counts or not counts["IDAT"]:
        raise PngError("PNG needs IHDR, at least one IDAT, and IEND")
    return width, height, depth, color, interlace, counts, idat_bytes


def main():
    parser = argparse.ArgumentParser(
        description="Summarize PNG dimensions and chunk types without printing metadata contents."
    )
    parser.add_argument("input", help="PNG image file")
    args = parser.parse_args()

    try:
        width, height, depth, color, interlace, counts, idat_bytes = inspect(args.input)
    except PngError as error:
        print(f"png-tally: invalid or unsupported PNG: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"png-tally: {error.strerror or 'unable to read input'}", file=sys.stderr)
        return 2

    print(f"Dimensions: {width} × {height} pixels")
    print(f"Color type: {COLOR_TYPES[color]}")
    print(f"Bit depth: {depth}")
    print(f"Interlacing: {'Adam7' if interlace else 'none'}")
    print(f"IDAT data: {idat_bytes} bytes; pixel data was not decompressed")
    print(f"Chunks: {sum(counts.values())}; CRCs verified: {sum(counts.values())}")
    print("Chunk counts:")
    for name, count in sorted(counts.items()):
        print(f"  {name}: {count}")
    markers = sorted(METADATA_MARKERS.intersection(counts))
    print(f"Potential metadata markers: {', '.join(markers) if markers else 'none detected'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
