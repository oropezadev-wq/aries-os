"""tools/wake_word_training/record_ambient_audio.py — graba audio ambiente
real y continuo (TV/videos de fondo, sin decir la wake word) para medir
falsas activaciones del modelo en condiciones de uso real.

Punto 3 del pedido del supervisor (2026-09-22, ver
`docs/specs/WakeWordTraining.spec.md`, Decisión 5): ni el falso-rechazo
sobre `dataset/eval_frozen/` ni el entrenamiento con negativos genéricos
(ACAV100M) miden esto — hace falta audio ambiente real, grabado con el
mismo micrófono que usaría Aries en producción.

No es parte del paquete `aries` (no se importa desde `src/`) — utilidad de
desarrollo de un solo uso, hermana de `record_samples.py`/
`record_hard_negatives.py`, pero con una mecánica distinta: acá NO hay
frase para decir ni corte por silencio — es captura continua durante un
tiempo objetivo, usando `MicrophoneListener.read_frame()` directo (mismo
frame de 1280 muestras @16kHz que espera openWakeWord) en vez de
`record_until_silence` (que cortaría en cualquier pausa del audio de
fondo, que es justo lo que NO queremos acá).

Se graba en tramos de `--chunk-minutes` (default 10) en vez de un único
archivo gigante: si algo se corta a mitad de camino, no se pierde todo lo
grabado antes, y los archivos quedan de un tamaño manejable para
escuchar/revisar.

Uso:
    python tools/wake_word_training/record_ambient_audio.py --minutes 90 --label "youtube variado"

Guarda los `.wav` (16kHz mono int16, igual formato que el resto del
pipeline) en `<output-dir>/`, con nombres `uuid4().hex.wav`, y un
manifiesto en `<output-dir>/sessions.jsonl` (igual convención que los
otros dos scripts de grabación).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from aries.voice.audio_io import MicrophoneListener, pcm_to_wav_bytes  # noqa: E402

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "dataset" / "ambient_audio"
SAMPLE_RATE = 16000


def _append_session_manifest(output_dir: Path, entry: dict) -> None:
    with (output_dir / "sessions.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=float, default=90.0, help="Duración total objetivo, en minutos")
    parser.add_argument("--chunk-minutes", type=float, default=10.0, help="Duración de cada archivo .wav")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--label", default="", help="Descripción corta de qué está sonando (ej. 'youtube variado') — solo para el manifiesto")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(args.output_dir.glob("*.wav"))
    existing_minutes = 0.0
    if existing:
        import wave

        for f in existing:
            with wave.open(str(f), "rb") as wf:
                existing_minutes += wf.getnframes() / wf.getframerate() / 60
        print(f"Ya hay {len(existing)} archivos ({existing_minutes:.1f} min) en {args.output_dir} — se completa hasta la meta.")

    remaining_minutes = max(0.0, args.minutes - existing_minutes)
    if remaining_minutes <= 0:
        print(f"Ya se alcanzó la meta de {args.minutes:.0f} min. Nada que grabar (pasá --minutes más alto si querés más).")
        return

    n_chunks = max(1, round(remaining_minutes / args.chunk_minutes))
    frames_per_chunk = int(args.chunk_minutes * 60 * SAMPLE_RATE / 1280)

    print(f"Grabando ~{remaining_minutes:.0f} min más, en {n_chunks} tramos de ~{args.chunk_minutes:.0f} min.")
    print("Arrancá el audio de fondo (YouTube/TV) AHORA, antes de tocar Enter.")
    input("Enter para empezar a grabar... ")

    session_started_at = datetime.now(timezone.utc).isoformat()
    chunk_files: list[str] = []
    listener = MicrophoneListener()

    try:
        with listener:
            for chunk_idx in range(n_chunks):
                chunk_start = time.monotonic()
                frames: list = []
                for _ in range(frames_per_chunk):
                    frames.append(listener.read_frame())
                pcm = b"".join(f.tobytes() for f in frames)
                wav_bytes = pcm_to_wav_bytes(pcm, sample_rate=SAMPLE_RATE)

                file_path = args.output_dir / f"{uuid.uuid4().hex}.wav"
                file_path.write_bytes(wav_bytes)
                chunk_files.append(file_path.name)

                elapsed_min = (time.monotonic() - chunk_start) / 60
                total_min = existing_minutes + (chunk_idx + 1) * args.chunk_minutes
                print(f"  Tramo {chunk_idx + 1}/{n_chunks} guardado ({elapsed_min:.1f} min) — {total_min:.0f} min totales acumulados.")
    except KeyboardInterrupt:
        print(f"\nCortado por el usuario. {len(chunk_files)} tramos nuevos guardados en esta corrida.")
    finally:
        _append_session_manifest(
            args.output_dir,
            {
                "started_at": session_started_at,
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "label": args.label,
                "chunk_minutes": args.chunk_minutes,
                "files": chunk_files,
            },
        )

    total_final = existing_minutes + len(chunk_files) * args.chunk_minutes
    print(f"\nListo: ~{total_final:.0f} min totales de audio ambiente en {args.output_dir}.")


if __name__ == "__main__":
    main()
