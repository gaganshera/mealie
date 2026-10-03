import { BaseAPI } from "../base/base-clients";
import type { CalendarFeedCreated, CalendarFeedStatus } from "~/lib/api/types/meal-plan";
import type { SuccessResponse } from "~/lib/api/types/response";

const prefix = "/api";

const routes = {
  calendarFeed: `${prefix}/households/calendar-feed`,
};

export class HouseholdCalendarFeedAPI extends BaseAPI {
  async getStatus() {
    return await this.requests.get<CalendarFeedStatus>(routes.calendarFeed);
  }

  async create() {
    return await this.requests.post<CalendarFeedCreated>(routes.calendarFeed, {});
  }

  async revoke() {
    return await this.requests.delete<SuccessResponse>(routes.calendarFeed);
  }
}
