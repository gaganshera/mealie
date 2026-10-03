import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from icalendar import Calendar, Event
from pydantic import UUID4

from mealie.lang.providers import Translator
from mealie.repos.all_repositories import get_repositories
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.meal_plan.calendar_feed import CalendarFeedStatus, CalendarFeedTokenInDB, CalendarFeedTokenSave
from mealie.schema.meal_plan.new_meal import ReadPlanEntry
from mealie.services._base_service import BaseService
from mealie.services.urls.url_constructors import recipe_url

FEED_DAYS_BEHIND = 30
FEED_DAYS_AHEAD = 90
FEED_REFRESH_INTERVAL = timedelta(hours=1)


def hash_feed_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class CalendarFeedService(BaseService):
    def __init__(self, repos: AllRepositories):
        self.repos = repos
        super().__init__()

    def get_token(self, user_id: UUID4) -> CalendarFeedTokenInDB | None:
        return self.repos.calendar_feed_tokens.get_one(user_id, key="user_id")

    def get_status(self, user_id: UUID4) -> CalendarFeedStatus:
        token = self.get_token(user_id)
        if token is None:
            return CalendarFeedStatus(enabled=False)

        return CalendarFeedStatus(enabled=True, created_at=token.created_at, last_accessed_at=token.last_accessed_at)

    def create_or_rotate(self, user_id: UUID4) -> str:
        """Creates a new feed token for the user, replacing any existing one. Returns the plain-text token."""
        self.revoke(user_id)

        raw_token = secrets.token_urlsafe(32)
        self.repos.calendar_feed_tokens.create(
            CalendarFeedTokenSave(user_id=user_id, token_hash=hash_feed_token(raw_token))
        )
        return raw_token

    def revoke(self, user_id: UUID4) -> bool:
        token = self.get_token(user_id)
        if token is None:
            return False

        self.repos.calendar_feed_tokens.delete(token.id)
        return True

    def resolve(self, raw_token: str) -> CalendarFeedTokenInDB | None:
        """Looks up a token across all groups and records the access. Returns `None` if there's no match."""
        token = self.repos.calendar_feed_tokens.get_one(hash_feed_token(raw_token), key="token_hash")
        if token is None:
            return None

        return self.repos.calendar_feed_tokens.patch(token.id, {"last_accessed_at": datetime.now(UTC)})

    def build_feed(self, token: CalendarFeedTokenInDB, translator: Translator) -> bytes:
        user = self.repos.users.get_one(token.user_id)
        if user is None or user.household_id is None:
            raise ValueError("calendar feed user has no household")

        household_repos = get_repositories(self.repos.session, group_id=user.group_id, household_id=user.household_id)
        household = household_repos.households.get_one(user.household_id)

        today = datetime.now(UTC)
        entries = household_repos.meals.get_meals_by_date_range(
            today - timedelta(days=FEED_DAYS_BEHIND), today + timedelta(days=FEED_DAYS_AHEAD)
        )
        return self.build_calendar(
            entries, user.group_slug, translator, household_name=household.name if household else ""
        )

    @staticmethod
    def build_calendar(
        entries: list[ReadPlanEntry], group_slug: str, translator: Translator, household_name: str = ""
    ) -> bytes:
        cal = Calendar()
        cal.add("prodid", "-//Mealie//Meal Plan//EN")
        cal.add("version", "2.0")
        cal.add("x-wr-calname", f"Mealie – {household_name}" if household_name else "Mealie")
        cal.add("refresh-interval", FEED_REFRESH_INTERVAL, parameters={"VALUE": "DURATION"})
        cal.add("x-published-ttl", "PT1H")

        now = datetime.now(UTC)
        for entry in entries:
            entry_type = translator.t(f"mealplan.entry-type.{entry.entry_type.value}", default=entry.entry_type.value)
            entry_type = entry_type[:1].upper() + entry_type[1:]
            name = entry.recipe.name if entry.recipe and entry.recipe.name else entry.title

            event = Event()
            event.add("uid", f"{entry.id}@mealie")
            event.add("dtstamp", now)
            event.add("dtstart", entry.date)
            event.add("dtend", entry.date + timedelta(days=1))
            event.add("summary", f"{entry_type}: {name}")

            description_parts: list[str] = []
            if entry.recipe and entry.recipe.slug:
                link = recipe_url(group_slug, entry.recipe.slug, None)
                event.add("url", link)
                description_parts.append(link)
            if entry.text:
                description_parts.append(entry.text)
            if description_parts:
                event.add("description", "\n\n".join(description_parts))

            cal.add_component(event)

        return cal.to_ical()
