# Crump Code benchmark fixtures

These deliberately small repositories are fixed source material for the private Crump Code quality
benchmark. Each case contains a narrow defect or planning problem plus an acceptance file.

The benchmark manifest pins the Git revision that first contains these fixtures. Candidate patches
may change only the allowlisted implementation paths. Acceptance files are immutable benchmark
evidence and must never be changed by a candidate.

The fixtures contain no credentials, personal data, network calls, dependency installation, or
production configuration. They are excluded from the Vercel function bundle.
