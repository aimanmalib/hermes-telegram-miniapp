/**
 * Demo banner text, kept out of the main language files so a production build
 * (where DEMO_ENABLED is constant false) drops it with the rest of demo mode.
 * `npm run check:no-demo` looks for it in dist/.
 */

import banner from "./demo.json";
import { getLang, type Lang } from "./index";

export const DEMO_BANNER: Record<Lang, string> = banner;

export function demoBannerText(): string {
  return DEMO_BANNER[getLang()];
}
