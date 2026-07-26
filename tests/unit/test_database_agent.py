"""Pruebas unitarias para DatabaseAgent.

No se mockea el motor de base de datos en ningún lado: cada test usa un
archivo SQLite real creado en un directorio temporal (mismo criterio de
rigor que `test_git_agent.py`/`test_process_agent.py`).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aries.agents.database.agent import DatabaseAgent
from aries.contracts.agent import ActionStatus


@pytest.fixture(name="agent")
def fixture_agent() -> DatabaseAgent:
    return DatabaseAgent()


@pytest.fixture(name="db_path")
def fixture_db_path(tmp_path: Path) -> str:
    """Archivo SQLite real con una tabla `users` precargada."""
    path = tmp_path / "test.db"
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, age INTEGER)"
    )
    conn.execute("INSERT INTO users (name, age) VALUES ('Ana', 30)")
    conn.execute("INSERT INTO users (name, age) VALUES ('Beto', 25)")
    conn.commit()
    conn.close()
    return str(path)


def _table_names(db_path: str) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


class TestMetadata:
    def test_agent_name(self, agent: DatabaseAgent) -> None:
        assert agent.get_agent_name() == "database"

    def test_capabilities_include_all_documented_actions(self, agent: DatabaseAgent) -> None:
        capabilities = agent.get_capabilities()
        for action in [
            "execute_query",
            "insert",
            "update",
            "delete",
            "list_tables",
            "get_schema",
            "execute_transaction",
        ]:
            assert action in capabilities

    @pytest.mark.parametrize(
        "query",
        [
            "DROP TABLE users",
            "  drop table users;",
            "TRUNCATE TABLE users",
            "DELETE FROM users",
            "UPDATE users SET age = 0",
        ],
    )
    def test_requires_confirmation_true_for_destructive_raw_sql(
        self, agent: DatabaseAgent, query: str
    ) -> None:
        assert agent.requires_confirmation("execute_query", query=query) is True

    @pytest.mark.parametrize(
        "query",
        ["SELECT * FROM users", "DELETE FROM users WHERE id = 1", "UPDATE users SET age = 1 WHERE id = 1"],
    )
    def test_requires_confirmation_false_for_safe_raw_sql(
        self, agent: DatabaseAgent, query: str
    ) -> None:
        assert agent.requires_confirmation("execute_query", query=query) is False

    def test_requires_confirmation_true_for_update_without_where(self, agent: DatabaseAgent) -> None:
        assert agent.requires_confirmation("update", where=None) is True
        assert agent.requires_confirmation("update", where={}) is True

    def test_requires_confirmation_false_for_update_with_where(self, agent: DatabaseAgent) -> None:
        assert agent.requires_confirmation("update", where={"id": 1}) is False

    def test_requires_confirmation_true_for_delete_without_where(self, agent: DatabaseAgent) -> None:
        assert agent.requires_confirmation("delete", where=None) is True

    def test_requires_confirmation_false_for_delete_with_where(self, agent: DatabaseAgent) -> None:
        assert agent.requires_confirmation("delete", where={"id": 1}) is False

    def test_requires_confirmation_false_for_insert(self, agent: DatabaseAgent) -> None:
        assert agent.requires_confirmation("insert") is False

    def test_requires_confirmation_true_for_transaction_with_destructive_op(
        self, agent: DatabaseAgent
    ) -> None:
        operations = [{"type": "delete", "table": "users", "where": None}]
        assert agent.requires_confirmation("execute_transaction", operations=operations) is True

    def test_requires_confirmation_false_for_transaction_all_safe(
        self, agent: DatabaseAgent
    ) -> None:
        operations = [
            {"type": "insert", "table": "users", "values": {"name": "x"}},
            {"type": "delete", "table": "users", "where": {"id": 1}},
        ]
        assert agent.requires_confirmation("execute_transaction", operations=operations) is False

    @pytest.mark.asyncio
    async def test_is_available(self, agent: DatabaseAgent) -> None:
        assert await agent.is_available() is True

    @pytest.mark.asyncio
    async def test_unknown_action_fails_gracefully(self, agent: DatabaseAgent, db_path: str) -> None:
        result = await agent.execute("drop_database", db_path=db_path)

        assert result.status == ActionStatus.FAILED
        assert "drop_database" in result.error


class TestExecuteQuery:
    @pytest.mark.asyncio
    async def test_select_returns_rows(self, agent: DatabaseAgent, db_path: str) -> None:
        result = await agent.execute(
            "execute_query", query="SELECT * FROM users ORDER BY id", db_path=db_path
        )

        assert result.status == ActionStatus.SUCCESS
        assert result.data["row_count"] == 2
        assert result.data["rows"][0]["name"] == "Ana"

    @pytest.mark.asyncio
    async def test_select_with_params(self, agent: DatabaseAgent, db_path: str) -> None:
        result = await agent.execute(
            "execute_query",
            query="SELECT * FROM users WHERE name = :name",
            params={"name": "Beto"},
            db_path=db_path,
        )

        assert result.status == ActionStatus.SUCCESS
        assert result.data["row_count"] == 1
        assert result.data["rows"][0]["age"] == 25

    @pytest.mark.asyncio
    async def test_empty_query_fails_gracefully(self, agent: DatabaseAgent, db_path: str) -> None:
        result = await agent.execute("execute_query", query="   ", db_path=db_path)

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_malformed_sql_fails_gracefully(self, agent: DatabaseAgent, db_path: str) -> None:
        result = await agent.execute("execute_query", query="SELEC * FROM users", db_path=db_path)

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_query_on_nonexistent_table_fails_gracefully(
        self, agent: DatabaseAgent, db_path: str
    ) -> None:
        result = await agent.execute(
            "execute_query", query="SELECT * FROM tabla_fantasma", db_path=db_path
        )

        assert result.status == ActionStatus.FAILED
        assert result.error is not None


class TestInsert:
    @pytest.mark.asyncio
    async def test_insert_success(self, agent: DatabaseAgent, db_path: str) -> None:
        result = await agent.execute(
            "insert", table="users", values={"name": "Carla", "age": 40}, db_path=db_path
        )

        assert result.status == ActionStatus.SUCCESS
        assert result.data["row_count"] == 1
        check = await agent.execute(
            "execute_query", query="SELECT * FROM users WHERE name = :n", params={"n": "Carla"}, db_path=db_path
        )
        assert check.data["row_count"] == 1

    @pytest.mark.asyncio
    async def test_insert_empty_values_fails_gracefully(
        self, agent: DatabaseAgent, db_path: str
    ) -> None:
        result = await agent.execute("insert", table="users", values={}, db_path=db_path)

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_insert_into_nonexistent_table_fails_gracefully(
        self, agent: DatabaseAgent, db_path: str
    ) -> None:
        result = await agent.execute(
            "insert", table="tabla_fantasma", values={"x": 1}, db_path=db_path
        )

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_insert_violating_unique_constraint_fails_gracefully(
        self, agent: DatabaseAgent, db_path: str
    ) -> None:
        result = await agent.execute(
            "insert", table="users", values={"name": "Ana", "age": 99}, db_path=db_path
        )

        assert result.status == ActionStatus.FAILED
        assert result.error is not None


class TestUpdate:
    @pytest.mark.asyncio
    async def test_update_with_where(self, agent: DatabaseAgent, db_path: str) -> None:
        result = await agent.execute(
            "update", table="users", values={"age": 31}, where={"name": "Ana"}, db_path=db_path
        )

        assert result.status == ActionStatus.SUCCESS
        assert result.data["row_count"] == 1
        check = await agent.execute(
            "execute_query", query="SELECT age FROM users WHERE name = :n", params={"n": "Ana"}, db_path=db_path
        )
        assert check.data["rows"][0]["age"] == 31

    @pytest.mark.asyncio
    async def test_update_without_where_still_executes_when_called_directly(
        self, agent: DatabaseAgent, db_path: str
    ) -> None:
        # requires_confirmation() advierte que esto es peligroso, pero
        # execute() no se auto-bloquea — es responsabilidad del caller
        # (Planner) pedir confirmación antes de invocar. Mismo criterio que
        # delete_file en FileSystemAgent y reset --hard en GitAgent.
        result = await agent.execute(
            "update", table="users", values={"age": 0}, db_path=db_path
        )

        assert result.status == ActionStatus.SUCCESS
        assert result.data["row_count"] == 2
        check = await agent.execute("execute_query", query="SELECT age FROM users", db_path=db_path)
        assert all(row["age"] == 0 for row in check.data["rows"])

    @pytest.mark.asyncio
    async def test_update_empty_values_fails_gracefully(
        self, agent: DatabaseAgent, db_path: str
    ) -> None:
        result = await agent.execute("update", table="users", values={}, db_path=db_path)

        assert result.status == ActionStatus.FAILED
        assert result.error is not None


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_with_where(self, agent: DatabaseAgent, db_path: str) -> None:
        result = await agent.execute("delete", table="users", where={"name": "Beto"}, db_path=db_path)

        assert result.status == ActionStatus.SUCCESS
        assert result.data["row_count"] == 1
        check = await agent.execute("execute_query", query="SELECT * FROM users", db_path=db_path)
        assert check.data["row_count"] == 1

    @pytest.mark.asyncio
    async def test_delete_without_where_deletes_all_when_called_directly(
        self, agent: DatabaseAgent, db_path: str
    ) -> None:
        result = await agent.execute("delete", table="users", db_path=db_path)

        assert result.status == ActionStatus.SUCCESS
        assert result.data["row_count"] == 2
        check = await agent.execute("execute_query", query="SELECT * FROM users", db_path=db_path)
        assert check.data["row_count"] == 0

    @pytest.mark.asyncio
    async def test_delete_from_nonexistent_table_fails_gracefully(
        self, agent: DatabaseAgent, db_path: str
    ) -> None:
        result = await agent.execute("delete", table="tabla_fantasma", db_path=db_path)

        assert result.status == ActionStatus.FAILED
        assert result.error is not None


class TestListTables:
    @pytest.mark.asyncio
    async def test_list_tables_returns_users(self, agent: DatabaseAgent, db_path: str) -> None:
        result = await agent.execute("list_tables", db_path=db_path)

        assert result.status == ActionStatus.SUCCESS
        assert "users" in result.data["tables"]

    @pytest.mark.asyncio
    async def test_list_tables_on_empty_database(self, agent: DatabaseAgent, tmp_path: Path) -> None:
        empty_db = tmp_path / "empty.db"
        sqlite3.connect(str(empty_db)).close()

        result = await agent.execute("list_tables", db_path=str(empty_db))

        assert result.status == ActionStatus.SUCCESS
        assert result.data["tables"] == []


class TestGetSchema:
    @pytest.mark.asyncio
    async def test_get_schema_returns_columns(self, agent: DatabaseAgent, db_path: str) -> None:
        result = await agent.execute("get_schema", table="users", db_path=db_path)

        assert result.status == ActionStatus.SUCCESS
        names = {col["name"] for col in result.data["columns"]}
        assert names == {"id", "name", "age"}
        id_col = next(c for c in result.data["columns"] if c["name"] == "id")
        assert id_col["primary_key"] is True
        name_col = next(c for c in result.data["columns"] if c["name"] == "name")
        assert name_col["nullable"] is False

    @pytest.mark.asyncio
    async def test_get_schema_nonexistent_table_fails_gracefully(
        self, agent: DatabaseAgent, db_path: str
    ) -> None:
        result = await agent.execute("get_schema", table="tabla_fantasma", db_path=db_path)

        assert result.status == ActionStatus.FAILED
        assert result.error is not None


class TestExecuteTransaction:
    @pytest.mark.asyncio
    async def test_transaction_success_applies_all_operations(
        self, agent: DatabaseAgent, db_path: str
    ) -> None:
        operations = [
            {"type": "insert", "table": "users", "values": {"name": "Dani", "age": 22}},
            {"type": "update", "table": "users", "values": {"age": 26}, "where": {"name": "Beto"}},
            {"type": "delete", "table": "users", "where": {"name": "Ana"}},
        ]

        result = await agent.execute("execute_transaction", operations=operations, db_path=db_path)

        assert result.status == ActionStatus.SUCCESS
        assert result.data["count"] == 3
        check = await agent.execute(
            "execute_query", query="SELECT name, age FROM users ORDER BY name", db_path=db_path
        )
        rows = {r["name"]: r["age"] for r in check.data["rows"]}
        assert rows == {"Beto": 26, "Dani": 22}

    @pytest.mark.asyncio
    async def test_transaction_rolls_back_atomically_on_failure(
        self, agent: DatabaseAgent, db_path: str
    ) -> None:
        operations = [
            {"type": "insert", "table": "users", "values": {"name": "Elena", "age": 50}},
            {"type": "insert", "table": "tabla_fantasma", "values": {"x": 1}},  # falla acá
        ]

        result = await agent.execute("execute_transaction", operations=operations, db_path=db_path)

        assert result.status == ActionStatus.FAILED
        # La inserción de "Elena" debe haberse revertido junto con todo lo demás.
        check = await agent.execute(
            "execute_query", query="SELECT * FROM users WHERE name = :n", params={"n": "Elena"}, db_path=db_path
        )
        assert check.data["row_count"] == 0

    @pytest.mark.asyncio
    async def test_transaction_empty_operations_fails_gracefully(
        self, agent: DatabaseAgent, db_path: str
    ) -> None:
        result = await agent.execute("execute_transaction", operations=[], db_path=db_path)

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_transaction_unknown_operation_type_fails_gracefully(
        self, agent: DatabaseAgent, db_path: str
    ) -> None:
        operations = [{"type": "drop_everything", "table": "users"}]

        result = await agent.execute("execute_transaction", operations=operations, db_path=db_path)

        assert result.status == ActionStatus.FAILED
        assert result.error is not None


class TestRepoPathErrors:
    @pytest.mark.asyncio
    async def test_nonexistent_directory_fails_gracefully(
        self, agent: DatabaseAgent, tmp_path: Path
    ) -> None:
        missing = tmp_path / "no_existe_subdir" / "x.db"

        result = await agent.execute("list_tables", db_path=str(missing))

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_empty_db_path_fails_gracefully(self, agent: DatabaseAgent) -> None:
        result = await agent.execute("list_tables", db_path="")

        assert result.status == ActionStatus.FAILED
        assert result.error is not None


class TestSQLInjection:
    """Confirma que la inyección SQL queda neutralizada, no solo bloqueada
    por una heurística de texto — se verifica el estado real de la base de
    datos después de cada intento, no solo el ActionResult."""

    @pytest.mark.asyncio
    async def test_injection_via_query_params_is_neutralized(
        self, agent: DatabaseAgent, db_path: str
    ) -> None:
        malicious_name = "x'; DROP TABLE users; --"

        result = await agent.execute(
            "execute_query",
            query="SELECT * FROM users WHERE name = :name",
            params={"name": malicious_name},
            db_path=db_path,
        )

        assert result.status == ActionStatus.SUCCESS
        assert result.data["row_count"] == 0  # no matchea a nadie, como debe ser
        assert "users" in _table_names(db_path)  # la tabla sigue existiendo

    @pytest.mark.asyncio
    async def test_injection_via_insert_values_key_is_rejected(
        self, agent: DatabaseAgent, db_path: str
    ) -> None:
        malicious_key = "name); DROP TABLE users; --"

        result = await agent.execute(
            "insert", table="users", values={malicious_key: "x"}, db_path=db_path
        )

        assert result.status == ActionStatus.FAILED
        assert "users" in _table_names(db_path)

    @pytest.mark.asyncio
    async def test_injection_via_update_where_key_is_rejected(
        self, agent: DatabaseAgent, db_path: str
    ) -> None:
        malicious_key = "id = 1; DROP TABLE users; --"

        result = await agent.execute(
            "update",
            table="users",
            values={"age": 1},
            where={malicious_key: 1},
            db_path=db_path,
        )

        assert result.status == ActionStatus.FAILED
        assert "users" in _table_names(db_path)

    @pytest.mark.asyncio
    async def test_injection_via_insert_values_content_is_stored_literally(
        self, agent: DatabaseAgent, db_path: str
    ) -> None:
        # El VALOR puede contener cualquier cosa, incluida sintaxis SQL —
        # como valor parametrizado, nunca se interpreta como SQL.
        payload = "'; DROP TABLE users; --"

        result = await agent.execute(
            "insert", table="users", values={"name": payload, "age": 1}, db_path=db_path
        )

        assert result.status == ActionStatus.SUCCESS
        assert "users" in _table_names(db_path)
        check = await agent.execute(
            "execute_query", query="SELECT * FROM users WHERE name = :n", params={"n": payload}, db_path=db_path
        )
        assert check.data["row_count"] == 1
