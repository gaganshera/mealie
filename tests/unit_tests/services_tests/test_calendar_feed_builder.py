from datetime import date, timedelta
from uuid import uuid4

from icalendar import Calendar
from sqlalchemy.orm import Session

from mealie.lang.providers import get_locale_provider
from mealie.repos.all_repositories import get_repositories
from mealie.schema.meal_plan.new_meal import PlanEntryType, ReadPlanEntry
from mealie.services.household_services.calendar_feed_service import CalendarFeedService


def make_entry(**kwargs) -> ReadPlanEntry:
    data = {
        "id": 1,
        "date": date(2026, 10, 3),
        "entry_type": PlanEntryType.dinner,
        "title": "",
        "text": "",
        "group_id": uuid4(),
        "user_id": uuid4(),
        "household_id": uuid4(),
        **kwargs,
    }
    return ReadPlanEntry(**data)


def build(session: Session, entries: list[ReadPlanEntry], household_name: str = "Home") -> Calendar:
    service = CalendarFeedService(get_repositories(session))
    return Calendar.from_ical(service.build_calendar(entries, "home", household_name, get_locale_provider()))


def test_calendar_properties(session: Session):
    cal = build(session, [], household_name="The Smiths")

    assert str(cal["prodid"]) == "-//Mealie//Meal Plan//EN"
    assert str(cal["version"]) == "2.0"
    assert str(cal["x-wr-calname"]) == "Mealie – The Smiths"
    assert cal.decoded("refresh-interval") == timedelta(hours=1)
    assert cal["x-published-ttl"].to_ical() == b"PT1H"
    assert cal.walk("VEVENT") == []


def test_all_day_event(session: Session):
    [event] = build(session, [make_entry(id=42, title="Pizza night")]).walk("VEVENT")

    assert str(event["uid"]) == "42@mealie"
    assert str(event["summary"]) == "Dinner: Pizza night"
    assert event.decoded("dtstart") == date(2026, 10, 3)
    assert event.decoded("dtend") == date(2026, 10, 4)
    assert "dtstamp" in event


def test_special_characters_round_trip(session: Session):
    title = "Fish, chips; peas\nand 🍕 \\ more"
    text = "Line one, with comma; semicolon\nLine two 🎉"
    [event] = build(session, [make_entry(title=title, text=text)]).walk("VEVENT")

    assert str(event["summary"]) == f"Dinner: {title}"
    assert str(event["description"]) == text
