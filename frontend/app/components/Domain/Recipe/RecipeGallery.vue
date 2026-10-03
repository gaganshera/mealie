<template>
  <div v-if="isEditForm || images.length" class="d-print-none">
    <!-- Edit mode: upload, caption, reorder, delete and set as cover -->
    <section v-if="isEditForm" class="my-4">
      <div class="d-flex align-center flex-wrap ga-2 mb-2">
        <h3 class="text-h6">
          {{ $t("recipe.gallery.title") }}
        </h3>
        <AppButtonUpload
          class="ml-auto"
          url="none"
          file-name="image"
          accept="image/*"
          :text="$t('recipe.gallery.add-images')"
          :text-btn="false"
          :post="false"
          :multiple="true"
          :disabled="loading"
          @uploaded="onUpload"
        />
      </div>
      <v-progress-linear v-if="loading" indeterminate class="mb-2" />
      <VueDraggable
        v-model="orderedImages"
        handle=".handle"
        :delay="250"
        :delay-on-touch-only="true"
        :animation="200"
        class="d-flex flex-wrap ga-3"
        @end="onDragEnd"
      >
        <v-card
          v-for="image in orderedImages"
          :key="image.id"
          width="180"
          variant="outlined"
        >
          <v-img
            :src="imageUrl(image.id, 'tiny-original')"
            :alt="image.caption || ''"
            aspect-ratio="1"
            cover
            class="handle"
            style="cursor: grab"
            :title="$t('recipe.gallery.drag-to-reorder')"
          />
          <v-card-text class="pa-2">
            <v-text-field
              v-model="captions[image.id]"
              :label="$t('recipe.gallery.caption')"
              density="compact"
              variant="underlined"
              hide-details
              @blur="saveCaption(image.id)"
              @keydown.enter="saveCaption(image.id)"
            />
          </v-card-text>
          <v-card-actions class="pa-1">
            <v-btn
              size="small"
              variant="text"
              :prepend-icon="$globals.icons.fileImage"
              @click="onSetAsCover(image.id)"
            >
              {{ $t("recipe.gallery.set-as-cover") }}
            </v-btn>
            <v-spacer />
            <v-btn
              size="small"
              variant="text"
              color="error"
              :icon="$globals.icons.delete"
              :aria-label="$t('recipe.gallery.delete-image')"
              :title="$t('recipe.gallery.delete-image')"
              @click="remove(image.id)"
            />
          </v-card-actions>
        </v-card>
      </VueDraggable>
    </section>

    <!-- View mode: thumbnails that open the lightbox -->
    <div v-else class="d-flex flex-wrap ga-2 my-4">
      <button
        v-for="(image, i) in images"
        :key="image.id"
        type="button"
        class="gallery-thumbnail"
        :aria-label="$t('recipe.gallery.open-image', { number: i + 1 })"
        @click="openLightbox(i)"
      >
        <v-img
          :src="imageUrl(image.id, 'tiny-original')"
          :alt="image.caption || ''"
          width="150"
          height="150"
          cover
          rounded
        />
      </button>
    </div>

    <RecipeImageLightbox
      v-if="lightboxOpen"
      v-model="lightboxOpen"
      v-model:index="lightboxIndex"
      :images="lightboxItems"
    />
  </div>
</template>

<script setup lang="ts">
import { VueDraggable } from "vue-draggable-plus";
import RecipeImageLightbox from "~/components/Domain/Recipe/RecipeImageLightbox.vue";
import { useStaticRoutes } from "~/composables/api";
import { usePageState } from "~/composables/recipe-page/shared-state";
import { useRecipeGallery } from "~/composables/recipes/use-recipe-gallery";
import { useLoggedInState } from "~/composables/use-logged-in-state";
import type { NoUndefinedField } from "~/lib/api/types/non-generated";
import type { Recipe, RecipeGalleryImageOut } from "~/lib/api/types/recipe";

const recipe = defineModel<NoUndefinedField<Recipe>>({ required: true });

const { isEditForm, imageKey } = usePageState(recipe.value.slug);
const { isOwnGroup } = useLoggedInState();
const { recipeImage } = useStaticRoutes();
const { images, loading, refresh, upload, updateCaption, reorder, remove, setAsCover, imageUrl, lightboxImages }
  = useRecipeGallery(recipe.value.id, () => recipe.value.slug);

onMounted(() => {
  // The gallery API needs a logged-in member of the recipe's group
  if (isOwnGroup.value) {
    refresh();
  }
});

// Drag-to-reorder works on a local copy, which is saved when the drag ends
const orderedImages = ref<RecipeGalleryImageOut[]>([]);
const captions = reactive<Record<string, string>>({});
watch(images, (value) => {
  orderedImages.value = [...value];
  for (const image of value) {
    captions[image.id] = image.caption ?? "";
  }
}, { immediate: true });

function onUpload(files: File | File[] | unknown) {
  const list = Array.isArray(files) ? files : [files];
  upload(list.filter((file): file is File => file instanceof File));
}

function onDragEnd() {
  const ids = orderedImages.value.map(image => image.id);
  if (ids.join() !== images.value.map(image => image.id).join()) {
    reorder(ids);
  }
}

function saveCaption(imageId: string) {
  const current = images.value.find(image => image.id === imageId);
  const caption = captions[imageId] ?? "";
  if (current && caption !== (current.caption ?? "")) {
    updateCaption(imageId, caption);
  }
}

async function onSetAsCover(imageId: string) {
  const image = await setAsCover(imageId);
  if (image) {
    recipe.value.image = image;
    imageKey.value++;
  }
}

const lightboxOpen = ref(false);
const lightboxIndex = ref(0);
const lightboxItems = computed(() => lightboxImages(
  recipe.value.image
    ? { url: recipeImage(recipe.value.id, recipe.value.image, imageKey.value), alt: recipe.value.name }
    : null,
));

function openLightbox(galleryIndex: number) {
  // The cover image comes first in the lightbox's browsing order
  lightboxIndex.value = galleryIndex + (recipe.value.image ? 1 : 0);
  lightboxOpen.value = true;
}
</script>

<style scoped>
.gallery-thumbnail {
  cursor: zoom-in;
  border-radius: 4px;
}
</style>
