<template>
  <v-img
    :key="imageKey"
    :max-width="maxWidth"
    min-height="50"
    cover
    width="100%"
    :height="hideImage ? undefined : imageHeight"
    :src="recipeImageUrl"
    class="d-print-none"
    :style="hideImage ? undefined : 'cursor: zoom-in'"
    v-bind="$attrs"
    @error="hideImage = true"
    @click="openLightbox"
  />
  <RecipeImageLightbox
    v-if="lightboxOpen"
    v-model="lightboxOpen"
    v-model:index="lightboxIndex"
    :images="lightboxImages(recipe.id, recipe.name, recipeFullImageUrl)"
  />
</template>

<script setup lang="ts">
import { useStaticRoutes, useUserApi } from "~/composables/api";
import type { HouseholdSummary } from "~/lib/api/types/household";
import { usePageState, usePageUser } from "~/composables/recipe-page/shared-state";
import { useRecipeGallery } from "~/composables/recipes/use-recipe-gallery";
import type { Recipe } from "~/lib/api/types/recipe";
import type { NoUndefinedField } from "~/lib/api/types/non-generated";

interface Props {
  recipe: NoUndefinedField<Recipe>;
  maxWidth?: string;
}
const props = withDefaults(defineProps<Props>(), {
  maxWidth: undefined,
});

const display = useDisplay();
const { recipeImage, recipeSmallImage } = useStaticRoutes();
const { imageKey } = usePageState(props.recipe.slug);
const { user } = usePageUser();

const recipeHousehold = ref<HouseholdSummary>();
if (user) {
  const userApi = useUserApi();
  userApi.households.getOne(props.recipe.householdId).then(({ data }) => {
    recipeHousehold.value = data || undefined;
  });
}

const { lightboxImages } = useRecipeGallery(props.recipe.slug);

const hideImage = ref(false);
const lightboxOpen = ref(false);
const lightboxIndex = ref(0);

function openLightbox() {
  if (hideImage.value) {
    return;
  }
  // The cover image comes first, followed by the gallery
  lightboxIndex.value = 0;
  lightboxOpen.value = true;
}

const imageHeight = computed(() => {
  return display.xs.value ? "200" : "400";
});

const recipeFullImageUrl = computed(() => {
  return recipeImage(props.recipe.id, props.recipe.image, imageKey.value);
});

const recipeImageUrl = computed(() => {
  return display.smAndDown.value
    ? recipeSmallImage(props.recipe.id, props.recipe.image, imageKey.value)
    : recipeFullImageUrl.value;
});

watch(
  () => recipeImageUrl.value,
  () => {
    hideImage.value = false;
  },
);
</script>
