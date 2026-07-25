"""Pruebas unitarias para FileSystemAgent."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from aries.agents.filesystem.agent import FileSystemAgent
from aries.contracts.agent import ActionStatus


@pytest.fixture(name="agent")
def fixture_agent() -> FileSystemAgent:
    return FileSystemAgent()


def _make_readonly(path: Path) -> None:
    os.chmod(path, stat.S_IREAD)


def _make_writable(path: Path) -> None:
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)


class TestMetadata:
    def test_agent_name(self, agent: FileSystemAgent) -> None:
        assert agent.get_agent_name() == "filesystem"

    def test_capabilities_include_all_documented_actions(self, agent: FileSystemAgent) -> None:
        capabilities = agent.get_capabilities()
        for action in [
            "open_file",
            "read_file",
            "list_directory",
            "create_directory",
            "delete_file",
            "create_file",
            "write_file",
        ]:
            assert action in capabilities

    def test_requires_confirmation_true_for_delete_file(self, agent: FileSystemAgent) -> None:
        assert agent.requires_confirmation("delete_file") is True

    @pytest.mark.parametrize(
        "action",
        ["open_file", "read_file", "list_directory", "create_directory", "create_file", "write_file"],
    )
    def test_requires_confirmation_false_for_non_destructive_actions(
        self, agent: FileSystemAgent, action: str
    ) -> None:
        assert agent.requires_confirmation(action) is False

    @pytest.mark.asyncio
    async def test_is_available(self, agent: FileSystemAgent) -> None:
        assert await agent.is_available() is True

    @pytest.mark.asyncio
    async def test_unknown_action_fails_gracefully(self, agent: FileSystemAgent) -> None:
        result = await agent.execute("format_disk")

        assert result.status == ActionStatus.FAILED
        assert "format_disk" in result.error


class TestReadFile:
    @pytest.mark.asyncio
    async def test_read_file_returns_content(self, agent: FileSystemAgent, tmp_path: Path) -> None:
        file_path = tmp_path / "hello.txt"
        file_path.write_text("hola mundo", encoding="utf-8")

        result = await agent.execute("read_file", path=str(file_path))

        assert result.status == ActionStatus.SUCCESS
        assert result.output == "hola mundo"
        assert result.data["path"] == str(file_path)
        assert result.error is None
        assert result.execution_time_ms >= 0

    @pytest.mark.asyncio
    async def test_open_file_is_alias_for_read_file(self, agent: FileSystemAgent, tmp_path: Path) -> None:
        file_path = tmp_path / "hello.txt"
        file_path.write_text("via alias", encoding="utf-8")

        result = await agent.execute("open_file", path=str(file_path))

        assert result.status == ActionStatus.SUCCESS
        assert result.output == "via alias"

    @pytest.mark.asyncio
    async def test_read_file_missing_returns_failed(self, agent: FileSystemAgent, tmp_path: Path) -> None:
        missing = tmp_path / "no_existe.txt"

        result = await agent.execute("read_file", path=str(missing))

        assert result.status == ActionStatus.FAILED
        assert result.output is None
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_read_file_on_directory_is_permission_denied(
        self, agent: FileSystemAgent, tmp_path: Path
    ) -> None:
        # En Windows, abrir un directorio como archivo levanta PermissionError
        # (a diferencia de POSIX, que levanta IsADirectoryError); el agente
        # normaliza ambos casos a un ActionResult FAILED con `error` no vacío.
        result = await agent.execute("read_file", path=str(tmp_path))

        assert result.status == ActionStatus.FAILED
        assert result.error is not None


class TestListDirectory:
    @pytest.mark.asyncio
    async def test_list_directory_returns_entries(self, agent: FileSystemAgent, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b.txt").write_text("b", encoding="utf-8")
        (tmp_path / "subdir").mkdir()

        result = await agent.execute("list_directory", path=str(tmp_path))

        assert result.status == ActionStatus.SUCCESS
        names = {entry["name"] for entry in result.data["entries"]}
        assert names == {"a.txt", "b.txt", "subdir"}
        subdir_entry = next(e for e in result.data["entries"] if e["name"] == "subdir")
        assert subdir_entry["is_dir"] is True

    @pytest.mark.asyncio
    async def test_list_directory_missing_returns_failed(
        self, agent: FileSystemAgent, tmp_path: Path
    ) -> None:
        missing = tmp_path / "no_existe"

        result = await agent.execute("list_directory", path=str(missing))

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_list_directory_on_file_fails(self, agent: FileSystemAgent, tmp_path: Path) -> None:
        file_path = tmp_path / "archivo.txt"
        file_path.write_text("contenido", encoding="utf-8")

        result = await agent.execute("list_directory", path=str(file_path))

        assert result.status == ActionStatus.FAILED
        assert result.error is not None


class TestCreateDirectory:
    @pytest.mark.asyncio
    async def test_create_directory_success(self, agent: FileSystemAgent, tmp_path: Path) -> None:
        new_dir = tmp_path / "nueva"

        result = await agent.execute("create_directory", path=str(new_dir))

        assert result.status == ActionStatus.SUCCESS
        assert new_dir.is_dir()

    @pytest.mark.asyncio
    async def test_create_directory_creates_parents(self, agent: FileSystemAgent, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "c"

        result = await agent.execute("create_directory", path=str(nested))

        assert result.status == ActionStatus.SUCCESS
        assert nested.is_dir()

    @pytest.mark.asyncio
    async def test_create_directory_already_exists_fails(
        self, agent: FileSystemAgent, tmp_path: Path
    ) -> None:
        existing = tmp_path / "ya_existe"
        existing.mkdir()

        result = await agent.execute("create_directory", path=str(existing))

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_create_directory_exist_ok_true_succeeds(
        self, agent: FileSystemAgent, tmp_path: Path
    ) -> None:
        existing = tmp_path / "ya_existe"
        existing.mkdir()

        result = await agent.execute("create_directory", path=str(existing), exist_ok=True)

        assert result.status == ActionStatus.SUCCESS


class TestDeleteFile:
    @pytest.mark.asyncio
    async def test_delete_file_success(self, agent: FileSystemAgent, tmp_path: Path) -> None:
        file_path = tmp_path / "borrar.txt"
        file_path.write_text("chau", encoding="utf-8")

        result = await agent.execute("delete_file", path=str(file_path))

        assert result.status == ActionStatus.SUCCESS
        assert not file_path.exists()

    @pytest.mark.asyncio
    async def test_delete_file_missing_returns_failed(
        self, agent: FileSystemAgent, tmp_path: Path
    ) -> None:
        missing = tmp_path / "no_existe.txt"

        result = await agent.execute("delete_file", path=str(missing))

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_delete_file_on_directory_fails(self, agent: FileSystemAgent, tmp_path: Path) -> None:
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        result = await agent.execute("delete_file", path=str(subdir))

        assert result.status == ActionStatus.FAILED
        assert subdir.exists()

    @pytest.mark.asyncio
    async def test_delete_file_readonly_is_permission_denied(
        self, agent: FileSystemAgent, tmp_path: Path
    ) -> None:
        file_path = tmp_path / "protegido.txt"
        file_path.write_text("no me borres", encoding="utf-8")
        _make_readonly(file_path)
        try:
            result = await agent.execute("delete_file", path=str(file_path))

            assert result.status == ActionStatus.FAILED
            assert result.error is not None
            assert file_path.exists()
        finally:
            _make_writable(file_path)

    def test_requires_confirmation_documents_destructive_intent(self, agent: FileSystemAgent) -> None:
        # No es un test de comportamiento nuevo, pero deja explícito en el
        # suite que delete_file es la única acción marcada como destructiva
        # para quien lea los tests sin leer el contrato.
        assert agent.requires_confirmation("delete_file") is True


class TestWriteFile:
    @pytest.mark.asyncio
    async def test_write_file_creates_new_file(self, agent: FileSystemAgent, tmp_path: Path) -> None:
        file_path = tmp_path / "nuevo.txt"

        result = await agent.execute("write_file", path=str(file_path), content="contenido nuevo")

        assert result.status == ActionStatus.SUCCESS
        assert file_path.read_text(encoding="utf-8") == "contenido nuevo"
        assert result.data["bytes_written"] == len("contenido nuevo".encode("utf-8"))

    @pytest.mark.asyncio
    async def test_write_file_overwrites_by_default(self, agent: FileSystemAgent, tmp_path: Path) -> None:
        file_path = tmp_path / "existente.txt"
        file_path.write_text("viejo", encoding="utf-8")

        result = await agent.execute("write_file", path=str(file_path), content="nuevo")

        assert result.status == ActionStatus.SUCCESS
        assert file_path.read_text(encoding="utf-8") == "nuevo"

    @pytest.mark.asyncio
    async def test_write_file_overwrite_false_fails_if_exists(
        self, agent: FileSystemAgent, tmp_path: Path
    ) -> None:
        file_path = tmp_path / "existente.txt"
        file_path.write_text("viejo", encoding="utf-8")

        result = await agent.execute(
            "write_file", path=str(file_path), content="nuevo", overwrite=False
        )

        assert result.status == ActionStatus.FAILED
        assert file_path.read_text(encoding="utf-8") == "viejo"

    @pytest.mark.asyncio
    async def test_create_file_is_alias_that_creates_empty_file(
        self, agent: FileSystemAgent, tmp_path: Path
    ) -> None:
        file_path = tmp_path / "vacio.txt"

        result = await agent.execute("create_file", path=str(file_path))

        assert result.status == ActionStatus.SUCCESS
        assert file_path.read_text(encoding="utf-8") == ""

    @pytest.mark.asyncio
    async def test_create_file_does_not_overwrite_existing_by_default(
        self, agent: FileSystemAgent, tmp_path: Path
    ) -> None:
        file_path = tmp_path / "existente.txt"
        file_path.write_text("no me borres", encoding="utf-8")

        result = await agent.execute("create_file", path=str(file_path), content="nuevo")

        assert result.status == ActionStatus.FAILED
        assert file_path.read_text(encoding="utf-8") == "no me borres"

    @pytest.mark.asyncio
    async def test_write_file_permission_denied_on_readonly_file(
        self, agent: FileSystemAgent, tmp_path: Path
    ) -> None:
        file_path = tmp_path / "protegido.txt"
        file_path.write_text("original", encoding="utf-8")
        _make_readonly(file_path)
        try:
            result = await agent.execute("write_file", path=str(file_path), content="nuevo")

            assert result.status == ActionStatus.FAILED
            assert result.error is not None
            assert file_path.read_text(encoding="utf-8") == "original"
        finally:
            _make_writable(file_path)

    @pytest.mark.asyncio
    async def test_write_file_on_directory_fails(self, agent: FileSystemAgent, tmp_path: Path) -> None:
        result = await agent.execute("write_file", path=str(tmp_path), content="x")

        assert result.status == ActionStatus.FAILED
        assert result.error is not None


class TestMissingParameters:
    @pytest.mark.asyncio
    async def test_missing_required_path_fails_gracefully(self, agent: FileSystemAgent) -> None:
        result = await agent.execute("read_file")

        assert result.status == ActionStatus.FAILED
        assert result.error is not None
