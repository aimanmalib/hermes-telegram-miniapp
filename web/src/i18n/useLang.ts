import { useSyncExternalStore } from "react";
import { getLang, subscribeLang, type Lang } from "./index";

/** Re-render when the language changes (used once, at the app root). */
export function useLang(): Lang {
  return useSyncExternalStore(subscribeLang, getLang, getLang);
}
