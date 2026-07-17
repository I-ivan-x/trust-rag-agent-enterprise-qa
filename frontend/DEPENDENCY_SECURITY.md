# Frontend dependency security baseline

Verified on 2026-07-18 with Node.js 24.15.0 and npm 11.12.1. CI uses the
minimum supported project runtime, Node.js 22.19.0.

## Before

The baseline lock resolved Astro 4.16.19, Vite 5.4.21, esbuild 0.21.5,
`@astrojs/tailwind` 5.1.5, and Tailwind CSS 3.4.19. `npm audit --json`
reported 1 moderate, 2 high, and 0 critical vulnerabilities. The high findings
were in the Astro/Vite development-server chain.

## After

The supported static toolchain is Astro 7.1.1, Vite 8.1.5, esbuild 0.28.1,
Tailwind CSS 4.3.3 through `@tailwindcss/vite` 4.3.3, and `@lucide/astro`
1.25.0. The deprecated `@astrojs/tailwind` and `lucide-astro` packages are
absent from the lock.

- `npm audit --audit-level=high`: passes; high=0 and critical=0.
- `npm audit --omit=dev --json`: 0 vulnerabilities.
- `npm run build`: produces one static page; no SSR or server islands.
- `npm ls vite esbuild`: one Vite 8.1.5 resolution and esbuild 0.28.1.

## Accepted moderate advisory

The full development tree reports 17 moderate entries. They all fan out from
`GHSA-8988-4f7v-96qf`, an unbounded W3C Baggage allocation issue in
`@opentelemetry/core` 1.30.1, through the pinned Lighthouse 13.4.0 CLI's
`@sentry/node` dependency and its instrumentation packages.

Reachability was checked rather than dismissed solely as “dev-only”:

- `npm ls @sentry/node @opentelemetry/core` has a single root path:
  `lighthouse -> @sentry/node -> @opentelemetry/*`.
- `npm audit --omit=dev` is clean, so this path is absent from the production
  dependency tree.
- A recursive scan of `dist/` finds no Sentry, OpenTelemetry, or W3C Baggage
  code in the shipped static assets.
- Lighthouse is invoked only as an offline acceptance CLI against the local
  static preview. The published site does not run the CLI, expose its Sentry
  instrumentation, or accept inbound W3C Baggage headers through it.

The moderate advisory is therefore accepted for the local audit tool while CI
continues to fail on any high or critical finding. This acceptance must be
revisited when Lighthouse updates its Sentry/OpenTelemetry chain or if the
site stops being static.
