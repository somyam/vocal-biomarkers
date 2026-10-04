import { expect, test } from "@playwright/test";

// Fake only the hardware and transport boundaries. Exercise the real recorder UI.
test.beforeEach(async ({ page }) => {
  await page.route("**/v1/checkins", route => route.fulfill({
    json: { checkin: { checkin_id: "test-checkin" }, stream_ticket: "test-ticket" },
  }));
  await page.addInitScript(() => {
    const harness = {
      tracks: [] as { readyState: string; stop: () => void }[],
      frames: 0,
      controls: [] as string[],
      processors: [] as any[],
      socket: null as any,
      eventSockets: [] as any[],
      snapshot: null as any,
      failMicrophone: false,
    };
    (window as any).recorderTest = harness;
    Object.defineProperty(navigator.mediaDevices, "getUserMedia", { value: async () => {
      if (harness.failMicrophone) throw new Error("Permission denied");
      const track = { readyState: "live", stop() { this.readyState = "ended"; } };
      harness.tracks.push(track);
      return { getTracks: () => [track] };
    } });
    class FakeAudioContext {
      audioWorklet = { addModule: async () => {} };
      destination = {};
      createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
      async close() {}
    }
    class FakeWorklet {
      port = { onmessage: null as any };
      constructor() { harness.processors.push(this); }
      connect() {}
      disconnect() {}
    }
    class FakeSocket {
      static OPEN = 1;
      readyState = 1;
      onopen: any;
      onmessage: any;
      onclose: any;
      constructor(url: string) {
        if (String(url).includes('/events?')) {
          harness.eventSockets.push(this);
          setTimeout(() => {
            this.onopen?.();
            this.onmessage?.({ data: JSON.stringify({ type: 'checkin.snapshot', sequence: 0, checkin: harness.snapshot }) });
          }, 0);
        } else {
          harness.socket = this;
          setTimeout(() => this.onopen?.(), 0);
        }
      }
      send(data: any) {
        if (typeof data === "string") harness.controls.push(JSON.parse(data).type);
        else harness.frames += 1;
      }
      close() { this.readyState = 3; this.onclose?.(); }
    }
    (window as any).AudioContext = FakeAudioContext;
    (window as any).AudioWorkletNode = FakeWorklet;
    (window as any).WebSocket = FakeSocket;
  });
  await page.goto("/?member=1&live=1");
  await page.getByRole("button", { name: "Morning Check-in", exact: true }).click();
  await page.getByRole("button", { name: "Start recording Morning Check-in", exact: true }).click();
  await expect(page.getByRole("button", { name: "Pause Morning Check-in recording" })).toBeVisible();
});

test("pause stops microphone, queued frames, captions, and timer; resume reacquires capture", async ({ page }) => {
  await page.evaluate(() => {
    const h = (window as any).recorderTest;
    h.oldFrame = h.processors[0].port.onmessage;
    h.oldFrame({ data: new ArrayBuffer(20) });
    h.socket.onmessage({ data: JSON.stringify({ type: "transcript_partial", text: "Before pause" }) });
  });
  await expect(page.getByText("Before pause", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Pause Morning Check-in recording" }).click();
  const timer = await page.locator(".recording-timer").textContent();
  await page.evaluate(() => {
    const h = (window as any).recorderTest;
    h.oldFrame({ data: new ArrayBuffer(20) });
    h.socket.onmessage({ data: JSON.stringify({ type: "transcript_partial", text: "Late caption" }) });
  });
  await expect(page.getByText("Late caption", { exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => {
    const h = (window as any).recorderTest;
    return { frames: h.frames, tracks: h.tracks.map((t: any) => t.readyState), controls: h.controls };
  })).toEqual({ frames: 1, tracks: ["ended"], controls: ["checkin.start", "checkin.pause"] });
  await page.waitForTimeout(1100);
  await expect(page.locator(".recording-timer")).toHaveText(timer!);
  await page.getByRole("button", { name: "Resume Morning Check-in recording" }).click();
  await expect(page.getByRole("button", { name: "Pause Morning Check-in recording" })).toBeVisible();
  await page.evaluate(() => {
    const h = (window as any).recorderTest;
    h.oldFrame({ data: new ArrayBuffer(20) });
    h.processors[1].port.onmessage({ data: new ArrayBuffer(20) });
  });
  expect(await page.evaluate(() => {
    const h = (window as any).recorderTest;
    return { frames: h.frames, tracks: h.tracks.map((t: any) => t.readyState), controls: h.controls };
  })).toEqual({ frames: 2, tracks: ["ended", "live"], controls: ["checkin.start", "checkin.pause", "checkin.resume"] });
  await page.getByRole("button", { name: "Close Morning Check-in" }).click();
  expect(await page.evaluate(() => (window as any).recorderTest.tracks.every((t: any) => t.readyState === "ended"))).toBe(true);
});

test("failed microphone reacquisition keeps the recorder paused", async ({ page }) => {
  await page.getByRole("button", { name: "Pause Morning Check-in recording" }).click();
  await expect(page.getByText("Paused", { exact: true })).toBeVisible();
  await page.evaluate(() => { (window as any).recorderTest.failMicrophone = true; });
  await page.getByRole("button", { name: "Resume Morning Check-in recording" }).click();
  await expect(page.getByRole("alert")).toContainText("still paused");
  expect(await page.evaluate(() => (window as any).recorderTest.controls)).toEqual(["checkin.start", "checkin.pause"]);
});

test("End Turn sits beside Save Conversation, stops capture, and displays the real reply event", async ({ page }) => {
  const save = page.getByRole("button", { name: "Save Conversation", exact: true });
  const endTurn = page.getByRole("button", { name: "End Turn", exact: true });
  await expect(save).toBeVisible();
  await expect(endTurn).toBeVisible();
  const saveBox = (await save.boundingBox())!;
  const turnBox = (await endTurn.boundingBox())!;
  expect(turnBox.x).toBeGreaterThan(saveBox.x + saveBox.width);
  expect(Math.abs(turnBox.y - saveBox.y)).toBeLessThan(2);
  await page.evaluate(() => {
    const h = (window as any).recorderTest;
    h.processors[0].port.onmessage({ data: new ArrayBuffer(20) });
  });
  await endTurn.click();
  await expect(endTurn).toBeDisabled();
  await expect(save).toBeDisabled();
  expect(await page.evaluate(() => {
    const h = (window as any).recorderTest;
    return { controls: h.controls, tracks: h.tracks.map((t: any) => t.readyState) };
  })).toEqual({ controls: ["checkin.start", "checkin.turn.end"], tracks: ["ended"] });
  await page.evaluate(() => {
    const socket = (window as any).recorderTest.socket;
    socket.onmessage({ data: JSON.stringify({ type: "turn_transcript", turn_id: "turn-1", text: "I feel calmer today." }) });
    socket.onmessage({ data: JSON.stringify({ type: "turn_result", turn_id: "turn-1", transcript: "I feel calmer today.", reply: "What helped you feel calmer?", model: "test-sonnet" }) });
  });
  await expect(page.getByText("I feel calmer today.", { exact: true })).toBeVisible();
  await expect(page.getByText("What helped you feel calmer?", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Resume Morning Check-in recording" })).toBeEnabled();
  await expect(endTurn).toBeEnabled();
  await expect(save).toBeEnabled();
  await page.screenshot({ path: "/tmp/vocal-end-turn.png" });
  await save.click();
  expect(await page.evaluate(() => (window as any).recorderTest.controls)).toEqual(["checkin.start", "checkin.turn.end", "checkin.end"]);
  expect(await page.evaluate(() => (window as any).recorderTest.tracks.length)).toBe(1);
});

test("Sonnet failures remain visible and End Turn can be retried", async ({ page }) => {
  await page.evaluate(() => (window as any).recorderTest.processors[0].port.onmessage({ data: new ArrayBuffer(20) }));
  await page.getByRole("button", { name: "End Turn", exact: true }).click();
  await page.evaluate(() => (window as any).recorderTest.socket.onmessage({ data: JSON.stringify({ type: "error", code: "conversation_failed", message: "Sonnet is unavailable. Try again." }) }));
  await expect(page.getByRole("alert")).toContainText("Sonnet is unavailable");
  await page.getByRole("button", { name: "End Turn", exact: true }).click();
  expect(await page.evaluate(() => (window as any).recorderTest.controls)).toEqual(["checkin.start", "checkin.turn.end", "checkin.turn.end"]);
});

function savedPayload() {
  return { checkin_id: 'test-checkin', recording_completed_at: '2026-10-04T00:00:00' as string | null, analysis_status: 'complete', completed_at: '2026-10-04T00:00:00' as string | null, transcript: 'Full transcript must not be repeated', conversation_messages: [
    { id: 'opening', role: 'assistant', text: 'How are you feeling today?', status: 'done' },
    { id: 'voice-user', role: 'user', text: 'Spoken first turn', status: 'done' },
    { id: 'voice-reply', role: 'assistant', text: 'Voice reply', status: 'done' },
    { id: 'saved-tail', role: 'user', text: 'Final saved speech', status: 'saved' },
  ] as any[] };
}

async function saveConversation(page: import('@playwright/test').Page, payload: ReturnType<typeof savedPayload>) {
  await page.route('**/v1/checkins/test-checkin/events-ticket', async route => {
    await page.evaluate(value => { (window as any).recorderTest.snapshot = value; }, payload);
    await route.fulfill({ json: { events_path: '/v1/checkins/test-checkin/events?ticket=fresh-ticket' } });
  });
  await page.route('**/v1/checkins/test-checkin/finish', route => route.fulfill({ json: payload }));
  await page.route('**/v1/checkins/test-checkin', route => route.fulfill({ json: payload }));
  await page.evaluate(() => {
    const h = (window as any).recorderTest;
    h.processors[0].port.onmessage({ data: new ArrayBuffer(20) });
    h.socket.onmessage({ data: JSON.stringify({ type: 'transcript_partial', text: 'Final saved speech' }) });
  });
  await page.getByRole('button', { name: 'Pause Morning Check-in recording' }).click();
  await page.getByRole('button', { name: 'Save Conversation', exact: true }).click();
  await expect(page.getByText('Final saved speech', { exact: true })).toBeVisible();
  await page.evaluate(() => (window as any).recorderTest.socket.onmessage({ data: JSON.stringify({ type: 'result' }) }));
  await expect(page.getByRole('region', { name: 'Saved conversation', exact: true })).toBeVisible();
}

test('Save shows full history; text chat persists and reopens without microphone capture', async ({ page }) => {
  const payload = savedPayload();
  await saveConversation(page, payload);
  for (const message of payload.conversation_messages) await expect(page.getByText(message.text, { exact: true })).toHaveCount(1);
  await expect(page.getByText(payload.transcript)).toHaveCount(0);
  await expect(page.getByText('Conversation saved', { exact: true })).toBeVisible();
  await page.route('**/v1/checkins/test-checkin/messages', async route => {
    const body = route.request().postDataJSON();
    expect(body.text).toBe('My typed reply');
    payload.conversation_messages.push({ id: `${body.request_id}-user`, role: 'user', text: body.text, status: 'done', request_id: body.request_id },
      { id: `${body.request_id}-assistant`, role: 'assistant', text: 'Claude text reply', status: 'done' });
    await route.fulfill({ json: payload });
  });
  const input = page.getByRole('textbox', { name: 'Reply to your coach' });
  await input.fill('My typed reply');
  await page.screenshot({ path: '/tmp/vocal-saved-keyboard.png' });
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(page.getByText('Claude text reply', { exact: true })).toBeVisible();
  await expect(input).toHaveValue('');
  await page.getByRole('button', { name: 'Close Morning Check-in' }).click();
  await page.getByRole('button', { name: 'Morning Check-in', exact: true }).click();
  await expect(page.getByText('Claude text reply', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => (window as any).recorderTest.tracks.map((track: any) => track.readyState))).toEqual(['ended']);
  await page.screenshot({ path: '/tmp/vocal-saved-conversation.png' });
});

test('failed text sends preserve the draft and retry the same request ID', async ({ page }) => {
  const payload = savedPayload();
  await saveConversation(page, payload);
  const bodies: any[] = [];
  await page.route('**/v1/checkins/test-checkin/messages', async route => {
    const body = route.request().postDataJSON();
    bodies.push(body);
    if (bodies.length === 1) { await route.abort(); return; }
    await route.fulfill({ json: { ...payload, conversation_messages: [...payload.conversation_messages,
      { id: `${body.request_id}-user`, request_id: body.request_id, role: 'user', text: body.text, status: 'done' },
      { id: 'reply', role: 'assistant', text: 'Recovered reply', status: 'done' }] } });
  });
  await page.getByRole('textbox', { name: 'Reply to your coach' }).fill('Keep my draft');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Please retry');
  await expect(page.getByRole('textbox')).toHaveValue('Keep my draft');
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(page.getByText('Recovered reply')).toBeVisible();
  expect(bodies).toHaveLength(2);
  expect(bodies[0]).toEqual(bodies[1]);
  await expect(page.getByText('Keep my draft', { exact: true })).toHaveCount(1);
});

test('pending save shows scrollable history and disables Send until completion', async ({ page }) => {
  const payload = savedPayload();
  payload.completed_at = null;
  payload.recording_completed_at = null;
  payload.analysis_status = "pending";
  payload.conversation_messages.push(...Array.from({ length: 30 }, (_, i) => ({ id: `history-${i}`, role: i % 2 ? 'assistant' : 'user', text: `Earlier message ${i}: this is a longer conversation to review.`, status: 'done' })));
  await saveConversation(page, payload);
  await expect(page.getByRole('textbox')).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeDisabled();
  const scroll = page.locator('.saved-history .mobile-scroll');
  expect(await scroll.evaluate(node => node.scrollHeight > node.clientHeight && node.scrollTop > 0)).toBe(true);
  await scroll.evaluate(node => { node.scrollTop = 0; });
  await expect(page.getByText('How are you feeling today?', { exact: true })).toBeVisible();
  payload.recording_completed_at = '2026-10-04T00:00:00';
  await pushSnapshot(page, payload, 1);
  await expect(page.getByRole('textbox')).toBeEnabled({ timeout: 5000 });
});

async function pushSnapshot(page: import('@playwright/test').Page, payload: ReturnType<typeof savedPayload>, sequence: number) {
  await page.evaluate(({ payload, sequence }) => {
    const h = (window as any).recorderTest;
    h.snapshot = payload;
    h.eventSockets.at(-1).onmessage({ data: JSON.stringify({ type: 'checkin.snapshot', sequence, checkin: payload }) });
  }, { payload, sequence });
}

test('analysis arrives by notification; reconnect recovers missed events without polling or capture', async ({ page }) => {
  const payload = savedPayload();
  payload.completed_at = null;
  payload.analysis_status = 'pending';
  let gets = 0;
  let tickets = 0;
  page.on('request', request => {
    if (request.url().endsWith('/v1/checkins/test-checkin') && request.method() === 'GET') gets++;
    if (request.url().endsWith('/events-ticket')) tickets++;
  });
  await saveConversation(page, payload);
  await expect(page.getByRole('textbox')).toBeEnabled();
  await expect(page.getByText('Audio analysis pending', { exact: false })).toBeVisible();
  await page.getByRole('textbox').fill('Keep draft during reconnect');
  const initialTickets = tickets; // React StrictMode may abort the first effect request.
  await page.waitForTimeout(3200);
  expect(gets).toBe(0);
  expect(tickets).toBe(initialTickets);
  payload.analysis_status = 'complete';
  payload.completed_at = '2026-10-04T00:00:00';
  await page.evaluate(() => (window as any).recorderTest.eventSockets.at(-1).close());
  await expect(page.getByText('Audio analysis complete', { exact: false })).toBeVisible();
  await expect(page.getByRole('textbox')).toHaveValue('Keep draft during reconnect');
  expect(tickets).toBe(initialTickets + 1);
  expect(gets).toBe(0);
  expect(await page.evaluate(() => (window as any).recorderTest.tracks.map((t: any) => t.readyState))).toEqual(['ended']);
});

test('Check analysis once is an explicit single request', async ({ page }) => {
  const payload = savedPayload();
  payload.completed_at = null;
  payload.analysis_status = 'delayed';
  let checks = 0;
  await page.route('**/analysis/refresh', route => {
    checks++;
    return route.fulfill({ json: { ...payload, completed_at: '2026-10-04T00:00:00', analysis_status: 'complete' } });
  });
  await saveConversation(page, payload);
  expect(checks).toBe(0);
  await page.getByRole('button', { name: 'Check analysis once' }).click();
  await expect(page.getByText('Audio analysis complete', { exact: false })).toBeVisible();
  expect(checks).toBe(1);
});
