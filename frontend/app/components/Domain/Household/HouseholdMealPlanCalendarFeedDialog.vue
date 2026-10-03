<template>
  <BaseDialog
    v-model="dialog"
    :title="$t('meal-plan.calendar-feed.title')"
    :icon="$globals.icons.calendar"
    :loading="loading"
    width="650"
  >
    <v-card-text>
      <p class="mb-4">
        {{ $t("meal-plan.calendar-feed.description") }}
      </p>

      <template v-if="created">
        <v-alert type="warning" variant="tonal" density="compact" class="mb-4">
          {{ $t("meal-plan.calendar-feed.link-shown-once") }}
        </v-alert>
        <div
          v-for="link in createdLinks"
          :key="link.label"
          class="d-flex align-center ga-2 mb-2"
        >
          <v-text-field
            :model-value="link.url"
            :label="link.label"
            readonly
            hide-details
            density="compact"
            variant="outlined"
          />
          <AppButtonCopy :copy-text="link.url" />
        </div>
      </template>

      <template v-else-if="status?.enabled">
        <p>
          {{ $t("meal-plan.calendar-feed.created-at", [status.createdAt ? $d(new Date(status.createdAt), "long") : $t("general.never")]) }}
        </p>
        <p>
          {{ $t("meal-plan.calendar-feed.last-used-at", [status.lastAccessedAt ? $d(new Date(status.lastAccessedAt), "long") : $t("general.never")]) }}
        </p>
        <p class="text-caption mt-2">
          {{ $t("meal-plan.calendar-feed.regenerate-warning") }}
        </p>
      </template>
    </v-card-text>

    <v-card-actions v-if="!created" class="justify-end">
      <template v-if="status?.enabled">
        <BaseButton
          delete
          :icon="$globals.icons.delete"
          :disabled="loading"
          @click="revoke"
        >
          {{ $t("meal-plan.calendar-feed.revoke") }}
        </BaseButton>
        <BaseButton
          :icon="$globals.icons.refresh"
          :disabled="loading"
          @click="create"
        >
          {{ $t("meal-plan.calendar-feed.regenerate") }}
        </BaseButton>
      </template>
      <BaseButton
        v-else
        :icon="$globals.icons.calendar"
        :disabled="loading || status === null"
        @click="create"
      >
        {{ $t("meal-plan.calendar-feed.create-link") }}
      </BaseButton>
    </v-card-actions>
  </BaseDialog>
</template>

<script setup lang="ts">
import { useUserApi } from "~/composables/api";
import type { CalendarFeedCreated, CalendarFeedStatus } from "~/lib/api/types/meal-plan";

const dialog = defineModel<boolean>({ default: false });

const i18n = useI18n();
const api = useUserApi();

const loading = ref(false);
const status = ref<CalendarFeedStatus | null>(null);
const created = ref<CalendarFeedCreated | null>(null);

const createdLinks = computed(() => {
  if (!created.value) return [];
  return [
    { label: i18n.t("meal-plan.calendar-feed.webcal-url"), url: created.value.webcalUrl },
    { label: i18n.t("meal-plan.calendar-feed.https-url"), url: created.value.url },
  ];
});

async function refreshStatus() {
  loading.value = true;
  const { data } = await api.mealplanCalendarFeed.getStatus();
  status.value = data;
  loading.value = false;
}

async function create() {
  loading.value = true;
  const { data } = await api.mealplanCalendarFeed.create();
  created.value = data;
  loading.value = false;
}

async function revoke() {
  loading.value = true;
  await api.mealplanCalendarFeed.revoke();
  loading.value = false;
  await refreshStatus();
}

watch(dialog, (open) => {
  if (open) {
    created.value = null;
    refreshStatus();
  }
}, { immediate: true });
</script>
