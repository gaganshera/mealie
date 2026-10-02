from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlparse
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from icalendar import Calendar

from mealie.schema.meal_plan.new_meal import CreatePlanEntry, PlanEntryType
from mealie.schema.recipe.recipe import Recipe
from mealie.services.household_services.calendar_feed_service import FEED_DAYS_AHEAD, FEED_DAYS_BACK
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser


@pytest.fixture(autouse=True)
def clean_feeds_and_mealplans(unique_user: TestUser, h2_user: TestUser) -> Generator[None]:
    yield
    for user in (unique_user, h2_user):
        user.repos.meals.delete_many([entry.id for entry in user.repos.meals.get_all()])
        token = user.repos.calendar_feed_tokens.get_one(user.user_id, key="user_id")
        if token:
            user.repos.calendar_feed_tokens.delete(token.id)


def today() -> date:
    return datetime.now(UTC).date()


def create_entry(
    api_client: TestClient,
    user: TestUser,
    plan_date: date,
    title: str = "",
    text: str = "",
    recipe_id: UUID | None = None,
    entry_type: PlanEntryType = PlanEntryType.dinner,
) -> dict:
    entry = CreatePlanEntry(date=plan_date, entry_type=entry_type, title=title, text=text, recipe_id=recipe_id)
    response = api_client.post(
        api_routes.households_mealplans, json=entry.model_dump(mode="json", by_alias=True), headers=user.token
    )
    assert response.status_code == 201
    return response.json()


def create_feed(api_client: TestClient, user: TestUser) -> dict:
    response = api_client.post(api_routes.households_calendar_feed, headers=user.token)
    assert response.status_code == 201
    return response.json()


def fetch_feed(api_client: TestClient, url: str):
    # No auth headers: calendar apps can't send them
    return api_client.get(urlparse(url).path)


def fetch_calendar(api_client: TestClient, url: str) -> Calendar:
    response = fetch_feed(api_client, url)
    assert response.status_code == 200
    return Calendar.from_ical(response.content)


def events_by_uid(calendar: Calendar) -> dict[str, object]:
    return {str(event["uid"]): event for event in calendar.walk("VEVENT")}


def test_create_feed_and_fetch_without_login(api_client: TestClient, unique_user: TestUser):
    feed = create_feed(api_client, unique_user)
    assert feed["url"].startswith("http")
    assert feed["url"].endswith(".ics")
    assert feed["webcalUrl"].startswith("webcal://")
    assert urlparse(feed["webcalUrl"]).path == urlparse(feed["url"]).path

    response = fetch_feed(api_client, feed["url"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/calendar; charset=utf-8"
    assert response.headers["content-disposition"] == 'inline; filename="mealie-mealplan.ics"'
    assert response.headers["cache-control"] == "private, max-age=900"
    assert response.text.startswith("BEGIN:VCALENDAR")


def test_feed_events(api_client: TestClient, unique_user: TestUser):
    recipe = unique_user.repos.recipes.create(
        Recipe(user_id=unique_user.user_id, group_id=UUID(unique_user.group_id), name=random_string())
    )
    recipe_entry = create_entry(
        api_client, unique_user, today(), recipe_id=recipe.id, text="extra sauce", entry_type=PlanEntryType.dinner
    )
    note_title = random_string()
    note_entry = create_entry(
        api_client, unique_user, today() + timedelta(days=3), title=note_title, entry_type=PlanEntryType.lunch
    )

    feed = create_feed(api_client, unique_user)
    events = events_by_uid(fetch_calendar(api_client, feed["url"]))
    assert set(events) == {f"{recipe_entry['id']}@mealie", f"{note_entry['id']}@mealie"}

    recipe_event = events[f"{recipe_entry['id']}@mealie"]
    assert str(recipe_event["summary"]) == f"Dinner: {recipe.name}"
    assert recipe_event.decoded("dtstart") == today()
    assert not isinstance(recipe_event.decoded("dtstart"), datetime)  # all-day event
    assert recipe_event.decoded("dtend") == today() + timedelta(days=1)
    assert str(recipe_event["url"]).endswith(f"/r/{recipe.slug}")
    assert str(recipe_event["description"]) == f"{recipe_event['url']}\n\nextra sauce"

    # entries without a recipe use their title
    note_event = events[f"{note_entry['id']}@mealie"]
    assert str(note_event["summary"]) == f"Lunch: {note_title}"
    assert "url" not in note_event


def test_feed_uid_is_stable(api_client: TestClient, unique_user: TestUser):
    entry = create_entry(api_client, unique_user, today(), title=random_string())
    feed = create_feed(api_client, unique_user)

    first = events_by_uid(fetch_calendar(api_client, feed["url"]))
    second = events_by_uid(fetch_calendar(api_client, feed["url"]))
    assert set(first) == set(second) == {f"{entry['id']}@mealie"}


def test_feed_date_range(api_client: TestClient, unique_user: TestUser):
    inside = [
        create_entry(api_client, unique_user, today() - timedelta(days=FEED_DAYS_BACK - 1), title="first"),
        create_entry(api_client, unique_user, today() + timedelta(days=FEED_DAYS_AHEAD - 1), title="last"),
    ]
    create_entry(api_client, unique_user, today() - timedelta(days=FEED_DAYS_BACK + 1), title="too old")
    create_entry(api_client, unique_user, today() + timedelta(days=FEED_DAYS_AHEAD + 1), title="too far")

    feed = create_feed(api_client, unique_user)
    events = events_by_uid(fetch_calendar(api_client, feed["url"]))
    assert set(events) == {f"{entry['id']}@mealie" for entry in inside}


def test_feed_household_isolation(api_client: TestClient, unique_user: TestUser, h2_user: TestUser):
    own_entry = create_entry(api_client, unique_user, today(), title=random_string())
    other_entry = create_entry(api_client, h2_user, today(), title=random_string())

    own_events = events_by_uid(fetch_calendar(api_client, create_feed(api_client, unique_user)["url"]))
    assert set(own_events) == {f"{own_entry['id']}@mealie"}

    other_events = events_by_uid(fetch_calendar(api_client, create_feed(api_client, h2_user)["url"]))
    assert set(other_events) == {f"{other_entry['id']}@mealie"}


def test_revoke_feed(api_client: TestClient, unique_user: TestUser):
    feed = create_feed(api_client, unique_user)
    assert fetch_feed(api_client, feed["url"]).status_code == 200

    response = api_client.delete(api_routes.households_calendar_feed, headers=unique_user.token)
    assert response.status_code == 200
    assert response.json()["enabled"] is False

    assert fetch_feed(api_client, feed["url"]).status_code == 404


def test_regenerate_feed(api_client: TestClient, unique_user: TestUser):
    old_feed = create_feed(api_client, unique_user)
    new_feed = create_feed(api_client, unique_user)
    assert old_feed["url"] != new_feed["url"]

    assert fetch_feed(api_client, old_feed["url"]).status_code == 404
    assert fetch_feed(api_client, new_feed["url"]).status_code == 200


def test_unknown_token(api_client: TestClient):
    response = api_client.get(api_routes.households_calendar_feed_token_ics(random_string(43)))
    assert response.status_code == 404


def test_feed_status(api_client: TestClient, unique_user: TestUser):
    response = api_client.get(api_routes.households_calendar_feed, headers=unique_user.token)
    assert response.status_code == 200
    assert response.json() == {"enabled": False, "createdAt": None, "lastAccessedAt": None}

    feed = create_feed(api_client, unique_user)
    status = api_client.get(api_routes.households_calendar_feed, headers=unique_user.token).json()
    assert status["enabled"] is True
    assert status["createdAt"] is not None
    assert status["lastAccessedAt"] is None

    fetch_feed(api_client, feed["url"])
    status = api_client.get(api_routes.households_calendar_feed, headers=unique_user.token).json()
    assert status["lastAccessedAt"] is not None


def test_feed_management_requires_login(api_client: TestClient):
    assert api_client.get(api_routes.households_calendar_feed).status_code == 401
    assert api_client.post(api_routes.households_calendar_feed).status_code == 401
    assert api_client.delete(api_routes.households_calendar_feed).status_code == 401
