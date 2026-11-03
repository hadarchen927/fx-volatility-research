# Public-release validation

Reviewed **3 November 2026**. This extends the 28 October technical release
with a public README, code guide, data attribution, locked dependencies and
a GitHub Actions workflow. The study settings, source snapshots and first
final-period evaluation remain those recorded on 23 October.

## Local verification

| Check | Result |
| --- | --- |
| Existing study tests | All 62 tests pass in the original Python environment. |
| Fresh installation | A separate Python 3.12.4 virtual environment installs the runtime dependencies successfully; `pip check` reports no broken requirements. |
| Fresh Git clone | Tests pass from a local Git clone of the public files, with no dependency on the working project path. |
| Offline reproduction | Both development and final stages complete in that clone using included snapshots. |
| Numerical equivalence | Quote/return/forecast counts, every split/year/gap score and publication audits match the original saved study. |
| Worked examples | All three completed examples run and match their references. |
| Frozen protocol | All five original code/configuration hashes match the local protocol record after Git checkout. |
| Data integrity | The original raw responses match their metadata hashes; raw and derived CSV bytes are retained. |
| Publication content | Public Markdown links and code-file coverage are checked; personal preparation notes and caches are excluded. |

The fresh environment uses **Matplotlib 3.8.4 and NumPy 1.26.4**. The
complete resolved runtime is recorded in
[requirements-lock.txt](../requirements-lock.txt). The original Anaconda
environment was not modified. Python 3.12 is the supported installation
target for this package.

The numerical algorithms use the standard library. NumPy is pinned for
compatibility with the plotting stack. Figure encodings can vary when
regenerated with a different rendering environment; the scientific checks
compare the numerical results. The [release manifest](release_manifest.json)
identifies the bytes of the published snapshot before regeneration.

## Verified study result

There are 4,097 quotes, 4,096 consecutive-observation returns and 4,076
scored forecasts after 20 warm-up returns. The 2025 final split contains
255 common targets:

| Model | Final MSE |
| --- | ---: |
| Rolling 20 | 4.507175055303078e-09 |
| EWMA 0.94 | 4.346710429933066e-09 |

EWMA MSE is **3.56% lower relative to rolling MSE**. This is descriptive
forecast-error evidence, not investment performance or a significance
result. The two-target development teaching example gives a different
percentage and is kept separate from this final comparison.

Independent numerical review also checked all 4,076 forecast records,
the first 2025 boundary and every annual/calendar-gap score. The original
3,821 development/validation rows form the unchanged prefix of the
combined forecast CSV.

## Git and packaging

`.gitattributes` preserves source/configuration LF line endings and saved
CSV/JSON bytes. A local commit/clone check is used to verify the frozen
files and package bytes before regeneration. The release manifest lists
public files and SHA-256 fingerprints, excluding itself from its own list.
It does not include private CV drafts, interview notes or dated schedules.

[The GitHub workflow](../.github/workflows/ci.yml) is configured for Python
3.12.4 on Windows and Ubuntu. Its syntax and command sequence have been
reviewed, and the commands have been exercised locally on Windows.
**GitHub-hosted jobs have not yet run**; their status is available after
upload. Linux execution is therefore configured, not claimed as verified.

## Reproduce

Use the environment setup in the [README](../README.md), then run:

```powershell
python -m unittest discover -s tests -v
python run_research.py --stage development --offline
python run_research.py --stage final --offline
python lessons/day10_rolling_exercise.py
python lessons/day11_ewma_exercise.py
python lessons/day12_mse_comparison.py
```

These are reproductions of an already evaluated experiment. The protocol
record is local provenance, not externally certified preregistration.
Code, tests and report drafting used AI assistance as a guided learning
project; personal contribution claims should reflect work actually checked.
