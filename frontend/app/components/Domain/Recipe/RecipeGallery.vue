<template>
  <div
    v-if="isOwnGroup && (edit || images.length)"
    class="my-4 d-print-none"
  >
    <div
      v-if="edit"
      class="d-flex align-center mb-2"
    >
      <span class="text-h6">{{ $t("recipe.gallery") }}</span>
      <v-spacer />
      <BaseButton
        :loading="uploading"
        :icon="$globals.icons.upload"
        @click="fileInput?.click()"
      >
        {{ $t("recipe.upload-images") }}
      </BaseButton>
      <input
        ref="fileInput"
        type="file"
        accept="image/*,.heic"
        multiple
        hidden
        @change="onFilesSelected"
      >
    </div>
    <VueDraggable
      v-model="images"
      :disabled="!edit"
      :animation="200"
      class="d-flex ga-2"
      :class="edit ? 'flex-wrap' : 'overflow-x-auto'"
      @end="reorder"
    >
      <div
        v-for="(image, i) in images"
        :key="image.id"
        class="gallery-item"
      >
        <v-img
          :src="recipeGalleryImage(recipe.id, image.id, 'tiny-original')"
          :alt="image.caption || recipe.name"
          width="150"
          height="150"
          cover
          class="rounded"
          :style="{ cursor: edit ? 'grab' : 'zoom-in' }"
          @click="openLightbox(i)"
        />
        <template v-if="edit">
          <v-text-field
            v-model="image.caption"
            :label="$t('recipe.gallery-caption')"
            density="compact"
            variant="underlined"
            hide-details
            @change="updateCaption(image.id, image.caption ?? null)"
          />
          <div class="d-flex justify-space-between">
            <v-btn
              icon
              variant="text"
              size="small"
              :title="$t('recipe.set-as-cover-image')"
              @click="setCover(image.id)"
            >
              <v-icon>{{ $globals.icons.star }}</v-icon>
            </v-btn>
            <v-btn
              icon
              variant="text"
              size="small"
              color="error"
              :title="$t('general.delete')"
              @click="remove(image.id)"
            >
              <v-icon>{{ $globals.icons.delete }}</v-icon>
            </v-btn>
          </div>
        </template>
      </div>
    </VueDraggable>
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
import RecipeImageLightbox from "~/components/Domain/Recipe/RecipeImageLightbox.vue";
import { useStaticRoutes } from "~/composables/api";
import { usePageState } from "~/composables/recipe-page/shared-state";
import { useRecipeGallery } from "~/composables/recipes/use-recipe-gallery";
import { useLoggedInState } from "~/composables/use-logged-in-state";
import type { Recipe } from "~/lib/api/types/recipe";
import type { NoUndefinedField } from "~/lib/api/types/non-generated";

interface Props {
  edit?: boolean;
}
const props = withDefaults(defineProps<Props>(), {
  edit: false,
});
const recipe = defineModel<NoUndefinedField<Recipe>>({ required: true });

const { isOwnGroup } = useLoggedInState();
const { recipeImage, recipeGalleryImage } = useStaticRoutes();
const { imageKey } = usePageState(recipe.value.slug);
const { images, uploading, refresh, upload, updateCaption, reorder, remove, setAsCover, lightboxImages }
  = useRecipeGallery(recipe.value.slug);

const fileInput = ref<HTMLInputElement | null>(null);
const lightboxOpen = ref(false);
const lightboxIndex = ref(0);

const coverUrl = computed(() =>
  recipe.value.image ? recipeImage(recipe.value.id, recipe.value.image, imageKey.value) : undefined,
);

onMounted(() => {
  if (isOwnGroup.value) {
    refresh();
  }
});

function openLightbox(galleryIndex: number) {
  if (props.edit) {
    return;
  }
  lightboxIndex.value = galleryIndex + (coverUrl.value ? 1 : 0);
  lightboxOpen.value = true;
}

async function onFilesSelected(event: Event) {
  const input = event.target as HTMLInputElement;
  await upload(Array.from(input.files ?? []));
  input.value = "";
}

async function setCover(imageId: string) {
  const image = await setAsCover(imageId);
  if (image) {
    recipe.value.image = image;
    imageKey.value++;
  }
}
</script>

<style scoped>
.gallery-item {
  width: 150px;
  flex-shrink: 0;
}
</style>
