import { useEffect, useRef, useState } from "react";
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

  function completeBrainDump() {
    setCompleted((current) => new Set(current).add("brain"));
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

function MorningCheckInOverlay({ onClose, onComplete }: { onClose: () => void; onComplete: () => void }) {
  return (
    <section className="morning-checkin-overlay" aria-label="Morning Check-in">
      <header className="checkin-header">
        <button type="button" className="close-checkin" onClick={onClose} aria-label="Close Morning Check-in">
          <Cross1Icon width={22} height={22} />
        </button>
        <p className="eyebrow"><span>Morning Check-in</span></p>
        <h1>What’s on your mind?</h1>
        <p>Externalizing thoughts reduces stress and clears working memory.</p>
      </header>
      <BrainDumpRecorder onComplete={onComplete} minimumSeconds={60} />
    </section>
  );
}

function BrainDumpRecorder({ onComplete, minimumSeconds }: { onComplete: () => void; minimumSeconds: number }) {
  const [recording, setRecording] = useState(false);
  const [paused, setPaused] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<AudioWorkletNode | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const checkinIdRef = useRef<string | null>(null);
  const startedAtRef = useRef<number>(0);
  const recordedMsRef = useRef(0);

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
      const message = JSON.parse(event.data) as { type?: string; message?: string };
      if (message.type === "error") setError(message.message ?? "Audio processing is unavailable right now.");
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
      const { checkin, stream_ticket: ticket } = await created.json() as { checkin: { id: string }; stream_ticket: string };
      const socket = await openStream(checkin.id, ticket);
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
      checkinIdRef.current = checkin.id;
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

  async function savePausedRecording() {
    if (!paused || elapsed < minimumSeconds || !checkinIdRef.current) return;
    const checkinId = checkinIdRef.current;
    socketRef.current?.send(JSON.stringify({ type: "checkin.end" }));
    await new Promise((resolve) => window.setTimeout(resolve, 250));
    socketRef.current?.close();
    socketRef.current = null;
    stopCapture();
    setPaused(false);
    try {
      const finished = await fetch(`${apiBase}/v1/checkins/${checkinId}/finish`, { method: "POST", headers: headers() });
      if (!finished.ok) throw new Error("Could not save the recording.");
      setSaved(true);
      onComplete();
    } catch {
      setError("Your recording could not be saved. Please try again.");
    }
  }

  const formattedTime = `${String(Math.floor(elapsed / 60)).padStart(2, "0")}:${String(elapsed % 60).padStart(2, "0")}`;

  return (
    <section className="brain-dump" aria-label="Morning Check-in voice reflection">
      <button type="button" className={recording ? "microphone is-listening" : paused ? "microphone is-paused" : "microphone"} onClick={recording ? pauseRecording : paused ? resumeRecording : startRecording} aria-pressed={recording} aria-label={recording ? "Pause Morning Check-in recording" : paused ? "Resume Morning Check-in recording" : "Start recording Morning Check-in"}>
        {recording ? <PauseIcon width={35} height={35} /> : paused ? <PlayIcon width={35} height={35} /> : <MicrophoneIcon size={35} weight="regular" />}
      </button>
      {recording || paused ? <strong className="recording-timer" aria-live="polite">{formattedTime}</strong> : null}
      <div className="checkin-checklist" aria-label="Morning Check-in guidance">
        <div><span className="checkin-checkmark"><CheckIcon width={14} height={14} /></span><span>Find a quiet space.</span></div>
        <div><span className="checkin-checkmark"><CheckIcon width={14} height={14} /></span><span>Talk for at least 1 minute.</span></div>
        <div><span className="checkin-checkmark"><CheckIcon width={14} height={14} /></span><span>Tap the mic when you are ready.</span></div>
      </div>
      <footer className="checkin-footer">
        <p>Reminder set for 8:00 am · <span>Change</span></p>
        <p>Your voice is analyzed for wellness indicators, not diagnoses. <span>How recordings are stored</span></p>
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

function TrendsScreen() {
  return (
    <section className="trends-page" aria-label="Trends">
      <header className="today-header trends-header">
        <h1>Trends</h1>
      </header>
    </section>
  );
}
