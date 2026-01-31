const HUGO_BACKEND_URL = process.env.HUGO_BACKEND_URL || "http://localhost:8080";

interface LookAroundParams {
  query?: string;
}

interface SpeakParams {
  text: string;
}

export async function look_around(params: LookAroundParams): Promise<string> {
  const query = params.query || "Describe what you see in detail.";
  const resp = await fetch(`${HUGO_BACKEND_URL}/tools/vision/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });

  if (!resp.ok) {
    return `Vision error: ${resp.status} ${resp.statusText}`;
  }

  const data = (await resp.json()) as { description: string };
  return data.description;
}

export async function speak_to_user(params: SpeakParams): Promise<string> {
  const resp = await fetch(`${HUGO_BACKEND_URL}/tools/voice/speak`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: params.text }),
  });

  if (!resp.ok) {
    return `Speech error: ${resp.status} ${resp.statusText}`;
  }

  return "Spoken successfully.";
}
