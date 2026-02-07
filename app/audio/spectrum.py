"""
Real-time spectrum analyzer – decodes audio to PCM samples and provides
FFT-based frequency band levels for the equalizer display.

Requires: numpy, pydub (+ ffmpeg on the system PATH).
Falls back gracefully if unavailable.
"""

import threading
from typing import Optional

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

try:
    from pydub import AudioSegment
    _HAS_PYDUB = True
except ImportError:
    _HAS_PYDUB = False

NUM_BANDS = 12
SAMPLE_RATE = 44100
FFT_SIZE = 2048


class SpectrumAnalyzer:
    """Decodes audio and provides FFT-based frequency band levels."""

    def __init__(self):
        self._samples: Optional[object] = None
        self._sample_rate: int = SAMPLE_RATE
        self._lock = threading.Lock()
        self._band_edges: list[tuple[int, int]] = []
        self._window = None
        if _HAS_NUMPY:
            self._window = np.hanning(FFT_SIZE)
            self._compute_band_edges(SAMPLE_RATE)

    @property
    def available(self) -> bool:
        return _HAS_NUMPY and _HAS_PYDUB

    @property
    def ready(self) -> bool:
        with self._lock:
            return self._samples is not None

    def load_file(self, filepath: str):
        """Decode audio file in a background thread."""
        if not self.available:
            return
        with self._lock:
            self._samples = None
        thread = threading.Thread(
            target=self._decode, args=(filepath,), daemon=True
        )
        thread.start()

    def get_levels(self, position_ms: int) -> Optional[list[int]]:
        """
        Return 12 frequency band levels (0-12) at the given playback position.
        Returns None if spectrum analysis is not available or not yet decoded.
        """
        if not _HAS_NUMPY:
            return None

        with self._lock:
            samples = self._samples
            sr = self._sample_rate

        if samples is None:
            return None

        sample_idx = int(position_ms * sr / 1000)
        start = max(0, sample_idx - FFT_SIZE // 2)
        end = start + FFT_SIZE

        if end > len(samples):
            return [0] * NUM_BANDS

        chunk = samples[start:end] * self._window

        fft_mag = np.abs(np.fft.rfft(chunk)) * 2.0 / FFT_SIZE

        levels = []
        for low_bin, high_bin in self._band_edges:
            hi = min(high_bin, len(fft_mag))
            if low_bin >= hi:
                levels.append(0)
                continue
            band_rms = np.sqrt(np.mean(fft_mag[low_bin:hi] ** 2))
            db = 20.0 * np.log10(band_rms + 1e-10)
            # Map dB to 0-12: -48 dB -> 0, -3 dB -> 12
            level = int(max(0, min(12, (db + 48) * 12 / 45)))
            levels.append(level)

        return levels

    def _decode(self, filepath: str):
        """Decode audio file to mono float32 samples."""
        try:
            audio = AudioSegment.from_file(filepath)
            audio = audio.set_channels(1).set_frame_rate(SAMPLE_RATE)
            raw = audio.raw_data
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            samples /= 32768.0

            with self._lock:
                self._samples = samples
                self._sample_rate = SAMPLE_RATE
        except Exception:
            with self._lock:
                self._samples = None

    def _compute_band_edges(self, sample_rate: int):
        """Pre-compute FFT bin index ranges for each frequency band."""
        f_min = 60.0
        f_max = 16000.0
        edges = []
        for i in range(NUM_BANDS):
            lo_freq = f_min * (f_max / f_min) ** (i / NUM_BANDS)
            hi_freq = f_min * (f_max / f_min) ** ((i + 1) / NUM_BANDS)
            lo_bin = max(1, int(lo_freq * FFT_SIZE / sample_rate))
            hi_bin = max(lo_bin + 1, int(hi_freq * FFT_SIZE / sample_rate))
            edges.append((lo_bin, hi_bin))
        self._band_edges = edges
