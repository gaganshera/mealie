from datetime import date, timedelta
from uuid import uuid4

import pytest
from icalendar import Calendar

from mealie.lang.providers import get_locale_provider
from mealie.schema.meal_plan.new_meal import PlanEntryType, ReadPlanEntry
from mealie.schema.recipe.recipe import RecipeSummary
from mealie.services.household_services.calendar_feed_service import CalendarFeedService, hash_token


def make_entry(entry_id: int, title: str = "", text: str = "", recipe: RecipeSummary | None = None) -> ReadPlanEntry:
    return ReadPlanEntry(
        id=entry_id,
        date=date(2026, 10, 3),
        entry_type=PlanEntryType.dinner,
        title=title,
        text=text,
        recipe_id=recipe.id if recipe else None,
        recipe=recipe,
        group_id=uuid4(),
        user_id=uuid4(),
        household_id=uuid4(),
    )


def build(entries: list[ReadPlanEntry], household_name: str = "Home") -> Calendar:
    service = CalendarFeedService(repos=None)  # type: ignore[arg-type]
    content = service.build_calendar(entries, "my-group", household_name, get_locale_provider(accept_language=None))
    return Calendar.from_ical(content)


def test_calendar_properties():
    calendar = build([], household_name="The Smiths")
    assert str(calendar["prodid"]) == "-//Mealie//Meal Plan//EN"
    assert str(calendar["version"]) == "2.0"
    assert str(calendar["x-wr-calname"]) == "Mealie – The Smiths"
    assert calendar["refresh-interval"].dt == timedelta(hours=1)
    assert str(calendar["x-published-ttl"]) == "PT1H"
    assert calendar.walk("VEVENT") == []


@pytest.mark.parametrize(
    "value",
    [
        "Fish, chips; peas",
        "Line one\nLine two",
        "Pizza 🍕 night",
        'Back\\slash and "quotes"',
    ],
)
def test_special_characters_round_trip(value: str):
    calendar = build([make_entry(1, title=value, text=value)])
    event = calendar.walk("VEVENT")[0]
    assert str(event["summary"]) == f"Dinner: {value}"
    assert str(event["description"]) == value


def test_recipe_link_in_url_and_description():
    recipe = RecipeSummary(id=uuid4(), name="Soup, of the day", slug="soup-of-the-day")
    calendar = build([make_entry(1, text="note", recipe=recipe)])
    event = calendar.walk("VEVENT")[0]

    assert str(event["summary"]) == "Dinner: Soup, of the day"
    assert str(event["url"]).endswith("/g/my-group/r/soup-of-the-day")
    assert str(event["description"]) == f"{event['url']}\n\nnote"


def test_hash_token_is_sha256():
    assert hash_token("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
