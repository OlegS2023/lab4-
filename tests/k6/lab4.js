import http from 'k6/http';
import { check, sleep } from 'k6';

// === Konfiguracja testu ===
export const options = {
  vus: 20,              // liczba wirtualnych użytkowników
  duration: '2m',       // czas trwania testu (2 minuty)
  thresholds: {
    http_req_duration: ['p(95)<2000'], // p95 latency < 2s
    http_req_failed: ['rate<0.05'],    // mniej niż 5% błędów
  },
};

// === Funkcja główna ===
export default function () {
  const url = 'http://localhost:8010/external/fetch';
  const payload = JSON.stringify({ resource_id: 42 });
  const params = {
    headers: { 'Content-Type': 'application/json' },
  };

  const res = http.post(url, payload, params);

  // Walidacja odpowiedzi
  check(res, {
    'status is 200': (r) => r.status === 200,
  });

  sleep(1); // pauza między żądaniami
}
