"""tools/wake_word_training/run_training.py — corre augmentación +
entrenamiento de `openwakeword` manualmente, sin pasar por
`openwakeword/train.py` como `__main__`.

Por qué no usar `train.py` directo: su bloque `__main__` hace
`sys.path.insert(0, config["piper_sample_generator_path"])` seguido de
`from generate_samples import generate_samples` **incondicionalmente**,
aunque no se pase `--generate_clips` — y ese módulo (parte de
`piper-sample-generator`) importa `torchaudio`, `webrtcvad`,
`espeak_phonemizer` y `piper_train.vits`, ninguna instalada ni necesaria
acá (nuestras muestras positivas son grabaciones reales, no TTS). Este
script importa `openwakeword.train` como módulo — su bloque `__main__`
nunca se ejecuta — y llama directo a las piezas que sí necesitamos
(`augment_clips`, `compute_features_from_generator`, `Model.auto_train`).

Ver docs/specs/WakeWordTraining.spec.md para el contexto completo.
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import numpy as np
import scipy.io.wavfile
import scipy.special
import yaml

# Shim: `acoustics` (dependencia transitiva de openwakeword.data, sin uso
# real en este entrenamiento — solo hace falta que el import no reviente)
# importa `scipy.special.sph_harm`, removido en scipy>=1.15 a favor de
# `sph_harm_y`. No se llama ninguna función real de `acoustics.directivity`
# en este script, así que un shim aproximado alcanza.
if not hasattr(scipy.special, "sph_harm"):
    from scipy.special import sph_harm_y

    def _sph_harm_compat(m, n, theta, phi):
        return sph_harm_y(n, m, phi, theta)

    scipy.special.sph_harm = _sph_harm_compat

import torch  # noqa: E402
import torchaudio  # noqa: E402

# Shim: la versión instalada de torchaudio removió sus backends de
# decodificación propios (sox/soundfile) a favor de TorchCodec, que a su
# vez necesita FFmpeg instalado como librería nativa del sistema — no
# presente en esta máquina, y no queremos depender de un binario externo
# instalado a mano solo para leer WAVs PCM planos (que es todo lo que
# `augment_clips` necesita: nuestras grabaciones reales y los RIR de
# MIT_environmental_impulse_responses son WAV 16-bit sin comprimir).
# Se reemplaza `torchaudio.load` por una versión con `scipy.io.wavfile`,
# devolviendo el mismo formato (Tensor `(canales, muestras)` float32 en
# [-1, 1] + sample rate) que `augment_clips`/`reverberate` esperan.
def _wav_load_shim(path, *_args, **_kwargs):
    sr, data = scipy.io.wavfile.read(str(path))
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        data = data.astype(np.float32) / 2147483648.0
    elif data.dtype == np.uint8:
        data = (data.astype(np.float32) - 128.0) / 128.0
    else:
        data = data.astype(np.float32)
    data = data[None, :] if data.ndim == 1 else data.T
    return torch.from_numpy(np.ascontiguousarray(data)), sr


torchaudio.load = _wav_load_shim

import gc  # noqa: E402

import openwakeword.data as _owd  # noqa: E402
from numpy.lib.format import open_memmap  # noqa: E402
from openwakeword.data import augment_clips  # noqa: E402
from openwakeword.train import Model  # noqa: E402
from openwakeword.utils import AudioFeatures, compute_features_from_generator  # noqa: E402


# Shim: `trim_mmap` (openwakeword.data) hace `np.load(path, mmap_mode='r')`
# y después `os.remove(path)` sobre ESE MISMO archivo — pero quien la llama
# (`compute_features_from_generator`, en utils.py) todavía tiene su propio
# mmap `fp` abierto sobre el mismo archivo en ese momento (nunca lo cierra
# antes de llamar a `trim_mmap`). En Linux/Mac se puede hacer `unlink` de
# un archivo con handles abiertos; en Windows no, así que `os.remove`
# revienta con PermissionError sin importar cuántos `del`/`gc.collect()` se
# hagan del lado de `trim_mmap` — el handle que bloquea vive en el frame
# del caller, fuera de nuestro alcance para cerrarlo desde acá.
#
# Salida real: en nuestro caso `n_total` que le pasamos a
# `compute_features_from_generator` siempre es exacto (contamos los
# archivos de verdad antes de augmentar, no estimamos), así que el array
# se llena completo y no quedan filas vacías al final para recortar —
# `trim_mmap` no tiene nada que hacer, solo repetía el archivo por las
# dudas. Se verifica igual (por si alguna vez `n_total` queda corto) y
# solo se hace la copia+swap si de verdad hace falta recortar algo.
def _trim_mmap_windows_safe(mmap_path: str) -> None:
    mmap_file1 = np.load(mmap_path, mmap_mode="r")
    i = -1
    while np.all(mmap_file1[i, :, :] == 0):
        i -= 1
    n_new = mmap_file1.shape[0] + i + 1

    if n_new == mmap_file1.shape[0]:
        del mmap_file1
        return

    output_file2 = str(Path(mmap_path).with_suffix("")) + "_trimmed.npy"
    mmap_file2 = open_memmap(output_file2, mode="w+", dtype=np.float32, shape=(n_new, mmap_file1.shape[1], mmap_file1.shape[2]))
    for i in range(0, mmap_file1.shape[0], 1024):
        end = min(i + 1024, n_new)
        if i >= n_new:
            break
        mmap_file2[i:end] = mmap_file1[i:end].copy()
        mmap_file2.flush()

    del mmap_file2
    del mmap_file1
    gc.collect()

    os.remove(mmap_path)
    os.rename(output_file2, mmap_path)


_owd.trim_mmap = _trim_mmap_windows_safe

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("run_training")

HERE = Path(__file__).resolve().parent


def _median_clip_length(wav_files: list[Path]) -> int:
    """Duración total de clip a usar (en muestras @16kHz), igual criterio
    que `openwakeword/train.py`: mediana de las grabaciones reales + margen."""
    durations = []
    for f in wav_files:
        _sr, data = scipy.io.wavfile.read(str(f))
        durations.append(len(data))
    total_length = int(round(np.median(durations) / 1000) * 1000) + 12000
    if total_length < 32000:
        total_length = 32000
    elif abs(total_length - 32000) <= 4000:
        total_length = 32000
    return total_length


def _make_features(
    positive_train_dir: Path,
    positive_test_dir: Path,
    rir_paths: list[str],
    background_paths: list[str],
    config: dict,
    model_dir: Path,
    overwrite: bool,
) -> tuple[Path, Path, int]:
    train_files = list(positive_train_dir.glob("*.wav"))
    test_files = list(positive_test_dir.glob("*.wav"))
    total_length = _median_clip_length(test_files or train_files)
    logger.info("total_length (muestras @16kHz): %d", total_length)

    positive_features_train = model_dir / "positive_features_train.npy"
    positive_features_test = model_dir / "positive_features_test.npy"

    if overwrite or not positive_features_train.exists() or not positive_features_test.exists():
        rounds = config.get("augmentation_rounds", 1)
        train_clips = [str(p) for p in train_files] * rounds
        test_clips = [str(p) for p in test_files] * rounds

        n_cpus = max(1, (os.cpu_count() or 1) // 2)

        logger.info("Augmentando + extrayendo features de %d clips de train...", len(train_clips))
        train_gen = augment_clips(
            train_clips,
            total_length=total_length,
            batch_size=config["augmentation_batch_size"],
            background_clip_paths=background_paths,
            RIR_paths=rir_paths,
        )
        compute_features_from_generator(
            train_gen,
            n_total=len(train_clips),
            clip_duration=total_length,
            output_file=str(positive_features_train),
            device="cpu",
            ncpu=n_cpus,
        )

        logger.info("Augmentando + extrayendo features de %d clips de test...", len(test_clips))
        test_gen = augment_clips(
            test_clips,
            total_length=total_length,
            batch_size=config["augmentation_batch_size"],
            background_clip_paths=background_paths,
            RIR_paths=rir_paths,
        )
        compute_features_from_generator(
            test_gen,
            n_total=len(test_clips),
            clip_duration=total_length,
            output_file=str(positive_features_test),
            device="cpu",
            ncpu=n_cpus,
        )
    else:
        logger.info("Features positivas ya existen en disco, se reusan (--overwrite-features para recalcular)")

    return positive_features_train, positive_features_test, total_length


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=HERE / "training_config.yaml")
    parser.add_argument("--steps", type=int, default=None, help="Override de config['steps'] — usar un número chico para una corrida de prueba")
    parser.add_argument("--overwrite-features", action="store_true")
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    if args.steps is not None:
        config["steps"] = args.steps

    output_dir = (HERE / config["output_dir"]).resolve()
    model_dir = output_dir / config["model_name"]
    model_dir.mkdir(parents=True, exist_ok=True)

    positive_train_dir = HERE / "dataset" / "positive_train"
    positive_test_dir = HERE / "dataset" / "positive_test"
    n_train = len(list(positive_train_dir.glob("*.wav")))
    n_test = len(list(positive_test_dir.glob("*.wav")))
    if n_train == 0 or n_test == 0:
        raise SystemExit(f"No hay grabaciones en {positive_train_dir} / {positive_test_dir} — correr record_samples.py primero.")
    logger.info("Positivas reales: %d train, %d test", n_train, n_test)

    rir_paths: list[str] = []
    for rel in config.get("rir_paths", []):
        d = HERE / rel
        if d.exists():
            rir_paths.extend(str(p) for p in d.glob("*") if p.is_file())
    background_paths: list[str] = []
    for rel in config.get("background_paths", []):
        d = HERE / rel
        if d.exists():
            background_paths.extend(str(p) for p in d.glob("*") if p.is_file())
    logger.info("RIR: %d archivos, ruido de fondo: %d archivos", len(rir_paths), len(background_paths))
    if not background_paths:
        logger.warning("Sin ruido de fondo (background_paths vacío) — la augmentación solo aplica reverb, no mezcla de ruido/música.")

    positive_features_train, positive_features_test, total_length = _make_features(
        positive_train_dir, positive_test_dir, rir_paths, background_paths, config, model_dir, args.overwrite_features
    )

    # --- Entrenamiento ---
    F = AudioFeatures(device="cpu")
    # OJO: `total_length` (en muestras) no siempre es múltiplo exacto de
    # 16000 para grabaciones reales (a diferencia de clips TTS, que suelen
    # rendear a duraciones más "redondas") — hay que usar división real
    # (`/16000`, segundos con decimales) para que el shape coincida con el
    # que produjo `compute_features_from_generator` más arriba (que hace
    # lo mismo internamente). Usar `//16000` acá daría un `input_shape`
    # más chico que las features ya calculadas, y `Model(...)` esperaría
    # menos frames por ejemplo de los que realmente hay.
    input_shape = F.get_embedding_shape(total_length / 16000)
    logger.info("input_shape del modelo: %s", input_shape)

    oww = Model(
        n_classes=1,
        input_shape=input_shape,
        model_type=config["model_type"],
        layer_dim=config["layer_size"],
        seconds_per_example=1280 * input_shape[0] / 16000,
    )

    def _reshape_to_input_shape(x: np.ndarray, n: int = input_shape[0]) -> np.ndarray:
        """Ajusta features de un dataset externo (con otra cantidad de
        frames por ejemplo) a `input_shape[0]` frames por ejemplo."""
        if n != x.shape[1]:
            x = np.vstack(x)
            return np.array([x[i : i + n, :] for i in range(0, x.shape[0] - n, n)])
        return x

    negative_sources = {name: str((HERE / rel).resolve()) for name, rel in config["feature_data_files"].items()}
    feature_data_files = dict(negative_sources)
    feature_data_files["positive"] = str(positive_features_train.resolve())

    data_transforms = {name: _reshape_to_input_shape for name in negative_sources}
    label_transforms = {name: (lambda x: [0 for _ in x]) for name in negative_sources}
    label_transforms["positive"] = lambda x: [1 for _ in x]

    n_per_class = {k: v for k, v in config["batch_n_per_class"].items() if k in feature_data_files}
    logger.info("n_per_class por batch: %s", n_per_class)

    from openwakeword.data import mmap_batch_generator

    batch_generator = mmap_batch_generator(
        feature_data_files,
        n_per_class=n_per_class,
        data_transform_funcs=data_transforms,
        label_transform_funcs=label_transforms,
    )

    class IterDataset(torch.utils.data.IterableDataset):
        def __init__(self, generator):
            self.generator = generator

        def __iter__(self):
            return self.generator

    X_train = torch.utils.data.DataLoader(IterDataset(batch_generator), batch_size=None)

    X_val_fp = np.load(config["false_positive_validation_data_path"] if Path(config["false_positive_validation_data_path"]).is_absolute() else str((HERE / config["false_positive_validation_data_path"]).resolve()))
    X_val_fp = np.array([X_val_fp[i : i + input_shape[0]] for i in range(0, X_val_fp.shape[0] - input_shape[0], input_shape[0])])
    X_val_fp_labels = np.zeros(X_val_fp.shape[0]).astype(np.float32)
    X_val_fp_loader = torch.utils.data.DataLoader(
        torch.utils.data.TensorDataset(torch.from_numpy(X_val_fp), torch.from_numpy(X_val_fp_labels)),
        batch_size=len(X_val_fp_labels),
    )

    # Set de validación "limpio" (accuracy/recall durante el entrenamiento):
    # positivas reales de test vs. una muestra chica de la primera fuente de
    # negativos configurada (no tenemos negativos adversariales sintéticos
    # todavía, ver docs/specs/WakeWordTraining.spec.md).
    X_val_pos = np.load(positive_features_test)
    first_negative_key = next(iter(negative_sources))
    neg_source = np.load(negative_sources[first_negative_key], mmap_mode="r")
    # Igual que en el batch de training: las features de ACAV100M vienen en
    # ventanas de 16 frames, pero `input_shape[0]` (derivado de la duración
    # real de nuestros clips) puede ser distinto — se re-empaquetan con la
    # misma transformación (`_reshape_to_input_shape`) antes de comparar.
    n_raw_neg = min(max(len(X_val_pos) * 4 * input_shape[0] // 16 + 16, 32), neg_source.shape[0])
    idx = np.random.choice(neg_source.shape[0], size=n_raw_neg, replace=False)
    X_val_neg = _reshape_to_input_shape(np.asarray(neg_source[np.sort(idx)]), n=input_shape[0])
    if len(X_val_neg) > len(X_val_pos) * 4:
        X_val_neg = X_val_neg[: len(X_val_pos) * 4]

    labels = np.hstack((np.ones(X_val_pos.shape[0]), np.zeros(X_val_neg.shape[0]))).astype(np.float32)
    X_val = torch.utils.data.DataLoader(
        torch.utils.data.TensorDataset(torch.from_numpy(np.vstack((X_val_pos, X_val_neg))), torch.from_numpy(labels)),
        batch_size=len(labels),
    )

    logger.info("Arrancando auto_train (steps=%s)...", config["steps"])
    best_model = oww.auto_train(
        X_train=X_train,
        X_val=X_val,
        false_positive_val_data=X_val_fp_loader,
        steps=config["steps"],
        max_negative_weight=config["max_negative_weight"],
        target_fp_per_hour=config["target_false_positives_per_hour"],
    )

    oww.export_model(model=best_model, model_name=config["model_name"], output_dir=str(output_dir))
    logger.info("Modelo exportado: %s", output_dir / f"{config['model_name']}.onnx")


if __name__ == "__main__":
    main()
