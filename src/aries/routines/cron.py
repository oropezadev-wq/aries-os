"""routines/cron.py — traduce el `schedule` amigable de un archivo de
rutina a una expresión cron de 5 campos, para no obligar a nadie a
escribir cron a mano (Routines.spec.md sección 1).

Convención de días: el atajo (`days_of_week` en el archivo de rutina)
usa **ISO/Python (0=lunes...6=domingo)**; cron usa **0=domingo...6=sábado**
(con `7` también válido como domingo, no usado acá). La traducción es
`cron_dow = (iso_dow + 1) % 7` — tabla completa abajo, para que nadie
tenga que redescubrirla leyendo el código:

| ISO (lunes=0) | 0 (lun) | 1 (mar) | 2 (mié) | 3 (jue) | 4 (vie) | 5 (sáb) | 6 (dom) |
|---|---|---|---|---|---|---|---|
| cron (domingo=0) | 1 | 2 | 3 | 4 | 5 | 6 | 0 |
"""

from __future__ import annotations

from typing import Any

_ISO_TO_CRON_DOW = {iso: (iso + 1) % 7 for iso in range(7)}


class ScheduleError(Exception):
    """`schedule` inválido en un archivo de rutina — nunca debe llegar
    sin capturar a quien orquesta la carga (`loader.py`)."""


def schedule_to_cron(schedule: dict[str, Any]) -> str:
    """Traduce `{"time": "HH:MM", "days_of_week": [...]}` a una expresión
    cron de 5 campos. `days_of_week` es opcional — ausente/vacío/`None`
    significa "todos los días", igual que documenta Routines.spec.md
    sección 1.

    Raises:
        ScheduleError: `time` ausente/mal formado, o `days_of_week` con
            un valor fuera de `0-6`.
    """
    time_value = schedule.get("time")
    if not isinstance(time_value, str):
        raise ScheduleError(f"'schedule.time' debe ser un string 'HH:MM': {time_value!r}")

    parts = time_value.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ScheduleError(f"'schedule.time' debe tener formato 'HH:MM': {time_value!r}")

    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ScheduleError(f"'schedule.time' fuera de rango: {time_value!r}")

    days_of_week = schedule.get("days_of_week")
    if not days_of_week:
        cron_dow_field = "*"
    else:
        if not isinstance(days_of_week, list) or not all(isinstance(day, int) for day in days_of_week):
            raise ScheduleError(f"'schedule.days_of_week' debe ser una lista de enteros: {days_of_week!r}")
        try:
            cron_days = sorted({_ISO_TO_CRON_DOW[day] for day in days_of_week})
        except KeyError as error:
            raise ScheduleError(f"'schedule.days_of_week' fuera de rango (0-6, lunes=0): {days_of_week!r}") from error
        cron_dow_field = ",".join(str(day) for day in cron_days)

    return f"{minute} {hour} * * {cron_dow_field}"
