from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, orm
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.orm import Mapped, mapped_column

from .._model_base import BaseMixins, SqlAlchemyBase
from .._model_utils.datetime import NaiveDateTime
from .._model_utils.guid import GUID

if TYPE_CHECKING:
    from ..users import User


class MealPlanCalendarFeedToken(SqlAlchemyBase, BaseMixins):
    """A read-only token for a user's meal plan iCal feed. Only the SHA-256 hash of the token is stored."""

    __tablename__ = "mealplan_calendar_feed_tokens"
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    last_accessed_at: Mapped[datetime | None] = mapped_column(NaiveDateTime, nullable=True, default=None)

    user_id: Mapped[GUID] = mapped_column(GUID, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    user: Mapped[User] = orm.relationship("User", back_populates="calendar_feed_token")

    # Not stored, so the feed always follows the user's current household
    group_id: AssociationProxy[GUID] = association_proxy("user", "group_id")
    household_id: AssociationProxy[GUID] = association_proxy("user", "household_id")

    def __init__(self, token_hash, user_id, last_accessed_at=None, **_) -> None:
        self.token_hash = token_hash
        self.user_id = user_id
        self.last_accessed_at = last_accessed_at
