import io
from collections.abc import Generator

import pillow_heif
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageChops, ImageStat

from mealie.core.config import get_app_dirs
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_gallery import RecipeGalleryImageOut
from mealie.services.recipe.recipe_gallery_service import MAX_IMAGES_PER_RECIPE
from tests import data
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

pillow_heif.register_heif_opener()

IMAGE_FILES = ["original.webp", "min-original.webp", "tiny-original.webp"]


def make_image(image_format: str, size: tuple[int, int] = (64, 48)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 80, 20)).save(buffer, format=image_format)
    return buffer.getvalue()


def upload(
    api_client: TestClient,
    user: TestUser,
    slug: str,
    image: bytes | None = None,
    extension: str = "png",
    caption: str | None = None,
):
    payload = {"extension": extension}
    if caption is not None:
        payload["caption"] = caption
    return api_client.post(
        api_routes.recipes_slug_gallery(slug),
        data=payload,
        files={"image": image if image is not None else make_image("PNG")},
        headers=user.token,
    )


def get_gallery(api_client: TestClient, user: TestUser, slug: str) -> list[dict]:
    response = api_client.get(api_routes.recipes_slug_gallery(slug), headers=user.token)
    assert response.status_code == 200
    return response.json()


def image_dir(recipe_id, image_id):
    return RecipeGalleryImageOut.image_dir_from_id(recipe_id, image_id)


@pytest.fixture
def lock_edits_from_other_households(unique_user: TestUser) -> Generator[None]:
    household = unique_user.repos.households.get_one(unique_user.household_id)
    assert household and household.preferences
    original = household.preferences.lock_recipe_edits_from_other_households

    household.preferences.lock_recipe_edits_from_other_households = True
    unique_user.repos.household_preferences.update(household.id, household.preferences)
    yield

    household.preferences.lock_recipe_edits_from_other_households = original
    unique_user.repos.household_preferences.update(household.id, household.preferences)


@pytest.mark.parametrize(
    "image, extension",
    [
        (data.images_test_image_1.read_bytes(), "jpg"),
        (data.images_test_image_2.read_bytes(), "png"),
        (make_image("HEIF"), "heic"),
    ],
    ids=["jpeg", "png", "heic"],
)
def test_upload_creates_webp_sizes(
    api_client: TestClient, unique_user: TestUser, recipe_ingredient_only: Recipe, image: bytes, extension: str
):
    recipe = recipe_ingredient_only
    response = upload(api_client, unique_user, recipe.slug, image, extension, caption="Grandma's card")
    assert response.status_code == 201
    gallery_image = response.json()
    assert gallery_image["position"] == 0
    assert gallery_image["caption"] == "Grandma's card"

    assert sorted(p.name for p in image_dir(recipe.id, gallery_image["id"]).iterdir()) == sorted(IMAGE_FILES)

    for file_name in IMAGE_FILES:
        response = api_client.get(
            api_routes.media_recipes_recipe_id_images_gallery_image_id_file_name(
                recipe.id, gallery_image["id"], file_name
            )
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/webp"


def test_upload_rejects_non_images(api_client: TestClient, unique_user: TestUser, recipe_ingredient_only: Recipe):
    recipe = recipe_ingredient_only
    assert upload(api_client, unique_user, recipe.slug, b"not an image", "png").status_code == 400
    assert upload(api_client, unique_user, recipe.slug, b"%PDF-1.4", "pdf").status_code == 400
    assert get_gallery(api_client, unique_user, recipe.slug) == []
    assert not any(Recipe.image_dir_from_id(recipe.id).joinpath("gallery").iterdir())


def test_upload_limit(api_client: TestClient, unique_user: TestUser, recipe_ingredient_only: Recipe):
    recipe = recipe_ingredient_only
    image = make_image("PNG", size=(8, 8))
    for _ in range(MAX_IMAGES_PER_RECIPE):
        assert upload(api_client, unique_user, recipe.slug, image).status_code == 201

    assert upload(api_client, unique_user, recipe.slug, image).status_code == 400
    assert len(get_gallery(api_client, unique_user, recipe.slug)) == MAX_IMAGES_PER_RECIPE


def test_order(api_client: TestClient, unique_user: TestUser, recipe_ingredient_only: Recipe):
    recipe = recipe_ingredient_only
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
    assert [image["id"] for image in get_gallery(api_client, unique_user, recipe.slug)] == new_order

    # the ids must be exactly the recipe's current images
    for bad_order in [ids[:2], [*ids, ids[0]], [ids[0], ids[1], str(recipe.id)]]:
        response = api_client.put(
            api_routes.recipes_slug_gallery_order(recipe.slug), json={"ids": bad_order}, headers=unique_user.token
        )
        assert response.status_code == 400
    assert [image["id"] for image in get_gallery(api_client, unique_user, recipe.slug)] == new_order


def test_caption_and_delete(api_client: TestClient, unique_user: TestUser, recipe_ingredient_only: Recipe):
    recipe = recipe_ingredient_only
    ids = [upload(api_client, unique_user, recipe.slug).json()["id"] for _ in range(3)]

    response = api_client.patch(
        api_routes.recipes_slug_gallery_image_id(recipe.slug, ids[1]),
        json={"caption": "Family recipe card"},
        headers=unique_user.token,
    )
    assert response.status_code == 200
    assert get_gallery(api_client, unique_user, recipe.slug)[1]["caption"] == "Family recipe card"

    response = api_client.delete(
        api_routes.recipes_slug_gallery_image_id(recipe.slug, ids[0]), headers=unique_user.token
    )
    assert response.status_code == 200
    assert not image_dir(recipe.id, ids[0]).joinpath("original.webp").exists()

    gallery = get_gallery(api_client, unique_user, recipe.slug)
    assert [image["id"] for image in gallery] == ids[1:]
    assert [image["position"] for image in gallery] == [0, 1]

    response = api_client.delete(
        api_routes.recipes_slug_gallery_image_id(recipe.slug, ids[0]), headers=unique_user.token
    )
    assert response.status_code == 404


def test_set_as_cover(api_client: TestClient, unique_user: TestUser, recipe_ingredient_only: Recipe):
    recipe = recipe_ingredient_only
    image_id = upload(api_client, unique_user, recipe.slug, data.images_test_image_1.read_bytes(), "jpg").json()["id"]
    old_key = api_client.get(api_routes.recipes_slug(recipe.slug), headers=unique_user.token).json()["image"]

    response = api_client.post(
        api_routes.recipes_slug_gallery_image_id_set_cover(recipe.slug, image_id), headers=unique_user.token
    )
    assert response.status_code == 200
    new_key = response.json()["image"]
    assert new_key and new_key != old_key
    assert api_client.get(api_routes.recipes_slug(recipe.slug), headers=unique_user.token).json()["image"] == new_key

    # write_image re-encodes the copy, so compare the pictures rather than the bytes
    cover_path = Recipe.image_dir_from_id(recipe.id).joinpath("original.webp")
    with Image.open(cover_path) as cover, Image.open(image_dir(recipe.id, image_id) / "original.webp") as source:
        assert cover.size == source.size
        difference = ImageStat.Stat(ImageChops.difference(cover.convert("RGB"), source.convert("RGB"))).mean
        assert max(difference) < 3

    # the image stays in the gallery
    assert [image["id"] for image in get_gallery(api_client, unique_user, recipe.slug)] == [image_id]


def test_saving_recipe_keeps_gallery(api_client: TestClient, unique_user: TestUser, recipe_ingredient_only: Recipe):
    recipe = recipe_ingredient_only
    ids = [upload(api_client, unique_user, recipe.slug).json()["id"] for _ in range(2)]

    recipe_data = api_client.get(api_routes.recipes_slug(recipe.slug), headers=unique_user.token).json()
    recipe_data["description"] = random_string()
    response = api_client.put(api_routes.recipes_slug(recipe.slug), json=recipe_data, headers=unique_user.token)
    assert response.status_code == 200

    assert [image["id"] for image in get_gallery(api_client, unique_user, recipe.slug)] == ids


def test_deleting_recipe_removes_gallery(api_client: TestClient, unique_user: TestUser):
    slug = api_client.post(api_routes.recipes, json={"name": random_string()}, headers=unique_user.token).json()
    recipe_id = api_client.get(api_routes.recipes_slug(slug), headers=unique_user.token).json()["id"]
    image_id = upload(api_client, unique_user, slug).json()["id"]

    response = api_client.delete(api_routes.recipes_slug(slug), headers=unique_user.token)
    assert response.status_code == 200

    assert unique_user.repos.recipe_gallery_images.get_one(image_id) is None
    # Recipe.directory_from_id would create the folder, so build the path directly
    assert not get_app_dirs().RECIPE_DATA_DIR.joinpath(recipe_id).exists()


def test_duplicating_recipe_copies_gallery(
    api_client: TestClient, unique_user: TestUser, recipe_ingredient_only: Recipe
):
    recipe = recipe_ingredient_only
    upload(api_client, unique_user, recipe.slug, caption="first")
    upload(api_client, unique_user, recipe.slug, caption="second")
    original = get_gallery(api_client, unique_user, recipe.slug)

    response = api_client.post(
        api_routes.recipes_slug_duplicate(recipe.slug), json={"name": random_string()}, headers=unique_user.token
    )
    assert response.status_code == 201
    copy = response.json()

    copied = get_gallery(api_client, unique_user, copy["slug"])
    assert [image["caption"] for image in copied] == ["first", "second"]
    assert {image["id"] for image in copied}.isdisjoint(image["id"] for image in original)
    for image in copied:
        assert image["recipeId"] == copy["id"]
        assert image_dir(copy["id"], image["id"]).joinpath("original.webp").is_file()

    # the original gallery is untouched
    assert get_gallery(api_client, unique_user, recipe.slug) == original
    for image in original:
        assert image_dir(recipe.id, image["id"]).joinpath("original.webp").is_file()


def test_other_household_cannot_edit_when_locked(
    api_client: TestClient,
    unique_user: TestUser,
    h2_user: TestUser,
    recipe_ingredient_only: Recipe,
    lock_edits_from_other_households: None,
):
    recipe = recipe_ingredient_only
    image_id = upload(api_client, unique_user, recipe.slug).json()["id"]

    # anyone who can see the recipe can see the gallery
    assert [image["id"] for image in get_gallery(api_client, h2_user, recipe.slug)] == [image_id]

    assert upload(api_client, h2_user, recipe.slug).status_code == 403
    responses = [
        api_client.patch(
            api_routes.recipes_slug_gallery_image_id(recipe.slug, image_id),
            json={"caption": "x"},
            headers=h2_user.token,
        ),
        api_client.put(
            api_routes.recipes_slug_gallery_order(recipe.slug), json={"ids": [image_id]}, headers=h2_user.token
        ),
        api_client.post(
            api_routes.recipes_slug_gallery_image_id_set_cover(recipe.slug, image_id), headers=h2_user.token
        ),
        api_client.delete(api_routes.recipes_slug_gallery_image_id(recipe.slug, image_id), headers=h2_user.token),
    ]
    assert [response.status_code for response in responses] == [403] * 4
    assert get_gallery(api_client, unique_user, recipe.slug)[0]["caption"] is None


def test_other_group_gets_404(
    api_client: TestClient, unique_user: TestUser, g2_user: TestUser, recipe_ingredient_only: Recipe
):
    recipe = recipe_ingredient_only
    image_id = upload(api_client, unique_user, recipe.slug).json()["id"]

    assert api_client.get(api_routes.recipes_slug_gallery(recipe.slug), headers=g2_user.token).status_code == 404
    assert upload(api_client, g2_user, recipe.slug).status_code == 404
    response = api_client.delete(api_routes.recipes_slug_gallery_image_id(recipe.slug, image_id), headers=g2_user.token)
    assert response.status_code == 404
    assert len(get_gallery(api_client, unique_user, recipe.slug)) == 1
