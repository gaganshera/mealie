from datetime import datetime

from pydantic import UUID4, ConfigDict

from mealie.schema._mealie import MealieModel


class CalendarFeedTokenSave(MealieModel):
    user_id: UUID4
    token_hash: str


class CalendarFeedTokenInDB(CalendarFeedTokenSave):
    id: UUID4
    created_at: datetime | None = None
    last_accessed_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class CalendarFeedStatus(MealieModel):
    enabled: bool = False
    created_at: datetime | None = None
    last_accessed_at: datetime | None = None


class CalendarFeedCreated(MealieModel):
    """Should ONLY be returned when the feed is created, as the URLs contain the secret token"""

    url: str
    webcal_url: str
