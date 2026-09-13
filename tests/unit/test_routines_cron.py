"""Tests de `routines/cron.py` — traducción del atajo `schedule` a cron.

Verifica en particular la conversión de convención de días (ISO lunes=0
vs. cron domingo=0), que es la parte no obvia — ver la tabla en el
docstring de `cron.py`.
"""

from __future__ import annotations

import pytest
from croniter import croniter

from aries.routines.cron import ScheduleError, schedule_to_cron


class TestScheduleToCron:
    def test_time_only_means_every_day(self) -> None:
        assert schedule_to_cron({"time": "07:00"}) == "0 7 * * *"

    def test_monday_translates_to_cron_one(self) -> None:
        # ISO lunes=0 -> cron 1
        assert schedule_to_cron({"time": "07:00", "days_of_week": [0]}) == "0 7 * * 1"

    def test_sunday_translates_to_cron_zero(self) -> None:
        # ISO domingo=6 -> cron 0
        assert schedule_to_cron({"time": "07:00", "days_of_week": [6]}) == "0 7 * * 0"

    def test_weekdays_monday_to_friday(self) -> None:
        # ISO [0,1,2,3,4] (lunes a viernes) -> cron [1,2,3,4,5]
        result = schedule_to_cron({"time": "07:00", "days_of_week": [0, 1, 2, 3, 4]})
        assert result == "0 7 * * 1,2,3,4,5"

    def test_days_are_sorted_and_deduplicated(self) -> None:
        result = schedule_to_cron({"time": "07:00", "days_of_week": [4, 0, 0, 2]})
        assert result == "0 7 * * 1,3,5"

    def test_empty_days_of_week_means_every_day(self) -> None:
        assert schedule_to_cron({"time": "07:00", "days_of_week": []}) == "0 7 * * *"

    def test_result_is_valid_for_croniter(self) -> None:
        cron = schedule_to_cron({"time": "07:00", "days_of_week": [0, 1, 2, 3, 4]})
        assert croniter.is_valid(cron)

    def test_missing_time_raises(self) -> None:
        with pytest.raises(ScheduleError):
            schedule_to_cron({"days_of_week": [0]})

    def test_malformed_time_raises(self) -> None:
        with pytest.raises(ScheduleError):
            schedule_to_cron({"time": "7am"})

    def test_time_out_of_range_raises(self) -> None:
        with pytest.raises(ScheduleError):
            schedule_to_cron({"time": "25:00"})

    def test_day_out_of_range_raises(self) -> None:
        with pytest.raises(ScheduleError):
            schedule_to_cron({"time": "07:00", "days_of_week": [7]})

    def test_days_of_week_not_a_list_raises(self) -> None:
        with pytest.raises(ScheduleError):
            schedule_to_cron({"time": "07:00", "days_of_week": "monday"})
