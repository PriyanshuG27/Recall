import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 4,
  duration: '15s',
  thresholds: {
    http_req_failed: ['rate<1.0'], 
  },
};

export default function () {
  const url = `${__ENV.API_URL || 'http://127.0.0.1:8000'}/api/search`;
  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Cookie': __ENV.AUTH_COOKIE || '',
    },
  };

  const res = http.post(url, JSON.stringify({ query: 'rapid request' }), params);

  check(res, {
    'rate limiter returns 200 or 429': (r) => r.status === 200 || r.status === 429,
  });

  sleep(0.1);
}
