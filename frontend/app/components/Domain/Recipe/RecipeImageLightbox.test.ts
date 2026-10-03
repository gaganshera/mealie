import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, test, vi } from "vitest";
import { nextTick } from "vue";
import RecipeImageLightbox, { type LightboxImage } from "./RecipeImageLightbox.vue";

vi.mock("vuetify", () => ({
  useTheme: () => ({ global: { current: { value: { dark: false } } } }),
}));

const wrappers: VueWrapper[] = [];

const images: LightboxImage[] = [
  { url: "/cover.webp", alt: "Cover" },
  { url: "/one.webp", alt: "One", caption: "Grandma's card" },
  { url: "/two.webp", alt: "Two", caption: null },
];

function mountLightbox(props: Record<string, unknown>) {
  const wrapper = mount(RecipeImageLightbox, {
    props: {
      "modelValue": true,
      "onUpdate:index": (value: number) => wrapper.setProps({ index: value }),
      ...props,
    },
    global: {
      mocks: {
        $globals: { icons: { close: "close", chevronLeft: "chevronLeft", chevronRight: "chevronRight" } },
      },
      stubs: {
        VDialog: { template: "<div><slot /></div>" },
        VIcon: { template: "<i><slot /></i>" },
        VBtn: {
          props: ["disabled"],
          emits: ["click"],
          template: "<button type=\"button\" :disabled=\"disabled\" @click=\"$emit('click', $event)\"><slot /></button>",
        },
      },
    },
    attachTo: document.body,
  });

  wrappers.push(wrapper);
  return wrapper;
}

function shownImage(wrapper: VueWrapper) {
  return wrapper.find("img").attributes("src");
}

function pressKey(key: string) {
  window.dispatchEvent(new KeyboardEvent("keydown", { key }));
}

describe("RecipeImageLightbox", () => {
  afterEach(() => {
    wrappers.forEach(wrapper => wrapper.unmount());
    wrappers.length = 0;
  });

  test("a single imageUrl still works, without navigation", () => {
    const wrapper = mountLightbox({ imageUrl: "/single.webp", imageAlt: "Single" });

    expect(shownImage(wrapper)).toBe("/single.webp");
    expect(wrapper.find("img").attributes("alt")).toBe("Single");
    expect(wrapper.find("[data-testid='lightbox-prev']").exists()).toBe(false);
    expect(wrapper.find("[data-testid='lightbox-next']").exists()).toBe(false);
    expect(wrapper.find("[data-testid='lightbox-counter']").exists()).toBe(false);
  });

  test("arrow buttons browse and stop at both ends", async () => {
    const wrapper = mountLightbox({ images, index: 0 });

    expect(shownImage(wrapper)).toBe("/cover.webp");
    expect(wrapper.find("[data-testid='lightbox-counter']").text()).toBe("1 / 3");
    expect(wrapper.find("[data-testid='lightbox-prev']").attributes("disabled")).toBeDefined();

    await wrapper.find("[data-testid='lightbox-prev']").trigger("click");
    expect(shownImage(wrapper)).toBe("/cover.webp");

    await wrapper.find("[data-testid='lightbox-next']").trigger("click");
    expect(shownImage(wrapper)).toBe("/one.webp");
    expect(wrapper.find("[data-testid='lightbox-caption']").text()).toBe("Grandma's card");
    expect(wrapper.find("[data-testid='lightbox-counter']").text()).toBe("2 / 3");

    await wrapper.find("[data-testid='lightbox-next']").trigger("click");
    expect(shownImage(wrapper)).toBe("/two.webp");
    expect(wrapper.find("[data-testid='lightbox-caption']").exists()).toBe(false);
    expect(wrapper.find("[data-testid='lightbox-next']").attributes("disabled")).toBeDefined();

    await wrapper.find("[data-testid='lightbox-next']").trigger("click");
    expect(shownImage(wrapper)).toBe("/two.webp");
    expect(wrapper.emitted("update:index")?.map(([value]) => value)).toEqual([1, 2]);
  });

  test("arrow keys browse and stop at both ends", async () => {
    const wrapper = mountLightbox({ images, index: 1 });

    pressKey("ArrowLeft");
    await nextTick();
    expect(shownImage(wrapper)).toBe("/cover.webp");

    pressKey("ArrowLeft");
    await nextTick();
    expect(shownImage(wrapper)).toBe("/cover.webp");

    for (let i = 0; i < 3; i++) {
      pressKey("ArrowRight");
      await nextTick();
    }
    expect(shownImage(wrapper)).toBe("/two.webp");
    expect(wrapper.emitted("update:index")?.map(([value]) => value)).toEqual([0, 1, 2]);
  });

  test("keys do nothing while the lightbox is closed", async () => {
    const wrapper = mountLightbox({ images, index: 0, modelValue: false });

    pressKey("ArrowRight");
    await nextTick();
    expect(wrapper.emitted("update:index")).toBeUndefined();
  });
});
