from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, orm
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.orm import Mapped, mapped_column

from mealie.db.models._model_utils.auto_init import auto_init
from mealie.db.models._model_utils.datetime import NaiveDateTime
from mealie.db.models._model_utils.guid import GUID

from .._model_base import BaseMixins, SqlAlchemyBase

if TYPE_CHECKING:
    from ..users import User


class MealPlanCalendarFeedToken(SqlAlchemyBase, BaseMixins):
    """A read-only secret that lets calendar apps fetch a user's household meal plan as iCal.

    Only the SHA-256 hash of the token is stored; the plain token is shown to the user once.
    """

    __tablename__ = "mealplan_calendar_feed_tokens"
    id: Mapped[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)

    user_id: Mapped[GUID] = mapped_column(GUID, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    user: Mapped[User] = orm.relationship("User", back_populates="calendar_feed_token")

    # Not stored, so the feed always follows the user's current household
    group_id: AssociationProxy[GUID] = association_proxy("user", "group_id")
    household_id: AssociationProxy[GUID] = association_proxy("user", "household_id")

    last_accessed_at: Mapped[datetime | None] = mapped_column(NaiveDateTime, nullable=True, default=None)

    @auto_init()
    def __init__(self, **_) -> None:
        pass
