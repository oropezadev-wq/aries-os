# Contrato: ILLMProvider

## Responsabilidad
Define cómo interactuar con proveedores de LLM sin dependencias específicas.

## Métodos Requeridos

### async complete(prompt, temperature, max_tokens, **kwargs) → LLMResponse
Genera texto basado en un prompt.

**Parámetros:**
- `prompt` (str): Texto a procesar
- `temperature` (float): Creatividad (0-1)
- `max_tokens` (int, opcional): Límite de tokens

**Retorna:** `LLMResponse` con:
- `content`: Texto generado
- `model`: Nombre del modelo usado
- `tokens_used`: Tokens consumidos (si disponible)

**Excepciones:**
- `LLMProviderError`: Error de proveedor
- `TimeoutError`: Timeout de respuesta

### async embed(text) → list[float]
Genera embedding (vector) de texto.

**Retorna:** Lista de números flotantes (dimensionalidad variable según modelo)

### is_available() → bool
Valida que el proveedor está operativo.

Verifica: conectividad, credenciales, modelo cargado.

### get_model_name() → str
Retorna el nombre del modelo actual.

## Implementaciones Conocidas
- OllamaProvider (local)
- OpenAIProvider (cloud)
- ClaudeProvider (cloud, Anthropic)
- GeminiProvider (cloud, Google)
- LMStudioProvider (local)

## Casos de Uso

**Usar Ollama localmente:**
```python
llm = OllamaProvider("neural-chat")
response = await llm.complete("¿Cuál es tu nombre?")
print(response.content)
```

**Usar OpenAI en producción:**
```python
llm = OpenAIProvider(api_key="sk-...")
response = await llm.complete("Explicar Aries OS")
```

## Restricciones
- No asumir modelo específico en el kernel
- Soportar cambio de proveedor en runtime
- Manejar timeouts gracefully
