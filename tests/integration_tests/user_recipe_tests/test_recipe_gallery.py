import io
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from mealie.core.config import get_app_dirs
from mealie.schema.recipe.recipe import Recipe
from mealie.schema.recipe.recipe_image_types import RecipeImageTypes
from mealie.services.recipe.recipe_gallery_service import MAX_GALLERY_IMAGES
from tests.utils import api_routes
from tests.utils.factories import random_string
from tests.utils.fixture_schemas import TestUser


def make_image(fmt: str = "PNG", color: tuple[int, int, int] = (200, 30, 30), size=(64, 48)) -> bytes:
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
    data: bytes | None = None,
    extension: str = "png",
    caption: str | None = None,
):
    form = {"extension": extension}
    if caption is not None:
        form["caption"] = caption
    return api_client.post(
        api_routes.recipes_slug_gallery(slug),
        data=form,
        files={"image": data if data is not None else make_image()},
        headers=user.token,
    )


def get_gallery(api_client: TestClient, user: TestUser, slug: str) -> list[dict]:
    response = api_client.get(api_routes.recipes_slug_gallery(slug), headers=user.token)
    assert response.status_code == 200
    return response.json()


def recipe_data_dir(recipe_id: str):
    # Recipe.directory_from_id creates the folder, so build the path by hand when checking that it's gone
    return get_app_dirs().RECIPE_DATA_DIR.joinpath(recipe_id)


@pytest.mark.parametrize("fmt, extension", [("JPEG", "jpg"), ("PNG", "png"), ("HEIF", "heic")])
def test_gallery_upload_creates_all_sizes(api_client: TestClient, unique_user: TestUser, fmt: str, extension: str):
    recipe = create_recipe(api_client, unique_user)

    response = upload(api_client, unique_user, recipe["slug"], make_image(fmt), extension, caption="Grandma's card")
    assert response.status_code == 201
    image = response.json()
    assert image["recipeId"] == recipe["id"]
    assert image["position"] == 0
    assert image["caption"] == "Grandma's card"

    image_dir = Recipe.gallery_image_dir_from_id(recipe["id"], image["id"])
    for image_type in RecipeImageTypes:
        assert image_dir.joinpath(image_type.value).is_file()

        response = api_client.get(
            api_routes.media_recipes_recipe_id_images_gallery_image_id_file_name(
                recipe["id"], image["id"], image_type.value
            )
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/webp"

    # only the WebP sizes are kept
    assert sorted(p.name for p in image_dir.iterdir()) == sorted(t.value for t in RecipeImageTypes)


def test_gallery_media_route_rejects_other_files(api_client: TestClient, unique_user: TestUser):
    recipe = create_recipe(api_client, unique_user)
    image = upload(api_client, unique_user, recipe["slug"]).json()

    route = api_routes.media_recipes_recipe_id_images_gallery_image_id_file_name(recipe["id"], image["id"], "x.png")
    assert api_client.get(route).status_code == 422

    route = api_routes.media_recipes_recipe_id_images_gallery_image_id_file_name(
        recipe["id"], uuid4(), RecipeImageTypes.original.value
    )
    assert api_client.get(route).status_code == 404


@pytest.mark.parametrize("data, extension", [(b"definitely not an image", "jpg"), (make_image(), "txt")])
def test_gallery_upload_rejects_non_images(api_client: TestClient, unique_user: TestUser, data: bytes, extension: str):
    recipe = create_recipe(api_client, unique_user)

    response = upload(api_client, unique_user, recipe["slug"], data, extension)
    assert response.status_code == 400
    assert get_gallery(api_client, unique_user, recipe["slug"]) == []
    gallery_dir = Recipe.image_dir_from_id(recipe["id"]).joinpath("gallery")
    assert not gallery_dir.exists() or list(gallery_dir.iterdir()) == []


def test_gallery_upload_limit(api_client: TestClient, unique_user: TestUser):
    recipe = create_recipe(api_client, unique_user)
    small = make_image(size=(8, 8))
    for _ in range(MAX_GALLERY_IMAGES):
        assert upload(api_client, unique_user, recipe["slug"], small).status_code == 201

    response = upload(api_client, unique_user, recipe["slug"], small)
    assert response.status_code == 400
    assert len(get_gallery(api_client, unique_user, recipe["slug"])) == MAX_GALLERY_IMAGES


def test_gallery_order(api_client: TestClient, unique_user: TestUser):
    recipe = create_recipe(api_client, unique_user)
    slug = recipe["slug"]
    ids = [upload(api_client, unique_user, slug, caption=str(i)).json()["id"] for i in range(3)]

    gallery = get_gallery(api_client, unique_user, slug)
    assert [image["id"] for image in gallery] == ids
    assert [image["position"] for image in gallery] == [0, 1, 2]

    new_order = [ids[2], ids[0], ids[1]]
    response = api_client.put(
        api_routes.recipes_slug_gallery_order(slug), json={"imageIds": new_order}, headers=unique_user.token
    )
    assert response.status_code == 200
    assert [image["id"] for image in response.json()] == new_order

    gallery = get_gallery(api_client, unique_user, slug)
    assert [image["id"] for image in gallery] == new_order
    assert [image["position"] for image in gallery] == [0, 1, 2]

    for bad_order in [ids[:2], [*ids, str(uuid4())], [ids[0], ids[0], ids[1]], [ids[0], ids[1], str(uuid4())]]:
        response = api_client.put(
            api_routes.recipes_slug_gallery_order(slug), json={"imageIds": bad_order}, headers=unique_user.token
        )
        assert response.status_code == 400

    assert [image["id"] for image in get_gallery(api_client, unique_user, slug)] == new_order


def test_gallery_caption_and_delete(api_client: TestClient, unique_user: TestUser):
    recipe = create_recipe(api_client, unique_user)
    slug = recipe["slug"]
    ids = [upload(api_client, unique_user, slug).json()["id"] for _ in range(3)]

    response = api_client.patch(
        api_routes.recipes_slug_gallery_image_id(slug, ids[1]),
        json={"caption": "Finished dish"},
        headers=unique_user.token,
    )
    assert response.status_code == 200
    assert response.json()["caption"] == "Finished dish"
    assert get_gallery(api_client, unique_user, slug)[1]["caption"] == "Finished dish"

    response = api_client.delete(api_routes.recipes_slug_gallery_image_id(slug, ids[0]), headers=unique_user.token)
    assert response.status_code == 200
    assert not recipe_data_dir(recipe["id"]).joinpath("images", "gallery", ids[0]).exists()

    gallery = get_gallery(api_client, unique_user, slug)
    assert [image["id"] for image in gallery] == ids[1:]
    assert [image["position"] for image in gallery] == [0, 1]
    assert gallery[0]["caption"] == "Finished dish"

    response = api_client.delete(api_routes.recipes_slug_gallery_image_id(slug, ids[0]), headers=unique_user.token)
    assert response.status_code == 404


def test_gallery_image_from_another_recipe(api_client: TestClient, unique_user: TestUser):
    recipe = create_recipe(api_client, unique_user)
    other_recipe = create_recipe(api_client, unique_user)
    image = upload(api_client, unique_user, other_recipe["slug"]).json()

    routes = [
        ("patch", api_routes.recipes_slug_gallery_image_id(recipe["slug"], image["id"])),
        ("delete", api_routes.recipes_slug_gallery_image_id(recipe["slug"], image["id"])),
        ("post", api_routes.recipes_slug_gallery_image_id_set_cover(recipe["slug"], image["id"])),
    ]
    for method, route in routes:
        kwargs = {"json": {"caption": "x"}} if method == "patch" else {}
        response = getattr(api_client, method)(route, headers=unique_user.token, **kwargs)
        assert response.status_code == 404

    assert len(get_gallery(api_client, unique_user, other_recipe["slug"])) == 1


def test_gallery_set_as_cover(api_client: TestClient, unique_user: TestUser):
    recipe = create_recipe(api_client, unique_user)
    slug = recipe["slug"]
    image = upload(api_client, unique_user, slug, make_image(color=(10, 200, 40), size=(80, 60))).json()

    response = api_client.post(
        api_routes.recipes_slug_gallery_image_id_set_cover(slug, image["id"]), headers=unique_user.token
    )
    assert response.status_code == 200
    new_key = response.json()["image"]
    assert new_key and new_key != recipe["image"]

    updated = api_client.get(api_routes.recipes_slug(slug), headers=unique_user.token).json()
    assert updated["image"] == new_key

    cover = Recipe.image_dir_from_id(recipe["id"]).joinpath(RecipeImageTypes.original.value)
    gallery_original = Recipe.gallery_image_dir_from_id(recipe["id"], image["id"]).joinpath(
        RecipeImageTypes.original.value
    )
    with Image.open(cover) as cover_img, Image.open(gallery_original) as gallery_img:
        assert cover_img.size == gallery_img.size
        cover_pixel = cover_img.convert("RGB").getpixel((40, 30))
        gallery_pixel = gallery_img.convert("RGB").getpixel((40, 30))
        assert isinstance(cover_pixel, tuple) and isinstance(gallery_pixel, tuple)
        assert all(abs(a - b) <= 3 for a, b in zip(cover_pixel, gallery_pixel, strict=True))

    # the image stays in the gallery
    assert [i["id"] for i in get_gallery(api_client, unique_user, slug)] == [image["id"]]


def test_gallery_untouched_by_recipe_update(api_client: TestClient, unique_user: TestUser):
    recipe = create_recipe(api_client, unique_user)
    slug = recipe["slug"]
    upload(api_client, unique_user, slug, caption="one")
    upload(api_client, unique_user, slug, caption="two")
    before = get_gallery(api_client, unique_user, slug)

    recipe["description"] = random_string()
    response = api_client.put(api_routes.recipes_slug(slug), json=recipe, headers=unique_user.token)
    assert response.status_code == 200

    response = api_client.patch(api_routes.recipes_slug(slug), json={"name": recipe["name"]}, headers=unique_user.token)
    assert response.status_code == 200

    assert get_gallery(api_client, unique_user, slug) == before


def test_gallery_removed_with_recipe(api_client: TestClient, unique_user: TestUser):
    recipe = create_recipe(api_client, unique_user)
    ids = [upload(api_client, unique_user, recipe["slug"]).json()["id"] for _ in range(2)]

    response = api_client.delete(api_routes.recipes_slug(recipe["slug"]), headers=unique_user.token)
    assert response.status_code == 200

    for image_id in ids:
        assert unique_user.repos.recipe_gallery_images.get_one(image_id) is None
    assert not recipe_data_dir(recipe["id"]).exists()


def test_gallery_duplicated_with_recipe(api_client: TestClient, unique_user: TestUser):
    recipe = create_recipe(api_client, unique_user)
    old_ids = [upload(api_client, unique_user, recipe["slug"], caption=f"c{i}").json()["id"] for i in range(2)]

    response = api_client.post(
        api_routes.recipes_slug_duplicate(recipe["slug"]), json={"name": random_string()}, headers=unique_user.token
    )
    assert response.status_code == 201
    copy = response.json()

    copy_gallery = get_gallery(api_client, unique_user, copy["slug"])
    assert [image["caption"] for image in copy_gallery] == ["c0", "c1"]
    assert [image["position"] for image in copy_gallery] == [0, 1]
    assert all(image["recipeId"] == copy["id"] for image in copy_gallery)

    new_ids = {image["id"] for image in copy_gallery}
    assert not new_ids & set(old_ids)

    copy_gallery_dir = recipe_data_dir(copy["id"]).joinpath("images", "gallery")
    assert {p.name for p in copy_gallery_dir.iterdir()} == new_ids
    for image_id in new_ids:
        assert copy_gallery_dir.joinpath(image_id, RecipeImageTypes.original.value).is_file()

    # the original keeps its own gallery, and deleting it leaves the copy's intact
    assert [image["id"] for image in get_gallery(api_client, unique_user, recipe["slug"])] == old_ids
    api_client.delete(api_routes.recipes_slug(recipe["slug"]), headers=unique_user.token)
    assert {image["id"] for image in get_gallery(api_client, unique_user, copy["slug"])} == new_ids


def test_gallery_other_household_locked(api_client: TestClient, unique_user: TestUser, h2_user: TestUser):
    household = unique_user.repos.households.get_one(h2_user.household_id)
    assert household and household.preferences
    household.preferences.private_household = False
    household.preferences.lock_recipe_edits_from_other_households = True
    unique_user.repos.household_preferences.update(household.id, household.preferences)

    recipe = create_recipe(api_client, h2_user)
    slug = recipe["slug"]
    image = upload(api_client, h2_user, slug).json()

    # viewing is allowed
    assert [i["id"] for i in get_gallery(api_client, unique_user, slug)] == [image["id"]]

    assert upload(api_client, unique_user, slug).status_code == 403
    responses = [
        api_client.patch(
            api_routes.recipes_slug_gallery_image_id(slug, image["id"]),
            json={"caption": "x"},
            headers=unique_user.token,
        ),
        api_client.put(
            api_routes.recipes_slug_gallery_order(slug), json={"imageIds": [image["id"]]}, headers=unique_user.token
        ),
        api_client.delete(api_routes.recipes_slug_gallery_image_id(slug, image["id"]), headers=unique_user.token),
        api_client.post(
            api_routes.recipes_slug_gallery_image_id_set_cover(slug, image["id"]), headers=unique_user.token
        ),
    ]
    assert [response.status_code for response in responses] == [403] * len(responses)
    assert get_gallery(api_client, h2_user, slug) == [image | {"caption": None}]


def test_gallery_other_group(api_client: TestClient, unique_user: TestUser, g2_user: TestUser):
    recipe = create_recipe(api_client, unique_user)
    slug = recipe["slug"]
    image = upload(api_client, unique_user, slug).json()

    responses = [
        api_client.get(api_routes.recipes_slug_gallery(slug), headers=g2_user.token),
        upload(api_client, g2_user, slug),
        api_client.patch(
            api_routes.recipes_slug_gallery_image_id(slug, image["id"]), json={"caption": "x"}, headers=g2_user.token
        ),
        api_client.put(
            api_routes.recipes_slug_gallery_order(slug), json={"imageIds": [image["id"]]}, headers=g2_user.token
        ),
        api_client.delete(api_routes.recipes_slug_gallery_image_id(slug, image["id"]), headers=g2_user.token),
        api_client.post(api_routes.recipes_slug_gallery_image_id_set_cover(slug, image["id"]), headers=g2_user.token),
    ]
    assert [response.status_code for response in responses] == [404] * len(responses)
    assert len(get_gallery(api_client, unique_user, slug)) == 1
