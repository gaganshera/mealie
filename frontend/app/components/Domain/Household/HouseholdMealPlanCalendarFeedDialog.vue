<template>
  <BaseDialog
    v-model="dialog"
    :title="$t('meal-plan.calendar-feed-title')"
    :icon="$globals.icons.calendar"
    :cancel-text="$t('general.close')"
    width="700"
    :loading="loading"
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
          {{ $t("meal-plan.calendar-feed-copy-warning") }}
        </v-alert>
        <v-text-field
          v-for="link in createdLinks"
          :key="link.label"
          :model-value="link.url"
          :label="link.label"
          readonly
          variant="outlined"
          density="compact"
        >
          <template #append>
            <AppButtonCopy :copy-text="link.url" />
          </template>
        </v-text-field>
      </template>

      <template v-else-if="status?.enabled">
        <p class="font-weight-medium">
          {{ $t("meal-plan.calendar-feed-active") }}
        </p>
        <p v-if="status.createdAt">
          {{ $t("general.created-on-date", [$d(new Date(status.createdAt))]) }}
        </p>
        <p>
          {{
            status.lastAccessedAt
              ? $t("meal-plan.calendar-feed-last-used", [$d(new Date(status.lastAccessedAt))])
              : $t("meal-plan.calendar-feed-never-used")
          }}
        </p>
        <p class="text-caption mt-2">
          {{ $t("meal-plan.calendar-feed-regenerate-hint") }}
        </p>
      </template>
    </v-card-text>

    <template #custom-card-action>
      <template v-if="status?.enabled">
        <BaseButton
          delete
          :disabled="loading"
          @click="revoke"
        >
          {{ $t("meal-plan.calendar-feed-revoke") }}
        </BaseButton>
        <BaseButton
          :disabled="loading"
          @click="createFeed"
        >
          <template #icon>
            {{ $globals.icons.refresh }}
          </template>
          {{ $t("meal-plan.calendar-feed-regenerate") }}
        </BaseButton>
      </template>
      <BaseButton
        v-else-if="status"
        :disabled="loading"
        @click="createFeed"
      >
        <template #icon>
          {{ $globals.icons.calendar }}
        </template>
        {{ $t("meal-plan.calendar-feed-create") }}
      </BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { useUserApi } from "~/composables/api";
import { alert } from "~/composables/use-toast";
import type { CalendarFeedCreated, CalendarFeedStatus } from "~/lib/api/types/meal-plan";

const dialog = defineModel<boolean>({ default: false });

const i18n = useI18n();
const api = useUserApi();

const loading = ref(false);
const status = ref<CalendarFeedStatus | null>(null);
const created = ref<CalendarFeedCreated | null>(null);

const createdLinks = computed(() => {
  if (!created.value) {
    return [];
  }
  return [
    { label: i18n.t("meal-plan.calendar-feed-webcal-url"), url: created.value.webcalUrl },
    { label: i18n.t("meal-plan.calendar-feed-https-url"), url: created.value.url },
  ];
});

async function refreshStatus() {
  const { data } = await api.calendarFeed.getStatus();
  status.value = data;
}

async function createFeed() {
  loading.value = true;
  const { data } = await api.calendarFeed.create();
  if (data) {
    created.value = data;
    await refreshStatus();
  }
  loading.value = false;
}

async function revoke() {
  loading.value = true;
  const { response } = await api.calendarFeed.revoke();
  if (response?.status === 200) {
    created.value = null;
    alert.success(i18n.t("meal-plan.calendar-feed-revoked"));
  }
  await refreshStatus();
  loading.value = false;
}

// The link is only shown right after it is created, so forget it whenever the dialog closes
watch(dialog, async (open) => {
  created.value = null;
  if (open) {
    loading.value = true;
    await refreshStatus();
    loading.value = false;
  }
}, { immediate: true });
</script>
