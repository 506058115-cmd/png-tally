# png-tally

Summarize a PNG image's dimensions, color mode, chunk types, and possible privacy-bearing metadata markers without printing metadata values or decoding pixels. Chunk payloads are streamed through the CRC check in bounded blocks. Input is limited to 128 MiB.

## Use

Requires Python 3.8+; no packages to install.

```sh
python png_tally.py photo.png
```

The tool verifies the PNG signature, the first `IHDR`, chunk lengths, each chunk CRC, and the required `IDAT` and `IEND` chunks. It reports the presence of `eXIf`, `tEXt`, `zTXt`, `iTXt`, and `tIME` chunks as potential metadata markers, but never interprets or prints their values. It does not inflate or validate compressed image data and is not a complete PNG conformance checker. Exit status is 0 for supported structure, 1 for malformed or unsupported PNG, and 2 for unreadable input.

## License

MIT
