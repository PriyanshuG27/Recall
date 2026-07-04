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
  const url = `${__ENV.API_URL || 'http://127.0.0.1:8000'}/api/me`;
  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Cookie': __ENV.AUTH_COOKIE || '',
      'X-Telegram-Init-Data': __ENV.TELEGRAM_INIT_DATA || '',
    },
  };

  const res = http.get(url, params);

  check(res, {
    'status is 200 or 401': (r) => r.status === 200 || r.status === 401,
    'auth validation under 1500ms': (r) => r.timings.duration < 1500,
  });

  sleep(1.0);
}
