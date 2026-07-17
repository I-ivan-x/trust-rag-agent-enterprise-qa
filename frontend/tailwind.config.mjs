/** Agent Reliability Lab — dark engineering control-room tokens. */
export default {
  content: ["./src/**/*.{astro,html,js,jsx,ts,tsx,vue,svelte,md,mdx}"],
  theme: {
    extend: {
      colors: {
        bg: "#070b10",
        surface: "#0d141c",
        "surface-2": "#121c26",
        line: "#263241",
        ink: "#f4f7fa",
        muted: "#b3beca",
        faint: "#8693a1",
        brand: "#35d399",
        auto: "#35d399",
        pending: "#f5b94c",
        escalate: "#f66b7a",
        detect: "#52d3f5",
        silver: "#b7c2ce",
      },
      fontFamily: {
        sans: ["Inter", "Segoe UI", "PingFang SC", "Microsoft YaHei", "system-ui", "sans-serif"],
        mono: ["Cascadia Code", "SFMono-Regular", "Consolas", "Liberation Mono", "monospace"],
      },
      maxWidth: { content: "1180px" },
    },
  },
  plugins: [],
};
