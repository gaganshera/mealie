from shutil import rmtree

from pydantic import UUID4

from mealie.core import exceptions
from mealie.pkgs import cache
from mealie.pkgs.img.minify import IMAGE_EXTENSIONS
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_gallery import RecipeGalleryImageOut
from mealie.services._base_service import BaseService
from mealie.services.recipe.recipe_data_service import RecipeDataService
from mealie.services.recipe.recipe_service import RecipeService

MAX_GALLERY_IMAGES = 30
MAX_GALLERY_UPLOAD_BYTES = 20 * 1024 * 1024


class GalleryImageError(Exception):
    """An upload or change to a recipe's gallery that can't be accepted"""


class RecipeGalleryService(BaseService):
    def __init__(self, repos: AllRepositories, recipe_service: RecipeService):
        self.repos = repos
        self.recipe_service = recipe_service
        super().__init__()

    @property
    def repo(self):
        return self.repos.recipe_gallery_images

    def get_recipe(self, slug_or_id: str) -> Recipe:
        return self.recipe_service.get_one(slug_or_id)

    def _check_can_update(self, recipe: Recipe) -> None:
        if not self.recipe_service.can_update([recipe.slug]):
            raise exceptions.PermissionDenied("You do not have permission to edit this recipe.")

    def _get_image(self, recipe: Recipe, image_id: UUID4) -> RecipeGalleryImageOut:
        image = self.repo.get_one(image_id)
        if image is None or image.recipe_id != recipe.id:
            raise exceptions.NoEntryFound("Gallery image not found.")
        return image

    def _renumber(self, images: list[RecipeGalleryImageOut]) -> None:
        for position, image in enumerate(images):
            if image.position != position:
                self.repo.patch(image.id, {"position": position})

    def list_images(self, recipe: Recipe) -> list[RecipeGalleryImageOut]:
        images = self.repo.multi_query({"recipe_id": recipe.id})
        return sorted(images, key=lambda image: image.position)

    def add(self, recipe: Recipe, data: bytes, extension: str, caption: str | None = None) -> RecipeGalleryImageOut:
        """Adds an image to the end of the recipe's gallery"""
        self._check_can_update(recipe)

        extension = extension.lower().lstrip(".")
        if f".{extension}" not in IMAGE_EXTENSIONS:
            raise GalleryImageError(f"Unsupported image type: {extension}")
        if len(data) > MAX_GALLERY_UPLOAD_BYTES:
            raise GalleryImageError("Image is too large")

        images = self.list_images(recipe)
        if len(images) >= MAX_GALLERY_IMAGES:
            raise GalleryImageError(f"A recipe can have at most {MAX_GALLERY_IMAGES} gallery images")

        image = self.repo.create(
            {
                "recipe_id": recipe.id,
                "group_id": recipe.group_id,
                "position": len(images),
                "caption": caption or None,
            }
        )

        image_dir = Recipe.gallery_image_dir_from_id(recipe.id, image.id)
        try:
            RecipeDataService(recipe.id).write_image(data, extension, image_dir=image_dir)
        except Exception as e:
            rmtree(image_dir, ignore_errors=True)
            self.repo.delete(image.id)
            raise GalleryImageError("Image could not be processed") from e

        return image

    def update_caption(self, recipe: Recipe, image_id: UUID4, caption: str | None) -> RecipeGalleryImageOut:
        self._check_can_update(recipe)
        self._get_image(recipe, image_id)
        return self.repo.patch(image_id, {"caption": caption or None})

    def reorder(self, recipe: Recipe, ids: list[UUID4]) -> list[RecipeGalleryImageOut]:
        """Reorders the gallery. `ids` must be exactly the recipe's current images."""
        self._check_can_update(recipe)

        images = {image.id: image for image in self.list_images(recipe)}
        if len(ids) != len(set(ids)) or set(ids) != set(images):
            raise GalleryImageError("The new order must contain every gallery image exactly once")

        self._renumber([images[image_id] for image_id in ids])
        return self.list_images(recipe)

    def delete(self, recipe: Recipe, image_id: UUID4) -> None:
        self._check_can_update(recipe)
        self._get_image(recipe, image_id)

        self.repo.delete(image_id)
        rmtree(Recipe.gallery_image_dir_from_id(recipe.id, image_id), ignore_errors=True)
        self._renumber(self.list_images(recipe))

    def set_as_cover(self, recipe: Recipe, image_id: UUID4) -> str:
        """Copies a gallery image to the recipe's cover image. The gallery image stays in the gallery."""
        self._check_can_update(recipe)
        self._get_image(recipe, image_id)

        source = Recipe.gallery_image_dir_from_id(recipe.id, image_id).joinpath("original.webp")
        if not source.is_file():
            raise exceptions.NoEntryFound("Gallery image file not found.")

        RecipeDataService(recipe.id).write_image(source, "webp")

        recipe.image = cache.cache_key.new_key()
        self.recipe_service.update_one(recipe.slug, recipe)
        return recipe.image
