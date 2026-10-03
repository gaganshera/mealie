from datetime import date, timedelta
from uuid import uuid4

import pytest
from icalendar import Calendar

from mealie.lang.providers import get_locale_provider
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.meal_plan.new_meal import ReadPlanEntry
from mealie.services.household_services.calendar_feed_service import CalendarFeedService


@pytest.fixture
def service(unfiltered_database: AllRepositories) -> CalendarFeedService:
    return CalendarFeedService(unfiltered_database)


def make_entry(entry_id: int, title: str, text: str = "", entry_type: str = "dinner") -> ReadPlanEntry:
    return ReadPlanEntry(
        id=entry_id,
        date=date(2026, 3, 14),
        entry_type=entry_type,
        title=title,
        text=text,
        group_id=uuid4(),
        user_id=uuid4(),
        household_id=uuid4(),
    )


def test_calendar_properties(service: CalendarFeedService):
    content = service.build_calendar([], "home", get_locale_provider(None), household_name="Family")
    calendar = Calendar.from_ical(content)

    assert str(calendar["prodid"]) == "-//Mealie//Meal Plan//EN"
    assert str(calendar["version"]) == "2.0"
    assert str(calendar["x-wr-calname"]) == "Mealie – Family"
    assert b"REFRESH-INTERVAL;VALUE=DURATION:PT1H" in content
    assert b"X-PUBLISHED-TTL:PT1H" in content
    assert calendar.walk("VEVENT") == []


@pytest.mark.parametrize(
    "title, text",
    [
        ("Pasta, beans; and more", "Use the big pot, not the small one; really"),
        ("Line one\nLine two", "Note\nwith\nnew lines"),
        ("Tacos 🌮 night", "Don't forget 🥑"),
        ('Back\\slash "quoted" colon: yes', "a;b,c\\d"),
    ],
)
def test_special_characters_round_trip(service: CalendarFeedService, title: str, text: str):
    content = service.build_calendar([make_entry(7, title, text)], "home", get_locale_provider(None))
    events = Calendar.from_ical(content).walk("VEVENT")

    assert len(events) == 1
    event = events[0]
    assert str(event["summary"]) == f"Dinner: {title}"
    assert str(event["description"]) == text
    assert str(event["uid"]) == "7@mealie"
    assert event.decoded("dtstart") == date(2026, 3, 14)
    assert event.decoded("dtend") == date(2026, 3, 14) + timedelta(days=1)
    assert "dtstamp" in event
