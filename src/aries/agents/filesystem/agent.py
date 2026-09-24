"""FileSystemAgent: agente IAgent para operaciones de archivos con stdlib.

Alcance deliberado: solo lectura/escritura/listado de archivos y directorios
vía `pathlib`. No ejecuta procesos ni controla el sistema operativo — eso
corresponde a ProcessAgent/WindowsAgent (ver docs/contracts/IAgent.md).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from structlog.stdlib import BoundLogger

from ...contracts.agent import ActionResult, ActionStatus, IAgent
from ...logging import get_logger

_HandlerResult = tuple[str, dict[str, Any]]


class FileSystemAgent(IAgent):
    """Agente que ejecuta operaciones de archivos y directorios.

    `open_file`/`read_file` y `create_file`/`write_file` son pares de alias:
    el contrato no distingue "abrir" de "leer" ni "crear" de "escribir" para
    un agente sin estado (no hay un handle de archivo que quede abierto), y
    `write_file` con `content` por defecto vacío ya cubre "crear un archivo
    vacío". Única diferencia entre el par: `create_file` no sobrescribe un
    archivo existente por defecto (falla con `FileExistsError`), mientras
    que `write_file` sí, porque "crear" que trunque silenciosamente algo
    que ya existe sería sorprendente. Ambos aceptan `overwrite` explícito.
    """

    _ALIASES: dict[str, str] = {
        "open_file": "read_file",
        "create_file": "write_file",
    }

    _DESTRUCTIVE_ACTIONS: frozenset[str] = frozenset({"delete_file"})

    def __init__(self, allowed_root: str = "") -> None:
        self.logger: BoundLogger = get_logger(self.__class__.__name__)
        self._handlers: dict[str, Callable[..., Awaitable[_HandlerResult]]] = {
            "read_file": self._read_file,
            "list_directory": self._list_directory,
            "create_directory": self._create_directory,
            "delete_file": self._delete_file,
            "write_file": self._write_file,
        }
        # Auditoría de seguridad 2026-09-23, hallazgo ALTO #3: sin esto,
        # cualquier `path` absoluto del disco era alcanzable (path
        # traversal / acceso a cualquier archivo). "" = sin raíz
        # configurada -> falla cerrado (decisión del usuario, no hay
        # default permisivo como el home del usuario). `.resolve()` una
        # sola vez acá, no en cada llamada — validado en Windows: resuelve
        # nombres 8.3 a su forma larga y normaliza mayúsculas/minúsculas,
        # ver docs/audits/2026-09-23-security-audit.md.
        self._allowed_root: Path | None = Path(allowed_root).resolve() if allowed_root else None

    def _resolve_within_root(self, path: str) -> Path:
        """Resuelve `path` y verifica que quede contenido en
        `self._allowed_root` — comparación estructural de componentes de
        ruta (`is_relative_to`), nunca de texto (un prefijo de string como
        `/allowed` matchearía `/allowed_evil`, `is_relative_to` no).
        Lanza `PermissionError` (ya manejado por `execute()`) si no hay
        raíz configurada o si la ruta cae afuera."""
        if self._allowed_root is None:
            raise PermissionError(
                "FileSystemAgent no tiene una raíz permitida configurada "
                "(Settings.filesystem_allowed_root) — todas las acciones de archivo están bloqueadas"
            )
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(self._allowed_root):
            raise PermissionError(f"Ruta fuera de la raíz permitida ({self._allowed_root}): {path}")
        return resolved

    def get_agent_name(self) -> str:
        return "filesystem"

    def get_capabilities(self) -> list[str]:
        return [
            "open_file",
            "read_file",
            "list_directory",
            "create_directory",
            "delete_file",
            "create_file",
            "write_file",
        ]

    def requires_confirmation(self, action: str, **_: Any) -> bool:
        # `**_` acá solo por consistencia con los otros 3 IAgent reales
        # (ProcessAgent/GitAgent/DatabaseAgent aceptan kwargs de extensión
        # opcionales) — FileSystemAgent no necesita ninguno en particular,
        # decide únicamente por el nombre de la acción.
        canonical = self._ALIASES.get(action, action)
        return canonical in self._DESTRUCTIVE_ACTIONS

    async def is_available(self) -> bool:
        return True

    async def execute(self, action: str, **kwargs: Any) -> ActionResult:
        canonical = self._ALIASES.get(action, action)
        handler = self._handlers.get(canonical)

        if handler is None:
            return ActionResult(
                status=ActionStatus.FAILED,
                error=f"Acción desconocida para FileSystemAgent: '{action}'",
            )

        if action == "create_file" and "overwrite" not in kwargs:
            kwargs = {**kwargs, "overwrite": False}

        path = kwargs.get("path", "")
        start = time.perf_counter()

        try:
            output, data = await handler(**kwargs)
        except FileNotFoundError:
            return self._failed(f"No existe el archivo o directorio: {path}", start)
        except PermissionError:
            return self._failed(f"Permiso denegado al acceder a: {path}", start)
        except FileExistsError:
            return self._failed(f"Ya existe: {path}", start)
        except IsADirectoryError:
            return self._failed(f"La ruta es un directorio, no un archivo: {path}", start)
        except NotADirectoryError:
            return self._failed(f"La ruta no es un directorio: {path}", start)
        except TypeError as error:
            return self._failed(f"Parámetros inválidos para '{action}': {error}", start)
        except OSError as error:
            return self._failed(f"Error del sistema de archivos en '{path}': {error}", start)

        execution_time_ms = (time.perf_counter() - start) * 1000
        self.logger.info("Acción de archivo completada", action=action, path=path)
        return ActionResult(
            status=ActionStatus.SUCCESS,
            output=output,
            data=data,
            execution_time_ms=execution_time_ms,
        )

    def _failed(self, error: str, start: float) -> ActionResult:
        execution_time_ms = (time.perf_counter() - start) * 1000
        self.logger.warning("Acción de archivo falló", error=error)
        return ActionResult(
            status=ActionStatus.FAILED,
            error=error,
            execution_time_ms=execution_time_ms,
        )

    async def _read_file(self, path: str, **_: Any) -> _HandlerResult:
        file_path = self._resolve_within_root(path)
        content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
        return content, {"path": str(file_path), "size": len(content)}

    async def _list_directory(self, path: str, **_: Any) -> _HandlerResult:
        dir_path = self._resolve_within_root(path)
        if not dir_path.exists():
            raise FileNotFoundError(path)
        if not dir_path.is_dir():
            raise NotADirectoryError(path)

        entries = [
            {"name": entry.name, "is_dir": entry.is_dir()}
            for entry in sorted(dir_path.iterdir(), key=lambda entry: entry.name)
        ]
        return f"{len(entries)} elemento(s) en {path}", {"path": str(dir_path), "entries": entries}

    async def _create_directory(
        self, path: str, parents: bool = True, exist_ok: bool = False, **_: Any
    ) -> _HandlerResult:
        dir_path = self._resolve_within_root(path)
        dir_path.mkdir(parents=parents, exist_ok=exist_ok)
        return f"Directorio creado: {path}", {"path": str(dir_path)}

    async def _delete_file(self, path: str, **_: Any) -> _HandlerResult:
        file_path = self._resolve_within_root(path)
        if not file_path.exists():
            raise FileNotFoundError(path)
        if file_path.is_dir():
            raise IsADirectoryError(path)

        file_path.unlink()
        return f"Archivo eliminado: {path}", {"path": str(file_path)}

    async def _write_file(
        self, path: str, content: str = "", overwrite: bool = True, **_: Any
    ) -> _HandlerResult:
        file_path = self._resolve_within_root(path)
        if file_path.is_dir():
            raise IsADirectoryError(path)
        if file_path.exists() and not overwrite:
            raise FileExistsError(path)

        await asyncio.to_thread(file_path.write_text, content, encoding="utf-8")
        return (
            f"Archivo escrito: {path}",
            {"path": str(file_path), "bytes_written": len(content.encode("utf-8"))},
        )
