````markdown
# GridAI — German Electricity Forecasting

GridAI is a time-series forecasting project for predicting electricity demand from German power-system data. It uses historical electricity measurements, temporal feature engineering, and machine-learning models to forecast future energy-system values.

## Project Structure

```text
GridAI/
├── <dataset>.csv
├── notebooks/
│   ├── 01_data_exploration.ipynb
│   ├── model_features.pkl
│   └── xgboost_load_forecasting_model.pkl
└── README.md
````

## Current Status

The current version contains the main data exploration, preprocessing, feature-engineering, and initial electricity-load forecasting workflow.

### Completed

* Loaded and inspected the German electricity time-series dataset.
* Processed timestamps while preserving German local-time analysis.
* Investigated missing timestamps and irregular time gaps.
* Analyzed missing values across variables.
* Removed variables with excessive missingness from the modelling dataset.
* Handled small internal gaps in retained predictors.
* Identified and corrected a clearly erroneous electricity-load outlier.
* Performed exploratory analysis of hourly, weekly, monthly, and daily load patterns.
* Created calendar features.
* Created lag features for 15 minutes, 1 hour, 1 day, and 1 week.
* Created rolling load statistics.
* Created chronological training, validation, and test sets.
* Built a persistence forecasting baseline.
* Trained an XGBoost regression model for 15-minute-ahead load forecasting.
* Evaluated the model using MAE and RMSE.
* Saved the trained model and feature list as `.pkl` files.

---

## Forecasting Task

The current forecasting task is:

> **Predict electricity load 15 minutes into the future.**

### Target

```text
load_Actual Load
```

The final modelling dataset contains **59 input features plus the target** and approximately **380,000 usable observations** after feature engineering and removal of rows with unavailable modelling features.

---

## Current Model

### XGBoost

The current model uses `XGBRegressor` with:

* 500 estimators
* Learning rate: `0.05`
* Maximum depth: `8`
* Subsample: `0.8`
* Column sampling: `0.8`
* Squared-error regression objective
* Fixed random state for reproducibility

### Current Results

| Model                |      Test MAE |
| -------------------- | ------------: |
| Persistence baseline |     519.34 MW |
| **XGBoost**          | **278.23 MW** |

The XGBoost model reduced test MAE by approximately **46.4%** compared with the persistence baseline.

**XGBoost Test RMSE:** `387.99 MW`

These results are from the current experimental setup and do not yet represent the final production configuration.

---

## Feature Engineering

### Historical Features

The model uses historical electricity-load information through:

* 15-minute lag
* 1-hour lag
* 1-day lag
* 1-week lag

### Rolling Features

* 1-hour rolling mean
* 1-day rolling mean
* 1-day rolling standard deviation

### Calendar Features

* Hour
* Minute
* Day of week
* Month
* Day of year
* Weekend indicator

The dataset also contains electricity-generation, renewable-generation, import, and forecast-related variables that are used as model inputs where appropriate.

---

## Data Quality

The dataset contains irregular gaps in its 15-minute timeline. These include a large historical gap in 2018 and other shorter missing periods.

Long missing periods are **not blindly filled with fabricated observations**.

Variables with more than 5% missing values were excluded from the modelling dataset. Small internal gaps in retained predictors were handled using limited interpolation.

Missing target observations were not artificially fabricated for modelling.

### Corrected Outlier

One clearly erroneous electricity-load observation was identified:

| Timestamp            |   Original Load | Corrected Load |
| -------------------- | --------------: | -------------: |
| 2026-06-25 16:30 UTC | 4,315,702.57803 |   62,423.10549 |

The original value was inconsistent with the immediately surrounding load observations and was corrected using the neighboring values.

---

## Train / Validation / Test

Because this is a time-series problem, the data is split chronologically rather than randomly.

```text
Historical Data
      │
      ├── 70% Training
      │
      ├── 15% Validation
      │
      └── 15% Test
```

This prevents future observations from being randomly mixed into the training data.

---

## Saved Model Files

### `xgboost_load_forecasting_model.pkl`

Contains the trained XGBoost electricity-load forecasting model.

### `model_features.pkl`

Contains the ordered list of features expected by the trained model.

Both files are used together when loading the saved model for prediction.

---

## Notebook

`01_data_exploration.ipynb` contains the main workflow:

1. Data loading and inspection
2. Timestamp processing
3. Missing-data analysis
4. Timestamp-gap analysis
5. Outlier detection and correction
6. Exploratory data analysis
7. Feature engineering
8. Lag and rolling features
9. Chronological data splitting
10. Persistence baseline
11. XGBoost training
12. Model evaluation
13. Prediction and error analysis
14. Feature-importance analysis

---

## Planned Forecasting Targets

The next stage of GridAI is to extend forecasting beyond electricity load to multiple electricity-system categories:

* Actual electricity load
* Wind generation
* Solar generation
* Hydro generation
* Fossil generation
* Nuclear generation
* Electricity imports

Separate target-specific models can be developed for these categories.

---

## Other Models to Evaluate

XGBoost is the current forecasting model, but other approaches can be evaluated using the same chronological train/validation/test methodology.

Potential alternatives include:

* Linear Regression
* Random Forest
* LightGBM
* CatBoost
* SARIMA / SARIMAX
* LSTM
* GRU

Models can be compared using metrics such as:

* MAE
* RMSE
* MAPE where appropriate
* Training time
* Prediction time

The final model choice should be based on measured performance and practical deployment requirements.

---

## Important Next Step: Forecast-Time Leakage

Before using the forecasting system as a real-time application, the model features must be checked for **forecast-time leakage**.

When predicting the next 15-minute interval, every input feature must represent information that would actually be available at the time the prediction is made.

For example, an actual measurement from the future prediction interval cannot be used as an input.

This check is required before treating the current model as production-ready.

---

## Planned Dashboard

The eventual GridAI web interface is intended to provide an interactive forecasting dashboard with:

* Actual vs predicted graphs
* Date and time filters
* Hourly, daily, weekly, and monthly views
* Forecasts for different electricity categories
* Model performance metrics
* Prediction errors
* Feature importance
* Recent electricity-system values
* Future forecasts

---

## Technologies

* **Python**
* **Pandas**
* **NumPy**
* **Matplotlib**
* **Scikit-learn**
* **XGBoost**
* **Jupyter Notebook**
* **Joblib**

---

## Goal

GridAI aims to become an interactive electricity forecasting system that learns temporal patterns in German power-system data and presents future forecasts through a web-based dashboard.

The project will eventually combine multiple forecasting models, electricity-system variables, and an interactive visualization layer to provide a comprehensive view of future German electricity demand and generation.

```
```
