# Code guide

This guide maps the public project's code, inputs and outputs. The study
compares two fixed EUR/USD squared-return forecasts; the
[README](README.md) explains reproduction and the
[research report](reports/research_report.md) explains results and
limitations.

The repository contains **seven root Python files**, **four test files**
and **three completed example scripts**. The implementation and report
were prepared with AI assistance as part of guided learning.

## Suggested reading order

1. Read `simple_return` in [fx_calculator.py](fx_calculator.py) to establish
   quotation and decimal-return units.
2. Read [research_data.py](research_data.py) alongside its tests: source
   bytes become validated quote records.
3. Read [forecast_models.py](forecast_models.py) alongside its tests:
   quotes become interval returns, causal forecasts and losses.
4. Read [run_research.py](run_research.py) and the pipeline tests to see
   configuration, protocol checks, target-date splits and output writing.
5. Run the three small completed examples below to inspect individual
   calculations.
6. Explore the three earlier teaching scripts for a smaller January 2024
   workflow, separate from the full research study.

## The seven root Python files

| File | Main responsibilities | Inputs and outputs |
| --- | --- | --- |
| [fx_calculator.py](fx_calculator.py) | Defines `simple_return(old_rate, new_rate)` and `payment_cost_sek`. Running its `main` prints artificial EUR/SEK examples. | Numeric rates/payment amounts in; numeric calculations out. The research imports only the currency-neutral return formula. |
| [research_data.py](research_data.py) | `download_snapshot` downloads or reuses a verified cache; `load_snapshot` and `parse_ecb_csv` validate it; `audit_quotes` checks the publication calendar and observations. | Requested dates and original CSV/metadata in; validated quote records and audit results out. Downloads save original bytes and provenance under `data/raw/`. Importing does not download. |
| [forecast_models.py](forecast_models.py) | `make_interval_returns` constructs returns/targets; `forecast_returns` generates rolling/EWMA forecasts before updating from their targets; `mse_comparison` scores them. | Quote or return records in; derived records and score dictionaries out. Functions work in memory, without downloading or writing reports. |
| [run_research.py](run_research.py) | CLI orchestration: `read_config`, `require_lock`, `split_name` and `run` connect data, models, protocol checks and plots. | Configuration, snapshots and the final-stage protocol record in; processed quotes, forecast CSVs, JSON summaries and PNG figures out. A development `--freeze` records or verifies the local protocol. |
| [download_fx_data.py](download_fx_data.py) | Earlier January 2024 teaching workflow: `get_snapshot` retrieves/reuses raw data; `parse_observations` validates it. | ECB response or saved snapshot in; original CSV, UTC retrieval metadata and a two-column working quote CSV out. |
| [audit_fx_data.py](audit_fx_data.py) | Checks the January teaching CSV's uniqueness, ordering, positive finite rates and expected publication dates. This is narrower than the research audit. | January working quotes in; console results and `reports/data_quality_report.json` out. |
| [analyze_fx_data.py](analyze_fx_data.py) | Reruns that audit, then `calculate_returns` and `describe_returns` compute interval returns, mean/sign counts and compounding checks; `save_plot` draws the overview. | January quotes in; interval-return CSV, `reports/return_summary.json` and `reports/fx_overview.png` out. |

EUR/SEK examples use SEK per euro; research data uses USD per euro. Do not
apply the SEK payment function to USD observations. The full research
pipeline is independent of the earlier download/audit/analysis entry
points, while reusing `simple_return`.

## Four test files

Run the suite from the project root:

```powershell
python -m unittest discover -s tests -v
```

The bundled [validation report](reports/validation_report.md) records
**62 passing tests**.

| Test file | Behavior checked |
| --- | --- |
| [tests/test_research_data.py](tests/test_research_data.py) | Series/units, invalid values and dates, flagged holiday placeholders, expected publication calendar, raw-file integrity and cache handling. Download tests use mocked responses and temporary files. |
| [tests/test_forecast_models.py](tests/test_forecast_models.py) | Hand-calculated forecasts, initialization, update order, unchanged earlier forecasts when future returns change, calendar gaps, invalid inputs, flat quotes, score interpretation and silent imports. |
| [tests/test_research_pipeline.py](tests/test_research_pipeline.py) | Configuration and split boundaries, history carried into the first final forecast, protocol checks before final-data access and offline behavior when saved data is missing. |
| [tests/test_learning_examples.py](tests/test_learning_examples.py) | The completed EWMA/scoring examples: known arithmetic, sign symmetry, invalid input lengths and undefined relative MSE for a zero rolling baseline. |

These are standard-library `unittest` tests covering source validation,
model behavior, integration and the numerical examples.

## Three completed example scripts and two fixtures

These examples read local files and print calculations. They do not
modify the model, snapshots or configuration.

| Example | Calculation and reference |
| --- | --- |
| [lessons/day10_rolling_exercise.py](lessons/day10_rolling_exercise.py) | `mean_squared_return` averages 20 earlier squared returns and checks the first scored rolling forecast, targeting 2 February 2010. |
| [lessons/day11_ewma_exercise.py](lessons/day11_ewma_exercise.py) | `ewma_update` combines the prior estimate and newly observed square, then checks the forecast targeting 3 February 2010. |
| [lessons/day12_mse_comparison.py](lessons/day12_mse_comparison.py) | `squared_error`, `mean_squared_error` and `relative_mse_change` score two development targets, then separately recalculate all 255 final-period targets and compare them with the saved summary. |

| Fixture | Contents |
| --- | --- |
| [lessons/day10_rolling_inputs.json](lessons/day10_rolling_inputs.json) | Twenty earlier returns, input dates and source fingerprints for the first rolling forecast. Its target return is excluded. |
| [lessons/day11_ewma_inputs.json](lessons/day11_ewma_inputs.json) | Prior forecast, newly observed return, fixed decay, origin/target dates and source fingerprints. The following target return is excluded. |

Keep the scripts and fixtures in their supplied locations. Their paths
are resolved relative to the scripts.

```powershell
python lessons/day10_rolling_exercise.py
python lessons/day11_ewma_exercise.py
python lessons/day12_mse_comparison.py
```

The two development illustrations in the scoring script are not the
255-target final sample.

## Configuration and support files

| File | Purpose |
| --- | --- |
| [study_config.json](study_config.json) | Fixed dates, splits, rolling window 20, EWMA decay 0.94, squared-simple-return target, MSE and zero-conditional-mean assumption. |
| [reports/research/protocol_lock.json](reports/research/protocol_lock.json) | UTC freeze record and code/configuration/development-data fingerprints. The final stage checks required fingerprints before accessing the final snapshot. It is a local audit trail, not externally certified preregistration. |
| [requirements.txt](requirements.txt) | Pins Matplotlib 3.8.4 and NumPy 1.26.4 for compatibility with the tested plotting stack. Model calculations and tests use the standard library. |
| [requirements-lock.txt](requirements-lock.txt) | Records the resolved runtime dependencies installed and tested in a fresh Python 3.12.4 environment for the public release. |
| [.gitattributes](.gitattributes) | Keeps Python and study-configuration text in LF format, preserves CSV/raw-response bytes and marks PNGs binary. Stable bytes support the recorded hashes. |
| [.gitignore](.gitignore) | Excludes local environments, Python caches, notebook checkpoints and `.env` from Git. It does not replace a review of files being published. |
| [.github/workflows/ci.yml](.github/workflows/ci.yml) | Configures tests, offline reproduction and worked examples on Windows and Ubuntu after upload. Local verification does not imply that the GitHub jobs have already run. |

The verified environment is Python 3.12.4 with Matplotlib 3.8.4. See the
README for environment setup.

## Data flow and generated artifacts

1. `run_research.py` reads the configuration and, for a final run, checks
   the bundled protocol.
2. `research_data.py` loads original bytes and metadata from
   [data/raw/](data/raw/), verifies integrity and audits numeric quotes.
3. `forecast_models.py` produces interval returns, forecasts and losses,
   using `fx_calculator.simple_return`.
4. The runner assigns splits by target date, summarizes by split/year/gap
   and writes [data/processed/](data/processed/) and
   [reports/research/](reports/research/).

The research output prefixes are `development_` and `final_`, followed
by `summary.json`, `forecasts.csv`, `annual_mse.png` or
`forecast_comparison.png`. The final-stage forecast CSV retains earlier
history too; select `split == "final"` for the 255 scored 2025 targets.

Forecast records retain previous/target dates, calendar gaps, simple
returns, squared targets, forecast origins, both forecasts/losses and
split labels. Summaries include provenance, audits, configuration, runtime
versions and scores. Plot monthly averages are for display; MSE uses
individual intervals.

## Reproduce the saved study

```powershell
python run_research.py --stage development --offline
python run_research.py --stage final --offline
```

Offline runs require the saved CSV/metadata pairs, make no downloads and
regenerate derived outputs. Reusing the bundled final results is
reproduction of the already evaluated study. Model or configuration
changes require a separately identified study rather than treating the
known 2025 outcomes as a fresh test.

Read the [experiment record](EXPERIMENTS.md) for implementation decisions
and the [research report](reports/research_report.md) for interpretation.
