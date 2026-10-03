<template>
  <div v-if="images.length || isEditForm" class="d-print-none px-4 pb-4">
    <template v-if="!isEditForm">
      <div class="d-flex flex-wrap justify-center ga-2">
        <v-img
          v-for="(image, i) in images"
          :key="image.id"
          :src="imageUrl(image, 'tiny-original')"
          :alt="image.caption || recipe.name"
          :title="image.caption || undefined"
          width="100"
          height="100"
          max-width="100"
          cover
          class="rounded flex-grow-0"
          style="cursor: zoom-in"
          @click="openLightbox(i)"
        />
      </div>
      <RecipeImageLightbox
        v-if="lightboxOpen"
        v-model="lightboxOpen"
        v-model:index="lightboxIndex"
        :images="lightboxImages(cover)"
      />
    </template>

    <template v-else>
      <div class="d-flex align-center flex-wrap ga-2 mb-2">
        <span class="text-h6 font-weight-regular">{{ $t("recipe.gallery") }}</span>
        <v-spacer />
        <AppButtonUpload
          url="none"
          file-name="image"
          accept="image/*,.heic"
          multiple
          :post="false"
          :text-btn="false"
          :text="$t('recipe.upload-images')"
          @uploaded="onUpload"
        />
      </div>
      <VueDraggable
        v-model="ordered"
        handle=".handle"
        :animation="200"
        class="d-flex flex-wrap ga-3"
        @end="saveOrder"
      >
        <v-card
          v-for="image in ordered"
          :key="image.id"
          width="200"
          variant="outlined"
        >
          <div class="position-relative">
            <v-img
              :src="imageUrl(image, 'tiny-original')"
              height="130"
              cover
            />
            <v-icon
              class="handle position-absolute top-0 left-0 ma-1 bg-surface rounded"
              :title="$t('recipe.gallery-drag-to-reorder')"
              style="cursor: grab"
            >
              {{ $globals.icons.arrowUpDown }}
            </v-icon>
          </div>
          <v-card-text class="pa-2">
            <v-text-field
              v-model="captions[image.id]"
              :label="$t('recipe.gallery-caption')"
              density="compact"
              variant="underlined"
              hide-details
              @blur="saveCaption(image)"
              @keydown.enter="saveCaption(image)"
            />
          </v-card-text>
          <v-card-actions class="pt-0">
            <v-btn
              size="small"
              variant="text"
              :icon="$globals.icons.fileImage"
              :title="$t('recipe.set-as-cover-image')"
              :aria-label="$t('recipe.set-as-cover-image')"
              @click="setAsCover(image)"
            />
            <v-spacer />
            <v-btn
              size="small"
              variant="text"
              color="error"
              :icon="$globals.icons.delete"
              :title="$t('general.delete')"
              :aria-label="$t('general.delete')"
              @click="imageToDelete = image"
            />
          </v-card-actions>
        </v-card>
      </VueDraggable>
      <BaseDialog
        :model-value="!!imageToDelete"
        :title="$t('recipe.delete-image')"
        :icon="$globals.icons.alertCircle"
        color="error"
        can-delete
        @update:model-value="(open: boolean) => { if (!open) imageToDelete = null; }"
        @delete="deleteImage"
      >
        <v-card-text>
          {{ $t("recipe.delete-image-confirmation") }}
        </v-card-text>
      </BaseDialog>
    </template>
  </div>
</template>

<script setup lang="ts">
import { VueDraggable } from "vue-draggable-plus";
import AppButtonUpload from "~/components/global/AppButtonUpload.vue";
import BaseDialog from "~/components/global/BaseDialog.vue";
import RecipeImageLightbox from "~/components/Domain/Recipe/RecipeImageLightbox.vue";
import { useStaticRoutes } from "~/composables/api";
import { usePageState } from "~/composables/recipe-page/shared-state";
import { useRecipeGallery } from "~/composables/recipes/use-recipe-gallery";
import { alert } from "~/composables/use-toast";
import type { NoUndefinedField } from "~/lib/api/types/non-generated";
import type { Recipe, RecipeGalleryImageOut } from "~/lib/api/types/recipe";

const recipe = defineModel<NoUndefinedField<Recipe>>({ required: true });

const i18n = useI18n();
const { recipeImage } = useStaticRoutes();
const { isEditForm, imageKey } = usePageState(recipe.value.slug);
const gallery = useRecipeGallery(recipe.value.id);
const { images, imageUrl, lightboxImages } = gallery;

// Viewing

const lightboxOpen = ref(false);
const lightboxIndex = ref(0);

const cover = computed(() =>
  recipe.value.image
    ? { url: recipeImage(recipe.value.id, recipe.value.image, imageKey.value), alt: recipe.value.name }
    : null,
);

function openLightbox(galleryIndex: number) {
  // the lightbox list starts with the cover image, when there is one
  lightboxIndex.value = galleryIndex + (cover.value ? 1 : 0);
  lightboxOpen.value = true;
}

// Editing

const ordered = ref<RecipeGalleryImageOut[]>([]);
const captions = ref<Record<string, string>>({});
const imageToDelete = ref<RecipeGalleryImageOut | null>(null);

watch(images, (value) => {
  ordered.value = [...value];
  captions.value = Object.fromEntries(value.map(image => [image.id, image.caption ?? ""]));
}, { immediate: true });

async function onUpload(files: File | File[] | unknown) {
  const list = Array.isArray(files) ? files : files instanceof File ? [files] : [];
  await gallery.upload(list);
}

async function saveCaption(image: RecipeGalleryImageOut) {
  const caption = captions.value[image.id] ?? "";
  if (caption === (image.caption ?? "")) {
    return;
  }
  await gallery.updateCaption(image.id, caption);
}

async function saveOrder() {
  const ids = ordered.value.map(image => image.id);
  if (ids.join() === images.value.map(image => image.id).join()) {
    return;
  }
  await gallery.reorder(ids);
}

async function setAsCover(image: RecipeGalleryImageOut) {
  const newKey = await gallery.setAsCover(image.id);
  if (newKey) {
    recipe.value.image = newKey;
    imageKey.value++;
    alert.success(i18n.t("recipe.gallery-cover-updated"));
  }
}

async function deleteImage() {
  if (imageToDelete.value) {
    await gallery.remove(imageToDelete.value.id);
    imageToDelete.value = null;
  }
}
</script>
