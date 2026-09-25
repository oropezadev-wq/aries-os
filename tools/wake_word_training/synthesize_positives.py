"""tools/wake_word_training/synthesize_positives.py — genera positivos
sintéticos de "oye aries" con varias voces de Piper en español, para
atacar la escasez de datos reales (ver docs/specs/WakeWordTraining.spec.md,
Decisión 2, revisión 2026-09-24).

Decisión 2 original (grabación real, no TTS sintético, 2026-09-21)
bloqueaba específicamente `piper-sample-generator` — requiere un
checkpoint multi-speaker que solo existe en inglés
(`en_US-libritts_r-medium.pt`). **Esto no usa esa herramienta.** Sintetiza
con varias voces *single-speaker* en español ya existentes
(`rhasspy/piper-voices`), cada una por separado — eso sí da diversidad de
hablante real en el idioma correcto (corrección del usuario, 2026-09-24;
la Decisión 2 bloqueaba la herramienta puntual, no la idea).

Catálogo real verificado (`rhasspy/piper-voices/voices.json`, 2026-09-24):
9 voces en español. Se usan 4 de calidad media/alta (se descartan las
`x_low`/`low`, señal más pobre): `es_MX-claude-high` (ya local, usada por
`PiperProvider` en producción), `es_MX-ald-medium`, `es_AR-daniela-high`
(español argentino — el usuario mencionó "cortana"/"gevy" como voces de
comunidad, no encontradas en el catálogo oficial; se sustituyen por estas,
con daniela como agregado extra por acento) y `es_ES-davefx-medium`.

Variación entre clips de una misma voz: `length_scale` (velocidad) y
`noise_scale`/`noise_w_scale` (variación estocástica de pronunciación —
Piper no da el mismo audio dos veces con el mismo texto por default). La
variación de pitch/reverb/ruido de fondo NO se hace acá — ya la aplica
`run_training.py`/`_make_features` vía `augment_clips` (mismo camino que
las grabaciones reales, ver `_make_features` en `run_training.py`), así
que los sintéticos pasan por la misma augmentación sin código adicional.

Cada voz nativa sintetiza a 22050 Hz — se resamplea a 16000 Hz (mismo
método que `_resample_frame` de `aries.voice.audio_io`, aplicado acá al
clip completo en vez de por frame) para que el resto del pipeline
(`_median_clip_length`, features, augmentación) no distinga origen
sintético de grabado real.

No es parte del paquete `aries` — utilidad de desarrollo de un solo uso.

Uso:
    python tools/wake_word_training/synthesize_positives.py --per-voice 250
"""

from __future__ import annotations

import argparse
import random
import uuid
from math import gcd
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

HERE = Path(__file__).resolve().parent
TARGET_PHRASE = "oye aries"
TARGET_SR = 16000

DEFAULT_VOICES_DIR = HERE / "piper_voices"
DEFAULT_VOICES = [
    "es_MX-claude-high",
    "es_MX-ald-medium",
    "es_AR-daniela-high",
    "es_ES-davefx-medium",
]

# length_scale < 1.0 habla más rápido, > 1.0 más lento. noise_scale/
# noise_w_scale controlan la variación estocástica de pronunciación/
# prosodia que Piper aplica por default (0 = determinístico).
LENGTH_SCALE_RANGE = (0.85, 1.25)
NOISE_SCALE_RANGE = (0.5, 0.9)
NOISE_W_SCALE_RANGE = (0.5, 0.9)


def _resample_to_target(pcm: np.ndarray, native_rate: int) -> np.ndarray:
    """Resamplea un clip completo (no un frame de 80ms) de `native_rate`
    a `TARGET_SR` — mismo método (`resample_poly`, filtro FIR polifásico)
    que `_resample_frame` en `aries.voice.audio_io`, sin el ajuste a un
    `target_length` fijo (acá el clip entero define su propia duración)."""
    if native_rate == TARGET_SR:
        return pcm
    divisor = gcd(native_rate, TARGET_SR)
    up, down = TARGET_SR // divisor, native_rate // divisor
    resampled = resample_poly(pcm.astype(np.float64), up, down)
    return np.clip(resampled, -32768, 32767).astype(np.int16)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voices-dir", type=Path, default=DEFAULT_VOICES_DIR)
    parser.add_argument("--voices", nargs="+", default=DEFAULT_VOICES)
    parser.add_argument("--per-voice", type=int, default=250, help="Clips sintéticos por voz")
    parser.add_argument("--output-dir", type=Path, default=HERE / "dataset" / "synthetic_positive")
    parser.add_argument("--seed", type=int, default=20260925, help="Semilla de length_scale/noise_scale — determinístico")
    args = parser.parse_args()

    from piper import PiperVoice
    from piper.config import SynthesisConfig

    rng = random.Random(args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    for voice_name in args.voices:
        model_path = args.voices_dir / f"{voice_name}.onnx"
        if not model_path.exists():
            print(f"AVISO: {model_path} no existe, se salta esa voz.")
            continue
        voice = PiperVoice.load(str(model_path))
        native_sr = voice.config.sample_rate

        made = 0
        for _ in range(args.per_voice):
            syn_config = SynthesisConfig(
                length_scale=rng.uniform(*LENGTH_SCALE_RANGE),
                noise_scale=rng.uniform(*NOISE_SCALE_RANGE),
                noise_w_scale=rng.uniform(*NOISE_W_SCALE_RANGE),
            )
            chunks = list(voice.synthesize(TARGET_PHRASE, syn_config=syn_config))
            if not chunks:
                continue
            pcm_bytes = b"".join(c.audio_int16_bytes for c in chunks)
            pcm = np.frombuffer(pcm_bytes, dtype=np.int16)
            pcm = _resample_to_target(pcm, native_sr)

            out_path = args.output_dir / f"{voice_name}_{uuid.uuid4().hex}.wav"
            wavfile.write(out_path, TARGET_SR, pcm)
            made += 1

        print(f"{voice_name}: {made}/{args.per_voice} clips generados")
        total += made

    print(f"Total: {total} clips sintéticos en {args.output_dir}")


if __name__ == "__main__":
    main()
