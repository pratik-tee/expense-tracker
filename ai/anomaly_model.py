import sqlite3
import os
import pandas as pd
from sklearn.ensemble import IsolationForest
import joblib

DB_NAME = "expenses.db"
MODEL_PATH = "ai/model.joblib"

def train_model():
    print(" Connecting to database...")

    if not os.path.exists(DB_NAME):
        print(" Database not found:", DB_NAME)
        return

    con = sqlite3.connect(DB_NAME)

    query = """
        SELECT amount
        FROM expenses
        WHERE amount IS NOT NULL
    """

    df = pd.read_sql_query(query, con)
    con.close()

    print(f" Total expenses found: {len(df)}")

    if len(df) < 20:
        print(" Not enough data to train model (need at least 20 expenses)")
        return

    X = df[["amount"]]

    print(" Training IsolationForest model...")
    model = IsolationForest(
        n_estimators=100,
        contamination=0.05,
        random_state=42
    )

    model.fit(X)

    joblib.dump(model, MODEL_PATH)

    print(" Anomaly model trained successfully!")
    print(f" Model saved at: {MODEL_PATH}")

if __name__ == "__main__":
    train_model()
