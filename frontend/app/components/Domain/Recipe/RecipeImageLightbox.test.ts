import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, test, vi } from "vitest";
import { nextTick, ref } from "vue";
import RecipeImageLightbox from "./RecipeImageLightbox.vue";

vi.mock("vuetify", () => ({
  useTheme: () => ({ global: { current: ref({ dark: false }) } }),
}));

const images = [
  { url: "/cover.webp", alt: "Cover" },
  { url: "/gallery-1.webp", alt: "Card", caption: "Grandma's recipe card" },
  { url: "/gallery-2.webp", alt: "" },
];

const wrappers: VueWrapper[] = [];

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
        $globals: { icons: { chevronLeft: "left", chevronRight: "right", close: "close" } },
      },
      stubs: {
        VDialog: {
          props: ["modelValue"],
          template: "<div v-if=\"modelValue\"><slot /></div>",
        },
        VBtn: {
          props: ["disabled"],
          template: "<button type=\"button\" :disabled=\"disabled\"><slot /></button>",
        },
        VIcon: { template: "<span><slot /></span>" },
      },
    },
  });
  wrappers.push(wrapper);
  return wrapper;
}

function keydown(key: string) {
  window.dispatchEvent(new KeyboardEvent("keydown", { key }));
}

function shownSrc(wrapper: VueWrapper) {
  return wrapper.find("img").attributes("src");
}

describe("RecipeImageLightbox", () => {
  afterEach(() => {
    wrappers.forEach(wrapper => wrapper.unmount());
    wrappers.length = 0;
  });

  test("a single imageUrl still works, without browsing controls", () => {
    const wrapper = mountLightbox({ imageUrl: "/single.webp", imageAlt: "Single" });

    expect(shownSrc(wrapper)).toBe("/single.webp");
    expect(wrapper.find("img").attributes("alt")).toBe("Single");
    expect(wrapper.find(".lightbox-prev").exists()).toBe(false);
    expect(wrapper.find(".lightbox-next").exists()).toBe(false);
    expect(wrapper.find(".lightbox-counter").exists()).toBe(false);
  });

  test("starts at the given index and shows the counter and caption", () => {
    const wrapper = mountLightbox({ images, index: 1 });

    expect(shownSrc(wrapper)).toBe("/gallery-1.webp");
    expect(wrapper.find(".lightbox-counter").text()).toBe("2 / 3");
    expect(wrapper.find(".lightbox-caption").text()).toBe("Grandma's recipe card");
  });

  test("arrow buttons browse and stop at both ends", async () => {
    const wrapper = mountLightbox({ images, index: 0 });
    const prev = () => wrapper.find(".lightbox-prev");
    const next = () => wrapper.find(".lightbox-next");

    expect(prev().attributes("disabled")).toBeDefined();
    await prev().trigger("click");
    expect(shownSrc(wrapper)).toBe("/cover.webp");

    await next().trigger("click");
    await next().trigger("click");
    expect(shownSrc(wrapper)).toBe("/gallery-2.webp");
    expect(wrapper.find(".lightbox-counter").text()).toBe("3 / 3");
    expect(next().attributes("disabled")).toBeDefined();

    await next().trigger("click");
    expect(shownSrc(wrapper)).toBe("/gallery-2.webp");

    await prev().trigger("click");
    expect(shownSrc(wrapper)).toBe("/gallery-1.webp");
  });

  test("arrow keys browse and stop at both ends", async () => {
    const wrapper = mountLightbox({ images, index: 0 });

    keydown("ArrowLeft");
    await nextTick();
    expect(shownSrc(wrapper)).toBe("/cover.webp");

    keydown("ArrowRight");
    await nextTick();
    expect(shownSrc(wrapper)).toBe("/gallery-1.webp");

    keydown("ArrowRight");
    keydown("ArrowRight");
    await nextTick();
    expect(shownSrc(wrapper)).toBe("/gallery-2.webp");

    keydown("ArrowLeft");
    await nextTick();
    expect(shownSrc(wrapper)).toBe("/gallery-1.webp");
  });

  test("arrow keys do nothing while closed", async () => {
    const onUpdateIndex = vi.fn();
    mountLightbox({ "images": images, "index": 0, "modelValue": false, "onUpdate:index": onUpdateIndex });

    keydown("ArrowRight");
    await nextTick();
    expect(onUpdateIndex).not.toHaveBeenCalled();
  });
});
