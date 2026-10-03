from datetime import datetime
from pathlib import Path

from pydantic import UUID4, ConfigDict

from mealie.schema._mealie import MealieModel
from mealie.schema._mealie.mealie_model import UpdatedAtField
from mealie.schema.recipe.recipe import Recipe


class RecipeGalleryImageCreate(MealieModel):
    caption: str | None = None


class RecipeGalleryImageUpdate(MealieModel):
    caption: str | None = None


class RecipeGalleryImageSave(RecipeGalleryImageCreate):
    id: UUID4
    group_id: UUID4
    recipe_id: UUID4
    position: int


class RecipeGalleryImageOut(MealieModel):
    id: UUID4
    recipe_id: UUID4
    position: int
    caption: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = UpdatedAtField(None)
    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def image_dir_from_id(cls, recipe_id: UUID4 | str, image_id: UUID4 | str) -> Path:
        return Recipe.gallery_image_dir_from_id(recipe_id, image_id)

    @property
    def image_dir(self) -> Path:
        return self.image_dir_from_id(self.recipe_id, self.id)


class RecipeGalleryOrder(MealieModel):
    ids: list[UUID4]
