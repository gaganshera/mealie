from datetime import datetime
from pathlib import Path

from pydantic import UUID4, ConfigDict

from mealie.schema._mealie import MealieModel
from mealie.schema._mealie.mealie_model import UpdatedAtField
from mealie.schema.recipe.recipe import Recipe


class RecipeGalleryImageCreate(MealieModel):
    caption: str | None = None


class RecipeGalleryImageSave(RecipeGalleryImageCreate):
    recipe_id: UUID4
    group_id: UUID4
    position: int


class RecipeGalleryImageUpdate(MealieModel):
    caption: str | None = None


class RecipeGalleryImageOut(MealieModel):
    id: UUID4
    recipe_id: UUID4
    position: int
    caption: str | None = None

    created_at: datetime
    updated_at: datetime = UpdatedAtField(...)
    model_config = ConfigDict(from_attributes=True)

    @property
    def image_dir(self) -> Path:
        return Recipe.gallery_image_dir_from_id(self.recipe_id, self.id)


class RecipeGalleryOrder(MealieModel):
    image_ids: list[UUID4]
