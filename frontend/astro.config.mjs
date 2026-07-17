import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";

// Static showcase. Snapshot-first; optional live mode reads PUBLIC_API_BASE.
export default defineConfig({
  output: "static",
  site: "https://example.com",
  vite: {
    plugins: [tailwindcss()],
  },
});
