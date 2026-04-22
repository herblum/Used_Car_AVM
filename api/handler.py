"""Serverless API for car price prediction.

Single POST /predict endpoint. Runs on AWS Lambda via Mangum adapter
or locally with `uvicorn handler:app`.
"""

import sys
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from mangum import Mangum

# Add ml_model to path so we can import predict/features
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ml_model"))

from predict import predict  # noqa: E402
from trim_extractor import KNOWN_TRIMS  # noqa: E402

app = FastAPI(title="UC AVM", description="Used car price prediction API")


class CarFeatures(BaseModel):
    marca: str | None = Field(None, example="Audi")
    modelo: str | None = Field(None, example="Q7")
    anio: int | None = Field(None, example=2017)
    kilometros: float | None = Field(None, example=62000)
    cilindrada_cc: int | None = Field(None, example=3000)
    combustible: str | None = Field(None, example="Diésel")
    transmision: str | None = Field(None, example="Automática")
    traccion: str | None = Field(None, example="Integral")
    tipo_carroceria: str | None = Field(None, example="SUV")
    puertas: int | None = Field(None, example=5)
    color: str | None = Field(None, example="Blanco")
    provincia: str | None = Field(None, example="Capital Federal")
    moneda: str | None = Field(None, example="USD")
    condicion: str | None = Field(None, example="used")
    es_concesionario: int | None = Field(None, example=0)
    trim_level: str | None = Field(None, example="Highline")


class PriceRange(BaseModel):
    price_low: float
    price_mid: float
    price_high: float
    currency: str


def _compute_derived(features: dict) -> dict:
    """Add vehiculo_edad and km_por_anio from user inputs."""
    anio = features.get("anio")
    km = features.get("kilometros")

    if anio is not None:
        edad = date.today().year - anio
        features["vehiculo_edad"] = edad
        if km is not None and edad > 0:
            features["km_por_anio"] = round(km / edad, 1)
        else:
            features["km_por_anio"] = None
    else:
        features["vehiculo_edad"] = None
        features["km_por_anio"] = None

    return features


@app.post("/predict", response_model=PriceRange)
def predict_price(car: CarFeatures) -> PriceRange:
    try:
        features = _compute_derived(car.model_dump())
        result = predict(features)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return PriceRange(**result)


@app.get("/trims/{marca}")
def get_trims(marca: str) -> list[str]:
    return KNOWN_TRIMS.get(marca.strip().lower(), [])


@app.get("/health")
def health():
    return {"status": "ok"}


# AWS Lambda entry point
lambda_handler = Mangum(app)
