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
          {{ $t("meal-plan.calendar-feed-link-shown-once") }}
        </v-alert>
        <v-text-field
          :model-value="created.webcalUrl"
          :label="$t('meal-plan.calendar-feed-webcal-url')"
          readonly
          variant="outlined"
          density="compact"
        >
          <template #append>
            <AppButtonCopy :copy-text="created.webcalUrl" />
          </template>
        </v-text-field>
        <v-text-field
          :model-value="created.url"
          :label="$t('meal-plan.calendar-feed-https-url')"
          readonly
          variant="outlined"
          density="compact"
        >
          <template #append>
            <AppButtonCopy :copy-text="created.url" />
          </template>
        </v-text-field>
      </template>

      <template v-else-if="status?.enabled">
        <p v-if="status.createdAt">
          {{ $t("meal-plan.calendar-feed-created-at", [$d(new Date(status.createdAt))]) }}
        </p>
        <p>
          {{ $t("meal-plan.calendar-feed-last-used", [status.lastAccessedAt ? $d(new Date(status.lastAccessedAt)) : $t("general.never")]) }}
        </p>
      </template>
    </v-card-text>

    <template #card-actions>
      <v-spacer />
      <template v-if="status?.enabled">
        <BaseButton
          delete
          :loading="loading"
          @click="revoke"
        >
          {{ $t("meal-plan.calendar-feed-revoke") }}
        </BaseButton>
        <BaseButton
          :icon="$globals.icons.refresh"
          :loading="loading"
          @click="create"
        >
          {{ $t("meal-plan.calendar-feed-regenerate") }}
        </BaseButton>
      </template>
      <BaseButton
        v-else
        create
        :loading="loading"
        @click="create"
      >
        {{ $t("meal-plan.create-subscription-link") }}
      </BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { whenever } from "@vueuse/core";
import { useUserApi } from "~/composables/api";
import type { CalendarFeedCreated, CalendarFeedStatus } from "~/lib/api/types/meal-plan";

const dialog = defineModel<boolean>({ default: false });

const api = useUserApi();
const status = ref<CalendarFeedStatus | null>(null);
const created = ref<CalendarFeedCreated | null>(null);
const loading = ref(false);

async function refreshStatus() {
  const { data } = await api.calendarFeed.getStatus();
  status.value = data;
}

whenever(
  () => dialog.value,
  () => {
    created.value = null;
    refreshStatus();
  },
);

async function create() {
  loading.value = true;
  const { data } = await api.calendarFeed.create();
  if (data) {
    created.value = data;
  }
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
</script>
