from datetime import date
from uuid import uuid4

from icalendar import Calendar

from mealie.lang.providers import get_locale_provider
from mealie.schema.meal_plan.new_meal import PlanEntryType, ReadPlanEntry
from mealie.services.household_services.calendar_feed_service import CalendarFeedService


def make_entry(title: str, text: str) -> ReadPlanEntry:
    return ReadPlanEntry(
        id=1,
        date=date(2026, 1, 1),
        entry_type=PlanEntryType.snack,
        title=title,
        text=text,
        group_id=uuid4(),
        user_id=uuid4(),
        household_id=uuid4(),
    )


def test_calendar_feed_builder_round_trip():
    title = "Fish, chips; peas\nand 🍕"
    text = "Line one, with comma; semicolon\nLine two 🎉"
    ics = CalendarFeedService.build_calendar([make_entry(title, text)], "group", "Family, Home", get_locale_provider())
    cal = Calendar.from_ical(ics)

    assert str(cal["prodid"]) == "-//Mealie//Meal Plan//EN"
    assert str(cal["version"]) == "2.0"
    assert str(cal["x-wr-calname"]) == "Mealie – Family, Home"
    assert "REFRESH-INTERVAL;VALUE=DURATION:PT1H" in ics.decode()
    assert "X-PUBLISHED-TTL:PT1H" in ics.decode()

    [event] = cal.walk("VEVENT")
    assert str(event["summary"]) == f"Snack: {title}"
    assert str(event["description"]) == text
    assert str(event["uid"]) == "1@mealie"
