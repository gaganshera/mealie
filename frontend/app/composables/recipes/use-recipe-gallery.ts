import { useStaticRoutes, useUserApi } from "~/composables/api";
import { alertUnreportedError } from "~/composables/use-toast";
import type { LightboxImage } from "~/components/Domain/Recipe/RecipeImageLightbox.vue";
import type { RecipeGalleryImageOut } from "~/lib/api/types/recipe";

// Shared per recipe, so the cover image and the gallery browse the same list
const galleries: Record<string, Ref<RecipeGalleryImageOut[]>> = {};

export const useRecipeGallery = (recipeSlug: string) => {
  const api = useUserApi();
  const i18n = useI18n();
  const { recipeGalleryImage } = useStaticRoutes();

  galleries[recipeSlug] ??= ref<RecipeGalleryImageOut[]>([]);
  const images = galleries[recipeSlug];
  const loading = ref(false);

  function reportError(error: unknown) {
    alertUnreportedError(error as Parameters<typeof alertUnreportedError>[0], i18n.t("events.something-went-wrong"));
  }

  async function refresh() {
    loading.value = true;
    const { data } = await api.recipes.getGallery(recipeSlug);
    if (data) {
      images.value = data;
    }
    loading.value = false;
  }

  async function addImages(files: File[]) {
    loading.value = true;
    for (const file of files) {
      const { data, error } = await api.recipes.addGalleryImage(recipeSlug, file);
      if (error) {
        reportError(error);
        continue;
      }
      if (data) {
        images.value = [...images.value, data];
      }
    }
    loading.value = false;
  }

  async function updateCaption(imageId: string, caption: string | null) {
    const { data, error } = await api.recipes.updateGalleryImageCaption(recipeSlug, imageId, caption || null);
    if (error) {
      reportError(error);
      return;
    }
    if (data) {
      images.value = images.value.map(image => (image.id === data.id ? data : image));
    }
  }

  async function reorder(imageIds: string[]) {
    const { data, error } = await api.recipes.reorderGallery(recipeSlug, imageIds);
    if (error) {
      reportError(error);
      await refresh();
      return;
    }
    if (data) {
      images.value = data;
    }
  }

  async function remove(imageId: string) {
    const { error } = await api.recipes.deleteGalleryImage(recipeSlug, imageId);
    if (error) {
      reportError(error);
      return;
    }
    await refresh();
  }

  /** Returns the recipe's new image key, or null if it failed */
  async function setAsCover(imageId: string): Promise<string | null> {
    const { data, error } = await api.recipes.setGalleryImageAsCover(recipeSlug, imageId);
    if (error) {
      reportError(error);
      return null;
    }
    return data?.image ?? null;
  }

  /** The lightbox browsing order: the cover image (if any), then the gallery */
  function lightboxImages(recipeId: string, recipeName: string, coverUrl?: string | null): LightboxImage[] {
    const gallery = images.value.map(image => ({
      url: recipeGalleryImage(recipeId, image.id),
      alt: image.caption || recipeName,
      caption: image.caption,
    }));
    return coverUrl ? [{ url: coverUrl, alt: recipeName }, ...gallery] : gallery;
  }

  return {
    images,
    loading,
    refresh,
    addImages,
    updateCaption,
    reorder,
    remove,
    setAsCover,
    lightboxImages,
  };
};
