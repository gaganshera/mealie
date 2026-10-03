import { useStaticRoutes, useUserApi } from "~/composables/api";
import { alert } from "~/composables/use-toast";
import type { RecipeGalleryImageOut } from "~/lib/api/types/recipe";

export interface LightboxImage {
  url: string;
  alt?: string;
  caption?: string | null;
}

// Shared per recipe, so the cover image and the gallery browse the same list
const galleries: Record<string, Ref<RecipeGalleryImageOut[]>> = {};

export function useRecipeGallery(slug: string) {
  const api = useUserApi();
  const i18n = useI18n();
  const { recipeGalleryImage } = useStaticRoutes();

  galleries[slug] ??= ref<RecipeGalleryImageOut[]>([]);
  const images = galleries[slug];
  const uploading = ref(false);

  async function refresh() {
    const { data } = await api.recipes.getGallery(slug);
    images.value = data ?? [];
  }

  async function upload(files: File[]) {
    uploading.value = true;
    for (const file of files) {
      const { data } = await api.recipes.addGalleryImage(slug, file);
      if (data) {
        images.value.push(data);
      }
      else {
        alert.error(i18n.t("recipe.gallery-upload-failed", [file.name]));
      }
    }
    uploading.value = false;
  }

  async function updateCaption(imageId: string, caption: string | null) {
    await api.recipes.updateGalleryImageCaption(slug, imageId, caption || null);
  }

  async function reorder() {
    const { data } = await api.recipes.reorderGallery(slug, images.value.map(image => image.id));
    if (data) {
      images.value = data;
    }
  }

  async function remove(imageId: string) {
    await api.recipes.deleteGalleryImage(slug, imageId);
    await refresh();
  }

  /** Returns the recipe's new image key, or null on failure */
  async function setAsCover(imageId: string) {
    const { data } = await api.recipes.setGalleryImageAsCover(slug, imageId);
    return data?.image ?? null;
  }

  /** The lightbox browsing order: the cover image (if any), then the gallery */
  function lightboxImages(recipeId: string, recipeName: string, coverUrl?: string): LightboxImage[] {
    return [
      ...(coverUrl ? [{ url: coverUrl, alt: recipeName }] : []),
      ...images.value.map(image => ({
        url: recipeGalleryImage(recipeId, image.id),
        alt: image.caption || recipeName,
        caption: image.caption,
      })),
    ];
  }

  return { images, uploading, refresh, upload, updateCaption, reorder, remove, setAsCover, lightboxImages };
}
