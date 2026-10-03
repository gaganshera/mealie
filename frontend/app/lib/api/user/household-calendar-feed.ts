import { BaseAPI } from "../base/base-clients";
import type { CalendarFeedCreated, CalendarFeedStatus } from "~/lib/api/types/meal-plan";

const prefix = "/api";

const routes = {
  base: `${prefix}/households/calendar-feed`,
};

export class HouseholdCalendarFeedAPI extends BaseAPI {
  async getStatus() {
    return await this.requests.get<CalendarFeedStatus>(routes.base);
  }

  async create() {
    return await this.requests.post<CalendarFeedCreated>(routes.base, {});
  }

  async revoke() {
    return await this.requests.delete(routes.base);
  }
}
