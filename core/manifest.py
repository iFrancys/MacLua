"""Binary Steam depot manifests: sections, protobuf, chunk crypto.

Format (SteamKit2 DepotManifest/VZipUtil/VZstdUtil):
- sections: u32le magic + u32le len + body; 0x71F617D0 payload (protobuf
  ContentManifestPayload), 0x1F4812BE metadata, 0x1B81B817 signature (skip),
  0x32C415AB end marker (without len).
- encrypted chunks: iv=AES256-ECB(cipher[0:16]); AES256-CBC+PKCS7 remainder.
- VZa: 'VZ'+'a', footer u32 CRC32 + i32 size + 'zv' (CRC authoritative).
- VSZa: 'VSZa', footer ... + i32 size + 'zsv'.
- ZIP: single entry.
- chunk checksum: Adler32 with seed s1=0,s2=0 (zlib starts at s1=1).
"""
import struct

PAYLOAD_MAGIC = 0x71F617D0
METADATA_MAGIC = 0x1F4812BE
SIGNATURE_MAGIC = 0x1B81B817
TERMINAL_MAGIC = 0x32C415AB


def _u32(b, pos):
    if pos + 4 > len(b):
        return None
    return struct.unpack_from("<I", b, pos)[0]


def split_sections(data):
    if not data:
        raise ValueError("empty manifest")
    out = []
    pos, n = 0, len(data)
    while pos < n:
        magic = _u32(data, pos)
        if magic is None:
            raise ValueError("truncated section header")
        if magic == TERMINAL_MAGIC:
            if pos + 4 != n:
                raise ValueError("terminal marker not at end")
            pos += 4
            break
        length = _u32(data, pos + 4)
        if length is None:
            raise ValueError("truncated section length")
        first, last = pos + 8, pos + 8 + length
        if last > n:
            raise ValueError("section past end of data")
        out.append((magic, data[first:last]))
        pos = last
    return out


def _varint(buf, pos, limit):
    result = shift = 0
    while pos < limit:
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
        if shift >= 70:
            raise ValueError("varint too long")
    raise ValueError("truncated varint")


def _fields(buf, pos=0, limit=None):
    """(field, wire, value): wire2 returns raw bytes (no recursion)."""
    limit = len(buf) if limit is None else limit
    while pos < limit:
        tag, pos = _varint(buf, pos, limit)
        field, wire = tag >> 3, tag & 7
        if wire == 0:
            value, pos = _varint(buf, pos, limit)
        elif wire == 1:
            if pos + 8 > limit:
                raise ValueError("truncated fixed64")
            value = struct.unpack_from("<Q", buf, pos)[0]
            pos += 8
        elif wire == 2:
            ln, pos = _varint(buf, pos, limit)
            if pos + ln > limit:
                raise ValueError("truncated bytes field")
            value = bytes(buf[pos:pos + ln])
            pos += ln
        elif wire == 5:
            if pos + 4 > limit:
                raise ValueError("truncated fixed32")
            value = struct.unpack_from("<I", buf, pos)[0]
            pos += 4
        else:
            raise ValueError("wire type %d not supported" % wire)
        yield field, wire, value


def _parse_chunk(buf):
    c = {"sha": None, "crc": None, "offset": None, "cb_original": None,
         "cb_compressed": None}
    for field, wire, value in _fields(buf):
        if field == 1 and wire == 2:
            if len(value) != 20:
                raise ValueError("chunk sha not 20B")
            c["sha"] = value
        elif field == 2 and wire == 5:
            c["crc"] = value
        elif field == 3 and wire == 0:
            c["offset"] = value
        elif field == 4 and wire == 0:
            c["cb_original"] = value
        elif field == 5 and wire == 0:
            c["cb_compressed"] = value
    if c["sha"] is None or None in (c["offset"], c["cb_original"],
                                    c["cb_compressed"], c["crc"]):
        raise ValueError("incomplete chunk")
    return c


def _parse_file(buf):
    e = {"name": None, "size": None, "flags": 0, "sha_content": None,
         "chunks": [], "linktarget": None}
    for field, wire, value in _fields(buf):
        if field == 1 and wire == 2:
            e["name"] = value.decode("utf-8", "replace")
        elif field == 2 and wire == 0:
            e["size"] = value
        elif field == 3 and wire == 0:
            e["flags"] = value
        elif field == 5 and wire == 2:
            e["sha_content"] = value
        elif field == 6 and wire == 2:
            e["chunks"].append(_parse_chunk(value))
        elif field == 7 and wire == 2:
            e["linktarget"] = value.decode("utf-8", "replace")
    if e["name"] is None or e["size"] is None:
        raise ValueError("incomplete file mapping")
    return e


def parse_metadata(payload):
    meta = {}
    for field, wire, value in _fields(payload):
        if wire != 0:
            continue
        if field == 1:
            meta["depot"] = value
        elif field == 2:
            meta["gid"] = value
        elif field == 3:
            meta["creation_time"] = value
        elif field == 4:
            meta["filenames_encrypted"] = bool(value)
    return meta


def parse_manifest_bytes(data: bytes):
    """{'depot','gid','creation_time','filenames_encrypted','files','size'} from bytes."""
    payload = None
    meta = {}
    for magic, body in split_sections(data):
        if magic == PAYLOAD_MAGIC:
            payload = body
        elif magic == METADATA_MAGIC:
            meta = parse_metadata(body)
    if payload is None:
        raise ValueError("missing payload section")
    if "depot" not in meta or "gid" not in meta:
        raise ValueError("missing manifest metadata")
    if meta.get("filenames_encrypted"):
        raise ValueError("encrypted filenames (requires AES step)")
    files = [m for field, wire, value in _fields(payload)
             if field == 1 and wire == 2
             for m in [_parse_file(value)]]
    if not files:
        raise ValueError("payload without file mapping")
    return {"depot": meta["depot"], "gid": meta["gid"],
            "creation_time": meta.get("creation_time"),
            "filenames_encrypted": False, "files": files, "size": len(data)}


def parse_manifest(path):
    """{'depot','gid','creation_time','filenames_encrypted','files','size'}."""
    with open(path, "rb") as f:
        data = f.read()
    return parse_manifest_bytes(data)


def adler0(data):
    """Steam Adler32 (seed s1=0, s2=0; zlib starts at s1=1)."""
    import zlib
    n = len(data)
    a = zlib.adler32(bytes(data))
    base = 65521
    return (((((a >> 16) & 0xFFFF) - n) % base) << 16) | (((a & 0xFFFF) - 1) % base)


def decrypt_chunk(cipher, key):
    """iv=AES256-ECB(cipher[:16]); plain=AES256-CBC+PKCS7(cipher[16:])."""
    if len(key) != 32:
        raise ValueError("32B depot key required")
    if len(cipher) < 32 or len(cipher) % 16:
        raise ValueError("invalid cipher length")
    try:
        from Crypto.Cipher import AES
    except ImportError as e:
        raise ValueError("missing pycryptodome: %s" % e)
    iv = AES.new(key, AES.MODE_ECB).decrypt(cipher[:16])
    plain = AES.new(key, AES.MODE_CBC, iv).decrypt(cipher[16:])
    pad = plain[-1]
    if pad < 1 or pad > 16 or plain[-pad:] != bytes([pad]) * pad:
        raise ValueError("invalid PKCS7 padding")
    return plain[:-pad]


def decompress_chunk(plain):
    """Dispatch per magic -> uncompressed bytes (with verification where specified)."""
    if plain[:4] == b"VSZa":
        try:
            import zstandard
        except ImportError as e:
            raise ValueError("missing zstandard: %s" % e)
        import struct as _s
        if len(plain) < 8 + 11 or plain[-3:] != b"zsv":
            raise ValueError("malformed VSZa chunk")
        _, outsize = _s.unpack_from("<Ii", plain, len(plain) - 11)
        if outsize < 0:
            raise ValueError("negative VSZa size")
        data = zstandard.ZstdDecompressor().decompress(plain[8:-11])
        if outsize and len(data) != outsize:
            raise ValueError("VSZa length %d != %d" % (len(data), outsize))
        return data
    if plain[:2] == b"VZ" and len(plain) > 3 and plain[2:3] == b"a":
        # VZip: raw LZMA1 stream without end marker; flush padding decodes
        # an extra phantom byte -> truncate to footer size, CRC32 is authoritative.
        import lzma as _lzma
        import struct as _s
        import zlib as _z
        if len(plain) < 7 + 5 + 10:
            raise ValueError("VZa chunk too short")
        if _s.unpack_from("<H", plain, len(plain) - 2)[0] != 0x767A:
            raise ValueError("missing VZa footer")
        outcrc, outsize = _s.unpack_from("<Ii", plain, len(plain) - 10)
        if outsize < 0:
            raise ValueError("negative VZa size")
        props = plain[7:12]
        p = props[0]
        dec = _lzma.LZMADecompressor(
            format=_lzma.FORMAT_RAW, filters=[{
                "id": _lzma.FILTER_LZMA1,
                "dict_size": max(1 << 12, int.from_bytes(props[1:5], "little")),
                "lc": p % 9, "lp": (p // 9) % 5, "pb": p // 45}])
        try:
            data = dec.decompress(plain[12:-10])
        except _lzma.LZMAError as e:
            raise ValueError("VZa decompression error: %s" % e)
        if outsize:
            if len(data) < outsize:
                raise ValueError("short VZa output %d < %d" % (len(data), outsize))
            data = data[:outsize]
        elif len(data) > 1 and (_z.crc32(data) & 0xFFFFFFFF) != (
                outcrc & 0xFFFFFFFF):
            # Without size, flush padding can evaluate to an extra byte:
            # strip only if CRC matches (never blindly).
            if (_z.crc32(data[:-1]) & 0xFFFFFFFF) == (outcrc & 0xFFFFFFFF):
                data = data[:-1]
        if (_z.crc32(data) & 0xFFFFFFFF) != (outcrc & 0xFFFFFFFF):
            raise ValueError("invalid VZa CRC32")
        return data
    if plain[:4] == b"PK\x03\x04":
        import io
        import zipfile
        with zipfile.ZipFile(io.BytesIO(plain)) as zf:
            names = zf.namelist()
            if len(names) != 1:
                raise ValueError("multi-entry ZIP chunk")
            return zf.read(names[0])
    raise ValueError("unknown chunk magic %s" % plain[:4].hex())

