<template>
  <BaseDialog
    v-model="dialog"
    :title="$t('meal-plan.calendar-feed.title')"
    :icon="$globals.icons.calendar"
    color="primary"
    width="600"
    @close="created = null"
  >
    <v-card-text>
      <p class="mb-4">
        {{ $t("meal-plan.calendar-feed.description") }}
      </p>

      <template v-if="created">
        <v-alert
          type="warning"
          variant="tonal"
          class="mb-4"
        >
          {{ $t("meal-plan.calendar-feed.link-shown-once") }}
        </v-alert>
        <div
          v-for="link in links"
          :key="link.label"
          class="d-flex align-center ga-2"
        >
          <v-text-field
            :model-value="link.url"
            :label="link.label"
            readonly
            variant="filled"
          />
          <AppButtonCopy
            :copy-text="link.url"
            class="mb-5"
          />
        </div>
      </template>
      <template v-else-if="status?.enabled">
        <p>{{ $t("meal-plan.calendar-feed.created-at", { date: formatDate(status.createdAt) }) }}</p>
        <p>{{ $t("meal-plan.calendar-feed.last-used-at", { date: formatDate(status.lastAccessedAt) }) }}</p>
        <p class="mt-4 text-medium-emphasis">
          {{ $t("meal-plan.calendar-feed.regenerate-description") }}
        </p>
      </template>
    </v-card-text>

    <template #custom-card-action>
      <template v-if="status?.enabled">
        <BaseButton
          delete
          :loading="loading"
          :text="$t('meal-plan.calendar-feed.revoke')"
          class="mr-2"
          @click="revoke"
        />
        <BaseButton
          :loading="loading"
          :icon="$globals.icons.refresh"
          :text="$t('meal-plan.calendar-feed.regenerate')"
          @click="create"
        />
      </template>
      <BaseButton
        v-else-if="status"
        create
        :loading="loading"
        :text="$t('meal-plan.calendar-feed.create-link')"
        @click="create"
      />
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { useUserApi } from "~/composables/api";
import { alert } from "~/composables/use-toast";
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
    { label: i18n.t("meal-plan.calendar-feed.webcal-url"), url: created.value.webcalUrl },
    { label: i18n.t("meal-plan.calendar-feed.https-url"), url: created.value.url },
  ];
});

function formatDate(value: string | null | undefined) {
  return value ? i18n.d(new Date(value), "short") : i18n.t("general.never");
}

async function refreshStatus() {
  const { data } = await api.calendarFeed.getStatus();
  status.value = data;
}

watch(dialog, (open) => {
  if (open) refreshStatus();
}, { immediate: true });

async function create() {
  loading.value = true;
  const { data } = await api.calendarFeed.create();
  if (data) {
    created.value = data;
    await refreshStatus();
  }
  else {
    alert.error(i18n.t("meal-plan.calendar-feed.error"));
  }
  loading.value = false;
}

async function revoke() {
  loading.value = true;
  const { data } = await api.calendarFeed.revoke();
  if (data) {
    status.value = data;
    created.value = null;
    alert.success(i18n.t("meal-plan.calendar-feed.revoked"));
  }
  else {
    alert.error(i18n.t("meal-plan.calendar-feed.error"));
  }
  loading.value = false;
}
</script>
