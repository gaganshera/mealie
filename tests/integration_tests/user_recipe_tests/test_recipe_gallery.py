import io
from pathlib import Path

import pillow_heif
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mealie.schema.recipe.recipe import Recipe
from mealie.services.recipe.recipe_gallery_service import MAX_IMAGES_PER_RECIPE
from tests import data
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

SIZES = ["original.webp", "min-original.webp", "tiny-original.webp"]


def heic_bytes() -> bytes:
    pillow_heif.register_heif_opener()
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), "red").save(buffer, format="HEIF")
    return buffer.getvalue()


def create_recipe(api_client: TestClient, user: TestUser) -> dict:
    response = api_client.post(api_routes.recipes, json={"name": random_string()}, headers=user.token)
    assert response.status_code == 201
    response = api_client.get(api_routes.recipes_slug(response.json()), headers=user.token)
    return response.json()


def upload(api_client: TestClient, user: TestUser, slug: str, content: bytes, extension: str, caption=None):
    form = {"extension": extension} | ({"caption": caption} if caption else {})
    return api_client.post(
        api_routes.recipes_slug_gallery(slug), data=form, files={"image": content}, headers=user.token
    )


def upload_ok(api_client: TestClient, user: TestUser, slug: str, caption=None) -> dict:
    response = upload(api_client, user, slug, data.images_test_image_1.read_bytes(), "jpg", caption)
    assert response.status_code == 201
    return response.json()


def gallery(api_client: TestClient, user: TestUser, slug: str) -> list[dict]:
    response = api_client.get(api_routes.recipes_slug_gallery(slug), headers=user.token)
    assert response.status_code == 200
    return response.json()


def gallery_dir(recipe_id: str, image_id: str) -> Path:
    return Recipe.directory_from_id(recipe_id).joinpath("images", "gallery", image_id)


@pytest.fixture
def recipe(api_client: TestClient, unique_user: TestUser):
    recipe = create_recipe(api_client, unique_user)
    yield recipe
    api_client.delete(api_routes.recipes_slug(recipe["slug"]), headers=unique_user.token)


@pytest.mark.parametrize(
    "content, extension",
    [
        (data.images_test_image_1.read_bytes(), "jpg"),
        (data.images_test_image_2.read_bytes(), "png"),
        (heic_bytes(), "heic"),
    ],
    ids=["jpeg", "png", "heic"],
)
def test_gallery_upload_creates_all_sizes(
    api_client: TestClient, unique_user: TestUser, recipe: dict, content: bytes, extension: str
):
    response = upload(api_client, unique_user, recipe["slug"], content, extension, caption="card")
    assert response.status_code == 201
    image = response.json()
    assert image["caption"] == "card"
    assert image["position"] == 0

    image_dir = gallery_dir(recipe["id"], image["id"])
    assert sorted(p.name for p in image_dir.iterdir()) == sorted(SIZES)

    for size in SIZES:
        route = api_routes.media_recipes_recipe_id_images_gallery_image_id_file_name(recipe["id"], image["id"], size)
        response = api_client.get(route)
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/webp"


def test_gallery_rejects_bad_uploads(api_client: TestClient, unique_user: TestUser, recipe: dict):
    response = upload(api_client, unique_user, recipe["slug"], b"not an image", "jpg")
    assert response.status_code == 400
    response = upload(api_client, unique_user, recipe["slug"], b"%PDF-1.4", "pdf")
    assert response.status_code == 400
    assert gallery(api_client, unique_user, recipe["slug"]) == []
    assert not Recipe.directory_from_id(recipe["id"]).joinpath("images", "gallery").exists() or not any(
        Recipe.directory_from_id(recipe["id"]).joinpath("images", "gallery").iterdir()
    )


def test_gallery_image_limit(api_client: TestClient, unique_user: TestUser, recipe: dict):
    tiny = io.BytesIO()
    Image.new("RGB", (8, 8)).save(tiny, format="PNG")
    for _ in range(MAX_IMAGES_PER_RECIPE):
        assert upload(api_client, unique_user, recipe["slug"], tiny.getvalue(), "png").status_code == 201

    response = upload(api_client, unique_user, recipe["slug"], tiny.getvalue(), "png")
    assert response.status_code == 400
    assert len(gallery(api_client, unique_user, recipe["slug"])) == MAX_IMAGES_PER_RECIPE


def test_gallery_order(api_client: TestClient, unique_user: TestUser, recipe: dict):
    slug = recipe["slug"]
    ids = [upload_ok(api_client, unique_user, slug)["id"] for _ in range(3)]
    assert [image["id"] for image in gallery(api_client, unique_user, slug)] == ids
    assert [image["position"] for image in gallery(api_client, unique_user, slug)] == [0, 1, 2]

    new_order = [ids[2], ids[0], ids[1]]
    response = api_client.put(
        api_routes.recipes_slug_gallery_order(slug), json={"ids": new_order}, headers=unique_user.token
    )
    assert response.status_code == 200
    assert [image["id"] for image in gallery(api_client, unique_user, slug)] == new_order

    for bad_order in [ids[:2], [*ids, ids[0]], [ids[0], ids[0], ids[1]], [*ids[:2], recipe["id"]]]:
        response = api_client.put(
            api_routes.recipes_slug_gallery_order(slug), json={"ids": bad_order}, headers=unique_user.token
        )
        assert response.status_code == 400
    assert [image["id"] for image in gallery(api_client, unique_user, slug)] == new_order


def test_gallery_caption_and_delete(api_client: TestClient, unique_user: TestUser, recipe: dict):
    slug = recipe["slug"]
    ids = [upload_ok(api_client, unique_user, slug)["id"] for _ in range(3)]

    response = api_client.patch(
        api_routes.recipes_slug_gallery_image_id(slug, ids[0]),
        json={"caption": "Grandma's card"},
        headers=unique_user.token,
    )
    assert response.status_code == 200
    assert gallery(api_client, unique_user, slug)[0]["caption"] == "Grandma's card"

    response = api_client.delete(api_routes.recipes_slug_gallery_image_id(slug, ids[1]), headers=unique_user.token)
    assert response.status_code == 204
    images = gallery(api_client, unique_user, slug)
    assert [image["id"] for image in images] == [ids[0], ids[2]]
    assert [image["position"] for image in images] == [0, 1]
    assert not gallery_dir(recipe["id"], ids[1]).exists()


def test_gallery_set_as_cover(api_client: TestClient, unique_user: TestUser, recipe: dict):
    slug = recipe["slug"]
    image = upload_ok(api_client, unique_user, slug)
    old_key = recipe["image"]

    response = api_client.post(
        api_routes.recipes_slug_gallery_image_id_set_cover(slug, image["id"]), headers=unique_user.token
    )
    assert response.status_code == 200
    new_key = response.json()["image"]
    assert new_key and new_key != old_key
    assert api_client.get(api_routes.recipes_slug(slug), headers=unique_user.token).json()["image"] == new_key

    cover = Recipe.directory_from_id(recipe["id"]).joinpath("images", "original.webp")
    with Image.open(cover) as cover_img, Image.open(gallery_dir(recipe["id"], image["id"]) / "original.webp") as src:
        assert cover_img.size == src.size

    # the image stays in the gallery
    assert [i["id"] for i in gallery(api_client, unique_user, slug)] == [image["id"]]


def test_gallery_survives_recipe_save(api_client: TestClient, unique_user: TestUser, recipe: dict):
    slug = recipe["slug"]
    image = upload_ok(api_client, unique_user, slug, caption="keep me")

    full = api_client.get(api_routes.recipes_slug(slug), headers=unique_user.token).json()
    full["description"] = "updated"
    response = api_client.put(api_routes.recipes_slug(slug), json=full, headers=unique_user.token)
    assert response.status_code == 200

    images = gallery(api_client, unique_user, slug)
    assert [(i["id"], i["caption"]) for i in images] == [(image["id"], "keep me")]


def test_gallery_removed_with_recipe(api_client: TestClient, unique_user: TestUser):
    recipe = create_recipe(api_client, unique_user)
    image = upload_ok(api_client, unique_user, recipe["slug"])
    recipe_dir = Recipe.directory_from_id(recipe["id"])

    response = api_client.delete(api_routes.recipes_slug(recipe["slug"]), headers=unique_user.token)
    assert response.status_code == 200
    assert unique_user.repos.recipe_gallery_images.get_one(image["id"]) is None
    assert not recipe_dir.exists()


def test_gallery_duplicated_with_recipe(api_client: TestClient, unique_user: TestUser, recipe: dict):
    images = [upload_ok(api_client, unique_user, recipe["slug"], caption=f"c{i}") for i in range(2)]

    response = api_client.post(
        api_routes.recipes_slug_duplicate(recipe["slug"]), json={"name": random_string()}, headers=unique_user.token
    )
    assert response.status_code == 201
    copy = response.json()

    copied = gallery(api_client, unique_user, copy["slug"])
    assert [i["caption"] for i in copied] == ["c0", "c1"]
    assert {i["id"] for i in copied}.isdisjoint({i["id"] for i in images})
    for image in copied:
        assert sorted(p.name for p in gallery_dir(copy["id"], image["id"]).iterdir()) == sorted(SIZES)

    # the original keeps its own rows and folders
    assert [i["id"] for i in gallery(api_client, unique_user, recipe["slug"])] == [i["id"] for i in images]
    for image in images:
        assert gallery_dir(recipe["id"], image["id"]).exists()

    api_client.delete(api_routes.recipes_slug(copy["slug"]), headers=unique_user.token)


def test_gallery_permissions(
    api_client: TestClient, unique_user: TestUser, h2_user: TestUser, g2_user: TestUser, recipe: dict
):
    slug = recipe["slug"]
    image = upload_ok(api_client, unique_user, slug)

    household = unique_user.repos.households.get_one(unique_user.household_id)
    assert household and household.preferences
    household.preferences.lock_recipe_edits_from_other_households = True
    unique_user.repos.household_preferences.update(household.id, household.preferences)

    # another household can view, but not change
    assert len(gallery(api_client, h2_user, slug)) == 1
    image_route = api_routes.recipes_slug_gallery_image_id(slug, image["id"])
    content = data.images_test_image_1.read_bytes()
    assert upload(api_client, h2_user, slug, content, "jpg").status_code == 403
    assert api_client.patch(image_route, json={"caption": "x"}, headers=h2_user.token).status_code == 403
    assert api_client.delete(image_route, headers=h2_user.token).status_code == 403
    order_route = api_routes.recipes_slug_gallery_order(slug)
    assert api_client.put(order_route, json={"ids": [image["id"]]}, headers=h2_user.token).status_code == 403
    cover_route = api_routes.recipes_slug_gallery_image_id_set_cover(slug, image["id"])
    assert api_client.post(cover_route, headers=h2_user.token).status_code == 403

    # another group can't see the recipe at all
    assert api_client.get(api_routes.recipes_slug_gallery(slug), headers=g2_user.token).status_code == 404
    assert upload(api_client, g2_user, slug, content, "jpg").status_code == 404
    assert api_client.delete(image_route, headers=g2_user.token).status_code == 404

    assert len(gallery(api_client, unique_user, slug)) == 1
