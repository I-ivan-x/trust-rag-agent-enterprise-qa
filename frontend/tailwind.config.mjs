/** TrustRAG Showcase — premium dark technical theme.
 *  Enterprise Gateway pattern (sober, high-integrity) — deliberately NOT the
 *  skill's default neon/cyberpunk palette. Emerald = the fail-closed/trust accent;
 *  semantic state colors mirror the governance model (auto / pending / escalate).
 */
export default {
  content: ["./src/**/*.{astro,html,js,jsx,ts,tsx,vue,svelte,md,mdx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0a0e16",
        surface: "#111726",
        "surface-2": "#161d2e",
        line: "#232b3d",
        ink: "#e6edf6",
        muted: "#8b97ad",
        faint: "#5b6678",
        brand: "#34d399", // emerald — trust / fail-closed / pass
        "brand-weak": "#0f2a23",
        auto: "#34d399", // committed / auto
        pending: "#fbbf24", // pending_approval
        escalate: "#fb7185", // escalated / blocked / danger
        detect: "#60a5fa", // conditions / info
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "PingFang SC", "Microsoft YaHei", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        card: "0 1px 0 0 rgba(255,255,255,0.03) inset, 0 8px 30px rgba(0,0,0,0.35)",
        glow: "0 0 0 1px rgba(52,211,153,0.25), 0 0 40px rgba(52,211,153,0.12)",
      },
      borderRadius: { xl2: "14px" },
      maxWidth: { content: "1120px" },
    },
  },
  plugins: [],
};
