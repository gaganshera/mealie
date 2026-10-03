from functools import cached_property

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm.session import Session

from mealie.db.db_setup import generate_session
from mealie.lang.providers import get_locale_provider
from mealie.repos.all_repositories import get_repositories
from mealie.routes._base import BaseUserController, controller
from mealie.routes._base.routers import UserAPIRouter
from mealie.schema.meal_plan.calendar_feed import CalendarFeedCreated, CalendarFeedStatus
from mealie.schema.response import ErrorResponse
from mealie.services.household_services.calendar_feed_service import CalendarFeedService

# Deliberately outside of /households/mealplans, where /{item_id} would swallow these routes
router = UserAPIRouter(prefix="/households/calendar-feed", tags=["Households: Meal Plan Calendar Feed"])
public_router = APIRouter(prefix="/households/calendar-feed", tags=["Households: Meal Plan Calendar Feed"])


@controller(router)
class CalendarFeedController(BaseUserController):
    @cached_property
    def service(self) -> CalendarFeedService:
        return CalendarFeedService(self.repos)

    def _feed_url(self, raw_token: str) -> str:
        return f"{self.settings.BASE_URL}/api/households/calendar-feed/{raw_token}.ics"

    @router.get("", response_model=CalendarFeedStatus)
    def get_status(self):
        token = self.repos.calendar_feed_tokens.get_one(self.user.id, key="user_id")
        if not token:
            return CalendarFeedStatus(enabled=False)

        return CalendarFeedStatus(enabled=True, created_at=token.created_at, last_accessed_at=token.last_accessed_at)

    @router.post("", status_code=status.HTTP_201_CREATED, response_model=CalendarFeedCreated)
    def create_or_rotate(self):
        """Creates a calendar feed link, replacing any existing one. The link is only returned once."""
        url = self._feed_url(self.service.create_or_rotate(self.user))
        webcal_url = "webcal://" + url.split("://", 1)[-1]
        return CalendarFeedCreated(url=url, webcal_url=webcal_url)

    @router.delete("", status_code=status.HTTP_204_NO_CONTENT)
    def revoke(self):
        token = self.repos.calendar_feed_tokens.get_one(self.user.id, key="user_id")
        if not token:
            raise HTTPException(status.HTTP_404_NOT_FOUND, ErrorResponse.respond("Calendar feed not found"))

        self.repos.calendar_feed_tokens.delete(token.id)


@public_router.get("/{token}.ics", response_class=Response)
def get_calendar_feed(token: str, session: Session = Depends(generate_session)) -> Response:
    service = CalendarFeedService(get_repositories(session, group_id=None, household_id=None))

    feed_token = service.resolve(token)
    calendar = service.build_feed(feed_token, get_locale_provider()) if feed_token else None
    if calendar is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, ErrorResponse.respond("Calendar feed not found"))

    return Response(
        content=calendar,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'inline; filename="mealie-mealplan.ics"',
            "Cache-Control": "private, max-age=900",
        },
    )
