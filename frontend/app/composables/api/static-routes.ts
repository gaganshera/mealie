function UnknownToString(ukn: string | unknown) {
  return typeof ukn === "string" ? ukn : "";
}

export const useStaticRoutes = () => {
  const { $config } = useNuxtApp();
  const prefix = `${$config.public.SUB_PATH}/api`.replace("//", "/");

  // Methods to Generate reference urls for assets/images *
  function recipeImage(recipeId: string, version: string | unknown = "", key: string | number = 1) {
    return `${prefix}/media/recipes/${recipeId}/images/original.webp?rnd=${key}&version=${UnknownToString(version)}`;
  }

  function recipeSmallImage(recipeId: string, version: string | unknown = "", key: string | number = 1) {
    return `${prefix}/media/recipes/${recipeId}/images/min-original.webp?rnd=${key}&version=${UnknownToString(
      version,
    )}`;
  }

  function recipeTinyImage(recipeId: string, version: string | unknown = "", key: string | number = 1) {
    return `${prefix}/media/recipes/${recipeId}/images/tiny-original.webp?rnd=${key}&version=${UnknownToString(
      version,
    )}`;
  }

  function recipeTimelineEventImage(recipeId: string, timelineEventId: string) {
    return `${prefix}/media/recipes/${recipeId}/images/timeline/${timelineEventId}/original.webp`;
  }

  function recipeTimelineEventSmallImage(recipeId: string, timelineEventId: string) {
    return `${prefix}/media/recipes/${recipeId}/images/timeline/${timelineEventId}/min-original.webp`;
  }

  function recipeTimelineEventTinyImage(recipeId: string, timelineEventId: string) {
    return `${prefix}/media/recipes/${recipeId}/images/timeline/${timelineEventId}/tiny-original.webp`;
  }

  function recipeGalleryImage(recipeId: string, imageId: string, size: "original" | "min" | "tiny" = "original") {
    const fileName = size === "original" ? "original.webp" : `${size}-original.webp`;
    return `${prefix}/media/recipes/${recipeId}/images/gallery/${imageId}/${fileName}`;
  }

  function recipeAssetPath(recipeId: string, assetName: string) {
    return `${prefix}/media/recipes/${recipeId}/assets/${assetName}`;
  }

  return {
    recipeImage,
    recipeSmallImage,
    recipeTinyImage,
    recipeTimelineEventImage,
    recipeTimelineEventSmallImage,
    recipeTimelineEventTinyImage,
    recipeGalleryImage,
    recipeAssetPath,
  };
};
