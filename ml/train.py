import os, joblib, warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sqlalchemy import create_engine
from dotenv import load_dotenv
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (mean_absolute_error, r2_score,
                             accuracy_score, classification_report,
                             confusion_matrix)
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")
load_dotenv()
os.makedirs("outputs", exist_ok=True)

# Load 
engine = create_engine(
    f"postgresql://{os.getenv('DB_USER','avito_user')}:{os.getenv('DB_PASSWORD','avito_pass')}"
    f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}/{os.getenv('DB_NAME','avito_db')}"
)
df = pd.read_sql("SELECT * FROM ml_schema.feature_store", engine)

# Clean 
df = df[(df["price"] >= 100) & (df["price"] <= 15000)]
df = df[df["area_m2"].between(20, 2000)]
df = df[df["rooms"].notna() & df["city"].notna()]
df["price_per_m2"] = df["price"] / df["area_m2"]

# Force all numeric columns and fill NaN with median
NUM_COLS = ["area_m2", "rooms", "bathrooms", "floor", "property_age", "price_per_m2"]
for col in NUM_COLS:
    df[col] = pd.to_numeric(df[col], errors="coerce")
    median_val = df[col].median()
    df[col] = df[col].fillna(median_val)
    print(f"  {col}: median={median_val:.2f}, nulls remaining={df[col].isna().sum()}")

# Encode city
le_city = LabelEncoder()
df["city_enc"] = le_city.fit_transform(df["city"].astype(str))

# Target
def categorize(p):
    if p < 500:    return "Budget"
    elif p < 1500: return "Mid-range"
    elif p < 4000: return "Premium"
    else:          return "Luxury"

df["category"] = df["price"].apply(categorize)
le_cat = LabelEncoder()
df["cat_enc"] = le_cat.fit_transform(df["category"])

print(f"\nClean rows: {len(df)}")
print(df["category"].value_counts())

FEATURES = ["area_m2", "rooms", "bathrooms", "floor",
            "property_age", "price_per_m2", "city_enc"]

X = df[FEATURES].copy()
y_reg = df["price"].copy()
y_clf = df["cat_enc"].copy()

# Final NaN check
print(f"\nNaN in X before split: {X.isna().sum().sum()}")
X = X.fillna(X.median())  # safety net
print(f"NaN in X after fillna: {X.isna().sum().sum()}")

X_tr, X_te, yr_tr, yr_te, yc_tr, yc_te = train_test_split(
    X, y_reg, y_clf,
    test_size=0.2, random_state=42, stratify=y_clf
)

scaler = StandardScaler()
X_tr_sc = scaler.fit_transform(X_tr)
X_te_sc = scaler.transform(X_te)


# MODEL 1 — Linear Regression

print("\n" + "="*50)
print("MODEL 1 — Linear Regression")

lr = Pipeline([
    ("imputer", SimpleImputer(strategy="median")),
    ("model",   LinearRegression())
])
lr.fit(X_tr_sc, yr_tr)
yr_pred = lr.predict(X_te_sc)

mae = mean_absolute_error(yr_te, yr_pred)
r2  = r2_score(yr_te, yr_pred)
print(f"  MAE : {mae:.0f}k DH")
print(f"  R²  : {r2:.4f}")

plt.figure(figsize=(7, 5))
plt.scatter(yr_te, yr_pred, alpha=0.4, color="steelblue")
plt.plot([yr_te.min(), yr_te.max()], [yr_te.min(), yr_te.max()], "r--")
plt.xlabel("Actual (k DH)"); plt.ylabel("Predicted (k DH)")
plt.title("Linear Regression — Actual vs Predicted")
plt.tight_layout()
plt.savefig("outputs/linear_regression.png", dpi=150); plt.close()
joblib.dump(lr, "outputs/linear_regression.pkl")


# MODEL 2 — Logistic Regression

print("\n" + "="*50)
print("MODEL 2 — Logistic Regression")

log = Pipeline([
    ("imputer", SimpleImputer(strategy="median")),
    ("model",   LogisticRegression(max_iter=1000, random_state=42))
])
log.fit(X_tr_sc, yc_tr)
yc_pred_log = log.predict(X_te_sc)

acc_log = accuracy_score(yc_te, yc_pred_log)
print(f"  Accuracy: {acc_log*100:.2f}%")
print(classification_report(yc_te, yc_pred_log, target_names=le_cat.classes_))

cm = confusion_matrix(yc_te, yc_pred_log)
plt.figure(figsize=(7, 5))
sns.heatmap(cm, annot=True, fmt="d", cmap="Greens",
            xticklabels=le_cat.classes_, yticklabels=le_cat.classes_)
plt.title("Logistic Regression — Confusion Matrix")
plt.tight_layout()
plt.savefig("outputs/logistic_confusion.png", dpi=150); plt.close()
joblib.dump(log, "outputs/logistic_regression.pkl")


# MODEL 3 — XGBoost

print("\n" + "="*50)
print("MODEL 3 — XGBoost")

xgb = XGBClassifier(
    n_estimators=300, max_depth=6, learning_rate=0.05,
    subsample=0.8, colsample_bytree=0.8,
    eval_metric="mlogloss", random_state=42, n_jobs=-1
)
xgb.fit(X_tr, yc_tr, eval_set=[(X_te, yc_te)], verbose=50)
yc_pred_xgb = xgb.predict(X_te)

acc_xgb = accuracy_score(yc_te, yc_pred_xgb)
print(f"  Accuracy: {acc_xgb*100:.2f}%")
print(classification_report(yc_te, yc_pred_xgb, target_names=le_cat.classes_))

cm2 = confusion_matrix(yc_te, yc_pred_xgb)
plt.figure(figsize=(7, 5))
sns.heatmap(cm2, annot=True, fmt="d", cmap="Blues",
            xticklabels=le_cat.classes_, yticklabels=le_cat.classes_)
plt.title("XGBoost — Confusion Matrix")
plt.tight_layout()
plt.savefig("outputs/xgb_confusion.png", dpi=150); plt.close()

fi = pd.Series(xgb.feature_importances_, index=FEATURES).sort_values()
plt.figure(figsize=(7, 5))
fi.plot(kind="barh", color="steelblue")
plt.title("XGBoost — Feature Importance")
plt.tight_layout()
plt.savefig("outputs/xgb_feature_importance.png", dpi=150); plt.close()
joblib.dump(xgb, "outputs/xgboost.pkl")

# Save encoders & scaler
joblib.dump(scaler,  "outputs/scaler.pkl")
joblib.dump(le_cat,  "outputs/le_category.pkl")
joblib.dump(le_city, "outputs/le_city.pkl")


print("\n" + "="*50)
print("SUMMARY")
print(f"  Linear Regression   → MAE={mae:.0f}k DH  R²={r2:.3f}")
print(f"  Logistic Regression → Accuracy={acc_log*100:.1f}%")
print(f"  XGBoost             → Accuracy={acc_xgb*100:.1f}%")
print("  All outputs saved in outputs/")
print("="*50)