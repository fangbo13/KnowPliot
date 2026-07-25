import http from 'k6/http';
import { check } from 'k6';
import { Rate, Trend } from 'k6/metrics';
import exec from 'k6/execution';

const BASE_URL = __ENV.BASE_URL || 'http://host.docker.internal:18080';
const acceptance = new Trend('send_acceptance', true);
const ordinaryRead = new Trend('ordinary_read', true);
const unexpectedErrors = new Rate('unexpected_errors');

export const options = {
  setupTimeout: '5m',
  scenarios: {
    mixed_rest: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RATE || 20),
      timeUnit: '1s',
      duration: `${Number(__ENV.DURATION_SECONDS || 120)}s`,
      preAllocatedVUs: Number(__ENV.USERS || 10),
      maxVUs: Number(__ENV.USERS || 10) * 2,
    },
  },
  thresholds: {
    send_acceptance: ['p(95)<800'],
    ordinary_read: ['p(95)<500', 'p(99)<1500'],
    unexpected_errors: ['rate<0.001'],
  },
};

function uuid() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (char) => {
    const value = Math.floor(Math.random() * 16);
    return (char === 'x' ? value : (value & 3) | 8).toString(16);
  });
}

export function setup() {
  const users = Number(__ENV.USERS || 10);
  const userOffset = Number(__ENV.USER_OFFSET || 0);
  const identities = [];
  for (let index = 0; index < users; index += 1) {
    const userIndex = userOffset + index;
    const email = `capacity${String(userIndex).padStart(5, '0')}@example.invalid`;
    const login = http.post(`${BASE_URL}/api/v1/auth/token/`, JSON.stringify({ email, password: 'CapacityOnly!2026' }), {
      headers: { 'Content-Type': 'application/json' },
    });
    if (login.status !== 200) throw new Error(`login_failed:${login.status}`);
    const access = login.json('access');
    const auth = { Authorization: `Bearer ${access}` };
    const spacesResponse = http.get(`${BASE_URL}/api/v1/spaces/`, { headers: auth });
    const spaces = spacesResponse.json('results') || spacesResponse.json();
    const spaceId = spaces[0].id;
    const headers = { ...auth, 'X-Space-Id': spaceId };
    const sessionsResponse = http.get(`${BASE_URL}/api/v1/chat/sessions/`, { headers });
    const sessions = sessionsResponse.json('results') || sessionsResponse.json();
    identities.push({ headers, sessionIds: sessions.map((session) => session.id) });
  }
  return identities;
}

export default function (identities) {
  const identity = identities[exec.scenario.iterationInTest % identities.length];
  const choice = exec.scenario.iterationInTest % 5;
  const sessionId = identity.sessionIds[exec.scenario.iterationInTest % identity.sessionIds.length];
  let response;
  if (choice === 4) {
    response = http.post(`${BASE_URL}/api/v1/chat/sessions/${sessionId}/send/`, JSON.stringify({
      content: 'REST capacity acceptance', client_request_id: uuid(), protocol_version: 3,
      answer_mode: 'fast', thinking_enabled: false,
    }), { headers: { ...identity.headers, 'Content-Type': 'application/json' } });
    acceptance.add(response.timings.duration);
    const validCapacityRejection = response.status === 429
      && Boolean(response.headers['Retry-After'])
      && response.json('code') === 'generation_capacity_reached';
    unexpectedErrors.add(!(response.status === 202 || validCapacityRejection));
    check(response, { 'acceptance contract': (item) => item.status === 202 || validCapacityRejection });
    return;
  }
  const paths = [
    '/api/v1/spaces/',
    '/api/v1/chat/sessions/',
    `/api/v1/chat/sessions/${sessionId}/messages/`,
    '/api/v1/notifications/unread-count/',
  ];
  response = http.get(`${BASE_URL}${paths[choice]}`, { headers: identity.headers });
  ordinaryRead.add(response.timings.duration);
  unexpectedErrors.add(response.status >= 500 || response.status === 0);
  check(response, { 'ordinary read succeeds': (item) => item.status === 200 });
}
