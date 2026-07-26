"""Pruebas unitarias para GitAgent.

No se mockea `git` en ningún lado: cada test usa un repositorio real creado
con `git init` sobre un directorio temporal (mismo criterio de rigor que
`test_filesystem_agent.py`/`test_process_agent.py`).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from aries.agents.git.agent import GitAgent
from aries.contracts.agent import ActionStatus


@pytest.fixture(name="agent")
def fixture_agent() -> GitAgent:
    return GitAgent()


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "."], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=path, check=True)


def _commit_file(path: Path, name: str, content: str, message: str) -> None:
    (path / name).write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=path, check=True)


@pytest.fixture(name="repo")
def fixture_repo(tmp_path: Path) -> Path:
    """Repo git real con un commit inicial."""
    _init_repo(tmp_path)
    _commit_file(tmp_path, "readme.txt", "hola", "commit inicial")
    return tmp_path


@pytest.fixture(name="empty_repo")
def fixture_empty_repo(tmp_path: Path) -> Path:
    """Repo git real sin ningún commit todavía."""
    _init_repo(tmp_path)
    return tmp_path


class TestMetadata:
    def test_agent_name(self, agent: GitAgent) -> None:
        assert agent.get_agent_name() == "git"

    def test_capabilities_include_all_documented_actions(self, agent: GitAgent) -> None:
        capabilities = agent.get_capabilities()
        for action in [
            "status",
            "add",
            "commit",
            "push",
            "pull",
            "log",
            "diff",
            "branch_list",
            "branch_create",
            "branch_checkout",
            "reset",
        ]:
            assert action in capabilities

    def test_requires_confirmation_true_for_push_force(self, agent: GitAgent) -> None:
        assert agent.requires_confirmation("push", force=True) is True

    def test_requires_confirmation_false_for_push_without_force(self, agent: GitAgent) -> None:
        assert agent.requires_confirmation("push", force=False) is False
        assert agent.requires_confirmation("push") is False

    def test_requires_confirmation_true_for_reset_hard(self, agent: GitAgent) -> None:
        assert agent.requires_confirmation("reset", mode="hard") is True

    def test_requires_confirmation_false_for_reset_soft(self, agent: GitAgent) -> None:
        assert agent.requires_confirmation("reset", mode="soft") is False
        assert agent.requires_confirmation("reset") is False

    @pytest.mark.parametrize(
        "action", ["status", "add", "commit", "pull", "log", "diff", "branch_list", "branch_create", "branch_checkout"]
    )
    def test_requires_confirmation_false_for_non_destructive_actions(
        self, agent: GitAgent, action: str
    ) -> None:
        assert agent.requires_confirmation(action) is False

    @pytest.mark.asyncio
    async def test_is_available(self, agent: GitAgent) -> None:
        # git está instalado en esta máquina (verificado con `git --version`
        # antes de escribir el agente) — no se mockea `shutil.which`.
        assert await agent.is_available() is True

    @pytest.mark.asyncio
    async def test_unknown_action_fails_gracefully(self, agent: GitAgent, repo: Path) -> None:
        result = await agent.execute("force_push_everything", repo_path=str(repo))

        assert result.status == ActionStatus.FAILED
        assert "force_push_everything" in result.error


class TestStatus:
    @pytest.mark.asyncio
    async def test_status_clean_repo(self, agent: GitAgent, repo: Path) -> None:
        result = await agent.execute("status", repo_path=str(repo))

        assert result.status == ActionStatus.SUCCESS
        assert result.data["clean"] is True
        assert result.data["files"] == []
        assert "master" in result.data["branch"] or "main" in result.data["branch"]

    @pytest.mark.asyncio
    async def test_status_untracked_file(self, agent: GitAgent, repo: Path) -> None:
        (repo / "nuevo.txt").write_text("contenido", encoding="utf-8")

        result = await agent.execute("status", repo_path=str(repo))

        assert result.status == ActionStatus.SUCCESS
        assert result.data["clean"] is False
        paths = {entry["path"] for entry in result.data["files"]}
        assert "nuevo.txt" in paths

    @pytest.mark.asyncio
    async def test_status_modified_file(self, agent: GitAgent, repo: Path) -> None:
        (repo / "readme.txt").write_text("modificado", encoding="utf-8")

        result = await agent.execute("status", repo_path=str(repo))

        assert result.status == ActionStatus.SUCCESS
        entries = {entry["path"]: entry["status"] for entry in result.data["files"]}
        assert entries.get("readme.txt") == "M"

    @pytest.mark.asyncio
    async def test_status_on_empty_repo_no_commits(self, agent: GitAgent, empty_repo: Path) -> None:
        result = await agent.execute("status", repo_path=str(empty_repo))

        assert result.status == ActionStatus.SUCCESS
        assert result.data["clean"] is True


class TestAdd:
    @pytest.mark.asyncio
    async def test_add_all(self, agent: GitAgent, repo: Path) -> None:
        (repo / "a.txt").write_text("a", encoding="utf-8")
        (repo / "b.txt").write_text("b", encoding="utf-8")

        result = await agent.execute("add", repo_path=str(repo))

        assert result.status == ActionStatus.SUCCESS
        status = await agent.execute("status", repo_path=str(repo))
        entries = {entry["path"]: entry["status"] for entry in status.data["files"]}
        assert entries.get("a.txt") == "A"
        assert entries.get("b.txt") == "A"

    @pytest.mark.asyncio
    async def test_add_specific_files(self, agent: GitAgent, repo: Path) -> None:
        (repo / "a.txt").write_text("a", encoding="utf-8")
        (repo / "b.txt").write_text("b", encoding="utf-8")

        result = await agent.execute("add", files=["a.txt"], repo_path=str(repo))

        assert result.status == ActionStatus.SUCCESS
        status = await agent.execute("status", repo_path=str(repo))
        entries = {entry["path"]: entry["status"] for entry in status.data["files"]}
        assert entries.get("a.txt") == "A"
        assert entries.get("b.txt") == "??"


class TestCommit:
    @pytest.mark.asyncio
    async def test_commit_success(self, agent: GitAgent, repo: Path) -> None:
        (repo / "nuevo.txt").write_text("contenido", encoding="utf-8")
        await agent.execute("add", repo_path=str(repo))

        result = await agent.execute("commit", message="agrega nuevo.txt", repo_path=str(repo))

        assert result.status == ActionStatus.SUCCESS
        log = subprocess.run(
            ["git", "log", "-1", "--pretty=%s"], cwd=repo, capture_output=True, text=True
        )
        assert log.stdout.strip() == "agrega nuevo.txt"

    @pytest.mark.asyncio
    async def test_commit_empty_message_fails_gracefully(self, agent: GitAgent, repo: Path) -> None:
        result = await agent.execute("commit", message="   ", repo_path=str(repo))

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_commit_nothing_staged_fails_gracefully(self, agent: GitAgent, repo: Path) -> None:
        result = await agent.execute("commit", message="no hay nada", repo_path=str(repo))

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_commit_missing_message_fails_gracefully(self, agent: GitAgent, repo: Path) -> None:
        result = await agent.execute("commit", repo_path=str(repo))

        assert result.status == ActionStatus.FAILED
        assert result.error is not None


class TestPushPull:
    @pytest.mark.asyncio
    async def test_push_to_bare_remote_succeeds(self, agent: GitAgent, repo: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
        bare = tmp_path_factory.mktemp("bare") / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=repo, capture_output=True, text=True
        ).stdout.strip()

        result = await agent.execute(
            "push", remote=str(bare), branch=branch, repo_path=str(repo)
        )

        assert result.status == ActionStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_push_without_configured_remote_fails_gracefully(
        self, agent: GitAgent, repo: Path
    ) -> None:
        result = await agent.execute("push", repo_path=str(repo))

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_pull_from_bare_remote_succeeds(
        self, agent: GitAgent, repo: Path, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        bare = tmp_path_factory.mktemp("bare2") / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=repo, capture_output=True, text=True
        ).stdout.strip()
        subprocess.run(["git", "push", str(bare), branch], cwd=repo, check=True)

        result = await agent.execute("pull", remote=str(bare), branch=branch, repo_path=str(repo))

        assert result.status == ActionStatus.SUCCESS


class TestLog:
    @pytest.mark.asyncio
    async def test_log_returns_commits(self, agent: GitAgent, repo: Path) -> None:
        _commit_file(repo, "segundo.txt", "b", "segundo commit")
        _commit_file(repo, "tercero.txt", "c", "tercer commit")

        result = await agent.execute("log", n=10, repo_path=str(repo))

        assert result.status == ActionStatus.SUCCESS
        assert result.data["count"] == 3
        messages = [c["message"] for c in result.data["commits"]]
        assert messages[0] == "tercer commit"
        assert messages[-1] == "commit inicial"
        assert all(c["hash"] for c in result.data["commits"])

    @pytest.mark.asyncio
    async def test_log_respects_n(self, agent: GitAgent, repo: Path) -> None:
        _commit_file(repo, "segundo.txt", "b", "segundo commit")
        _commit_file(repo, "tercero.txt", "c", "tercer commit")

        result = await agent.execute("log", n=2, repo_path=str(repo))

        assert result.status == ActionStatus.SUCCESS
        assert result.data["count"] == 2

    @pytest.mark.asyncio
    async def test_log_invalid_n_fails_gracefully(self, agent: GitAgent, repo: Path) -> None:
        result = await agent.execute("log", n=0, repo_path=str(repo))

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_log_on_empty_repo_fails_gracefully(
        self, agent: GitAgent, empty_repo: Path
    ) -> None:
        result = await agent.execute("log", repo_path=str(empty_repo))

        assert result.status == ActionStatus.FAILED
        assert result.error is not None


class TestDiff:
    @pytest.mark.asyncio
    async def test_diff_unstaged_shows_change(self, agent: GitAgent, repo: Path) -> None:
        (repo / "readme.txt").write_text("cambiado", encoding="utf-8")

        result = await agent.execute("diff", repo_path=str(repo))

        assert result.status == ActionStatus.SUCCESS
        assert "readme.txt" in result.output
        assert "cambiado" in result.output

    @pytest.mark.asyncio
    async def test_diff_staged_only_shows_staged_change(self, agent: GitAgent, repo: Path) -> None:
        (repo / "readme.txt").write_text("cambiado", encoding="utf-8")

        unstaged = await agent.execute("diff", staged=True, repo_path=str(repo))
        assert unstaged.output.strip() == ""

        await agent.execute("add", repo_path=str(repo))
        staged = await agent.execute("diff", staged=True, repo_path=str(repo))
        assert "readme.txt" in staged.output


class TestBranch:
    @pytest.mark.asyncio
    async def test_branch_list_shows_current(self, agent: GitAgent, repo: Path) -> None:
        result = await agent.execute("branch_list", repo_path=str(repo))

        assert result.status == ActionStatus.SUCCESS
        assert result.data["count"] == 1
        assert result.data["branches"][0]["current"] is True

    @pytest.mark.asyncio
    async def test_branch_create_without_checkout(self, agent: GitAgent, repo: Path) -> None:
        result = await agent.execute("branch_create", name="feature-x", repo_path=str(repo))

        assert result.status == ActionStatus.SUCCESS
        branch_list = await agent.execute("branch_list", repo_path=str(repo))
        names = {b["name"] for b in branch_list.data["branches"]}
        assert "feature-x" in names
        current = next(b for b in branch_list.data["branches"] if b["current"])
        assert current["name"] != "feature-x"

    @pytest.mark.asyncio
    async def test_branch_create_with_checkout(self, agent: GitAgent, repo: Path) -> None:
        result = await agent.execute(
            "branch_create", name="feature-y", checkout=True, repo_path=str(repo)
        )

        assert result.status == ActionStatus.SUCCESS
        branch_list = await agent.execute("branch_list", repo_path=str(repo))
        current = next(b for b in branch_list.data["branches"] if b["current"])
        assert current["name"] == "feature-y"

    @pytest.mark.asyncio
    async def test_branch_checkout_switches_branch(self, agent: GitAgent, repo: Path) -> None:
        await agent.execute("branch_create", name="otra-rama", repo_path=str(repo))

        result = await agent.execute("branch_checkout", name="otra-rama", repo_path=str(repo))

        assert result.status == ActionStatus.SUCCESS
        branch_list = await agent.execute("branch_list", repo_path=str(repo))
        current = next(b for b in branch_list.data["branches"] if b["current"])
        assert current["name"] == "otra-rama"

    @pytest.mark.asyncio
    async def test_branch_checkout_nonexistent_fails_gracefully(
        self, agent: GitAgent, repo: Path
    ) -> None:
        result = await agent.execute("branch_checkout", name="no-existe", repo_path=str(repo))

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_branch_create_empty_name_fails_gracefully(
        self, agent: GitAgent, repo: Path
    ) -> None:
        result = await agent.execute("branch_create", name="  ", repo_path=str(repo))

        assert result.status == ActionStatus.FAILED
        assert result.error is not None


class TestReset:
    @pytest.mark.asyncio
    async def test_reset_soft_keeps_working_tree_staged(self, agent: GitAgent, repo: Path) -> None:
        _commit_file(repo, "segundo.txt", "b", "segundo commit")

        result = await agent.execute("reset", mode="soft", target="HEAD~1", repo_path=str(repo))

        assert result.status == ActionStatus.SUCCESS
        assert (repo / "segundo.txt").exists()
        status = await agent.execute("status", repo_path=str(repo))
        entries = {entry["path"]: entry["status"] for entry in status.data["files"]}
        assert entries.get("segundo.txt") == "A"

    @pytest.mark.asyncio
    async def test_reset_hard_discards_uncommitted_changes(
        self, agent: GitAgent, repo: Path
    ) -> None:
        (repo / "readme.txt").write_text("cambio no commiteado", encoding="utf-8")

        result = await agent.execute("reset", mode="hard", repo_path=str(repo))

        assert result.status == ActionStatus.SUCCESS
        assert (repo / "readme.txt").read_text(encoding="utf-8") == "hola"

    @pytest.mark.asyncio
    async def test_reset_default_mode_is_soft(self, agent: GitAgent, repo: Path) -> None:
        _commit_file(repo, "segundo.txt", "b", "segundo commit")

        result = await agent.execute("reset", target="HEAD~1", repo_path=str(repo))

        assert result.status == ActionStatus.SUCCESS
        # soft: el archivo del commit deshecho queda staged, no perdido
        status = await agent.execute("status", repo_path=str(repo))
        entries = {entry["path"]: entry["status"] for entry in status.data["files"]}
        assert entries.get("segundo.txt") == "A"

    @pytest.mark.asyncio
    async def test_reset_invalid_mode_fails_gracefully(self, agent: GitAgent, repo: Path) -> None:
        result = await agent.execute("reset", mode="mixed", repo_path=str(repo))

        assert result.status == ActionStatus.FAILED
        assert result.error is not None


class TestRepoPathErrors:
    @pytest.mark.asyncio
    async def test_nonexistent_repo_path_fails_gracefully(
        self, agent: GitAgent, tmp_path: Path
    ) -> None:
        missing = tmp_path / "no_existe"

        result = await agent.execute("status", repo_path=str(missing))

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_not_a_git_repo_fails_gracefully(self, agent: GitAgent, tmp_path: Path) -> None:
        result = await agent.execute("status", repo_path=str(tmp_path))

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_timeout(self, agent: GitAgent, repo: Path) -> None:
        result = await agent.execute("status", repo_path=str(repo), timeout=0.0000001)

        assert result.status == ActionStatus.FAILED
        assert result.error is not None
