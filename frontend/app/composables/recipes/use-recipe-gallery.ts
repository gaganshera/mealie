import { useStaticRoutes, useUserApi } from "~/composables/api";
import { alertUnreportedError } from "~/composables/use-toast";
import type { RecipeGalleryImageOut } from "~/lib/api/types/recipe";

export interface LightboxImage {
  url: string;
  alt?: string;
  caption?: string | null;
}

// Shared per recipe, so the cover image and the gallery row browse the same list
const memo: Record<string, Ref<RecipeGalleryImageOut[]>> = {};

/**
 * Loads a recipe's gallery and wraps its actions. Every call for the same recipe shares one list.
 * Requests use the recipe id, which the API accepts in place of the slug and which survives a rename.
 */
export function useRecipeGallery(recipeId: string) {
  const api = useUserApi();
  const i18n = useI18n();
  const { recipeGalleryImage } = useStaticRoutes();

  const isNew = !memo[recipeId];
  const images = memo[recipeId] ??= ref<RecipeGalleryImageOut[]>([]);

  async function refresh() {
    const { data } = await api.recipes.getGallery(recipeId);
    if (data) {
      images.value = data;
    }
  }

  async function upload(files: File[]) {
    for (const file of files) {
      const { data, error } = await api.recipes.addGalleryImage(recipeId, file);
      if (error || !data) {
        alertUnreportedError(error, i18n.t("events.something-went-wrong"));
        continue;
      }
      images.value = [...images.value, data];
    }
  }

  async function updateCaption(imageId: string, caption: string) {
    const { data, error } = await api.recipes.updateGalleryImage(recipeId, imageId, { caption: caption || null });
    if (error || !data) {
      alertUnreportedError(error, i18n.t("events.something-went-wrong"));
      return;
    }
    images.value = images.value.map(image => (image.id === data.id ? data : image));
  }

  async function reorder(imageIds: string[]) {
    const { data, error } = await api.recipes.reorderGallery(recipeId, imageIds);
    if (error || !data) {
      alertUnreportedError(error, i18n.t("events.something-went-wrong"));
      await refresh();
      return;
    }
    images.value = data;
  }

  async function remove(imageId: string) {
    const { error } = await api.recipes.deleteGalleryImage(recipeId, imageId);
    if (error) {
      alertUnreportedError(error, i18n.t("events.something-went-wrong"));
      return;
    }
    // positions are renumbered on the server
    await refresh();
  }

  /** Returns the recipe's new image key, or null if it failed */
  async function setAsCover(imageId: string): Promise<string | null> {
    const { data, error } = await api.recipes.setGalleryImageAsCover(recipeId, imageId);
    if (error || !data) {
      alertUnreportedError(error, i18n.t("events.something-went-wrong"));
      return null;
    }
    return data.image;
  }

  function imageUrl(image: RecipeGalleryImageOut, size: "original" | "min-original" | "tiny-original" = "original") {
    return recipeGalleryImage(recipeId, image.id, size);
  }

  /** The lightbox browses the cover image (if there is one) followed by the gallery */
  function lightboxImages(cover: LightboxImage | null): LightboxImage[] {
    return [
      ...(cover ? [cover] : []),
      ...images.value.map(image => ({ url: imageUrl(image), alt: image.caption || "", caption: image.caption })),
    ];
  }

  if (isNew) {
    refresh();
  }

  return {
    images,
    refresh,
    upload,
    updateCaption,
    reorder,
    remove,
    setAsCover,
    imageUrl,
    lightboxImages,
  };
}
