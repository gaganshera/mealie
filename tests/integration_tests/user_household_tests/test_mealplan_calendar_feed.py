from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlparse

from fastapi.testclient import TestClient
from icalendar import Calendar

from mealie.services.household_services.calendar_feed_service import FEED_DAYS_AHEAD, FEED_DAYS_BACK
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser


def create_feed(api_client: TestClient, user: TestUser) -> dict:
    response = api_client.post(api_routes.households_calendar_feed, headers=user.token)
    assert response.status_code == 201
    return response.json()


def fetch_feed(api_client: TestClient, url: str):
    # no auth headers: the token in the URL is the only credential
    return api_client.get(urlparse(url).path)


def create_entry(
    api_client: TestClient,
    user: TestUser,
    entry_date: date,
    *,
    title: str = "",
    text: str = "",
    recipe_id: str | None = None,
    entry_type: str = "dinner",
) -> dict:
    data = {"date": entry_date.isoformat(), "entryType": entry_type, "title": title, "text": text}
    if recipe_id:
        data["recipeId"] = recipe_id

    response = api_client.post(api_routes.households_mealplans, json=data, headers=user.token)
    assert response.status_code == 201
    return response.json()


def parse_events(content: bytes) -> dict[str, dict]:
    calendar = Calendar.from_ical(content)
    return {str(event["uid"]): event for event in calendar.walk("VEVENT")}


def today() -> date:
    return datetime.now(UTC).date()


def test_create_feed_and_fetch_without_login(api_client: TestClient, unique_user: TestUser):
    feed = create_feed(api_client, unique_user)
    assert feed["url"].startswith("http")
    assert feed["url"].endswith(".ics")
    assert feed["webcalUrl"].startswith("webcal://")
    assert feed["webcalUrl"].split("://", 1)[1] == feed["url"].split("://", 1)[1]

    response = fetch_feed(api_client, feed["url"])
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert "charset=utf-8" in response.headers["content-type"]
    assert response.headers["content-disposition"] == 'inline; filename="mealie-mealplan.ics"'
    assert response.headers["cache-control"] == "private, max-age=900"
    assert response.content.startswith(b"BEGIN:VCALENDAR")


def test_feed_events(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    recipe_name = random_string()
    response = api_client.post(api_routes.recipes, json={"name": recipe_name}, headers=user.token)
    assert response.status_code == 201
    recipe = api_client.get(api_routes.recipes_slug(response.json()), headers=user.token).json()

    with_recipe = create_entry(api_client, user, today(), recipe_id=recipe["id"], text="Make extra")
    note_title = random_string()
    note_only = create_entry(api_client, user, today() + timedelta(days=3), title=note_title, entry_type="lunch")
    in_past = create_entry(api_client, user, today() - timedelta(days=FEED_DAYS_BACK - 1), title=random_string())

    # outside the date range
    create_entry(api_client, user, today() - timedelta(days=FEED_DAYS_BACK + 2), title=random_string())
    create_entry(api_client, user, today() + timedelta(days=FEED_DAYS_AHEAD + 2), title=random_string())

    feed = create_feed(api_client, user)
    response = fetch_feed(api_client, feed["url"])
    assert response.status_code == 200
    events = parse_events(response.content)

    assert set(events) == {f"{e['id']}@mealie" for e in (with_recipe, note_only, in_past)}

    recipe_event = events[f"{with_recipe['id']}@mealie"]
    assert str(recipe_event["summary"]) == f"Dinner: {recipe_name}"
    assert recipe_event.decoded("dtstart") == today()
    assert not isinstance(recipe_event.decoded("dtstart"), datetime)
    assert recipe_event.decoded("dtend") == today() + timedelta(days=1)
    assert str(recipe_event["url"]).endswith(f"/r/{recipe['slug']}")
    assert str(recipe_event["description"]) == f"{recipe_event['url']}\n\nMake extra"

    note_event = events[f"{note_only['id']}@mealie"]
    assert str(note_event["summary"]) == f"Lunch: {note_title}"
    assert note_event.decoded("dtstart") == today() + timedelta(days=3)
    assert note_event.decoded("dtend") == today() + timedelta(days=4)
    assert "url" not in note_event


def test_feed_uid_is_stable(api_client: TestClient, unique_user: TestUser):
    entry = create_entry(api_client, unique_user, today(), title=random_string())
    feed = create_feed(api_client, unique_user)

    first = parse_events(fetch_feed(api_client, feed["url"]).content)
    second = parse_events(fetch_feed(api_client, feed["url"]).content)

    uid = f"{entry['id']}@mealie"
    assert uid in first
    assert uid in second
    assert set(first) == set(second)


def test_feed_household_isolation(api_client: TestClient, unique_user: TestUser, h2_user: TestUser):
    own_entry = create_entry(api_client, unique_user, today(), title=random_string())
    other_entry = create_entry(api_client, h2_user, today(), title=random_string())

    feed = create_feed(api_client, unique_user)
    events = parse_events(fetch_feed(api_client, feed["url"]).content)
    assert f"{own_entry['id']}@mealie" in events
    assert f"{other_entry['id']}@mealie" not in events

    h2_feed = create_feed(api_client, h2_user)
    h2_events = parse_events(fetch_feed(api_client, h2_feed["url"]).content)
    assert f"{other_entry['id']}@mealie" in h2_events
    assert f"{own_entry['id']}@mealie" not in h2_events


def test_feed_revoke_and_regenerate(api_client: TestClient, unique_user: TestUser):
    old_feed = create_feed(api_client, unique_user)
    assert fetch_feed(api_client, old_feed["url"]).status_code == 200

    new_feed = create_feed(api_client, unique_user)
    assert new_feed["url"] != old_feed["url"]
    assert fetch_feed(api_client, old_feed["url"]).status_code == 404
    assert fetch_feed(api_client, new_feed["url"]).status_code == 200

    response = api_client.delete(api_routes.households_calendar_feed, headers=unique_user.token)
    assert response.status_code == 200
    assert fetch_feed(api_client, new_feed["url"]).status_code == 404

    response = api_client.delete(api_routes.households_calendar_feed, headers=unique_user.token)
    assert response.status_code == 404


def test_feed_unknown_token(api_client: TestClient):
    response = api_client.get(api_routes.households_calendar_feed_token_ics(random_string(43)))
    assert response.status_code == 404


def test_feed_routes_require_login(api_client: TestClient):
    assert api_client.get(api_routes.households_calendar_feed).status_code == 401
    assert api_client.post(api_routes.households_calendar_feed).status_code == 401
    assert api_client.delete(api_routes.households_calendar_feed).status_code == 401


def test_feed_status(api_client: TestClient, unique_user: TestUser):
    api_client.delete(api_routes.households_calendar_feed, headers=unique_user.token)
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
    assert status["enabled"] is True
    assert status["lastAccessedAt"] is not None
