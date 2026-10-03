from functools import cached_property

from fastapi import File, Form, HTTPException, status
from pydantic import UUID4

from mealie.core import exceptions
from mealie.routes._base import BaseUserController, controller
from mealie.routes._base.routers import MealieCrudRoute, UserAPIRouter
from mealie.schema.recipe.recipe_gallery import RecipeGalleryImageOut, RecipeGalleryImageUpdate, RecipeGalleryOrder
from mealie.schema.recipe.request_helpers import UpdateImageResponse
from mealie.schema.response import ErrorResponse
from mealie.services.recipe.recipe_gallery_service import InvalidGalleryImage, RecipeGalleryService
from mealie.services.recipe.recipe_service import RecipeService

router = UserAPIRouter(route_class=MealieCrudRoute)


@controller(router)
class RecipeGalleryController(BaseUserController):
    @cached_property
    def service(self) -> RecipeGalleryService:
        recipe_service = RecipeService(self.repos, self.user, self.household, translator=self.translator)
        return RecipeGalleryService(self.repos, recipe_service)

    def handle_exceptions(self, ex: Exception) -> None:
        if isinstance(ex, exceptions.PermissionDenied):
            raise HTTPException(status.HTTP_403_FORBIDDEN, ErrorResponse.respond(message="Permission Denied"))
        if isinstance(ex, exceptions.NoEntryFound):
            raise HTTPException(status.HTTP_404_NOT_FOUND, ErrorResponse.respond(message="No Entry Found"))
        if isinstance(ex, InvalidGalleryImage):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, ErrorResponse.respond(message=str(ex)))
        raise ex

    @router.get("/{slug}/gallery", response_model=list[RecipeGalleryImageOut])
    def get_all(self, slug: str):
        try:
            return self.service.list_images(slug)
        except Exception as e:
            self.handle_exceptions(e)

    @router.post("/{slug}/gallery", response_model=RecipeGalleryImageOut, status_code=status.HTTP_201_CREATED)
    def create_one(
        self,
        slug: str,
        image: bytes = File(...),
        extension: str = Form(...),
        caption: str | None = Form(None),
    ):
        try:
            return self.service.add(slug, image, extension, caption)
        except Exception as e:
            self.handle_exceptions(e)

    @router.put("/{slug}/gallery/order", response_model=list[RecipeGalleryImageOut])
    def reorder(self, slug: str, data: RecipeGalleryOrder):
        try:
            return self.service.reorder(slug, data.image_ids)
        except Exception as e:
            self.handle_exceptions(e)

    @router.patch("/{slug}/gallery/{image_id}", response_model=RecipeGalleryImageOut)
    def update_one(self, slug: str, image_id: UUID4, data: RecipeGalleryImageUpdate):
        try:
            return self.service.update_caption(slug, image_id, data.caption)
        except Exception as e:
            self.handle_exceptions(e)

    @router.delete("/{slug}/gallery/{image_id}", response_model=RecipeGalleryImageOut)
    def delete_one(self, slug: str, image_id: UUID4):
        try:
            return self.service.delete(slug, image_id)
        except Exception as e:
            self.handle_exceptions(e)

    @router.post("/{slug}/gallery/{image_id}/set-cover", response_model=UpdateImageResponse)
    def set_as_cover(self, slug: str, image_id: UUID4):
        try:
            return UpdateImageResponse(image=self.service.set_as_cover(slug, image_id))
        except Exception as e:
            self.handle_exceptions(e)
