"""Explainable forecasts of the next observed FX interval's squared return.

Rolling and EWMA forecasts approximate conditional return variance under a
zero conditional mean assumption. They forecast each observed quote interval:
calendar gaps are retained as metadata, without daily scaling or annualization.
All functions are pure; importing this module does not fetch or write data.
"""

from datetime import date
import math
from numbers import Real

from fx_calculator import simple_return


def _finite_number(value, label):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be a finite number.")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number.")
    return number


def _iso_date(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO date (YYYY-MM-DD).")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO date (YYYY-MM-DD).") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{label} must be an ISO date (YYYY-MM-DD).")
    return parsed


def _record_list(records, label):
    if not isinstance(records, list):
        raise ValueError(f"{label} must be a list of records.")
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"{label}[{index}] must be a record.")


def _field(record, key, label):
    if key not in record:
        raise ValueError(f"{label} is missing {key!r}.")
    return record[key]


def _mean(values):
    # Divide first so a mean of large, finite nonnegative values does not
    # overflow merely because their unscaled sum would overflow.
    count = len(values)
    return math.fsum(value / count for value in values)


def make_interval_returns(quotes):
    """Return consecutive simple returns and their unscaled squared targets.

    ``quotes`` is a chronological list of ``date`` (YYYY-MM-DD) and positive
    finite ``usd_per_eur`` records. Zero or one quote gives an empty list.
    Invalid quotes, duplicate dates, and reverse chronology raise ValueError.
    """
    _record_list(quotes, "quotes")
    validated = []
    for index, quote in enumerate(quotes):
        label = f"quotes[{index}]"
        quote_date = _iso_date(_field(quote, "date", label), f"{label}.date")
        rate = _finite_number(
            _field(quote, "usd_per_eur", label), f"{label}.usd_per_eur"
        )
        if rate <= 0:
            raise ValueError(f"{label}.usd_per_eur must be positive.")
        if validated and quote_date <= validated[-1][0]:
            raise ValueError("Quote dates must be strictly increasing.")
        validated.append((quote_date, rate))

    returns = []
    for (previous_date, previous_rate), (current_date, current_rate) in zip(
        validated, validated[1:]
    ):
        interval_return = simple_return(previous_rate, current_rate)
        target = interval_return * interval_return
        if not math.isfinite(interval_return) or not math.isfinite(target):
            raise ValueError("A quote interval produces a nonfinite return or target.")
        returns.append(
            {
                "previous_date": previous_date.isoformat(),
                "date": current_date.isoformat(),
                "calendar_gap_days": (current_date - previous_date).days,
                "simple_return": interval_return,
                "target_squared_return": target,
            }
        )
    return returns


def _validate_returns(returns):
    _record_list(returns, "returns")
    targets = []
    previous_end = None
    for index, record in enumerate(returns):
        label = f"returns[{index}]"
        start = _iso_date(
            _field(record, "previous_date", label), f"{label}.previous_date"
        )
        end = _iso_date(_field(record, "date", label), f"{label}.date")
        if end <= start:
            raise ValueError(f"{label} must end after its previous_date.")
        if previous_end is not None and start != previous_end:
            raise ValueError("Return intervals must be chronological and contiguous.")
        gap = _field(record, "calendar_gap_days", label)
        if isinstance(gap, bool) or not isinstance(gap, int) or gap != (end - start).days:
            raise ValueError(f"{label}.calendar_gap_days must match its dates.")
        interval_return = _finite_number(
            _field(record, "simple_return", label), f"{label}.simple_return"
        )
        if interval_return <= -1:
            raise ValueError(f"{label}.simple_return must be greater than -1 for positive FX quotes.")
        target = _finite_number(
            _field(record, "target_squared_return", label),
            f"{label}.target_squared_return",
        )
        expected_target = interval_return * interval_return
        if target < 0 or not math.isfinite(expected_target) or not math.isclose(
            target, expected_target, rel_tol=1e-12, abs_tol=0.0
        ):
            raise ValueError(f"{label}.target_squared_return must equal simple_return squared.")
        targets.append(target)
        previous_end = end
    return targets


def _squared_loss(forecast, target):
    error = forecast - target
    loss = error * error
    if not math.isfinite(loss):
        raise ValueError("A squared forecast error exceeds finite numeric range.")
    return loss


def forecast_returns(returns, window=20, decay=0.94):
    """Forecast squared returns using only earlier observed return intervals.

    At target index ``i``, rolling uses squares ``i-window:i``. EWMA is seeded
    with the first ``window`` squares; after emitting a forecast it updates as
    ``decay * forecast + (1 - decay) * target``. Thus the first scored index is
    ``window`` and its forecast origin is that interval's ``previous_date``.

    At least ``window + 1`` valid, contiguous returns are required; insufficient
    history raises ValueError. Input records are copied and never modified.
    """
    if isinstance(window, bool) or not isinstance(window, int) or window < 1:
        raise ValueError("window must be an integer greater than or equal to 1.")
    decay = _finite_number(decay, "decay")
    if not 0 < decay < 1:
        raise ValueError("decay must be strictly between 0 and 1.")
    targets = _validate_returns(returns)
    if len(targets) <= window:
        raise ValueError(
            f"At least {window + 1} interval returns are required for window={window}."
        )

    forecasts = []
    ewma = _mean(targets[:window])
    for index in range(window, len(targets)):
        target = targets[index]
        rolling = _mean(targets[index - window : index])
        forecast = dict(returns[index])
        forecast.update(
            {
                "forecast_origin": returns[index]["previous_date"],
                "rolling_forecast": rolling,
                "ewma_forecast": ewma,
                "rolling_loss": _squared_loss(rolling, target),
                "ewma_loss": _squared_loss(ewma, target),
            }
        )
        forecasts.append(forecast)
        # The current target becomes available only after its forecast is saved.
        ewma = decay * ewma + (1 - decay) * target
    return forecasts


def mse_comparison(forecasts):
    """Summarize squared forecast errors on the same scored intervals.

    Relative MSE change is ``ewma_mse / rolling_mse - 1``: negative favors EWMA,
    positive favors rolling. It is None when rolling MSE is zero (even if both
    MSEs are zero). Empty input and invalid or negative losses raise ValueError.
    """
    _record_list(forecasts, "forecasts")
    if not forecasts:
        raise ValueError("At least one forecast is required to compare MSE.")
    losses = {"rolling_loss": [], "ewma_loss": []}
    for index, forecast in enumerate(forecasts):
        label = f"forecasts[{index}]"
        for key in losses:
            loss = _finite_number(_field(forecast, key, label), f"{label}.{key}")
            if loss < 0:
                raise ValueError(f"{label}.{key} must be nonnegative.")
            losses[key].append(loss)
    rolling_mse = _mean(losses["rolling_loss"])
    ewma_mse = _mean(losses["ewma_loss"])
    return {
        "count": len(forecasts),
        "rolling_mse": rolling_mse,
        "ewma_mse": ewma_mse,
        "ewma_relative_mse_change": (
            ewma_mse / rolling_mse - 1 if rolling_mse != 0 else None
        ),
    }
