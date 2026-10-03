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
    props: { modelValue: true, ...props },
    attachTo: document.body,
    global: {
      mocks: {
        $globals: { icons: { close: "close", chevronLeft: "chevronLeft", chevronRight: "chevronRight" } },
      },
      stubs: {
        VDialog: { template: "<div><slot /></div>" },
        VIcon: { template: "<i><slot /></i>" },
        VBtn: {
          props: ["disabled"],
          template: "<button type=\"button\" :disabled=\"disabled\"><slot /></button>",
        },
      },
    },
  });
  wrappers.push(wrapper);
  return wrapper;
}

function src(wrapper: VueWrapper) {
  return wrapper.find("img").attributes("src");
}

async function press(key: string) {
  window.dispatchEvent(new KeyboardEvent("keydown", { key }));
  await nextTick();
}

describe("recipeImageLightbox", () => {
  afterEach(() => {
    wrappers.forEach(wrapper => wrapper.unmount());
    wrappers.length = 0;
  });

  test("shows a single imageUrl without navigation", () => {
    const wrapper = mountLightbox({ imageUrl: "/only.webp", imageAlt: "Only" });

    expect(src(wrapper)).toBe("/only.webp");
    expect(wrapper.find("img").attributes("alt")).toBe("Only");
    expect(wrapper.find(".lightbox-prev").exists()).toBe(false);
    expect(wrapper.find(".lightbox-next").exists()).toBe(false);
    expect(wrapper.find(".lightbox-counter").exists()).toBe(false);
  });

  test("navigation buttons stop at both ends", async () => {
    const wrapper = mountLightbox({ images, "index": 0, "onUpdate:index": (i: number) => wrapper.setProps({ index: i }) });

    expect(src(wrapper)).toBe("/cover.webp");
    expect(wrapper.find(".lightbox-counter").text()).toBe("1 / 3");
    expect(wrapper.find(".lightbox-prev").attributes("disabled")).toBeDefined();

    await wrapper.find(".lightbox-next").trigger("click");
    expect(src(wrapper)).toBe("/one.webp");
    expect(wrapper.find(".lightbox-caption").text()).toBe("First photo");

    await wrapper.find(".lightbox-next").trigger("click");
    expect(src(wrapper)).toBe("/two.webp");
    expect(wrapper.find(".lightbox-counter").text()).toBe("3 / 3");
    expect(wrapper.find(".lightbox-next").attributes("disabled")).toBeDefined();

    await wrapper.find(".lightbox-next").trigger("click");
    expect(src(wrapper)).toBe("/two.webp");
    expect(wrapper.emitted("update:index")).toEqual([[1], [2]]);

    await wrapper.find(".lightbox-prev").trigger("click");
    expect(src(wrapper)).toBe("/one.webp");
  });

  test("arrow keys browse the images", async () => {
    const wrapper = mountLightbox({ images, "index": 1, "onUpdate:index": (i: number) => wrapper.setProps({ index: i }) });
    expect(src(wrapper)).toBe("/one.webp");

    await press("ArrowRight");
    expect(src(wrapper)).toBe("/two.webp");

    await press("ArrowRight");
    expect(src(wrapper)).toBe("/two.webp");

    await press("ArrowLeft");
    await press("ArrowLeft");
    expect(src(wrapper)).toBe("/cover.webp");

    await press("ArrowLeft");
    expect(src(wrapper)).toBe("/cover.webp");
    expect(wrapper.emitted("update:index")).toEqual([[2], [1], [0]]);
  });

  test("arrow keys do nothing when closed", async () => {
    const wrapper = mountLightbox({ images, modelValue: false, index: 0 });

    await press("ArrowRight");
    expect(wrapper.emitted("update:index")).toBeUndefined();
  });
});
