import shutil

from pydantic import UUID4

from mealie.core import exceptions
from mealie.pkgs import cache
from mealie.pkgs.img.minify import IMAGE_EXTENSIONS
from mealie.repos.repository_factory import AllRepositories
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_gallery import RecipeGalleryImageOut, RecipeGalleryImageSave
from mealie.services._base_service import BaseService
from mealie.services.recipe.recipe_data_service import RecipeDataService
from mealie.services.recipe.recipe_service import RecipeService

GALLERY_MAX_IMAGES = 30
GALLERY_MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class InvalidGalleryImage(Exception):
    pass


class RecipeGalleryService(BaseService):
    def __init__(self, repos: AllRepositories, recipe_service: RecipeService) -> None:
        self.repos = repos
        self.recipe_service = recipe_service
        super().__init__()

    def _get_editable_recipe(self, slug: str) -> Recipe:
        recipe = self.recipe_service.get_one(slug)
        if not self.recipe_service.can_update([recipe.slug]):
            raise exceptions.PermissionDenied("You do not have permission to edit this recipe.")
        return recipe

    def _images(self, recipe: Recipe) -> list[RecipeGalleryImageOut]:
        images = self.repos.recipe_gallery_images.multi_query({"recipe_id": recipe.id})
        return sorted(images, key=lambda image: image.position)

    def _get_image(self, recipe: Recipe, image_id: UUID4) -> RecipeGalleryImageOut:
        image = self.repos.recipe_gallery_images.get_one(image_id)
        if not image or image.recipe_id != recipe.id:
            raise exceptions.NoEntryFound("Gallery image not found.")
        return image

    def _renumber(self, images: list[RecipeGalleryImageOut]) -> list[RecipeGalleryImageOut]:
        """Saves each image's position as its index in `images`"""
        for position, image in enumerate(images):
            if image.position != position:
                images[position] = self.repos.recipe_gallery_images.patch(image.id, {"position": position})
        return images

    def list_images(self, slug: str) -> list[RecipeGalleryImageOut]:
        return self._images(self.recipe_service.get_one(slug))

    def add(self, slug: str, data: bytes, extension: str, caption: str | None = None) -> RecipeGalleryImageOut:
        recipe = self._get_editable_recipe(slug)

        extension = extension.lower().lstrip(".")
        if f".{extension}" not in IMAGE_EXTENSIONS:
            raise InvalidGalleryImage(f"Unsupported image type: {extension}")
        if len(data) > GALLERY_MAX_UPLOAD_BYTES:
            raise InvalidGalleryImage(f"Images can be at most {GALLERY_MAX_UPLOAD_BYTES // (1024 * 1024)} MB")

        existing = self._images(recipe)
        if len(existing) >= GALLERY_MAX_IMAGES:
            raise InvalidGalleryImage(f"A recipe can have at most {GALLERY_MAX_IMAGES} gallery images")

        new_image = RecipeGalleryImageSave(
            recipe_id=recipe.id, group_id=recipe.group_id, position=len(existing), caption=caption
        )
        image = self.repos.recipe_gallery_images.create(new_image)

        try:
            RecipeDataService(recipe.id, logger=self.logger).write_image(data, extension, image.image_dir)
        except Exception as e:
            shutil.rmtree(image.image_dir, ignore_errors=True)
            self.repos.recipe_gallery_images.delete(image.id)
            raise InvalidGalleryImage("The file could not be read as an image") from e

        return image

    def update_caption(self, slug: str, image_id: UUID4, caption: str | None) -> RecipeGalleryImageOut:
        recipe = self._get_editable_recipe(slug)
        image = self._get_image(recipe, image_id)
        return self.repos.recipe_gallery_images.patch(image.id, {"caption": caption})

    def reorder(self, slug: str, image_ids: list[UUID4]) -> list[RecipeGalleryImageOut]:
        recipe = self._get_editable_recipe(slug)
        images = {image.id: image for image in self._images(recipe)}

        if len(image_ids) != len(set(image_ids)) or set(image_ids) != set(images):
            raise InvalidGalleryImage("The new order must list every gallery image of the recipe exactly once")

        return self._renumber([images[image_id] for image_id in image_ids])

    def delete(self, slug: str, image_id: UUID4) -> RecipeGalleryImageOut:
        recipe = self._get_editable_recipe(slug)
        image = self._get_image(recipe, image_id)

        self.repos.recipe_gallery_images.delete(image.id)
        shutil.rmtree(image.image_dir, ignore_errors=True)

        self._renumber(self._images(recipe))
        return image

    def set_as_cover(self, slug: str, image_id: UUID4) -> str:
        """Copies a gallery image to the recipe's cover image; the gallery image stays in the gallery"""
        recipe = self._get_editable_recipe(slug)
        image = self._get_image(recipe, image_id)

        source = image.image_dir.joinpath("original.webp")
        if not source.is_file():
            raise exceptions.NoEntryFound("Gallery image file not found.")

        RecipeDataService(recipe.id, logger=self.logger).write_image(source, "webp")

        recipe.image = cache.cache_key.new_key()
        self.recipe_service.update_one(recipe.slug, recipe)
        return recipe.image
