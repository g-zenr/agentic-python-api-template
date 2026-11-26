import http from "k6/http";
import { check } from "k6";

export const options = {
  vus: 10,
  duration: "30s",
  thresholds: {
    http_req_duration: ["p(95)<500"],
    http_req_failed: ["rate<0.01"],
  },
};

export default function () {
  const base = __ENV.BASE_URL || "http://localhost:8000/api/v1";
  const login = http.post(`${base}/auth/login`, JSON.stringify({
    email: __ENV.EMAIL || "user@example.com",
    password: __ENV.PASSWORD || "supersecret",
  }), { headers: { "Content-Type": "application/json" } });
  const token = login.status === 200 ? login.json("data.accessToken") : null;
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const res = http.get(`${base}/notes`, { headers });
  check(res, { "notes ok": (r) => r.status === 200 || r.status === 401 });
}