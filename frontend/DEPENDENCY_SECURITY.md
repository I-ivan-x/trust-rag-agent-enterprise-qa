# Frontend dependency security baseline

Verified on 2026-07-27 with Node.js 24.15.0 and npm 11.12.1. CI uses the
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
- `npm audit --json`: 0 vulnerabilities across the full development tree.
- `npm audit --omit=dev --json`: 0 vulnerabilities.
- `npm run build`: produces one static page; no SSR or server islands.
- `npm ls vite esbuild`: one Vite 8.1.5 resolution and esbuild 0.28.1.

## Lighthouse advisory closure

Lighthouse was patched from 13.4.0 to 13.4.1. That release removes the
vulnerable `@sentry/node` / OpenTelemetry / minimatch chain previously reported
as 16 moderate and 3 high entries by the current npm advisory database.
The lock now contains 330 packages and the full online audit reports zero
known vulnerabilities. CI continues to fail on any future high or critical
finding, and the lock-bound public repository audit fails when the dependency
record is not refreshed.
