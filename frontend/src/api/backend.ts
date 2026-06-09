const BACKEND_URL = "http://localhost:17890";

export async function checkHealth() {
  const res = await fetch(`${BACKEND_URL}/health`);
  return res.json();
}

export async function getTrips() {
  const res = await fetch(`${BACKEND_URL}/api/trips`);
  return res.json();
}

export async function archivePreview(body: object) {
  const res = await fetch(`${BACKEND_URL}/api/archive/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}
