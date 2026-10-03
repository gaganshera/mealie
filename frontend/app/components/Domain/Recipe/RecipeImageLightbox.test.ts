import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, test, vi } from "vitest";
import { nextTick } from "vue";
import RecipeImageLightbox from "./RecipeImageLightbox.vue";

vi.mock("vuetify", () => ({
  useTheme: () => ({ global: { current: { value: { dark: false } } } }),
}));

const images = [
  { url: "/cover.webp", alt: "cover" },
  { url: "/one.webp", alt: "one", caption: "First" },
  { url: "/two.webp", alt: "two", caption: "Second" },
];

const wrappers: VueWrapper[] = [];

function mountLightbox(props: Record<string, unknown>) {
  const wrapper = mount(RecipeImageLightbox, {
    props: { "modelValue": true, ...props, "onUpdate:index": (i: number) => wrapper.setProps({ index: i }) },
    global: {
      mocks: { $globals: { icons: { close: "close", chevronLeft: "left", chevronRight: "right" } } },
      stubs: {
        VDialog: { props: ["modelValue"], template: "<div v-if=\"modelValue\"><slot /></div>" },
        VBtn: { props: ["disabled"], template: "<button type=\"button\" :disabled=\"disabled\"><slot /></button>" },
        VIcon: { template: "<span><slot /></span>" },
      },
    },
  });
  wrappers.push(wrapper);
  return wrapper;
}

function src(wrapper: VueWrapper) {
  return wrapper.find("img").attributes("src");
}

function keydown(key: string) {
  window.dispatchEvent(new KeyboardEvent("keydown", { key }));
}

describe("RecipeImageLightbox", () => {
  afterEach(() => {
    wrappers.forEach(wrapper => wrapper.unmount());
    wrappers.length = 0;
  });

  test("a single imageUrl still works", () => {
    const wrapper = mountLightbox({ imageUrl: "/single.webp", imageAlt: "single" });
    expect(src(wrapper)).toBe("/single.webp");
    expect(wrapper.find("img").attributes("alt")).toBe("single");
    expect(wrapper.find(".lightbox-prev").exists()).toBe(false);
    expect(wrapper.find(".lightbox-counter").exists()).toBe(false);
  });

  test("navigation stops at both ends", async () => {
    const wrapper = mountLightbox({ images, index: 0 });
    expect(src(wrapper)).toBe("/cover.webp");
    expect(wrapper.find(".lightbox-prev").attributes("disabled")).toBeDefined();

    await wrapper.find(".lightbox-prev").trigger("click");
    expect(src(wrapper)).toBe("/cover.webp");

    await wrapper.find(".lightbox-next").trigger("click");
    await wrapper.find(".lightbox-next").trigger("click");
    expect(src(wrapper)).toBe("/two.webp");
    expect(wrapper.find(".lightbox-next").attributes("disabled")).toBeDefined();
    expect(wrapper.find(".lightbox-counter").text()).toBe("3 / 3");
    expect(wrapper.find(".lightbox-caption").text()).toBe("Second");

    await wrapper.find(".lightbox-next").trigger("click");
    expect(src(wrapper)).toBe("/two.webp");
  });

  test("arrow keys browse the images", async () => {
    const wrapper = mountLightbox({ images, index: 1 });
    expect(src(wrapper)).toBe("/one.webp");

    keydown("ArrowRight");
    await nextTick();
    expect(src(wrapper)).toBe("/two.webp");

    keydown("ArrowRight");
    await nextTick();
    expect(src(wrapper)).toBe("/two.webp");

    for (let i = 0; i < 3; i++) {
      keydown("ArrowLeft");
      await nextTick();
    }
    expect(src(wrapper)).toBe("/cover.webp");
    expect(wrapper.find(".lightbox-counter").text()).toBe("1 / 3");
  });
});
