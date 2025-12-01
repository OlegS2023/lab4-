import http from 'k6/http';
import { sleep } from 'k6';

export const options = {
  scenarios: {
    spike: {
      executor: 'constant-arrival-rate',
      rate: 200,          // Spike load: 200 RPS
      timeUnit: '1s',
      duration: '45s',
      preAllocatedVUs: 50,
      maxVUs: 200,
      exec: 'spike_test',
    },
    timeout: {
      executor: 'constant-vus',
      vus: 10,
      duration: '1m',
      exec: 'timeout_test',
    },
    maxconn: {
      executor: 'constant-vus',
      vus: 50,
      duration: '1m',
      exec: 'maxconn_test',
    },
    proto_http1: {
      executor: 'constant-vus',
      vus: 20,
      duration: '2m',
      exec: 'http1_test',
    },
    proto_http2: {
      executor: 'constant-vus',
      vus: 20,
      duration: '2m',
      exec: 'http2_test',
    },
  },
};

// Spike load
export function spike_test() {
  http.post('http://localhost:8010/external/fetch', JSON.stringify({ resource_id: 42 }), {
    headers: { 'Content-Type': 'application/json' },
    httpVersion: '1.1',
    tags: { scenario: 'spike' },
  });
  sleep(1);
}

// Timeout test
export function timeout_test() {
  http.post('http://localhost:8010/external/fetch?delay=180', JSON.stringify({ resource_id: 42 }), {
    headers: { 'Content-Type': 'application/json' },
    httpVersion: '1.1',
    tags: { scenario: 'timeout' },
  });
  sleep(1);
}

// Max connections sweep
export function maxconn_test() {
  http.post('http://localhost:8010/external/fetch', JSON.stringify({ resource_id: 42 }), {
    headers: { 'Content-Type': 'application/json' },
    httpVersion: '1.1',
    tags: { scenario: 'maxconn' },
  });
  sleep(1);
}

// Protocol comparison
export function http1_test() {
  http.post('http://localhost:8010/external/fetch', JSON.stringify({ resource_id: 42 }), {
    headers: { 'Content-Type': 'application/json' },
    httpVersion: '1.1',
    tags: { proto: 'HTTP/1.1' },
  });
  sleep(1);
}

export function http2_test() {
  http.post('http://localhost:8010/external/fetch', JSON.stringify({ resource_id: 42 }), {
    headers: { 'Content-Type': 'application/json' },
    httpVersion: '2',
    tags: { proto: 'HTTP/2' },
  });
  sleep(1);
}
