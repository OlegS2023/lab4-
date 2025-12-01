# Lab 4: Load Testing & Outbound Client Tuning

---

## k6 Tests

### 1. Overview
We created a new endpoint `/external/fetch` in FastAPI.  
This endpoint makes an outbound HTTP request (HTTP/1.1 or HTTP/2), validates the response, saves a record into the `external_results` table in Postgres, and returns a summary JSON.  
All requests produce traces, metrics, and logs that are sent to Prometheus, Loki, and Tempo.  

### 2. Environment
- FastAPI + httpx outbound client  
- PostgreSQL 15  
- OpenTelemetry Collector → Loki, Tempo, Prometheus  
- k6 with Prometheus Remote Write  

Outbound client settings are configurable with environment variables:  
`OUT_MAX_CONNECTIONS`, `OUT_POOL_TIMEOUT_MS`, `OUT_KEEPALIVE`, `OUT_PROTOCOL`, `OUT_READ_TIMEOUT`.

### 3. k6 Script
We prepared a k6 script `lab4.js` with two scenarios:
- `http1_test` → outbound call using HTTP/1.1  
- `http2_test` → outbound call using HTTP/2  

Run command:
```powershell
cd ./tests/k6
& "C:\Program Files\k6\k6.exe" run -o experimental-prometheus-rw .\lab4.js
## 4. Experiments

### Spike Load
![Spike RPS](grafanatests\01-spike-rps.png)  
![Spike Error %](docs/load-tests/01-spike-error.png)  
![Spike Latency p95](docs/load-tests/01-spike-latency.png)

**Setup:** 200 RPS, 45s, HTTP/1.1, maxconn=100, keepalive=20.  
**Findings:**  
- System sustained full load without errors.  
- p95 latency stable (<200ms).  
- Connection pool never saturated.  
**Conclusion:** Baseline path is healthy and stable under sudden bursts.

---

### Timeout 180s
![Timeout RPS](docs/load-tests/02-timeout-rps.png)  
![Timeout Error %](docs/load-tests/02-timeout-error.png)  
![Timeout Latency p95](docs/load-tests/02-timeout-latency.png)

**Setup:** External delay 180s, 10 VUs, HTTP/1.1.  
**Findings:**  
- Client did not fail early.  
- Latency increased significantly.  
- Error % remained low.  
**Conclusion:** System tolerates long external delays without crashing.

---

### Max Connections Sweep
![Maxconn RPS](docs/load-tests/03-maxconn-rps.png)  
![Maxconn Error %](docs/load-tests/03-maxconn-error.png)  
![Maxconn Latency p95](docs/load-tests/03-maxconn-latency.png)

**Setup:** Sweep connection pool sizes (10–100).  
**Findings:**  
- Small pools (10–20) caused errors.  
- Best range was 50–100.  
**Conclusion:** Optimal pool size ensures stability and throughput.

---

### Keep‑Alive Sweep
![Keepalive RPS](docs/load-tests/04-keepalive-rps.png)  
![Keepalive Error %](docs/load-tests/04-keepalive-error.png)  
![Keepalive Latency p95](docs/load-tests/04-keepalive-latency.png)

**Setup:** Sweep keep‑alive values (10–50).  
**Findings:**  
- Best results with 20–50.  
- Too small caused churn and errors.  
**Conclusion:** Proper keep‑alive tuning improves efficiency.

---

### Protocol Comparison (HTTP/1.1 vs HTTP/2)
![HTTP/1.1](docs/load-tests/05-h1.png)  
![HTTP/2](docs/load-tests/05-h2.png)  
![Latency Comparison](docs/load-tests/05-proto-latency.png)

**Setup:** 20 VUs, 2m, POST /external/fetch.  
**Findings:**  
- HTTP/2 showed lower latency and better concurrency.  
- HTTP/1.1 stable but slightly higher p95 latency.  
**Conclusion:** HTTP/2 is recommended for outbound client.

---

### Slow Postgres
![Slow Postgres RPS](docs/load-tests/06-slowpost-rps.png)  
![Slow Postgres Error %](docs/load-tests/06-slowpost-error.png)  
![Slow Postgres Latency p95](docs/load-tests/06-slowpost-latency.png)

**Setup:** Artificial database slowdown.  
**Findings:**  
- Latency increased.  
- System stayed stable.  
**Conclusion:** Database slowness impacts latency but does not destabilize system.