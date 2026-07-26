"""GitAgent: agente IAgent para operaciones Git sobre el binario `git` vía
subprocess, sin librerías nuevas (no `GitPython`, no `pygit2`).

Alcance deliberado: el set de operaciones de Git listado en `get_capabilities()`.
No expone un `run_git_command(command: str)` genérico tipo `ProcessAgent.run_command`
— cada capacidad arma su propio argv explícito a partir de kwargs validados,
nunca interpola texto libre del caller directamente en un comando de shell.
`shell=False` siempre, igual que `FileSystemAgent`/`ProcessAgent`.

Notas de diseño (decisiones tomadas sin bloquear — sesión nocturna autónoma,
revisables mañana; ver también PROGRESS.md):

- **Sin aislamiento de SO.** A diferencia de `ProcessAgent` (que depende de
  `tasklist`, exclusivo de Windows), `git` es el mismo binario con el mismo
  comportamiento en Windows/Linux/Mac — no hay ninguna llamada específica de
  SO que aislar acá. No se agregó un `_require_windows()` ni equivalente
  porque no hace falta; agregarlo hubiera sido detección de SO sin propósito.
- **`ActionResult.status` refleja el resultado semántico de la operación de
  Git, no solo si el proceso pudo arrancar** — a diferencia de
  `ProcessAgent.run_command`/`run_script`, donde `SUCCESS` significa "el
  shell/intérprete corrió" independientemente del `exit_code` del programa
  ejecutado. Acá cada capacidad es una operación con significado propio
  (`commit`, `push`, etc.), así que `exit_code != 0` → `ActionResult.FAILED`
  con `error` tomado de `stderr` (o `stdout` si `stderr` viene vacío — Git no
  es consistente sobre a qué stream manda sus mensajes: `checkout`/`push`
  escriben su resumen a stderr incluso en éxito; `reset --hard`/`pull` usan
  stdout; verificado empíricamente, no asumido). Es una decisión deliberada,
  no un descuido: para un agente con capacidades semánticas específicas
  (como `FileSystemAgent`), que `execute()` refleje el éxito real de la
  operación es más útil para quien llama que obligarlo a inspeccionar
  `data["exit_code"]` siempre.
- **`repo_path` es un kwarg por-llamada, no un estado del agente** — mismo
  patrón que `path`/`cwd` en `FileSystemAgent`/`ProcessAgent`. El agente es
  stateless; no fija el repo en el constructor. Default `"."`.
- **`add`, `commit`, `push`, `reset`, etc. no tienen un capability separada
  por "todo vs específico"** — `add(files=None)` agrega todo (`git add -A`);
  `add(files=[...])` agrega solo esos paths, con `--` antes de la lista para
  que un nombre de archivo que empiece con `-` no se interprete como flag
  (mismo principio de seguridad que `ProcessAgent` aplicando `--` /
  evitando interpolar texto libre sin escapar).
- **`reset` solo soporta `mode="soft"` o `"hard"`, no `"mixed"`** — la tarea
  que pidió este agente solo mencionó soft/hard explícitamente; no se agregó
  `mixed` para no ampliar el alcance sin que se haya pedido. `mode="soft"`
  es el default (el menos destructivo de los dos soportados) para minimizar
  riesgo si algún caller omite el parámetro.
- **`requires_confirmation` cubre exactamente los dos casos que la tarea
  pidió explícitamente** (`push` con `force=True`, `reset` con
  `mode="hard"`) más nada — con el set de capacidades actual (sin `rebase`,
  `commit --amend`, `filter-branch`, etc.) no hay ninguna otra operación en
  este agente que reescriba historia, así que no hace falta una heurística
  más amplia como la de `ProcessAgent._looks_destructive`.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import time
from typing import Any, Awaitable, Callable

from structlog.stdlib import BoundLogger

from ...contracts.agent import ActionResult, ActionStatus, IAgent
from ...logging import get_logger

_HandlerResult = tuple[str, dict[str, Any]]

DEFAULT_TIMEOUT_SECONDS = 30.0
_RESET_MODES: frozenset[str] = frozenset({"soft", "hard"})
_LOG_FIELD_SEP = "\x1f"


class GitAgent(IAgent):
    """Agente que ejecuta operaciones Git sobre un repositorio en disco."""

    def __init__(self) -> None:
        self.logger: BoundLogger = get_logger(self.__class__.__name__)
        self._handlers: dict[str, Callable[..., Awaitable[_HandlerResult]]] = {
            "status": self._status,
            "add": self._add,
            "commit": self._commit,
            "push": self._push,
            "pull": self._pull,
            "log": self._log,
            "diff": self._diff,
            "branch_list": self._branch_list,
            "branch_create": self._branch_create,
            "branch_checkout": self._branch_checkout,
            "reset": self._reset,
        }

    def get_agent_name(self) -> str:
        return "git"

    def get_capabilities(self) -> list[str]:
        return list(self._handlers)

    def requires_confirmation(
        self,
        action: str,
        force: bool = False,
        mode: str | None = None,
        **_: Any,
    ) -> bool:
        if action == "push" and force:
            return True
        if action == "reset" and mode == "hard":
            return True
        return False

    async def is_available(self) -> bool:
        return shutil.which("git") is not None

    async def execute(self, action: str, **kwargs: Any) -> ActionResult:
        handler = self._handlers.get(action)

        if handler is None:
            return ActionResult(
                status=ActionStatus.FAILED,
                error=f"Acción desconocida para GitAgent: '{action}'",
            )

        repo_path = kwargs.get("repo_path", ".")
        start = time.perf_counter()

        try:
            output, data = await handler(**kwargs)
        except FileNotFoundError:
            return self._failed(
                f"No existe el repositorio o no se encontró el binario git: {repo_path}", start
            )
        except NotADirectoryError:
            # Verificado empíricamente: en Windows, `subprocess.run(cwd=...)`
            # levanta NotADirectoryError tanto si repo_path no existe como si
            # existe pero es un archivo — no FileNotFoundError como se podría
            # esperar. El mensaje cubre ambos casos a propósito.
            return self._failed(
                f"repo_path no existe o no es un directorio: {repo_path}", start
            )
        except subprocess.TimeoutExpired:
            timeout = kwargs.get("timeout", DEFAULT_TIMEOUT_SECONDS)
            return self._failed(f"'{action}' excedió el timeout de {timeout}s", start)
        except ValueError as error:
            return self._failed(f"Parámetros inválidos para '{action}': {error}", start)
        except TypeError as error:
            return self._failed(f"Parámetros inválidos para '{action}': {error}", start)
        except OSError as error:
            return self._failed(f"Error del sistema al ejecutar '{action}': {error}", start)

        execution_time_ms = (time.perf_counter() - start) * 1000
        exit_code = data.get("exit_code", 0)

        if exit_code != 0:
            error = (data.get("stderr") or data.get("stdout") or f"git {action} falló").strip()
            self.logger.warning("Operación git falló", action=action, exit_code=exit_code)
            return ActionResult(
                status=ActionStatus.FAILED,
                output=output,
                data=data,
                error=error,
                execution_time_ms=execution_time_ms,
            )

        self.logger.info("Operación git completada", action=action, repo_path=repo_path)
        return ActionResult(
            status=ActionStatus.SUCCESS,
            output=output,
            data=data,
            execution_time_ms=execution_time_ms,
        )

    def _failed(self, error: str, start: float) -> ActionResult:
        execution_time_ms = (time.perf_counter() - start) * 1000
        self.logger.warning("GitAgent falló antes de correr git", error=error)
        return ActionResult(
            status=ActionStatus.FAILED,
            error=error,
            execution_time_ms=execution_time_ms,
        )

    async def _run_git(
        self, args: list[str], repo_path: str, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        return await asyncio.to_thread(
            subprocess.run,
            ["git", *args],
            cwd=repo_path,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    async def _status(
        self, repo_path: str = ".", timeout: float = DEFAULT_TIMEOUT_SECONDS, **_: Any
    ) -> _HandlerResult:
        completed = await self._run_git(["status", "--porcelain=v1", "-b"], repo_path, timeout)
        lines = completed.stdout.splitlines()
        branch = lines[0].lstrip("#").strip() if lines else ""
        files = [
            {"status": line[:2].strip() or line[:2], "path": line[3:]}
            for line in lines[1:]
            if len(line) >= 3
        ]
        data = {
            "repo_path": repo_path,
            "branch": branch,
            "files": files,
            "clean": not files,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        return completed.stdout, data

    async def _add(
        self,
        files: list[str] | None = None,
        repo_path: str = ".",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        **_: Any,
    ) -> _HandlerResult:
        args = ["add", "--", *files] if files else ["add", "-A"]
        completed = await self._run_git(args, repo_path, timeout)
        data = {
            "repo_path": repo_path,
            "files": files or "all",
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        output = completed.stdout or completed.stderr or f"Agregado: {files or 'todo'}"
        return output, data

    async def _commit(
        self,
        message: str,
        repo_path: str = ".",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        **_: Any,
    ) -> _HandlerResult:
        if not isinstance(message, str) or not message.strip():
            raise ValueError("el mensaje de commit no puede estar vacío")

        completed = await self._run_git(["commit", "-m", message], repo_path, timeout)
        data = {
            "repo_path": repo_path,
            "message": message,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        return completed.stdout or completed.stderr, data

    async def _push(
        self,
        remote: str | None = None,
        branch: str | None = None,
        force: bool = False,
        repo_path: str = ".",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        **_: Any,
    ) -> _HandlerResult:
        args = ["push"]
        if force:
            args.append("--force")
        if remote:
            args.append(remote)
        if branch:
            args.append(branch)

        completed = await self._run_git(args, repo_path, timeout)
        data = {
            "repo_path": repo_path,
            "remote": remote,
            "branch": branch,
            "force": force,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        # git push escribe su resumen a stderr incluso en éxito (verificado
        # empíricamente), por eso el fallback stdout-o-stderr acá también.
        return completed.stdout or completed.stderr, data

    async def _pull(
        self,
        remote: str | None = None,
        branch: str | None = None,
        repo_path: str = ".",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        **_: Any,
    ) -> _HandlerResult:
        args = ["pull"]
        if remote:
            args.append(remote)
        if branch:
            args.append(branch)

        completed = await self._run_git(args, repo_path, timeout)
        data = {
            "repo_path": repo_path,
            "remote": remote,
            "branch": branch,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        return completed.stdout or completed.stderr, data

    async def _log(
        self, n: int = 10, repo_path: str = ".", timeout: float = DEFAULT_TIMEOUT_SECONDS, **_: Any
    ) -> _HandlerResult:
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise ValueError("n debe ser un entero positivo")

        fmt = f"%H{_LOG_FIELD_SEP}%an{_LOG_FIELD_SEP}%ad{_LOG_FIELD_SEP}%s"
        completed = await self._run_git(
            ["log", f"-n{n}", f"--pretty=format:{fmt}", "--date=iso-strict"], repo_path, timeout
        )

        commits: list[dict[str, str]] = []
        if completed.returncode == 0:
            for line in completed.stdout.splitlines():
                parts = line.split(_LOG_FIELD_SEP)
                if len(parts) == 4:
                    commits.append(
                        {"hash": parts[0], "author": parts[1], "date": parts[2], "message": parts[3]}
                    )

        data = {
            "repo_path": repo_path,
            "commits": commits,
            "count": len(commits),
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        return completed.stdout, data

    async def _diff(
        self,
        staged: bool = False,
        path: str | None = None,
        repo_path: str = ".",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        **_: Any,
    ) -> _HandlerResult:
        args = ["diff", "--staged"] if staged else ["diff"]
        if path:
            args.extend(["--", path])

        completed = await self._run_git(args, repo_path, timeout)
        data = {
            "repo_path": repo_path,
            "staged": staged,
            "path": path,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        return completed.stdout, data

    async def _branch_list(
        self, repo_path: str = ".", timeout: float = DEFAULT_TIMEOUT_SECONDS, **_: Any
    ) -> _HandlerResult:
        completed = await self._run_git(
            ["branch", "--format=%(refname:short)%09%(HEAD)"], repo_path, timeout
        )
        branches: list[dict[str, Any]] = []
        for line in completed.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) != 2:
                continue
            name, is_head = parts
            branches.append({"name": name, "current": is_head.strip() == "*"})

        data = {
            "repo_path": repo_path,
            "branches": branches,
            "count": len(branches),
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        return completed.stdout, data

    async def _branch_create(
        self,
        name: str,
        checkout: bool = False,
        repo_path: str = ".",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        **_: Any,
    ) -> _HandlerResult:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("el nombre de la rama no puede estar vacío")

        args = ["checkout", "-b", name] if checkout else ["branch", name]
        completed = await self._run_git(args, repo_path, timeout)
        data = {
            "repo_path": repo_path,
            "name": name,
            "checkout": checkout,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        return completed.stdout or completed.stderr, data

    async def _branch_checkout(
        self,
        name: str,
        repo_path: str = ".",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        **_: Any,
    ) -> _HandlerResult:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("el nombre de la rama no puede estar vacío")

        completed = await self._run_git(["checkout", name], repo_path, timeout)
        data = {
            "repo_path": repo_path,
            "name": name,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        # `git checkout` escribe su confirmación ("Switched to branch...") a
        # stderr incluso en éxito — verificado empíricamente.
        return completed.stdout or completed.stderr, data

    async def _reset(
        self,
        mode: str = "soft",
        target: str = "HEAD",
        repo_path: str = ".",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        **_: Any,
    ) -> _HandlerResult:
        if mode not in _RESET_MODES:
            raise ValueError(f"mode debe ser 'soft' o 'hard', no {mode!r}")

        completed = await self._run_git(["reset", f"--{mode}", target], repo_path, timeout)
        data = {
            "repo_path": repo_path,
            "mode": mode,
            "target": target,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        return completed.stdout or completed.stderr or f"reset --{mode} {target}", data
