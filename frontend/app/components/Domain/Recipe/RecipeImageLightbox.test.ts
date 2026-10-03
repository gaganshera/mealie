import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, test, vi } from "vitest";
import { nextTick } from "vue";
import RecipeImageLightbox from "./RecipeImageLightbox.vue";

vi.mock("vuetify", () => ({
  useTheme: () => ({ global: { current: { value: { dark: false } } } }),
}));

const wrappers: VueWrapper[] = [];

const images = [
  { url: "/cover.webp", alt: "Cover" },
  { url: "/one.webp", alt: "One", caption: "First photo" },
  { url: "/two.webp", alt: "Two", caption: "Second photo" },
];

function mountLightbox(props: Record<string, unknown>) {
  const wrapper = mount(RecipeImageLightbox, {
    props: {
      "modelValue": true,
      "onUpdate:index": (value: number) => wrapper.setProps({ index: value }),
      ...props,
    },
    attachTo: document.body,
    global: {
      mocks: {
        $globals: { icons: { close: "close", chevronLeft: "chevronLeft", chevronRight: "chevronRight" } },
      },
      stubs: {
        VDialog: { template: "<div><slot /></div>" },
        VBtn: {
          props: ["disabled"],
          template: "<button :disabled=\"disabled\" @click=\"$emit('click', $event)\"><slot /></button>",
        },
        VIcon: { template: "<i><slot /></i>" },
      },
    },
  });
  wrappers.push(wrapper);
  return wrapper;
}

function imgSrc(wrapper: VueWrapper) {
  return wrapper.find("img").attributes("src");
}

describe("RecipeImageLightbox", () => {
  afterEach(() => {
    wrappers.splice(0).forEach(wrapper => wrapper.unmount());
  });

  test("a single imageUrl still works, without browsing controls", () => {
    const wrapper = mountLightbox({ imageUrl: "/single.webp", imageAlt: "Single" });

    expect(imgSrc(wrapper)).toBe("/single.webp");
    expect(wrapper.find("img").attributes("alt")).toBe("Single");
    expect(wrapper.find(".lightbox-prev").exists()).toBe(false);
    expect(wrapper.find(".lightbox-next").exists()).toBe(false);
    expect(wrapper.find(".lightbox-counter").exists()).toBe(false);
  });

  test("opens at the given index and shows the counter and caption", () => {
    const wrapper = mountLightbox({ images, index: 1 });

    expect(imgSrc(wrapper)).toBe("/one.webp");
    expect(wrapper.find(".lightbox-counter").text()).toBe("2 / 3");
    expect(wrapper.find(".lightbox-caption").text()).toBe("First photo");
  });

  test("arrow buttons browse and stop at both ends", async () => {
    const wrapper = mountLightbox({ images, index: 0 });

    expect(wrapper.find(".lightbox-prev").attributes("disabled")).toBeDefined();
    await wrapper.find(".lightbox-prev").trigger("click");
    expect(imgSrc(wrapper)).toBe("/cover.webp");

    await wrapper.find(".lightbox-next").trigger("click");
    expect(imgSrc(wrapper)).toBe("/one.webp");
    await wrapper.find(".lightbox-next").trigger("click");
    expect(imgSrc(wrapper)).toBe("/two.webp");

    expect(wrapper.find(".lightbox-next").attributes("disabled")).toBeDefined();
    await wrapper.find(".lightbox-next").trigger("click");
    expect(imgSrc(wrapper)).toBe("/two.webp");
    expect(wrapper.find(".lightbox-counter").text()).toBe("3 / 3");
  });

  test("arrow keys browse and stop at both ends", async () => {
    const wrapper = mountLightbox({ images, index: 0 });

    const press = async (key: string) => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key }));
      await nextTick();
    };

    await press("ArrowLeft");
    expect(imgSrc(wrapper)).toBe("/cover.webp");

    await press("ArrowRight");
    await press("ArrowRight");
    expect(imgSrc(wrapper)).toBe("/two.webp");

    await press("ArrowRight");
    expect(imgSrc(wrapper)).toBe("/two.webp");

    await press("ArrowLeft");
    expect(imgSrc(wrapper)).toBe("/one.webp");
  });

  test("arrow keys do nothing while closed", async () => {
    const wrapper = mountLightbox({ images, index: 0, modelValue: false });

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight" }));
    await nextTick();
    expect(wrapper.emitted("update:index")).toBeUndefined();
  });
});
