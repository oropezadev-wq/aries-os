"""DatabaseAgent: agente IAgent para operaciones SQL sobre SQLite usando
SQLAlchemy Core (no ORM) — sin agregar dependencias nuevas: `sqlalchemy>=2.0`
ya estaba declarada en `pyproject.toml`. **Nota de entorno**: no estaba
instalada en el entorno donde corre esta sesión (ni en `.venv` ni en
`.venv-1` — ninguno de los dos es el entorno real del proyecto; ver
PROGRESS.md), así que se instaló ahí antes de escribir este archivo. No es
una dependencia nueva, es completar lo que el manifiesto ya declaraba.

Alcance deliberado: **solo SQLite, vía un `db_path` de archivo** (no un
connection string arbitrario) — mismo criterio conservador que
`FileSystemAgent.path`/`ProcessAgent.cwd`/`GitAgent.repo_path`. No se agregó
soporte para Postgres/MySQL/otros motores: la tarea pidió probar contra
SQLite y no pidió explícitamente otros motores, así que no se amplió el
alcance sin que se pidiera.

## El riesgo real: inyección SQL, tratada con el mismo criterio que
## `shell=True` en `ProcessAgent`

Ninguna capacidad arma SQL por interpolación de string. Concretamente:

- `execute_query` recibe `query` (el SQL, con placeholders `:nombre`) y
  `params` (los valores) **por separado**, y los pasa a
  `conn.execute(text(query), params)` — SQLAlchemy hace el bind, nunca se
  concatena `params` dentro de `query` en este código. Verificado
  empíricamente: un intento de inyección vía `params` (ej.
  `params={"name": "x'; DROP TABLE users; --"}`) queda como valor literal,
  no se ejecuta como SQL.
- `insert`/`update`/`delete` **no arman SQL a mano en absoluto** — usan
  reflexión de SQLAlchemy (`Table(nombre, metadata, autoload_with=engine)`)
  y construyen la sentencia con SQLAlchemy Core (`tbl.insert().values(...)`,
  `tbl.update().where(...)`, etc.). Esto protege tanto los *valores* (bind
  params, igual que `execute_query`) como los *identificadores* (nombres de
  tabla/columna pasan por el manejo de identificadores de SQLAlchemy, no por
  f-strings). Verificado empíricamente: un nombre de "columna" malicioso en
  `values` (ej. `{"name); DROP TABLE users; --": "x"}`) no compila
  (`CompileError`, "Unconsumed column names") — nunca llega a ejecutarse.
  Una columna inexistente en `where` levanta `KeyError` al acceder a
  `tbl.c[columna]`, también antes de ejecutar nada.

No hay una capacidad `execute_raw_sql` sin parametrizar, ni ningún camino
para que el caller fuerce interpolación cruda — a propósito, mismo criterio
que la ausencia de un `run_shell_command` genérico en `ProcessAgent`.

## Otras notas de diseño

- **Sin capa de aislamiento de SO** (igual que `GitAgent`, a diferencia de
  `ProcessAgent`): SQLAlchemy/SQLite ya son portables, no hay ninguna
  llamada específica de plataforma que aislar.
- **`ActionResult.status` refleja el resultado semántico**, igual que
  `GitAgent` y a diferencia de `ProcessAgent.run_command`: una excepción de
  SQLAlchemy (tabla inexistente, violación de integridad, SQL inválido, PID
  — perdón, columna — inexistente) se atrapa y se retorna como
  `ActionResult(FAILED)`, nunca se deja propagar.
- **`execute_transaction` es atómica de verdad**: todas las operaciones de
  la lista corren dentro de un único `engine.begin()` — si cualquiera falla,
  SQLAlchemy hace rollback de todo el bloque (verificado empíricamente: una
  operación fallida a mitad de una transacción de prueba dejó cero cambios
  de las operaciones anteriores de esa misma transacción).
- **Motor SQLAlchemy por llamada, no cacheado en el agente**: cada capacidad
  crea su propio `Engine` y lo dispone (`engine.dispose()`) al terminar —
  agente sin estado, mismo patrón que sus hermanos (`repo_path`/`db_path`
  como kwarg por llamada, no fijado en el constructor), y evita retener
  handles abiertos sobre el archivo `.db` entre llamadas (relevante en
  Windows).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

import sqlalchemy as sa
from sqlalchemy import MetaData, Table, inspect, text
from sqlalchemy.exc import IntegrityError, NoSuchTableError, OperationalError, SQLAlchemyError
from structlog.stdlib import BoundLogger

from ...contracts.agent import ActionResult, ActionStatus, IAgent
from ...logging import get_logger

_HandlerResult = tuple[str, dict[str, Any]]


class DatabaseAgent(IAgent):
    """Agente que ejecuta operaciones SQL sobre una base SQLite en disco."""

    def __init__(self) -> None:
        self.logger: BoundLogger = get_logger(self.__class__.__name__)
        self._handlers: dict[str, Callable[..., Awaitable[_HandlerResult]]] = {
            "execute_query": self._execute_query,
            "insert": self._insert,
            "update": self._update,
            "delete": self._delete,
            "list_tables": self._list_tables,
            "get_schema": self._get_schema,
            "execute_transaction": self._execute_transaction,
        }

    def get_agent_name(self) -> str:
        return "database"

    def get_capabilities(self) -> list[str]:
        return list(self._handlers)

    def requires_confirmation(
        self,
        action: str,
        query: str | None = None,
        where: dict[str, Any] | None = None,
        operations: list[dict[str, Any]] | None = None,
        **_: Any,
    ) -> bool:
        if action == "execute_query" and query:
            return self._looks_destructive_sql(query)
        if action in ("update", "delete"):
            return not where
        if action == "execute_transaction" and operations:
            return any(self._operation_requires_confirmation(op) for op in operations)
        return False

    @classmethod
    def _operation_requires_confirmation(cls, op: dict[str, Any]) -> bool:
        op_type = op.get("type")
        if op_type == "execute_query":
            return cls._looks_destructive_sql(op.get("query", ""))
        if op_type in ("update", "delete"):
            return not op.get("where")
        return False

    @staticmethod
    def _looks_destructive_sql(query: str) -> bool:
        """Heurística de mejor esfuerzo, NO un control de seguridad real.

        Mismo espíritu que `ProcessAgent._looks_destructive`: solo sirve
        para decidir si pedir confirmación, nunca para decidir si ejecutar
        o no — eso lo sigue controlando exclusivamente la parametrización
        (ver docstring del módulo). No detecta variantes ofuscadas.
        """
        normalized = " ".join(query.strip().lower().split())
        if normalized.startswith("drop table") or normalized.startswith("truncate"):
            return True
        if normalized.startswith("delete") and " where " not in f" {normalized} ":
            return True
        if normalized.startswith("update") and " where " not in f" {normalized} ":
            return True
        return False

    async def is_available(self) -> bool:
        return True

    async def execute(self, action: str, **kwargs: Any) -> ActionResult:
        handler = self._handlers.get(action)

        if handler is None:
            return ActionResult(
                status=ActionStatus.FAILED,
                error=f"Acción desconocida para DatabaseAgent: '{action}'",
            )

        start = time.perf_counter()

        try:
            output, data = await handler(**kwargs)
        except NoSuchTableError as error:
            return self._failed(f"No existe la tabla: {error}", start)
        except IntegrityError as error:
            return self._failed(f"Violación de integridad: {self._short(error)}", start)
        except OperationalError as error:
            return self._failed(f"Error operacional de SQLite: {self._short(error)}", start)
        except SQLAlchemyError as error:
            return self._failed(f"Error de SQLAlchemy: {self._short(error)}", start)
        except KeyError as error:
            return self._failed(
                f"Falta un campo requerido o columna inválida para '{action}': {error}", start
            )
        except ValueError as error:
            return self._failed(f"Parámetros inválidos para '{action}': {error}", start)
        except TypeError as error:
            return self._failed(f"Parámetros inválidos para '{action}': {error}", start)

        execution_time_ms = (time.perf_counter() - start) * 1000
        self.logger.info("Operación de base de datos completada", action=action)
        return ActionResult(
            status=ActionStatus.SUCCESS,
            output=output,
            data=data,
            execution_time_ms=execution_time_ms,
        )

    def _failed(self, error: str, start: float) -> ActionResult:
        execution_time_ms = (time.perf_counter() - start) * 1000
        self.logger.warning("Operación de base de datos falló", error=error)
        return ActionResult(
            status=ActionStatus.FAILED,
            error=error,
            execution_time_ms=execution_time_ms,
        )

    @staticmethod
    def _short(error: Exception) -> str:
        return str(error).split("\n")[0]

    @staticmethod
    def _engine(db_path: str) -> sa.Engine:
        if not isinstance(db_path, str) or not db_path.strip():
            raise ValueError("db_path no puede estar vacío")
        return sa.create_engine(f"sqlite:///{db_path}")

    # --- Capacidades ---------------------------------------------------

    async def _execute_query(
        self,
        query: str,
        params: dict[str, Any] | None = None,
        db_path: str = "",
        **_: Any,
    ) -> _HandlerResult:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query no puede estar vacía")
        return await asyncio.to_thread(self._execute_query_sync, query, params, db_path)

    def _execute_query_sync(
        self, query: str, params: dict[str, Any] | None, db_path: str
    ) -> _HandlerResult:
        engine = self._engine(db_path)
        try:
            with engine.begin() as conn:
                result = conn.execute(text(query), params or {})
                if result.returns_rows:
                    rows = [dict(row._mapping) for row in result]
                    data = {"db_path": db_path, "rows": rows, "row_count": len(rows)}
                    return f"{len(rows)} fila(s)", data
                row_count = result.rowcount
            data = {"db_path": db_path, "rows": [], "row_count": row_count}
            return f"{row_count} fila(s) afectada(s)", data
        finally:
            engine.dispose()

    async def _insert(
        self, table: str, values: dict[str, Any], db_path: str = "", **_: Any
    ) -> _HandlerResult:
        if not isinstance(values, dict) or not values:
            raise ValueError("values no puede estar vacío")
        return await asyncio.to_thread(self._insert_sync, table, values, db_path)

    def _insert_sync(self, table: str, values: dict[str, Any], db_path: str) -> _HandlerResult:
        engine = self._engine(db_path)
        try:
            tbl = Table(table, MetaData(), autoload_with=engine)
            with engine.begin() as conn:
                result = conn.execute(tbl.insert().values(**values))
                inserted_pk = list(result.inserted_primary_key) if result.inserted_primary_key else None
                row_count = result.rowcount
            data = {
                "db_path": db_path,
                "table": table,
                "row_count": row_count,
                "inserted_primary_key": inserted_pk,
            }
            return f"{row_count} fila(s) insertada(s) en {table}", data
        finally:
            engine.dispose()

    async def _update(
        self,
        table: str,
        values: dict[str, Any],
        where: dict[str, Any] | None = None,
        db_path: str = "",
        **_: Any,
    ) -> _HandlerResult:
        if not isinstance(values, dict) or not values:
            raise ValueError("values no puede estar vacío")
        return await asyncio.to_thread(self._update_sync, table, values, where, db_path)

    def _update_sync(
        self, table: str, values: dict[str, Any], where: dict[str, Any] | None, db_path: str
    ) -> _HandlerResult:
        engine = self._engine(db_path)
        try:
            tbl = Table(table, MetaData(), autoload_with=engine)
            stmt = tbl.update().values(**values)
            if where:
                stmt = stmt.where(sa.and_(*(tbl.c[col] == val for col, val in where.items())))
            with engine.begin() as conn:
                result = conn.execute(stmt)
                row_count = result.rowcount
            data = {"db_path": db_path, "table": table, "where": where, "row_count": row_count}
            return f"{row_count} fila(s) actualizada(s) en {table}", data
        finally:
            engine.dispose()

    async def _delete(
        self,
        table: str,
        where: dict[str, Any] | None = None,
        db_path: str = "",
        **_: Any,
    ) -> _HandlerResult:
        return await asyncio.to_thread(self._delete_sync, table, where, db_path)

    def _delete_sync(
        self, table: str, where: dict[str, Any] | None, db_path: str
    ) -> _HandlerResult:
        engine = self._engine(db_path)
        try:
            tbl = Table(table, MetaData(), autoload_with=engine)
            stmt = tbl.delete()
            if where:
                stmt = stmt.where(sa.and_(*(tbl.c[col] == val for col, val in where.items())))
            with engine.begin() as conn:
                result = conn.execute(stmt)
                row_count = result.rowcount
            data = {"db_path": db_path, "table": table, "where": where, "row_count": row_count}
            return f"{row_count} fila(s) eliminada(s) de {table}", data
        finally:
            engine.dispose()

    async def _list_tables(self, db_path: str = "", **_: Any) -> _HandlerResult:
        return await asyncio.to_thread(self._list_tables_sync, db_path)

    def _list_tables_sync(self, db_path: str) -> _HandlerResult:
        engine = self._engine(db_path)
        try:
            names = inspect(engine).get_table_names()
            data = {"db_path": db_path, "tables": names, "count": len(names)}
            return f"{len(names)} tabla(s)", data
        finally:
            engine.dispose()

    async def _get_schema(self, table: str, db_path: str = "", **_: Any) -> _HandlerResult:
        return await asyncio.to_thread(self._get_schema_sync, table, db_path)

    def _get_schema_sync(self, table: str, db_path: str) -> _HandlerResult:
        engine = self._engine(db_path)
        try:
            insp = inspect(engine)
            if table not in insp.get_table_names():
                raise NoSuchTableError(table)

            columns = [
                {
                    "name": col["name"],
                    "type": str(col["type"]),
                    "nullable": col["nullable"],
                    "default": col.get("default"),
                    "primary_key": bool(col.get("primary_key")),
                }
                for col in insp.get_columns(table)
            ]
            data = {"db_path": db_path, "table": table, "columns": columns}
            return f"{len(columns)} columna(s) en {table}", data
        finally:
            engine.dispose()

    async def _execute_transaction(
        self, operations: list[dict[str, Any]], db_path: str = "", **_: Any
    ) -> _HandlerResult:
        if not isinstance(operations, list) or not operations:
            raise ValueError("operations no puede estar vacío")
        return await asyncio.to_thread(self._execute_transaction_sync, operations, db_path)

    def _execute_transaction_sync(
        self, operations: list[dict[str, Any]], db_path: str
    ) -> _HandlerResult:
        engine = self._engine(db_path)
        try:
            metadata = MetaData()
            reflected: dict[str, Table] = {}

            def get_table(name: str) -> Table:
                if name not in reflected:
                    reflected[name] = Table(name, metadata, autoload_with=engine)
                return reflected[name]

            results: list[dict[str, Any]] = []
            with engine.begin() as conn:
                for index, op in enumerate(operations):
                    op_type = op.get("type")

                    if op_type == "insert":
                        tbl = get_table(op["table"])
                        result = conn.execute(tbl.insert().values(**op["values"]))
                        results.append({"type": "insert", "row_count": result.rowcount})
                    elif op_type == "update":
                        tbl = get_table(op["table"])
                        stmt = tbl.update().values(**op["values"])
                        where = op.get("where")
                        if where:
                            stmt = stmt.where(
                                sa.and_(*(tbl.c[col] == val for col, val in where.items()))
                            )
                        result = conn.execute(stmt)
                        results.append({"type": "update", "row_count": result.rowcount})
                    elif op_type == "delete":
                        tbl = get_table(op["table"])
                        stmt = tbl.delete()
                        where = op.get("where")
                        if where:
                            stmt = stmt.where(
                                sa.and_(*(tbl.c[col] == val for col, val in where.items()))
                            )
                        result = conn.execute(stmt)
                        results.append({"type": "delete", "row_count": result.rowcount})
                    elif op_type == "execute_query":
                        result = conn.execute(text(op["query"]), op.get("params") or {})
                        if result.returns_rows:
                            rows = [dict(row._mapping) for row in result]
                            results.append(
                                {"type": "execute_query", "rows": rows, "row_count": len(rows)}
                            )
                        else:
                            results.append(
                                {"type": "execute_query", "row_count": result.rowcount}
                            )
                    else:
                        raise ValueError(
                            f"Tipo de operación desconocido en operations[{index}]: {op_type!r}"
                        )

            data = {"db_path": db_path, "operations": results, "count": len(results)}
            return f"{len(results)} operación(es) aplicadas atómicamente", data
        finally:
            engine.dispose()
