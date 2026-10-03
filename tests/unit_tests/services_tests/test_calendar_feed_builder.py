from datetime import date, timedelta
from uuid import uuid4

from icalendar import Calendar

from mealie.lang.providers import get_locale_provider
from mealie.schema.meal_plan.new_meal import PlanEntryType, ReadPlanEntry
from mealie.services.household_services.calendar_feed_service import CalendarFeedService


def make_entry(entry_id: int, title: str, text: str = "", entry_type=PlanEntryType.dinner) -> ReadPlanEntry:
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


def build(entries: list[ReadPlanEntry], household_name: str = "Family") -> Calendar:
    data = CalendarFeedService.build_calendar(
        entries, "home", get_locale_provider("en-US"), household_name=household_name
    )
    assert isinstance(data, bytes)
    return Calendar.from_ical(data)


def test_calendar_properties():
    cal = build([], household_name="The Smiths")

    assert str(cal["prodid"]) == "-//Mealie//Meal Plan//EN"
    assert str(cal["version"]) == "2.0"
    assert str(cal["x-wr-calname"]) == "Mealie – The Smiths"
    assert cal.decoded("refresh-interval") == timedelta(hours=1)
    assert str(cal["x-published-ttl"]) == "PT1H"
    assert list(cal.walk("VEVENT")) == []


def test_special_characters_round_trip():
    title = 'Pasta, "fresh"; with sauce\\ \U0001f35d'
    text = "Line one, with comma;\nLine two: semicolon; emoji \U0001f969\n\nLast line"
    cal = build([make_entry(42, title, text, PlanEntryType.side)])

    [event] = cal.walk("VEVENT")
    assert str(event["summary"]) == f"Side: {title}"
    assert str(event["description"]) == text
    assert str(event["uid"]) == "42@mealie"
    assert event.decoded("dtstart") == date(2026, 3, 14)
    assert event.decoded("dtend") == date(2026, 3, 15)
    assert "dtstamp" in event
