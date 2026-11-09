"""Minimal WAV reader/writer (PCM 16/24/32-bit and 32-bit float), NumPy only."""
import struct

import numpy as np


def write(path, sr, data):
    data = np.asarray(data)
    ch = 1 if data.ndim == 1 else data.shape[1]
    if data.dtype == np.int16:
        fmt, bits, raw = 1, 16, data.astype("<i2").tobytes()
    else:
        fmt, bits, raw = 3, 32, data.astype("<f4").tobytes()
    block = ch * bits // 8
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + len(raw)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<IHHIIHH", 16, fmt, ch, sr, sr * block, block, bits))
        f.write(b"data" + struct.pack("<I", len(raw)) + raw)


def read(path):
    """Returns (sample_rate, float32 array shaped (n,) or (n, channels)) scaled to -1..1."""
    with open(path, "rb") as f:
        buf = f.read()
    if buf[:4] != b"RIFF" or buf[8:12] != b"WAVE":
        raise ValueError("Not a WAV file")
    pos, fmt, ch, sr, bits, data = 12, None, 1, 44100, 16, None
    while pos + 8 <= len(buf):
        cid, size = buf[pos:pos + 4], struct.unpack("<I", buf[pos + 4:pos + 8])[0]
        body = buf[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            fmt, ch, sr = struct.unpack("<HHI", body[:8])
            bits = struct.unpack("<H", body[14:16])[0]
            if fmt == 0xFFFE and len(body) >= 26:  # WAVE_FORMAT_EXTENSIBLE
                fmt = struct.unpack("<H", body[24:26])[0]
        elif cid == b"data":
            if size == 0 or size == 0xFFFFFFFF:  # streaming writers leave this unset
                body = buf[pos + 8:]
            data = body
        pos += 8 + size + (size & 1)
        if data is not None and cid == b"data":
            break
    if data is None or fmt is None:
        raise ValueError("Broken WAV file")
    if fmt == 3 and bits == 32:
        y = np.frombuffer(data[: len(data) // 4 * 4], "<f4").astype(np.float32)
    elif fmt == 1 and bits == 16:
        y = np.frombuffer(data[: len(data) // 2 * 2], "<i2").astype(np.float32) / 32768
    elif fmt == 1 and bits == 24:
        b = np.frombuffer(data[: len(data) // 3 * 3], np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        v = np.where(v & 0x800000, v - 0x1000000, v)
        y = v.astype(np.float32) / 8388608
    elif fmt == 1 and bits == 32:
        y = np.frombuffer(data[: len(data) // 4 * 4], "<i4").astype(np.float32) / 2147483648
    elif fmt == 1 and bits == 8:
        y = (np.frombuffer(data, np.uint8).astype(np.float32) - 128) / 128
    else:
        raise ValueError(f"Unsupported WAV format ({fmt}, {bits}-bit)")
    if ch > 1:
        y = y[: len(y) // ch * ch].reshape(-1, ch)
    return sr, y
