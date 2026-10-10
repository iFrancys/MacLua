"""Reader/writer minimale per il VDF binario di Steam.

Tipi: 0x00 sezione, 0x01 stringa, 0x02 int32, 0x07 int64. Qualsiasi altro
tipo fallisce esplicito: meglio un errore che un file riscritto male.
"""
import struct

__all__ = ["Reader", "parse_node", "ser_node"]

_KNOWN = (0x00, 0x01, 0x02, 0x07)


class Reader:
    __slots__ = ("d", "o")

    def __init__(self, d, o=0):
        self.d = d
        self.o = o

    def u8(self):
        b = self.d[self.o:self.o + 1]
        if not b:
            raise EOFError("u8 oltre la fine")
        self.o += 1
        return b[0]

    def cstr(self):
        end = self.d.find(b"\x00", self.o)
        if end < 0:
            raise EOFError("stringa non terminata")
        s = self.d[self.o:end].decode("utf-8", "replace")
        self.o = end + 1
        return s

    def take(self, n):
        if self.o + n > len(self.d):
            raise EOFError("payload oltre la fine")
        b = self.d[self.o:self.o + n]
        self.o += n
        return b


def parse_node(r):
    """Un nodo; ('end',) sul terminatore 0x08."""
    t = r.u8()
    if t == 0x08:
        return ("end",)
    if t not in _KNOWN:
        raise ValueError("tipo VDF non supportato 0x%02x a off 0x%x" % (t, r.o - 1))
    key = r.cstr()
    if t == 0x00:
        kids = []
        while True:
            n = parse_node(r)
            if n[0] == "end":
                return ("sec", key, kids)
            kids.append(n)
    if t == 0x01:
        return ("str", key, r.cstr())
    if t == 0x02:
        return ("i32", key, struct.unpack("<i", r.take(4))[0])
    return ("i64", key, struct.unpack("<q", r.take(8))[0])


def _cstr(buf, s):
    buf += s.encode("utf-8")
    buf.append(0x00)


def ser_node(n, buf):
    """Accoda la codifica di n a buf (bytearray). Senza 0x08 finale."""
    tag = n[0]
    if tag == "sec":
        buf.append(0x00)
        _cstr(buf, n[1])
        for child in n[2]:
            ser_node(child, buf)
        buf.append(0x08)
    elif tag == "str":
        buf.append(0x01)
        _cstr(buf, n[1])
        _cstr(buf, n[2])
    elif tag == "i32":
        buf.append(0x02)
        _cstr(buf, n[1])
        buf += struct.pack("<i", n[2])
    elif tag == "i64":
        buf.append(0x07)
        _cstr(buf, n[1])
        buf += struct.pack("<q", n[2])
    else:
        raise ValueError("nodo VDF sconosciuto: %r" % (tag,))
    return buf
