"""Minimal read-only reader for legacy Excel files (.xls, BIFF8 in an OLE2 container).

Only what the SAT's monthly reports need: the first worksheet as rows of text and numbers. No macros, no formulas
evaluated, no external links, no writing. Anything unexpected raises ValueError so the caller can skip the file.
"""

import struct

MAGIC = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
END = 0xFFFFFFFA  # sector ids at or above this are markers, not sectors
MAX_BYTES = 8 * 1024 * 1024
MAX_CELLS = 400_000


def _stream(data):
    """The 'Workbook' (or 'Book') stream of an OLE2 file."""
    if data[:8] != MAGIC:
        raise ValueError('not an OLE2 file')
    ssz = 1 << struct.unpack_from('<H', data, 0x1E)[0]
    msz = 1 << struct.unpack_from('<H', data, 0x20)[0]
    nfat = struct.unpack_from('<I', data, 0x2C)[0]
    dir_start = struct.unpack_from('<I', data, 0x30)[0]
    cutoff = struct.unpack_from('<I', data, 0x38)[0]
    minifat_start = struct.unpack_from('<I', data, 0x3C)[0]
    difat_start = struct.unpack_from('<I', data, 0x44)[0]
    ndifat = struct.unpack_from('<I', data, 0x48)[0]

    def sector(sid):
        start = (sid + 1) * ssz
        chunk = data[start : start + ssz]
        if len(chunk) != ssz:
            raise ValueError('truncated sector')
        return chunk

    difat = list(struct.unpack_from('<109I', data, 0x4C))
    sid = difat_start
    for _ in range(min(ndifat, 64)):
        if sid >= END:
            break
        values = struct.unpack('<%dI' % (ssz // 4), sector(sid))
        difat.extend(values[:-1])
        sid = values[-1]
    fat = []
    for sid in difat[:nfat]:
        if sid < END:
            fat.extend(struct.unpack('<%dI' % (ssz // 4), sector(sid)))

    def chain(start, table):
        out, sid = [], start
        while sid < END:
            out.append(sid)
            if len(out) > len(table) + 1 or sid >= len(table):
                raise ValueError('broken sector chain')
            sid = table[sid]
        return out

    def read(start):
        return b''.join(sector(s) for s in chain(start, fat))

    directory = read(dir_start)
    entries = []
    for n in range(len(directory) // 128):
        raw = directory[n * 128 : (n + 1) * 128]
        name_len = struct.unpack_from('<H', raw, 64)[0]
        name = raw[: max(name_len - 2, 0)].decode('utf-16le', errors='ignore')
        entries.append((name, raw[66], struct.unpack_from('<I', raw, 116)[0], struct.unpack_from('<I', raw, 120)[0]))
    target = next((e for e in entries if e[1] == 2 and e[0] in ('Workbook', 'Book')), None)
    if target is None:
        raise ValueError('no workbook stream')
    _, _, start, size = target
    if size >= cutoff:
        return read(start)[:size]
    root = entries[0]  # small streams live in the mini stream
    mini = read(root[2])[: root[3]]
    raw_fat = read(minifat_start)
    mini_fat = struct.unpack('<%dI' % (len(raw_fat) // 4), raw_fat)
    return b''.join(mini[s * msz : (s + 1) * msz] for s in chain(start, mini_fat))[:size]


class _Chunks:
    """Cursor over the chunks of a shared-string table (an SST record plus its CONTINUE records)."""

    def __init__(self, chunks):
        self.chunks, self.index, self.pos = chunks, 0, 0

    def _advance(self):
        self.index += 1
        self.pos = 0
        if self.index >= len(self.chunks):
            raise ValueError('shared strings end early')

    def take(self, count):
        chunk = self.chunks[self.index]
        if self.pos + count > len(chunk):
            self._advance()
            chunk = self.chunks[self.index]
        out = chunk[self.pos : self.pos + count]
        self.pos += count
        return out

    def skip(self, count):
        while count > 0:
            available = len(self.chunks[self.index]) - self.pos
            if available == 0:
                self._advance()
                continue
            step = min(available, count)
            self.pos += step
            count -= step

    def characters(self, count, wide):
        out = []
        while count > 0:
            chunk = self.chunks[self.index]
            width = 2 if wide else 1
            fit = min(count, (len(chunk) - self.pos) // width)
            raw = chunk[self.pos : self.pos + fit * width]
            out.append(raw.decode('utf-16le' if wide else 'latin-1', errors='replace'))
            self.pos += fit * width
            count -= fit
            if count > 0:  # the string continues in the next record, which starts with a new encoding flag
                self._advance()
                wide = bool(self.chunks[self.index][0] & 1)
                self.pos = 1
        return ''.join(out)


def _shared_strings(chunks):
    cursor = _Chunks(chunks)
    cursor.pos = 8  # total and unique counts
    unique = struct.unpack_from('<I', chunks[0], 4)[0]
    strings = []
    for _ in range(min(unique, MAX_CELLS)):
        try:
            length = struct.unpack('<H', cursor.take(2))[0]
            flags = cursor.take(1)[0]
        except (ValueError, struct.error, IndexError):
            break
        runs = struct.unpack('<H', cursor.take(2))[0] if flags & 8 else 0
        extra = struct.unpack('<I', cursor.take(4))[0] if flags & 4 else 0
        strings.append(cursor.characters(length, bool(flags & 1)))
        cursor.skip(runs * 4 + extra)
    return strings


def _rk(value):
    if value & 2:
        number = float(struct.unpack('<i', struct.pack('<I', value))[0] >> 2)
    else:
        number = struct.unpack('<d', struct.pack('<Q', (value & 0xFFFFFFFC) << 32))[0]
    return number / 100 if value & 1 else number


def read_rows(data):
    """First worksheet of an .xls file as a list of rows (text, numbers or None). ValueError if unsupported."""
    if len(data) > MAX_BYTES:
        raise ValueError('file too large')
    try:
        return _read_rows(data)
    except (struct.error, IndexError, OverflowError, UnicodeError) as exc:
        raise ValueError('corrupt or unsupported .xls') from exc


def _read_rows(data):
    stream = _stream(data)
    records, pos = [], 0
    while pos + 4 <= len(stream):
        rid, length = struct.unpack_from('<HH', stream, pos)
        records.append((rid, stream[pos + 4 : pos + 4 + length]))
        pos += 4 + length
    strings, cells, sheet, bofs = [], {}, False, 0
    i = 0
    while i < len(records):
        rid, body = records[i]
        if rid == 0x0809:  # BOF: globals first, then each sheet
            bofs += 1
            sheet = bofs == 2 and struct.unpack_from('<H', body, 2)[0] == 0x0010
        elif rid == 0x000A and sheet:
            break
        elif rid == 0x00FC:
            chunks = [body]
            while i + 1 < len(records) and records[i + 1][0] == 0x003C:
                i += 1
                chunks.append(records[i][1])
            strings = _shared_strings(chunks)
        elif sheet:
            if rid == 0x00FD:
                row, col, _, index = struct.unpack_from('<HHHI', body)
                cells[(row, col)] = strings[index] if index < len(strings) else None
            elif rid == 0x0204:
                row, col, _, length = struct.unpack_from('<HHHH', body)
                wide = bool(body[8] & 1)
                cells[(row, col)] = body[9 : 9 + length * (2 if wide else 1)].decode(
                    'utf-16le' if wide else 'latin-1', errors='replace'
                )
            elif rid == 0x0203:
                row, col, _, number = struct.unpack_from('<HHHd', body)
                cells[(row, col)] = number
            elif rid == 0x027E:
                row, col, _, value = struct.unpack_from('<HHHI', body)
                cells[(row, col)] = _rk(value)
            elif rid == 0x00BD:
                row, first = struct.unpack_from('<HH', body)
                for n in range((len(body) - 6) // 6):
                    cells[(row, first + n)] = _rk(struct.unpack_from('<I', body, 4 + n * 6 + 2)[0])
        if len(cells) > MAX_CELLS:
            raise ValueError('too many cells')
        i += 1
    if not cells:
        return []
    width = max(col for _, col in cells) + 1
    return [[cells.get((r, c)) for c in range(width)] for r in range(max(row for row, _ in cells) + 1)]
