import type { Ref } from "vue";
import { useUserApi } from "~/composables/api";
import { alertUnreportedError } from "~/composables/use-toast";
import type { RecipeGalleryImageOut } from "~/lib/api/types/recipe";

// Shared per recipe, so the cover image and the gallery browse the same list
const galleries = new Map<string, Ref<RecipeGalleryImageOut[]>>();

export function useRecipeGallery(slug: string) {
  const api = useUserApi();
  const i18n = useI18n();

  if (!galleries.has(slug)) {
    galleries.set(slug, ref<RecipeGalleryImageOut[]>([]));
  }
  const images = galleries.get(slug)!;
  const loading = ref(false);

  function onError(error: unknown) {
    alertUnreportedError(error as Parameters<typeof alertUnreportedError>[0], i18n.t("events.something-went-wrong"));
  }

  async function refresh() {
    loading.value = true;
    const { data, error } = await api.recipes.getGallery(slug);
    loading.value = false;
    if (error) {
      onError(error);
      return;
    }
    images.value = data ?? [];
  }

  async function upload(files: File[]) {
    loading.value = true;
    for (const file of files) {
      const { error } = await api.recipes.addGalleryImage(slug, file);
      if (error) {
        onError(error);
        break;
      }
    }
    loading.value = false;
    await refresh();
  }

  async function updateCaption(id: string, caption: string) {
    const { data, error } = await api.recipes.updateGalleryImage(slug, id, { caption });
    if (error) {
      onError(error);
      return;
    }
    if (data) {
      images.value = images.value.map(image => (image.id === id ? data : image));
    }
  }

  async function reorder(ids: string[]) {
    const { data, error } = await api.recipes.reorderGallery(slug, ids);
    if (error) {
      onError(error);
      await refresh();
      return;
    }
    if (data) {
      images.value = data;
    }
  }

  async function remove(id: string) {
    const { error } = await api.recipes.deleteGalleryImage(slug, id);
    if (error) {
      onError(error);
    }
    await refresh();
  }

  /** Returns the recipe's new image key, or null if it failed */
  async function setAsCover(id: string): Promise<string | null> {
    const { data, error } = await api.recipes.setGalleryImageAsCover(slug, id);
    if (error) {
      onError(error);
      return null;
    }
    return data?.image ?? null;
  }

  return {
    images,
    loading,
    refresh,
    upload,
    updateCaption,
    reorder,
    remove,
    setAsCover,
  };
}
