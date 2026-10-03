from functools import cached_property

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from mealie.db.db_setup import generate_session
from mealie.lang import get_locale_provider
from mealie.lang.providers import Translator
from mealie.routes._base.base_controllers import BaseUserController
from mealie.routes._base.controller import controller
from mealie.routes._base.routers import UserAPIRouter
from mealie.schema.meal_plan.calendar_feed import CalendarFeedCreated, CalendarFeedStatus
from mealie.schema.response.responses import ErrorResponse
from mealie.services.household_services.calendar_feed_service import CalendarFeedService

# Kept outside /households/mealplans, whose /{item_id} route would swallow these paths
PREFIX = "/households/calendar-feed"

router = UserAPIRouter(prefix=PREFIX, tags=["Households: Meal Plan Calendar Feed"])
public_router = APIRouter(prefix=PREFIX, tags=["Households: Meal Plan Calendar Feed"])


@controller(router)
class CalendarFeedController(BaseUserController):
    @cached_property
    def service(self) -> CalendarFeedService:
        return CalendarFeedService(self.session)

    @router.get("", response_model=CalendarFeedStatus)
    def get_status(self):
        token = self.service.get(self.user.id)
        if not token:
            return CalendarFeedStatus(enabled=False)
        return CalendarFeedStatus(enabled=True, created_at=token.created_at, last_accessed_at=token.last_accessed_at)

    @router.post("", response_model=CalendarFeedCreated, status_code=201)
    def create_or_rotate(self):
        raw_token = self.service.create_or_rotate(self.user)
        url = f"{self.settings.BASE_URL}/api{PREFIX}/{raw_token}.ics"
        return CalendarFeedCreated(url=url, webcal_url="webcal://" + url.split("://", 1)[-1])

    @router.delete("", status_code=204)
    def revoke(self):
        self.service.revoke(self.user.id)


@public_router.get("/{token}.ics", response_class=Response)
def get_calendar_feed(
    token: str,
    session: Session = Depends(generate_session),
    translator: Translator = Depends(get_locale_provider),
) -> Response:
    service = CalendarFeedService(session)
    user = service.resolve(token)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=ErrorResponse.respond("Feed Not Found"))

    return Response(
        content=service.feed_for_user(user, translator),
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'inline; filename="mealie-mealplan.ics"',
            "Cache-Control": "private, max-age=900",
        },
    )
