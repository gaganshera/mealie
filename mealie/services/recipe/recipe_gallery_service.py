import builtins
import shutil
from pathlib import Path

from pydantic import UUID4

from mealie.core import exceptions
from mealie.pkgs import cache
from mealie.pkgs.img.minify import IMAGE_EXTENSIONS
from mealie.repos.all_repositories import get_repositories
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_gallery import RecipeGalleryImageOut, RecipeGalleryImageSave
from mealie.services._base_service import BaseService
from mealie.services.recipe.recipe_data_service import RecipeDataService
from mealie.services.recipe.recipe_service import RecipeService

MAX_GALLERY_IMAGES = 30
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class GalleryImageError(Exception):
    """Raised for a gallery request that can't be fulfilled as sent (bad file, limits, mismatched ids)"""


class RecipeGalleryService(BaseService):
    def __init__(self, repos: AllRepositories, recipe_service: RecipeService):
        self.recipe_service = recipe_service
        self.repo = get_repositories(repos.session, group_id=repos.group_id, household_id=None).recipe_gallery_images
        super().__init__()

    def _check_can_update(self, recipe: Recipe) -> None:
        if not recipe.slug or not self.recipe_service.can_update([recipe.slug]):
            raise exceptions.PermissionDenied("You do not have permission to edit this recipe.")

    def _get_image(self, recipe: Recipe, image_id: UUID4) -> RecipeGalleryImageOut:
        image = self.repo.get_one(image_id)
        if not image or image.recipe_id != recipe.id:
            raise exceptions.NoEntryFound("Gallery image not found.")
        return image

    def _renumber(self, images: list[RecipeGalleryImageOut]) -> None:
        changed = [{"id": image.id, "position": i} for i, image in enumerate(images) if image.position != i]
        if changed:
            self.repo.update_many(changed)

    @staticmethod
    def _remove_dir(image_dir: Path) -> None:
        shutil.rmtree(image_dir, ignore_errors=True)

    def list(self, recipe: Recipe) -> list[RecipeGalleryImageOut]:
        images = self.repo.multi_query({"recipe_id": recipe.id})
        return sorted(images, key=lambda image: image.position)

    def add(self, recipe: Recipe, data: bytes, extension: str, caption: str | None = None) -> RecipeGalleryImageOut:
        """Adds an image to the end of the gallery"""
        self._check_can_update(recipe)

        extension = extension.lower().lstrip(".")
        if f".{extension}" not in IMAGE_EXTENSIONS:
            raise GalleryImageError(f"Unsupported image type '{extension}'")
        if len(data) > MAX_UPLOAD_BYTES:
            raise GalleryImageError("Image is too large")

        existing = self.list(recipe)
        if len(existing) >= MAX_GALLERY_IMAGES:
            raise GalleryImageError(f"A recipe can have at most {MAX_GALLERY_IMAGES} gallery images")

        assert recipe.id
        image = self.repo.create(
            RecipeGalleryImageSave(
                recipe_id=recipe.id, group_id=recipe.group_id, position=len(existing), caption=caption
            )
        )

        try:
            RecipeDataService(recipe.id).write_image(data, extension, image.image_dir)
        except Exception as e:
            self.logger.exception(f"Failed to process gallery image for recipe {recipe.slug}")
            self.repo.delete(image.id)
            self._remove_dir(image.image_dir)
            raise GalleryImageError("File could not be processed as an image") from e

        return image

    def update_caption(self, recipe: Recipe, image_id: UUID4, caption: str | None) -> RecipeGalleryImageOut:
        self._check_can_update(recipe)
        self._get_image(recipe, image_id)
        return self.repo.patch(image_id, {"caption": caption})

    def reorder(self, recipe: Recipe, image_ids: builtins.list[UUID4]) -> builtins.list[RecipeGalleryImageOut]:
        """Reorders the gallery. `image_ids` must be exactly the recipe's current images."""
        self._check_can_update(recipe)

        current = {image.id: image for image in self.list(recipe)}
        if len(image_ids) != len(current) or set(image_ids) != set(current):
            raise GalleryImageError("The image ids must match the recipe's gallery images exactly")

        self._renumber([current[image_id] for image_id in image_ids])
        return self.list(recipe)

    def delete(self, recipe: Recipe, image_id: UUID4) -> RecipeGalleryImageOut:
        """Deletes an image and its files, then closes the gap in positions"""
        self._check_can_update(recipe)
        image = self._get_image(recipe, image_id)

        self.repo.delete(image.id)
        self._remove_dir(image.image_dir)
        self._renumber(self.list(recipe))
        return image

    def set_as_cover(self, recipe: Recipe, image_id: UUID4) -> str:
        """Copies a gallery image to the recipe's cover image. The image stays in the gallery."""
        self._check_can_update(recipe)
        image = self._get_image(recipe, image_id)

        source = image.image_dir.joinpath("original.webp")
        if not source.exists():
            raise exceptions.NoEntryFound("Gallery image file not found.")

        assert recipe.id and recipe.slug
        RecipeDataService(recipe.id).write_image(source, "webp")

        recipe.image = cache.cache_key.new_key()
        self.recipe_service.update_one(recipe.slug, recipe)
        return recipe.image
