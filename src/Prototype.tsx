import { useEffect, useRef, useState, type PointerEvent } from "react";
import { MicrophoneIcon } from "@phosphor-icons/react";
import {
  ActivityLogIcon,
  BarChartIcon,
  CheckIcon,
  Cross1Icon,
  ChevronDownIcon,
  ChevronRightIcon,
  FileTextIcon,
  HeartIcon,
  LightningBoltIcon,
  MixerHorizontalIcon,
  PauseIcon,
  PlayIcon,
  PlusIcon,
  SunIcon,
} from "@radix-ui/react-icons";
import { MobileScroll } from "./mobile";

type Tab = "today" | "trends";
type Frequency = "Daily" | "Weekly" | "Custom";

type Habit = {
  id: string;
  name: string;
  detail: string;
  Icon: typeof SunIcon;
};

const habits: Habit[] = [
  { id: "hydrate", name: "Hydrate", detail: "First glass before coffee", Icon: LightningBoltIcon },
  { id: "glutathione", name: "Liposomal Glutathione", detail: "Morning protocol", Icon: MixerHorizontalIcon },
  { id: "light", name: "Morning Light", detail: "10 minutes outdoors", Icon: SunIcon },
  { id: "brain", name: "Morning Check-in", detail: "Voice reflection", Icon: FileTextIcon },
  { id: "meditation", name: "Meditation", detail: "10 quiet minutes", Icon: HeartIcon },
  { id: "cold", name: "Clinic Visit — Cold Plunge", detail: "Recovery appointment", Icon: ActivityLogIcon },
  { id: "workout", name: "Workout", detail: "Strength training · 45 min", Icon: BarChartIcon },
];

const frequencies: Frequency[] = ["Daily", "Weekly", "Custom"];

export default function Prototype() {
  const [tab, setTab] = useState<Tab>("today");
  const [completed, setCompleted] = useState<Set<string>>(() => new Set());
  const [brainOpen, setBrainOpen] = useState(false);
  const [brainTranscript, setBrainTranscript] = useState<string | null>(null);
  const [frequency, setFrequency] = useState<Frequency>("Daily");
  const [addHabitOpen, setAddHabitOpen] = useState(true);

  function toggleHabit(id: string) {
    setCompleted((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function completeBrainDump(transcript: string | null) {
    setCompleted((current) => new Set(current).add("brain"));
    setBrainTranscript(transcript);
  }

  return (
    <div className="longevity-app" data-testid="longevity-app">
      <MobileScroll className="app-screen">
        <main className="screen-content" aria-label={tab === "today" ? "Today" : "Trends"}>
          {tab === "today" ? (
            <TodayScreen
              completed={completed}
              brainOpen={brainOpen}
              frequency={frequency}
              addHabitOpen={addHabitOpen}
              onToggle={toggleHabit}
              onBrainToggle={() => setBrainOpen((value) => !value)}
              onFrequency={setFrequency}
              onAddHabit={() => setAddHabitOpen((value) => !value)}
            />
          ) : (
            <TrendsScreen />
          )}
        </main>
      </MobileScroll>

      {tab === "today" && brainOpen ? (
        <MorningCheckInOverlay
          onClose={() => setBrainOpen(false)}
          onComplete={completeBrainDump}
          onViewData={() => {
            setBrainOpen(false);
            setTab("trends");
          }}
          transcript={brainTranscript}
        />
      ) : null}

      <nav className="bottom-nav" aria-label="Primary navigation">
        <button type="button" className={tab === "today" ? "nav-item is-active" : "nav-item"} onClick={() => setTab("today")} aria-current={tab === "today" ? "page" : undefined}>
          <SunIcon width={24} height={24} />
          <span>Today</span>
        </button>
        <button type="button" className={tab === "trends" ? "nav-item is-active" : "nav-item"} onClick={() => setTab("trends")} aria-current={tab === "trends" ? "page" : undefined}>
          <BarChartIcon width={24} height={24} />
          <span>Trends</span>
        </button>
      </nav>
    </div>
  );
}

function TodayScreen({ completed, brainOpen, frequency, addHabitOpen, onToggle, onBrainToggle, onFrequency, onAddHabit }: {
  completed: Set<string>;
  brainOpen: boolean;
  frequency: Frequency;
  addHabitOpen: boolean;
  onToggle: (id: string) => void;
  onBrainToggle: () => void;
  onFrequency: (value: Frequency) => void;
  onAddHabit: () => void;
}) {
  return (
    <>
      <header className="today-header">
        <p className="eyebrow"><span>Sunday, September 20, 2026</span></p>
        <h1>Good morning, Maya</h1>
      </header>

      <section className="habit-list" aria-label="Daily habits">
        {habits.map((habit) => {
          const isBrainDump = habit.id === "brain";
          const isComplete = completed.has(habit.id);
          const Icon = habit.Icon;
          return (
            <article className="habit" key={habit.id}>
              <div className="habit-row">
                <button type="button" className={isComplete ? "complete-control is-complete" : "complete-control"} onClick={() => onToggle(habit.id)} aria-label={`Mark ${habit.name} ${isComplete ? "incomplete" : "complete"}`}>
                  {isComplete ? <CheckIcon width={18} height={18} /> : null}
                </button>
                <button type="button" className="habit-main" onClick={isBrainDump ? onBrainToggle : () => onToggle(habit.id)} aria-expanded={isBrainDump ? brainOpen : undefined}>
                  <Icon className="habit-icon" width={25} height={25} />
                  <span className="habit-copy"><strong>{habit.name}</strong><small>{habit.detail}</small></span>
                  <ChevronRightIcon className="row-chevron" width={23} height={23} />
                </button>
              </div>
            </article>
          );
        })}
      </section>

      <section className={addHabitOpen ? "add-habit is-expanded" : "add-habit"} aria-label="Add a habit">
        <button type="button" className="add-habit-trigger" onClick={onAddHabit} aria-expanded={addHabitOpen}>
          <span className="plus-orb"><PlusIcon width={24} height={24} /></span>
          <span><strong>Add habit</strong><small>{addHabitOpen ? "Choose how often it repeats" : "Make your protocol yours"}</small></span>
          <ChevronDownIcon className={addHabitOpen ? "row-chevron is-open" : "row-chevron"} width={23} height={23} />
        </button>
        {addHabitOpen ? <div className="frequency-group" role="group" aria-label="Habit frequency">
          {frequencies.map((option) => <button type="button" key={option} className={frequency === option ? "frequency is-selected" : "frequency"} onClick={() => onFrequency(option)} aria-pressed={frequency === option}>{option}</button>)}
        </div> : null}
      </section>
    </>
  );
}

function MorningCheckInOverlay({ onClose, onComplete, onViewData, transcript }: { onClose: () => void; onComplete: (transcript: string | null) => void; onViewData: () => void; transcript: string | null }) {
  return (
    <section className="morning-checkin-overlay" aria-label="Morning Check-in">
      <header className="checkin-header">
        <button type="button" className="close-checkin" onClick={onClose} aria-label="Close Morning Check-in">
          <Cross1Icon width={22} height={22} />
        </button>
        <p className="eyebrow"><span>Morning Check-in</span></p>
        {transcript === null ? (
          <>
            <h1>How's your health?</h1>
            <p>Externalizing thoughts reduces stress and clears working memory. Your voice is analyzed for wellness indicators, not diagnoses.</p>
          </>
        ) : (
          <h1>Your reflection</h1>
        )}
      </header>
      {transcript === null ? (
        <BrainDumpRecorder onComplete={onComplete} onViewData={onViewData} minimumSeconds={30} />
      ) : (
        <CheckInTranscript transcript={transcript} />
      )}
    </section>
  );
}

function CheckInTranscript({ transcript }: { transcript: string }) {
  return (
    <section className="brain-dump checkin-transcript" aria-label="Morning Check-in transcript">
      <div className="transcript-box">
        <p>{transcript.trim().length > 0 ? transcript : "No transcript was captured for this check-in."}</p>
      </div>
    </section>
  );
}

type ActivityStep = { id: number; text: string };

function BrainDumpRecorder({ onComplete, onViewData, minimumSeconds }: { onComplete: (transcript: string | null) => void; onViewData: () => void; minimumSeconds: number }) {
  const [recording, setRecording] = useState(false);
  const [paused, setPaused] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [steps, setSteps] = useState<ActivityStep[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<AudioWorkletNode | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const checkinIdRef = useRef<string | null>(null);
  const startedAtRef = useRef<number>(0);
  const recordedMsRef = useRef(0);
  const stepIdRef = useRef(0);
  const finishedRef = useRef(false);

  const apiBase = (import.meta.env.VITE_VOCAL_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
  const apiToken = import.meta.env.VITE_VOCAL_API_TOKEN ?? "development-token";

  useEffect(() => {
    if (!recording) return;

    const interval = window.setInterval(() => {
      setElapsed(Math.floor((recordedMsRef.current + Date.now() - startedAtRef.current) / 1000));
    }, 250);

    return () => window.clearInterval(interval);
  }, [recording]);

  useEffect(() => {
    return () => {
      socketRef.current?.close();
      processorRef.current?.disconnect();
      sourceRef.current?.disconnect();
      audioContextRef.current?.close();
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  function headers() {
    return { "Content-Type": "application/json", Authorization: `Bearer ${apiToken}` };
  }

  function addStep(text: string) {
    setSteps((current) => [...current, { id: stepIdRef.current++, text }]);
  }

  function truncate(text: string, max: number) {
    return text.length > max ? `${text.slice(0, max - 1)}…` : text;
  }

  // Called once the backend reports a terminal outcome for this check-in ("result", or a
  // processing_timeout it gave up waiting on) -- or by the safety-net timeout below if
  // neither message ever arrives. Closes the socket and fetches the saved check-in.
  async function finishRecording() {
    if (finishedRef.current) return;
    finishedRef.current = true;
    socketRef.current?.close();
    socketRef.current = null;
    const checkinId = checkinIdRef.current;
    if (!checkinId) {
      setProcessing(false);
      setError("Your recording could not be saved. Please try again.");
      return;
    }
    try {
      const finished = await fetch(`${apiBase}/v1/checkins/${checkinId}/finish`, { method: "POST", headers: headers() });
      if (!finished.ok) throw new Error("Could not save the recording.");
      const payload = await finished.json() as { transcript?: string | null };
      setProcessing(false);
      setSaved(true);
      onComplete(payload.transcript ?? null);
    } catch {
      setProcessing(false);
      setError("Your recording could not be saved. Please try again.");
    }
  }

  async function openStream(checkinId: string, ticket: string) {
    const streamUrl = new URL(`${apiBase}/v1/checkins/${checkinId}/stream`);
    streamUrl.protocol = streamUrl.protocol === "https:" ? "wss:" : "ws:";
    streamUrl.searchParams.set("ticket", ticket);
    const socket = new WebSocket(streamUrl);
    socket.binaryType = "arraybuffer";
    await new Promise<void>((resolve, reject) => {
      socket.onopen = () => resolve();
      socket.onerror = () => reject(new Error("Could not open the secure audio stream."));
    });
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data) as { type?: string; message?: string; text?: string; code?: string };
      switch (message.type) {
        case "processing":
          addStep("Analyzing your check-in…");
          break;
        case "analyzing":
          addStep("Scoring your voice…");
          break;
        case "transcribing":
          addStep("Transcribing what you said…");
          break;
        case "transcript":
          addStep(message.text ? `Heard: “${truncate(message.text, 70)}”` : "Transcript ready.");
          break;
        case "result":
          addStep("Saved to your trends.");
          void finishRecording();
          break;
        case "error":
          // processing_timeout is terminal but not fatal: the backend gave up waiting on
          // this connection, not on the check-in itself, which keeps completing in the
          // background. pulse_processing_failed/transcription_failed are per-step and
          // non-fatal too -- the backend still finishes and will send "result". Anything
          // else (e.g. invalid_pcm_frame, mid-recording) is a real, blocking problem.
          if (message.code === "processing_timeout") {
            addStep("Taking longer than expected — finishing in the background.");
            void finishRecording();
          } else if (message.code === "pulse_processing_failed" || message.code === "transcription_failed") {
            addStep(message.message ?? "One step had an issue, but your check-in is still being saved.");
          } else {
            setError(message.message ?? "Audio processing is unavailable right now.");
          }
          break;
        default:
          break;
      }
    };
    socketRef.current = socket;
    socket.send(JSON.stringify({ type: "checkin.start", sample_rate: 16000, encoding: "pcm_s16le" }));
    return socket;
  }

  function stopCapture() {
    processorRef.current?.disconnect();
    sourceRef.current?.disconnect();
    void audioContextRef.current?.close();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    processorRef.current = null;
    sourceRef.current = null;
    audioContextRef.current = null;
    streamRef.current = null;
  }

  async function startRecording() {
    setError(null);
    setSaved(false);

    if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode) {
      setError("Live audio recording is not available in this browser.");
      return;
    }

    try {
      const created = await fetch(`${apiBase}/v1/checkins`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ source: "morning-check-in" }),
      });
      if (!created.ok) throw new Error("Could not create a Morning Check-in.");
      const { checkin, stream_ticket: ticket } = await created.json() as { checkin: { checkin_id: string }; stream_ticket: string };
      const socket = await openStream(checkin.checkin_id, ticket);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const context = new AudioContext();
      await context.audioWorklet.addModule("/pcm-processor.js");
      const source = context.createMediaStreamSource(stream);
      const processor = new AudioWorkletNode(context, "pcm-processor", { processorOptions: { targetRate: 16000 } });
      processor.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
        if (socket.readyState === WebSocket.OPEN) socket.send(event.data);
      };
      source.connect(processor);
      processor.connect(context.destination);
      audioContextRef.current = context;
      sourceRef.current = source;
      processorRef.current = processor;
      checkinIdRef.current = checkin.checkin_id;
      startedAtRef.current = Date.now();
      recordedMsRef.current = 0;
      setElapsed(0);
      setRecording(true);
    } catch {
      stopCapture();
      socketRef.current?.close();
      setError("Microphone access and the private check-in service are needed to record.");
    }
  }

  function pauseRecording() {
    const context = audioContextRef.current;
    if (!context || !recording) return;
    recordedMsRef.current += Date.now() - startedAtRef.current;
    setElapsed(Math.floor(recordedMsRef.current / 1000));
    void context.suspend();
    socketRef.current?.send(JSON.stringify({ type: "checkin.pause" }));
    setRecording(false);
    setPaused(true);
  }

  function resumeRecording() {
    const context = audioContextRef.current;
    if (!context || !paused) return;
    startedAtRef.current = Date.now();
    void context.resume();
    socketRef.current?.send(JSON.stringify({ type: "checkin.resume" }));
    setPaused(false);
    setRecording(true);
  }

  function savePausedRecording() {
    if (!paused || elapsed < minimumSeconds || !checkinIdRef.current) return;
    finishedRef.current = false;
    setSteps([]);
    setProcessing(true);
    setPaused(false);
    socketRef.current?.send(JSON.stringify({ type: "checkin.end" }));
    stopCapture();
    // The backend now keeps this socket open until the check-in's Amplifier scoring and
    // transcription both actually finish -- real API calls, so this can take real
    // seconds, not the fixed 250ms this used to wait before force-closing and calling
    // /finish regardless of whether anything had actually completed. onmessage above
    // drives finishRecording() once a terminal event arrives; this is only the backstop
    // in case that message itself never does (e.g. a dropped connection).
    window.setTimeout(() => {
      if (finishedRef.current) return;
      addStep("Still working on it — check back shortly.");
      void finishRecording();
    }, 130_000);
  }

  const formattedTime = `${String(Math.floor(elapsed / 60)).padStart(2, "0")}:${String(elapsed % 60).padStart(2, "0")}`;

  if (processing) {
    return (
      <section className="brain-dump checkin-processing" aria-label="Saving your Morning Check-in">
        <div className="checkin-activity" aria-live="polite">
          <p className="checkin-activity-hd">Saving your check-in…</p>
          <ul className="checkin-activity-log">
            {steps.map((step) => <li key={step.id}>{step.text}</li>)}
          </ul>
        </div>
        {error ? <span className="recording-error" role="alert">{error}</span> : null}
      </section>
    );
  }

  if (saved) {
    return (
      <section className="brain-dump checkin-saved" aria-label="Morning Check-in saved">
        <p className="saved-confirmation" role="status" aria-live="polite">saved.</p>
        <div className="saved-actions" aria-label="Next steps">
          <button type="button" className="save-audio" onClick={onViewData}>View Data</button>
          <button type="button" className="stop-recording">Continue conversation in chat</button>
        </div>
      </section>
    );
  }

  return (
    <section className="brain-dump" aria-label="Morning Check-in voice reflection">
      <button type="button" className={recording ? "microphone is-listening" : paused ? "microphone is-paused" : "microphone"} onClick={recording ? pauseRecording : paused ? resumeRecording : startRecording} aria-pressed={recording} aria-label={recording ? "Pause Morning Check-in recording" : paused ? "Resume Morning Check-in recording" : "Start recording Morning Check-in"}>
        {recording ? <PauseIcon width={35} height={35} /> : paused ? <PlayIcon width={35} height={35} /> : <MicrophoneIcon size={35} weight="regular" />}
      </button>
      {recording || paused ? <strong className="recording-timer" aria-live="polite">{formattedTime}</strong> : null}
      <div className="checkin-checklist" aria-label="Morning Check-in guidance">
        <div><span className="checkin-checkmark"><CheckIcon width={14} height={14} /></span><span>Find a quiet space.</span></div>
        <div><span className="checkin-checkmark"><CheckIcon width={14} height={14} /></span><span>Talk for at least 30 seconds.</span></div>
        <div><span className="checkin-checkmark"><CheckIcon width={14} height={14} /></span><span>Tap the mic when you are ready.</span></div>
      </div>
      <footer className="checkin-footer">
        <p>Reminder set for 8:00 am · <span>Change</span></p>
      </footer>
      {error ? <span className="recording-error" role="alert">{error}</span> : null}
      <div className="recorder-actions">
        {paused ? <>
          <button type="button" className="stop-recording" onClick={resumeRecording}>Resume</button>
          <button type="button" className="save-audio" onClick={savePausedRecording} disabled={elapsed < minimumSeconds || saved}>Save</button>
        </> : null}
      </div>
    </section>
  );
}

type SignalPoint = {
  signal_name: string;
  recorded_at: string;
  score: number;
  level: string;
  flagged: boolean;
  latest_score: number | null;
  baseline_score: number | null;
  deviation_from_baseline: number | null;
  anomaly: boolean | null;
  z_score: number | null;
  population_z: number | null;
};

const SIGNAL_LABELS: Record<string, string> = {
  "mood-disruption": "Mood disruption",
  "anxiety": "Anxiety",
  "stress": "Stress",
  "fatigue": "Fatigue",
  "dehydration": "Dehydration",
  "elevated-blood-pressure": "Elevated blood pressure",
};

const SIGNAL_ORDER = ["mood-disruption", "anxiety", "stress", "fatigue", "dehydration", "elevated-blood-pressure"];

const LEVEL_ORDER = ["none", "low", "consider", "moderate"];
const LEVEL_RANK: Record<string, number> = Object.fromEntries(LEVEL_ORDER.map((level, index) => [level, index]));

function levelRank(level: string) {
  return LEVEL_RANK[level] ?? LEVEL_ORDER.length - 1;
}

function capitalizeLevel(level: string) {
  return level.length ? level[0].toUpperCase() + level.slice(1) : level;
}

function average(values: number[]) {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function trendDirection(ranks: number[]): "down" | "up" | "stable" {
  const span = Math.max(1, Math.floor(ranks.length / 3));
  const delta = average(ranks.slice(-span)) - average(ranks.slice(0, span));
  if (Math.abs(delta) < 0.4) return "stable";
  return delta < 0 ? "down" : "up";
}

function formatDay(recordedAt: string) {
  return new Date(recordedAt).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function TrendsScreen() {
  const [signals, setSignals] = useState<Record<string, SignalPoint[]> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const apiBase = (import.meta.env.VITE_VOCAL_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
    const apiToken = import.meta.env.VITE_VOCAL_API_TOKEN ?? "development-token";
    let cancelled = false;
    fetch(`${apiBase}/v1/signals`, { headers: { Authorization: `Bearer ${apiToken}` } })
      .then((response) => {
        if (!response.ok) throw new Error("Could not load trends.");
        return response.json() as Promise<{ items: SignalPoint[] }>;
      })
      .then(({ items }) => {
        if (cancelled) return;
        const grouped: Record<string, SignalPoint[]> = {};
        for (const item of items) {
          (grouped[item.signal_name] ??= []).push(item);
        }
        setSignals(grouped);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load your trends right now.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const names = signals ? SIGNAL_ORDER.filter((name) => signals[name]?.length) : [];

  return (
    <section className="trends-page" aria-label="Trends">
      <header className="today-header trends-header">
        <h1>Trends</h1>
      </header>

      {error ? <span className="recording-error" role="alert">{error}</span> : null}

      {signals && names.length === 0 && !error ? (
        <p className="trends-empty">No pulse data yet — complete a Morning Check-in to start your trends.</p>
      ) : null}

      <div className="trend-grid">
        {names.map((name) => <TrendCard key={name} label={SIGNAL_LABELS[name] ?? name} points={signals![name]} />)}
      </div>

      <button type="button" className="wearables-bubble">
        <PlusIcon width={13} height={13} />
        <span>Shop wearables for more data</span>
      </button>
    </section>
  );
}

function TrendCard({ label, points }: { label: string; points: SignalPoint[] }) {
  const ranks = points.map((point) => levelRank(point.level));
  const latest = points[points.length - 1];
  const direction = trendDirection(ranks);
  const arrow = direction === "down" ? "↓" : direction === "up" ? "↑" : "→";
  const directionWord = direction === "down" ? "declining" : direction === "up" ? "rising" : "steady";

  return (
    <article className="trend-card" aria-label={label}>
      <header className="trend-card-head">
        <div className="trend-card-title">
          <strong>{label}</strong>
          <small>{capitalizeLevel(latest.level)}</small>
        </div>
        <span className={`trend-direction trend-direction-${direction}`}>{arrow} {directionWord}</span>
      </header>
      <TrendChart points={points} ranks={ranks} />
      <div className="trend-axis">
        <span>{formatDay(points[0].recorded_at)}</span>
        <span>{formatDay(points[points.length - 1].recorded_at)}</span>
      </div>
    </article>
  );
}

const CHART_W = 280;
const CHART_H = 108;
const CHART_PAD_TOP = 10;
const CHART_PAD_BOTTOM = 10;
const CHART_PAD_LEFT = 58;
const CHART_PAD_RIGHT = 8;
const LEVEL_TOP_RANK = LEVEL_ORDER.length - 1;

function TrendChart({ points, ranks }: { points: SignalPoint[]; ranks: number[] }) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  function xAt(index: number) {
    return CHART_PAD_LEFT + (index / Math.max(1, ranks.length - 1)) * (CHART_W - CHART_PAD_LEFT - CHART_PAD_RIGHT);
  }
  function yAt(rank: number) {
    return CHART_PAD_TOP + ((LEVEL_TOP_RANK - rank) / LEVEL_TOP_RANK) * (CHART_H - CHART_PAD_TOP - CHART_PAD_BOTTOM);
  }

  const linePath = ranks.map((rank, index) => `${index === 0 ? "M" : "L"}${xAt(index).toFixed(1)},${yAt(rank).toFixed(1)}`).join(" ");
  const baseY = CHART_H - CHART_PAD_BOTTOM;
  const areaPath = `${linePath} L${xAt(ranks.length - 1).toFixed(1)},${baseY.toFixed(1)} L${xAt(0).toFixed(1)},${baseY.toFixed(1)} Z`;
  const lastIndex = ranks.length - 1;

  function updateHover(event: PointerEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const relativeX = ((event.clientX - rect.left) / rect.width) * CHART_W;
    let nearest = 0;
    let nearestDistance = Infinity;
    ranks.forEach((_, index) => {
      const distance = Math.abs(xAt(index) - relativeX);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearest = index;
      }
    });
    setHoverIndex(nearest);
  }

  const activeIndex = hoverIndex ?? lastIndex;
  const tooltipWidth = 76;
  const tooltipX = Math.min(CHART_W - tooltipWidth - 2, Math.max(2, xAt(activeIndex) - tooltipWidth / 2));

  return (
    <svg
      className="trend-chart"
      viewBox={`0 0 ${CHART_W} ${CHART_H}`}
      role="img"
      aria-label={`Trend line, ${ranks.length} readings, by level`}
      onPointerMove={updateHover}
      onPointerDown={updateHover}
      onPointerLeave={() => setHoverIndex(null)}
    >
      {LEVEL_ORDER.map((level, rank) => (
        <g key={level}>
          <line className="trend-gridline" x1={CHART_PAD_LEFT} x2={CHART_W - CHART_PAD_RIGHT} y1={yAt(rank)} y2={yAt(rank)} />
          <text className="trend-gridline-label" x={CHART_PAD_LEFT - 8} y={yAt(rank) + 3}>{capitalizeLevel(level)}</text>
        </g>
      ))}
      <path className="trend-area" d={areaPath} />
      <path className="trend-line" d={linePath} />
      <circle className="trend-marker" cx={xAt(lastIndex)} cy={yAt(ranks[lastIndex])} r={4} />
      {hoverIndex !== null ? (
        <>
          <line className="trend-crosshair" x1={xAt(hoverIndex)} x2={xAt(hoverIndex)} y1={CHART_PAD_TOP} y2={baseY} />
          <circle className="trend-hover-marker" cx={xAt(hoverIndex)} cy={yAt(ranks[hoverIndex])} r={4} />
          <g transform={`translate(${tooltipX}, 0)`}>
            <rect className="trend-tooltip-bg" width={tooltipWidth} height={16} rx={5} />
            <text className="trend-tooltip-text" x={tooltipWidth / 2} y={11}>
              {formatDay(points[hoverIndex].recorded_at)} · {capitalizeLevel(points[hoverIndex].level)}
            </text>
          </g>
        </>
      ) : null}
    </svg>
  );
}
