from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlparse

from fastapi.testclient import TestClient
from icalendar import Calendar

from mealie.services.household_services.calendar_feed_service import FEED_DAYS_AHEAD, FEED_DAYS_BEHIND
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser


def create_entry(
    api_client: TestClient,
    user: TestUser,
    *,
    entry_date: date | None = None,
    entry_type: str = "dinner",
    title: str = "",
    text: str = "",
    recipe_id: str | None = None,
) -> dict:
    data = {
        "date": (entry_date or datetime.now(UTC).date()).strftime("%Y-%m-%d"),
        "entryType": entry_type,
        "title": title,
        "text": text,
        "recipeId": recipe_id,
    }
    response = api_client.post(api_routes.households_mealplans, json=data, headers=user.token)
    assert response.status_code == 201
    return response.json()


def create_feed(api_client: TestClient, user: TestUser) -> str:
    """Creates the user's feed and returns the path of its `.ics` URL"""
    response = api_client.post(api_routes.households_calendar_feed, headers=user.token)
    assert response.status_code == 201
    data = response.json()

    url = urlparse(data["url"])
    assert url.scheme in ("http", "https")
    assert data["webcalUrl"] == f"webcal://{url.netloc}{url.path}"
    assert url.path.startswith("/api/households/calendar-feed/")
    assert url.path.endswith(".ics")
    return url.path


def fetch_calendar(api_client: TestClient, path: str) -> Calendar:
    response = api_client.get(path)  # no auth headers
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert response.headers["cache-control"] == "private, max-age=900"
    assert "mealie-mealplan.ics" in response.headers["content-disposition"]
    return Calendar.from_ical(response.content)


def events_by_uid(cal: Calendar) -> dict[str, dict]:
    return {str(event["uid"]): event for event in cal.walk("VEVENT")}


def test_calendar_feed_events(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    recipe_name = random_string()
    response = api_client.post(api_routes.recipes, json={"name": recipe_name}, headers=user.token)
    assert response.status_code == 201
    recipe = api_client.get(api_routes.recipes_slug(recipe_name), headers=user.token).json()

    today = datetime.now(UTC).date()
    note_title = random_string()
    recipe_entry = create_entry(api_client, user, entry_type="dinner", recipe_id=recipe["id"], text="Use leftovers")
    note_entry = create_entry(
        api_client, user, entry_date=today + timedelta(days=3), entry_type="lunch", title=note_title
    )

    path = create_feed(api_client, user)
    cal = fetch_calendar(api_client, path)
    events = events_by_uid(cal)
    assert set(events) == {f"{recipe_entry['id']}@mealie", f"{note_entry['id']}@mealie"}

    recipe_event = events[f"{recipe_entry['id']}@mealie"]
    assert str(recipe_event["summary"]) == f"Dinner: {recipe_name}"
    assert recipe_event.decoded("dtstart") == today
    assert not isinstance(recipe_event.decoded("dtstart"), datetime)  # all-day event
    assert recipe_event.decoded("dtend") == today + timedelta(days=1)
    group_slug = api_client.get(api_routes.groups_self, headers=user.token).json()["slug"]
    assert str(recipe_event["url"]).endswith(f"/g/{group_slug}/r/{recipe['slug']}")
    assert str(recipe_event["url"]) in str(recipe_event["description"])
    assert "Use leftovers" in str(recipe_event["description"])

    # note-only entries use their title
    note_event = events[f"{note_entry['id']}@mealie"]
    assert str(note_event["summary"]) == f"Lunch: {note_title}"
    assert note_event.decoded("dtstart") == today + timedelta(days=3)
    assert note_event.decoded("dtend") == today + timedelta(days=4)
    assert "url" not in note_event

    # UIDs are stable between fetches
    assert set(events_by_uid(fetch_calendar(api_client, path))) == set(events)


def test_calendar_feed_date_range(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    today = datetime.now(UTC).date()
    inside = [
        create_entry(api_client, user, entry_date=today - timedelta(days=FEED_DAYS_BEHIND - 1), title="old-inside"),
        create_entry(api_client, user, entry_date=today + timedelta(days=FEED_DAYS_AHEAD - 1), title="new-inside"),
    ]
    outside = [
        create_entry(api_client, user, entry_date=today - timedelta(days=FEED_DAYS_BEHIND + 2), title="too-old"),
        create_entry(api_client, user, entry_date=today + timedelta(days=FEED_DAYS_AHEAD + 2), title="too-new"),
    ]

    events = events_by_uid(fetch_calendar(api_client, create_feed(api_client, user)))
    for entry in inside:
        assert f"{entry['id']}@mealie" in events
    for entry in outside:
        assert f"{entry['id']}@mealie" not in events


def test_calendar_feed_household_isolation(api_client: TestClient, unique_user: TestUser, h2_user: TestUser):
    own_title = random_string()
    other_title = random_string()
    own_entry = create_entry(api_client, unique_user, title=own_title)
    other_entry = create_entry(api_client, h2_user, title=other_title)

    response = api_client.get(create_feed(api_client, unique_user))
    assert response.status_code == 200
    events = events_by_uid(Calendar.from_ical(response.content))
    assert f"{own_entry['id']}@mealie" in events
    assert f"{other_entry['id']}@mealie" not in events
    assert other_title not in response.text


def test_calendar_feed_revoke_and_regenerate(api_client: TestClient, unique_user: TestUser):
    old_path = create_feed(api_client, unique_user)
    assert api_client.get(old_path).status_code == 200

    # regenerating invalidates the old URL
    new_path = create_feed(api_client, unique_user)
    assert new_path != old_path
    assert api_client.get(old_path).status_code == 404
    assert api_client.get(new_path).status_code == 200

    # revoking invalidates the current URL
    response = api_client.delete(api_routes.households_calendar_feed, headers=unique_user.token)
    assert response.status_code == 200
    assert api_client.get(new_path).status_code == 404

    response = api_client.delete(api_routes.households_calendar_feed, headers=unique_user.token)
    assert response.status_code == 404


def test_calendar_feed_unknown_token(api_client: TestClient):
    response = api_client.get(api_routes.households_calendar_feed_token_ics(random_string(43)))
    assert response.status_code == 404


def test_calendar_feed_requires_login(api_client: TestClient):
    assert api_client.get(api_routes.households_calendar_feed).status_code == 401
    assert api_client.post(api_routes.households_calendar_feed).status_code == 401
    assert api_client.delete(api_routes.households_calendar_feed).status_code == 401


def test_calendar_feed_status(api_client: TestClient, unique_user_fn_scoped: TestUser):
    user = unique_user_fn_scoped
    response = api_client.get(api_routes.households_calendar_feed, headers=user.token)
    assert response.status_code == 200
    assert response.json() == {"enabled": False, "createdAt": None, "lastAccessedAt": None}

    path = create_feed(api_client, user)
    status = api_client.get(api_routes.households_calendar_feed, headers=user.token).json()
    assert status["enabled"] is True
    assert status["createdAt"]
    assert status["lastAccessedAt"] is None

    fetch_calendar(api_client, path)
    status = api_client.get(api_routes.households_calendar_feed, headers=user.token).json()
    assert status["enabled"] is True
    assert status["lastAccessedAt"]

    api_client.delete(api_routes.households_calendar_feed, headers=user.token)
    status = api_client.get(api_routes.households_calendar_feed, headers=user.token).json()
    assert status["enabled"] is False
