# Contrato: IMemory

## Responsabilidad
Define cómo almacenar, recuperar y gestionar información en memoria.

## Tipos de Memoria
- **conversation**: Historial de conversaciones
- **preference**: Preferencias del usuario
- **profile**: Perfil e información personal
- **document**: Documentos guardados
- **learning**: Cosas aprendidas del usuario
- **automation**: Automatizaciones configuradas
- **context**: Contexto actual

## Métodos Requeridos

### async store(content, memory_type, metadata, importance) → MemoryItem
Guarda información.

**Retorna:** MemoryItem con ID, timestamps, etc.

### async retrieve(memory_id) → Optional[MemoryItem]
Obtiene información por ID.

### async search(query, memory_type, limit) → list[MemoryItem]
Busca información.

**Nota:** Implementar búsqueda fulltext si es posible.

### async delete(memory_id) → bool
Elimina información.

### async clear_expired() → int
Limpia información vieja/vencida.

Retorna cantidad eliminada.

### async get_by_type(memory_type) → list[MemoryItem]
Obtiene todos los items de un tipo.

## Estructura de Base de Datos (Esperada)

```sql
-- Tabla única o múltiples según implementación
memory (
  id UUID PRIMARY KEY,
  type VARCHAR(50),
  content TEXT,
  metadata JSONB,
  importance INT (1-10),
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  expires_at TIMESTAMP,
  
  -- Índices esperados:
  INDEX (type),
  INDEX (created_at),
  FULLTEXT INDEX (content)
)
```

## Implementaciones Esperadas
- PostgreSQLMemory (producción)
- SQLiteMemory (desarrollo)
- RedisMemory (caché)
- VectorMemory (búsqueda semántica con embeddings)
