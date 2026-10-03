import io
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mealie.schema.recipe.recipe import Recipe
from mealie.services.recipe.recipe_gallery_service import MAX_GALLERY_IMAGES
from tests import data
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser

IMAGE_SIZES = ["original.webp", "min-original.webp", "tiny-original.webp"]


def make_image(fmt: str = "PNG", size: tuple[int, int] = (64, 48), color: str = "red") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def create_recipe(api_client: TestClient, user: TestUser) -> dict:
    response = api_client.post(api_routes.recipes, json={"name": random_string()}, headers=user.token)
    assert response.status_code == 201
    response = api_client.get(api_routes.recipes_slug(response.json()), headers=user.token)
    assert response.status_code == 200
    return response.json()


def upload(
    api_client: TestClient,
    user: TestUser,
    slug: str,
    image: bytes | None = None,
    extension: str = "png",
    caption: str | None = None,
):
    form = {"extension": extension}
    if caption is not None:
        form["caption"] = caption

    return api_client.post(
        api_routes.recipes_slug_gallery(slug),
        data=form,
        files={"image": image if image is not None else make_image()},
        headers=user.token,
    )


def list_gallery(api_client: TestClient, user: TestUser, slug: str) -> list[dict]:
    response = api_client.get(api_routes.recipes_slug_gallery(slug), headers=user.token)
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize(
    "image, extension",
    [
        (data.images_test_image_1.read_bytes(), "jpg"),
        (data.images_test_image_2.read_bytes(), "png"),
        (make_image("HEIF"), "heic"),
    ],
    ids=["jpeg", "png", "heic"],
)
def test_gallery_upload_creates_all_sizes(api_client: TestClient, unique_user: TestUser, image: bytes, extension: str):
    recipe = create_recipe(api_client, unique_user)

    response = upload(api_client, unique_user, recipe["slug"], image, extension, caption="Grandma's card")
    assert response.status_code == 201
    created = response.json()
    assert created["recipeId"] == recipe["id"]
    assert created["position"] == 0
    assert created["caption"] == "Grandma's card"

    image_dir = Recipe.gallery_image_dir_from_id(recipe["id"], created["id"])
    assert sorted(p.name for p in image_dir.iterdir()) == sorted(IMAGE_SIZES)

    for file_name in IMAGE_SIZES:
        response = api_client.get(
            api_routes.media_recipes_recipe_id_images_gallery_image_id_file_name(recipe["id"], created["id"], file_name)
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/webp"

    response = api_client.get(
        api_routes.media_recipes_recipe_id_images_gallery_image_id_file_name(recipe["id"], created["id"], "other.webp")
    )
    assert response.status_code == 422


def test_gallery_upload_rejects_non_images(api_client: TestClient, unique_user: TestUser):
    recipe = create_recipe(api_client, unique_user)

    response = upload(api_client, unique_user, recipe["slug"], b"definitely not an image", "png")
    assert response.status_code == 400

    response = upload(api_client, unique_user, recipe["slug"], make_image(), "txt")
    assert response.status_code == 400

    assert list_gallery(api_client, unique_user, recipe["slug"]) == []
    gallery_dir = Recipe.image_dir_from_id(recipe["id"]).joinpath("gallery")
    assert not gallery_dir.exists() or list(gallery_dir.iterdir()) == []


def test_gallery_image_limit(api_client: TestClient, unique_user: TestUser):
    recipe = create_recipe(api_client, unique_user)
    image = make_image(size=(8, 8))

    for _ in range(MAX_GALLERY_IMAGES):
        assert upload(api_client, unique_user, recipe["slug"], image).status_code == 201

    response = upload(api_client, unique_user, recipe["slug"], image)
    assert response.status_code == 400
    assert len(list_gallery(api_client, unique_user, recipe["slug"])) == MAX_GALLERY_IMAGES


def test_gallery_order(api_client: TestClient, unique_user: TestUser):
    recipe = create_recipe(api_client, unique_user)
    ids = [upload(api_client, unique_user, recipe["slug"], caption=str(i)).json()["id"] for i in range(3)]

    gallery = list_gallery(api_client, unique_user, recipe["slug"])
    assert [image["id"] for image in gallery] == ids
    assert [image["position"] for image in gallery] == [0, 1, 2]

    new_order = [ids[2], ids[0], ids[1]]
    response = api_client.put(
        api_routes.recipes_slug_gallery_order(recipe["slug"]), json={"imageIds": new_order}, headers=unique_user.token
    )
    assert response.status_code == 200
    assert [image["id"] for image in response.json()] == new_order

    gallery = list_gallery(api_client, unique_user, recipe["slug"])
    assert [image["id"] for image in gallery] == new_order
    assert [image["position"] for image in gallery] == [0, 1, 2]

    for bad_order in [ids[:2], [*ids, str(uuid4())], [ids[0], ids[0], ids[1]], [ids[0], ids[1], str(uuid4())]]:
        response = api_client.put(
            api_routes.recipes_slug_gallery_order(recipe["slug"]),
            json={"imageIds": bad_order},
            headers=unique_user.token,
        )
        assert response.status_code == 400

    assert [image["id"] for image in list_gallery(api_client, unique_user, recipe["slug"])] == new_order


def test_gallery_caption_and_delete(api_client: TestClient, unique_user: TestUser):
    recipe = create_recipe(api_client, unique_user)
    ids = [upload(api_client, unique_user, recipe["slug"]).json()["id"] for _ in range(3)]

    response = api_client.patch(
        api_routes.recipes_slug_gallery_image_id(recipe["slug"], ids[1]),
        json={"caption": "The finished dish"},
        headers=unique_user.token,
    )
    assert response.status_code == 200
    assert response.json()["caption"] == "The finished dish"
    assert list_gallery(api_client, unique_user, recipe["slug"])[1]["caption"] == "The finished dish"

    deleted_dir = Recipe.gallery_image_dir_from_id(recipe["id"], ids[0])
    response = api_client.delete(
        api_routes.recipes_slug_gallery_image_id(recipe["slug"], ids[0]), headers=unique_user.token
    )
    assert response.status_code == 200
    assert not deleted_dir.exists()

    gallery = list_gallery(api_client, unique_user, recipe["slug"])
    assert [image["id"] for image in gallery] == ids[1:]
    assert [image["position"] for image in gallery] == [0, 1]

    response = api_client.delete(
        api_routes.recipes_slug_gallery_image_id(recipe["slug"], ids[0]), headers=unique_user.token
    )
    assert response.status_code == 404


def test_gallery_image_must_belong_to_recipe(api_client: TestClient, unique_user: TestUser):
    recipe = create_recipe(api_client, unique_user)
    other_recipe = create_recipe(api_client, unique_user)
    image_id = upload(api_client, unique_user, recipe["slug"]).json()["id"]

    response = api_client.delete(
        api_routes.recipes_slug_gallery_image_id(other_recipe["slug"], image_id), headers=unique_user.token
    )
    assert response.status_code == 404
    assert len(list_gallery(api_client, unique_user, recipe["slug"])) == 1


def test_gallery_set_as_cover(api_client: TestClient, unique_user: TestUser):
    recipe = create_recipe(api_client, unique_user)
    upload(api_client, unique_user, recipe["slug"], make_image(size=(40, 40), color="blue"))
    image_id = upload(api_client, unique_user, recipe["slug"], make_image(size=(120, 80), color="green")).json()["id"]

    response = api_client.post(
        api_routes.recipes_slug_gallery_image_id_set_cover(recipe["slug"], image_id), headers=unique_user.token
    )
    assert response.status_code == 200
    new_key = response.json()["image"]
    assert new_key and new_key != recipe["image"]

    response = api_client.get(api_routes.recipes_slug(recipe["slug"]), headers=unique_user.token)
    assert response.json()["image"] == new_key

    cover = Recipe.image_dir_from_id(recipe["id"]).joinpath("original.webp")
    gallery_image = Recipe.gallery_image_dir_from_id(recipe["id"], image_id).joinpath("original.webp")
    with Image.open(cover) as cover_img, Image.open(gallery_image) as gallery_img:
        assert cover_img.size == gallery_img.size == (120, 80)
        assert cover_img.convert("RGB").getpixel((60, 40)) == pytest.approx(
            gallery_img.convert("RGB").getpixel((60, 40)), abs=8
        )

    # the image stays in the gallery
    assert image_id in [image["id"] for image in list_gallery(api_client, unique_user, recipe["slug"])]


def test_gallery_survives_recipe_update(api_client: TestClient, unique_user: TestUser):
    recipe = create_recipe(api_client, unique_user)
    ids = [upload(api_client, unique_user, recipe["slug"]).json()["id"] for _ in range(2)]

    recipe["description"] = random_string()
    response = api_client.put(api_routes.recipes_slug(recipe["slug"]), json=recipe, headers=unique_user.token)
    assert response.status_code == 200

    response = api_client.patch(
        api_routes.recipes_slug(recipe["slug"]), json={"name": recipe["name"]}, headers=unique_user.token
    )
    assert response.status_code == 200

    assert [image["id"] for image in list_gallery(api_client, unique_user, recipe["slug"])] == ids


def test_gallery_deleted_with_recipe(api_client: TestClient, unique_user: TestUser):
    recipe = create_recipe(api_client, unique_user)
    image_id = upload(api_client, unique_user, recipe["slug"]).json()["id"]
    recipe_dir = Recipe.directory_from_id(recipe["id"])
    assert recipe_dir.exists()

    response = api_client.delete(api_routes.recipes_slug(recipe["slug"]), headers=unique_user.token)
    assert response.status_code == 200

    assert not recipe_dir.exists()
    assert unique_user.repos.recipe_gallery_images.get_one(image_id) is None


def test_gallery_duplicated_with_recipe(api_client: TestClient, unique_user: TestUser):
    recipe = create_recipe(api_client, unique_user)
    ids = [upload(api_client, unique_user, recipe["slug"], caption=str(i)).json()["id"] for i in range(2)]

    response = api_client.post(
        api_routes.recipes_slug_duplicate(recipe["slug"]), json={"name": random_string()}, headers=unique_user.token
    )
    assert response.status_code == 201
    duplicate = response.json()

    gallery = list_gallery(api_client, unique_user, duplicate["slug"])
    assert len(gallery) == 2
    assert [image["caption"] for image in gallery] == ["0", "1"]
    assert {image["id"] for image in gallery}.isdisjoint(ids)

    for image in gallery:
        assert image["recipeId"] == duplicate["id"]
        image_dir = Recipe.gallery_image_dir_from_id(duplicate["id"], image["id"])
        assert sorted(p.name for p in image_dir.iterdir()) == sorted(IMAGE_SIZES)

    copied_old_dirs = Recipe.image_dir_from_id(duplicate["id"]).joinpath("gallery")
    assert sorted(p.name for p in copied_old_dirs.iterdir()) == sorted(image["id"] for image in gallery)

    # the original keeps its own gallery
    response = api_client.delete(
        api_routes.recipes_slug_gallery_image_id(duplicate["slug"], gallery[0]["id"]), headers=unique_user.token
    )
    assert response.status_code == 200
    assert [image["id"] for image in list_gallery(api_client, unique_user, recipe["slug"])] == ids
    assert Recipe.gallery_image_dir_from_id(recipe["id"], ids[0]).joinpath("original.webp").exists()


def test_gallery_locked_for_other_households(api_client: TestClient, unique_user: TestUser, h2_user: TestUser):
    household = unique_user.repos.households.get_one(h2_user.household_id)
    assert household and household.preferences
    household.preferences.private_household = False
    household.preferences.lock_recipe_edits_from_other_households = True
    unique_user.repos.household_preferences.update(household.id, household.preferences)

    recipe = create_recipe(api_client, h2_user)
    image_id = upload(api_client, h2_user, recipe["slug"]).json()["id"]

    # other households can still see the gallery
    assert [image["id"] for image in list_gallery(api_client, unique_user, recipe["slug"])] == [image_id]

    slug = recipe["slug"]
    assert upload(api_client, unique_user, slug).status_code == 403
    responses = [
        api_client.patch(
            api_routes.recipes_slug_gallery_image_id(slug, image_id), json={"caption": "x"}, headers=unique_user.token
        ),
        api_client.put(
            api_routes.recipes_slug_gallery_order(slug), json={"imageIds": [image_id]}, headers=unique_user.token
        ),
        api_client.post(api_routes.recipes_slug_gallery_image_id_set_cover(slug, image_id), headers=unique_user.token),
        api_client.delete(api_routes.recipes_slug_gallery_image_id(slug, image_id), headers=unique_user.token),
    ]
    assert [response.status_code for response in responses] == [403] * 4
    assert len(list_gallery(api_client, h2_user, slug)) == 1


def test_gallery_other_group(api_client: TestClient, unique_user: TestUser, g2_user: TestUser):
    recipe = create_recipe(api_client, unique_user)
    image_id = upload(api_client, unique_user, recipe["slug"]).json()["id"]
    slug = recipe["slug"]

    responses = [
        api_client.get(api_routes.recipes_slug_gallery(slug), headers=g2_user.token),
        upload(api_client, g2_user, slug),
        api_client.patch(
            api_routes.recipes_slug_gallery_image_id(slug, image_id), json={"caption": "x"}, headers=g2_user.token
        ),
        api_client.put(
            api_routes.recipes_slug_gallery_order(slug), json={"imageIds": [image_id]}, headers=g2_user.token
        ),
        api_client.post(api_routes.recipes_slug_gallery_image_id_set_cover(slug, image_id), headers=g2_user.token),
        api_client.delete(api_routes.recipes_slug_gallery_image_id(slug, image_id), headers=g2_user.token),
    ]
    assert [response.status_code for response in responses] == [404] * 6
    assert len(list_gallery(api_client, unique_user, slug)) == 1
