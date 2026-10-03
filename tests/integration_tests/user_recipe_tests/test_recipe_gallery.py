import io
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageChops, ImageStat

from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_gallery import RecipeGalleryImageSave
from mealie.services.recipe import recipe_gallery_service
from mealie.services.recipe.recipe_gallery_service import GALLERY_MAX_IMAGES
from tests import data
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

IMAGE_FILES = ["original.webp", "min-original.webp", "tiny-original.webp"]


def heic_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 10, 10)).save(buffer, format="HEIF")
    return buffer.getvalue()


def upload(
    api_client: TestClient,
    user: TestUser,
    slug: str,
    image: bytes | None = None,
    extension: str = "jpg",
    caption: str | None = None,
):
    form = {"extension": extension}
    if caption is not None:
        form["caption"] = caption
    return api_client.post(
        api_routes.recipes_slug_gallery(slug),
        data=form,
        files={"image": image if image is not None else data.images_test_image_1.read_bytes()},
        headers=user.token,
    )


def upload_ok(api_client: TestClient, user: TestUser, slug: str, **kwargs) -> dict:
    response = upload(api_client, user, slug, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()


def get_gallery(api_client: TestClient, user: TestUser, slug: str) -> list[dict]:
    response = api_client.get(api_routes.recipes_slug_gallery(slug), headers=user.token)
    assert response.status_code == 200
    return response.json()


def gallery_dir(recipe_id: str, image_id: str) -> Path:
    return Recipe.directory_from_id(recipe_id).joinpath("images", "gallery", image_id)


@pytest.fixture
def recipe(api_client: TestClient, unique_user: TestUser) -> Generator[Recipe]:
    response = api_client.post(api_routes.recipes, json={"name": random_string()}, headers=unique_user.token)
    assert response.status_code == 201
    recipe = unique_user.repos.recipes.get_one(response.json())
    assert recipe

    yield recipe

    api_client.delete(api_routes.recipes_slug(recipe.slug), headers=unique_user.token)


@pytest.mark.parametrize(
    "extension, image",
    [
        ("jpg", data.images_test_image_1.read_bytes()),
        ("png", data.images_test_image_2.read_bytes()),
        ("heic", heic_bytes()),
    ],
    ids=["jpg", "png", "heic"],
)
def test_gallery_upload_creates_all_sizes(
    api_client: TestClient, unique_user: TestUser, recipe: Recipe, extension: str, image: bytes
):
    created = upload_ok(api_client, unique_user, recipe.slug, image=image, extension=extension, caption="Card")
    assert created["caption"] == "Card"
    assert created["position"] == 0
    assert created["recipeId"] == str(recipe.id)

    image_dir = gallery_dir(str(recipe.id), created["id"])
    assert sorted(f.name for f in image_dir.iterdir()) == sorted(IMAGE_FILES)

    for file_name in IMAGE_FILES:
        response = api_client.get(
            api_routes.media_recipes_recipe_id_images_gallery_image_id_file_name(recipe.id, created["id"], file_name)
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/webp"


@pytest.mark.parametrize(
    "extension, image",
    [
        ("jpg", b"this is not an image"),
        ("txt", data.images_test_image_1.read_bytes()),
        ("svg", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"),
    ],
    ids=["corrupt-jpg", "txt", "svg"],
)
def test_gallery_upload_rejects_non_images(
    api_client: TestClient, unique_user: TestUser, recipe: Recipe, extension: str, image: bytes
):
    response = upload(api_client, unique_user, recipe.slug, image=image, extension=extension)
    assert response.status_code == 400

    assert get_gallery(api_client, unique_user, recipe.slug) == []
    gallery_root = Recipe.directory_from_id(recipe.id).joinpath("images", "gallery")
    assert not gallery_root.exists() or not any(gallery_root.iterdir())


def test_gallery_upload_size_limit(
    api_client: TestClient, unique_user: TestUser, recipe: Recipe, monkeypatch: pytest.MonkeyPatch
):
    image = data.images_test_image_1.read_bytes()
    monkeypatch.setattr(recipe_gallery_service, "GALLERY_MAX_UPLOAD_BYTES", len(image) - 1)

    response = upload(api_client, unique_user, recipe.slug, image=image)
    assert response.status_code == 400
    assert get_gallery(api_client, unique_user, recipe.slug) == []


def test_gallery_image_count_limit(api_client: TestClient, unique_user: TestUser, recipe: Recipe):
    assert recipe.id
    for position in range(GALLERY_MAX_IMAGES):
        unique_user.repos.recipe_gallery_images.create(
            RecipeGalleryImageSave(recipe_id=recipe.id, group_id=recipe.group_id, position=position)
        )

    response = upload(api_client, unique_user, recipe.slug)
    assert response.status_code == 400
    assert len(get_gallery(api_client, unique_user, recipe.slug)) == GALLERY_MAX_IMAGES


def test_gallery_order(api_client: TestClient, unique_user: TestUser, recipe: Recipe):
    ids = [upload_ok(api_client, unique_user, recipe.slug, caption=str(i))["id"] for i in range(3)]

    gallery = get_gallery(api_client, unique_user, recipe.slug)
    assert [image["id"] for image in gallery] == ids
    assert [image["position"] for image in gallery] == [0, 1, 2]

    new_order = [ids[2], ids[0], ids[1]]
    response = api_client.put(
        api_routes.recipes_slug_gallery_order(recipe.slug), json={"imageIds": new_order}, headers=unique_user.token
    )
    assert response.status_code == 200
    assert [image["id"] for image in response.json()] == new_order

    gallery = get_gallery(api_client, unique_user, recipe.slug)
    assert [image["id"] for image in gallery] == new_order
    assert [image["position"] for image in gallery] == [0, 1, 2]


@pytest.mark.parametrize(
    "make_order",
    [
        pytest.param(lambda ids, other: ids[:2], id="missing"),
        pytest.param(lambda ids, other: [*ids, ids[0]], id="duplicate"),
        pytest.param(lambda ids, other: [*ids[:2], other], id="foreign"),
        pytest.param(lambda ids, other: [], id="empty"),
    ],
)
def test_gallery_order_must_match_exactly(api_client: TestClient, unique_user: TestUser, recipe: Recipe, make_order):
    ids = [upload_ok(api_client, unique_user, recipe.slug)["id"] for _ in range(3)]
    other_recipe = unique_user.repos.recipes.create(
        Recipe(user_id=unique_user.user_id, group_id=unique_user.group_id, name=random_string())
    )
    other_id = upload_ok(api_client, unique_user, other_recipe.slug)["id"]

    try:
        response = api_client.put(
            api_routes.recipes_slug_gallery_order(recipe.slug),
            json={"imageIds": make_order(ids, other_id)},
            headers=unique_user.token,
        )
        assert response.status_code == 400
        assert [image["id"] for image in get_gallery(api_client, unique_user, recipe.slug)] == ids
    finally:
        api_client.delete(api_routes.recipes_slug(other_recipe.slug), headers=unique_user.token)


def test_gallery_update_caption(api_client: TestClient, unique_user: TestUser, recipe: Recipe):
    created = upload_ok(api_client, unique_user, recipe.slug, caption="Before")

    response = api_client.patch(
        api_routes.recipes_slug_gallery_image_id(recipe.slug, created["id"]),
        json={"caption": "Grandma's card, 1962"},
        headers=unique_user.token,
    )
    assert response.status_code == 200
    assert response.json()["caption"] == "Grandma's card, 1962"

    [image] = get_gallery(api_client, unique_user, recipe.slug)
    assert image["caption"] == "Grandma's card, 1962"


def test_gallery_delete(api_client: TestClient, unique_user: TestUser, recipe: Recipe):
    ids = [upload_ok(api_client, unique_user, recipe.slug)["id"] for _ in range(3)]
    assert gallery_dir(str(recipe.id), ids[1]).is_dir()

    response = api_client.delete(
        api_routes.recipes_slug_gallery_image_id(recipe.slug, ids[1]), headers=unique_user.token
    )
    assert response.status_code == 200

    gallery = get_gallery(api_client, unique_user, recipe.slug)
    assert [image["id"] for image in gallery] == [ids[0], ids[2]]
    assert [image["position"] for image in gallery] == [0, 1]
    assert not gallery_dir(str(recipe.id), ids[1]).exists()
    assert unique_user.repos.recipe_gallery_images.get_one(ids[1]) is None

    response = api_client.delete(
        api_routes.recipes_slug_gallery_image_id(recipe.slug, ids[1]), headers=unique_user.token
    )
    assert response.status_code == 404


def test_gallery_set_as_cover(api_client: TestClient, unique_user: TestUser, recipe: Recipe):
    upload_ok(api_client, unique_user, recipe.slug)
    created = upload_ok(
        api_client, unique_user, recipe.slug, image=data.images_test_image_2.read_bytes(), extension="png"
    )
    old_key = recipe.image

    response = api_client.post(
        api_routes.recipes_slug_gallery_image_id_set_cover(recipe.slug, created["id"]), headers=unique_user.token
    )
    assert response.status_code == 200
    new_key = response.json()["image"]
    assert new_key and new_key != old_key

    response = api_client.get(api_routes.recipes_slug(recipe.slug), headers=unique_user.token)
    assert response.json()["image"] == new_key

    # the cover is re-encoded on the way in, so compare the pictures rather than the bytes
    cover = Recipe.directory_from_id(recipe.id).joinpath("images", "original.webp")
    source = gallery_dir(str(recipe.id), created["id"]).joinpath("original.webp")
    with Image.open(cover) as cover_img, Image.open(source) as source_img:
        assert cover_img.size == source_img.size
        diff = ImageChops.difference(cover_img.convert("RGB"), source_img.convert("RGB"))
        assert max(ImageStat.Stat(diff).mean) < 5

    # the image stays in the gallery
    assert [image["id"] for image in get_gallery(api_client, unique_user, recipe.slug)][1] == created["id"]


def test_recipe_update_keeps_gallery(api_client: TestClient, unique_user: TestUser, recipe: Recipe):
    ids = [upload_ok(api_client, unique_user, recipe.slug)["id"] for _ in range(2)]

    recipe_json = api_client.get(api_routes.recipes_slug(recipe.slug), headers=unique_user.token).json()
    recipe_json["description"] = random_string()
    response = api_client.put(api_routes.recipes_slug(recipe.slug), json=recipe_json, headers=unique_user.token)
    assert response.status_code == 200

    assert [image["id"] for image in get_gallery(api_client, unique_user, recipe.slug)] == ids


def test_recipe_delete_removes_gallery(api_client: TestClient, unique_user: TestUser):
    response = api_client.post(api_routes.recipes, json={"name": random_string()}, headers=unique_user.token)
    slug = response.json()
    recipe = unique_user.repos.recipes.get_one(slug)
    assert recipe and recipe.id

    upload_ok(api_client, unique_user, slug)
    upload_ok(api_client, unique_user, slug)
    recipe_dir = Recipe.directory_from_id(recipe.id)

    response = api_client.delete(api_routes.recipes_slug(slug), headers=unique_user.token)
    assert response.status_code == 200

    assert unique_user.repos.recipe_gallery_images.multi_query({"recipe_id": recipe.id}) == []
    assert not recipe_dir.exists()


def test_recipe_duplicate_copies_gallery(api_client: TestClient, unique_user: TestUser, recipe: Recipe):
    originals = [upload_ok(api_client, unique_user, recipe.slug, caption=f"Photo {i}") for i in range(2)]

    response = api_client.post(
        api_routes.recipes_slug_duplicate(recipe.slug), json={"name": random_string()}, headers=unique_user.token
    )
    assert response.status_code == 201
    copy = response.json()

    try:
        copies = get_gallery(api_client, unique_user, copy["slug"])
        assert [image["caption"] for image in copies] == ["Photo 0", "Photo 1"]
        assert [image["position"] for image in copies] == [0, 1]
        assert {image["id"] for image in copies}.isdisjoint({image["id"] for image in originals})

        for image in copies:
            assert image["recipeId"] == copy["id"]
            files = gallery_dir(copy["id"], image["id"]).iterdir()
            assert sorted(f.name for f in files) == sorted(IMAGE_FILES)

        # no folders left over under the original image ids
        copy_gallery = Recipe.directory_from_id(copy["id"]).joinpath("images", "gallery")
        assert {d.name for d in copy_gallery.iterdir()} == {image["id"] for image in copies}

        # the original keeps its own gallery
        assert get_gallery(api_client, unique_user, recipe.slug) == originals
    finally:
        api_client.delete(api_routes.recipes_slug(copy["slug"]), headers=unique_user.token)


def test_gallery_other_household_locked(
    api_client: TestClient, unique_user: TestUser, h2_user: TestUser, recipe: Recipe
):
    image_id = upload_ok(api_client, unique_user, recipe.slug)["id"]

    household = unique_user.repos.households.get_one(unique_user.household_id)
    assert household and household.preferences
    original_lock = household.preferences.lock_recipe_edits_from_other_households
    household.preferences.lock_recipe_edits_from_other_households = True
    unique_user.repos.household_preferences.update(household.id, household.preferences)

    try:
        # viewing is fine
        assert [image["id"] for image in get_gallery(api_client, h2_user, recipe.slug)] == [image_id]

        assert upload(api_client, h2_user, recipe.slug).status_code == 403
        responses = [
            api_client.patch(
                api_routes.recipes_slug_gallery_image_id(recipe.slug, image_id),
                json={"caption": "x"},
                headers=h2_user.token,
            ),
            api_client.put(
                api_routes.recipes_slug_gallery_order(recipe.slug), json={"imageIds": [image_id]}, headers=h2_user.token
            ),
            api_client.delete(api_routes.recipes_slug_gallery_image_id(recipe.slug, image_id), headers=h2_user.token),
            api_client.post(
                api_routes.recipes_slug_gallery_image_id_set_cover(recipe.slug, image_id), headers=h2_user.token
            ),
        ]
        assert [response.status_code for response in responses] == [403, 403, 403, 403]
        assert len(get_gallery(api_client, unique_user, recipe.slug)) == 1
    finally:
        household.preferences.lock_recipe_edits_from_other_households = original_lock
        unique_user.repos.household_preferences.update(household.id, household.preferences)


def test_gallery_other_group(api_client: TestClient, unique_user: TestUser, g2_user: TestUser, recipe: Recipe):
    image_id = upload_ok(api_client, unique_user, recipe.slug)["id"]

    assert api_client.get(api_routes.recipes_slug_gallery(recipe.slug), headers=g2_user.token).status_code == 404
    assert upload(api_client, g2_user, recipe.slug).status_code == 404
    response = api_client.delete(api_routes.recipes_slug_gallery_image_id(recipe.slug, image_id), headers=g2_user.token)
    assert response.status_code == 404
    assert len(get_gallery(api_client, unique_user, recipe.slug)) == 1


def test_gallery_image_of_another_recipe(api_client: TestClient, unique_user: TestUser, recipe: Recipe):
    other_recipe = unique_user.repos.recipes.create(
        Recipe(user_id=unique_user.user_id, group_id=unique_user.group_id, name=random_string())
    )
    other_id = upload_ok(api_client, unique_user, other_recipe.slug)["id"]

    try:
        response = api_client.delete(
            api_routes.recipes_slug_gallery_image_id(recipe.slug, other_id), headers=unique_user.token
        )
        assert response.status_code == 404
        assert len(get_gallery(api_client, unique_user, other_recipe.slug)) == 1
    finally:
        api_client.delete(api_routes.recipes_slug(other_recipe.slug), headers=unique_user.token)
