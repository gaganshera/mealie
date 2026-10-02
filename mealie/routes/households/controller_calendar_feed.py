import re
from functools import cached_property

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from mealie.db.db_setup import generate_session
from mealie.lang.providers import Translator, get_locale_provider
from mealie.repos.all_repositories import get_repositories
from mealie.routes._base import BaseUserController, controller
from mealie.routes._base.routers import UserAPIRouter
from mealie.schema.meal_plan.calendar_feed import CalendarFeedCreated, CalendarFeedStatus
from mealie.schema.response import ErrorResponse
from mealie.services.household_services.calendar_feed_service import CalendarFeedService

# Deliberately outside /households/mealplans, whose /{item_id} route would otherwise match these paths
router = UserAPIRouter(prefix="/households/calendar-feed", tags=["Households: Calendar Feed"])
public_router = APIRouter(prefix="/households/calendar-feed", tags=["Households: Calendar Feed"])


@controller(router)
class CalendarFeedController(BaseUserController):
    @cached_property
    def service(self) -> CalendarFeedService:
        return CalendarFeedService(self.repos)

    def _get_status(self) -> CalendarFeedStatus:
        token = self.repos.calendar_feed_tokens.get_one(self.user.id, key="user_id")
        if token is None:
            return CalendarFeedStatus(enabled=False)

        return CalendarFeedStatus(enabled=True, created_at=token.created_at, last_accessed_at=token.last_accessed_at)

    @router.get("", response_model=CalendarFeedStatus)
    def get_calendar_feed_status(self):
        return self._get_status()

    @router.post("", response_model=CalendarFeedCreated, status_code=201)
    def create_calendar_feed(self):
        """Creates the calendar feed, replacing any existing one. The returned URLs are only shown once."""
        raw_token = self.service.create_or_rotate(self.user)
        url = f"{self.settings.BASE_URL}/api/households/calendar-feed/{raw_token}.ics"
        webcal_url = re.sub(r"^https?://", "webcal://", url)
        return CalendarFeedCreated(url=url, webcal_url=webcal_url)

    @router.delete("", response_model=CalendarFeedStatus)
    def revoke_calendar_feed(self):
        token = self.repos.calendar_feed_tokens.get_one(self.user.id, key="user_id")
        if token is not None:
            self.repos.calendar_feed_tokens.delete(token.id)

        return self._get_status()


@public_router.get("/{token}.ics", response_class=Response)
def get_calendar_feed(
    token: str,
    session: Session = Depends(generate_session),
    translator: Translator = Depends(get_locale_provider),
) -> Response:
    """Public meal plan iCal feed. The token in the URL is the only authentication."""

    service = CalendarFeedService(get_repositories(session, group_id=None, household_id=None))
    feed_token = service.resolve(token)
    if feed_token is None or feed_token.household_id is None:
        raise HTTPException(status_code=404, detail=ErrorResponse.respond("Calendar feed not found"))

    repos = get_repositories(session, group_id=feed_token.group_id, household_id=feed_token.household_id)
    group = repos.groups.get_one(feed_token.group_id)
    household = repos.households.get_one(feed_token.household_id)
    if group is None or household is None:
        raise HTTPException(status_code=404, detail=ErrorResponse.respond("Calendar feed not found"))

    start, end = service.feed_date_range()
    entries = repos.meals.get_meals_by_date_range(start, end)
    content = service.build_calendar(entries, group.slug, household.name, translator)

    return Response(
        content=content,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'inline; filename="mealie-mealplan.ics"',
            "Cache-Control": "private, max-age=900",
        },
    )
