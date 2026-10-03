import builtins
import shutil
from typing import TYPE_CHECKING

from pydantic import UUID4

from mealie.core import exceptions
from mealie.pkgs import cache
from mealie.pkgs.img.minify import IMAGE_EXTENSIONS
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_gallery import RecipeGalleryImageOut, RecipeGalleryImageSave
from mealie.schema.recipe.recipe_image_types import RecipeImageTypes
from mealie.services._base_service import BaseService
from mealie.services.recipe.recipe_data_service import RecipeDataService

if TYPE_CHECKING:
    from mealie.services.recipe.recipe_service import RecipeService

MAX_GALLERY_IMAGES = 30
MAX_GALLERY_UPLOAD_BYTES = 20 * 1024 * 1024


class GalleryImageError(Exception):
    """The upload or request can't be applied to the gallery; reported to the client as a 400."""


class RecipeGalleryService(BaseService):
    def __init__(self, repos: AllRepositories, recipe_service: RecipeService):
        self.repos = repos
        self.recipe_service = recipe_service
        super().__init__()

    @property
    def repo(self):
        return self.repos.recipe_gallery_images

    def get_recipe(self, slug: str) -> Recipe:
        """Returns any recipe the user can see. Raises `NoEntryFound` otherwise."""
        return self.recipe_service.get_one(slug)

    def _check_can_update(self, recipe: Recipe) -> None:
        if not recipe.slug or not self.recipe_service.can_update([recipe.slug]):
            raise exceptions.PermissionDenied("You do not have permission to edit this recipe.")

    def _get_image(self, recipe: Recipe, image_id: UUID4) -> RecipeGalleryImageOut:
        image = self.repo.get_one(image_id)
        if image is None or image.recipe_id != recipe.id:
            raise exceptions.NoEntryFound("Gallery image not found.")
        return image

    def _renumber(self, images: list[RecipeGalleryImageOut]) -> list[RecipeGalleryImageOut]:
        changed = [{"id": image.id, "position": i} for i, image in enumerate(images) if image.position != i]
        if changed:
            self.repo.update_many(changed)
        return [image.model_copy(update={"position": i}) for i, image in enumerate(images)]

    def list(self, recipe: Recipe) -> list[RecipeGalleryImageOut]:
        if recipe.id is None:
            return []
        images = self.repo.multi_query({"recipe_id": recipe.id})
        return sorted(images, key=lambda image: image.position)

    def add(self, recipe: Recipe, data: bytes, extension: str, caption: str | None = None) -> RecipeGalleryImageOut:
        """Adds an image to the end of the recipe's gallery"""
        self._check_can_update(recipe)
        assert recipe.id is not None

        extension = extension.lower().lstrip(".")
        if f".{extension}" not in IMAGE_EXTENSIONS:
            raise GalleryImageError("Unsupported image type")
        if len(data) > MAX_GALLERY_UPLOAD_BYTES:
            raise GalleryImageError("Image is too large")

        existing = self.list(recipe)
        if len(existing) >= MAX_GALLERY_IMAGES:
            raise GalleryImageError(f"A recipe can have at most {MAX_GALLERY_IMAGES} gallery images")

        save = RecipeGalleryImageSave(
            recipe_id=recipe.id, group_id=recipe.group_id, position=len(existing), caption=caption or None
        )
        image = self.repo.create(save)
        try:
            RecipeDataService(recipe.id).write_image(data, extension, image_dir=image.image_dir)
        except Exception as e:
            self.repo.delete(image.id)
            shutil.rmtree(image.image_dir, ignore_errors=True)
            raise GalleryImageError("File is not a valid image") from e

        return image

    def update_caption(self, recipe: Recipe, image_id: UUID4, caption: str | None) -> RecipeGalleryImageOut:
        self._check_can_update(recipe)
        self._get_image(recipe, image_id)
        return self.repo.patch(image_id, {"caption": caption or None})

    def reorder(self, recipe: Recipe, image_ids: builtins.list[UUID4]) -> builtins.list[RecipeGalleryImageOut]:
        """Puts the gallery in the given order. The ids must be exactly the recipe's current images."""
        self._check_can_update(recipe)

        images = {image.id: image for image in self.list(recipe)}
        if len(image_ids) != len(images) or set(image_ids) != set(images):
            raise GalleryImageError("Image ids must match the recipe's gallery images exactly")

        return self._renumber([images[image_id] for image_id in image_ids])

    def delete(self, recipe: Recipe, image_id: UUID4) -> RecipeGalleryImageOut:
        """Removes the image and its files, then closes the gap in positions"""
        self._check_can_update(recipe)
        image = self._get_image(recipe, image_id)

        self.repo.delete(image.id)
        shutil.rmtree(image.image_dir, ignore_errors=True)

        self._renumber(self.list(recipe))
        return image

    def set_as_cover(self, recipe: Recipe, image_id: UUID4) -> str:
        """Copies the gallery image to the recipe's cover image. The image stays in the gallery."""
        self._check_can_update(recipe)
        assert recipe.id is not None and recipe.slug is not None
        image = self._get_image(recipe, image_id)

        source = image.image_dir.joinpath(RecipeImageTypes.original.value)
        if not source.is_file():
            raise exceptions.NoEntryFound("Gallery image file not found.")

        RecipeDataService(recipe.id).write_image(source, "webp")

        recipe.image = cache.cache_key.new_key()
        self.recipe_service.update_one(recipe.slug, recipe)
        return recipe.image

    @staticmethod
    def duplicate(repos: AllRepositories, old_recipe_id: UUID4, new_recipe: Recipe) -> None:
        """Gives a duplicated recipe its own gallery rows. Expects the recipe's data folder to be copied already,
        and renames the copied `gallery/<old_id>` folders to the new ids."""
        assert new_recipe.id is not None
        old_images = repos.recipe_gallery_images.multi_query({"recipe_id": old_recipe_id})
        if not old_images:
            return

        gallery_dir = Recipe.image_dir_from_id(new_recipe.id).joinpath("gallery")
        for old_image in old_images:
            save = RecipeGalleryImageSave(
                recipe_id=new_recipe.id,
                group_id=new_recipe.group_id,
                position=old_image.position,
                caption=old_image.caption,
            )
            new_image = repos.recipe_gallery_images.create(save)

            copied_dir = gallery_dir.joinpath(str(old_image.id))
            if copied_dir.exists():
                copied_dir.rename(gallery_dir.joinpath(str(new_image.id)))
