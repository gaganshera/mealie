from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .._model_base import BaseMixins, FilterableColumn, SqlAlchemyBase
from .._model_utils.auto_init import auto_init
from .._model_utils.guid import GUID

if TYPE_CHECKING:
    from . import RecipeModel


class RecipeGalleryImage(SqlAlchemyBase, BaseMixins):
    """An extra photo on a recipe. The files live in `images/gallery/<id>/` next to the cover image."""

    __tablename__ = "recipe_gallery_images"
    id: FilterableColumn[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)

    recipe_id: FilterableColumn[GUID] = mapped_column(GUID, ForeignKey("recipes.id"), nullable=False, index=True)
    recipe: Mapped[RecipeModel] = relationship("RecipeModel", back_populates="gallery_images")

    group_id: FilterableColumn[GUID] = mapped_column(GUID, ForeignKey("groups.id"), nullable=False, index=True)

    position: FilterableColumn[int] = mapped_column(Integer, nullable=False, default=0)
    caption: FilterableColumn[str | None] = mapped_column(String, nullable=True)

    @auto_init()
    def __init__(self, **_) -> None:
        pass
