from functools import cached_property

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm.session import Session

from mealie.db.db_setup import generate_session
from mealie.lang.providers import get_locale_provider
from mealie.repos.all_repositories import get_repositories
from mealie.routes._base import BaseUserController, controller
from mealie.schema.meal_plan.calendar_feed import CalendarFeedCreated, CalendarFeedStatus
from mealie.schema.response.responses import ErrorResponse, SuccessResponse
from mealie.services.household_services.calendar_feed_service import CalendarFeedService

router = APIRouter(prefix="/households/calendar-feed", tags=["Households: Calendar Feed"])
public_router = APIRouter(prefix="/households/calendar-feed", tags=["Households: Calendar Feed"])


@controller(router)
class CalendarFeedController(BaseUserController):
    @cached_property
    def service(self) -> CalendarFeedService:
        return CalendarFeedService(self.repos)

    @router.get("", response_model=CalendarFeedStatus)
    def get_status(self):
        token = self.service.get_token(self.user.id)
        if token is None:
            return CalendarFeedStatus(enabled=False)

        return CalendarFeedStatus(enabled=True, created_at=token.created_at, last_accessed_at=token.last_accessed_at)

    @router.post("", response_model=CalendarFeedCreated, status_code=status.HTTP_201_CREATED)
    def create_or_rotate(self):
        raw_token = self.service.create_or_rotate(self.user)
        return self.service.feed_urls(raw_token)

    @router.delete("", response_model=SuccessResponse)
    def revoke(self):
        if not self.service.revoke(self.user.id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, ErrorResponse.respond("Calendar feed not found"))

        return SuccessResponse.respond("Calendar feed revoked")


@public_router.get("/{token}.ics", response_class=Response)
def get_calendar_feed(token: str, session: Session = Depends(generate_session)) -> Response:
    """Public meal plan calendar feed. The token in the URL is the only authentication."""
    service = CalendarFeedService(get_repositories(session, group_id=None, household_id=None))

    feed_token = service.resolve(token)
    if feed_token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, ErrorResponse.respond("Calendar feed not found"))

    # Calendar apps send no meaningful language, so use the default one
    content = service.get_feed(feed_token, get_locale_provider(None))
    return Response(
        content=content,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'inline; filename="mealie-mealplan.ics"',
            "Cache-Control": "private, max-age=900",
        },
    )
