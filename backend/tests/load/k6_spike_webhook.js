import http from 'k6/http';
import { check } from 'k6';

export const options = {
  stages: [
    { duration: '10s', target: 2 },
    { duration: '10s', target: 10 }, // Spike to 10 VUs (Neon connections pool limit friendly)
    { duration: '15s', target: 10 },
    { duration: '10s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<3000'],
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const url = `${__ENV.API_URL || 'http://127.0.0.1:8000'}/webhook`;
  const payload = JSON.stringify({
    update_id: Math.floor(Math.random() * 10000000),
    message: {
      message_id: Math.floor(Math.random() * 50000),
      from: { id: 88888, first_name: 'SpikeTester' },
      chat: { id: 88888 },
      text: 'https://youtube.com/watch?v=dQw4w9WgXcQ',
    },
  });

  const params = { headers: { 'Content-Type': 'application/json' } };
  const res = http.post(url, payload, params);

  check(res, {
    'status is 200': (r) => r.status === 200,
    'ACK under 3000ms during spike': (r) => r.timings.duration < 3000,
  });
}
