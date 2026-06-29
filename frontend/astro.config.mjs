import { defineConfig } from "astro/config";
import tailwind from "@astrojs/tailwind";

// Static showcase. Snapshot-first; optional live mode reads PUBLIC_API_BASE.
export default defineConfig({
  integrations: [tailwind({ applyBaseStyles: false })],
  site: "https://example.com",
});
