# Aries OS Blueprint v0.1

Este paquete contiene la documentación inicial del proyecto.
No incluye código; establece la arquitectura y reglas del desarrollo.

## Setup — soporte de voz (opcional)

Si vas a usar `voice/` (`OpenWakeWordProvider`), después de instalar las
dependencias del extra `voice` (`pip install -e ".[voice]"`) hace falta
descargar los modelos pre-entrenados de openWakeWord **una sola vez** —
no vienen empaquetados en el paquete pip:

```bash
python -c "from openwakeword.utils import download_models; download_models()"
```

Sin este paso, `OpenWakeWordProvider` falla al construirse (no encuentra
los archivos `.onnx`/`.tflite` de los modelos). Ver `docs/specs/Voice.spec.md`
para el resto del setup de Voice (modelo de voz de Piper, etc.).
