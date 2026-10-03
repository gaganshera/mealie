from functools import cached_property

from fastapi import File, Form, HTTPException, status
from pydantic import UUID4

from mealie.core import exceptions
from mealie.routes._base import BaseUserController, controller
from mealie.routes._base.routers import UserAPIRouter
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_gallery import RecipeGalleryImageOut, RecipeGalleryImageUpdate, RecipeGalleryOrder
from mealie.schema.recipe.request_helpers import UpdateImageResponse
from mealie.schema.response.responses import ErrorResponse
from mealie.services.recipe.recipe_gallery_service import GalleryImageError, RecipeGalleryService
from mealie.services.recipe.recipe_service import RecipeService

router = UserAPIRouter(prefix="/{slug}/gallery")


@controller(router)
class RecipeGalleryController(BaseUserController):
    @cached_property
    def recipe_service(self) -> RecipeService:
        return RecipeService(self.repos, self.user, self.household, translator=self.translator)

    @cached_property
    def service(self) -> RecipeGalleryService:
        return RecipeGalleryService(self.repos, self.recipe_service)

    def _get_recipe(self, slug: str) -> Recipe:
        try:
            return self.recipe_service.get_one(slug)
        except exceptions.NoEntryFound as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, ErrorResponse.respond(message="No Entry Found")) from e

    def _handle_exceptions(self, ex: Exception):
        if isinstance(ex, exceptions.PermissionDenied):
            raise HTTPException(status.HTTP_403_FORBIDDEN, ErrorResponse.respond(message="Permission Denied")) from ex
        if isinstance(ex, exceptions.NoEntryFound):
            raise HTTPException(status.HTTP_404_NOT_FOUND, ErrorResponse.respond(message="No Entry Found")) from ex
        if isinstance(ex, GalleryImageError):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, ErrorResponse.respond(message=str(ex))) from ex
        raise ex

    @router.get("", response_model=list[RecipeGalleryImageOut])
    def get_all(self, slug: str):
        return self.service.list(self._get_recipe(slug))

    @router.post("", response_model=RecipeGalleryImageOut, status_code=status.HTTP_201_CREATED)
    def create_one(
        self,
        slug: str,
        image: bytes = File(...),
        extension: str = Form(...),
        caption: str | None = Form(None),
    ):
        recipe = self._get_recipe(slug)
        try:
            return self.service.add(recipe, image, extension, caption or None)
        except Exception as e:
            self._handle_exceptions(e)

    @router.put("/order", response_model=list[RecipeGalleryImageOut])
    def update_order(self, slug: str, data: RecipeGalleryOrder):
        recipe = self._get_recipe(slug)
        try:
            return self.service.reorder(recipe, data.image_ids)
        except Exception as e:
            self._handle_exceptions(e)

    @router.patch("/{image_id}", response_model=RecipeGalleryImageOut)
    def update_one(self, slug: str, image_id: UUID4, data: RecipeGalleryImageUpdate):
        recipe = self._get_recipe(slug)
        try:
            return self.service.update_caption(recipe, image_id, data.caption)
        except Exception as e:
            self._handle_exceptions(e)

    @router.delete("/{image_id}", response_model=RecipeGalleryImageOut)
    def delete_one(self, slug: str, image_id: UUID4):
        recipe = self._get_recipe(slug)
        try:
            return self.service.delete(recipe, image_id)
        except Exception as e:
            self._handle_exceptions(e)

    @router.post("/{image_id}/set-cover", response_model=UpdateImageResponse)
    def set_cover(self, slug: str, image_id: UUID4):
        recipe = self._get_recipe(slug)
        try:
            return UpdateImageResponse(image=self.service.set_as_cover(recipe, image_id))
        except Exception as e:
            self._handle_exceptions(e)
