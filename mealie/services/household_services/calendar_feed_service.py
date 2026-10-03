import hashlib
import secrets
from datetime import UTC, datetime, timedelta

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


class CalendarFeedService(BaseService):
    """Manages per-user meal plan feed tokens and renders the household meal plan as an iCal file.

    `repos` must not be scoped to a group, since anonymous feed requests look tokens up across all groups.
    """

    def __init__(self, repos: AllRepositories):
        self.repos = repos
        super().__init__()

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

    def get_for_user(self, user: PrivateUser) -> CalendarFeedTokenInDB | None:
        return self.repos.calendar_feed_tokens.get_one(user.id, key="user_id")

    def create_or_rotate(self, user: PrivateUser) -> str:
        """Creates a new feed token for the user, replacing any existing one, and returns it in plain text"""
        self.revoke(user)

        raw_token = secrets.token_urlsafe(32)
        self.repos.calendar_feed_tokens.create(
            CalendarFeedTokenSave(user_id=user.id, token_hash=self.hash_token(raw_token))
        )
        return raw_token

    def revoke(self, user: PrivateUser) -> bool:
        existing = self.get_for_user(user)
        if not existing:
            return False

        self.repos.calendar_feed_tokens.delete(existing.id)
        return True

    def resolve(self, raw_token: str) -> CalendarFeedTokenInDB | None:
        token = self.repos.calendar_feed_tokens.get_one(self.hash_token(raw_token), key="token_hash")
        if not token:
            return None

        return self.repos.calendar_feed_tokens.patch(
            token.id, {"last_accessed_at": datetime.now(UTC).replace(tzinfo=None)}
        )

    def build_feed(self, token: CalendarFeedTokenInDB, translator: Translator) -> bytes | None:
        """Renders the meal plan of the token user's current household, or `None` if the user has no household"""
        user = self.repos.users.get_one(token.user_id)
        if not user or not user.household_id:
            return None

        today = datetime.now(UTC)
        household_repos = get_repositories(self.repos.session, group_id=user.group_id, household_id=user.household_id)
        entries = household_repos.meals.get_meals_by_date_range(
            today - timedelta(days=FEED_DAYS_BACK), today + timedelta(days=FEED_DAYS_AHEAD)
        )
        entries.sort(key=lambda entry: (entry.date, entry.id))

        return self.build_calendar(entries, user.group_slug, user.household, translator)

    def build_calendar(
        self, entries: list[ReadPlanEntry], group_slug: str, household_name: str, translator: Translator
    ) -> bytes:
        cal = Calendar()
        cal.add("prodid", "-//Mealie//Meal Plan//EN")
        cal.add("version", "2.0")
        cal.add("x-wr-calname", f"Mealie – {household_name}")
        cal.add("refresh-interval", timedelta(hours=1), parameters={"VALUE": "DURATION"})
        cal.add("x-published-ttl", vDuration(timedelta(hours=1)))

        now = datetime.now(UTC)
        for entry in entries:
            entry_type = translator.t(f"mealplan.entry-type.{entry.entry_type.value}", default=entry.entry_type.value)
            entry_type = entry_type[:1].upper() + entry_type[1:]
            name = entry.recipe.name if entry.recipe else entry.title

            event = Event()
            event.add("uid", f"{entry.id}@mealie")
            event.add("dtstamp", now)
            event.add("dtstart", entry.date)
            event.add("dtend", entry.date + timedelta(days=1))
            event.add("summary", f"{entry_type}: {name}")

            description: list[str] = []
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
