import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '10s', target: 3 },
    { duration: '40s', target: 3 },
    { duration: '10s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<1500'],
    http_req_failed: ['rate<0.05'],
  },
};

export default function () {
  const baseUrl = __ENV.API_URL || 'http://127.0.0.1:8000';
  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Cookie': __ENV.AUTH_COOKIE || '',
    },
  };

  const searchRes = http.post(`${baseUrl}/api/search`, JSON.stringify({ query: 'soak test item' }), params);
  check(searchRes, { 'search ok': (r) => r.status === 200 || r.status === 429 });

  sleep(2.0);

  const itemsRes = http.get(`${baseUrl}/api/items?limit=10`, params);
  check(itemsRes, { 'items ok': (r) => r.status === 200 });

  sleep(3.0);
}
