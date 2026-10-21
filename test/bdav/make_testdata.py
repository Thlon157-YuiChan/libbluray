#!/usr/bin/env python3
"""Generate synthetic BDAV / BDMV test trees for libbluray.

Creates a small but structurally valid MPEG-2 transport stream (192 byte
M2TS) containing a PAT, a PMT and one MPEG-2 video elementary stream with
I-picture GOPs, plus a deliberate PCR discontinuity so that the clip has
two STC sequences.

The stream is then wrapped into two disc trees:

  <out>/BDAV/     BD-RE Part 3 (BDAV) format: info.bdav, PLAYLIST/*.rpls,
                  CLIPINF/*.clpi (M2TS0100), STREAM/*.m2ts
  <out>/BDMV/     BDMV format: PLAYLIST/*.mpls, CLIPINF/*.clpi (HDMV0100),
                  STREAM/*.m2ts

Both trees carry the same content, so libbluray can be exercised on the
BDMV code path (regression) and on the BDAV code path (new) with the
same data.

The BDAV metadata is byte-compatible with the reference implementation
<https://github.com/sorshi/bdav> (its writer was validated against
chotBDAV.exe), so the generated files can also be diffed against
sorshi/bdav's tools/bdav_dump.py output.

Usage:
    make_testdata.py <output-dir>
"""

import sys
from pathlib import Path

# --- transport stream parameters -------------------------------------------

PMT_PID = 0x1000
VIDEO_PID = 0x0100
PCR_PID = VIDEO_PID
SERVICE_ID = 1
TSID = 1

PACKETS_PER_GOP = 100
PCR_STEP = 27000          # 27 MHz units per TS packet -> 1000 packets/s
DISCONTINUITY_AT = 1000   # packet index of the PCR jump
TOTAL_PACKETS = 2000

TS_RECORDING_RATE = 0x386666


def be(value: int, size: int) -> bytes:
    return value.to_bytes(size, "big")


def encode_pts(pts: int) -> bytes:
    b = bytearray(5)
    b[0] = 0x21 | ((pts >> 29) & 0x0E)
    b[1] = (pts >> 22) & 0xFF
    b[2] = (((pts >> 15) & 0x7F) << 1) | 1
    b[3] = (pts >> 7) & 0xFF
    b[4] = ((pts & 0x7F) << 1) | 1
    return bytes(b)


def encode_pcr(base: int, ext: int = 0) -> bytes:
    b = bytearray(6)
    b[0] = (base >> 25) & 0xFF
    b[1] = (base >> 17) & 0xFF
    b[2] = (base >> 9) & 0xFF
    b[3] = (base >> 1) & 0xFF
    b[4] = ((base & 0x01) << 7) | 0x7E | ((ext >> 1) & 0x01)
    b[5] = ((ext & 0x01) << 7)
    return bytes(b)


def crc32_mpeg(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte << 24
        for _ in range(8):
            if crc & 0x80000000:
                crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF
            else:
                crc = (crc << 1) & 0xFFFFFFFF
    return crc


def build_pat() -> bytes:
    body = bytearray()
    body += bytes([0x00, 0xB0, 0x0D])
    body += bytes([TSID >> 8 & 0xFF, TSID & 0xFF])
    body += bytes([0xC1, 0x00, 0x00])
    body += bytes([0x00, SERVICE_ID])
    body += bytes([0xE0 | (PMT_PID >> 8), PMT_PID & 0xFF])
    crc = crc32_mpeg(bytes(body))
    return bytes(body) + be(crc, 4)


def build_pmt() -> bytes:
    body = bytearray()
    body += bytes([0x02, 0xB0, 0x12])
    body += bytes([SERVICE_ID >> 8 & 0xFF, SERVICE_ID & 0xFF])
    body += bytes([0xC1, 0x00, 0x00])
    body += bytes([0xE0 | (PCR_PID >> 8), PCR_PID & 0xFF])
    body += bytes([0xF0, 0x00])
    body += bytes([0x02, 0xE0 | (VIDEO_PID >> 8), VIDEO_PID & 0xFF, 0xF0, 0x00])
    crc = crc32_mpeg(bytes(body))
    return bytes(body) + be(crc, 4)


def mpeg2_sequence_header() -> bytes:
    # 1920x1080, 16:9, 25fps
    return bytes([0x00, 0x00, 0x01, 0xB3, 0x78, 0x04, 0x38, 0x33, 0xFF, 0xFF, 0xFF, 0x00])


def mpeg2_gop_header(gop: int) -> bytes:
    tc = (gop * 12) & 0x1FFFFFF
    return bytes([0x00, 0x00, 0x01, 0xB8,
                  (tc >> 17) & 0xFF, (tc >> 9) & 0xFF, (tc >> 1) & 0xFF,
                  ((tc & 0x01) << 7) | 0x80])


def mpeg2_picture_header(tr: int) -> bytes:
    b = bytearray([0x00, 0x00, 0x01, 0x00])
    b.append((tr >> 2) & 0xFF)
    b.append(((tr & 0x03) << 6) | (1 << 3))     # picture_coding_type = 1 (I)
    b += bytes([0x00, 0x00, 0x00, 0x00])
    return bytes(b)


def build_video_pes(gop: int, pts90: int) -> bytes:
    es = bytearray()
    es += mpeg2_sequence_header()
    es += mpeg2_gop_header(gop)
    es += mpeg2_picture_header(gop % 2)
    es += bytes([0x00, 0x00, 0x01, 0x01, 0x00, 0x00, 0x00])
    es += bytes(64)
    pes = bytearray()
    pes += bytes([0x00, 0x00, 0x01, 0xE0, 0x00, 0x00, 0x80, 0x80, 0x05])
    pes += encode_pts(pts90)
    pes += es
    pes[4] = (len(pes) - 6) >> 8 & 0xFF
    pes[5] = (len(pes) - 6) & 0xFF
    return bytes(pes)


def ts_packet(pid: int, pusi: bool, payload: bytes, continuity: int,
              pcr: int | None = None, discontinuity: bool = False) -> bytes:
    body = bytearray()
    body.append(0x47)
    body.append((0x40 if pusi else 0x00) | ((pid >> 8) & 0x1F))
    body.append(pid & 0xFF)
    if pcr is not None:
        flags = 0x10 | (0x80 if discontinuity else 0x00)
        af = bytes([flags]) + encode_pcr(pcr)
        body.append(0x30 | (continuity & 0x0F))
        body.append(len(af))
        body += af
        room = 188 - 5 - len(af)
    else:
        body.append(0x10 | (continuity & 0x0F))
        room = 184
    body += payload[:room]
    body += bytes(max(0, room - len(payload)))
    assert len(body) == 188
    return bytes(body)


def make_m2ts() -> bytes:
    pat = build_pat()
    pmt = build_pmt()

    packets: list[bytes] = []
    pcr = 27_000_000
    cont = {0x0000: 0, PMT_PID: 0, VIDEO_PID: 0}

    def emit(pid, pusi, payload, pcrv=None, disc=False):
        packets.append(ts_packet(pid, pusi, payload, cont[pid], pcr=pcrv, discontinuity=disc))
        cont[pid] = (cont[pid] + 1) & 0x0F

    for spn in range(TOTAL_PACKETS):
        if spn == 0:
            emit(0x0000, True, bytes([0x00]) + pat)
        if spn == DISCONTINUITY_AT - 1:
            emit(0x0000, True, bytes([0x00]) + pat)

        if spn % PACKETS_PER_GOP == 0:
            gop = spn // PACKETS_PER_GOP
            pts90 = gop * (90000 * PACKETS_PER_GOP) // 1000
            if spn >= DISCONTINUITY_AT:
                pts90 += 90000      # 1 s jump together with the PCR
            pes = build_video_pes(gop, pts90)
            if spn == 0:
                emit(PMT_PID, True, bytes([0x00]) + pmt)
            off = 0
            first = True
            while off < len(pes):
                emit(VIDEO_PID, first, pes[off:off + 184],
                     pcrv=pcr if first else None,
                     disc=(spn == DISCONTINUITY_AT and first))
                off += 184
                first = False
        else:
            emit(VIDEO_PID, False, b"", pcrv=pcr)

        pcr += PCR_STEP
        if spn == DISCONTINUITY_AT:
            pcr += 27_000_000   # 1 s PCR jump

    # pad with null packets to a 6144 byte boundary (32 source packets)
    while len(packets) % 32:
        emit(VIDEO_PID, False, b"")

    out = bytearray()
    for i, pkt in enumerate(packets):
        ats = (i * 300) & 0x3FFFFFFF
        out += be(ats, 4)
        out += pkt
    return bytes(out)


# --- disc metadata ---------------------------------------------------------

class Analysis:
    """Minimal subset of the analysis results needed to write the metadata."""

    def __init__(self):
        self.packet_count = 0
        self.transport_stream_id = TSID
        self.service_id = SERVICE_ID
        self.pmt_pid = PMT_PID
        self.video_pid = VIDEO_PID
        self.video_stream_type = 0x02
        self.stc_sequences = []   # (spn_start, pcr_pid, start_45k, end_45k)
        self.eps = []             # (spn, pts90)


def analyze(m2ts: bytes) -> Analysis:
    """Very small subset of sorshi/bdav's tsparse.analyze_m2ts()."""
    a = Analysis()
    a.packet_count = len(m2ts) // 192

    pcr = 27_000_000
    spn = 0
    gop = 0
    pts90 = 0
    stc_start_spn = 0
    stc_start_pts = 0
    first_pat = True

    while spn < a.packet_count:
        pkt = m2ts[spn * 192 + 4:spn * 192 + 192]
        pid = (pkt[1] & 0x1F) << 8 | pkt[2]
        pusi = bool(pkt[1] & 0x40)
        afc = (pkt[3] >> 4) & 0x3
        payload_off = 4
        if afc & 0x2:
            aflen = pkt[4]
            if aflen >= 7 and pkt[5] & 0x10 and pid == PCR_PID:
                base = pkt[6] << 25 | pkt[7] << 17 | pkt[8] << 9 | pkt[9] << 1 | pkt[10] >> 7
                if base > pcr + 90000 and a.stc_sequences:
                    # PCR discontinuity: new STC sequence
                    a.stc_sequences.append((stc_start_spn, PCR_PID, stc_start_pts, pts90 // 2))
                    stc_start_spn = spn
                    stc_start_pts = pts90
                pcr = base
            payload_off = 5 + pkt[4]
        if pid == VIDEO_PID and pusi and (afc & 0x1) and payload_off < 188:
            payload = pkt[payload_off:188]
            if payload[0:3] == b"\x00\x00\x01" and payload[7] & 0x80:
                p = payload[9:14]
                pts = ((p[0] >> 1) & 0x07) << 30 | p[1] << 22 | (p[2] >> 1) << 15 | p[3] << 7 | p[4] >> 1
                if a.eps:
                    a.eps.append((spn, pts))
                else:
                    a.eps.append((spn, pts))
                    stc_start_pts = pts
                    stc_start_spn = 0
                pts90 = pts
            gop += 1
        elif pid == VIDEO_PID and not pusi:
            pass
        if spn % PACKETS_PER_GOP == 0:
            # next GOP starts 100 packets later
            pass
        spn += 1
        if spn % PACKETS_PER_GOP == 0 and spn < a.packet_count:
            pts90 += 9000
            if spn >= DISCONTINUITY_AT:
                pts90 += 90000

    # build STC sequences from the EP list
    a.stc_sequences = []
    stc_start_spn = 0
    stc_start_pts = a.eps[0][1]
    for idx, (espn, epts) in enumerate(a.eps):
        if epts - a.eps[idx - 1][1] > 90000 if idx else False:
            a.stc_sequences.append((stc_start_spn, PCR_PID, stc_start_pts // 2, a.eps[idx - 1][1] // 2))
            stc_start_spn = espn
            stc_start_pts = epts
    a.stc_sequences.append((stc_start_spn, PCR_PID, stc_start_pts // 2, a.eps[-1][1] // 2))
    return a


def build_ep_map(a: Analysis):
    fine_entries = bytearray()
    coarse_entries = bytearray()
    prev_fine_pts = None
    prev_fine_spn = None
    for idx, (spn, pts90) in enumerate(a.eps):
        pts45 = pts90 >> 1
        pts_fine = (pts45 >> 8) & 0x7FF
        spn_fine = spn & 0x1FFFF
        if prev_fine_pts is None or pts_fine <= prev_fine_pts or spn_fine <= prev_fine_spn:
            coarse_entries += be(idx << 14 | (pts45 >> 18) & 0x3FFF, 4)
            coarse_entries += be(spn, 4)
        prev_fine_pts = pts_fine
        prev_fine_spn = spn_fine
        fine_entries += be(1 << 28 | pts_fine << 17 | spn_fine, 4)
    ncoarse = len(coarse_entries) // 8
    nfine = len(fine_entries) // 4

    ep_for_pid = be(4 + len(coarse_entries), 4) + coarse_entries + fine_entries
    ep_map = bytearray()
    ep_map += bytes((0, 1))
    ep_map += be(a.video_pid, 2)
    ep_map += be(1 << 34 | ncoarse << 18 | nfine, 6)
    ep_map += be(14, 4)
    ep_map += ep_for_pid
    return ep_map


VIDEO_ATTRS = (0x4, 0x3, 0x3)   # 1080i, 25 fps, 16:9


def build_bdav_clpi(a: Analysis) -> bytes:
    clip_info = bytearray()
    clip_info += be(0xB0, 4)
    clip_info += be(0, 2)
    clip_info += bytes((1, 0))
    clip_info += be(0, 4)
    clip_info += be(TS_RECORDING_RATE, 4)
    clip_info += be(a.packet_count, 4)
    clip_info += bytes(128)
    clip_info += be(0x1E, 2)
    clip_info += bytes((0x7C, 0x00))
    clip_info += be(0, 4)
    clip_info += bytes((0x04,))
    clip_info += be(a.transport_stream_id, 2)
    clip_info += be(a.service_id, 2)
    clip_info += b"JPN"
    clip_info += b"\xff" * 16

    stc_body = bytearray()
    for spn_start, pcr_pid, start_45k, end_45k in a.stc_sequences:
        stc_body += be(pcr_pid, 2)
        stc_body += be(spn_start, 4)
        stc_body += be(start_45k, 4)
        stc_body += be(end_45k, 4)
    seq = bytearray()
    seq += be(2 + 6 + len(stc_body), 4)
    seq += bytes((0, 1))
    seq += be(0, 4)
    seq += bytes((len(a.stc_sequences), 0))
    seq += stc_body
    if len(seq) % 4:
        seq += bytes(4 - len(seq) % 4)

    # BDAV: stream coding info is 3 bytes (no ISRC, no language)
    ps_body = bytearray()
    ps_body += be(1, 4)
    ps_body += be(a.pmt_pid, 2)
    ps_body += bytes((1, 1))
    ps_body += be(a.video_pid, 2)
    ps_body += bytes((3, a.video_stream_type,
                      (VIDEO_ATTRS[0] << 4) | VIDEO_ATTRS[1],
                      VIDEO_ATTRS[2] << 4))
    prog = bytearray()
    prog += be(2 + len(ps_body), 4)
    prog += bytes((0, 1))
    prog += ps_body
    if len(prog) % 4:
        prog += bytes(4 - len(prog) % 4)

    cpi_body = be(1, 2) + build_ep_map(a)
    cpi = be(len(cpi_body), 4) + cpi_body

    seq_start = 0x28 + len(clip_info)
    prog_start = seq_start + len(seq)
    cpi_start = prog_start + len(prog)
    clipmark_start = cpi_start + len(cpi)

    out = bytearray()
    out += b"M2TS0100"
    out += be(seq_start, 4)
    out += be(prog_start, 4)
    out += be(cpi_start, 4)
    out += be(clipmark_start, 4)
    out += bytes(16)
    assert len(out) == 0x28
    out += clip_info + seq + prog + cpi
    assert len(out) == clipmark_start
    out += be(0, 4)
    return bytes(out)


def build_bdav_rpls(a: Analysis) -> bytes:
    app = bytearray()
    app += be(0x5DE, 4)
    app += bytes((0, 0, 1, 0))
    app += bytes((0x12, 0))
    app += bytes((0x20, 0x26, 0x01, 0x01, 0x00, 0x00, 0x00))
    app += bytes((0x00, 0x00, 0x02))
    app += be(0, 2) + be(0, 2)
    app += be(0xFFFF, 2)
    app += bytes((1,))
    app += bytes(20)
    app += bytes((0,))
    app += bytes(255)
    app += be(0, 2)
    app += bytes(0x5DE + 4 - len(app))
    app += bytes(2)

    items = bytearray()
    for stc_id, (spn_start, pcr_pid, start_45k, end_45k) in enumerate(a.stc_sequences):
        item = bytearray()
        item += b"00001"
        item += b"M2TS"
        item += bytes((0, 1, stc_id))
        item += be(start_45k, 4)
        item += be(end_45k, 4)
        items += be(len(item), 2) + item
    playlist_body = be(1, 2) + be(len(a.stc_sequences), 2) + be(0, 2) + items
    playlist = be(len(playlist_body), 4) + playlist_body

    marks = bytearray()
    for stc_id, (spn_start, pcr_pid, start_45k, end_45k) in enumerate(a.stc_sequences):
        marks += bytes((4, 0)) + be(0x0108, 2) + be(stc_id, 2) + be(start_45k, 4)
        marks += be(0xFFFF, 2) + be(0xFFFF, 2) + bytes(32)
    mark_block = be(len(marks), 4) + be(len(a.stc_sequences), 2) + marks

    pl_start = 0x28 + len(app)
    pl_end = pl_start + len(playlist)
    mark_start = pl_end + ((-pl_end) % 4) + 4

    out = bytearray()
    out += b"PLST0100"
    out += be(pl_start, 4)
    out += be(mark_start, 4)
    out += be(0, 4)
    out += bytes(0x28 - len(out))
    out += app
    out += playlist
    out += bytes(mark_start - len(out))
    out += mark_block
    if len(out) % 4:
        out += bytes(4 - len(out) % 4)
    return bytes(out)


def build_bdav_index(name: str) -> bytes:
    ui = bytearray()
    ui += be(0x114, 4)
    ui += bytes((0, 0, 1, 0))
    ui += b"0000"
    ui += bytes(10)
    ui += b"\xff\xff"
    ui += bytes(0x114 + 4 - len(ui))
    body = bytearray()
    body += be(1, 2)
    body += name.encode("ascii")
    out = bytearray()
    out += b"BDAV0100"
    out += be(0x140, 4)
    out += be(0, 4)
    out += bytes(0x28 - len(out))
    out += ui
    assert len(out) == 0x140
    out += be(len(body), 4) + body
    if len(out) % 4:
        out += bytes(4 - len(out) % 4)
    return bytes(out)


def build_bdmv_clpi(a: Analysis) -> bytes:
    clip_info = bytearray()
    clip_info += be(0xB0, 4)
    clip_info += be(0, 2)
    clip_info += bytes((1, 0))
    clip_info += be(0, 4)
    clip_info += be(TS_RECORDING_RATE, 4)
    clip_info += be(a.packet_count, 4)
    clip_info += bytes(128)
    clip_info += be(0x1E, 2)
    clip_info += bytes((0x7C, 0x00))
    clip_info += be(0, 4)
    clip_info += bytes((0x04,))
    clip_info += be(a.transport_stream_id, 2)
    clip_info += be(a.service_id, 2)
    clip_info += b"JPN"
    clip_info += b"\xff" * 16

    stc_body = bytearray()
    for spn_start, pcr_pid, start_45k, end_45k in a.stc_sequences:
        stc_body += be(pcr_pid, 2)
        stc_body += be(spn_start, 4)
        stc_body += be(start_45k, 4)
        stc_body += be(end_45k, 4)
    seq = bytearray()
    seq += be(2 + 6 + len(stc_body), 4)
    seq += bytes((0, 1))
    seq += be(0, 4)
    seq += bytes((len(a.stc_sequences), 0))
    seq += stc_body
    if len(seq) % 4:
        seq += bytes(4 - len(seq) % 4)

    # BDMV: 16 byte stream coding info (with ISRC)
    ps_body = bytearray()
    ps_body += be(1, 4)
    ps_body += be(a.pmt_pid, 2)
    ps_body += bytes((1, 1))
    ps_body += be(a.video_pid, 2)
    ps_body += bytes((16, a.video_stream_type,
                      (VIDEO_ATTRS[0] << 4) | VIDEO_ATTRS[1],
                      VIDEO_ATTRS[2] << 4))
    ps_body += bytes(12)
    prog = bytearray()
    prog += be(2 + len(ps_body), 4)
    prog += bytes((0, 1))
    prog += ps_body
    if len(prog) % 4:
        prog += bytes(4 - len(prog) % 4)

    cpi_body = be(1, 2) + build_ep_map(a)
    cpi = be(len(cpi_body), 4) + cpi_body

    seq_start = 0x28 + len(clip_info)
    prog_start = seq_start + len(seq)
    cpi_start = prog_start + len(prog)
    clipmark_start = cpi_start + len(cpi)

    out = bytearray()
    out += b"HDMV0100"
    out += be(seq_start, 4)
    out += be(prog_start, 4)
    out += be(cpi_start, 4)
    out += be(clipmark_start, 4)
    out += be(0, 4)
    out += bytes(12)
    assert len(out) == 0x28
    out += clip_info + seq + prog + cpi
    assert len(out) == clipmark_start
    out += be(0, 4)
    return bytes(out)


def build_bdmv_mpls(a: Analysis) -> bytes:
    app = bytearray()
    app += be(14, 4)
    app += bytes((0, 1))
    app += be(0, 2)
    app += bytes([0xFF] * 8)
    app += bytes((0x80, 0x00))

    streams = bytearray()
    streams += bytes((3, 1)) + be(a.video_pid, 2)
    streams += bytes((2, a.video_stream_type,
                      (VIDEO_ATTRS[0] << 4) | VIDEO_ATTRS[1]))
    stn = bytearray()
    stn += be(14 + len(streams), 2)
    stn += bytes(2)
    stn += bytes((1, 0, 0, 0, 0, 0, 0, 0))
    stn += bytes(4)
    stn += streams

    items = bytearray()
    for stc_id, (spn_start, pcr_pid, start_45k, end_45k) in enumerate(a.stc_sequences):
        item = bytearray()
        item += b"00000"
        item += b"M2TS"
        item += bytes((0x00, 0x01))
        item += bytes((stc_id,))
        item += be(start_45k, 4)
        item += be(end_45k, 4)
        item += bytes([0xFF] * 8)
        item += bytes((0x80, 0x00, 0x00, 0x00))
        item += stn
        items += be(len(item), 2) + item
    playlist_body = be(0, 2) + be(len(a.stc_sequences), 2) + be(0, 2) + items
    playlist = be(len(playlist_body), 4) + playlist_body

    marks = bytearray()
    for stc_id, (spn_start, pcr_pid, start_45k, end_45k) in enumerate(a.stc_sequences):
        marks += bytes((0, 1)) + be(stc_id, 2) + be(start_45k, 4) + be(0xFFFF, 2) + be(0, 4)
    mark_block = be(len(marks), 4) + be(len(a.stc_sequences), 2) + marks

    pl_start = 0x28 + len(app)
    if pl_start % 4:
        app += bytes(4 - pl_start % 4)
        pl_start = 0x28 + len(app)
    pl_end = pl_start + len(playlist)
    mark_start = pl_end + ((-pl_end) % 4)

    out = bytearray()
    out += b"MPLS0100"
    out += be(pl_start, 4)
    out += be(mark_start, 4)
    out += be(0, 4)
    out += bytes(0x28 - len(out))
    out += app
    out += playlist
    out += bytes(mark_start - len(out))
    out += mark_block
    if len(out) % 4:
        out += bytes(4 - len(out) % 4)
    return bytes(out)


def main() -> int:
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "testdata")
    m2ts = make_m2ts()
    a = analyze(m2ts)

    # BDAV disc root
    bdav = out_dir / "bdav_disc" / "BDAV"
    (bdav / "PLAYLIST").mkdir(parents=True, exist_ok=True)
    (bdav / "CLIPINF").mkdir(parents=True, exist_ok=True)
    (bdav / "STREAM").mkdir(parents=True, exist_ok=True)
    (bdav / "PLAYLIST" / "00001.rpls").write_bytes(build_bdav_rpls(a))
    (bdav / "CLIPINF" / "00001.clpi").write_bytes(build_bdav_clpi(a))
    (bdav / "STREAM" / "00001.m2ts").write_bytes(m2ts)
    (bdav / "info.bdav").write_bytes(build_bdav_index("00001.rpls"))

    # BDMV disc root
    bdmv = out_dir / "bdmv_disc" / "BDMV"
    (bdmv / "PLAYLIST").mkdir(parents=True, exist_ok=True)
    (bdmv / "CLIPINF").mkdir(parents=True, exist_ok=True)
    (bdmv / "STREAM").mkdir(parents=True, exist_ok=True)
    (bdmv / "PLAYLIST" / "00000.mpls").write_bytes(build_bdmv_mpls(a))
    (bdmv / "CLIPINF" / "00000.clpi").write_bytes(build_bdmv_clpi(a))
    (bdmv / "STREAM" / "00000.m2ts").write_bytes(m2ts)

    print(f"{out_dir}: BDAV + BDMV test discs written "
          f"({a.packet_count} packets, {len(a.eps)} EP, "
          f"{len(a.stc_sequences)} STC sequences)")
    print(f"  BDAV disc root: {out_dir / 'bdav_disc'}")
    print(f"  BDMV disc root: {out_dir / 'bdmv_disc'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
