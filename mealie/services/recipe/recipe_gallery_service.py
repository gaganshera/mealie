import shutil
from uuid import uuid4

from pydantic import UUID4

from mealie.core import exceptions
from mealie.pkgs import cache
from mealie.pkgs.img.minify import IMAGE_EXTENSIONS
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_gallery import RecipeGalleryImageOut, RecipeGalleryImageSave
from mealie.services._base_service import BaseService
from mealie.services.recipe.recipe_data_service import RecipeDataService
from mealie.services.recipe.recipe_service import RecipeService

MAX_IMAGES_PER_RECIPE = 30
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class GalleryImageError(Exception):
    """A gallery request that can't be fulfilled because of what was sent (returned as a 400)"""


class RecipeGalleryService(BaseService):
    def __init__(self, recipe_service: RecipeService):
        super().__init__()
        self.recipe_service = recipe_service
        self.repo = recipe_service.repos.recipe_gallery_images

    def _assert_can_update(self, recipe: Recipe) -> None:
        if not self.recipe_service.can_update([recipe.slug]):
            raise exceptions.PermissionDenied("You do not have permission to edit this recipe.")

    def _get_image(self, recipe: Recipe, image_id: UUID4) -> RecipeGalleryImageOut:
        image = self.repo.get_one(image_id)
        if image is None or image.recipe_id != recipe.id:
            raise exceptions.NoEntryFound("Gallery image not found.")
        return image

    def list_images(self, recipe: Recipe) -> list[RecipeGalleryImageOut]:
        images = self.repo.multi_query({"recipe_id": recipe.id})
        return sorted(images, key=lambda image: image.position)

    def add(self, recipe: Recipe, data: bytes, extension: str, caption: str | None = None) -> RecipeGalleryImageOut:
        """Adds an image to the end of the recipe's gallery"""
        self._assert_can_update(recipe)

        extension = extension.split(".")[-1].lower()
        if f".{extension}" not in IMAGE_EXTENSIONS:
            raise GalleryImageError("Unsupported image type")
        if len(data) > MAX_UPLOAD_BYTES:
            raise GalleryImageError("Image is too large")

        images = self.list_images(recipe)
        if len(images) >= MAX_IMAGES_PER_RECIPE:
            raise GalleryImageError(f"A recipe can have at most {MAX_IMAGES_PER_RECIPE} gallery images")

        image_id = uuid4()
        image_dir = Recipe.gallery_image_dir_from_id(recipe.id, image_id)
        try:
            RecipeDataService(recipe.id).write_image(data, extension, image_dir=image_dir)
        except Exception as e:
            shutil.rmtree(image_dir, ignore_errors=True)
            raise GalleryImageError("The file could not be read as an image") from e

        position = images[-1].position + 1 if images else 0
        return self.repo.create(
            RecipeGalleryImageSave(
                id=image_id, group_id=recipe.group_id, recipe_id=recipe.id, position=position, caption=caption
            )
        )

    def update_caption(self, recipe: Recipe, image_id: UUID4, caption: str | None) -> RecipeGalleryImageOut:
        self._assert_can_update(recipe)
        self._get_image(recipe, image_id)
        return self.repo.patch(image_id, {"caption": caption})

    def reorder(self, recipe: Recipe, ids: list[UUID4]) -> list[RecipeGalleryImageOut]:
        """Sets the gallery order. `ids` must be exactly the recipe's current images."""
        self._assert_can_update(recipe)

        images = {image.id: image for image in self.list_images(recipe)}
        if len(ids) != len(images) or set(ids) != set(images):
            raise GalleryImageError("The order must list each of the recipe's gallery images exactly once")

        for position, image_id in enumerate(ids):
            if images[image_id].position != position:
                self.repo.patch(image_id, {"position": position})

        return self.list_images(recipe)

    def delete(self, recipe: Recipe, image_id: UUID4) -> RecipeGalleryImageOut:
        """Deletes an image and its files, then closes the gap in positions"""
        self._assert_can_update(recipe)
        image = self._get_image(recipe, image_id)

        self.repo.delete(image_id)
        shutil.rmtree(image.image_dir, ignore_errors=True)

        for position, remaining in enumerate(self.list_images(recipe)):
            if remaining.position != position:
                self.repo.patch(remaining.id, {"position": position})

        return image

    def set_as_cover(self, recipe: Recipe, image_id: UUID4) -> str:
        """Copies a gallery image to the recipe's cover image and returns the new image key"""
        self._assert_can_update(recipe)
        image = self._get_image(recipe, image_id)

        source = image.image_dir.joinpath("original.webp")
        if not source.is_file():
            raise exceptions.NoEntryFound("Gallery image file not found.")

        RecipeDataService(recipe.id).write_image(source, "webp")

        recipe.image = cache.cache_key.new_key()
        self.recipe_service.update_one(recipe.slug, recipe)
        return recipe.image
