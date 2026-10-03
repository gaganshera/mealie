import shutil

from pydantic import UUID4

from mealie.core import exceptions
from mealie.pkgs import img
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_gallery import RecipeGalleryImageCreate, RecipeGalleryImageOut
from mealie.services._base_service import BaseService
from mealie.services.recipe.recipe_data_service import RecipeDataService
from mealie.services.recipe.recipe_service import RecipeService

MAX_IMAGES_PER_RECIPE = 30
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class InvalidGalleryRequest(Exception):
    """Raised for uploads or reorders that can't be applied; maps to a 400"""


class RecipeGalleryService(BaseService):
    def __init__(self, recipe_service: RecipeService) -> None:
        self.recipe_service = recipe_service
        self.repo = recipe_service.repos.recipe_gallery_images
        super().__init__()

    def _editable_recipe(self, slug: str) -> Recipe:
        recipe = self.recipe_service.get_one(slug)
        if not self.recipe_service.can_update([recipe.slug]):
            raise exceptions.PermissionDenied("You do not have permission to edit this recipe.")
        return recipe

    def _images(self, recipe: Recipe) -> list[RecipeGalleryImageOut]:
        images = self.repo.multi_query({"recipe_id": recipe.id})
        return sorted(images, key=lambda image: image.position)

    def _get_image(self, recipe: Recipe, image_id: UUID4) -> RecipeGalleryImageOut:
        image = self.repo.get_one(image_id)
        if image is None or image.recipe_id != recipe.id:
            raise exceptions.NoEntryFound("Gallery image not found.")
        return image

    def _renumber(self, ids: list[UUID4]) -> None:
        self.repo.update_many([{"id": image_id, "position": i} for i, image_id in enumerate(ids)])

    def list_images(self, slug: str) -> list[RecipeGalleryImageOut]:
        return self._images(self.recipe_service.get_one(slug))

    def add(self, slug: str, data: bytes, extension: str, create: RecipeGalleryImageCreate) -> RecipeGalleryImageOut:
        recipe = self._editable_recipe(slug)

        extension = extension.lower().lstrip(".")
        if f".{extension}" not in img.IMAGE_EXTENSIONS:
            raise InvalidGalleryRequest("Unsupported image type")
        if len(data) > MAX_UPLOAD_BYTES:
            raise InvalidGalleryRequest("Image is too large")

        images = self._images(recipe)
        if len(images) >= MAX_IMAGES_PER_RECIPE:
            raise InvalidGalleryRequest(f"A recipe can have at most {MAX_IMAGES_PER_RECIPE} gallery images")

        image = self.repo.create(
            {
                "recipe_id": recipe.id,
                "group_id": recipe.group_id,
                "position": len(images),
                "caption": create.caption,
            }
        )
        image_dir = Recipe.gallery_image_dir_from_id(recipe.id, image.id)
        try:
            RecipeDataService(recipe.id).write_image(data, extension, image_dir=image_dir)
        except Exception as e:
            shutil.rmtree(image_dir, ignore_errors=True)
            self.repo.delete(image.id)
            raise InvalidGalleryRequest("File is not a valid image") from e

        return image

    def update_caption(self, slug: str, image_id: UUID4, caption: str | None) -> RecipeGalleryImageOut:
        recipe = self._editable_recipe(slug)
        self._get_image(recipe, image_id)
        return self.repo.update(image_id, {"caption": caption})

    def reorder(self, slug: str, ids: list[UUID4]) -> list[RecipeGalleryImageOut]:
        recipe = self._editable_recipe(slug)
        current = self._images(recipe)
        if len(ids) != len(current) or set(ids) != {image.id for image in current}:
            raise InvalidGalleryRequest("Order must list each of the recipe's gallery images exactly once")

        self._renumber(ids)
        return self._images(recipe)

    def delete(self, slug: str, image_id: UUID4) -> None:
        recipe = self._editable_recipe(slug)
        self._get_image(recipe, image_id)

        self.repo.delete(image_id)
        shutil.rmtree(Recipe.gallery_image_dir_from_id(recipe.id, image_id), ignore_errors=True)
        self._renumber([image.id for image in self._images(recipe)])

    def set_as_cover(self, slug: str, image_id: UUID4) -> str:
        recipe = self._editable_recipe(slug)
        self._get_image(recipe, image_id)

        source = Recipe.gallery_image_dir_from_id(recipe.id, image_id).joinpath("original.webp")
        RecipeDataService(recipe.id).write_image(source, "webp")
        return self.recipe_service.group_recipes.update_image(recipe.slug)
