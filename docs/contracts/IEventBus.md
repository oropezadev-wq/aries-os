# Contrato: IEventBus

## Responsabilidad
Define la interfaz para un bus de eventos asincrónico desacoplado, permitiendo que los componentes publiquen y consuman eventos sin depender de una implementación específica.

## Métodos Requeridos

### async publish(event: BaseEvent) -> None
Publica un evento en el bus.

- Debe notificar a todos los handlers suscritos por tipo de evento.
- Debe permitir suscripciones tanto por nombre de evento (`str`) como por clase de evento.
- No debe provocar excepciones no controladas cuando no hay handlers registrados.

### async subscribe(event_type: EventType, handler: Handler) -> None
Suscribe un handler a un tipo de evento.

- `event_type` puede ser un `str` o una subclase de `BaseEvent`.
- `handler` puede ser una función síncrona o asíncrona que reciba un `BaseEvent`.
- La implementación debe normalizar el tipo de evento de manera estable.

### async unsubscribe(event_type: EventType, handler: Handler) -> None
Desuscribe un handler de un tipo de evento.

- No debe fallar si el handler no estaba registrado.
- Debe limpiar entradas internas cuando no queden handlers para un evento.

## Tipos auxiliares

- `Handler`: puede ser un `AsyncEventHandler` o un `EventHandler`.
- `EventType`: puede ser un `str` o una subclase de `BaseEvent`.
