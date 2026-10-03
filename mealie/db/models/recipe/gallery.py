from typing import TYPE_CHECKING

import sqlalchemy as sa
from pydantic import ConfigDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mealie.db.models._model_base import BaseMixins, FilterableColumn, SqlAlchemyBase
from mealie.db.models._model_utils.auto_init import auto_init
from mealie.db.models._model_utils.guid import GUID

if TYPE_CHECKING:
    from . import RecipeModel


class RecipeGalleryImage(SqlAlchemyBase, BaseMixins):
    """An additional photo on a recipe. The image files live in `<recipe dir>/images/gallery/<id>/`."""

    __tablename__ = "recipe_gallery_images"
    id: FilterableColumn[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)

    group_id: FilterableColumn[GUID] = mapped_column(GUID, sa.ForeignKey("groups.id"), nullable=False, index=True)

    recipe_id: FilterableColumn[GUID] = mapped_column(GUID, sa.ForeignKey("recipes.id"), nullable=False, index=True)
    recipe: Mapped[RecipeModel] = relationship("RecipeModel", back_populates="gallery_images")

    position: FilterableColumn[int] = mapped_column(sa.Integer, nullable=False, default=0)
    caption: FilterableColumn[str | None] = mapped_column(sa.String, nullable=True)

    # Declaring an `exclude` lets a new row keep the id it's created with, which is also its image folder's
    # name. auto_init still ignores `id` when updating an existing row.
    model_config = ConfigDict(exclude={"recipe"})

    @auto_init()
    def __init__(self, **_) -> None:
        pass
