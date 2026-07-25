"""Pruebas unitarias para ProcessAgent."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from aries.agents.process.agent import DEFAULT_TIMEOUT_SECONDS, ProcessAgent
from aries.contracts.agent import ActionStatus


@pytest.fixture(name="agent")
def fixture_agent() -> ProcessAgent:
    return ProcessAgent()


class TestMetadata:
    def test_agent_name(self, agent: ProcessAgent) -> None:
        assert agent.get_agent_name() == "process"

    def test_capabilities_include_all_documented_actions(self, agent: ProcessAgent) -> None:
        capabilities = agent.get_capabilities()
        for action in [
            "run_command",
            "run_script",
            "kill_process",
            "list_processes",
            "get_process_info",
        ]:
            assert action in capabilities

    def test_requires_confirmation_true_for_kill_process(self, agent: ProcessAgent) -> None:
        assert agent.requires_confirmation("kill_process") is True

    @pytest.mark.parametrize(
        "command", ["rm -rf /tmp", "del archivo.txt", "format c:", "echo hola && rm -rf /"]
    )
    def test_requires_confirmation_true_for_known_destructive_commands(
        self, agent: ProcessAgent, command: str
    ) -> None:
        assert agent.requires_confirmation("run_command", command=command) is True

    @pytest.mark.parametrize("command", ["echo hola", "dir", "python --version"])
    def test_requires_confirmation_false_for_benign_commands(
        self, agent: ProcessAgent, command: str
    ) -> None:
        assert agent.requires_confirmation("run_command", command=command) is False

    def test_requires_confirmation_false_for_run_command_without_content(
        self, agent: ProcessAgent
    ) -> None:
        # Sin el kwarg `command` no hay forma de evaluar el contenido; el
        # default es False (no bloquear a ciegas), no True.
        assert agent.requires_confirmation("run_command") is False

    @pytest.mark.parametrize("action", ["run_script", "list_processes", "get_process_info"])
    def test_requires_confirmation_false_for_non_destructive_actions(
        self, agent: ProcessAgent, action: str
    ) -> None:
        assert agent.requires_confirmation(action) is False

    @pytest.mark.asyncio
    async def test_is_available(self, agent: ProcessAgent) -> None:
        assert await agent.is_available() is True

    @pytest.mark.asyncio
    async def test_unknown_action_fails_gracefully(self, agent: ProcessAgent) -> None:
        result = await agent.execute("reboot_system")

        assert result.status == ActionStatus.FAILED
        assert "reboot_system" in result.error


class TestRunCommand:
    @pytest.mark.asyncio
    async def test_run_command_success(self, agent: ProcessAgent) -> None:
        # "echo" no es un ejecutable real en Windows (es interno de cmd.exe),
        # así que con shell=False el comando de prueba debe ser un programa
        # real. `sys.executable` siempre lo es.
        command = f'"{sys.executable}" -c "print(1 + 1)"'

        result = await agent.execute("run_command", command=command)

        assert result.status == ActionStatus.SUCCESS
        assert result.output.strip() == "2"
        assert result.data["exit_code"] == 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_run_command_unquoted_windows_path_is_not_corrupted(
        self, agent: ProcessAgent
    ) -> None:
        # Regresión: shlex.split() en modo POSIX (el default) trata "\" como
        # carácter de escape fuera de comillas, corrompiendo una ruta
        # Windows sin comillas (ej. C:\Users\...\python.exe se convertía en
        # C:Users...python.exe y fallaba con FileNotFoundError). La ruta va
        # deliberadamente SIN comillas acá para ejercitar ese caso; el
        # argumento -c sigue entre comillas para confirmar que ese caso
        # (visto en test_run_command_success) sigue funcionando también.
        assert "\\" in sys.executable
        command = f'{sys.executable} -c "print(3 + 4)"'

        result = await agent.execute("run_command", command=command)

        assert result.status == ActionStatus.SUCCESS
        assert result.output.strip() == "7"
        assert result.data["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_run_command_nonexistent_fails_gracefully(self, agent: ProcessAgent) -> None:
        # Con shell=False, un ejecutable inexistente SÍ levanta
        # FileNotFoundError de Python directamente (a diferencia del extinto
        # comportamiento con shell=True) — el agente lo atrapa y retorna
        # FAILED, igual que run_script con un script inexistente.
        result = await agent.execute("run_command", command="programa_que_no_existe_xyz123")

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_run_command_does_not_chain_via_shell_metacharacters(
        self, agent: ProcessAgent, tmp_path: Path
    ) -> None:
        # Prueba de regresión de seguridad: sin shell=True, "&&" ya no
        # encadena un segundo comando — se pasa como argv literal al
        # programa, que lo ignora (o falla) sin ejecutar nada más.
        guarded_file = tmp_path / "no_deberia_borrarse.txt"
        guarded_file.write_text("contenido", encoding="utf-8")
        command = f'"{sys.executable}" -c "print(1)" && del "{guarded_file}"'

        result = await agent.execute("run_command", command=command)

        assert guarded_file.exists()
        assert result.status == ActionStatus.SUCCESS
        assert result.output.strip() == "1"

    @pytest.mark.asyncio
    async def test_run_command_malformed_quoting_fails_gracefully(
        self, agent: ProcessAgent
    ) -> None:
        result = await agent.execute("run_command", command='echo "sin cerrar')

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_run_command_empty_string_fails_gracefully(self, agent: ProcessAgent) -> None:
        result = await agent.execute("run_command", command="   ")

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_run_command_timeout(self, agent: ProcessAgent) -> None:
        result = await agent.execute(
            "run_command", command="ping 127.0.0.1 -n 10", timeout=0.5
        )

        assert result.status == ActionStatus.FAILED
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_run_command_default_timeout_is_reasonable(self) -> None:
        assert 0 < DEFAULT_TIMEOUT_SECONDS <= 120

    @pytest.mark.asyncio
    async def test_run_command_respects_cwd(self, agent: ProcessAgent, tmp_path: Path) -> None:
        # "cd" es interno de cmd.exe, no un ejecutable — se verifica cwd
        # con un programa real que reporte su propio directorio de trabajo.
        command = f'"{sys.executable}" -c "import os; print(os.getcwd())"'

        result = await agent.execute("run_command", command=command, cwd=str(tmp_path))

        assert result.status == ActionStatus.SUCCESS
        assert result.output.strip() == str(tmp_path)

    @pytest.mark.asyncio
    async def test_run_command_missing_command_kwarg_fails_gracefully(
        self, agent: ProcessAgent
    ) -> None:
        result = await agent.execute("run_command")

        assert result.status == ActionStatus.FAILED
        assert result.error is not None


class TestRunScript:
    @pytest.mark.asyncio
    async def test_run_script_python_success(self, agent: ProcessAgent, tmp_path: Path) -> None:
        script = tmp_path / "hola.py"
        script.write_text("print('hola desde script')\n", encoding="utf-8")

        result = await agent.execute("run_script", path=str(script))

        assert result.status == ActionStatus.SUCCESS
        assert "hola desde script" in result.output
        assert result.data["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_run_script_with_args(self, agent: ProcessAgent, tmp_path: Path) -> None:
        script = tmp_path / "saluda.py"
        script.write_text(
            "import sys\nprint('hola', sys.argv[1])\n", encoding="utf-8"
        )

        result = await agent.execute("run_script", path=str(script), args=["mundo"])

        assert result.status == ActionStatus.SUCCESS
        assert "hola mundo" in result.output

    @pytest.mark.asyncio
    async def test_run_script_missing_returns_failed(
        self, agent: ProcessAgent, tmp_path: Path
    ) -> None:
        missing = tmp_path / "no_existe.py"

        result = await agent.execute("run_script", path=str(missing))

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_run_script_on_directory_fails(
        self, agent: ProcessAgent, tmp_path: Path
    ) -> None:
        result = await agent.execute("run_script", path=str(tmp_path))

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_run_script_timeout(self, agent: ProcessAgent, tmp_path: Path) -> None:
        script = tmp_path / "lento.py"
        script.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")

        result = await agent.execute("run_script", path=str(script), timeout=0.5)

        assert result.status == ActionStatus.FAILED
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_run_script_explicit_interpreter(
        self, agent: ProcessAgent, tmp_path: Path
    ) -> None:
        script = tmp_path / "hola.py"
        script.write_text("print('via interprete explicito')\n", encoding="utf-8")

        result = await agent.execute(
            "run_script", path=str(script), interpreter=sys.executable
        )

        assert result.status == ActionStatus.SUCCESS
        assert "via interprete explicito" in result.output


class TestKillProcess:
    @pytest.mark.asyncio
    async def test_kill_process_terminates_real_child(self, agent: ProcessAgent) -> None:
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            time.sleep(0.3)  # dar tiempo a que el proceso hijo arranque

            result = await agent.execute("kill_process", pid=child.pid)

            assert result.status == ActionStatus.SUCCESS
            assert result.data["pid"] == child.pid
            child.wait(timeout=5)
            assert child.returncode is not None
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)

    @pytest.mark.asyncio
    async def test_kill_process_nonexistent_pid_fails_gracefully(
        self, agent: ProcessAgent
    ) -> None:
        result = await agent.execute("kill_process", pid=999_999)

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_kill_process_permission_denied(
        self, agent: ProcessAgent, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No apuntamos a un PID protegido real del sistema (riesgoso incluso
        # si en la práctica siempre falla) — simulamos el escenario
        # inyectando el error que el SO devolvería, para ejercitar el mismo
        # camino de código de forma determinista y segura.
        monkeypatch.setattr(
            agent,
            "_tasklist",
            lambda extra_args=None: [
                {"pid": 4, "name": "System", "session_name": "Services", "session_number": "0", "mem_usage": "0 KB"}
            ],
        )

        def _raise_permission_error(pid: int, sig: int) -> None:
            raise PermissionError("[WinError 5] Acceso denegado")

        monkeypatch.setattr("aries.agents.process.agent.os.kill", _raise_permission_error)

        result = await agent.execute("kill_process", pid=4)

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_kill_process_invalid_pid_type_fails_gracefully(
        self, agent: ProcessAgent
    ) -> None:
        result = await agent.execute("kill_process", pid="not-a-pid")

        assert result.status == ActionStatus.FAILED
        assert result.error is not None


class TestListProcesses:
    @pytest.mark.asyncio
    async def test_list_processes_returns_running_processes(self, agent: ProcessAgent) -> None:
        result = await agent.execute("list_processes")

        assert result.status == ActionStatus.SUCCESS
        assert result.data["count"] > 0
        assert len(result.data["processes"]) == result.data["count"]
        first = result.data["processes"][0]
        assert "pid" in first
        assert "name" in first
        assert isinstance(first["pid"], int)

    @pytest.mark.asyncio
    async def test_list_processes_includes_current_python_process(
        self, agent: ProcessAgent
    ) -> None:
        result = await agent.execute("list_processes")

        pids = {entry["pid"] for entry in result.data["processes"]}
        assert os.getpid() in pids


class TestGetProcessInfo:
    @pytest.mark.asyncio
    async def test_get_process_info_for_current_process(self, agent: ProcessAgent) -> None:
        result = await agent.execute("get_process_info", pid=os.getpid())

        assert result.status == ActionStatus.SUCCESS
        assert result.data["pid"] == os.getpid()
        assert result.data["name"]

    @pytest.mark.asyncio
    async def test_get_process_info_nonexistent_pid_fails_gracefully(
        self, agent: ProcessAgent
    ) -> None:
        result = await agent.execute("get_process_info", pid=999_999)

        assert result.status == ActionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_get_process_info_invalid_pid_type_fails_gracefully(
        self, agent: ProcessAgent
    ) -> None:
        result = await agent.execute("get_process_info", pid="not-a-pid")

        assert result.status == ActionStatus.FAILED
        assert result.error is not None
