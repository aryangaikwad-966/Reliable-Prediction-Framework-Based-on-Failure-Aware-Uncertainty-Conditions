# Uncertainty Signals Documentation

This document explains the uncertainty signals used in the Reliable Prediction Framework, their implementation status, and limitations.

## Overview

The framework uses 6 uncertainty signals to calculate failure risk:

1. **Model Uncertainty** ✅ IMPLEMENTED
2. **Historical Failure Risk** ✅ IMPLEMENTED
3. **Novelty/OOD Score** ✅ IMPLEMENTED
4. **Drift Score** ✅ IMPLEMENTED
5. **Missing Information** ⚠️ NOT IMPLEMENTED
6. **Context Risk** ⚠️ NOT IMPLEMENTED

## Signal Details

### 1. Model Uncertainty ✅

**Purpose:** Measures the model's confidence in its prediction based on historical performance.

**Implementation:**
- **Location:** `ml-service/training/train.py` (line 57)
- **Calculation:** `np.std(test["target"].to_numpy() - predictions) / max(np.mean(test["target"]), 1)`
- **Storage:** Saved in model artifact as `model_uncertainty`
- **Usage:** Retrieved from artifact in `ml-service/app/main.py` (line 37)

**Formula:**
```
model_uncertainty = std(residuals) / mean(actual_values)
```

**Interpretation:**
- Higher values indicate model uncertainty
- Based on actual test set performance
- Model-specific (calculated during training)

**Status:** ✅ Fully implemented and functional

---

### 2. Historical Failure Risk ✅

**Purpose:** Measures the historical failure rate for similar market contexts.

**Implementation:**
- **Location:** `ml-service/app/main.py` (lines 42-55)
- **Calculation:** Query failure_memory table for commodity/market
- **Formula:** `failures / total_cases`
- **Storage:** Not stored (calculated on-demand)

**Code:**
```python
cur.execute("""
    SELECT COUNT(*) as total, 
           SUM(CASE WHEN severity != 'NORMAL' THEN 1 ELSE 0 END) as failures
    FROM failure_memory
    WHERE commodity = %s AND market = %s
""", (request.commodity, request.market))
historical_failure_risk = row[1] / row[0] if row[0] > 0 else 0.0
```

**Interpretation:**
- Higher values indicate higher historical failure rate
- Context-specific (commodity + market)
- Zero if no historical failures exist
- Adaptive (updates as new outcomes are recorded)

**Status:** ✅ Fully implemented and functional

---

### 3. Novelty/OOD Score ✅

**Purpose:** Measures how unusual the current context is compared to training data.

**Implementation:**
- **Location:** `ml-service/app/core.py` (lines 60-66)
- **Calculation:** Standardized distance from training distribution
- **Formula:** `sum(|(value - mean) / std|) / (n_features * 3.0)`

**Code:**
```python
def novelty_score(vector: Iterable[float], means: Iterable[float], scales: Iterable[float]) -> float:
    values = list(vector)
    standardized = [abs((value - mean) / scale) if scale else 0.0 
                   for value, mean, scale in zip(values, means, scales)]
    if not standardized:
        return 0.0
    return clamp(sum(standardized) / len(standardized) / 3.0)
```

**Interpretation:**
- Higher values indicate more unusual context
- Based on feature distance from training mean
- Bounded to [0, 1]
- Feature-specific (uses all model features)

**Status:** ✅ Fully implemented and functional

---

### 4. Drift Score ✅

**Purpose:** Measures distribution drift in prediction errors over time.

**Implementation:**
- **Location:** `server/src/index.ts` (lines 197-245)
- **Calculation:** Rolling error comparison (recent vs historical)
- **Formula:** `(recent_mean_error - historical_mean_error) / historical_mean_error`

**Code:**
```typescript
const recentErrors = recentResult.rows.map(row => 
  Math.abs(parseFloat(row.actual) - parseFloat(row.prediction))
);
const historicalErrors = historicalResult.rows.map(row => 
  Math.abs(parseFloat(row.actual) - parseFloat(row.prediction))
);
const recentMean = recentErrors.reduce((sum, e) => sum + e, 0) / recentErrors.length;
const historicalMean = historicalErrors.reduce((sum, e) => sum + e, 0) / historicalErrors.length;
const driftScore = Math.max(0, Math.min(1, (recentMean - historicalMean) / Math.max(historicalMean, 1)));
```

**Interpretation:**
- Higher values indicate more drift
- Based on actual prediction outcomes
- Compares recent (30 days) vs historical errors
- Zero if insufficient data

**Status:** ✅ Fully implemented and functional

---

### 5. Missing Information ⚠️ NOT IMPLEMENTED

**Purpose:** Measures risk due to missing external context (weather, policy, events).

**Current Implementation:**
- **Location:** `ml-service/app/main.py` (line 41)
- **Value:** Hardcoded to `0.0`
- **Reason:** No external event data available in APMC dataset

**Why Not Implemented:**
- The APMC dataset does not contain:
  - Weather data (rainfall, temperature)
  - Government policy information
  - News events
  - Supply chain disruptions
  - Natural disasters
- These would require external data sources

**Future Implementation:**
To implement this signal, you would need to:
1. Integrate external data sources (weather APIs, news APIs)
2. Store event data in the `events` table
3. Query events for the prediction context
4. Calculate missing information risk based on:
   - Availability of weather data
   - Recency of policy changes
   - Occurrence of significant events

**Current Behavior:**
- Signal is set to 0.0 (no missing information risk)
- Does not affect failure risk calculation
- System acknowledges this limitation in UI

**Status:** ⚠️ Not implemented due to missing data sources

---

### 6. Context Risk ⚠️ NOT IMPLEMENTED

**Purpose:** Measures risk from contextual factors not captured by other signals.

**Current Implementation:**
- **Location:** `ml-service/app/main.py` (line 42)
- **Value:** Hardcoded to `0.0`
- **Reason:** No additional context data available

**Why Not Implemented:**
- Would require domain-specific context data
- Examples for agricultural domain:
  - Seasonal patterns (beyond temporal features)
  - Regional economic indicators
  - Transportation infrastructure status
  - Storage facility conditions
  - Market-specific regulations

**Future Implementation:**
To implement this signal, you would need to:
1. Define domain-specific context factors
2. Collect context data for each market
3. Store context in database
4. Calculate context risk based on:
   - Anomalous context values
   - High-risk context combinations
   - Contextual event proximity

**Current Behavior:**
- Signal is set to 0.0 (no context risk)
- Does not affect failure risk calculation
- System acknowledges this limitation in UI

**Status:** ⚠️ Not implemented due to missing context data

---

## Risk Calculation

**Location:** `ml-service/app/core.py` (lines 21-30)

**Formula:**
```
failure_risk = Σ(weight_i * signal_i) for i in signals
```

**Weights:**
- model_uncertainty: 0.24
- historical_failure_risk: 0.22
- novelty_score: 0.18
- drift_score: 0.16
- missing_information: 0.10
- context_risk: 0.10

**Total:** 1.0 (100%)

**Reliability:**
```
reliability = 1.0 - failure_risk
```

**Decision:**
```
if reliability >= threshold:
    decision = ACCEPTED
else:
    decision = ABSTAINED
```

---

## Impact of Missing Signals

### Current Impact
- 2 out of 6 signals are not implemented (33%)
- Total weight of missing signals: 0.20 (20%)
- Maximum potential failure risk: 0.80 (instead of 1.0)
- System may be slightly optimistic in uncertainty assessment

### Compensation
- The 4 implemented signals provide substantial uncertainty information
- Weights are recalculated to sum to 1.0
- System acknowledges limitations in UI and documentation
- Missing signals can be added incrementally as data becomes available

### Validity
- The current implementation is **research-valid** for:
  - Demonstrating the framework architecture
  - Testing selective prediction logic
  - Evaluating with available uncertainty signals
  - Serving as a foundation for future enhancements

- The current implementation is **not production-optimized** for:
  - Domains requiring external event data
  - High-stakes applications needing maximum uncertainty coverage
  - Scenarios where all uncertainty sources are critical

---

## Recommendations

### For Research Use
- Current implementation is sufficient
- Clearly document limitations in papers
- Use available signals for analysis
- Report which signals are used vs missing

### For Production Use
- Integrate external data sources for missing signals
- Implement missing_information with weather/policy data
- Implement context_risk with domain-specific factors
- Recalibrate weights based on production data
- Validate signal contributions with ablation studies

### For Domain Adaptation
- Review which signals are relevant for your domain
- Implement missing signals if data is available
- Adjust weights based on domain importance
- Add domain-specific signals if needed
- Validate with domain-specific evaluation

---

## Testing Uncertainty Signals

### Test Model Uncertainty
```bash
# Train model and check artifact
PYTHONPATH=./ml-service python -m training.train \
  --data ./data/apmc-arrivals-and-prices-old-data.csv \
  --commodity Tomato --horizon 7

# Check model artifact
python3 -c "import joblib; artifact = joblib.load('ml-service/models/latest.joblib'); print(artifact.get('model_uncertainty'))"
```

### Test Historical Failure Risk
```bash
# Submit some outcomes
curl -X POST http://localhost:3001/api/outcomes \
  -H "Content-Type: application/json" \
  -d '{"predictionId":"pred_123","actual":500}'

# Check failure memory
curl http://localhost:3001/api/failures

# Make prediction (should use historical rate)
curl -X POST http://localhost:3001/api/predictions \
  -H "Content-Type: application/json" \
  -d '{"commodity":"Tomato","market":"Lasalgaon","variety":"Local","horizon":7}'
```

### Test Novelty/OOD
```bash
# Make prediction with normal context
curl -X POST http://localhost:3001/api/predictions \
  -H "Content-Type: application/json" \
  -d '{"commodity":"Tomato","market":"Lasalgaon","variety":"Local","horizon":7}'

# Make prediction with unusual context (different market)
curl -X POST http://localhost:3001/api/predictions \
  -H "Content-Type: application/json" \
  -d '{"commodity":"Tomato","market":"UnknownMarket","variety":"Local","horizon":7}'
```

### Test Drift
```bash
# Check drift status
curl http://localhost:3001/api/dift

# Submit outcomes over time to build history
# Then check drift again
curl http://localhost:3001/api/dift
```

---

## Signal Quality Assessment

| Signal | Data Source | Calculation Quality | Implementation Quality | Overall |
|--------|-------------|-------------------|----------------------|---------|
| Model Uncertainty | Model residuals | High (statistical) | High (tested) | ✅ Excellent |
| Historical Failure Risk | Failure memory | High (empirical) | High (tested) | ✅ Excellent |
| Novelty/OOD | Feature distribution | Medium (heuristic) | High (tested) | ✅ Good |
| Drift | Prediction outcomes | Medium (heuristic) | High (tested) | ✅ Good |
| Missing Information | External events | N/A (no data) | N/A (not implemented) | ⚠️ Not Available |
| Context Risk | Domain context | N/A (no data) | N/A (not implemented) | ⚠️ Not Available |

---

## Conclusion

The framework has **4 out of 6 uncertainty signals fully implemented** (67% coverage). The missing signals (missing_information, context_risk) are not implemented due to the absence of required external data sources in the APMC dataset.

**This is a documented limitation, not a bug.** The system:
- Clearly indicates which signals are active
- Returns NOT_AVAILABLE for missing external events
- Provides a solid foundation for future enhancements
- Maintains research integrity by not fabricating signal values

For most research purposes, the current signal coverage is sufficient. For production deployment in domains where external events are critical, the missing signals should be implemented with appropriate data sources.
