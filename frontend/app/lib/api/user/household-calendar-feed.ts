import { BaseAPI } from "../base/base-clients";
import type { CalendarFeedCreated, CalendarFeedStatus } from "~/lib/api/types/meal-plan";

const prefix = "/api";

const routes = {
  calendarFeed: `${prefix}/households/calendar-feed`,
};

export class HouseholdCalendarFeedAPI extends BaseAPI {
  async getStatus() {
    return await this.requests.get<CalendarFeedStatus>(routes.calendarFeed);
  }

  /** Creates the feed link, replacing any existing one. The returned URLs are only available once. */
  async create() {
    return await this.requests.post<CalendarFeedCreated>(routes.calendarFeed, {});
  }

  async revoke() {
    return await this.requests.delete(routes.calendarFeed);
  }
}
