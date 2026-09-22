"""tools/wake_word_training/record_hard_negatives.py — graba negativos
difíciles: la voz real del usuario diciendo fragmentos parecidos a "Oye
Aries" pero que NO son la wake word, para que el modelo no aprenda a
dispararse con cualquiera de sus dos palabras sueltas.

Pedido explícito del supervisor (2026-09-21, ver
`docs/specs/WakeWordTraining.spec.md`): el dataset actual solo tiene
ejemplos positivos (la frase completa) y negativos genéricos (ACAV100M,
ruido de fondo) — ninguno de los dos le enseña al modelo a distinguir
"Oye Aries" completa de "oye" sola (+ otra palabra) o "Aries" sola. Sin
esto, un clasificador chico puede aprender el atajo de dispararse con
cualquiera de las dos palabras en vez de la frase entera.

No es parte del paquete `aries` (no se importa desde `src/`) — utilidad de
desarrollo de un solo uso, hermana de `record_samples.py` (misma
mecánica de grabación vía `MicrophoneListener`/`record_until_silence`,
mismo esquema de nombres `uuid4().hex.wav`, mismo manifiesto de sesión).

A diferencia de `record_samples.py`, acá NO hay split train/test: estos
negativos van a sumarse como una fuente más de `feature_data_files` en
`training_config.yaml` (todos etiquetados clase 0), igual que ACAV100M —
ese cableado queda pendiente para cuando haya grabaciones (no tiene
sentido armarlo contra un directorio vacío, YAGNI).

Uso:
    python tools/wake_word_training/record_hard_negatives.py --count-per-phrase 20

Guarda los `.wav` en `<output-dir>/<frase-normalizada>/`, ej.
`dataset/hard_negatives/oye_mira/<uuid>.wav`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from aries.voice.audio_io import (  # noqa: E402
    MicrophoneListener,
    record_until_silence,
    wav_bytes_to_pcm,
)

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "dataset" / "hard_negatives"

# Las 4 frases pedidas explícitamente: "oye" + otra palabra (para que el
# modelo no aprenda a dispararse solo con "oye"), y "aries" suelta (para
# que tampoco se dispare solo con el nombre). No se agregan variantes no
# pedidas — si hace falta más cobertura, se suma después con --phrases.
DEFAULT_PHRASES = ["oye mira", "oye tu", "oye ya", "aries"]


def _slug(phrase: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", phrase.lower()).strip("_")


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


def _append_session_manifest(output_dir: Path, started_at: str, files: list[str]) -> None:
    if not files:
        return
    entry = {
        "started_at": started_at,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "files": files,  # rutas relativas a output_dir, ej. "oye_mira/<uuid>.wav"
    }
    with (output_dir / "sessions.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phrases",
        nargs="+",
        default=DEFAULT_PHRASES,
        help=f"Frases a grabar (default: {DEFAULT_PHRASES})",
    )
    parser.add_argument("--count-per-phrase", type=int, default=20, help="Tomas a grabar por cada frase")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Carpeta destino (una subcarpeta por frase)")
    parser.add_argument("--max-seconds", type=float, default=4.0, help="Duración máxima por toma antes de cortar por timeout")
    parser.add_argument(
        "--min-rms",
        type=float,
        default=200.0,
        help="RMS mínimo para aceptar una toma sin preguntar — por debajo, se avisa que pudo grabarse en silencio",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    listener = MicrophoneListener()
    session_started_at = datetime.now(timezone.utc).isoformat()
    session_files: list[str] = []

    print(f"Frases a grabar: {args.phrases} — {args.count_per_phrase} tomas cada una.")
    print("Enter para grabar cada toma (graba hasta ~0.6s de silencio o hasta el máximo). Ctrl+C para cortar en cualquier momento.\n")

    try:
        for phrase in args.phrases:
            phrase_dir = args.output_dir / _slug(phrase)
            phrase_dir.mkdir(exist_ok=True)
            n_existing = len(list(phrase_dir.glob("*.wav")))
            remaining = max(0, args.count_per_phrase - n_existing)
            if n_existing:
                print(f"\"{phrase}\": ya hay {n_existing} tomas — faltan {remaining}.")

            recorded = 0
            while recorded < remaining:
                input(f"  [{phrase!r} {n_existing + recorded + 1}/{args.count_per_phrase}] Enter y decí \"{phrase}\"... ")
                wav_bytes, rms = _record_one_take(listener, args.max_seconds)

                if rms < args.min_rms:
                    keep = input(f"    RMS bajo ({rms:.0f}) — ¿parece que no se grabó nada? Guardar igual? [s/N] ")
                    if keep.strip().lower() != "s":
                        print("    Descartada, repetí la toma.")
                        continue

                file_path = phrase_dir / f"{uuid.uuid4().hex}.wav"
                file_path.write_bytes(wav_bytes)
                session_files.append(f"{phrase_dir.name}/{file_path.name}")
                recorded += 1
                print(f"    Guardada (RMS={rms:.0f})")
    except KeyboardInterrupt:
        _append_session_manifest(args.output_dir, session_started_at, session_files)
        print(f"\nCortado por el usuario. Grabadas {len(session_files)} tomas nuevas en esta corrida.")
        return

    _append_session_manifest(args.output_dir, session_started_at, session_files)
    total = sum(len(list((args.output_dir / _slug(p)).glob("*.wav"))) for p in args.phrases)
    print(f"\nListo: {total} tomas totales de negativos difíciles en {args.output_dir}.")


if __name__ == "__main__":
    main()
