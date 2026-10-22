import type { Status } from "../../api/types";
import type { FindingFilter } from "../../domain/review";

export type FilterAction =
  | { type: "toggleStatus"; status: Status }
  | { type: "document"; document: string | null }
  | { type: "onlyOpen"; value: boolean }
  | { type: "query"; value: string }
  | { type: "reset" };

export const initialFilter: FindingFilter = { statuses: new Set(), document: null, onlyOpen: false, query: "" };

export function filterReducer(state: FindingFilter, action: FilterAction): FindingFilter {
  switch (action.type) {
    case "toggleStatus": {
      const statuses = new Set(state.statuses);
      if (statuses.has(action.status)) statuses.delete(action.status);
      else statuses.add(action.status);
      return { ...state, statuses };
    }
    case "document":
      return { ...state, document: action.document };
    case "onlyOpen":
      return { ...state, onlyOpen: action.value };
    case "query":
      return { ...state, query: action.value };
    case "reset":
      return initialFilter;
  }
}
