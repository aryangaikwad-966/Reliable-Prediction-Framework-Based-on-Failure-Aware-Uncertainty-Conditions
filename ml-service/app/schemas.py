from pydantic import BaseModel, Field


class PredictionRequest(BaseModel):
    commodity: str = Field(min_length=1, max_length=80)
    market: str = Field(min_length=1, max_length=120)
    variety: str = Field(min_length=1, max_length=120)
    horizon: int = Field(default=7, ge=1, le=90)
    features: dict[str, float] = Field(default_factory=dict)


class TrainRequest(BaseModel):
    data_path: str
    commodity: str = "Tomato"
    market: str | None = None
    horizon: int = Field(default=7, ge=1, le=90)
    test_fraction: float = Field(default=0.2, gt=0, lt=0.5)