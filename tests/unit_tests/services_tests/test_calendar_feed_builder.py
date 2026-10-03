import uuid
from datetime import date, timedelta

import pytest
from icalendar import Calendar
from sqlalchemy.orm import Session

from mealie.lang.providers import get_locale_provider
from mealie.repos.all_repositories import get_repositories
from mealie.schema.meal_plan.new_meal import PlanEntryType, ReadPlanEntry
from mealie.schema.recipe.recipe import RecipeSummary
from mealie.services.household_services.calendar_feed_service import CalendarFeedService


@pytest.fixture
def service(session: Session) -> CalendarFeedService:
    return CalendarFeedService(get_repositories(session, group_id=None, household_id=None))


def make_entry(entry_id: int, *, title: str = "", text: str = "", recipe: RecipeSummary | None = None) -> ReadPlanEntry:
    return ReadPlanEntry(
        id=entry_id,
        date=date(2026, 10, 3),
        entry_type=PlanEntryType.dinner,
        title=title,
        text=text,
        recipe_id=recipe.id if recipe else None,
        recipe=recipe,
        group_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        household_id=uuid.uuid4(),
    )


def build(service: CalendarFeedService, entries: list[ReadPlanEntry], household_name: str = "Family") -> Calendar:
    ical = service.build_calendar(entries, "home", household_name, get_locale_provider(None))
    return Calendar.from_ical(ical)


def test_calendar_properties(service: CalendarFeedService):
    cal = build(service, [], household_name="Smith; Jones, & Co")

    assert str(cal["PRODID"]) == "-//Mealie//Meal Plan//EN"
    assert str(cal["VERSION"]) == "2.0"
    assert str(cal["X-WR-CALNAME"]) == "Mealie – Smith; Jones, & Co"
    assert cal.decoded("REFRESH-INTERVAL") == timedelta(hours=1)
    assert cal["REFRESH-INTERVAL"].params["VALUE"] == "DURATION"
    assert str(cal["X-PUBLISHED-TTL"]) == "PT1H"
    assert cal.walk("VEVENT") == []

    raw = service.build_calendar([], "home", "Family", get_locale_provider(None)).decode()
    assert "REFRESH-INTERVAL;VALUE=DURATION:PT1H\r\n" in raw
    assert "X-PUBLISHED-TTL:PT1H\r\n" in raw


@pytest.mark.parametrize(
    "value",
    [
        "Fish, chips; and peas",
        "Line one\nLine two\nLine three",
        "Pizza 🍕 night — très bon",
        'Backslash \\ and "quotes"',
    ],
)
def test_special_characters_round_trip(service: CalendarFeedService, value: str):
    recipe = RecipeSummary(id=uuid.uuid4(), name=value, slug="some-recipe")
    cal = build(service, [make_entry(1, title=value, text=value), make_entry(2, recipe=recipe, text=value)])
    events = {str(event["UID"]): event for event in cal.walk("VEVENT")}

    note_event = events["1@mealie"]
    assert str(note_event["SUMMARY"]) == f"Dinner: {value}"
    assert str(note_event["DESCRIPTION"]) == value

    recipe_event = events["2@mealie"]
    assert str(recipe_event["SUMMARY"]) == f"Dinner: {value}"
    assert str(recipe_event["URL"]).endswith("/g/home/r/some-recipe")
    assert str(recipe_event["DESCRIPTION"]) == f"{recipe_event['URL']}\n\n{value}"


def test_all_day_event(service: CalendarFeedService):
    cal = build(service, [make_entry(7, title="Soup")])
    (event,) = cal.walk("VEVENT")

    assert event.decoded("DTSTART") == date(2026, 10, 3)
    assert event.decoded("DTEND") == date(2026, 10, 4)
    assert "DTSTAMP" in event
