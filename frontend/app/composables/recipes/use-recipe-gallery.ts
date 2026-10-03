import { useStaticRoutes, useUserApi } from "~/composables/api";
import { alertUnreportedError } from "~/composables/use-toast";
import type { RecipeGalleryImageOut } from "~/lib/api/types/recipe";

export interface LightboxImage {
  url: string;
  alt?: string;
  caption?: string | null;
}

// Shared per recipe, so the cover image's lightbox and the gallery component see the same images
const galleries = new Map<string, Ref<RecipeGalleryImageOut[]>>();
const pending = new Map<string, Promise<void>>();

export function useRecipeGallery(recipeId: string, slug: string) {
  const i18n = useI18n();
  const api = useUserApi();
  const { recipeGalleryImage } = useStaticRoutes();

  if (!galleries.has(recipeId)) {
    galleries.set(recipeId, ref<RecipeGalleryImageOut[]>([]));
  }
  const images = galleries.get(recipeId)!;
  const loading = ref(false);

  async function refresh() {
    const { data } = await api.recipes.getGallery(slug);
    if (data) {
      images.value = data;
    }
  }

  /** Loads the gallery, sharing one request between components that mount at the same time */
  function load() {
    if (!pending.has(recipeId)) {
      pending.set(recipeId, refresh().finally(() => pending.delete(recipeId)));
    }
    return pending.get(recipeId)!;
  }

  async function upload(files: File[]) {
    loading.value = true;
    for (const file of files) {
      const { data, error } = await api.recipes.addGalleryImage(slug, file);
      if (error || !data) {
        alertUnreportedError(error, i18n.t("events.something-went-wrong"));
        continue;
      }
      images.value = [...images.value, data];
    }
    loading.value = false;
  }

  async function updateCaption(imageId: string, caption: string) {
    const { data, error } = await api.recipes.updateGalleryImage(slug, imageId, { caption });
    if (error || !data) {
      alertUnreportedError(error, i18n.t("events.something-went-wrong"));
      return;
    }
    images.value = images.value.map(image => (image.id === imageId ? data : image));
  }

  async function reorder(imageIds: string[]) {
    const { data, error } = await api.recipes.reorderGallery(slug, imageIds);
    if (error || !data) {
      alertUnreportedError(error, i18n.t("events.something-went-wrong"));
      await refresh();
      return;
    }
    images.value = data;
  }

  async function remove(imageId: string) {
    const { error } = await api.recipes.deleteGalleryImage(slug, imageId);
    if (error) {
      alertUnreportedError(error, i18n.t("events.something-went-wrong"));
      return;
    }
    await refresh();
  }

  /** Returns the recipe's new image key, or null if it failed */
  async function setAsCover(imageId: string): Promise<string | null> {
    const { data, error } = await api.recipes.setGalleryImageAsCover(slug, imageId);
    if (error || !data) {
      alertUnreportedError(error, i18n.t("events.something-went-wrong"));
      return null;
    }
    return data.image;
  }

  function imageUrl(imageId: string, size: "original" | "min" | "tiny" = "original") {
    return recipeGalleryImage(recipeId, imageId, size);
  }

  /** The browsing order for the lightbox: the cover image (if any), then the gallery images */
  function lightboxImages(coverUrl: string | null | undefined, alt: string): LightboxImage[] {
    const gallery = images.value.map(image => ({
      url: imageUrl(image.id),
      alt: image.caption || alt,
      caption: image.caption,
    }));
    return coverUrl ? [{ url: coverUrl, alt }, ...gallery] : gallery;
  }

  return {
    images,
    loading,
    load,
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
