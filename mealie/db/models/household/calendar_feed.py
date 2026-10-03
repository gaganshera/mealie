from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import ForeignKey, String, orm
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.orm import Mapped, mapped_column

from .._model_base import BaseMixins, SqlAlchemyBase
from .._model_utils.auto_init import auto_init
from .._model_utils.datetime import NaiveDateTime
from .._model_utils.guid import GUID

if TYPE_CHECKING:
    from ..users import User


class MealPlanCalendarFeedToken(SqlAlchemyBase, BaseMixins):
    __tablename__ = "mealplan_calendar_feed_tokens"
    id: Mapped[GUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    last_accessed_at: Mapped[datetime | None] = mapped_column(NaiveDateTime, nullable=True)

    user_id: Mapped[GUID] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    user: Mapped[User] = orm.relationship("User", back_populates="calendar_feed_token")

    # Not stored: the feed follows the user's current household
    group_id: AssociationProxy[GUID] = association_proxy("user", "group_id")
    household_id: AssociationProxy[GUID] = association_proxy("user", "household_id")

    @auto_init()
    def __init__(self, **_) -> None:
        pass
