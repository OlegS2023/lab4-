Lab 4: Load Testing & Outbound Client Tuning
1. Overview
We created a new endpoint /external/fetch in FastAPI. This endpoint makes an outbound HTTP request (HTTP/1.1 or HTTP/2), validates the response, saves a record into the external_results table in Postgres, and returns a summary JSON. All requests produce traces, metrics, and logs that are sent to Prometheus, Loki, and Tempo.

Load tests were executed with k6 using Prometheus Remote Write. Results and screenshots are stored in docs/load-tests/.

2. Environment
-FastAPI + httpx outbound client

-PostgreSQL 15

-OpenTelemetry Collector → Loki, Tempo, Prometheus

-k6 with Prometheus Remote Write

Outbound client settings are configurable with environment variables: 
OUT_MAX_CONNECTIONS, OUT_POOL_TIMEOUT_MS, OUT_KEEPALIVE, OUT_PROTOCOL, OUT_READ_TIMEOUT.

3. k6 Tests
We prepared a k6 script lab4.js with two scenarios:

http1_test → outbound call using HTTP/1.1

http2_test → outbound call using HTTP/2

Each scenario has tags so results can be separated in Grafana. Run command:
