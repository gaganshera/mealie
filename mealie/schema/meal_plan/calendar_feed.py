from datetime import datetime

from pydantic import UUID4, ConfigDict

from mealie.schema._mealie import MealieModel


class CalendarFeedTokenSave(MealieModel):
    user_id: UUID4
    token_hash: str


class CalendarFeedTokenInDB(CalendarFeedTokenSave):
    id: int
    group_id: UUID4
    household_id: UUID4 | None = None
    created_at: datetime | None = None
    last_accessed_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class CalendarFeedStatus(MealieModel):
    enabled: bool
    created_at: datetime | None = None
    last_accessed_at: datetime | None = None


class CalendarFeedCreated(MealieModel):
    """Should ONLY be returned when creating a feed, as the URLs contain the token"""

    url: str
    webcal_url: str
