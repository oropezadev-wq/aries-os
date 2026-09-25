"""tools/wake_word_training/evaluate_model.py — evalúa un modelo de wake
word con la métrica que pidió el supervisor (2026-09-22, ver
docs/specs/WakeWordTraining.spec.md, Decisión 5, puntos 2 y 3): falsos
rechazos sobre un set de evaluación congelado, a una tasa fija de falsas
activaciones por hora medida en audio ambiente real — no comparar scores
crudos entre modelos.

No es parte del paquete `aries` — utilidad de desarrollo de un solo uso.

Dos fuentes de datos, cada una para una mitad de la métrica:

- `dataset/eval_frozen/` (Decisión 5, punto 1): tomas reales de la wake
  word que el modelo NUNCA vio en entrenamiento (ni siquiera aumentadas).
  Para cada toma se busca el score máximo con padding de silencio (mismo
  método que se usó en la comparación anterior, PROGRESS.md) — recall(t)
  = fracción de tomas con score máximo >= t. Falso rechazo = 1 - recall.

- `dataset/ambient_audio/` (Decisión 5, punto 3): audio ambiente real
  (TV/video de fondo, sin la wake word) grabado con record_ambient_audio.py.
  Se concatenan los tramos en el orden real de grabación (sessions.jsonl)
  y se corre inferencia frame por frame, continua, igual que
  `OpenWakeWordProvider.process_frame` en producción (no se cortan en
  ejemplos de duración fija como hace la métrica interna de
  `openwakeword.train.Model.fp` — esto mide el comportamiento real en
  streaming, no una aproximación por ventanas). Una "falsa activación" es
  una racha contigua de frames con score >= t (no cada frame por
  separado, que sobrecontaría una misma detección) — FA/hora = eventos /
  horas totales de audio.

Uso:
    python tools/wake_word_training/evaluate_model.py \\
        --model output/oye_aries.onnx --compare-hey-jarvis
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import numpy as np
from scipy.io import wavfile

HERE = Path(__file__).resolve().parent

DEFAULT_THRESHOLDS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
TARGET_FA_PER_HOUR = 0.5  # mismo target_false_positives_per_hour que training_config.yaml


def _load_model(path_or_name: str, key: str):
    from openwakeword.model import Model

    if path_or_name.endswith(".onnx"):
        return Model(wakeword_model_paths=[path_or_name], inference_framework="onnx"), key
    return Model(wakeword_models=[path_or_name], inference_framework="onnx"), path_or_name


def _score_eval_frozen(model, key: str, eval_dir: Path) -> np.ndarray:
    """Score máximo por toma, con 1s de silencio de padding a cada lado
    (mismo método usado en la comparación anterior con hey_jarvis)."""
    files = sorted(glob.glob(str(eval_dir / "*.wav")))
    pad = np.zeros(16000, dtype=np.int16)
    scores = []
    for f in files:
        sr, x = wavfile.read(f)
        if x.ndim > 1:
            x = x[:, 0]
        pcm = np.concatenate([pad, x, pad])
        best = 0.0
        for i in range(0, len(pcm) - 1279, 1280):
            best = max(best, model.predict(pcm[i : i + 1280]).get(key, 0.0))
        scores.append(best)
    return np.array(scores)


def _score_ambient_stream(model, key: str, ambient_dir: Path) -> tuple[np.ndarray, float]:
    """Corre inferencia frame por frame sobre el audio ambiente completo,
    concatenado en el orden real de grabación (sessions.jsonl), como un
    único stream continuo (igual que en producción). Devuelve la serie de
    scores (uno cada 80ms) y la duración total en horas."""
    manifest_path = ambient_dir / "sessions.jsonl"
    ordered_files: list[str] = []
    if manifest_path.exists():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            ordered_files.extend(entry["files"])
    else:
        ordered_files = sorted(p.name for p in ambient_dir.glob("*.wav"))

    scores = []
    total_samples = 0
    for name in ordered_files:
        sr, x = wavfile.read(ambient_dir / name)
        if x.ndim > 1:
            x = x[:, 0]
        total_samples += len(x)
        for i in range(0, len(x) - 1279, 1280):
            scores.append(model.predict(x[i : i + 1280]).get(key, 0.0))
    return np.array(scores), total_samples / 16000 / 3600


def _events_above_threshold(scores: np.ndarray, threshold: float) -> int:
    """Cuenta rachas contiguas de frames >= threshold como un solo evento
    (una detección real dispara varios frames seguidos, no debería
    contarse varias veces)."""
    above = scores >= threshold
    if not above.any():
        return 0
    # +1 en cada transición False->True
    return int(np.sum(above[1:] & ~above[:-1]) + (1 if above[0] else 0))


def _frr_at_fixed_fa_per_hour(
    eval_scores: np.ndarray,
    ambient_scores: np.ndarray,
    ambient_hours: float,
    target_fa_per_hour: float,
    grid_size: int = 400,
) -> tuple[float, float]:
    """Punto de operación real pedido por el supervisor (Decisión 5,
    punto 2 de `docs/specs/WakeWordTraining.spec.md`): falso rechazo
    exactamente en el umbral donde FA/hora == `target_fa_per_hour`, no en
    "el umbral más cercano entre los que se pasaron por `--thresholds`"
    (lo que hacía antes esta función, y que no es un punto de comparación
    objetivo entre corridas si dos corridas usan grillas de umbral
    distintas). Devuelve `(umbral, falso_rechazo)` en ese punto exacto.

    FA/hora(umbral) es monótona no creciente (un umbral más alto nunca
    genera más falsas activaciones); se evalúa en una grilla fina entre
    0.001 y 0.999 (se excluyen los extremos exactos 0/1, degenerados:
    en 0.0 el stream entero cuenta como un único evento contiguo) y se
    interpola linealmente entre los dos puntos que bracketean el target."""
    grid = np.linspace(0.001, 0.999, grid_size)
    fa_curve = np.array([_events_above_threshold(ambient_scores, t) / ambient_hours for t in grid])

    below = np.where(fa_curve < target_fa_per_hour)[0]
    if fa_curve[0] < target_fa_per_hour:
        # Ni el umbral más permisivo de la grilla llega al target: no hay
        # ningún punto de operación real con este modelo/dataset en el
        # rango evaluado. Se informa el extremo, no se fabrica un número.
        recall = float((eval_scores >= grid[0]).mean())
        return float(grid[0]), 1 - recall
    if len(below) == 0:
        recall = float((eval_scores >= grid[-1]).mean())
        return float(grid[-1]), 1 - recall

    hi = int(below[0])
    lo = hi - 1
    t_lo, t_hi = grid[lo], grid[hi]
    fa_lo, fa_hi = fa_curve[lo], fa_curve[hi]
    threshold = t_lo if fa_lo == fa_hi else t_lo + (fa_lo - target_fa_per_hour) / (fa_lo - fa_hi) * (t_hi - t_lo)

    recall = float((eval_scores >= threshold).mean())
    return float(threshold), 1 - recall


def _evaluate(model, key: str, eval_dir: Path, ambient_dir: Path, thresholds: list[float], fa_targets: list[float]) -> None:
    eval_scores = _score_eval_frozen(model, key, eval_dir)
    ambient_scores, ambient_hours = _score_ambient_stream(model, key, ambient_dir)

    print(f"\n=== {key} ===")
    print(f"eval_frozen: n={len(eval_scores)} tomas (nunca vistas en entrenamiento)")
    print(f"ambient_audio: {ambient_hours:.2f} horas, {len(ambient_scores)} frames\n")
    print(f"{'umbral':>7s} {'recall':>8s} {'falso_rechazo':>14s} {'FA/hora':>10s}")

    for t in thresholds:
        recall = float((eval_scores >= t).mean())
        frr = 1 - recall
        n_events = _events_above_threshold(ambient_scores, t)
        fa_per_hour = n_events / ambient_hours
        print(f"{t:7.2f} {recall:8.2%} {frr:14.2%} {fa_per_hour:10.2f}")

    # Curva completa de puntos de operación (no un solo punto a 0.5
    # FA/hora): a mayor FA/hora tolerado, el umbral baja y el recall
    # sube — un solo punto puede esconder que a una tasa más alta (pero
    # todavía usable en la práctica) el modelo sí sirve.
    print("\n=== Curva de puntos de operación (interpolados, comparables entre corridas) ===")
    for target in fa_targets:
        threshold, frr = _frr_at_fixed_fa_per_hour(eval_scores, ambient_scores, ambient_hours, target)
        print(f"@ {target:>4.1f} FA/hora: umbral={threshold:.4f} -> falso_rechazo={frr:.1%} (recall={1 - frr:.1%})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=str(HERE / "output" / "oye_aries.onnx"), help="Ruta a un .onnx custom, o nombre de un modelo preempaquetado (ej. hey_jarvis)")
    parser.add_argument("--eval-dir", type=Path, default=HERE / "dataset" / "eval_frozen")
    parser.add_argument("--ambient-dir", type=Path, default=HERE / "dataset" / "ambient_audio")
    parser.add_argument("--thresholds", type=float, nargs="+", default=DEFAULT_THRESHOLDS)
    parser.add_argument(
        "--fa-targets", type=float, nargs="+", default=[0.5, 1.0, 2.0, 5.0],
        help="Tasas de FA/hora a las que reportar el punto de operación interpolado (curva completa, no un solo punto)",
    )
    parser.add_argument("--compare-hey-jarvis", action="store_true", help="Corre también hey_jarvis sobre los mismos datos, para comparar")
    args = parser.parse_args()

    model, key = _load_model(args.model, "oye_aries")
    _evaluate(model, key, args.eval_dir, args.ambient_dir, args.thresholds, args.fa_targets)

    if args.compare_hey_jarvis:
        hj_model, hj_key = _load_model("hey_jarvis", "hey_jarvis")
        _evaluate(hj_model, hj_key, args.eval_dir, args.ambient_dir, args.thresholds, args.fa_targets)


if __name__ == "__main__":
    main()
