# ML pipeline

## Features

The training adapter creates shifted price lags (1, 2, 3, 7, 14, 30), rolling price means and standard deviations, price changes, arrival lags and rolling arrivals, calendar fields, and an out-of-time target at the selected horizon.

Every rolling feature is shifted before calculation. The target is shifted forward. This prevents the current or future target from leaking into the current observation.

## Model and reliability

The baseline is `XGBRegressor`. The artifact records features, training period, model version, feature means/scales, and holdout metrics.

The MVP uncertainty engine combines:

- stored model uncertainty estimate;
- contextual failure-memory rate;
- standardized distance from the training distribution;
- rolling residual drift;
- missing external context;
- future event/context risk.

These values feed a weighted, bounded risk formulation. The weights are a transparent project configuration, not a universal scientific law. A prediction is accepted only when calculated reliability meets the configured threshold. Otherwise its public `prediction` is `null`.

The novelty score is an interpretable bounded standardized-distance signal. It is not presented as a perfect OOD detector. Drift is a rolling residual comparison and returns no detection when there is not enough history.