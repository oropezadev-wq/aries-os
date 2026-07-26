"""Pruebas unitarias para AgentManager.

Los tests de "integración end-to-end" no mockean nada: usan los 4 agentes
reales contra un archivo/directorio/repo temporal real, igual que sus
propios test suites (`test_filesystem_agent.py`, `test_process_agent.py`,
`test_git_agent.py`, `test_database_agent.py`).
"""

from __future__ import annotations

import subprocess
import sqlite3
import sys
from pathlib import Path

import pytest

from aries.agents.manager import AgentManager
from aries.contracts.agent import ActionResult, ActionStatus, IAgent


class FakeAgent(IAgent):
    """Agente mínimo para probar `register()`/`dispatch()` sin depender de
    los 4 agentes reales."""

    def __init__(self, name: str = "fake") -> None:
        self._name = name

    def get_agent_name(self) -> str:
        return self._name

    def get_capabilities(self) -> list[str]:
        return ["ping"]

    def requires_confirmation(self, action: str, **_: object) -> bool:
        return False

    async def is_available(self) -> bool:
        return True

    async def execute(self, action: str, **kwargs: object) -> ActionResult:
        return ActionResult(status=ActionStatus.SUCCESS, output="pong", data=dict(kwargs))


@pytest.fixture(name="manager")
def fixture_manager() -> AgentManager:
    return AgentManager()


class TestRegistration:
    def test_registers_all_four_default_agents(self, manager: AgentManager) -> None:
        assert set(manager.list_agents()) == {"filesystem", "process", "git", "database"}

    def test_list_agents_includes_known_capabilities(self, manager: AgentManager) -> None:
        capabilities = manager.list_agents()
        assert "write_file" in capabilities["filesystem"]
        assert "run_command" in capabilities["process"]
        assert "commit" in capabilities["git"]
        assert "execute_query" in capabilities["database"]

    def test_get_agent_returns_registered_instance(self, manager: AgentManager) -> None:
        agent = manager.get_agent("filesystem")
        assert agent is not None
        assert agent.get_agent_name() == "filesystem"

    def test_get_agent_returns_none_for_unknown(self, manager: AgentManager) -> None:
        assert manager.get_agent("no_existe") is None

    def test_register_adds_new_agent(self, manager: AgentManager) -> None:
        manager.register(FakeAgent("fake"))

        assert "fake" in manager.list_agents()
        assert manager.list_agents()["fake"] == ["ping"]

    def test_register_replaces_existing_agent_by_name(self, manager: AgentManager) -> None:
        first = FakeAgent("dup")
        second = FakeAgent("dup")
        manager.register(first)
        manager.register(second)

        assert manager.get_agent("dup") is second

    def test_manager_with_explicit_agent_list_does_not_include_defaults(self) -> None:
        manager = AgentManager(agents=[FakeAgent("solo")])

        assert set(manager.list_agents()) == {"solo"}


class TestDispatchValidation:
    @pytest.mark.asyncio
    async def test_dispatch_unknown_agent_fails_gracefully(self, manager: AgentManager) -> None:
        result = await manager.dispatch("no_existe", "algo")

        assert result.status == ActionStatus.FAILED
        assert "no_existe" in result.error

    @pytest.mark.asyncio
    async def test_dispatch_unknown_action_fails_gracefully(self, manager: AgentManager) -> None:
        result = await manager.dispatch("filesystem", "formatear_disco")

        assert result.status == ActionStatus.FAILED
        assert "formatear_disco" in result.error
        assert "filesystem" in result.error

    @pytest.mark.asyncio
    async def test_dispatch_unknown_action_does_not_touch_the_agent(
        self, manager: AgentManager, tmp_path: Path
    ) -> None:
        # Si la acción no está en get_capabilities(), dispatch() ni siquiera
        # debería llamar a execute() — lo confirmamos con un agente fake que
        # levantaría si se le llamara con una acción no declarada.
        class StrictFakeAgent(FakeAgent):
            async def execute(self, action: str, **kwargs: object) -> ActionResult:
                if action not in self.get_capabilities():
                    raise AssertionError("dispatch() no debió llamar a execute() acá")
                return await super().execute(action, **kwargs)

        manager = AgentManager(agents=[StrictFakeAgent("strict")])

        result = await manager.dispatch("strict", "no_declarada")

        assert result.status == ActionStatus.FAILED


class TestDispatchReturnsResultUnmodified:
    @pytest.mark.asyncio
    async def test_dispatch_returns_same_result_as_direct_call(
        self, manager: AgentManager
    ) -> None:
        fake = FakeAgent("fake")
        manager.register(fake)

        direct = await fake.execute("ping", extra="valor")
        via_manager = await manager.dispatch("fake", "ping", extra="valor")

        assert via_manager == direct


class TestDispatchIntegrationFileSystem:
    @pytest.mark.asyncio
    async def test_write_and_read_file_through_manager(
        self, manager: AgentManager, tmp_path: Path
    ) -> None:
        target = tmp_path / "hola.txt"

        write_result = await manager.dispatch(
            "filesystem", "write_file", path=str(target), content="hola mundo"
        )
        assert write_result.status == ActionStatus.SUCCESS
        assert target.read_text(encoding="utf-8") == "hola mundo"

        read_result = await manager.dispatch("filesystem", "read_file", path=str(target))
        assert read_result.status == ActionStatus.SUCCESS
        assert read_result.output == "hola mundo"

    @pytest.mark.asyncio
    async def test_read_missing_file_through_manager_fails_gracefully(
        self, manager: AgentManager, tmp_path: Path
    ) -> None:
        result = await manager.dispatch(
            "filesystem", "read_file", path=str(tmp_path / "no_existe.txt")
        )

        assert result.status == ActionStatus.FAILED


class TestDispatchIntegrationProcess:
    @pytest.mark.asyncio
    async def test_run_command_through_manager(self, manager: AgentManager) -> None:
        command = f'"{sys.executable}" -c "print(6 * 7)"'

        result = await manager.dispatch("process", "run_command", command=command)

        assert result.status == ActionStatus.SUCCESS
        assert result.output.strip() == "42"


class TestDispatchIntegrationGit:
    @pytest.mark.asyncio
    async def test_status_through_manager_on_real_repo(
        self, manager: AgentManager, tmp_path: Path
    ) -> None:
        subprocess.run(["git", "init", "-q", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=tmp_path, check=True)
        (tmp_path / "readme.txt").write_text("hola", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "inicial"], cwd=tmp_path, check=True)

        result = await manager.dispatch("git", "status", repo_path=str(tmp_path))

        assert result.status == ActionStatus.SUCCESS
        assert result.data["clean"] is True


class TestDispatchIntegrationDatabase:
    @pytest.mark.asyncio
    async def test_list_tables_through_manager_on_real_sqlite_file(
        self, manager: AgentManager, tmp_path: Path
    ) -> None:
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE notas (id INTEGER PRIMARY KEY, texto TEXT)")
        conn.commit()
        conn.close()

        result = await manager.dispatch("database", "list_tables", db_path=str(db_path))

        assert result.status == ActionStatus.SUCCESS
        assert "notas" in result.data["tables"]
