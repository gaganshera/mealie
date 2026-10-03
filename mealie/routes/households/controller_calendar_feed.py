from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm.session import Session

from mealie.db.db_setup import generate_session
from mealie.lang.providers import get_locale_provider
from mealie.repos.all_repositories import get_repositories
from mealie.routes._base import BaseUserController, controller
from mealie.schema.meal_plan.calendar_feed import CalendarFeedCreated, CalendarFeedStatus
from mealie.schema.response.responses import ErrorResponse, SuccessResponse
from mealie.services.household_services.calendar_feed_service import CalendarFeedService

# Deliberately outside /households/mealplans, whose /{item_id} route would otherwise capture these paths
router = APIRouter(prefix="/households/calendar-feed", tags=["Households: Meal Plan Calendar Feed"])
public_router = APIRouter(prefix="/households/calendar-feed", tags=["Households: Meal Plan Calendar Feed"])


def _feed_service(session: Session) -> CalendarFeedService:
    return CalendarFeedService(get_repositories(session, group_id=None, household_id=None))


@controller(router)
class CalendarFeedController(BaseUserController):
    @property
    def service(self) -> CalendarFeedService:
        return _feed_service(self.session)

    def _feed_urls(self, raw_token: str) -> CalendarFeedCreated:
        base_url = self.settings.BASE_URL.rstrip("/")
        url = f"{base_url}/api/households/calendar-feed/{raw_token}.ics"
        return CalendarFeedCreated(url=url, webcal_url="webcal://" + url.split("://", 1)[-1])

    @router.get("", response_model=CalendarFeedStatus)
    def get_status(self):
        token = self.service.get_for_user(self.user)
        if not token:
            return CalendarFeedStatus(enabled=False)

        return CalendarFeedStatus(enabled=True, created_at=token.created_at, last_accessed_at=token.last_accessed_at)

    @router.post("", response_model=CalendarFeedCreated, status_code=status.HTTP_201_CREATED)
    def create_or_rotate(self):
        """Creates a calendar feed link, replacing any existing one. The link is only returned once."""
        raw_token = self.service.create_or_rotate(self.user)
        return self._feed_urls(raw_token)

    @router.delete("", response_model=SuccessResponse)
    def revoke(self):
        if not self.service.revoke(self.user):
            raise HTTPException(status.HTTP_404_NOT_FOUND, ErrorResponse.respond("Calendar feed not found"))

        return SuccessResponse.respond("Calendar feed revoked")


@public_router.get("/{token}.ics", response_class=Response)
def get_calendar_feed(token: str, session: Session = Depends(generate_session)) -> Response:
    """Anonymous iCal feed of the token user's household meal plan"""
    service = _feed_service(session)

    feed_token = service.resolve(token)
    if not feed_token:
        raise HTTPException(status.HTTP_404_NOT_FOUND, ErrorResponse.respond("Calendar feed not found"))

    # Calendar apps don't send a meaningful language, so use the default one
    calendar = service.build_feed(feed_token, get_locale_provider(None))
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
