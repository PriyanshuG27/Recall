import http from 'k6/http';
import { check } from 'k6';

export const options = {
  stages: [
    { duration: '10s', target: 5 },
    { duration: '15s', target: 5 },
    { duration: '10s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<3000'],
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const url = `${__ENV.API_URL || 'http://localhost:8000'}/webhook`;
  const chatId = 90000 + __VU; // Unique chat_id per virtual user to simulate real traffic
  const payload = JSON.stringify({
    update_id: Math.floor(Math.random() * 1000000000),
    message: {
      message_id: Math.floor(Math.random() * 100000),
      from: { id: chatId, first_name: `TestUser_${__VU}` },
      chat: { id: chatId },
      text: 'https://instagram.com/reel/C123456',
    },
  });

  const params = { headers: { 'Content-Type': 'application/json' } };
  const res = http.post(url, payload, params);

  check(res, {
    'status is 200': (r) => r.status === 200,
    'ACK under 3000ms': (r) => r.timings.duration < 3000,
  });
}
