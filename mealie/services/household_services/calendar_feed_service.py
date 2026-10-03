import hashlib
import secrets
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from icalendar import Calendar, Event, vDuration
from pydantic import UUID4

from mealie.lang.providers import Translator
from mealie.repos.all_repositories import get_repositories
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.meal_plan.calendar_feed import CalendarFeedCreated, CalendarFeedTokenInDB, CalendarFeedTokenSave
from mealie.schema.meal_plan.new_meal import ReadPlanEntry
from mealie.schema.user.user import PrivateUser
from mealie.services._base_service import BaseService
from mealie.services.urls.url_constructors import recipe_url

FEED_DAYS_BACK = 30
FEED_DAYS_AHEAD = 90
FEED_REFRESH_INTERVAL = timedelta(hours=1)


class CalendarFeedService(BaseService):
    def __init__(self, repos: AllRepositories):
        self.repos = repos
        super().__init__()

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

    def get_token(self, user_id: UUID4) -> CalendarFeedTokenInDB | None:
        return self.repos.calendar_feed_tokens.get_one(user_id, key="user_id")

    def create_or_rotate(self, user: PrivateUser) -> str:
        """Creates a new feed token for the user, replacing any existing one. Returns the plain-text token."""
        self.revoke(user.id)

        raw_token = secrets.token_urlsafe(32)
        self.repos.calendar_feed_tokens.create(
            CalendarFeedTokenSave(user_id=user.id, token_hash=self.hash_token(raw_token))
        )
        return raw_token

    def revoke(self, user_id: UUID4) -> bool:
        existing = self.get_token(user_id)
        if existing is None:
            return False

        self.repos.calendar_feed_tokens.delete(existing.id)
        return True

    def resolve(self, raw_token: str) -> CalendarFeedTokenInDB | None:
        """Looks up a feed token and records the access. Returns `None` if the token is unknown."""
        token = self.repos.calendar_feed_tokens.get_one(self.hash_token(raw_token), key="token_hash")
        if token is None:
            return None

        return self.repos.calendar_feed_tokens.update(
            token.id,
            {"user_id": token.user_id, "token_hash": token.token_hash, "last_accessed_at": datetime.now(UTC)},
        )

    def feed_urls(self, raw_token: str) -> CalendarFeedCreated:
        url = f"{self.settings.BASE_URL}/api/households/calendar-feed/{raw_token}.ics"
        return CalendarFeedCreated(url=url, webcal_url="webcal://" + url.split("://", 1)[-1])

    def get_feed(self, token: CalendarFeedTokenInDB, translator: Translator) -> bytes:
        repos = get_repositories(self.repos.session, group_id=token.group_id, household_id=token.household_id)

        now = datetime.now(UTC)
        entries = repos.meals.get_meals_by_date_range(
            now - timedelta(days=FEED_DAYS_BACK), now + timedelta(days=FEED_DAYS_AHEAD)
        )

        group = repos.groups.get_one(token.group_id)
        household = repos.households.get_one(token.household_id) if token.household_id else None

        return self.build_calendar(
            entries,
            group.slug if group else "",
            translator,
            household_name=household.name if household else "",
        )

    def build_calendar(
        self,
        entries: Iterable[ReadPlanEntry],
        group_slug: str,
        translator: Translator,
        household_name: str = "",
    ) -> bytes:
        calendar = Calendar()
        calendar.add("prodid", "-//Mealie//Meal Plan//EN")
        calendar.add("version", "2.0")
        calendar.add("x-wr-calname", f"Mealie – {household_name}" if household_name else "Mealie")
        calendar.add("refresh-interval", FEED_REFRESH_INTERVAL, parameters={"VALUE": "DURATION"})
        calendar.add("x-published-ttl", vDuration(FEED_REFRESH_INTERVAL))

        dtstamp = datetime.now(UTC)
        for entry in sorted(entries, key=lambda e: (e.date, e.id)):
            entry_type = translator.t(f"mealplan.entry-type.{entry.entry_type.value}", default=entry.entry_type.value)
            name = entry.recipe.name if entry.recipe and entry.recipe.name else entry.title

            event = Event()
            event.add("uid", f"{entry.id}@mealie")
            event.add("dtstamp", dtstamp)
            event.add("dtstart", entry.date)
            event.add("dtend", entry.date + timedelta(days=1))
            event.add("summary", f"{entry_type[:1].upper()}{entry_type[1:]}: {name}")

            description_parts: list[str] = []
            if entry.recipe and entry.recipe.slug:
                link = recipe_url(group_slug, entry.recipe.slug, self.settings.BASE_URL)
                event.add("url", link)
                description_parts.append(link)
            if entry.text:
                description_parts.append(entry.text)
            if description_parts:
                event.add("description", "\n\n".join(description_parts))

            calendar.add_component(event)

        return calendar.to_ical()
