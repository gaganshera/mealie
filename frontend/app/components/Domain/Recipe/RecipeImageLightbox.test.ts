import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, test, vi } from "vitest";
import { defineComponent, h, nextTick } from "vue";
import RecipeImageLightbox from "./RecipeImageLightbox.vue";

vi.mock("vuetify", () => ({
  useTheme: () => ({ global: { current: { value: { dark: false } } } }),
}));

// Just enough of Vuetify to render the lightbox's own markup
const stubs = {
  VDialog: defineComponent({
    props: { modelValue: Boolean },
    setup: (props, { slots }) => () => (props.modelValue ? h("div", slots.default?.()) : null),
  }),
  VBtn: defineComponent({
    inheritAttrs: false,
    props: { disabled: Boolean },
    emits: ["click"],
    setup: (props, { slots, emit, attrs }) => () =>
      h("button", { class: attrs.class, disabled: props.disabled, onClick: (e: Event) => emit("click", e) }, slots.default?.()),
  }),
  VIcon: defineComponent({ setup: (_, { slots }) => () => h("i", slots.default?.()) }),
};

const images = [
  { url: "/cover.webp", alt: "Cover" },
  { url: "/one.webp", alt: "One", caption: "Grandma's card" },
  { url: "/two.webp", alt: "Two" },
];

function mountLightbox(props: Record<string, unknown>) {
  return mount(RecipeImageLightbox, {
    props: { modelValue: true, ...props },
    attachTo: document.body,
    global: {
      stubs,
      mocks: { $globals: { icons: { close: "close", chevronLeft: "left", chevronRight: "right" } } },
    },
  });
}

function src(wrapper: ReturnType<typeof mountLightbox>) {
  return wrapper.get("img").attributes("src");
}

// jsdom has no PointerEvent, but the handlers only read the coordinates a MouseEvent carries too
function swipe(wrapper: ReturnType<typeof mountLightbox>, fromX: number, toX: number) {
  const img = wrapper.get("img").element;
  img.dispatchEvent(new MouseEvent("pointerdown", { clientX: fromX, clientY: 100, bubbles: true }));
  img.dispatchEvent(new MouseEvent("pointerup", { clientX: toX, clientY: 110, bubbles: true }));
  return nextTick();
}

function pressKey(key: string) {
  window.dispatchEvent(new KeyboardEvent("keydown", { key }));
  return nextTick();
}

describe("RecipeImageLightbox", () => {
  let wrapper: ReturnType<typeof mountLightbox> | null = null;

  afterEach(() => {
    wrapper?.unmount();
    wrapper = null;
  });

  test("a single imageUrl still works, without browsing controls", () => {
    wrapper = mountLightbox({ imageUrl: "/only.webp", imageAlt: "Only" });

    expect(src(wrapper)).toBe("/only.webp");
    expect(wrapper.get("img").attributes("alt")).toBe("Only");
    expect(wrapper.find(".lightbox-prev").exists()).toBe(false);
    expect(wrapper.find(".lightbox-next").exists()).toBe(false);
    expect(wrapper.find(".lightbox-counter").exists()).toBe(false);
  });

  test("opens at the given index and shows the counter and caption", () => {
    wrapper = mountLightbox({ images, index: 1 });

    expect(src(wrapper)).toBe("/one.webp");
    expect(wrapper.get(".lightbox-counter").text()).toBe("2 / 3");
    expect(wrapper.get(".lightbox-caption").text()).toBe("Grandma's card");
  });

  test("the arrow buttons move between images and stop at both ends", async () => {
    wrapper = mountLightbox({ images, "index": 0, "onUpdate:index": (i: number) => wrapper?.setProps({ index: i }) });

    expect(wrapper.get(".lightbox-prev").attributes("disabled")).toBeDefined();

    await wrapper.get(".lightbox-next").trigger("click");
    await wrapper.get(".lightbox-next").trigger("click");
    expect(src(wrapper)).toBe("/two.webp");
    expect(wrapper.get(".lightbox-next").attributes("disabled")).toBeDefined();

    await wrapper.get(".lightbox-next").trigger("click");
    expect(src(wrapper)).toBe("/two.webp");
    expect(wrapper.emitted("update:index")).toEqual([[1], [2]]);

    await wrapper.get(".lightbox-prev").trigger("click");
    expect(src(wrapper)).toBe("/one.webp");
  });

  test("the arrow keys move between images and stop at both ends", async () => {
    // without a v-model:index binding the lightbox keeps the index itself
    wrapper = mountLightbox({ images });

    await pressKey("ArrowLeft");
    expect(src(wrapper)).toBe("/cover.webp");

    await pressKey("ArrowRight");
    expect(src(wrapper)).toBe("/one.webp");
    await pressKey("ArrowRight");
    await pressKey("ArrowRight");
    expect(src(wrapper)).toBe("/two.webp");

    await pressKey("ArrowLeft");
    expect(src(wrapper)).toBe("/one.webp");
  });

  test("a horizontal swipe moves between images", async () => {
    wrapper = mountLightbox({ images });

    await swipe(wrapper, 300, 150);
    expect(src(wrapper)).toBe("/one.webp");

    // too short to count as a swipe
    await swipe(wrapper, 300, 280);
    expect(src(wrapper)).toBe("/one.webp");

    await swipe(wrapper, 100, 250);
    expect(src(wrapper)).toBe("/cover.webp");
  });

  test("keys do nothing once the lightbox is closed", async () => {
    wrapper = mountLightbox({ images, modelValue: false });

    await pressKey("ArrowRight");
    await wrapper.setProps({ modelValue: true });
    expect(src(wrapper)).toBe("/cover.webp");
  });
});
