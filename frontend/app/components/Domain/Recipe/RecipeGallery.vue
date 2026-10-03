<template>
  <div v-if="edit || images.length" class="d-print-none">
    <div v-if="edit" class="d-flex align-center flex-wrap ga-2 mb-2">
      <h2 class="text-h5 mr-auto">
        {{ $t("recipe.gallery") }}
      </h2>
      <AppButtonUpload
        multiple
        accept="image/*,.heic"
        :text="$t('recipe.upload-images')"
        :disabled="loading"
        @uploaded="onUploaded"
      />
    </div>

    <!-- View mode: a row of thumbnails -->
    <div v-if="!edit" class="d-flex flex-wrap ga-2 my-2">
      <v-img
        v-for="(image, i) in images"
        :key="image.id"
        :src="recipeGalleryImage(recipe.id, image.id, 'tiny-original')"
        :alt="image.caption || recipe.name"
        width="300"
        height="300"
        max-width="300"
        cover
        class="rounded gallery-thumb"
        @click="openLightbox(i)"
      />
    </div>

    <!-- Edit mode: captions, reordering, delete and set as cover -->
    <VueDraggable
      v-else
      v-model="images"
      handle=".handle"
      :delay="250"
      :delay-on-touch-only="true"
      :animation="200"
      class="d-flex flex-wrap ga-4"
      @end="onReorder"
    >
      <v-card
        v-for="(image, i) in images"
        :key="image.id"
        width="300"
        variant="outlined"
      >
        <v-img
          :src="recipeGalleryImage(recipe.id, image.id, 'tiny-original')"
          :alt="image.caption || recipe.name"
          height="300"
          cover
          class="gallery-thumb"
          @click="openLightbox(i)"
        />
        <v-card-text class="pb-0">
          <v-text-field
            :model-value="image.caption ?? ''"
            :label="$t('recipe.gallery-caption')"
            density="compact"
            variant="underlined"
            hide-details
            @change="(e: Event) => updateCaption(image.id, (e.target as HTMLInputElement).value)"
          />
        </v-card-text>
        <v-card-actions>
          <v-icon class="handle">
            {{ $globals.icons.arrowUpDown }}
          </v-icon>
          <v-spacer />
          <v-btn
            icon
            size="small"
            variant="text"
            :title="$t('recipe.set-as-cover-image')"
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
            @click="remove(image.id)"
          >
            <v-icon>{{ $globals.icons.delete }}</v-icon>
          </v-btn>
        </v-card-actions>
      </v-card>
    </VueDraggable>

    <RecipeImageLightbox
      v-if="lightboxOpen"
      v-model="lightboxOpen"
      v-model:index="lightboxIndex"
      :images="lightboxImages"
    />
  </div>
</template>

<script setup lang="ts">
import { VueDraggable } from "vue-draggable-plus";
import RecipeImageLightbox from "~/components/Domain/Recipe/RecipeImageLightbox.vue";
import { useStaticRoutes } from "~/composables/api";
import { usePageState } from "~/composables/recipe-page/shared-state";
import { useRecipeGallery } from "~/composables/recipes/use-recipe-gallery";
import type { NoUndefinedField } from "~/lib/api/types/non-generated";
import type { Recipe } from "~/lib/api/types/recipe";

interface Props {
  edit?: boolean;
}
withDefaults(defineProps<Props>(), {
  edit: false,
});

const recipe = defineModel<NoUndefinedField<Recipe>>({ required: true });

const { recipeImage, recipeGalleryImage } = useStaticRoutes();
const { imageKey } = usePageState(recipe.value.slug);
const gallery = useRecipeGallery(recipe.value.slug);
const { images, loading } = gallery;

onMounted(() => {
  gallery.refresh();
});

// The lightbox browses the cover image first, then the gallery
const lightboxOpen = ref(false);
const lightboxIndex = ref(0);
const hasCover = computed(() => !!recipe.value.image);

const lightboxImages = computed(() => [
  ...(hasCover.value
    ? [{ url: recipeImage(recipe.value.id, recipe.value.image, imageKey.value), alt: recipe.value.name }]
    : []),
  ...images.value.map(image => ({
    url: recipeGalleryImage(recipe.value.id, image.id),
    alt: image.caption || recipe.value.name,
    caption: image.caption,
  })),
]);

function openLightbox(galleryIndex: number) {
  lightboxIndex.value = galleryIndex + (hasCover.value ? 1 : 0);
  lightboxOpen.value = true;
}

async function onUploaded(files: File | File[] | unknown) {
  if (!files) {
    return;
  }
  await gallery.upload(Array.isArray(files) ? files : [files as File]);
}

async function updateCaption(id: string, caption: string) {
  await gallery.updateCaption(id, caption);
}

async function onReorder() {
  await gallery.reorder(images.value.map(image => image.id));
}

async function remove(id: string) {
  await gallery.remove(id);
}

async function setAsCover(id: string) {
  const image = await gallery.setAsCover(id);
  if (image) {
    recipe.value.image = image;
    imageKey.value++;
  }
}
</script>

<style scoped>
.gallery-thumb {
  cursor: zoom-in;
}

.handle {
  cursor: grab;
}
</style>
