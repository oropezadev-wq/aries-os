"""Pruebas de `GET /health` contra la app real de `aries.api` (lifespan real,
vía `with TestClient(app)`).

Se reemplazan por dobles, después del arranque real y dentro del `with`, solo
las dependencias EXTERNAS cuyo estado el test necesita controlar (Redis vía
`app.state.health_redis`, Ollama vía `app.state.llm_provider`, y en un caso el
task de `Kernel.run()`); el resto — app, lifespan, Kernel corriendo, derivación
de `status` — es real. El caso "Redis caído" usa el cliente REAL apuntando a un
puerto cerrado, no un doble.
"""

from __future__ import annotations

import asyncio
import time

import pytest
import redis as redis_sync
from fastapi.testclient import TestClient

import aries.api as api
from aries.api import app
from aries.contracts.llm import ILLMProvider, LLMResponse


class FakeLLMProvider(ILLMProvider):
    """`ILLMProvider` cuyo `is_available()` se controla desde el test."""

    def __init__(self, mode: str = "up") -> None:
        self.mode = mode  # "up" | "down" | "hang" | "ignore_cancel"

    async def complete(self, prompt: str, temperature: float = 0.7, max_tokens: int | None = None, **kwargs) -> LLMResponse:
        return LLMResponse(content="", model="fake", tokens_used=0)

    async def embed(self, text: str) -> list[float]:
        return []

    async def is_available(self) -> bool:
        if self.mode == "down":
            return False
        if self.mode == "hang":
            await asyncio.sleep(30)
        if self.mode == "ignore_cancel":
            # Un probe mal portado que se traga la cancelación: `wait_for`
            # no puede terminarlo a tiempo, solo el tope global lo corta.
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                await asyncio.sleep(30)
        return True

    async def close(self) -> None:
        return None

    def get_model_name(self) -> str:
        return "fake"


class FakeRedis:
    async def ping(self) -> bool:
        return True


class DeadTask:
    """Doble mínimo de un `asyncio.Task` ya terminado."""

    def __init__(self, error: BaseException | None = None, *, cancelled: bool = False) -> None:
        self._error = error
        self._cancelled = cancelled

    def done(self) -> bool:
        return True

    def cancelled(self) -> bool:
        return self._cancelled

    def exception(self) -> BaseException | None:
        return self._error


def _healthy_dependencies() -> None:
    """Deja Redis y Ollama sanos (dobles) sobre el `app.state` del lifespan
    real ya arrancado, para que cada test rompa solo lo que quiere probar."""
    app.state.health_redis = FakeRedis()
    app.state.llm_provider = FakeLLMProvider("up")


def _redis_reachable(url: str) -> bool:
    try:
        redis_sync.Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1).ping()
        return True
    except redis_sync.exceptions.RedisError:
        return False


class TestHealthAllOk:
    def test_all_checks_ok_and_criticality_is_as_designed(self) -> None:
        with TestClient(app) as client:
            _healthy_dependencies()
            response = client.get("/health")

        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "ok"
        assert body["checks"] == {
            "kernel": {"status": "ok", "critical": True, "detail": None},
            "redis": {"status": "ok", "critical": False, "detail": None},
            "ollama": {"status": "ok", "critical": False, "detail": None},
        }

    def test_real_redis_client_reports_ok(self) -> None:
        if not _redis_reachable(api.settings.redis_url):
            pytest.skip(f"Redis no alcanzable en {api.settings.redis_url}")

        with TestClient(app) as client:
            app.state.llm_provider = FakeLLMProvider("up")  # Redis queda el cliente real del lifespan
            response = client.get("/health")

        assert response.json()["checks"]["redis"]["status"] == "ok"
        assert response.json()["status"] == "ok"


class TestApiUpButRedisDown:
    def test_reports_degraded_not_critical_and_still_200(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Antes de arrancar el lifespan: el cliente REAL del health se construye
        # con esta URL (puerto cerrado) y estos topes cortos.
        monkeypatch.setattr(api.settings, "redis_url", "redis://localhost:1/0")
        monkeypatch.setattr(api, "_HEALTH_CHECK_TIMEOUT_SECONDS", 0.5)

        with TestClient(app) as client:
            app.state.llm_provider = FakeLLMProvider("up")
            response = client.get("/health")

        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "degraded"
        assert body["checks"]["redis"]["status"] == "error"
        assert body["checks"]["redis"]["critical"] is False
        assert body["checks"]["redis"]["detail"]
        assert body["checks"]["ollama"]["status"] == "ok"
        assert body["checks"]["kernel"]["status"] == "ok"


class TestApiUpButOllamaDown:
    def test_reports_degraded_not_critical_and_still_200(self) -> None:
        with TestClient(app) as client:
            _healthy_dependencies()
            app.state.llm_provider = FakeLLMProvider("down")
            response = client.get("/health")

        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "degraded"
        assert body["checks"]["ollama"] == {"status": "error", "critical": False, "detail": "Ollama no disponible"}
        assert body["checks"]["redis"]["status"] == "ok"

    def test_hung_ollama_is_capped_by_the_probe_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(api, "_HEALTH_CHECK_TIMEOUT_SECONDS", 0.2)

        with TestClient(app) as client:
            _healthy_dependencies()
            app.state.llm_provider = FakeLLMProvider("hang")
            started = time.monotonic()
            response = client.get("/health")
            elapsed = time.monotonic() - started

        body = response.json()
        assert elapsed < 2.0  # el probe colgaba 30s
        assert body["status"] == "degraded"
        assert body["checks"]["ollama"]["detail"].startswith("timeout")

    def test_probe_that_ignores_cancellation_is_capped_by_the_global_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(api, "_HEALTH_CHECK_TIMEOUT_SECONDS", 0.2)
        monkeypatch.setattr(api, "_HEALTH_TOTAL_TIMEOUT_SECONDS", 0.5)

        with TestClient(app) as client:
            _healthy_dependencies()
            app.state.llm_provider = FakeLLMProvider("ignore_cancel")
            started = time.monotonic()
            response = client.get("/health")
            elapsed = time.monotonic() - started

        body = response.json()
        assert elapsed < 2.0
        assert body["status"] == "degraded"
        assert body["checks"]["ollama"]["detail"].startswith("timeout global")


class TestKernelRunLoopDead:
    def test_dead_run_loop_is_critical_and_reports_the_cause(self) -> None:
        with TestClient(app) as client:
            _healthy_dependencies()
            app.state.kernel_run_task = DeadTask(RuntimeError("boom en el tick"))
            response = client.get("/health")

        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "critical"
        assert body["checks"]["kernel"]["status"] == "error"
        assert body["checks"]["kernel"]["critical"] is True
        assert "boom en el tick" in body["checks"]["kernel"]["detail"]

    def test_cancelled_run_loop_is_critical(self) -> None:
        with TestClient(app) as client:
            _healthy_dependencies()
            app.state.kernel_run_task = DeadTask(cancelled=True)
            response = client.get("/health")

        assert response.json()["status"] == "critical"
        assert "cancelado" in response.json()["checks"]["kernel"]["detail"]

    def test_critical_wins_over_a_simultaneous_non_critical_failure(self) -> None:
        with TestClient(app) as client:
            _healthy_dependencies()
            app.state.llm_provider = FakeLLMProvider("down")
            app.state.kernel_run_task = DeadTask(RuntimeError("x"))
            response = client.get("/health")

        assert response.json()["status"] == "critical"


class TestHealthWithoutInitializedState:
    def test_missing_state_reports_errors_instead_of_crashing(self) -> None:
        with TestClient(app) as client:
            app.state.health_redis = None
            app.state.llm_provider = None
            app.state.kernel_run_task = None
            response = client.get("/health")

        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "critical"
        assert body["checks"]["kernel"]["detail"] == "Kernel no inicializado"
        assert body["checks"]["redis"]["status"] == "error"
        assert body["checks"]["ollama"]["status"] == "error"
