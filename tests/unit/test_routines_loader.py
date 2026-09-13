"""Tests de `routines/loader.py` — parseo/validación real contra
archivos JSON de verdad en un directorio temporal, mismo criterio que
`tests/unit/test_plugin_manifest.py` para plugins."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aries.routines.loader import RoutineError, load_routines, parse_routine
from aries.routines.models import AgentAction, ChainedAction, SpeakAction


def _write(tmp_path: Path, name: str, data: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestParseRoutineSpeak:
    def test_schedule_shortcut_translated_to_cron(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "buenos-dias.json",
            {
                "id": "buenos-dias",
                "schedule": {"time": "07:00", "days_of_week": [0, 1, 2, 3, 4]},
                "action": {"type": "speak", "text": "Buenos días"},
            },
        )
        routine = parse_routine(path)
        assert routine.id == "buenos-dias"
        assert routine.cron == "0 7 * * 1,2,3,4,5"
        assert routine.on_startup is False
        assert routine.enabled is True
        assert routine.action == SpeakAction(text="Buenos días")

    def test_raw_cron_accepted_directly(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "r.json",
            {"id": "r", "cron": "*/15 9-18 * * *", "action": {"type": "speak", "text": "hola"}},
        )
        routine = parse_routine(path)
        assert routine.cron == "*/15 9-18 * * *"

    def test_on_startup(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "r.json", {"id": "r", "on_startup": True, "action": {"type": "speak", "text": "hola"}})
        routine = parse_routine(path)
        assert routine.on_startup is True
        assert routine.cron is None

    def test_disabled_routine(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "r.json",
            {"id": "r", "cron": "0 7 * * *", "enabled": False, "action": {"type": "speak", "text": "hola"}},
        )
        assert parse_routine(path).enabled is False


class TestParseRoutineAgentAndChained:
    def test_agent_action(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "r.json",
            {
                "id": "r",
                "cron": "0 * * * *",
                "action": {"type": "agent", "agent_name": "git", "action": "status", "params": {"repo_path": "."}},
            },
        )
        routine = parse_routine(path)
        assert routine.action == AgentAction(agent_name="git", action="status", params={"repo_path": "."})

    def test_agent_action_without_params_defaults_to_empty_dict(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path, "r.json", {"id": "r", "cron": "0 * * * *", "action": {"type": "agent", "agent_name": "git", "action": "status"}}
        )
        assert parse_routine(path).action.params == {}

    def test_chained_action(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "r.json",
            {
                "id": "r",
                "cron": "0 * * * *",
                "action": {
                    "type": "chained",
                    "actions": [
                        {"type": "agent", "agent_name": "git", "action": "status"},
                        {"type": "speak", "text": "listo"},
                    ],
                },
            },
        )
        routine = parse_routine(path)
        assert isinstance(routine.action, ChainedAction)
        assert routine.action.actions == (
            AgentAction(agent_name="git", action="status", params={}),
            SpeakAction(text="listo"),
        )

    def test_nested_chained_rejected(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "r.json",
            {
                "id": "r",
                "cron": "0 * * * *",
                "action": {"type": "chained", "actions": [{"type": "chained", "actions": []}]},
            },
        )
        with pytest.raises(RoutineError):
            parse_routine(path)


class TestParseRoutineValidationErrors:
    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(RoutineError):
            parse_routine(tmp_path / "no-existe.json")

    def test_malformed_json(self, tmp_path: Path) -> None:
        path = tmp_path / "r.json"
        path.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(RoutineError):
            parse_routine(path)

    def test_invalid_id(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "r.json", {"id": "Con Espacios", "cron": "0 * * * *", "action": {"type": "speak", "text": "hola"}})
        with pytest.raises(RoutineError):
            parse_routine(path)

    def test_cron_and_schedule_mutually_exclusive(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "r.json",
            {"id": "r", "cron": "0 * * * *", "schedule": {"time": "07:00"}, "action": {"type": "speak", "text": "hola"}},
        )
        with pytest.raises(RoutineError):
            parse_routine(path)

    def test_on_startup_and_cron_mutually_exclusive(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            "r.json",
            {"id": "r", "on_startup": True, "cron": "0 * * * *", "action": {"type": "speak", "text": "hola"}},
        )
        with pytest.raises(RoutineError):
            parse_routine(path)

    def test_missing_schedule_and_cron_and_on_startup(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "r.json", {"id": "r", "action": {"type": "speak", "text": "hola"}})
        with pytest.raises(RoutineError):
            parse_routine(path)

    def test_invalid_cron_expression(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "r.json", {"id": "r", "cron": "not a cron", "action": {"type": "speak", "text": "hola"}})
        with pytest.raises(RoutineError):
            parse_routine(path)

    def test_unknown_action_type(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "r.json", {"id": "r", "cron": "0 * * * *", "action": {"type": "dance"}})
        with pytest.raises(RoutineError):
            parse_routine(path)

    def test_missing_action(self, tmp_path: Path) -> None:
        path = _write(tmp_path, "r.json", {"id": "r", "cron": "0 * * * *"})
        with pytest.raises(RoutineError):
            parse_routine(path)


class TestLoadRoutines:
    def test_missing_directory_returns_empty_list(self, tmp_path: Path) -> None:
        assert load_routines(tmp_path / "no-existe") == []

    def test_loads_all_valid_routines_in_directory(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.json", {"id": "a", "cron": "0 7 * * *", "action": {"type": "speak", "text": "a"}})
        _write(tmp_path, "b.json", {"id": "b", "on_startup": True, "action": {"type": "speak", "text": "b"}})
        routines = load_routines(tmp_path)
        assert sorted(r.id for r in routines) == ["a", "b"]

    def test_invalid_routine_is_skipped_not_fatal(self, tmp_path: Path) -> None:
        _write(tmp_path, "good.json", {"id": "good", "cron": "0 7 * * *", "action": {"type": "speak", "text": "ok"}})
        _write(tmp_path, "bad.json", {"id": "Bad Id", "cron": "0 7 * * *", "action": {"type": "speak", "text": "ok"}})
        routines = load_routines(tmp_path)
        assert [r.id for r in routines] == ["good"]

    def test_ignores_non_json_files(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.json", {"id": "a", "cron": "0 7 * * *", "action": {"type": "speak", "text": "a"}})
        (tmp_path / "README.md").write_text("no es una rutina", encoding="utf-8")
        routines = load_routines(tmp_path)
        assert [r.id for r in routines] == ["a"]
