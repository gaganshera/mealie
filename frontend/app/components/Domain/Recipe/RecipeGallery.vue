<template>
  <div v-if="isEditForm || images.length" class="px-4 pb-2 d-print-none">
    <div v-if="!isEditForm" class="d-flex ga-2 overflow-x-auto py-2">
      <v-img
        v-for="(image, i) in images"
        :key="image.id"
        :src="imageUrl(image.id, 'tiny')"
        :alt="image.caption || recipe.name"
        width="150"
        height="150"
        max-width="150"
        cover
        class="rounded flex-grow-0 flex-shrink-0"
        style="cursor: zoom-in"
        @click="openLightbox(i)"
      />
    </div>

    <template v-else>
      <div class="d-flex align-center flex-wrap ga-2 py-2">
        <h3 class="text-h6 font-weight-regular">
          {{ $t("recipe.gallery.title") }}
        </h3>
        <v-spacer />
        <BaseButton
          :icon="$globals.icons.upload"
          :loading="loading"
          @click="fileInput?.click()"
        >
          {{ $t("recipe.upload-images") }}
        </BaseButton>
        <input
          ref="fileInput"
          type="file"
          multiple
          accept="image/*,.heic,.avif"
          hidden
          @change="onFilesSelected"
        >
      </div>
      <p v-if="!images.length" class="text-medium-emphasis">
        {{ $t("recipe.gallery.no-images") }}
      </p>
      <VueDraggable
        v-model="images"
        handle=".handle"
        :delay="250"
        :delay-on-touch-only="true"
        :animation="200"
        @end="onDragEnd"
      >
        <div
          v-for="image in images"
          :key="image.id"
          class="d-flex align-center ga-2 mb-2"
        >
          <v-icon
            class="handle"
            style="cursor: grab"
            :title="$t('recipe.gallery.drag-to-reorder')"
          >
            {{ $globals.icons.arrowUpDown }}
          </v-icon>
          <v-img
            :src="imageUrl(image.id, 'tiny')"
            :alt="image.caption || recipe.name"
            width="80"
            height="80"
            max-width="80"
            cover
            class="rounded flex-grow-0 flex-shrink-0"
          />
          <v-text-field
            v-model="captions[image.id]"
            :label="$t('recipe.gallery.caption')"
            density="compact"
            variant="outlined"
            hide-details
            @blur="saveCaption(image.id)"
          />
          <v-btn
            icon
            variant="text"
            :title="$t('recipe.set-as-cover-image')"
            :aria-label="$t('recipe.set-as-cover-image')"
            @click="setCover(image.id)"
          >
            <v-icon>{{ $globals.icons.fileImage }}</v-icon>
          </v-btn>
          <v-btn
            icon
            variant="text"
            color="error"
            :title="$t('general.delete')"
            :aria-label="$t('general.delete')"
            @click="remove(image.id)"
          >
            <v-icon>{{ $globals.icons.delete }}</v-icon>
          </v-btn>
        </div>
      </VueDraggable>
    </template>

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

const recipe = defineModel<NoUndefinedField<Recipe>>({ required: true });

const { isEditForm, imageKey } = usePageState(recipe.value.slug);
const { recipeImage } = useStaticRoutes();
const { images, loading, load, upload, updateCaption, reorder, remove, setAsCover, imageUrl, lightboxImages: buildLightboxImages }
  = useRecipeGallery(recipe.value.id, recipe.value.slug);

onMounted(load);

// Editable copies of the captions, saved when the field loses focus
const captions = ref<Record<string, string>>({});
watch(images, (value) => {
  captions.value = Object.fromEntries(value.map(image => [image.id, image.caption ?? ""]));
}, { immediate: true });

async function saveCaption(imageId: string) {
  const caption = captions.value[imageId] ?? "";
  const image = images.value.find(i => i.id === imageId);
  if (!image || caption === (image.caption ?? "")) {
    return;
  }
  await updateCaption(imageId, caption);
}

const fileInput = ref<HTMLInputElement | null>(null);

async function onFilesSelected(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files ?? []);
  input.value = "";
  if (files.length) {
    await upload(files);
  }
}

function onDragEnd() {
  reorder(images.value.map(image => image.id));
}

async function setCover(imageId: string) {
  const newImage = await setAsCover(imageId);
  if (newImage) {
    recipe.value.image = newImage;
    imageKey.value++;
  }
}

const coverUrl = computed(() =>
  recipe.value.image ? recipeImage(recipe.value.id, recipe.value.image, imageKey.value) : null,
);
const lightboxImages = computed(() => buildLightboxImages(coverUrl.value, recipe.value.name));
const lightboxOpen = ref(false);
const lightboxIndex = ref(0);

function openLightbox(galleryIndex: number) {
  // The lightbox starts with the cover image, when there is one
  lightboxIndex.value = coverUrl.value ? galleryIndex + 1 : galleryIndex;
  lightboxOpen.value = true;
}
</script>
