import io
from collections.abc import Generator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mealie.core.config import get_app_dirs
from mealie.schema.recipe.recipe import Recipe
from mealie.services.recipe.recipe_gallery_service import MAX_GALLERY_IMAGES
from tests import data
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

IMAGE_SIZES = ["original.webp", "min-original.webp", "tiny-original.webp"]


def heic_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 10, 10)).save(buffer, format="HEIF")
    return buffer.getvalue()


def png_bytes(color: tuple[int, int, int] = (10, 200, 10), size: tuple[int, int] = (40, 40)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def recipe(api_client: TestClient, unique_user: TestUser) -> Generator[Recipe]:
    response = api_client.post(api_routes.recipes, json={"name": random_string()}, headers=unique_user.token)
    assert response.status_code == 201
    recipe = unique_user.repos.recipes.get_one(response.json())
    assert recipe

    yield recipe

    api_client.delete(api_routes.recipes_slug(recipe.slug), headers=unique_user.token)


def upload(
    api_client: TestClient,
    user: TestUser,
    slug: str,
    content: bytes | None = None,
    extension: str = "png",
    caption: str | None = None,
):
    form: dict[str, str] = {"extension": extension}
    if caption is not None:
        form["caption"] = caption

    return api_client.post(
        api_routes.recipes_slug_gallery(slug),
        data=form,
        files={"image": content if content is not None else png_bytes()},
        headers=user.token,
    )


def get_gallery(api_client: TestClient, user: TestUser, slug: str) -> list[dict]:
    response = api_client.get(api_routes.recipes_slug_gallery(slug), headers=user.token)
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize(
    "content, extension",
    [
        (data.images_test_image_1.read_bytes(), "jpg"),
        (data.images_test_image_2.read_bytes(), "png"),
        (heic_bytes(), "heic"),
    ],
    ids=["jpeg", "png", "heic"],
)
def test_gallery_upload_creates_sizes(
    api_client: TestClient, unique_user: TestUser, recipe: Recipe, content: bytes, extension: str
):
    response = upload(api_client, unique_user, recipe.slug, content, extension, caption="Grandma's card")
    assert response.status_code == 201
    image = response.json()
    assert image["recipeId"] == str(recipe.id)
    assert image["position"] == 0
    assert image["caption"] == "Grandma's card"

    image_dir = Recipe.gallery_image_dir_from_id(recipe.id, image["id"])
    assert sorted(f.name for f in image_dir.iterdir()) == sorted(IMAGE_SIZES)

    for size in IMAGE_SIZES:
        response = api_client.get(
            api_routes.media_recipes_recipe_id_images_gallery_image_id_file_name(recipe.id, image["id"], size)
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/webp"


def test_gallery_rejects_non_images(api_client: TestClient, unique_user: TestUser, recipe: Recipe):
    response = upload(api_client, unique_user, recipe.slug, b"not an image at all", "png")
    assert response.status_code == 400

    response = upload(api_client, unique_user, recipe.slug, b"%PDF-1.4", "pdf")
    assert response.status_code == 400

    assert get_gallery(api_client, unique_user, recipe.slug) == []
    gallery_dir = Recipe.image_dir_from_id(recipe.id).joinpath("gallery")
    assert not gallery_dir.exists() or not any(gallery_dir.iterdir())


def test_gallery_limit(api_client: TestClient, unique_user: TestUser, recipe: Recipe):
    content = png_bytes(size=(8, 8))
    for _ in range(MAX_GALLERY_IMAGES):
        assert upload(api_client, unique_user, recipe.slug, content).status_code == 201

    response = upload(api_client, unique_user, recipe.slug, content)
    assert response.status_code == 400
    assert len(get_gallery(api_client, unique_user, recipe.slug)) == MAX_GALLERY_IMAGES


def test_gallery_order_and_reorder(api_client: TestClient, unique_user: TestUser, recipe: Recipe):
    ids = [upload(api_client, unique_user, recipe.slug).json()["id"] for _ in range(3)]

    gallery = get_gallery(api_client, unique_user, recipe.slug)
    assert [image["id"] for image in gallery] == ids
    assert [image["position"] for image in gallery] == [0, 1, 2]

    new_order = [ids[2], ids[0], ids[1]]
    response = api_client.put(
        api_routes.recipes_slug_gallery_order(recipe.slug), json={"ids": new_order}, headers=unique_user.token
    )
    assert response.status_code == 200
    assert [image["id"] for image in response.json()] == new_order

    gallery = get_gallery(api_client, unique_user, recipe.slug)
    assert [image["id"] for image in gallery] == new_order
    assert [image["position"] for image in gallery] == [0, 1, 2]


@pytest.mark.parametrize(
    "make_order",
    [
        lambda ids: ids[:2],  # missing one
        lambda ids: [*ids, ids[0]],  # duplicate
        lambda ids: [ids[0], ids[1], "4d2c4b1c-3d6a-4f61-9a43-61d0b0f2b5a1"],  # unknown id
    ],
    ids=["missing", "duplicate", "unknown"],
)
def test_gallery_reorder_rejects_mismatched_ids(
    api_client: TestClient, unique_user: TestUser, recipe: Recipe, make_order
):
    ids = [upload(api_client, unique_user, recipe.slug).json()["id"] for _ in range(3)]

    response = api_client.put(
        api_routes.recipes_slug_gallery_order(recipe.slug), json={"ids": make_order(ids)}, headers=unique_user.token
    )
    assert response.status_code == 400
    assert [image["id"] for image in get_gallery(api_client, unique_user, recipe.slug)] == ids


def test_gallery_caption_update(api_client: TestClient, unique_user: TestUser, recipe: Recipe):
    image_id = upload(api_client, unique_user, recipe.slug).json()["id"]

    response = api_client.patch(
        api_routes.recipes_slug_gallery_image_id(recipe.slug, image_id),
        json={"caption": "The finished dish"},
        headers=unique_user.token,
    )
    assert response.status_code == 200
    assert response.json()["caption"] == "The finished dish"
    assert get_gallery(api_client, unique_user, recipe.slug)[0]["caption"] == "The finished dish"


def test_gallery_delete_closes_gap(api_client: TestClient, unique_user: TestUser, recipe: Recipe):
    ids = [upload(api_client, unique_user, recipe.slug).json()["id"] for _ in range(3)]
    image_dir = Recipe.gallery_image_dir_from_id(recipe.id, ids[1])
    assert image_dir.exists()

    response = api_client.delete(
        api_routes.recipes_slug_gallery_image_id(recipe.slug, ids[1]), headers=unique_user.token
    )
    assert response.status_code == 200
    assert not image_dir.exists()

    gallery = get_gallery(api_client, unique_user, recipe.slug)
    assert [image["id"] for image in gallery] == [ids[0], ids[2]]
    assert [image["position"] for image in gallery] == [0, 1]


def test_gallery_set_as_cover(api_client: TestClient, unique_user: TestUser, recipe: Recipe):
    image_id = upload(api_client, unique_user, recipe.slug, png_bytes((1, 2, 250), (120, 80))).json()["id"]
    old_image_key = recipe.image

    response = api_client.post(
        api_routes.recipes_slug_gallery_image_id_set_cover(recipe.slug, image_id), headers=unique_user.token
    )
    assert response.status_code == 200
    new_image_key = response.json()["image"]
    assert new_image_key and new_image_key != old_image_key

    updated = api_client.get(api_routes.recipes_slug(recipe.slug), headers=unique_user.token).json()
    assert updated["image"] == new_image_key

    cover = Recipe.image_dir_from_id(recipe.id).joinpath("original.webp")
    gallery_original = Recipe.gallery_image_dir_from_id(recipe.id, image_id).joinpath("original.webp")
    with Image.open(cover) as cover_img, Image.open(gallery_original) as gallery_img:
        assert cover_img.size == gallery_img.size == (120, 80)
        assert cover_img.convert("RGB").getpixel((60, 40)) == pytest.approx(
            gallery_img.convert("RGB").getpixel((60, 40)), abs=8
        )

    # the image stays in the gallery
    assert [image["id"] for image in get_gallery(api_client, unique_user, recipe.slug)] == [image_id]


def test_gallery_survives_recipe_update(api_client: TestClient, unique_user: TestUser, recipe: Recipe):
    ids = [upload(api_client, unique_user, recipe.slug).json()["id"] for _ in range(2)]

    recipe_json = api_client.get(api_routes.recipes_slug(recipe.slug), headers=unique_user.token).json()
    recipe_json["description"] = random_string()
    response = api_client.put(api_routes.recipes_slug(recipe.slug), json=recipe_json, headers=unique_user.token)
    assert response.status_code == 200

    assert [image["id"] for image in get_gallery(api_client, unique_user, recipe.slug)] == ids


def test_gallery_removed_with_recipe(api_client: TestClient, unique_user: TestUser):
    response = api_client.post(api_routes.recipes, json={"name": random_string()}, headers=unique_user.token)
    recipe = unique_user.repos.recipes.get_one(response.json())
    assert recipe
    image_id = upload(api_client, unique_user, recipe.slug).json()["id"]

    response = api_client.delete(api_routes.recipes_slug(recipe.slug), headers=unique_user.token)
    assert response.status_code == 200

    assert unique_user.repos.recipe_gallery_images.get_one(UUID(image_id)) is None
    # not Recipe.directory_from_id, which would create the folder again
    assert not get_app_dirs().RECIPE_DATA_DIR.joinpath(str(recipe.id)).exists()


def test_gallery_duplicated_with_recipe(api_client: TestClient, unique_user: TestUser, recipe: Recipe):
    ids = [upload(api_client, unique_user, recipe.slug, caption=f"Photo {i}").json()["id"] for i in range(2)]

    response = api_client.post(
        api_routes.recipes_slug_duplicate(recipe.slug), json={"name": random_string()}, headers=unique_user.token
    )
    assert response.status_code == 201
    copy = response.json()

    try:
        copy_gallery = get_gallery(api_client, unique_user, copy["slug"])
        assert len(copy_gallery) == 2
        assert [image["caption"] for image in copy_gallery] == ["Photo 0", "Photo 1"]
        assert not {image["id"] for image in copy_gallery} & set(ids)

        for image in copy_gallery:
            image_dir = Recipe.image_dir_from_id(copy["id"]).joinpath("gallery", image["id"])
            assert sorted(f.name for f in image_dir.iterdir()) == sorted(IMAGE_SIZES)
        for old_id in ids:
            assert not Recipe.image_dir_from_id(copy["id"]).joinpath("gallery", old_id).exists()

        # the original keeps its own gallery
        assert [image["id"] for image in get_gallery(api_client, unique_user, recipe.slug)] == ids
    finally:
        api_client.delete(api_routes.recipes_slug(copy["slug"]), headers=unique_user.token)


def test_gallery_permissions_other_household(
    api_client: TestClient, unique_user: TestUser, h2_user: TestUser, recipe: Recipe
):
    image_id = upload(api_client, unique_user, recipe.slug).json()["id"]

    household = unique_user.repos.households.get_one(unique_user.household_id)
    assert household and household.preferences
    original_lock = household.preferences.lock_recipe_edits_from_other_households
    household.preferences.lock_recipe_edits_from_other_households = True
    unique_user.repos.household_preferences.update(household.id, household.preferences)

    try:
        # viewing is still allowed
        assert [image["id"] for image in get_gallery(api_client, h2_user, recipe.slug)] == [image_id]

        assert upload(api_client, h2_user, recipe.slug).status_code == 403
        response = api_client.patch(
            api_routes.recipes_slug_gallery_image_id(recipe.slug, image_id),
            json={"caption": "nope"},
            headers=h2_user.token,
        )
        assert response.status_code == 403
        response = api_client.put(
            api_routes.recipes_slug_gallery_order(recipe.slug), json={"ids": [image_id]}, headers=h2_user.token
        )
        assert response.status_code == 403
        response = api_client.post(
            api_routes.recipes_slug_gallery_image_id_set_cover(recipe.slug, image_id), headers=h2_user.token
        )
        assert response.status_code == 403
        response = api_client.delete(
            api_routes.recipes_slug_gallery_image_id(recipe.slug, image_id), headers=h2_user.token
        )
        assert response.status_code == 403
    finally:
        household.preferences.lock_recipe_edits_from_other_households = original_lock
        unique_user.repos.household_preferences.update(household.id, household.preferences)

    assert len(get_gallery(api_client, unique_user, recipe.slug)) == 1


def test_gallery_other_group_not_found(
    api_client: TestClient, unique_user: TestUser, g2_user: TestUser, recipe: Recipe
):
    image_id = upload(api_client, unique_user, recipe.slug).json()["id"]

    assert api_client.get(api_routes.recipes_slug_gallery(recipe.slug), headers=g2_user.token).status_code == 404
    assert upload(api_client, g2_user, recipe.slug).status_code == 404
    response = api_client.delete(api_routes.recipes_slug_gallery_image_id(recipe.slug, image_id), headers=g2_user.token)
    assert response.status_code == 404

    # an image id from another recipe is not found either
    other = api_client.post(api_routes.recipes, json={"name": random_string()}, headers=g2_user.token).json()
    try:
        response = api_client.delete(api_routes.recipes_slug_gallery_image_id(other, image_id), headers=g2_user.token)
        assert response.status_code == 404
    finally:
        api_client.delete(api_routes.recipes_slug(other), headers=g2_user.token)

    assert len(get_gallery(api_client, unique_user, recipe.slug)) == 1
