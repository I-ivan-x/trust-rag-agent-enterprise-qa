# Security Policy

## Maintenance target

Current `main` is the best-effort maintenance target. The immutable
`v3.0-q4-reliability` tag remains the latest stable product/reference tag; it
is not patched in place. Q5 is a completed research track and is not a product
release. No support or response-time SLA is implied.

## Reporting a vulnerability

Do not include credentials, personal data, exploit payloads, or sensitive
deployment details in a public issue. Use the repository host's private
security-advisory channel when available. If no private channel is available,
contact the repository owner through a private account channel before
publishing technical details.

Please include:

- affected commit or stable tag;
- affected component and entry point;
- minimal reproduction steps using synthetic data;
- expected and observed authorization boundary;
- whether the issue can produce disclosure, unsafe tool execution, approval
  bypass, or evidence/Claim tampering.

Acknowledgement and remediation timing depend on severity and reproducibility.
No bounty or response-time commitment is implied.

## Security boundaries

- Model output is untrusted until it passes typed validation, evidence binding,
  role/capability reauthorization, approval routing, and side-effect guards.
- Demonstration data is synthetic and cannot become formal Claim evidence.
- Secrets, PII, private endpoints, ignored runtime output, and unclassified
  data roots fail the public-repository gate.
- Historical evaluation artifacts remain immutable; current public conclusions
  are generated from the Claim registry.
- Real provider credentials belong only in local ignored environment files.
  Never commit `.env`, access tokens, API keys, or provider responses containing
  private prompts or customer data.

## Dependency advisories

Frontend production and development dependencies currently record no known
vulnerability in the tracked audit. Lighthouse 13.4.1 closes the former
Sentry/OpenTelemetry development chain described in
`frontend/DEPENDENCY_SECURITY.md`; high and critical npm findings remain
release-blocking. Advisory evidence must be refreshed before a later release
that changes either lockfile.
