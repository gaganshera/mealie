import hashlib
import secrets
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from dateutil.tz import tzlocal
from icalendar import Calendar, Event, vDuration

from mealie.lang.providers import Translator
from mealie.repos.all_repositories import get_repositories
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.meal_plan.calendar_feed import CalendarFeedTokenInDB, CalendarFeedTokenSave
from mealie.schema.meal_plan.new_meal import ReadPlanEntry
from mealie.schema.user.user import PrivateUser
from mealie.services._base_service import BaseService
from mealie.services.urls.url_constructors import recipe_url

FEED_DAYS_BACK = 30
FEED_DAYS_AHEAD = 90
FEED_REFRESH_INTERVAL = timedelta(hours=1)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


class CalendarFeedService(BaseService):
    def __init__(self, repos: AllRepositories) -> None:
        self.repos = repos
        super().__init__()

    def create_or_rotate(self, user: PrivateUser) -> str:
        """Creates a new feed token for the user, replacing any existing one, and returns the raw token"""
        existing = self.repos.calendar_feed_tokens.get_one(user.id, key="user_id")
        if existing:
            self.repos.calendar_feed_tokens.delete(existing.id)

        raw_token = secrets.token_urlsafe(32)
        self.repos.calendar_feed_tokens.create(CalendarFeedTokenSave(user_id=user.id, token_hash=hash_token(raw_token)))
        return raw_token

    def resolve(self, raw_token: str) -> CalendarFeedTokenInDB | None:
        token = self.repos.calendar_feed_tokens.get_one(hash_token(raw_token), key="token_hash")
        if not token:
            return None

        return self.repos.calendar_feed_tokens.patch(token.id, {"last_accessed_at": datetime.now(UTC)})

    def build_feed(self, token: CalendarFeedTokenInDB, translator: Translator) -> bytes | None:
        """Builds the calendar for the token user's current household, or None if they don't have one"""
        if not token.household_id:
            return None

        repos = get_repositories(self.repos.session, group_id=token.group_id, household_id=token.household_id)
        group = repos.groups.get_one(token.group_id)
        household = repos.households.get_one(token.household_id)
        if not group or not household:
            return None

        today = datetime.now(tzlocal())
        entries = repos.meals.get_meals_by_date_range(
            today - timedelta(days=FEED_DAYS_BACK), today + timedelta(days=FEED_DAYS_AHEAD)
        )
        return self.build_calendar(entries, group.slug, household.name, translator)

    def build_calendar(
        self, entries: Iterable[ReadPlanEntry], group_slug: str, household_name: str, translator: Translator
    ) -> bytes:
        cal = Calendar()
        cal.add("prodid", "-//Mealie//Meal Plan//EN")
        cal.add("version", "2.0")
        cal.add("x-wr-calname", f"Mealie – {household_name}")
        cal.add("refresh-interval", FEED_REFRESH_INTERVAL, parameters={"VALUE": "DURATION"})
        cal.add("x-published-ttl", vDuration(FEED_REFRESH_INTERVAL))

        now = datetime.now(UTC)
        for entry in entries:
            entry_type = translator.t(f"mealplan.entry-type.{entry.entry_type.value}", default=entry.entry_type.value)
            title = entry.recipe.name if entry.recipe and entry.recipe.name else entry.title

            event = Event()
            event.add("uid", f"{entry.id}@mealie")
            event.add("dtstart", entry.date)
            event.add("dtend", entry.date + timedelta(days=1))
            event.add("dtstamp", now)
            event.add("summary", f"{entry_type[:1].upper()}{entry_type[1:]}: {title}")

            description = []
            if entry.recipe and entry.recipe.slug:
                link = recipe_url(group_slug, entry.recipe.slug, self.settings.BASE_URL)
                event.add("url", link)
                description.append(link)
            if entry.text:
                description.append(entry.text)
            if description:
                event.add("description", "\n\n".join(description))

            cal.add_component(event)

        return cal.to_ical()
