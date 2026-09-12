"""tools/wake_word_training/record_samples.py — graba repeticiones reales de
la wake word para entrenar un modelo custom de openWakeWord (ver
`docs/specs/WakeWordTraining.spec.md`).

No es parte del paquete `aries` (no se importa desde `src/`) — es una
utilidad de desarrollo de un solo uso, corrida manualmente una vez para
armar el dataset de entrenamiento. Reusa `MicrophoneListener`/
`record_until_silence` de `aries.voice.audio_io` tal cual (mismo fix de
captura WASAPI que ya usa el pipeline en vivo) para que las condiciones de
grabación sean las mismas que las de uso real del asistente.

Uso:
    python tools/wake_word_training/record_samples.py --count 200

Guarda los `.wav` en `<output-dir>/positive_train/` y
`<output-dir>/positive_test/` (split 90/10), con nombres `uuid4().hex.wav`
— mismo esquema de nombres que usa `openwakeword/train.py` para las
muestras sintéticas, así el resto del pipeline de entrenamiento no
distingue origen sintético de grabado real.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from aries.voice.audio_io import (  # noqa: E402
    MicrophoneListener,
    record_until_silence,
    wav_bytes_to_pcm,
)

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "dataset"
TEST_SPLIT_RATIO = 0.1  # ~1 de cada 10 tomas va a positive_test, no a positive_train


def _rms(pcm: bytes) -> float:
    samples = np.frombuffer(pcm, dtype=np.int16)
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))


def _record_one_take(listener: MicrophoneListener, max_seconds: float) -> tuple[bytes, float]:
    with listener:
        wav_bytes = record_until_silence(
            listener,
            max_seconds=max_seconds,
            silence_threshold=300.0,
            silence_duration_seconds=0.6,
        )
    pcm, _sample_rate, _channels, _width = wav_bytes_to_pcm(wav_bytes)
    return wav_bytes, _rms(pcm)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phrase", default="Hola Aries", help="Frase a grabar (solo para el prompt en pantalla)")
    parser.add_argument("--count", type=int, default=200, help="Cantidad total de tomas a grabar")
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Carpeta destino (se crean positive_train/positive_test adentro)"
    )
    parser.add_argument("--max-seconds", type=float, default=4.0, help="Duración máxima por toma antes de cortar por timeout")
    parser.add_argument(
        "--min-rms",
        type=float,
        default=200.0,
        help="RMS mínimo para aceptar una toma sin preguntar — por debajo, se avisa que pudo grabarse en silencio",
    )
    args = parser.parse_args()

    train_dir = args.output_dir / "positive_train"
    test_dir = args.output_dir / "positive_test"
    train_dir.mkdir(parents=True, exist_ok=True)
    test_dir.mkdir(parents=True, exist_ok=True)

    n_existing = len(list(train_dir.glob("*.wav"))) + len(list(test_dir.glob("*.wav")))
    if n_existing:
        print(f"Ya hay {n_existing} tomas guardadas en {args.output_dir} — continuando desde ahí.")

    listener = MicrophoneListener()
    remaining = max(0, args.count - n_existing)

    print(f"Frase: \"{args.phrase}\" — faltan {remaining} tomas.")
    print("Enter para grabar cada toma (graba hasta ~0.6s de silencio o hasta el máximo). Ctrl+C para cortar en cualquier momento.\n")

    recorded = 0
    try:
        while recorded < remaining:
            input(f"[{n_existing + recorded + 1}/{args.count}] Enter y decí \"{args.phrase}\"... ")
            wav_bytes, rms = _record_one_take(listener, args.max_seconds)

            if rms < args.min_rms:
                keep = input(f"  RMS bajo ({rms:.0f}) — ¿parece que no se grabó nada? Guardar igual? [s/N] ")
                if keep.strip().lower() != "s":
                    print("  Descartada, repetí la toma.")
                    continue

            destination = test_dir if (n_existing + recorded) % int(1 / TEST_SPLIT_RATIO) == 0 else train_dir
            file_path = destination / f"{uuid.uuid4().hex}.wav"
            file_path.write_bytes(wav_bytes)
            recorded += 1
            print(f"  Guardada en {destination.name}/ (RMS={rms:.0f})")
    except KeyboardInterrupt:
        print(f"\nCortado por el usuario. Grabadas {recorded} tomas nuevas ({n_existing + recorded} en total).")
        return

    print(f"\nListo: {n_existing + recorded} tomas totales en {args.output_dir}.")


if __name__ == "__main__":
    main()
