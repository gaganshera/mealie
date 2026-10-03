from functools import cached_property

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm.session import Session

from mealie.core.config import get_app_settings
from mealie.db.db_setup import generate_session
from mealie.lang.providers import Translator, get_locale_provider
from mealie.repos.all_repositories import get_repositories
from mealie.routes._base.base_controllers import BaseUserController
from mealie.routes._base.controller import controller
from mealie.routes._base.routers import UserAPIRouter
from mealie.schema.meal_plan.calendar_feed import CalendarFeedCreated, CalendarFeedStatus
from mealie.schema.response.responses import ErrorResponse, SuccessResponse
from mealie.services.household_services.calendar_feed_service import CalendarFeedService

# Deliberately not under /households/mealplans: that controller's /{item_id} route would match first
PREFIX = "/households/calendar-feed"

router = UserAPIRouter(prefix=PREFIX, tags=["Households: Meal Plan Calendar Feed"])
public_router = APIRouter(prefix=PREFIX, tags=["Households: Meal Plan Calendar Feed"])


def feed_urls(raw_token: str) -> CalendarFeedCreated:
    base_url = get_app_settings().BASE_URL.rstrip("/")
    url = f"{base_url}/api{PREFIX}/{raw_token}.ics"
    _, _, rest = url.partition("://")
    return CalendarFeedCreated(url=url, webcal_url=f"webcal://{rest}")


@controller(router)
class CalendarFeedController(BaseUserController):
    @cached_property
    def service(self) -> CalendarFeedService:
        return CalendarFeedService(self.repos)

    @router.get("", response_model=CalendarFeedStatus)
    def get_calendar_feed_status(self):
        return self.service.get_status(self.user.id)

    @router.post("", response_model=CalendarFeedCreated, status_code=201)
    def create_calendar_feed(self):
        """Creates the calendar feed link, replacing any existing one. The link is only returned once."""
        return feed_urls(self.service.create_or_rotate(self.user.id))

    @router.delete("", response_model=SuccessResponse)
    def revoke_calendar_feed(self):
        if not self.service.revoke(self.user.id):
            raise HTTPException(status_code=404, detail=ErrorResponse.respond("Calendar feed not found"))

        return SuccessResponse.respond(message="Calendar feed revoked")


@public_router.get("/{token}.ics", response_class=Response)
def get_calendar_feed(
    token: str,
    session: Session = Depends(generate_session),
    translator: Translator = Depends(get_locale_provider),
) -> Response:
    """Public iCal feed of a household's meal plan, authenticated only by the secret token in the URL"""
    service = CalendarFeedService(get_repositories(session, group_id=None, household_id=None))

    feed_token = service.resolve(token)
    if feed_token is None:
        raise HTTPException(status_code=404, detail=ErrorResponse.respond("Calendar feed not found"))

    return Response(
        content=service.build_feed(feed_token, translator),
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'inline; filename="mealie-mealplan.ics"',
            "Cache-Control": "private, max-age=900",
        },
    )
