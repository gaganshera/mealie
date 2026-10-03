<template>
  <v-dialog
    v-model="model"
    fullscreen
    scrim="transparent"
    transition="fade-transition"
  >
    <div
      class="lightbox-content"
      :style="{ backgroundColor: scrimColor }"
      @click="onBackgroundClick"
    >
      <div ref="frameRef" class="lightbox-frame">
        <img
          v-if="current"
          :src="current.url"
          :alt="current.alt"
          class="lightbox-img"
          draggable="false"
          :style="imgStyle"
          @load="onImageLoad"
          @click="onImageClick"
          @pointerdown="onPointerDown"
          @pointermove="onPointerMove"
          @pointerup="onPointerUp"
          @pointercancel="onPointerUp"
        >
      </div>
      <template v-if="hasMultiple">
        <v-btn
          icon
          variant="text"
          class="lightbox-nav lightbox-prev"
          :disabled="!canPrev"
          :aria-label="$t('general.previous')"
          @click.stop="prev"
        >
          <v-icon>{{ $globals.icons.chevronLeft }}</v-icon>
        </v-btn>
        <v-btn
          icon
          variant="text"
          class="lightbox-nav lightbox-next"
          :disabled="!canNext"
          :aria-label="$t('general.next')"
          @click.stop="next"
        >
          <v-icon>{{ $globals.icons.chevronRight }}</v-icon>
        </v-btn>
      </template>
      <div
        v-if="hasMultiple || current?.caption"
        class="lightbox-footer"
        @click.stop
      >
        <div v-if="current?.caption" class="lightbox-caption">
          {{ current.caption }}
        </div>
        <div v-if="hasMultiple" class="lightbox-counter">
          {{ index + 1 }} / {{ items.length }}
        </div>
      </div>
      <v-btn
        icon
        variant="text"
        class="lightbox-close"
        :aria-label="$t('general.close')"
        @click.stop="model = false"
      >
        <v-icon>{{ $globals.icons.close }}</v-icon>
      </v-btn>
    </div>
  </v-dialog>
</template>

<script setup lang="ts">
import { useTheme } from "vuetify";

export interface LightboxImage {
  url: string;
  alt?: string;
  caption?: string | null;
}

interface Props {
  imageUrl?: string;
  imageAlt?: string;
  images?: LightboxImage[];
}

const props = defineProps<Props>();
const model = defineModel<boolean>({ required: true });
const index = defineModel<number>("index", { default: 0 });

// A single `imageUrl` is the same as a one-image list
const items = computed<LightboxImage[]>(() => {
  if (props.images?.length) {
    return props.images;
  }
  return props.imageUrl ? [{ url: props.imageUrl, alt: props.imageAlt }] : [];
});

const current = computed<LightboxImage | undefined>(() => items.value[index.value]);
const hasMultiple = computed(() => items.value.length > 1);
const canPrev = computed(() => index.value > 0);
const canNext = computed(() => index.value < items.value.length - 1);

const theme = useTheme();
const isDark = computed(() => theme.global.current.value.dark);

const scrimColor = computed(() =>
  isDark.value ? "rgba(0, 0, 0, 0.75)" : "rgba(255, 255, 255, 0.75)",
);

const imageShadow = computed(() =>
  isDark.value
    ? "0 0 24px rgba(255, 255, 255, 0.45), 0 0 140px rgba(255, 255, 255, 0.45)"
    : "0 6px 16px rgba(0, 0, 0, 0.55), 0 18px 80px rgba(0, 0, 0, 0.7)",
);

// The <img> box must be sized to the actual rendered pixels of the image (not the
// frame's bounding box) so the box-shadow/glow hugs the photo's real edges rather
// than the invisible letterboxed area object-fit:contain would otherwise leave.
const frameRef = ref<HTMLElement | null>(null);
const frameSize = reactive({ w: 0, h: 0 });
const naturalSize = reactive({ w: 0, h: 0 });

function updateFrameSize() {
  if (frameRef.value) {
    frameSize.w = frameRef.value.clientWidth;
    frameSize.h = frameRef.value.clientHeight;
  }
}

function onImageLoad(event: Event) {
  const img = event.target as HTMLImageElement;
  naturalSize.w = img.naturalWidth;
  naturalSize.h = img.naturalHeight;
  updateFrameSize();
}

function onKeydown(event: KeyboardEvent) {
  if (!model.value) {
    return;
  }
  if (event.key === "ArrowLeft") {
    prev();
  }
  else if (event.key === "ArrowRight") {
    next();
  }
}

onMounted(() => {
  updateFrameSize();
  window.addEventListener("resize", updateFrameSize);
  window.addEventListener("keydown", onKeydown);
});

onUnmounted(() => {
  window.removeEventListener("resize", updateFrameSize);
  window.removeEventListener("keydown", onKeydown);
});

const renderedSize = computed(() => {
  if (!naturalSize.w || !naturalSize.h || !frameSize.w || !frameSize.h) {
    return null;
  }

  const scale = Math.min(frameSize.w / naturalSize.w, frameSize.h / naturalSize.h);
  return { width: naturalSize.w * scale, height: naturalSize.h * scale };
});

const ZOOM_SCALE = 2;

const zoomed = ref(false);
const pan = reactive({ x: 0, y: 0 });
const dragging = ref(false);
const dragMoved = ref(false);
let dragStart = { x: 0, y: 0, panX: 0, panY: 0 };

// Keep the zoomed image overlapping its frame: at most half the overhang in each
// direction, so it can never be dragged completely out of view.
function applyPan(x: number, y: number) {
  const limitX = renderedSize.value
    ? Math.max(0, (renderedSize.value.width * ZOOM_SCALE - frameSize.w) / 2)
    : 0;
  const limitY = renderedSize.value
    ? Math.max(0, (renderedSize.value.height * ZOOM_SCALE - frameSize.h) / 2)
    : 0;

  pan.x = Math.min(Math.max(x, -limitX), limitX);
  pan.y = Math.min(Math.max(y, -limitY), limitY);
}

function resetZoom() {
  zoomed.value = false;
  pan.x = 0;
  pan.y = 0;
}

function prev() {
  if (canPrev.value) {
    resetZoom();
    index.value--;
  }
}

function next() {
  if (canNext.value) {
    resetZoom();
    index.value++;
  }
}

// Horizontal swipes browse the images while not zoomed in
const SWIPE_THRESHOLD = 50;
let swipeStart: { x: number; y: number } | null = null;

watch(model, (open) => {
  if (!open) {
    resetZoom();
  }
});

function onBackgroundClick() {
  model.value = false;
}

function onImageClick(event: MouseEvent) {
  event.stopPropagation();
  if (dragMoved.value) {
    dragMoved.value = false;
    return;
  }
  if (zoomed.value) {
    resetZoom();
  }
  else {
    zoomed.value = true;
  }
}

function onPointerDown(event: PointerEvent) {
  event.stopPropagation();
  if (!zoomed.value) {
    swipeStart = { x: event.clientX, y: event.clientY };
    (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
    return;
  }
  dragging.value = true;
  dragMoved.value = false;
  dragStart = { x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y };
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
}

function onPointerMove(event: PointerEvent) {
  if (!dragging.value) {
    return;
  }
  const dx = event.clientX - dragStart.x;
  const dy = event.clientY - dragStart.y;
  if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
    dragMoved.value = true;
  }
  applyPan(dragStart.panX + dx, dragStart.panY + dy);
}

function onPointerUp(event: PointerEvent) {
  event.stopPropagation();
  dragging.value = false;

  if (swipeStart && hasMultiple.value) {
    const dx = event.clientX - swipeStart.x;
    const dy = event.clientY - swipeStart.y;
    if (Math.abs(dx) > SWIPE_THRESHOLD && Math.abs(dx) > Math.abs(dy)) {
      // Swallow the click that follows the swipe, so it doesn't zoom in
      dragMoved.value = true;
      if (dx > 0) {
        prev();
      }
      else {
        next();
      }
    }
  }
  swipeStart = null;
}

const imgStyle = computed(() => ({
  ...(renderedSize.value
    ? { width: `${renderedSize.value.width}px`, height: `${renderedSize.value.height}px` }
    : {}),
  boxShadow: imageShadow.value,
  transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoomed.value ? ZOOM_SCALE : 1})`,
  transition: dragging.value ? "none" : "transform 0.2s ease, box-shadow 0.2s ease",
  cursor: zoomed.value ? "zoom-out" : "zoom-in",
}));
</script>

<style scoped>
.lightbox-content {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100vw;
  height: 100vh;
  cursor: zoom-out;
  transition: background-color 0.2s ease;
  overflow: hidden;
}

.lightbox-close {
  position: absolute;
  top: 12px;
  right: 12px;
}

.lightbox-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
}

.lightbox-prev {
  left: 12px;
}

.lightbox-next {
  right: 12px;
}

.lightbox-footer {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  max-width: 80vw;
  text-align: center;
  cursor: default;
}

.lightbox-caption {
  font-size: 1rem;
}

.lightbox-counter {
  font-size: 0.875rem;
  opacity: 0.8;
}

.lightbox-frame {
  width: 90vw;
  height: 90vh;
  display: flex;
  align-items: center;
  justify-content: center;
}

.lightbox-img {
  max-width: 100%;
  max-height: 100%;
  display: block;
  touch-action: none;
  user-select: none;
}
</style>
