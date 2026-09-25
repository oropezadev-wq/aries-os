"""tools/wake_word_training/repartition_positive_split.py — re-reparte
`dataset/positive_train/` + `dataset/positive_test/` con un `positive_test`
más grande, sin tocar `dataset/eval_frozen/` (vive en su propia carpeta,
nunca se toca acá).

No es parte del paquete `aries` — utilidad de desarrollo de un solo uso,
igual que `record_samples.py`.

Por qué (2026-09-24, señalado por el usuario): `positive_test` tenía 8
archivos (split 90/10 original de `record_samples.py`, pensado para
maximizar datos de entrenamiento, no para dar una estimación confiable de
`Final Model Recall` en `auto_train`). Con 8 tomas, ese número es
demasiado ruidoso para usarse como criterio de selección entre corridas
— se confirmó empíricamente: eligió `seed4` (0,5625 en `positive_test`)
sobre `seed2` (0,1875), pero contra `eval_frozen` (30 tomas) el orden
real es el opuesto (`seed2` da 63,3 % de recall @ 0,5 FA/hora, `seed4`
da 16,7 %). Sin un criterio de selección confiable, ningún reentrenamiento
futuro se puede elegir con criterio.

Uso:
    python tools/wake_word_training/repartition_positive_split.py --test-size 28

Determinístico: mismo `--seed` (default 20260924) da siempre el mismo
resultado — documentado en `dataset/POSITIVE_SPLIT_MANIFEST.json`.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATASET_DIR = HERE / "dataset"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-size", type=int, default=28, help="Cantidad de archivos para positive_test tras repartir")
    parser.add_argument("--seed", type=int, default=20260924, help="Semilla del shuffle — determinístico, documentado en el manifest")
    parser.add_argument("--dataset-dir", type=Path, default=DATASET_DIR)
    args = parser.parse_args()

    train_dir = args.dataset_dir / "positive_train"
    test_dir = args.dataset_dir / "positive_test"

    all_files = sorted(p.name for p in train_dir.glob("*.wav")) + sorted(p.name for p in test_dir.glob("*.wav"))
    before = {"positive_train": len(list(train_dir.glob("*.wav"))), "positive_test": len(list(test_dir.glob("*.wav")))}

    if args.test_size >= len(all_files):
        raise SystemExit(f"--test-size {args.test_size} >= total de archivos ({len(all_files)}) — no queda nada para train.")

    rng = random.Random(args.seed)
    shuffled = list(all_files)
    rng.shuffle(shuffled)
    new_test = set(shuffled[: args.test_size])

    moved = []
    for name in all_files:
        target_dir = test_dir if name in new_test else train_dir
        # Buscar en cuál de las dos carpetas está hoy (podría ya estar en target_dir).
        current_path = train_dir / name if (train_dir / name).exists() else test_dir / name
        target_path = target_dir / name
        if current_path != target_path:
            shutil.move(str(current_path), str(target_path))
            moved.append(name)

    after = {"positive_train": len(list(train_dir.glob("*.wav"))), "positive_test": len(list(test_dir.glob("*.wav")))}

    manifest = {
        "repartitioned_at": datetime.now(timezone.utc).isoformat(),
        "reason": "positive_test con 8 archivos era un criterio de selección demasiado ruidoso — "
        "confirmado empíricamente (2026-09-24): eligió mal entre 7 modelos candidatos frente a eval_frozen (30 archivos).",
        "seed": args.seed,
        "before": before,
        "after": after,
        "n_moved": len(moved),
        "note": "dataset/eval_frozen/ NO se tocó — vive en su propia carpeta, ajena a este split.",
    }
    manifest_path = args.dataset_dir / "POSITIVE_SPLIT_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Antes: {before}")
    print(f"Después: {after}")
    print(f"Archivos movidos: {len(moved)}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
