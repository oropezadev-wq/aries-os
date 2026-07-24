# Aries OS — Project State

> Fuente de verdad del estado técnico de la arquitectura.
> Este documento describe qué componentes existen realmente y cuál es su nivel de implementación.
>
> No registrar aquí tareas ni historial de cambios.
> Para eso existen PROGRESS.md y CHANGELOG.md.

---

# Estado General

**Nombre del proyecto:** Aries OS

**Tipo:** Plataforma de Inteligencia Artificial Personal

**Estado actual:** Foundation / Core Architecture

**Arquitectura objetivo:**

- Clean Architecture
- Event Driven Architecture
- SOLID
- Dependency Injection
- Plugin Based
- Modular Monolith (preparado para evolucionar a microservicios)

---

# Componentes del Sistema

| Módulo | Estado |
|---------|--------|
| Kernel | 🟡 Parcial |
| Configuration | 🟢 Implementado |
| Logging | 🟢 Implementado |
| Contracts | 🟢 Implementado |
| Exceptions | 🟢 Implementado |
| API | 🟢 Implementado |
| LLM Provider | 🟢 Implementado |
| Memory | 🟡 Parcial |
| Planner | ⚪ No implementado |
| Event Bus | ⚪ No implementado |
| Plugin Manager | ⚪ No implementado |
| Agent Manager | ⚪ No implementado |
| Skills | ⚪ No implementado |
| Voice Pipeline | ⚪ No implementado |
| Desktop Integration | ⚪ No implementado |
| Scheduler | ⚪ No implementado |
| Automation | ⚪ No implementado |
| Security | ⚪ No implementado |
| Storage | ⚪ No implementado |
| Telemetry | ⚪ No implementado |

---

# Dependencias principales

Kernel

↓

Configuration

↓

Logging

↓

Dependency Injection

↓

Event Bus

↓

Planner

↓

Memory

↓

Skills

↓

Agents

↓

Plugins

↓

Infrastructure

---

# Componentes implementados

Actualmente existen implementaciones reales para:

- Configuración mediante Pydantic Settings
- Logging con Structlog
- FastAPI
- Kernel básico
- InMemory Memory Provider
- Ollama Provider
- Interfaces principales
- Tests iniciales

---

# Componentes pendientes

Pendientes de implementación:

- Event Bus
- Planner
- Plugin Manager
- Agent Manager
- Skill Registry
- Context Manager
- Voice Pipeline
- Desktop Controller
- Scheduler
- Security Policies
- Storage persistente
- Telemetry

---

# Principios Arquitectónicos

Todo componente debe:

- Ser desacoplado.
- Depender únicamente de interfaces.
- Ser fácilmente testeable.
- Tener documentación.
- Registrar logs.
- Manejar errores.

---

# Restricciones

Nunca:

- Acoplar módulos.
- Usar variables globales.
- Saltarse el Event Bus.
- Depender directamente de implementaciones concretas.
- Mezclar lógica de negocio con infraestructura.

---

# Próxima Meta Arquitectónica

Construir la infraestructura central:

1. Event Bus
2. Dependency Injection Container
3. Plugin Manager
4. Planner

Después de eso podrán desarrollarse los primeros agentes reales.

---

Última actualización:

Actualizar este documento únicamente cuando cambie la arquitectura del sistema.