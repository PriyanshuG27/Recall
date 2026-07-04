import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '10s', target: 5 },
    { duration: '15s', target: 5 },
    { duration: '10s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<1500'],
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const url = `${__ENV.API_URL || 'http://127.0.0.1:8000'}/api/items?limit=20&offset=0`;
  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Cookie': __ENV.AUTH_COOKIE || '',
    },
  };

  const res = http.get(url, params);

  check(res, {
    'status is 200': (r) => r.status === 200,
    'user items retrieval under 1500ms': (r) => r.timings.duration < 1500,
  });

  sleep(1.0);
}
