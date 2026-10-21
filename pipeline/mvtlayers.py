"""Byte-level helpers to split/rebuild a Mapbox Vector Tile by layer (no geometry re-encoding)."""
def _varint(b, i):
    r = s = 0
    while True:
        c = b[i]; i += 1
        r |= (c & 0x7F) << s
        if not c & 0x80:
            return r, i
        s += 7

def _enc_varint(n):
    out = bytearray()
    while True:
        c = n & 0x7F; n >>= 7
        if n: out.append(c | 0x80)
        else:
            out.append(c); return bytes(out)

def split_layers(tile):
    """-> list of (layer_name, raw_layer_message_bytes)"""
    i, out = 0, []
    while i < len(tile):
        key, i = _varint(tile, i)
        field, wt = key >> 3, key & 7
        assert wt == 2, wt
        ln, i = _varint(tile, i)
        msg = tile[i:i + ln]; i += ln
        if field == 3:
            # layer name = field 1 (string) inside layer message
            j, name = 0, None
            while j < len(msg):
                k2, j = _varint(msg, j)
                f2, w2 = k2 >> 3, k2 & 7
                if w2 == 2:
                    l2, j = _varint(msg, j)
                    if f2 == 1:
                        name = msg[j:j + l2].decode(); break
                    j += l2
                elif w2 == 0:
                    _, j = _varint(msg, j)
                elif w2 == 5: j += 4
                elif w2 == 1: j += 8
            out.append((name, msg))
    return out

def join_layers(layers):
    return b''.join(b'\x1a' + _enc_varint(len(m)) + m for _, m in layers)
