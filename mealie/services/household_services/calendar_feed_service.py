import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from icalendar import Calendar, Event

from mealie.lang.providers import Translator
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.meal_plan.calendar_feed import CalendarFeedTokenInDB, CalendarFeedTokenSave
from mealie.schema.meal_plan.new_meal import ReadPlanEntry
from mealie.schema.user.user import PrivateUser
from mealie.services._base_service import BaseService
from mealie.services.urls.url_constructors import recipe_url

FEED_DAYS_BACK = 30
FEED_DAYS_AHEAD = 90
REFRESH_INTERVAL = timedelta(hours=1)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


class CalendarFeedService(BaseService):
    def __init__(self, repos: AllRepositories):
        super().__init__()
        self.repos = repos

    def create_or_rotate(self, user: PrivateUser) -> str:
        """Creates a new feed token for the user, replacing any existing one, and returns the plain-text token"""

        existing = self.repos.calendar_feed_tokens.get_one(user.id, key="user_id")
        if existing:
            self.repos.calendar_feed_tokens.delete(existing.id)

        raw_token = secrets.token_urlsafe(32)
        self.repos.calendar_feed_tokens.create(CalendarFeedTokenSave(user_id=user.id, token_hash=hash_token(raw_token)))
        return raw_token

    def resolve(self, raw_token: str) -> CalendarFeedTokenInDB | None:
        token = self.repos.calendar_feed_tokens.get_one(hash_token(raw_token), key="token_hash")
        if token is None:
            return None

        return self.repos.calendar_feed_tokens.patch(token.id, {"last_accessed_at": datetime.now(UTC)})

    @staticmethod
    def feed_date_range() -> tuple[datetime, datetime]:
        now = datetime.now(UTC)
        return now - timedelta(days=FEED_DAYS_BACK), now + timedelta(days=FEED_DAYS_AHEAD)

    def build_calendar(
        self, entries: list[ReadPlanEntry], group_slug: str, household_name: str, translator: Translator
    ) -> bytes:
        calendar = Calendar()
        calendar.add("prodid", "-//Mealie//Meal Plan//EN")
        calendar.add("version", "2.0")
        calendar.add("x-wr-calname", f"Mealie – {household_name}")
        calendar.add("refresh-interval", REFRESH_INTERVAL, parameters={"VALUE": "DURATION"})
        # icalendar renders a timedelta on an X- property as "1:00:00", so pass the ISO duration as text
        calendar.add("x-published-ttl", "PT1H")

        stamp = datetime.now(UTC)
        for entry in sorted(entries, key=lambda e: (e.date, e.id)):
            entry_type = translator.t(f"mealplan.entry-type.{entry.entry_type.value}", default=entry.entry_type.value)
            entry_type = entry_type[:1].upper() + entry_type[1:]
            name = (entry.recipe.name if entry.recipe else None) or entry.title

            event = Event()
            event.add("uid", f"{entry.id}@mealie")
            event.add("dtstart", entry.date)
            event.add("dtend", entry.date + timedelta(days=1))
            event.add("dtstamp", stamp)
            event.add("summary", f"{entry_type}: {name}")

            description = []
            if entry.recipe:
                link = recipe_url(group_slug, entry.recipe.slug, self.settings.BASE_URL)
                event.add("url", link)
                description.append(link)
            if entry.text:
                description.append(entry.text)
            if description:
                event.add("description", "\n\n".join(description))

            calendar.add_component(event)

        return calendar.to_ical()
