from collections.abc import Callable
from functools import cached_property

from fastapi import File, Form, HTTPException, status
from pydantic import UUID4

from mealie.core import exceptions
from mealie.routes._base import BaseUserController, controller
from mealie.routes._base.routers import UserAPIRouter
from mealie.schema.recipe.recipe_gallery import (
    RecipeGalleryImageCreate,
    RecipeGalleryImageOut,
    RecipeGalleryImageUpdate,
    RecipeGalleryOrder,
)
from mealie.schema.recipe.request_helpers import UpdateImageResponse
from mealie.schema.response.responses import ErrorResponse
from mealie.services.recipe.recipe_gallery_service import InvalidGalleryRequest, RecipeGalleryService
from mealie.services.recipe.recipe_service import RecipeService

router = UserAPIRouter()


@controller(router)
class RecipeGalleryController(BaseUserController):
    @cached_property
    def service(self) -> RecipeGalleryService:
        return RecipeGalleryService(RecipeService(self.repos, self.user, self.household, translator=self.translator))

    def _run[T](self, action: Callable[[], T]) -> T:
        try:
            return action()
        except exceptions.NoEntryFound as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=ErrorResponse.respond(str(e))) from e
        except exceptions.PermissionDenied as e:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=ErrorResponse.respond(str(e))) from e
        except InvalidGalleryRequest as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=ErrorResponse.respond(str(e))) from e

    @router.get("/{slug}/gallery", response_model=list[RecipeGalleryImageOut])
    def get_gallery(self, slug: str):
        return self._run(lambda: self.service.list_images(slug))

    @router.post("/{slug}/gallery", response_model=RecipeGalleryImageOut, status_code=201)
    def add_gallery_image(
        self,
        slug: str,
        image: bytes = File(...),
        extension: str = Form(...),
        caption: str | None = Form(None),
    ):
        create = RecipeGalleryImageCreate(caption=caption)
        return self._run(lambda: self.service.add(slug, image, extension, create))

    @router.put("/{slug}/gallery/order", response_model=list[RecipeGalleryImageOut])
    def reorder_gallery(self, slug: str, data: RecipeGalleryOrder):
        return self._run(lambda: self.service.reorder(slug, data.ids))

    @router.patch("/{slug}/gallery/{image_id}", response_model=RecipeGalleryImageOut)
    def update_gallery_image(self, slug: str, image_id: UUID4, data: RecipeGalleryImageUpdate):
        return self._run(lambda: self.service.update_caption(slug, image_id, data.caption))

    @router.delete("/{slug}/gallery/{image_id}", status_code=204)
    def delete_gallery_image(self, slug: str, image_id: UUID4):
        self._run(lambda: self.service.delete(slug, image_id))

    @router.post("/{slug}/gallery/{image_id}/set-cover", response_model=UpdateImageResponse)
    def set_gallery_image_as_cover(self, slug: str, image_id: UUID4):
        return UpdateImageResponse(image=self._run(lambda: self.service.set_as_cover(slug, image_id)))
