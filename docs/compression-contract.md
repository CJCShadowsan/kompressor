# Compression Contract

All enabled default codecs are either reversible or explicitly reported as non-reversible warnings.

## JSON table

Marker: `<kompressor:json_table_v1>`

The first non-marker line is the header. Subsequent lines are rows. The delimiter is declared in metadata, and escaped delimiters, newlines, and backslashes are restored during decompression.

## JSON path

Marker: `<kompressor:json_path_v1>`

Each line is `JSONPath=value` with JSON literal values. Local exact decompression currently uses metadata retained by the Python API.

## XML path

Marker: `<kompressor:xml_path_v1>`

Each line is a path/text or path/attribute entry. Local exact decompression currently uses metadata retained by the Python API.

## Pattern hash

Marker: `<kompressor:pattern_hash_v1>`

`@dict` maps short ids to repeated lines. `@rows` is the original line sequence with repeated lines replaced by ids.

## Binary

Binary prompt compression is disabled by default. Base64/base85 are available only by explicit API configuration. Base122-style encoding is experimental until live token-count evidence proves savings.
