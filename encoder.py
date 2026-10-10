"""
Pure-Python implementation of the HeroQuest (DOS) compression format.

This module replaces the external ``enc.exe`` / ``dec.exe`` tools. It is a
direct port of the original C++ sources (``enc.cpp`` / ``dec.cpp``) and
produces output that is byte-for-byte identical to them.

Public API
----------
    compress(data: bytes) -> bytes
    decompress(data: bytes, max_len: int = 0xFFFF) -> bytes

Stream format
-------------
Every token starts with a control byte:

    00000000                    end of stream (EOF)
    000LLLLL                    literal span, L bytes follow          (L = 1..31)
    001LLLLL LLLLLLLL           literal span, (L<<8 | next) + 32 bytes follow
    010LLLLL xxxxxxxx           run of byte x, L + 3 times            (3..34, the
                                encoder only uses 3..18)
    011LLLLL LLLLLLLL xxxxxxxx  run of byte x, (L<<8 | next) + 36 times
    10LDDDDD                    short match: length 2 (L=0) or 3 (L=1),
                                D = distance to the END of the match
    11LLLLDD DDDDDDDD           long match: length L + 4 (4..19),
                                D = 10-bit distance to the END of the match

"Distance to the end of the match" means that the source of a copy starts at
``len(out) - (D + length)``: matches never overlap the bytes being written.

Note on ``max_len``: the original decoder runs with a 16-bit counter
(``0xFFFF``) and therefore stops after 65535 output bytes. The same limit is
kept by default for compatibility with ``dec.exe``.
"""

from bisect import bisect_left

# ── Encoder parameters (same as enc.cpp) ───────────────────────────────────────
_MAX_MATCH = 15 + 4          # longest match / run the encoder looks at
_WINDOW = 1 << 10            # how far back matches are searched (10-bit distance)
_LITRUN_MAX = (1 << 13) - 1  # a literal span is flushed when it grows past this


# ══════════════════════════════════════════════════════════════════════════════
#  DECOMPRESSION
# ══════════════════════════════════════════════════════════════════════════════
def decompress(data: bytes, max_len: int = 0xFFFF) -> bytes:
    """Decompress a HeroQuest stream (port of ``dec.cpp``).

    Decoding stops at the EOF token, at the end of the input, or when
    ``max_len`` bytes have been produced (whichever comes first).
    Raises ``ValueError`` if a match points before the start of the output.
    """
    data = bytes(data)
    n = len(data)
    out = bytearray()
    i = 0
    remaining = max_len

    while remaining > 0:
        if i >= n:                      # input exhausted without an EOF token
            break
        b = data[i]
        i += 1
        if b == 0x00:                   # EOF
            break

        if b & 0x80:
            if b & 0x40:
                # 11LLLLDD DDDDDDDD -- long match
                if i >= n:
                    break
                length = ((b >> 2) & 0x0F) + 4
                dist = ((b & 0x03) << 8) | data[i]
                i += 1
            else:
                # 10LDDDDD -- short match
                length = 3 if (b & 0x20) else 2
                dist = b & 0x1F
            src = len(out) - (dist + length)
            if src < 0:
                raise ValueError("Corrupt compressed data: invalid match distance")
            length = min(length, remaining)
            out += out[src:src + length]
            remaining -= length

        elif b & 0x40:
            # 010LLLLL x / 011LLLLL LLLLLLLL x -- run of a single byte
            if b & 0x20:
                if i >= n:
                    break
                count = (((b & 0x1F) << 8) | data[i]) + 36
                i += 1
            else:
                count = (b & 0x1F) + 3
            if i >= n:
                break
            value = data[i]
            i += 1
            count = min(count, remaining)
            out += bytes((value,)) * count
            remaining -= count

        else:
            # 000LLLLL / 001LLLLL LLLLLLLL -- literal span
            if b & 0x20:
                if i >= n:
                    break
                count = (((b & 0x1F) << 8) | data[i]) + 32
                i += 1
            else:
                count = b & 0x1F
            count = min(count, remaining, n - i)   # tolerate truncated input
            out += data[i:i + count]
            i += count
            remaining -= count

    return bytes(out)


# ══════════════════════════════════════════════════════════════════════════════
#  COMPRESSION
# ══════════════════════════════════════════════════════════════════════════════
def compress(data: bytes) -> bytes:
    """Compress ``data`` into a HeroQuest stream (port of ``enc.cpp``).

    The output is identical to the one produced by the original ``enc.exe``.
    """
    inp = bytes(data)
    size = len(inp)
    out = bytearray()

    # Positions of every 2-byte sequence seen so far (ascending). A previous
    # position can only be a useful match candidate if its first two bytes
    # equal the current ones, so we never need to scan the whole window.
    index = {}
    indexed = 0                         # positions < indexed are already in `index`

    pos = 0
    litrun = 0

    def flush_litrun():
        nonlocal litrun
        if litrun < 32:
            out.append(litrun & 0x1F)
        else:
            out.append(0x20 + (((litrun - 32) >> 8) & 0x1F))
            out.append((litrun - 32) & 0xFF)
        out.extend(inp[pos - litrun:pos])
        litrun = 0

    while pos < size:
        # Make every position before `pos` available for lookups.
        while indexed < pos:
            if indexed + 1 < size:
                key = (inp[indexed] << 8) | inp[indexed + 1]
                index.setdefault(key, []).append(indexed)
            indexed += 1

        l = min(size - pos, _MAX_MATCH)

        # ── run of identical bytes starting here ───────────────────────────────
        rleval = inp[pos]
        r = 1
        while r < l and inp[pos + r] == rleval:
            r += 1
        rlelen = r if r >= 3 else 0

        # ── best match inside the window ───────────────────────────────────────
        # The original scans the window from the oldest to the newest position
        # and lets later positions win ties. Scanning from the newest to the
        # oldest (first hit wins) gives the same result and allows an early
        # exit as soon as nothing can improve any more.
        ml = 0      # best match length
        mj = 0      # best match position
        m1l = 0     # short-match (10LDDDDD) length
        m1d = 0     # short-match distance

        if l >= 2:
            candidates = index.get((inp[pos] << 8) | inp[pos + 1])
            if candidates:
                start = bisect_left(candidates, max(0, pos - _WINDOW))
                target = inp[pos:pos + l]
                m3d = 0         # newest position with a 3-byte short match
                m2d = 0         # newest position with a 2-byte short match
                for ci in range(len(candidates) - 1, start - 1, -1):
                    j = candidates[ci]
                    dist = pos - j
                    if dist > 34 and ml >= l:
                        break               # nothing left that can win

                    # raw common prefix length (limited to l)
                    if inp[j:j + l] == target:
                        r = l
                    else:
                        r = 2
                        while inp[pos + r] == inp[j + r]:
                            r += 1

                    if dist <= 34:
                        if not m3d and r >= 3:
                            m3d = dist
                        elif not m2d and r >= 2 and dist <= 33:
                            m2d = dist

                    if dist - r < 1:            # match would overlap the new data
                        r = dist
                        if r < 4:
                            r = 0
                    if r > ml:
                        ml, mj = r, j

                if m3d:
                    m1l, m1d = 3, m3d
                elif m2d:
                    m1l, m1d = 2, m2d

        # ── choose the token ───────────────────────────────────────────────────
        if 18 < rlelen < 36:
            rlelen = 18
        if rlelen > 8227:
            rlelen = 8227

        if rlelen >= 3 and rlelen >= ml:
            # run of a single byte
            if litrun > 0:
                flush_litrun()
            if rlelen <= 18:
                out.append(0x40 + (rlelen - 3))
            else:                                   # (never reached: runs are <= 19)
                out.append(0x60 + ((rlelen - 36) >> 8))
                out.append((rlelen - 36) & 0xFF)
            out.append(rleval)
            pos += rlelen
            continue

        if ml < 4 or mj + ml > pos:
            if m1l > 0 and m1d >= m1l and m1d - m1l < 32:
                # 10LDDDDD -- short match
                if litrun > 0:
                    flush_litrun()
                out.append((0x80 if m1l == 2 else 0xA0) + m1d - m1l)
                pos += m1l
            else:
                # literal byte
                pos += 1
                litrun += 1
                if litrun > _LITRUN_MAX:
                    flush_litrun()
        else:
            # 11LLLLDD DDDDDDDD -- long match
            if litrun > 0:
                flush_litrun()
            dist = (pos - mj) - ml
            out.append(0xC0 + (ml - 4) * 4 + (dist >> 8))
            out.append(dist & 0xFF)
            pos += ml

    if litrun > 0:
        flush_litrun()
    out.append(0x00)                                # EOF
    return bytes(out)
