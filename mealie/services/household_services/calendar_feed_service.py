import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from dateutil.tz import tzlocal
from icalendar import Calendar, Event
from pydantic import UUID4
from sqlalchemy.orm import Session

from mealie.lang.providers import Translator
from mealie.repos.all_repositories import get_repositories
from mealie.schema.meal_plan.calendar_feed import CalendarFeedTokenInDB, CalendarFeedTokenSave
from mealie.schema.meal_plan.new_meal import ReadPlanEntry
from mealie.schema.user.user import PrivateUser
from mealie.services._base_service import BaseService
from mealie.services.urls.url_constructors import recipe_url

FEED_DAYS_BACK = 30
FEED_DAYS_AHEAD = 90


class CalendarFeedService(BaseService):
    def __init__(self, session: Session):
        self.session = session
        # tokens are looked up before the user (and so the group) is known
        self.repos = get_repositories(session, group_id=None, household_id=None)
        super().__init__()

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

    def get(self, user_id: UUID4) -> CalendarFeedTokenInDB | None:
        return self.repos.calendar_feed_tokens.get_one(user_id, "user_id")

    def revoke(self, user_id: UUID4) -> None:
        if existing := self.get(user_id):
            self.repos.calendar_feed_tokens.delete(existing.id)

    def create_or_rotate(self, user: PrivateUser) -> str:
        """Replaces any existing token for the user and returns the new plain-text token"""
        self.revoke(user.id)
        raw_token = secrets.token_urlsafe(32)
        self.repos.calendar_feed_tokens.create(
            CalendarFeedTokenSave(user_id=user.id, token_hash=self.hash_token(raw_token))
        )
        return raw_token

    def resolve(self, raw_token: str) -> PrivateUser | None:
        """Returns the token's user, or None for an unknown token"""
        token = self.repos.calendar_feed_tokens.get_one(self.hash_token(raw_token), "token_hash")
        if not token:
            return None

        self.repos.calendar_feed_tokens.update(token.id, {"last_accessed_at": datetime.now(UTC)})
        return self.repos.users.get_one(token.user_id)

    def feed_for_user(self, user: PrivateUser, translator: Translator) -> bytes:
        repos = get_repositories(self.session, group_id=user.group_id, household_id=user.household_id)
        today = datetime.now(tzlocal())
        entries = repos.meals.get_meals_by_date_range(
            today - timedelta(days=FEED_DAYS_BACK), today + timedelta(days=FEED_DAYS_AHEAD)
        )
        return CalendarFeedService.build_calendar(entries, user.group_slug, user.household, translator)

    @staticmethod
    def build_calendar(
        entries: list[ReadPlanEntry], group_slug: str, household_name: str, translator: Translator
    ) -> bytes:
        cal = Calendar()
        cal.add("prodid", "-//Mealie//Meal Plan//EN")
        cal.add("version", "2.0")
        cal.add("x-wr-calname", f"Mealie – {household_name}")
        cal.add("refresh-interval", timedelta(hours=1), parameters={"VALUE": "DURATION"})
        cal.add("x-published-ttl", "PT1H")

        now = datetime.now(UTC)
        for entry in entries:
            entry_type = translator.t(f"mealplan.entry-type.{entry.entry_type.value}", default=entry.entry_type.value)
            name = entry.recipe.name if entry.recipe else entry.title

            event = Event()
            event.add("uid", f"{entry.id}@mealie")
            event.add("dtstamp", now)
            event.add("dtstart", entry.date)
            event.add("dtend", entry.date + timedelta(days=1))
            event.add("summary", f"{entry_type.capitalize()}: {name}")

            description = [entry.text] if entry.text else []
            if entry.recipe:
                link = recipe_url(group_slug, entry.recipe.slug, None)
                event.add("url", link)
                description.insert(0, link)
            if description:
                event.add("description", "\n\n".join(description))

            cal.add_component(event)

        return cal.to_ical()
