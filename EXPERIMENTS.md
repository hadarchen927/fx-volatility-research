# Research decisions and experiment record

## Fixed study

The study compares a rolling 20-return mean of squares with EWMA decay
0.94 for the next published EUR/USD interval's squared simple return.
The source is ECB series `EXR.D.USD.EUR.SP00.A`, in USD per EUR.

The choices were set before retrieving the long history, without a
hyperparameter search:

| Choice | Specification |
| --- | --- |
| Requested history | 2010–2025 |
| Development | 2010–2021 |
| Validation | 2022–2024 |
| Final evaluation | 2025 |
| Warm-up | First 20 returns, excluded from scoring |
| Primary loss | Squared error against the squared-return target |
| Calendar treatment | Preserve publication gaps; no daily scaling |
| Mean assumption | Zero conditional mean for variance interpretation |

January 2024 had already been inspected in the introductory analysis, so
it belongs to the development process rather than an untouched final test.
Validation did not select a replacement specification.

## Source-format repair during development

The first long-history parsing attempt stopped at an empty rate on
1 January 2010. Inspection identified nine empty `OBS_STATUS=H` rows,
all on verified holidays in 2010–2012. The parser was adjusted to skip
only empty holiday/weekend placeholders on nonpublication dates, while
preserving their original response bytes and recording them in metadata.
The numeric series then matched all expected publication dates.

This was a source-format repair before final access. It introduced no
imputed price, zero return or model-setting change.

## Protocol and first final-period access

On 23 October 2026, the development/validation snapshot was retrieved at
18:09:17 UTC. The [local protocol record](reports/research/protocol_lock.json)
was created at 18:09:20 UTC. The 2025 snapshot was retrieved at 18:09:57 UTC.
Its metadata and original response remain in `data/raw/`.

The final stage checks the recorded code/configuration and development
raw-data hashes before accessing its final snapshot. This local record
documents pipeline ordering; it is not externally certified preregistration.

## Outcome

EWMA recorded 1.75% lower development MSE, 1.81% lower validation MSE and
3.56% lower MSE across 255 final-period targets in 2025. No setting was
changed in response to that final result. The report retains exceptions,
including years where rolling performs better and very small gap groups.

Later work completed calculation examples, added tests and prepared public
documentation. The five frozen study files and the empirical scores were
retained. Dependency installation was separately checked for the public
package; this did not select a new model or retune the evaluation.

See [the research report](reports/research_report.md),
[validation](reports/validation_report.md) and
[data sources](DATA_SOURCES.md). These are descriptive historical results,
with no statistical-significance or trading-profit claim.
