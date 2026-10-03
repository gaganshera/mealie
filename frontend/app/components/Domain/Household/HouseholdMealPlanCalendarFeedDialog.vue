<template>
  <BaseDialog
    v-model="dialog"
    :title="$t('meal-plan.calendar-feed-title')"
    :icon="$globals.icons.calendar"
  >
    <v-card-text>
      <p class="mb-4">
        {{ $t("meal-plan.calendar-feed-description") }}
      </p>
      <template v-if="created">
        <v-alert
          type="warning"
          variant="tonal"
          density="compact"
          class="mb-4"
        >
          {{ $t("meal-plan.calendar-feed-link-warning") }}
        </v-alert>
        <div
          v-for="link in links"
          :key="link.label"
          class="d-flex align-center ga-2 mb-2"
        >
          <v-text-field
            :model-value="link.url"
            :label="link.label"
            readonly
            variant="filled"
            hide-details
          />
          <AppButtonCopy :copy-text="link.url" />
        </div>
      </template>
      <template v-if="status?.enabled">
        <p v-if="status.createdAt">
          {{ $t("meal-plan.calendar-feed-created", [$d(new Date(status.createdAt))]) }}
        </p>
        <p>
          {{
            status.lastAccessedAt
              ? $t("meal-plan.calendar-feed-last-used", [$d(new Date(status.lastAccessedAt))])
              : $t("meal-plan.calendar-feed-never-used")
          }}
        </p>
      </template>
    </v-card-text>
    <template #custom-card-action>
      <template v-if="status?.enabled">
        <BaseButton
          delete
          :loading="loading"
          @click="revoke"
        >
          {{ $t("meal-plan.revoke") }}
        </BaseButton>
        <BaseButton
          :icon="$globals.icons.refresh"
          :loading="loading"
          @click="create"
        >
          {{ $t("meal-plan.regenerate") }}
        </BaseButton>
      </template>
      <BaseButton
        v-else
        :icon="$globals.icons.calendar"
        :loading="loading"
        @click="create"
      >
        {{ $t("meal-plan.create-subscription-link") }}
      </BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { useUserApi } from "~/composables/api";
import type { CalendarFeedCreated, CalendarFeedStatus } from "~/lib/api/types/meal-plan";

const dialog = defineModel<boolean>("modelValue", { type: Boolean, default: false });

const i18n = useI18n();
const api = useUserApi();

const status = ref<CalendarFeedStatus | null>(null);
const created = ref<CalendarFeedCreated | null>(null);
const loading = ref(false);

const links = computed(() => {
  if (!created.value) return [];
  return [
    { label: i18n.t("meal-plan.calendar-feed-webcal-url"), url: created.value.webcalUrl },
    { label: i18n.t("meal-plan.calendar-feed-https-url"), url: created.value.url },
  ];
});

async function refreshStatus() {
  const { data } = await api.calendarFeed.getStatus();
  status.value = data;
}

async function create() {
  loading.value = true;
  const { data } = await api.calendarFeed.create();
  created.value = data;
  await refreshStatus();
  loading.value = false;
}

async function revoke() {
  loading.value = true;
  await api.calendarFeed.revoke();
  created.value = null;
  await refreshStatus();
  loading.value = false;
}

watch(dialog, (open) => {
  if (open) {
    refreshStatus();
  }
  else {
    // the link is only shown once
    created.value = null;
  }
});
</script>
