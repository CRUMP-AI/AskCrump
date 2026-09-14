# Retina brand-mark delivery release — 2026-09-14

## Outcome

Ask Crump's application shell now uses a lossless 320×357 WebP delivery derivative for the Crump
mark. The largest live use is 86 CSS pixels, so the derivative still supplies more than three device
pixels per CSS pixel on a 3× phone display. The 640×714 WebP and original PNG remain available as
larger-format masters, but neither is loaded by the active application shell.

The delivered mark falls from 243,926 bytes to 81,150 bytes, saving 162,776 bytes (66.7%) from the
previous WebP runtime asset and 272,563 bytes (77.1%) from the PNG master. Together with the existing
104,568-byte workspace lockup, startup brand-image source bytes fall from 348,494 to 185,718 bytes,
a further 46.7% reduction. Against the original two PNGs, the combined reduction is 311,280 bytes
(62.6%).

The application keeps its established preload, eager decode, explicit dimensions, layout, labels,
and destinations. This deliberately avoids reintroducing the sign-in/logo flicker that can occur
when the first visible mark is deferred.

## Visual proof

The delivery derivative was generated losslessly from the reviewed 640×714 WebP. Automated
compositing on the application background compared it with the master at 86, 172, and 258 rendered
pixels—the 1×, 2×, and 3× display cases for the largest live use. Maximum per-channel RMS difference
was below 0.65 on a 0–255 scale at every size. The reviewed derivative is 81,150 bytes with SHA-256
`97a95059ad0997ffb88a78d6b3dca655eaf6efbd7945fcd60eacc7d494649917`.

## Pre-deployment evidence

A five-variant constrained-mobile audit first isolated image scheduling from image size. Removing
both the preload and eager load improved the synthetic LCP, but would weaken the proven flicker
boundary. Replacing only the asset with the 320-pixel derivative produced the same synthetic timing
range while keeping the mark eager and stable. The candidate asset in that exploratory audit was
locally fulfilled, so those numbers are directional and are not presented as production performance
proof.

The retained production audit compares the hosted 320-pixel asset with the hosted 640-pixel asset
under identical alternating browser contexts. Production acceptance requires exact MIME and bytes,
no request for the full-size runtime mark or retired PNGs, successful image decoding, no browser
error, no layout shift above 0.01, and a clean phone/tablet/desktop control matrix.

## Production acceptance

Pending deployment and hosted verification.

## Boundaries

This release changes only the delivery size of the existing Crump mark. It does not alter artwork,
layout, button behavior, destinations, authentication, customer data, analytics, AI providers,
generation behavior, payments, pricing, database objects, or marketing publication. Performance
improvement will be claimed only if the hosted alternating comparison supports it. The first valid
D1 cohort read remains the next funnel decision boundary on 2026-09-15 UTC.
