from collections.abc import Callable
from functools import cached_property
from typing import TypeVar

from fastapi import File, Form, HTTPException, UploadFile, status
from pydantic import UUID4

from mealie.core import exceptions
from mealie.routes._base import BaseUserController, controller
from mealie.routes._base.routers import UserAPIRouter
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_gallery import RecipeGalleryImageOut, RecipeGalleryImageUpdate, RecipeGalleryOrder
from mealie.schema.recipe.request_helpers import UpdateImageResponse
from mealie.schema.response import ErrorResponse
from mealie.services.recipe.recipe_gallery_service import MAX_UPLOAD_BYTES, GalleryImageError, RecipeGalleryService
from mealie.services.recipe.recipe_service import RecipeService

router = UserAPIRouter()

T = TypeVar("T")


@controller(router)
class RecipeGalleryController(BaseUserController):
    @cached_property
    def recipe_service(self) -> RecipeService:
        return RecipeService(self.repos, self.user, self.household, translator=self.translator)

    @cached_property
    def service(self) -> RecipeGalleryService:
        return RecipeGalleryService(self.recipe_service)

    def _run(self, action: Callable[[], T]) -> T:
        try:
            return action()
        except exceptions.PermissionDenied as e:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail=ErrorResponse.respond(message="Permission Denied")
            ) from e
        except exceptions.NoEntryFound as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=ErrorResponse.respond(message=str(e))) from e
        except GalleryImageError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=ErrorResponse.respond(message=str(e))) from e

    def _get_recipe(self, slug: str) -> Recipe:
        return self._run(lambda: self.recipe_service.get_one(slug))

    @router.get("/{slug}/gallery", response_model=list[RecipeGalleryImageOut])
    def get_gallery(self, slug: str):
        recipe = self._get_recipe(slug)
        return self.service.list_images(recipe)

    @router.post("/{slug}/gallery", response_model=RecipeGalleryImageOut, status_code=201)
    def add_gallery_image(
        self,
        slug: str,
        image: UploadFile = File(...),
        extension: str = Form(...),
        caption: str | None = Form(None),
    ):
        recipe = self._get_recipe(slug)
        # Read one byte past the limit so oversized uploads are rejected without reading them whole
        data = image.file.read(MAX_UPLOAD_BYTES + 1)
        return self._run(lambda: self.service.add(recipe, data, extension, caption))

    @router.put("/{slug}/gallery/order", response_model=list[RecipeGalleryImageOut])
    def reorder_gallery(self, slug: str, order: RecipeGalleryOrder):
        recipe = self._get_recipe(slug)
        return self._run(lambda: self.service.reorder(recipe, order.ids))

    @router.patch("/{slug}/gallery/{image_id}", response_model=RecipeGalleryImageOut)
    def update_gallery_image(self, slug: str, image_id: UUID4, data: RecipeGalleryImageUpdate):
        recipe = self._get_recipe(slug)
        return self._run(lambda: self.service.update_caption(recipe, image_id, data.caption))

    @router.delete("/{slug}/gallery/{image_id}", response_model=RecipeGalleryImageOut)
    def delete_gallery_image(self, slug: str, image_id: UUID4):
        recipe = self._get_recipe(slug)
        return self._run(lambda: self.service.delete(recipe, image_id))

    @router.post("/{slug}/gallery/{image_id}/set-cover", response_model=UpdateImageResponse)
    def set_gallery_image_as_cover(self, slug: str, image_id: UUID4):
        recipe = self._get_recipe(slug)
        return UpdateImageResponse(image=self._run(lambda: self.service.set_as_cover(recipe, image_id)))
