"""PCM audio encode/decode helpers for Gemini Live streaming."""

from __future__ import annotations

import base64
import struct
from typing import Optional


# Gemini Live expects 16-bit PCM, 16kHz mono input
INPUT_SAMPLE_RATE = 16000
INPUT_CHANNELS = 1
INPUT_SAMPLE_WIDTH = 2  # 16-bit = 2 bytes

# Gemini Live outputs 24kHz PCM audio
OUTPUT_SAMPLE_RATE = 24000
OUTPUT_CHANNELS = 1
OUTPUT_SAMPLE_WIDTH = 2


def pcm_to_base64(pcm_bytes: bytes) -> str:
    """Encode raw PCM bytes to base64 string for Gemini Live."""
    return base64.b64encode(pcm_bytes).decode("ascii")


def base64_to_pcm(b64_string: str) -> bytes:
    """Decode base64 string from Gemini Live to raw PCM bytes."""
    return base64.b64decode(b64_string)


def float32_to_pcm16(float_data: bytes) -> bytes:
    """Convert float32 audio samples to 16-bit PCM.

    Browser AudioWorklet typically outputs float32 samples in [-1.0, 1.0].
    Gemini Live expects 16-bit signed integer PCM.
    """
    num_samples = len(float_data) // 4  # 4 bytes per float32
    floats = struct.unpack(f"<{num_samples}f", float_data)
    pcm = struct.pack(
        f"<{num_samples}h",
        *(max(-32768, min(32767, int(s * 32767))) for s in floats),
    )
    return pcm


def pcm16_to_float32(pcm_data: bytes) -> bytes:
    """Convert 16-bit PCM to float32 samples for browser playback."""
    num_samples = len(pcm_data) // 2  # 2 bytes per int16
    shorts = struct.unpack(f"<{num_samples}h", pcm_data)
    floats = struct.pack(
        f"<{num_samples}f",
        *(s / 32768.0 for s in shorts),
    )
    return floats


def compute_rms(pcm_data: bytes) -> float:
    """Compute RMS volume level from 16-bit PCM data. Returns 0.0-1.0."""
    if not pcm_data or len(pcm_data) < 2:
        return 0.0
    num_samples = len(pcm_data) // 2
    shorts = struct.unpack(f"<{num_samples}h", pcm_data)
    rms = (sum(s * s for s in shorts) / num_samples) ** 0.5
    return min(1.0, rms / 32768.0)
