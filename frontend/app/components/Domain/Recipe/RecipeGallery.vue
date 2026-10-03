<template>
  <div v-if="edit || images.length" class="d-print-none my-4">
    <div class="d-flex align-center flex-wrap ga-2 mb-2">
      <h2 class="text-h6 font-weight-regular">
        {{ $t("recipe.gallery") }}
      </h2>
      <AppButtonUpload
        v-if="edit"
        class="ml-auto"
        url="none"
        file-name="image"
        accept="image/*"
        :text="$t('recipe.gallery-add-images')"
        :text-btn="false"
        :post="false"
        :multiple="true"
        :disabled="loading"
        @uploaded="onUploaded"
      />
    </div>

    <!-- View mode: a row of thumbnails that open the lightbox -->
    <div v-if="!edit" class="gallery-row">
      <v-img
        v-for="(image, i) in images"
        :key="image.id"
        :src="recipeGalleryImage(recipe.id, image.id, 'tiny-original')"
        :alt="image.caption || recipe.name"
        :title="image.caption || undefined"
        class="gallery-thumb rounded"
        cover
        @click="openLightbox(i)"
      />
    </div>

    <!-- Edit mode: captions, reordering, delete and set as cover -->
    <template v-else>
      <p v-if="images.length > 1" class="text-caption mb-2">
        {{ $t("recipe.gallery-drag-to-reorder") }}
      </p>
      <VueDraggable
        v-model="editList"
        class="gallery-row"
        :delay="250"
        :delay-on-touch-only="true"
        :animation="200"
        @end="onReorder"
      >
        <v-card
          v-for="image in editList"
          :key="image.id"
          class="gallery-edit-card"
          variant="outlined"
        >
          <v-img
            :src="recipeGalleryImage(recipe.id, image.id, 'tiny-original')"
            :alt="image.caption || recipe.name"
            class="gallery-thumb"
            cover
          />
          <v-card-text class="pa-2">
            <v-text-field
              :model-value="image.caption ?? ''"
              :label="$t('recipe.gallery-caption')"
              density="compact"
              variant="underlined"
              hide-details
              @change="(event: Event) => updateCaption(image.id, (event.target as HTMLInputElement).value)"
            />
          </v-card-text>
          <v-card-actions class="pt-0">
            <v-icon class="cursor-move" :title="$t('recipe.gallery-drag-to-reorder')">
              {{ $globals.icons.arrowUpDown }}
            </v-icon>
            <v-spacer />
            <v-btn
              icon
              size="small"
              variant="text"
              :title="$t('recipe.gallery-set-as-cover')"
              :aria-label="$t('recipe.gallery-set-as-cover')"
              @click="setAsCover(image.id)"
            >
              <v-icon>{{ $globals.icons.fileImage }}</v-icon>
            </v-btn>
            <v-btn
              icon
              size="small"
              variant="text"
              color="error"
              :title="$t('general.delete')"
              :aria-label="$t('general.delete')"
              @click="remove(image.id)"
            >
              <v-icon>{{ $globals.icons.delete }}</v-icon>
            </v-btn>
          </v-card-actions>
        </v-card>
      </VueDraggable>
    </template>

    <RecipeImageLightbox
      v-if="lightboxOpen"
      v-model="lightboxOpen"
      v-model:index="lightboxIndex"
      :images="lightboxImages(recipe.id, recipe.name, coverUrl)"
    />
  </div>
</template>

<script setup lang="ts">
import { VueDraggable } from "vue-draggable-plus";
import RecipeImageLightbox from "./RecipeImageLightbox.vue";
import { useStaticRoutes } from "~/composables/api";
import { usePageState } from "~/composables/recipe-page/shared-state";
import { useRecipeGallery } from "~/composables/recipes/use-recipe-gallery";
import { alert } from "~/composables/use-toast";
import type { Recipe, RecipeGalleryImageOut } from "~/lib/api/types/recipe";
import type { NoUndefinedField } from "~/lib/api/types/non-generated";

interface Props {
  edit?: boolean;
}
withDefaults(defineProps<Props>(), {
  edit: false,
});
const recipe = defineModel<NoUndefinedField<Recipe>>({ required: true });

const i18n = useI18n();
const { recipeImage, recipeGalleryImage } = useStaticRoutes();
const { imageKey } = usePageState(recipe.value.slug);
const gallery = useRecipeGallery(recipe.value.slug);
const { images, loading, lightboxImages } = gallery;

onMounted(gallery.refresh);

const coverUrl = computed(() =>
  recipe.value.image ? recipeImage(recipe.value.id, recipe.value.image, imageKey.value) : null,
);

const lightboxOpen = ref(false);
const lightboxIndex = ref(0);

function openLightbox(galleryIndex: number) {
  // The cover image comes first when browsing
  lightboxIndex.value = galleryIndex + (coverUrl.value ? 1 : 0);
  lightboxOpen.value = true;
}

// VueDraggable reorders this copy; the new order is saved when the drag ends
const editList = ref<RecipeGalleryImageOut[]>([]);
watch(images, (value) => {
  editList.value = [...value];
}, { immediate: true });

async function onUploaded(payload: unknown) {
  const files = (Array.isArray(payload) ? payload : [payload]).filter((file): file is File => file instanceof File);
  if (files.length) {
    await gallery.addImages(files);
  }
}

async function onReorder() {
  const ids = editList.value.map(image => image.id);
  if (ids.join() !== images.value.map(image => image.id).join()) {
    await gallery.reorder(ids);
  }
}

async function updateCaption(imageId: string, caption: string) {
  await gallery.updateCaption(imageId, caption);
}

async function remove(imageId: string) {
  await gallery.remove(imageId);
}

async function setAsCover(imageId: string) {
  const newImage = await gallery.setAsCover(imageId);
  if (newImage) {
    recipe.value.image = newImage;
    imageKey.value++;
    alert.success(i18n.t("recipe.gallery-cover-updated"));
  }
}
</script>

<style scoped>
.gallery-row {
  display: flex;
  flex-wrap: nowrap;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 4px;
}

.gallery-thumb {
  flex: 0 0 150px;
  width: 150px;
  height: 150px;
  cursor: zoom-in;
}

.gallery-edit-card {
  flex: 0 0 180px;
  width: 180px;
}

.gallery-edit-card .gallery-thumb {
  width: 100%;
  cursor: move;
}
</style>
