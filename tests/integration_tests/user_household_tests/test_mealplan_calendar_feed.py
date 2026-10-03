from collections.abc import Generator
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

import pytest
from dateutil.tz import tzlocal
from fastapi.testclient import TestClient
from icalendar import Calendar

from mealie.services.household_services.calendar_feed_service import FEED_DAYS_AHEAD, FEED_DAYS_BACK
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser


def today() -> date:
    return datetime.now(tzlocal()).date()


def create_entry(api_client: TestClient, user: TestUser, day: date, **kwargs) -> dict:
    payload = {"date": day.strftime("%Y-%m-%d"), "entryType": "dinner", **kwargs}
    response = api_client.post(api_routes.households_mealplans, json=payload, headers=user.token)
    assert response.status_code == 201
    return response.json()


def create_recipe(api_client: TestClient, user: TestUser, name: str) -> dict:
    response = api_client.post(api_routes.recipes, json={"name": name}, headers=user.token)
    assert response.status_code == 201
    response = api_client.get(api_routes.recipes_slug(response.json()), headers=user.token)
    assert response.status_code == 200
    return response.json()


def create_feed(api_client: TestClient, user: TestUser) -> dict:
    response = api_client.post(api_routes.households_calendar_feed, headers=user.token)
    assert response.status_code == 201
    return response.json()


def feed_path(feed: dict) -> str:
    return urlparse(feed["url"]).path


def fetch_calendar(api_client: TestClient, feed: dict) -> Calendar:
    response = api_client.get(feed_path(feed))
    assert response.status_code == 200
    return Calendar.from_ical(response.content)


def events_by_uid(cal: Calendar) -> dict:
    return {str(event["uid"]): event for event in cal.walk("VEVENT")}


@pytest.fixture
def cleanup(api_client: TestClient, unique_user: TestUser, h2_user: TestUser) -> Generator[None]:
    yield
    for user in (unique_user, h2_user):
        api_client.delete(api_routes.households_calendar_feed, headers=user.token)


def test_create_feed_and_fetch_without_login(api_client: TestClient, unique_user: TestUser, cleanup):
    entry = create_entry(api_client, unique_user, today(), title=random_string())

    feed = create_feed(api_client, unique_user)
    assert feed["url"].startswith("http")
    assert feed["url"].endswith(".ics")
    assert feed["webcalUrl"].startswith("webcal://")
    assert feed["webcalUrl"].split("://", 1)[1] == feed["url"].split("://", 1)[1]

    response = api_client.get(feed_path(feed))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert "charset=utf-8" in response.headers["content-type"]
    assert response.headers["content-disposition"] == 'inline; filename="mealie-mealplan.ics"'
    assert response.headers["cache-control"] == "private, max-age=900"
    assert response.content.startswith(b"BEGIN:VCALENDAR")

    cal = Calendar.from_ical(response.content)
    assert f"{entry['id']}@mealie" in events_by_uid(cal)


def test_feed_events_match_entries(api_client: TestClient, unique_user: TestUser, cleanup):
    recipe = create_recipe(api_client, unique_user, random_string())
    recipe_entry = create_entry(
        api_client, unique_user, today() + timedelta(days=2), recipeId=recipe["id"], text="Use the big pot"
    )
    note_title = random_string()
    note_entry = create_entry(api_client, unique_user, today() - timedelta(days=3), title=note_title, entryType="lunch")

    feed = create_feed(api_client, unique_user)
    events = events_by_uid(fetch_calendar(api_client, feed))

    # one event for every entry the household has in the range
    start = datetime.now(tzlocal()) - timedelta(days=FEED_DAYS_BACK)
    end = datetime.now(tzlocal()) + timedelta(days=FEED_DAYS_AHEAD)
    entries = unique_user.repos.meals.get_meals_by_date_range(start, end)
    assert set(events) == {f"{e.id}@mealie" for e in entries}

    event = events[f"{recipe_entry['id']}@mealie"]
    assert str(event["summary"]) == f"Dinner: {recipe['name']}"
    assert event.decoded("dtstart") == today() + timedelta(days=2)
    assert not isinstance(event.decoded("dtstart"), datetime)  # all-day
    assert event.decoded("dtend") == today() + timedelta(days=3)
    group_slug = api_client.get(api_routes.groups_self, headers=unique_user.token).json()["slug"]
    assert str(event["url"]).endswith(f"/g/{group_slug}/r/{recipe['slug']}")
    description = str(event["description"])
    assert str(event["url"]) in description
    assert "Use the big pot" in description

    # entries without a recipe use their title
    event = events[f"{note_entry['id']}@mealie"]
    assert str(event["summary"]) == f"Lunch: {note_title}"
    assert "url" not in event


def test_feed_date_range(api_client: TestClient, unique_user: TestUser, cleanup):
    inside = [
        create_entry(api_client, unique_user, today() - timedelta(days=FEED_DAYS_BACK), title=random_string()),
        create_entry(api_client, unique_user, today() + timedelta(days=FEED_DAYS_AHEAD), title=random_string()),
    ]
    outside = [
        create_entry(api_client, unique_user, today() - timedelta(days=FEED_DAYS_BACK + 1), title=random_string()),
        create_entry(api_client, unique_user, today() + timedelta(days=FEED_DAYS_AHEAD + 1), title=random_string()),
    ]

    events = events_by_uid(fetch_calendar(api_client, create_feed(api_client, unique_user)))
    for entry in inside:
        assert f"{entry['id']}@mealie" in events
    for entry in outside:
        assert f"{entry['id']}@mealie" not in events


def test_feed_uid_is_stable(api_client: TestClient, unique_user: TestUser, cleanup):
    entry = create_entry(api_client, unique_user, today(), title=random_string())
    feed = create_feed(api_client, unique_user)

    first = events_by_uid(fetch_calendar(api_client, feed))
    second = events_by_uid(fetch_calendar(api_client, feed))
    assert f"{entry['id']}@mealie" in first
    assert set(first) == set(second)


def test_feed_household_isolation(api_client: TestClient, unique_user: TestUser, h2_user: TestUser, cleanup):
    own_entry = create_entry(api_client, unique_user, today(), title=random_string())
    other_entry = create_entry(api_client, h2_user, today(), title=random_string())

    events = events_by_uid(fetch_calendar(api_client, create_feed(api_client, unique_user)))
    assert f"{own_entry['id']}@mealie" in events
    assert f"{other_entry['id']}@mealie" not in events

    events = events_by_uid(fetch_calendar(api_client, create_feed(api_client, h2_user)))
    assert f"{other_entry['id']}@mealie" in events
    assert f"{own_entry['id']}@mealie" not in events


def test_revoke_feed(api_client: TestClient, unique_user: TestUser, cleanup):
    feed = create_feed(api_client, unique_user)
    assert api_client.get(feed_path(feed)).status_code == 200

    response = api_client.delete(api_routes.households_calendar_feed, headers=unique_user.token)
    assert response.status_code == 204
    assert api_client.get(feed_path(feed)).status_code == 404

    response = api_client.delete(api_routes.households_calendar_feed, headers=unique_user.token)
    assert response.status_code == 404


def test_regenerate_feed(api_client: TestClient, unique_user: TestUser, cleanup):
    old_feed = create_feed(api_client, unique_user)
    new_feed = create_feed(api_client, unique_user)
    assert old_feed["url"] != new_feed["url"]

    assert api_client.get(feed_path(old_feed)).status_code == 404
    assert api_client.get(feed_path(new_feed)).status_code == 200


def test_unknown_token(api_client: TestClient):
    response = api_client.get(api_routes.households_calendar_feed_token_ics(random_string(43)))
    assert response.status_code == 404


def test_feed_status(api_client: TestClient, unique_user: TestUser, cleanup):
    response = api_client.get(api_routes.households_calendar_feed, headers=unique_user.token)
    assert response.status_code == 200
    assert response.json()["enabled"] is False

    feed = create_feed(api_client, unique_user)
    status = api_client.get(api_routes.households_calendar_feed, headers=unique_user.token).json()
    assert status["enabled"] is True
    assert status["createdAt"]
    assert status["lastAccessedAt"] is None

    fetch_calendar(api_client, feed)
    status = api_client.get(api_routes.households_calendar_feed, headers=unique_user.token).json()
    assert status["lastAccessedAt"]


def test_feed_routes_require_login(api_client: TestClient):
    assert api_client.get(api_routes.households_calendar_feed).status_code == 401
    assert api_client.post(api_routes.households_calendar_feed).status_code == 401
    assert api_client.delete(api_routes.households_calendar_feed).status_code == 401
