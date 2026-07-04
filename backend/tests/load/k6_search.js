import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 3,
  duration: '20s',
  thresholds: {
    http_req_duration: ['p(95)<1500'],
    http_req_failed: ['rate<0.05'],
  },
};

export default function () {
  const url = `${__ENV.API_URL || 'http://127.0.0.1:8000'}/api/search`;
  const payload = JSON.stringify({ query: 'machine learning architecture' });

  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Cookie': __ENV.AUTH_COOKIE || ''
    },
  };
  
  const res = http.post(url, payload, params);

  check(res, {
    'status is 200': (r) => r.status === 200,
    'search under 1500ms': (r) => r.timings.duration < 1500,
  });

  // Sleep to pace requests under the 60 req/min rate limit
  sleep(1.5);
}
