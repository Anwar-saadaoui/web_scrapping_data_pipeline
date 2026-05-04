import joblib
import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Avito ML API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load models
lr      = joblib.load("/models/linear_regression.pkl")
log_reg = joblib.load("/models/logistic_regression.pkl")
xgb     = joblib.load("/models/xgboost.pkl")
scaler  = joblib.load("/models/scaler.pkl")
le_city = joblib.load("/models/le_city.pkl")
le_cat  = joblib.load("/models/le_category.pkl")

FEATURES = ["area_m2", "rooms", "bathrooms", "floor",
            "property_age", "price_per_m2", "city_enc"]

class PropertyInput(BaseModel):
    area_m2:      float
    rooms:        float
    bathrooms:    float = 1
    floor:        float = 0
    property_age: float = 10
    city:         str   = "Casablanca"
    price_per_m2: Optional[float] = None

def encode_city(city: str) -> int:
    city = city.strip().title()
    if city in le_city.classes_:
        return int(le_city.transform([city])[0])
    return 0

def build_features(data: PropertyInput, scaler=None):
    price_per_m2 = data.price_per_m2 or 10000 / data.area_m2
    city_enc     = encode_city(data.city)
    X = np.array([[
        data.area_m2,
        data.rooms,
        data.bathrooms,
        data.floor,
        data.property_age,
        price_per_m2,
        city_enc,
    ]])
    if scaler:
        X = scaler.transform(X)
    return X


@app.get("/")
def root():
    return {"message": "Avito ML API is running", "models": ["linear_regression", "logistic_regression", "xgboost"]}


@app.get("/cities")
def get_cities():
    return {"cities": list(le_city.classes_)}


@app.get("/categories")
def get_categories():
    return {"categories": list(le_cat.classes_)}


@app.post("/predict/price")
def predict_price(data: PropertyInput):
    """Linear Regression — predict exact price in DH"""
    X = build_features(data, scaler=scaler)
    price_k  = float(lr.predict(X)[0])
    price_dh = round(price_k * 1000, 2)
    return {
        "model":       "Linear Regression",
        "task":        "Price Prediction",
        "input":       data.dict(),
        "predicted_price_kdh": round(price_k, 2),
        "predicted_price_dh":  price_dh,
        "formatted":   f"{price_dh:,.0f} DH",
    }


@app.post("/predict/category/logistic")
def predict_category_logistic(data: PropertyInput):
    """Logistic Regression — classify price category"""
    X        = build_features(data, scaler=scaler)
    pred     = log_reg.predict(X)[0]
    proba    = log_reg.predict_proba(X)[0]
    label    = le_cat.inverse_transform([pred])[0]
    proba_dict = {cls: round(float(p)*100, 1)
                  for cls, p in zip(le_cat.classes_, proba)}
    return {
        "model":      "Logistic Regression",
        "task":       "Price Category Classification",
        "input":      data.dict(),
        "category":   label,
        "confidence": f"{max(proba)*100:.1f}%",
        "probabilities": proba_dict,
    }


@app.post("/predict/category/xgboost")
def predict_category_xgboost(data: PropertyInput):
    """XGBoost — classify price category"""
    X        = build_features(data, scaler=None)
    pred     = xgb.predict(X)[0]
    proba    = xgb.predict_proba(X)[0]
    label    = le_cat.inverse_transform([pred])[0]
    proba_dict = {cls: round(float(p)*100, 1)
                  for cls, p in zip(le_cat.classes_, proba)}
    return {
        "model":      "XGBoost",
        "task":       "Price Category Classification",
        "input":      data.dict(),
        "category":   label,
        "confidence": f"{max(proba)*100:.1f}%",
        "probabilities": proba_dict,
    }


@app.post("/predict/all")
def predict_all(data: PropertyInput):
    """Run all 3 models at once"""
    X_sc = build_features(data, scaler=scaler)
    X_raw= build_features(data, scaler=None)

    price_k = float(lr.predict(X_sc)[0])

    log_pred  = log_reg.predict(X_sc)[0]
    log_proba = log_reg.predict_proba(X_sc)[0]
    log_label = le_cat.inverse_transform([log_pred])[0]

    xgb_pred  = xgb.predict(X_raw)[0]
    xgb_proba = xgb.predict_proba(X_raw)[0]
    xgb_label = le_cat.inverse_transform([xgb_pred])[0]

    return {
        "input": data.dict(),
        "linear_regression": {
            "predicted_price_dh": round(price_k * 1000, 2),
            "formatted": f"{price_k*1000:,.0f} DH",
        },
        "logistic_regression": {
            "category": log_label,
            "confidence": f"{max(log_proba)*100:.1f}%",
            "probabilities": {cls: round(float(p)*100,1)
                              for cls, p in zip(le_cat.classes_, log_proba)},
        },
        "xgboost": {
            "category": xgb_label,
            "confidence": f"{max(xgb_proba)*100:.1f}%",
            "probabilities": {cls: round(float(p)*100,1)
                              for cls, p in zip(le_cat.classes_, xgb_proba)},
        },
    }