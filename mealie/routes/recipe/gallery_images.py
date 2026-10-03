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

router = UserAPIRouter()


@controller(router)
class RecipeGalleryController(BaseUserController):
    @cached_property
    def service(self) -> RecipeGalleryService:
        recipe_service = RecipeService(self.repos, self.user, self.household, translator=self.translator)
        return RecipeGalleryService(self.repos, recipe_service)

    def handle_exceptions(self, ex: Exception) -> None:
        if isinstance(ex, exceptions.PermissionDenied):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=ErrorResponse.respond(message="Permission Denied"))
        if isinstance(ex, exceptions.NoEntryFound):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=ErrorResponse.respond(message="No Entry Found"))
        if isinstance(ex, GalleryImageError):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=ErrorResponse.respond(message=str(ex)))

        self.logger.exception(ex)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail=ErrorResponse.respond(message=self.t("generic.server-error"))
        )

    def _get_recipe(self, slug: str) -> Recipe:
        try:
            return self.service.get_recipe(slug)
        except Exception as e:
            self.handle_exceptions(e)
            raise

    @router.get("/{slug}/gallery", response_model=list[RecipeGalleryImageOut])
    def get_gallery(self, slug: str):
        return self.service.list(self._get_recipe(slug))

    @router.post("/{slug}/gallery", response_model=RecipeGalleryImageOut, status_code=201)
    def add_gallery_image(
        self,
        slug: str,
        image: bytes = File(...),
        extension: str = Form(...),
        caption: str | None = Form(None),
    ):
        recipe = self._get_recipe(slug)
        try:
            return self.service.add(recipe, image, extension, caption)
        except Exception as e:
            self.handle_exceptions(e)

    @router.put("/{slug}/gallery/order", response_model=list[RecipeGalleryImageOut])
    def reorder_gallery(self, slug: str, data: RecipeGalleryOrder):
        recipe = self._get_recipe(slug)
        try:
            return self.service.reorder(recipe, data.image_ids)
        except Exception as e:
            self.handle_exceptions(e)

    @router.patch("/{slug}/gallery/{image_id}", response_model=RecipeGalleryImageOut)
    def update_gallery_image(self, slug: str, image_id: UUID4, data: RecipeGalleryImageUpdate):
        recipe = self._get_recipe(slug)
        try:
            return self.service.update_caption(recipe, image_id, data.caption)
        except Exception as e:
            self.handle_exceptions(e)

    @router.delete("/{slug}/gallery/{image_id}", response_model=RecipeGalleryImageOut)
    def delete_gallery_image(self, slug: str, image_id: UUID4):
        recipe = self._get_recipe(slug)
        try:
            return self.service.delete(recipe, image_id)
        except Exception as e:
            self.handle_exceptions(e)

    @router.post("/{slug}/gallery/{image_id}/set-cover", response_model=UpdateImageResponse)
    def set_gallery_image_as_cover(self, slug: str, image_id: UUID4):
        recipe = self._get_recipe(slug)
        try:
            return UpdateImageResponse(image=self.service.set_as_cover(recipe, image_id))
        except Exception as e:
            self.handle_exceptions(e)
