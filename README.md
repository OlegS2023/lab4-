Project: Monitoring FastAPI + k6 + Grafana
1. Project Goal
The goal of this project is to build and validate a complete monitoring stack: FastAPI → k6 → VictoriaMetrics → Grafana. This setup enables running load tests and observing metrics in real time.

2. Environment Setup
All components are run in Docker (FastAPI, Prometheus/VictoriaMetrics, Grafana).

Load tests are executed using k6.

Example command to run a test:

Kod
& "C:\Program Files\k6\k6.exe" run -o experimental-prometheus-rw --tag testid="lab4-osh-20251129" "C:\k6tests\lab4.js"
3. k6 Test Configuration
File lab4.js:

js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 20,              // number of virtual users
  duration: '2m',       // test duration
  thresholds: {
    http_req_duration: ['p(95)<2000'], // p95 latency < 2s
    http_req_failed: ['rate<0.05'],    // less than 5% errors
  },
};

export default function () {
  const url = 'http://localhost:8010/external/fetch';
  const payload = JSON.stringify({ resource_id: 42 });
  const params = { headers: { 'Content-Type': 'application/json' } };

  const res = http.post(url, payload, params);

  check(res, { 'status is 200': (r) => r.status === 200 });

  sleep(1);
}
4. Grafana Metrics
Requests per second (RPS)
Kod
sum(rate(k6_http_reqs_total[1m]))
Error rate (errors per second)
Kod
sum(rate(k6_http_req_failed_total[1m]))
Error % (percentage of failed requests)
Kod
100 * (
  sum(rate(k6_http_req_failed_total[1m]))
  /
  sum(rate(k6_http_reqs_total[1m]))
)
Latency p95
Kod
histogram_quantile(
  0.95,
  sum(rate(k6_http_req_duration_bucket[1m])) by (le)
)
Latency p99
Kod
histogram_quantile(
  0.99,
  sum(rate(k6_http_req_duration_bucket[1m])) by (le)
)
5. Grafana Dashboard
Prepared panels include:

RPS (requests per second)

Error rate and Error %

Latency p95/p99

Additional metrics: blocked, connecting, sending, waiting (p95/p99)

