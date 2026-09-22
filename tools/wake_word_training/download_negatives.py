"""tools/wake_word_training/download_negatives.py — descarga audio de fondo
real (no reverb/silencio) para `negative_data/background_noise/`, usado por
`openwakeword.data.augment_clips` (`background_clip_paths`, augmentación
`AddBackgroundNoise`) al entrenar el modelo custom (ver
`docs/specs/WakeWordTraining.spec.md`).

No es parte del paquete `aries` — utilidad de desarrollo de un solo uso.

Fuente: **solo AudioSet** (`agkphysics/AudioSet` en HuggingFace, split
`train`, streaming — clips de YouTube ya recortados a 10s, mezcla amplia de
habla/ruido/música/ambiente). El notebook oficial de entrenamiento de
openWakeWord (`dscripka/openWakeWord`) también usa FMA (`rudraml/fma`) como
segunda fuente, pero ese repo expone los datos vía un script de carga
(`fma.py`) que la versión instalada de `datasets` (5.x) ya no soporta
("Dataset scripts are no longer supported") — se decidió no perseguir un
workaround (downgrade de `datasets` o reimplementar la descarga del mirror
original de FMA) para esto, que es una fuente secundaria de variedad
adicional, no la única. AudioSet solo ya cubre música/ruido/habla de fondo
razonablemente bien (es la fuente primaria también en el notebook oficial).
Queda documentado como limitación conocida, no bloqueante — se puede sumar
FMA más adelante si hace falta más variedad.

La decodificación de audio usa `soundfile` directo sobre los bytes FLAC
crudos (`datasets.Audio(decode=False)`), no el decoder default de
`datasets` (torchcodec, vía FFmpeg) — FFmpeg no está instalado en esta
máquina (mismo problema que ya resolvió `run_training.py` para
`torchaudio.load`, ver su docstring).

Uso:
    python tools/wake_word_training/download_negatives.py --target-minutes 60
"""

from __future__ import annotations

import argparse
import io
import logging
from pathlib import Path

import numpy as np
import scipy.io.wavfile
import scipy.signal
import soundfile as sf

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("download_negatives")

TARGET_SR = 16000
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "negative_data" / "background_noise"


def _to_16k_mono_int16(data: np.ndarray, sr: int) -> np.ndarray:
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != TARGET_SR:
        from math import gcd

        g = gcd(sr, TARGET_SR)
        data = scipy.signal.resample_poly(data, TARGET_SR // g, sr // g)
    peak = np.max(np.abs(data)) or 1.0
    if peak > 1.0:
        data = data / peak  # los floats de soundfile ya suelen venir en [-1, 1], por las dudas
    return (data * 32767.0).astype(np.int16)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-minutes", type=float, default=60.0, help="Minutos totales de audio a juntar")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-consecutive-errors", type=int, default=10, help="Corta si el streaming falla seguido (problema de red, no de datos)")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    existing = list(args.output_dir.glob("audioset_*.wav"))
    if existing:
        logger.info("Ya hay %d clips en %s — se completa hasta la meta, no se re-descargan.", len(existing), args.output_dir)

    import datasets

    ds = datasets.load_dataset("agkphysics/AudioSet", split="train", streaming=True)
    ds = ds.cast_column("audio", datasets.Audio(decode=False))

    target_seconds = args.target_minutes * 60.0
    collected_seconds = sum(
        scipy.io.wavfile.read(f)[1].shape[0] / TARGET_SR for f in existing
    )
    idx = len(existing)
    consecutive_errors = 0

    logger.info("Meta: %.1f min (%.1f min ya en disco). Empezando streaming de AudioSet...", args.target_minutes, collected_seconds / 60)

    it = iter(ds)
    while collected_seconds < target_seconds:
        try:
            example = next(it)
        except StopIteration:
            logger.warning("Se acabó el dataset antes de llegar a la meta (%.1f/%.1f min).", collected_seconds / 60, args.target_minutes)
            break
        except Exception as error:  # noqa: BLE001 — streaming remoto: red, parquet corrupto, lo que sea, no es fatal
            consecutive_errors += 1
            logger.warning("Error leyendo un ejemplo del stream (%d seguidos): %s", consecutive_errors, error)
            if consecutive_errors >= args.max_consecutive_errors:
                logger.error("Demasiados errores seguidos, corto acá (%.1f/%.1f min).", collected_seconds / 60, args.target_minutes)
                break
            continue

        consecutive_errors = 0
        raw = example["audio"]["bytes"]
        if not raw:
            continue

        try:
            data, sr = sf.read(io.BytesIO(raw))
        except Exception as error:  # noqa: BLE001 — algún clip con FLAC corrupto/vacío, se descarta y sigue
            logger.warning("No se pudo decodificar un clip, se descarta: %s", error)
            continue

        pcm16 = _to_16k_mono_int16(data, sr)
        if pcm16.size == 0:
            continue

        destination = args.output_dir / f"audioset_{idx:05d}.wav"
        scipy.io.wavfile.write(destination, TARGET_SR, pcm16)
        collected_seconds += pcm16.size / TARGET_SR
        idx += 1

        if idx % 25 == 0:
            logger.info("%.1f / %.1f min (%d clips)", collected_seconds / 60, args.target_minutes, idx)

    logger.info("Listo: %.1f min en %d clips, en %s", collected_seconds / 60, idx, args.output_dir)


if __name__ == "__main__":
    main()
