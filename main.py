import os
import io
import json
import time
import tempfile
import logging
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel
from gradio_client import Client, handle_file

from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session

# === OpenTelemetry ===
from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.trace import get_current_span

# === Prometheus ===
from prometheus_fastapi_instrumentator import Instrumentator

# === Lifespan setup ===
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Start aplikacji...")
    create_db_and_tables()
    init_gradio_client()
    yield
    print("Zamykanie aplikacji...")

# === FastAPI app ===
app = FastAPI(
    title="HF Model Prediction Logger",
    description="API do predykcji i logowania wyników z Hugging Face",
    lifespan=lifespan
)

from opentelemetry.sdk.resources import Resource

trace.set_tracer_provider(
    TracerProvider(resource=Resource.create({"service.name": "fastapi-ml-api"}))
)

tracer = trace.get_tracer(__name__)
span_processor = BatchSpanProcessor(OTLPSpanExporter(endpoint="http://otel-collector:4318/v1/traces"))
trace.get_tracer_provider().add_span_processor(span_processor)

FastAPIInstrumentor().instrument_app(app)
RequestsInstrumentor().instrument()
LoggingInstrumentor().instrument(set_logging_format=True)
instrumentator = Instrumentator()
instrumentator.instrument(app).expose(app)

# === Logger ===
logger = logging.getLogger("uvicorn.error")

# === Prometheus custom metrics ===
from prometheus_client import Counter, Histogram

external_requests_total = Counter(
    "external_requests_total",
    "Liczba wywołań external_fetch",
    ["outcome"]  # etykieta: ok / error
)

external_request_latency = Histogram(
    "external_request_latency_ms",
    "Czas trwania wywołań external_fetch w ms",
    buckets=[50, 100, 250, 500, 1000, 2000, 5000, 10000]
)


# === Konfiguracja DB ===
DATABASE_URL_STR = os.environ.get("DATABASE_URL")
HF_TOKEN = os.environ.get("HF_TOKEN")
HF_SPACE_ID = os.environ.get("HF_SPACE_ID", "Oleg0509/pets")

if not DATABASE_URL_STR:
    raise ValueError("DATABASE_URL nie jest ustawiona.")
if not HF_TOKEN:
    print("OSTRZEŻENIE: HF_TOKEN nie jest ustawiony.")

engine = create_engine(DATABASE_URL_STR)
SQLAlchemyInstrumentor().instrument(engine=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

class ExternalResult(Base):
    __tablename__ = "external_results"

    id = Column(Integer, primary_key=True, index=True)
    correlation_id = Column(String, index=True, nullable=False)   # unikalny identyfikator requestu
    ext_url = Column(String, nullable=False)                      # URL wywołanego API
    status_code = Column(Integer, nullable=True)                  # kod HTTP odpowiedzi
    duration_ms = Column(Integer, nullable=True)                  # czas trwania requestu w ms
    payload_hash = Column(String, nullable=True)                  # hash odpowiedzi (np. SHA256)
    stored_json = Column(JSON, nullable=True)                     # skrócona odpowiedź w JSON
    created_at = Column(DateTime, default=datetime.utcnow)        # timestamp zapisu


class PredictionLog(Base):
    __tablename__ = "prediction_logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    filename = Column(String, index=True, nullable=True)
    request_data = Column(JSON, nullable=True)
    prediction_result = Column(JSON, nullable=True)
    error_message = Column(String, nullable=True)

def create_db_and_tables():
    max_retries = 10
    wait_seconds = 5
    print("Inicjowanie połączenia z bazą danych...")
    for attempt in range(max_retries):
        try:
            with engine.connect() as conn:
                conn.execute(select(1))
            Base.metadata.create_all(bind=engine)
            print("Połączono z bazą danych.")
            return
        except OperationalError as e:
            print(f"Próba {attempt + 1}: DB niegotowa ({e}) — czekam {wait_seconds}s...")
            time.sleep(wait_seconds)
        except Exception as e:
            print(f"Nieoczekiwany błąd DB: {e}")
            time.sleep(wait_seconds)
    raise Exception("Nie można połączyć z bazą danych.")

gradio_client_instance: Optional[Client] = None

def init_gradio_client():
    global gradio_client_instance
    try:
        gradio_client_instance = Client(HF_SPACE_ID)
        print(f"Połączono ze Space'em: {HF_SPACE_ID}")
        print(gradio_client_instance.view_api(all_endpoints=True))
    except Exception as e:
        print(f"Błąd Space HF: {e}")
        gradio_client_instance = None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class PredictionResponse(BaseModel):
    filename: Optional[str]
    prediction: Any
    log_id: int
    trace_id: Optional[str]

class ErrorResponse(BaseModel):
    detail: str

@app.get("/", summary="Endpoint powitalny")
async def root():
    return {"message": "Witaj w API do logowania predykcji!"}

@app.post("/predict", response_model=PredictionResponse,
          responses={500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
async def predict_image(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not gradio_client_instance:
        raise HTTPException(status_code=503, detail="Space HF nie działa.")

    log_entry = PredictionLog(
        filename=file.filename,
        request_data={"content_type": file.content_type, "size": file.size}
    )

    try:
        with tracer.start_as_current_span("call_hf_space") as span:
            span.set_attribute("filename", file.filename)
            with tempfile.NamedTemporaryFile(delete=True, suffix=file.filename) as temp_file:
                contents = await file.read()
                temp_file.write(contents)
                temp_file_path = temp_file.name

                prediction_result = gradio_client_instance.predict(
                    image=handle_file(temp_file_path),
                    api_name="/classify"
                )
            log_entry.prediction_result = prediction_result

    except Exception as e:
        trace_id = format(get_current_span().get_span_context().trace_id, "032x")
        logger.error(f"Błąd predykcji: {e}, trace_id={trace_id}")
        error_msg = f"Błąd predykcji: {e}"
        log_entry.error_message = error_msg
        try:
            db.add(log_entry)
            db.commit()
            db.refresh(log_entry)
        except Exception as db_e:
            print(f"Błąd zapisu logu błędu: {db_e}")
        raise HTTPException(status_code=500, detail=error_msg)

    try:
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
    except Exception as db_e:
        raise HTTPException(status_code=500, detail=f"Błąd zapisu logu sukcesu: {db_e}")

    trace_id = format(get_current_span().get_span_context().trace_id, "032x")
    logger.info(f"Predykcja OK, trace_id={trace_id}, log_id={log_entry.id}")

    return PredictionResponse(
        filename=file.filename,
        prediction=prediction_result,
        log_id=log_entry.id,
        trace_id=trace_id
    )

@app.get("/logs", response_model=List[Dict[str, Any]])
async def get_logs(limit: int = 20, db: Session = Depends(get_db)):
    try:
        logs = db.scalars(
            select(PredictionLog).order_by(PredictionLog.timestamp.desc()).limit(limit)
        ).all()
        return [{
            "id": log.id,
            "timestamp": log.timestamp,
            "filename": log.filename,
            "request_data": log.request_data,
            "prediction_result": log.prediction_result,
            "error_message": log.error_message
        } for log in logs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Błąd odczytu logów: {e}")
import httpx
import hashlib
import uuid

@app.post("/external/fetch")
async def external_fetch(params: Dict[str, Any] = None, db: Session = Depends(get_db)):
    correlation_id = str(uuid.uuid4())
    ext_url = os.environ.get("EXTERNAL_API_BASE_URL", "https://httpbin.org/get")

    max_connections = int(os.environ.get("OUT_MAX_CONNECTIONS", "100"))
    pool_timeout = float(os.environ.get("OUT_POOL_TIMEOUT_MS", "1000")) / 1000.0
    keepalive = int(os.environ.get("OUT_KEEPALIVE", "20"))
    protocol = os.environ.get("OUT_PROTOCOL", "h1")
    read_timeout = float(os.environ.get("OUT_READ_TIMEOUT", "180"))

    limits = httpx.Limits(
        max_connections=max_connections,
        max_keepalive_connections=keepalive,
        keepalive_expiry=30.0
    )
    timeout = httpx.Timeout(connect=5.0, read=read_timeout, write=5.0, pool=pool_timeout)

    start_time = time.time()
    with tracer.start_as_current_span("external_fetch") as span:
        span.set_attribute("correlation_id", correlation_id)
        span.set_attribute("ext_url", ext_url)
        span.set_attribute("protocol", protocol)
        span.set_attribute("max_connections", max_connections)
        span.set_attribute("keepalive", keepalive)

        try:
            async with httpx.AsyncClient(limits=limits, timeout=timeout, http2=(protocol == "h2")) as client:
                response = await client.get(ext_url, params=params)

            duration_ms = int((time.time() - start_time) * 1000)
            payload_hash = hashlib.sha256(response.content).hexdigest()

            log_entry = ExternalResult(
                correlation_id=correlation_id,
                ext_url=ext_url,
                status_code=response.status_code,
                duration_ms=duration_ms,
                payload_hash=payload_hash,
                stored_json=response.json(),
            )
            db.add(log_entry)
            db.commit()
            db.refresh(log_entry)

            # Prometheus metrics
            external_requests_total.labels(outcome="ok").inc()
            external_request_latency.observe(duration_ms)

            trace_id = format(get_current_span().get_span_context().trace_id, "032x")
            logger.info(f"External call OK, trace_id={trace_id}, correlation_id={correlation_id}")

            return {
                "id": log_entry.id,
                "ext_status": response.status_code,
                "duration_ms": duration_ms,
                "stored": True,
                "correlation_id": correlation_id,
                "trace_id": trace_id,
            }

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            log_entry = ExternalResult(
                correlation_id=correlation_id,
                ext_url=ext_url,
                status_code=None,
                duration_ms=duration_ms,
                payload_hash=None,
                stored_json={"error": str(e)},
            )
            db.add(log_entry)
            db.commit()
            db.refresh(log_entry)

            # Prometheus metrics
            external_requests_total.labels(outcome="error").inc()
            external_request_latency.observe(duration_ms)

            trace_id = format(get_current_span().get_span_context().trace_id, "032x")
            logger.error(f"External call FAILED, trace_id={trace_id}, correlation_id={correlation_id}, error={e}")

            raise HTTPException(status_code=500, detail=f"External call failed: {e}")

if __name__ == "__main__":
    import uvicorn
    print("Uruchamianie serwera Uvicorn...")
    if not DATABASE_URL_STR or not HF_TOKEN:
        print("BŁĄD: Brakuje DATABASE_URL lub HF_TOKEN.")
    else:
        uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
