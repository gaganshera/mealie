from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlparse
from uuid import UUID

from fastapi.testclient import TestClient
from icalendar import Calendar

from mealie.schema.meal_plan.new_meal import CreatePlanEntry, PlanEntryType
from mealie.schema.recipe.recipe import Recipe
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser


def create_recipe(user: TestUser) -> Recipe:
    return user.repos.recipes.create(Recipe(user_id=user.user_id, group_id=UUID(user.group_id), name=random_string()))


def create_entry(
    api_client: TestClient,
    user: TestUser,
    entry_date: date,
    *,
    recipe: Recipe | None = None,
    title: str = "",
    text: str = "",
    entry_type: PlanEntryType = PlanEntryType.dinner,
) -> dict:
    new_plan = CreatePlanEntry(
        date=entry_date, entry_type=entry_type, recipe_id=recipe.id if recipe else None, title=title, text=text
    ).model_dump(mode="json")

    response = api_client.post(api_routes.households_mealplans, json=new_plan, headers=user.token)
    assert response.status_code == 201
    return response.json()


def create_feed(api_client: TestClient, user: TestUser) -> str:
    """Creates a feed and returns its path, to be fetched without auth"""
    response = api_client.post(api_routes.households_calendar_feed, headers=user.token)
    assert response.status_code == 201

    data = response.json()
    assert urlparse(data["url"]).scheme in ("http", "https")
    assert data["webcalUrl"].startswith("webcal://")
    assert data["webcalUrl"].removeprefix("webcal://") == data["url"].split("://", 1)[1]

    path = urlparse(data["url"]).path
    assert path.endswith(".ics")
    return path


def fetch_events(api_client: TestClient, feed_path: str) -> dict[str, dict]:
    response = api_client.get(feed_path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")

    cal = Calendar.from_ical(response.content)
    return {str(event["UID"]): event for event in cal.walk("VEVENT")}


def today() -> date:
    return datetime.now(UTC).date()


def test_calendar_feed_events(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    recipe = create_recipe(user)
    recipe_entry = create_entry(api_client, user, today(), recipe=recipe, text="extra cheese")
    note_entry = create_entry(
        api_client, user, today() + timedelta(days=3), title="Leftovers", entry_type=PlanEntryType.lunch
    )

    events = fetch_events(api_client, create_feed(api_client, user))
    assert set(events) == {f"{recipe_entry['id']}@mealie", f"{note_entry['id']}@mealie"}

    recipe_event = events[f"{recipe_entry['id']}@mealie"]
    assert str(recipe_event["SUMMARY"]) == f"Dinner: {recipe.name}"
    start = recipe_event.decoded("DTSTART")
    end = recipe_event.decoded("DTEND")
    assert type(start) is date
    assert start == today()
    assert end == today() + timedelta(days=1)
    assert recipe.slug in str(recipe_event["URL"])
    description = str(recipe_event["DESCRIPTION"])
    assert str(recipe_event["URL"]) in description
    assert "extra cheese" in description

    note_event = events[f"{note_entry['id']}@mealie"]
    assert str(note_event["SUMMARY"]) == "Lunch: Leftovers"
    assert note_event.decoded("DTSTART") == today() + timedelta(days=3)
    assert "URL" not in note_event


def test_calendar_feed_uid_is_stable(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    create_entry(api_client, user, today(), title=random_string())
    feed_path = create_feed(api_client, user)

    first = fetch_events(api_client, feed_path)
    second = fetch_events(api_client, feed_path)
    assert len(first) == 1
    assert set(first) == set(second)


def test_calendar_feed_date_range(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    included = [
        create_entry(api_client, user, today() - timedelta(days=29), title="recent"),
        create_entry(api_client, user, today() + timedelta(days=89), title="upcoming"),
    ]
    create_entry(api_client, user, today() - timedelta(days=31), title="too old")
    create_entry(api_client, user, today() + timedelta(days=91), title="too far ahead")

    events = fetch_events(api_client, create_feed(api_client, user))
    assert set(events) == {f"{entry['id']}@mealie" for entry in included}


def test_calendar_feed_household_isolation(api_client: TestClient, unique_user: TestUser, h2_user: TestUser):
    own_entry = create_entry(api_client, unique_user, today(), title=random_string())
    other_entry = create_entry(api_client, h2_user, today(), title=random_string())

    events = fetch_events(api_client, create_feed(api_client, unique_user))
    assert f"{own_entry['id']}@mealie" in events
    assert f"{other_entry['id']}@mealie" not in events

    h2_events = fetch_events(api_client, create_feed(api_client, h2_user))
    assert f"{other_entry['id']}@mealie" in h2_events
    assert f"{own_entry['id']}@mealie" not in h2_events


def test_calendar_feed_revoke_and_regenerate(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    old_path = create_feed(api_client, user)
    assert api_client.get(old_path).status_code == 200

    new_path = create_feed(api_client, user)
    assert new_path != old_path
    assert api_client.get(old_path).status_code == 404
    assert api_client.get(new_path).status_code == 200

    response = api_client.delete(api_routes.households_calendar_feed, headers=user.token)
    assert response.status_code == 200
    assert api_client.get(new_path).status_code == 404

    response = api_client.delete(api_routes.households_calendar_feed, headers=user.token)
    assert response.status_code == 404


def test_calendar_feed_unknown_token(api_client: TestClient):
    response = api_client.get(api_routes.households_calendar_feed_token_ics(random_string(43)))
    assert response.status_code == 404


def test_calendar_feed_status(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    response = api_client.get(api_routes.households_calendar_feed, headers=user.token)
    assert response.status_code == 200
    assert response.json()["enabled"] is False

    feed_path = create_feed(api_client, user)
    status = api_client.get(api_routes.households_calendar_feed, headers=user.token).json()
    assert status["enabled"] is True
    assert status["createdAt"]
    assert status["lastAccessedAt"] is None

    fetch_events(api_client, feed_path)
    status = api_client.get(api_routes.households_calendar_feed, headers=user.token).json()
    assert status["enabled"] is True
    assert status["lastAccessedAt"]


def test_calendar_feed_requires_login(api_client: TestClient):
    assert api_client.get(api_routes.households_calendar_feed).status_code == 401
    assert api_client.post(api_routes.households_calendar_feed).status_code == 401
    assert api_client.delete(api_routes.households_calendar_feed).status_code == 401
