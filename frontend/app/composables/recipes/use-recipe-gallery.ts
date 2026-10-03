import { useStaticRoutes, useUserApi } from "~/composables/api";
import { alert, alertUnreportedError } from "~/composables/use-toast";
import type { RecipeGalleryImageOut } from "~/lib/api/types/recipe";

export interface LightboxImage {
  url: string;
  alt?: string;
  caption?: string | null;
}

// The gallery is shown by more than one component on the recipe page (the cover image opens it in the
// lightbox, the gallery strip lists and edits it), so each recipe's gallery is shared state.
const galleries = new Map<string, Ref<RecipeGalleryImageOut[]>>();

function galleryState(recipeId: string) {
  let state = galleries.get(recipeId);
  if (!state) {
    state = ref<RecipeGalleryImageOut[]>([]);
    galleries.set(recipeId, state);
  }
  return state;
}

/**
 * Loads a recipe's photo gallery and wraps its actions.
 *
 * @param recipeId the recipe's id, which keys the shared gallery state
 * @param slug the recipe's slug, used for the API calls
 */
export function useRecipeGallery(recipeId: string, slug: MaybeRefOrGetter<string>) {
  const api = useUserApi();
  const i18n = useI18n();
  const { recipeGalleryImage } = useStaticRoutes();

  const images = galleryState(recipeId);
  const loading = ref(false);

  async function refresh() {
    const { data } = await api.recipes.getGallery(toValue(slug));
    if (data) {
      images.value = data;
    }
  }

  async function upload(files: File[]) {
    loading.value = true;
    for (const file of files) {
      const { data, error } = await api.recipes.addGalleryImage(toValue(slug), file);
      if (data) {
        images.value = [...images.value, data];
      }
      else {
        alertUnreportedError(error, i18n.t("recipe.gallery.upload-failed", { name: file.name }));
      }
    }
    loading.value = false;
  }

  async function updateCaption(imageId: string, caption: string) {
    const { data, error } = await api.recipes.updateGalleryImage(toValue(slug), imageId, { caption: caption || null });
    if (data) {
      images.value = images.value.map(image => (image.id === imageId ? data : image));
    }
    else {
      alertUnreportedError(error, i18n.t("events.something-went-wrong"));
    }
  }

  async function reorder(ids: string[]) {
    const { data, error } = await api.recipes.reorderGallery(toValue(slug), ids);
    if (data) {
      images.value = data;
    }
    else {
      alertUnreportedError(error, i18n.t("events.something-went-wrong"));
      await refresh();
    }
  }

  async function remove(imageId: string) {
    const { data, error } = await api.recipes.deleteGalleryImage(toValue(slug), imageId);
    if (data) {
      await refresh();
    }
    else {
      alertUnreportedError(error, i18n.t("events.something-went-wrong"));
    }
  }

  /** Makes a gallery image the recipe's cover and returns the new image key */
  async function setAsCover(imageId: string): Promise<string | null> {
    const { data, error } = await api.recipes.setGalleryImageAsCover(toValue(slug), imageId);
    if (data?.image) {
      alert.success(i18n.t("recipe.gallery.cover-updated"));
      return data.image;
    }
    alertUnreportedError(error, i18n.t("events.something-went-wrong"));
    return null;
  }

  function imageUrl(imageId: string, size: "original" | "min-original" | "tiny-original" = "original") {
    return recipeGalleryImage(recipeId, imageId, size);
  }

  /** The lightbox's browsing order: the cover image (when there is one), then the gallery images */
  function lightboxImages(cover: LightboxImage | null): LightboxImage[] {
    const gallery = images.value.map(image => ({
      url: imageUrl(image.id),
      alt: image.caption ?? "",
      caption: image.caption,
    }));
    return cover ? [cover, ...gallery] : gallery;
  }

  return { images, loading, refresh, upload, updateCaption, reorder, remove, setAsCover, imageUrl, lightboxImages };
}
