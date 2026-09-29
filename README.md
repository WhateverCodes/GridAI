# GridAI ⚡

## German Electricity Forecasting using Time-Series Machine Learning and XGBoost

GridAI is a time-series machine learning project for forecasting German electricity demand and generation from historical 15-minute electricity measurements.

The project combines data cleaning, temporal analysis, feature engineering, XGBoost regression, baseline forecasting and model evaluation into an end-to-end forecasting pipeline.

---

## Project Overview

Electricity demand and generation change continuously throughout the day and are influenced by time of day, weekdays, seasonal patterns and recent system behaviour.

GridAI uses historical electricity measurements to study these patterns and build short-term forecasting models for:

- Electricity Load
- Wind Generation
- Solar Generation
- Hydro Generation

The project also explores Direct and Delta XGBoost approaches and compares machine-learning models against a persistence baseline.

---

## Objectives

The main objectives of GridAI are to:

1. Clean and prepare a large real-world electricity time-series dataset.
2. Analyze daily, weekly and seasonal electricity patterns.
3. Develop lag, rolling and calendar-based features.
4. Train machine-learning models for short-term forecasting.
5. Compare XGBoost against a persistence baseline.
6. Study Direct and Delta XGBoost forecasting approaches.
7. Evaluate models using MAE and RMSE.
8. Build a dashboard for interacting with the forecasting system.

---

## Dataset

The project uses a German electricity time-series dataset containing measurements at 15-minute intervals.

The original dataset contains approximately:

- 395,000+ observations
- 88 columns
- Electricity load measurements
- Renewable generation
- Fossil generation
- Nuclear generation
- Electricity imports
- Other electricity-system measurements

The original CSV is not included in this repository because of its large file size.

### Reproducing the Dataset Pipeline

1. Obtain the original dataset from its source.
2. Place the CSV file in the project directory.
3. Open the data exploration notebook.
4. Update the dataset path if required.
5. Run the notebook from the beginning.

> The dataset version used during development may differ from newer versions of the original source. Changes to the source data may therefore require updates to preprocessing or cleaning steps.

---

## Data Preprocessing

The raw dataset is processed before it is used for machine learning.

### Timestamp Processing

- Convert timestamps into a consistent datetime representation.
- Handle timezone information.
- Sort observations chronologically.
- Check for duplicate timestamps.
- Analyze missing time intervals.

### Missing-Value Analysis

Missing values are analyzed for every measurement column.

Features with excessive missing data are excluded from the main modelling dataset, while appropriate small internal gaps can be handled through interpolation.

### Outlier Detection

Statistical and temporal checks are used to identify abnormal observations.

An extreme electricity-load observation was investigated by comparing it with neighbouring 15-minute measurements. The clearly erroneous observation was corrected using the surrounding values.

### Model-Ready Data

After cleaning and validation, the dataset is transformed into a structured time-series dataset suitable for feature engineering and forecasting.

---

## Feature Engineering

GridAI uses historical and temporal information to help the models learn electricity behaviour.

### Lag Features

| Feature | Description |
|---|---|
| `lag_15min` | Previous 15-minute value |
| `lag_1hour` | Value one hour earlier |
| `lag_1day` | Value one day earlier |
| `lag_1week` | Value one week earlier |

These features capture short-term persistence as well as daily and weekly patterns.

### Rolling Features

The project uses:

- 1-hour rolling mean
- 1-day rolling mean
- 1-day rolling standard deviation

Rolling statistics summarize recent behaviour and volatility.

The rolling calculations are shifted so that the value being predicted is not included in its own input features.

### Calendar Features

The models also use:

- Hour
- Minute
- Day of week
- Month
- Day of year
- Weekend indicator

These features help capture recurring temporal patterns.

---

## Forecasting Models

### XGBoost

GridAI uses XGBoost regression models because the forecasting problem contains structured numerical, lag and temporal features and requires the model to capture nonlinear relationships.

XGBoost also provides feature-importance information, which helps analyze which historical features contribute most to predictions.

### Direct XGBoost

In Direct XGBoost, the model predicts the target value directly.

```text
Historical Features
        |
        v
     XGBoost
        |
        v
Predicted Target
```

### Delta XGBoost

Delta XGBoost predicts the change from the previous observation:

```text
Delta = Target(t) - Target(t-15)
```

The predicted target is then reconstructed as:

```text
Predicted Target(t)
= Target(t-15) + Predicted Delta
```

This allows the model to focus on the short-term change in the time series.

---

## Forecast-Safe Modelling

A key consideration in time-series forecasting is that a model should only use information that would actually be available when the forecast is generated.

For example, when predicting the electricity load at 08:00, the model can use information available through 07:45, but should not use the actual 08:00 load.

A forecast-safe model can therefore use:

- Historical target values
- Lag features
- Rolling statistics based only on previous observations
- Calendar features

This distinction is important because a model can perform very well on historical data while still using variables that would not be available during real future inference.

---

## Baseline Model

GridAI uses a persistence model as a simple baseline.

The persistence assumption is:

```text
Next value ≈ Most recent observed value
```

For short-term electricity forecasting, this provides a useful reference point for determining whether the machine-learning model provides additional predictive value.

---

## Evaluation

### MAE — Mean Absolute Error

MAE measures the average absolute difference between actual and predicted values.

```text
MAE = average(|Actual - Prediction|)
```

Lower MAE indicates smaller average forecasting errors.

### RMSE — Root Mean Squared Error

RMSE gives greater weight to larger errors.

```text
RMSE = sqrt(average((Actual - Prediction)^2))
```

Lower RMSE indicates fewer large forecasting errors.

---

## Time-Series Validation

Because GridAI is a forecasting project, the data is split chronologically rather than randomly.

```text
Past Data
    |
    v
+-----------+
|   Train   |
+-----------+
      |
      v
+-----------+
| Validation|
+-----------+
      |
      v
+-----------+
|   Test    |
+-----------+
```

This preserves temporal ordering and better represents real-world forecasting.

---

## Historical Model Results

The historical modelling experiments produced the following results:

| Target | Model | MAE | RMSE |
|---|---|---:|---:|
| Load | Delta XGBoost | ~258 MW | ~364 MW |
| Wind | Delta XGBoost | ~148 MW | ~220 MW |
| Solar | Delta XGBoost | ~105 MW | ~236 MW |
| Hydro | Direct XGBoost | ~32 MW | ~58 MW |

These results describe the historical modelling experiments and should be distinguished from forecast-safe deployment models.

---

## Dashboard

GridAI includes a web dashboard for interacting with the forecasting system.

The dashboard provides:

- Forecast generation
- Historical time-series visualization
- Interactive charts
- Target selection
- Forecast time selection
- Forecast values in MW
- Model information
- Forecast metadata

The goal is to make the forecasting system easier to explore and interpret rather than limiting the project to notebook-based predictions.

---

## System Architecture

```text
                 Raw Electricity Dataset
                           |
                           v
                Data Cleaning & Analysis
                           |
                           v
                 Feature Engineering
                           |
              +------------+------------+
              |                         |
              v                         v
       Persistence                 XGBoost Models
         Baseline                       |
              |                         |
              +------------+------------+
                           |
                           v
                    Model Evaluation
                     MAE / RMSE
                           |
                           v
                  Forecasting Backend
                           |
                           v
                     GridAI Dashboard
```

---

## Repository Structure

```text
GridAI/
|
├── notebooks/
│   ├── 01_data_exploration.ipynb
│   ├── model_features.pkl
│   └── xgboost_load_forecasting_model.pkl
|
├── backend/
│   ├── app.py
│   ├── data/
│   └── models/
|
├── index.html
├── style.css
├── script.js
├── requirements.txt
├── README.md
└── .gitignore
```

The exact structure may evolve as the project is developed further.

---

## Technologies Used

### Programming

- Python
- JavaScript
- HTML
- CSS

### Machine Learning

- XGBoost
- Scikit-learn
- Pandas
- NumPy

### Data Analysis

- Matplotlib
- Seaborn
- Jupyter Notebook

### Backend

- FastAPI

### Model Serialization

- Joblib
- Pickle

---

## Running the Project

### 1. Clone the repository

```bash
git clone <repository-url>
cd GridAI
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

### 3. Activate the environment

Windows:

```bash
venv\Scripts\activate
```

Linux/macOS:

```bash
source venv/bin/activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Run the backend

```bash
uvicorn backend.app:app --reload
```

Then open the dashboard according to the project's frontend setup.

---

## Machine Learning Pipeline

```text
Raw Dataset
     |
     v
Data Cleaning
     |
     v
Missing-Value Analysis
     |
     v
Timestamp & Gap Analysis
     |
     v
Outlier Detection
     |
     v
Lag Features
     |
     v
Rolling Features
     |
     v
Calendar Features
     |
     v
Chronological Split
     |
     +------> Persistence Baseline
     |
     v
XGBoost Training
     |
     v
Validation
     |
     v
Test Evaluation
     |
     v
Model Export
     |
     v
Forecasting Dashboard
```

---

## Team Contributions

| Member | Responsibility |
|---|---|
| **Aditi** | Data Cleaning & Preprocessing |
| **Sumit** | Four Forecasting Models |
| **Saachi** | Direct vs Delta XGBoost & Project Analysis |
| **Aymaan** | Rolling & Temporal Analysis |

### Aditi
Responsible for missing-value analysis, timestamp and gap handling, outlier detection, data cleaning and preparation of the model-ready dataset.

### Sumit
Responsible for developing and evaluating the Load, Wind, Solar and Hydro forecasting models using XGBoost and persistence baselines.

### Saachi
Responsible for analyzing Direct versus Delta XGBoost, model comparison, the overall forecasting methodology and forecast-safe modelling.

### Aymaan
Responsible for temporal analysis, lag features, rolling statistics and understanding daily, weekly and seasonal electricity patterns.

---

## Future Scope

Potential improvements include:

- Multi-step forecasting over longer horizons.
- Forecasting additional electricity generation sources.
- Incorporating weather variables such as temperature, wind speed and solar radiation.
- Incorporating public holidays and special events.
- Comparing XGBoost with LightGBM, LSTM, GRU and Transformer-based models.
- Automated model retraining as new data becomes available.
- Improved recursive forecasting strategies.
- Model monitoring and drift detection.
- Cloud deployment.
- Probabilistic forecasting with prediction intervals.

---

## Limitations

- The original dataset is not included because of its large file size.
- Historical performance does not automatically guarantee future forecasting performance.
- Some electricity variables contain substantial missing data.
- Weather and other external factors are not fully represented.
- Forecast accuracy differs between electricity sources.
- Longer recursive forecasting horizons can accumulate prediction errors.

---

## Key Takeaway

GridAI demonstrates an end-to-end time-series machine learning workflow:

```text
Data
  ↓
Cleaning
  ↓
Temporal Analysis
  ↓
Feature Engineering
  ↓
Baseline
  ↓
XGBoost
  ↓
Evaluation
  ↓
Forecasting
  ↓
Dashboard
```

The project focuses not only on achieving low historical forecasting error, but also on understanding whether the information used by a model would actually be available when making a real future prediction.

---

## Project

**GridAI — German Electricity Forecasting**

An academic machine learning project focused on real-world time-series preprocessing, temporal feature engineering, forecasting, model evaluation and deployment.
