# Capacitor 8.5.2 dependency hold — 2026-09-14

## Decision

Keep `@capacitor/core`, `@capacitor/cli`, `@capacitor/android`, and
`@capacitor/ios` pinned at 8.4.2. Do not merge the partial Dependabot updates for
Core or CLI, and do not publish a mixed 8.4/8.5 native toolchain.

## Evidence

The complete matched 8.5.2 set was evaluated from a clean npm lock update. Its
Android and iOS projects generated successfully. Both source verifiers passed,
including the new iOS scene template and Capacitor bridge. The upgrade was then
rejected by the existing dependency-security gate:

- `@capacitor/cli@8.5.2` adds `xcode@3.0.1`;
- `xcode@3.0.1` resolves `uuid@7.0.3`;
- npm reports `GHSA-w5hq-g745-h8pq`, a moderate buffer-bounds advisory affecting
  that UUID version; and
- the exact lock reports three moderate findings through this dependency chain.

The audit's forced remediation would downgrade the CLI rather than provide a
reviewed compatible 8.5.x resolution. Overriding `xcode`'s declared UUID major
range with a later incompatible major would be an unverified build-tool patch,
so Ask Crump will not do that.

After the rejection, the package manifest and npm lock were restored to the
reviewed 8.4.2 set. The working tree again produced no package diff.

## Re-entry gate

Reconsider the matched Capacitor upgrade only when an official stable release
removes or updates the vulnerable transitive chain, or when the advisory is
authoritatively withdrawn. Then require all of the following before release:

1. one aligned Core/CLI/Android/iOS version set;
2. clean `npm ci`, dependency-tree, and moderate-or-higher audit results;
3. fresh Android and iOS project generation;
4. Android Java 21 compilation and macOS iOS Release compilation;
5. native privacy, metadata, signing-source, and store packet gates; and
6. the complete Python, JavaScript, browser-control, and accessibility suites.

This is a supply-chain hold, not evidence of a current customer-facing defect.
The production 8.4.2 runtime remains unchanged.
