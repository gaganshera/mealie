from datetime import date, datetime, timedelta
from urllib.parse import urlparse
from uuid import UUID

from dateutil.tz import tzlocal
from fastapi.testclient import TestClient
from icalendar import Calendar

from mealie.schema.meal_plan.new_meal import CreatePlanEntry
from mealie.schema.recipe.recipe import Recipe
from mealie.services.household_services.calendar_feed_service import FEED_DAYS_AHEAD, FEED_DAYS_BACK
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser


def today() -> date:
    # the feed's date range is local, like the meal planner's
    return datetime.now(tzlocal()).date()


def create_entry(api_client: TestClient, user: TestUser, **kwargs) -> dict:
    data = CreatePlanEntry(**{"date": today(), "entry_type": "dinner", **kwargs}).model_dump(mode="json")
    response = api_client.post(api_routes.households_mealplans, json=data, headers=user.token)
    assert response.status_code == 201
    return response.json()


def create_feed(api_client: TestClient, user: TestUser) -> dict:
    response = api_client.post(api_routes.households_calendar_feed, headers=user.token)
    assert response.status_code == 201
    return response.json()


def fetch_feed(api_client: TestClient, url: str):
    # no auth headers: calendar apps can't send any
    return api_client.get(urlparse(url).path)


def events_by_uid(api_client: TestClient, url: str) -> dict:
    response = fetch_feed(api_client, url)
    assert response.status_code == 200
    cal = Calendar.from_ical(response.content)
    return {str(event["uid"]): event for event in cal.walk("VEVENT")}


def test_create_feed_and_fetch_without_login(api_client: TestClient, unique_user: TestUser):
    feed = create_feed(api_client, unique_user)
    assert feed["url"].endswith(".ics")
    assert feed["webcalUrl"].startswith("webcal://")
    assert feed["webcalUrl"].split("://", 1)[1] == feed["url"].split("://", 1)[1]

    response = fetch_feed(api_client, feed["url"])
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert response.content.startswith(b"BEGIN:VCALENDAR")


def test_feed_events(api_client: TestClient, unique_user: TestUser):
    recipe = unique_user.repos.recipes.create(
        Recipe(user_id=unique_user.user_id, group_id=UUID(unique_user.group_id), name=random_string())
    )
    recipe_entry = create_entry(api_client, unique_user, recipe_id=str(recipe.id), text="extra cheese")
    note_entry = create_entry(api_client, unique_user, title="Leftovers", entry_type="lunch")
    in_range = create_entry(api_client, unique_user, title="soon", date=today() + timedelta(days=FEED_DAYS_AHEAD))
    too_old = create_entry(api_client, unique_user, title="old", date=today() - timedelta(days=FEED_DAYS_BACK + 1))
    too_far = create_entry(api_client, unique_user, title="far", date=today() + timedelta(days=FEED_DAYS_AHEAD + 1))

    feed = create_feed(api_client, unique_user)
    events = events_by_uid(api_client, feed["url"])

    event = events[f"{recipe_entry['id']}@mealie"]
    assert str(event["summary"]) == f"Dinner: {recipe.name}"
    assert event.decoded("dtstart") == today()
    assert event.decoded("dtend") == today() + timedelta(days=1)
    assert recipe.slug in str(event["url"])
    assert str(event["url"]) in str(event["description"])
    assert "extra cheese" in str(event["description"])

    note_event = events[f"{note_entry['id']}@mealie"]
    assert str(note_event["summary"]) == "Lunch: Leftovers"
    assert "url" not in note_event

    assert f"{in_range['id']}@mealie" in events
    assert f"{too_old['id']}@mealie" not in events
    assert f"{too_far['id']}@mealie" not in events

    # UIDs are stable, so calendar apps update events instead of duplicating them
    assert events_by_uid(api_client, feed["url"]).keys() == events.keys()


def test_feed_household_isolation(api_client: TestClient, unique_user: TestUser, h2_user: TestUser):
    own_entry = create_entry(api_client, unique_user, title="ours")
    other_entry = create_entry(api_client, h2_user, title="theirs")

    events = events_by_uid(api_client, create_feed(api_client, unique_user)["url"])
    assert f"{own_entry['id']}@mealie" in events
    assert f"{other_entry['id']}@mealie" not in events


def test_feed_revoke_and_regenerate(api_client: TestClient, unique_user: TestUser):
    old = create_feed(api_client, unique_user)
    new = create_feed(api_client, unique_user)
    assert fetch_feed(api_client, old["url"]).status_code == 404
    assert fetch_feed(api_client, new["url"]).status_code == 200

    response = api_client.delete(api_routes.households_calendar_feed, headers=unique_user.token)
    assert response.status_code == 204
    assert fetch_feed(api_client, new["url"]).status_code == 404

    assert api_client.get(api_routes.households_calendar_feed_token_ics(random_string())).status_code == 404


def test_feed_status(api_client: TestClient, unique_user: TestUser):
    api_client.delete(api_routes.households_calendar_feed, headers=unique_user.token)
    status = api_client.get(api_routes.households_calendar_feed, headers=unique_user.token).json()
    assert status == {"enabled": False, "createdAt": None, "lastAccessedAt": None}

    feed = create_feed(api_client, unique_user)
    status = api_client.get(api_routes.households_calendar_feed, headers=unique_user.token).json()
    assert status["enabled"] is True
    assert status["createdAt"] is not None
    assert status["lastAccessedAt"] is None

    fetch_feed(api_client, feed["url"])
    status = api_client.get(api_routes.households_calendar_feed, headers=unique_user.token).json()
    assert status["lastAccessedAt"] is not None
