# Experiments

The experiment framework is designed for chronological, expanding-window comparisons:

| Configuration | Components | Status before a run |
| --- | --- | --- |
| A — Base | XGBoost base forecast | `NOT RUN` |
| B — Base + Uncertainty | Base + model uncertainty | `NOT RUN` |
| C — Base + Failure Memory | Base + contextual failure cases | `NOT RUN` |
| D — Base + Failure Memory + OOD | Adds novelty distance | `NOT RUN` |
| E — Full framework | Adds drift, context, risk, and abstention | `NOT RUN` |

Each run must record the dataset version, date range, commodity, market, horizon, configuration, and measured results. Forecasting metrics are MAE, RMSE, MAPE, and R². Selective metrics are coverage, selective risk, abstention rate, failure detection rate, calibration, Brier score where applicable, and AURC.

The most important plot is the risk-coverage curve. Sort predictions from low to high risk, progressively retain more predictions, and calculate error only on retained predictions. A claim that abstention improves reliability should be made only from these recorded results.

The current repository represents experiment configurations and returns `NOT RUN`; it does not manufacture results.