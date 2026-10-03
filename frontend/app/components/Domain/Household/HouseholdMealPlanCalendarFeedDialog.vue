<template>
  <BaseDialog
    v-model="dialog"
    :title="$t('meal-plan.calendar-feed')"
    :icon="$globals.icons.calendar"
    color="primary"
    width="700"
  >
    <v-card-text>
      <p class="mb-4">
        {{ $t("meal-plan.calendar-feed-description") }}
      </p>

      <template v-if="created">
        <v-alert type="warning" variant="tonal" density="compact" class="mb-4">
          {{ $t("meal-plan.calendar-feed-link-shown-once") }}
        </v-alert>
        <v-row
          v-for="link in createdLinks"
          :key="link.label"
          dense
        >
          <v-col cols="9">
            <v-text-field
              :model-value="link.url"
              :label="link.label"
              type="text"
              readonly
              variant="filled"
            />
          </v-col>
          <v-col cols="3" class="pl-1 mt-3">
            <AppButtonCopy :icon="false" color="info" :copy-text="link.url" />
          </v-col>
        </v-row>
      </template>

      <template v-else-if="status?.enabled">
        <p v-if="status.createdAt">
          {{ $t("meal-plan.calendar-feed-created", [$d(new Date(status.createdAt))]) }}
        </p>
        <p>
          {{ $t("meal-plan.calendar-feed-last-used", [status.lastAccessedAt ? $d(new Date(status.lastAccessedAt)) : $t("general.never")]) }}
        </p>
        <p class="mt-4 text-caption">
          {{ $t("meal-plan.regenerate-calendar-feed-description") }}
        </p>
      </template>
    </v-card-text>

    <template #custom-card-action>
      <template v-if="status?.enabled && !created">
        <BaseButton
          delete
          :loading="loading"
          :icon="$globals.icons.delete"
          @click="revoke"
        >
          {{ $t("meal-plan.revoke") }}
        </BaseButton>
        <BaseButton
          :loading="loading"
          :icon="$globals.icons.refresh"
          @click="create"
        >
          {{ $t("meal-plan.regenerate") }}
        </BaseButton>
      </template>
      <BaseButton
        v-else-if="status && !created"
        :loading="loading"
        :icon="$globals.icons.calendar"
        @click="create"
      >
        {{ $t("meal-plan.create-subscription-link") }}
      </BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { useUserApi } from "~/composables/api";
import { alert } from "~/composables/use-toast";
import AppButtonCopy from "~/components/global/AppButtonCopy.vue";
import BaseButton from "~/components/global/BaseButton.vue";
import BaseDialog from "~/components/global/BaseDialog.vue";
import type { CalendarFeedCreated, CalendarFeedStatus } from "~/lib/api/types/meal-plan";

const dialog = defineModel<boolean>({ required: true });

const i18n = useI18n();
const api = useUserApi();

const status = ref<CalendarFeedStatus | null>(null);
const created = ref<CalendarFeedCreated | null>(null);
const loading = ref(false);

const createdLinks = computed(() => {
  if (!created.value) return [];
  return [
    { label: i18n.t("meal-plan.calendar-feed-webcal-link"), url: created.value.webcalUrl },
    { label: i18n.t("meal-plan.calendar-feed-https-link"), url: created.value.url },
  ];
});

async function refreshStatus() {
  const { data } = await api.calendarFeed.getStatus();
  status.value = data;
}

async function create() {
  loading.value = true;
  const { data } = await api.calendarFeed.create();
  loading.value = false;

  if (!data) {
    alert.error(i18n.t("events.something-went-wrong"));
    return;
  }
  created.value = data;
  await refreshStatus();
}

async function revoke() {
  loading.value = true;
  const { response } = await api.calendarFeed.revoke();
  loading.value = false;

  if (response?.status !== 204) {
    alert.error(i18n.t("events.something-went-wrong"));
    return;
  }
  await refreshStatus();
}

// the link is only ever shown right after it was created, so forget it once the dialog closes
watch(dialog, (val) => {
  created.value = null;
  if (val) {
    refreshStatus();
  }
}, { immediate: true });
</script>
