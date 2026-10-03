from datetime import datetime

from pydantic import UUID4, ConfigDict

from mealie.schema._mealie import MealieModel
from mealie.schema._mealie.mealie_model import UpdatedAtField


class RecipeGalleryImageCreate(MealieModel):
    caption: str | None = None


class RecipeGalleryImageUpdate(MealieModel):
    caption: str | None = None


class RecipeGalleryImageOut(MealieModel):
    id: UUID4
    recipe_id: UUID4
    position: int
    caption: str | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = UpdatedAtField(None)
    model_config = ConfigDict(from_attributes=True)


class RecipeGalleryOrder(MealieModel):
    ids: list[UUID4]
