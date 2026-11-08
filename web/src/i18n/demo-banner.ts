/**
 * Demo pill text, kept out of the main language files so a production build
 * (where DEMO_ENABLED is constant false) drops it with the rest of demo mode.
 * `npm run check:no-demo` looks for it in dist/.
 */

import texts from "./demo.json";
import { getLang, type Lang } from "./index";

export interface DemoText {
  /** Short label in the header pill. */
  pill: string;
  /** Longer explanation, used as the pill's title / accessible name. */
  detail: string;
}

export const DEMO_TEXT: Record<Lang, DemoText> = texts;

export function demoText(): DemoText {
  return DEMO_TEXT[getLang()];
}
