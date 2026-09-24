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
  const [conversationTranscript, setConversationTranscript] = useState<string | null>(null);
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
        <main className="screen-content" aria-label="Today">
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
        </main>
      </MobileScroll>

      {tab === "today" && brainOpen ? (
        <MorningCheckInOverlay
          onClose={() => {
            setBrainOpen(false);
            setConversationTranscript(null);
          }}
          onComplete={completeBrainDump}
          onViewData={() => {
            setBrainOpen(false);
            setConversationTranscript(null);
          }}
          transcript={brainTranscript}
          conversationTranscript={conversationTranscript}
          onConversationReady={setConversationTranscript}
        />
      ) : null}

      <nav className="bottom-nav" aria-label="Primary navigation">
        <button type="button" className={tab === "today" ? "nav-item is-active" : "nav-item"} onClick={() => setTab("today")} aria-current={tab === "today" ? "page" : undefined}>
          <SunIcon width={24} height={24} />
          <span>Today</span>
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

function MorningCheckInOverlay({ onClose, onComplete, onViewData, transcript, conversationTranscript, onConversationReady }: { onClose: () => void; onComplete: (transcript: string | null) => void; onViewData: () => void; transcript: string | null; conversationTranscript: string | null; onConversationReady: (transcript: string) => void }) {
  return (
    <section className="morning-checkin-overlay" aria-label="Morning Check-in">
      <header className="checkin-header">
        <button type="button" className="close-checkin" onClick={onClose} aria-label="Close Morning Check-in">
          <Cross1Icon width={22} height={22} />
        </button>
        <p className="eyebrow"><span>Morning Check-in</span></p>
        {conversationTranscript !== null ? (
          <h1>Coach</h1>
        ) : transcript === null ? (
          <>
            <h1>1 Minute Brain Dump</h1>
            <p>Externalizing thoughts reduces stress and clears working memory. Your voice is analyzed for wellness indicators, not diagnoses.</p>
          </>
        ) : (
          <h1>Your reflection</h1>
        )}
      </header>
      {conversationTranscript !== null ? (
        <ConversationScreen transcript={conversationTranscript} />
      ) : transcript === null ? (
        <BrainDumpRecorder onComplete={onComplete} onViewData={onViewData} />
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

type CoachMessage = { id: string; role: ConversationRole; text: string };

function ConversationScreen({ transcript }: { transcript: string }) {
  const reflection = transcript.trim() || "No transcript was captured for this check-in.";
  const [messages, setMessages] = useState<CoachMessage[]>([{ id: "reflection", role: "user", text: reflection }]);
  const [draft, setDraft] = useState("");
  const [waiting, setWaiting] = useState(true);
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    publishLiveTrace("result", "Conversation started", "The saved transcript was sent to the prototype coach.");
    publishConversationMessage("user", reflection);
    const timer = window.setTimeout(() => {
      const reply = initialCoachReply();
      setMessages((current) => [...current, { id: "initial-coach", role: "agent", text: reply }]);
      setWaiting(false);
      publishConversationMessage("agent", reply);
    }, 650);
    return () => window.clearTimeout(timer);
  }, [reflection]);

  function sendMessage() {
    const text = draft.trim();
    if (!text || waiting) return;
    const userMessage = { id: `user-${Date.now()}`, role: "user" as const, text };
    setMessages((current) => [...current, userMessage]);
    setDraft("");
    setWaiting(true);
    publishConversationMessage("user", text);
    window.setTimeout(() => {
      const reply = "I’m here with you. Would you like to focus on a small habit, a clinic visit, or a plan for the week?";
      setMessages((current) => [...current, { id: `agent-${Date.now()}`, role: "agent", text: reply }]);
      setWaiting(false);
      publishConversationMessage("agent", reply);
    }, 650);
  }

  return (
    <section className="conversation-screen" aria-label="Conversation with your coach">
      <div className="conversation-messages">
        {messages.map((message) => <p key={message.id} className={message.role === "agent" ? "coach-bubble" : "member-bubble"}>{message.text}</p>)}
        {waiting ? <p className="coach-typing" aria-live="polite">Coach is thinking<span>···</span></p> : null}
      </div>
      <form className="coach-composer" onSubmit={(event) => { event.preventDefault(); sendMessage(); }}>
        <input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Reply to your coach…" aria-label="Reply to your coach" />
        <button type="submit" disabled={!draft.trim() || waiting}>Send</button>
      </form>
    </section>
  );
}

type SignalResult = { name: string; level: string };
type TraceKind = "request" | "stream" | "audio" | "model" | "result" | "error";
type ConversationRole = "user" | "agent";

function publishLiveTrace(kind: TraceKind, title: string, detail: string, signals?: SignalResult[]) {
  if (window.parent === window) return;
  window.parent.postMessage({
    source: "vocal-biomarkers-member-app",
    kind,
    title,
    detail,
    signals,
    at: new Date().toISOString(),
  }, window.location.origin);
}

function publishConversationMessage(role: ConversationRole, text: string) {
  if (window.parent === window) return;
  window.parent.postMessage({
    source: "vocal-biomarkers-member-app",
    type: "conversation",
    role,
    text,
    at: new Date().toISOString(),
  }, window.location.origin);
}

function initialCoachReply() {
  return "Thanks for sharing that. It sounds like you have a lot on your plate. Would you like to choose one small support for the week?";
}

type DemoEvent =
  | { kind: "agent"; text: string }
  | { kind: "user_audio"; audio: string; text: string }
  | { kind: "pulse_call"; chunk: number; window: string; jobId: string; signals: SignalResult[] }
  | { kind: "reasoning"; lines: string[] }
  | { kind: "tool"; call: string }
  | { kind: "saved" };

const PULSE_GROUP_ID = "user-1024";
const PULSE_ENDPOINT = `/v2/models/pulse/groups/${PULSE_GROUP_ID}/analyze/longitudinal`;

// Every line here is exactly what public/demo/user-*.wav actually says -- generated from
// this same text -- so what's shown on screen and what's playing never drift apart.
const DEMO_SCRIPT: DemoEvent[] = [
  {
    kind: "reasoning", lines: [
      "Load user habit logs. Load Morning-check in history."
    ]
  },
  { kind: "agent", text: "How are you feeling today?" },
  { kind: "user_audio", audio: "/demo/user-1.wav", text: "I'm having a good morning, but I have a lot of work coming up this week. My boss is out of office so I have been taking on a lot more work. My kids are on summer session so I have to shuttle them around to their activities and watch them during the days. I tripped over some toys yesterday and got really angry which I feel bad about. I have been listening to some good health podcasts, but not sure what is actually useful because there is so much information. I've been sticking to a good morning routine, but I haven't been able to make it to the gym because my back is hurting and I've been ordering in food all week." },
  // Mirrors the real overlapping-window bucketer: a partial read at the first hop (0-15s),
  // then a fuller, more confident read once the whole clip has landed (0-30s).
  {
    kind: "pulse_call", chunk: 0, window: "0:00–0:15", jobId: "pulse-4f2a1c9e", signals: [
      { name: "mood-disruption", level: "low" },
      { name: "anxiety", level: "consider" },
      { name: "stress", level: "consider" },
      { name: "fatigue", level: "none" },
      { name: "elevated-blood-pressure", level: "none" },
      { name: "dehydration", level: "none" },
    ]
  },
  {
    kind: "pulse_call", chunk: 1, window: "0:00–0:30", jobId: "pulse-9b7d3e12", signals: [
      { name: "mood-disruption", level: "low" },
      { name: "anxiety", level: "moderate" },
      { name: "stress", level: "moderate" },
      { name: "fatigue", level: "low" },
      { name: "elevated-blood-pressure", level: "consider" },
      { name: "dehydration", level: "low" },
    ]
  },
  { kind: "saved" },
  {
    kind: "reasoning", lines: [
      "No audio issues detected and personal baseline weight > 0.7 so baseline has been established.",
      "Parsing the check-in transcript for stress and mood language.",
      "Anxiety and stress are reading slightly elevated against her personal baseline this morning. This aligns with user reported condition.",
      "Elevated-blood-pressure has been trending up for the last 3 days — not a large enough change from baseline to flag to user.",
      "Dehydration and fatigue are both trending down compared to recent check-ins",
    ]
  },
  { kind: "agent", text: "Sorry about all the work and the back pain! I can hear that you are a bit more stressed than your usual, which fits what you are describing. Have you tried an at-home meditation? I can add one to your profile." },
  { kind: "user_audio", audio: "/demo/user-2.wav", text: "Sure." },
  { kind: "tool", call: "add-protocol { name: \"at-home meditation\", frequency: \"daily\", reason: \"anxiety and stress elevated vs. baseline\" }" },
  { kind: "agent", text: "Yes, and how have you been enjoying the new supplements you are taking?" },
  {
    kind: "reasoning", lines: [
      "GET /v2/groups/user-1024/longitudinal?from=2026-07-15&to=2026-09-23 — pulling Maya's trajectory for context.",
      "Reading trajectory since starting new supplements.",
    ]
  },
  { kind: "user_audio", audio: "/demo/user-3.wav", text: "I've only been on them for a week so I do not really know if they are working, and they're super expensive." },
  { kind: "agent", text: "That's fair — a week isn't long. I have noticed your hydration and energy readings trending up over this same week, though it's too early to say that's the supplement at work rather than anything else going on. Worth watching as you keep going." },
  { kind: "user_audio", audio: "/demo/user-4.wav", text: "That's pretty cool actually, but I do not feel like it." },
  { kind: "agent", text: "Mood tends to shift more slowly than hydration or energy, and I don't have enough data yet to say if or when this one will move for you. Diet plays a role too — want to chat about meal planning?" },
  { kind: "user_audio", audio: "/demo/user-5.wav", text: "Yes, I have been eating a lot of fast casual because of work. What are some quick meals I can make?" },
  {
    kind: "reasoning", lines: [
      "Suggesting meal plans tailored to elevated blood pressure without surfacing blood pressure issues to user.",
    ]
  },
  { kind: "tool", call: "suggest-meal-plan { style: \"low-sodium, fast\", target: \"manage blood pressure\" }" },
  { kind: "agent", text: "I've added a meal protocol to your profile. Be sure to log your daily activities there!" },
  { kind: "saved" },
];

type DemoMessage = { id: string; role: "agent" | "user"; text: string };

// Tapping the mic on the Brain Dump page plays this scripted check-in straight
// through -- agent and user turns show live as chat bubbles (the same
// treatment as the real Coach chat), while the reasoning and tool-call steps
// behind them are never rendered here. Those two go out solely through
// publishLiveTrace, for the external trace panel (presentation.html) to
// render; publishConversationMessage carries the same agent/user turns shown
// on screen out to that panel too, so both views stay in sync.
function BrainDumpRecorder({ onComplete, onViewData }: { onComplete: (transcript: string | null) => void; onViewData: () => void }) {
  const [phase, setPhase] = useState<"idle" | "playing" | "done">("idle");
  const [messages, setMessages] = useState<DemoMessage[]>([]);
  const [listening, setListening] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const idRef = useRef(0);
  const cancelledRef = useRef(false);
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    return () => {
      cancelledRef.current = true;
      audioRef.current?.pause();
    };
  }, []);

  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [messages, listening]);

  function wait(ms: number) {
    return new Promise<void>((resolve) => window.setTimeout(resolve, ms));
  }

  function addMessage(role: DemoMessage["role"], text: string) {
    setMessages((current) => [...current, { id: `demo-${idRef.current++}`, role, text }]);
  }

  // Plays a clip while revealing its known text word-by-word, paced to that clip's
  // real duration (not a fixed rate) -- the same illusion clinical_agent's replay
  // uses (precomputed text revealed on a timer instead of running live Whisper),
  // just driven by <audio>'s own loadedmetadata/duration rather than a fixed pace.
  function playWithLiveTranscript(src: string, text: string, onPartial: (partial: string) => void) {
    return new Promise<void>((resolve) => {
      const audio = audioRef.current;
      if (!audio) {
        onPartial(text);
        resolve();
        return;
      }
      const words = text.split(" ");
      let wordTimer: number | null = null;
      let settled = false;
      function finish() {
        if (settled) return;
        settled = true;
        if (wordTimer !== null) window.clearInterval(wordTimer);
        onPartial(text);
        resolve();
      }
      audio.onended = finish;
      audio.onerror = finish;
      audio.onloadedmetadata = () => {
        const durationMs = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration * 1000 : words.length * 260;
        const perWord = Math.max(70, durationMs / words.length);
        let revealed = 0;
        wordTimer = window.setInterval(() => {
          revealed += 1;
          const done = revealed >= words.length;
          onPartial(done ? words.join(" ") : `${words.slice(0, revealed).join(" ")} ▍`);
          if (done && wordTimer !== null) {
            window.clearInterval(wordTimer);
            wordTimer = null;
          }
        }, perWord);
        void audio.play().catch(finish);
      };
      audio.src = src;
      audio.load();
    });
  }

  async function run() {
    cancelledRef.current = false;
    setMessages([]);
    setListening(false);
    setPhase("playing");
    publishLiveTrace("result", "Check-in started", "Recording a Morning Check-in and coach conversation.");
    await wait(900);
    for (const event of DEMO_SCRIPT) {
      if (cancelledRef.current) return;
      if (event.kind === "agent") {
        setListening(false);
        addMessage("agent", event.text);
        publishConversationMessage("agent", event.text);
        await wait(2600);
      } else if (event.kind === "user_audio") {
        setListening(true);
        const liveId = `demo-${idRef.current++}`;
        let revealedAny = false;
        setMessages((current) => [...current, { id: liveId, role: "user", text: "" }]);
        await playWithLiveTranscript(event.audio, event.text, (partial) => {
          if (!revealedAny && partial.trim().length > 0) {
            revealedAny = true;
            setListening(false);
          }
          setMessages((current) => current.map((message) => (message.id === liveId ? { ...message, text: partial } : message)));
        });
        if (cancelledRef.current) return;
        setListening(false);
        publishConversationMessage("user", event.text);
        await wait(1600);
      } else if (event.kind === "pulse_call") {
        // The actual outgoing request, not a description of one -- same endpoint,
        // same job-id/result shape the real overlapping-window bucketer produces.
        publishLiveTrace("model", "Pulse analysis", `chunk ${event.chunk} (${event.window}) → POST ${PULSE_ENDPOINT} → job ${event.jobId}`);
        await wait(1700);
        publishLiveTrace("model", "Pulse analysis", `chunk ${event.chunk} → job ${event.jobId} returned — No audio issues:`, event.signals);
        await wait(2600);
      } else if (event.kind === "reasoning") {
        // Reasoning never reaches `messages` -- trace-only, by design.
        for (const line of event.lines) {
          if (cancelledRef.current) return;
          publishLiveTrace("model", "Agent reasoning", line);
          await wait(1700);
        }
        await wait(1000);
      } else if (event.kind === "tool") {
        // Tool calls never reach `messages` either -- trace-only.
        publishLiveTrace("request", "Tool call", event.call);
        await wait(2000);
      } else if (event.kind === "saved") {
        publishLiveTrace("result", "Check-in saved", "The check-in was saved and scored.");
        await wait(1600);
      }
    }
    if (cancelledRef.current) return;
    setPhase("done");
    onComplete(null);
  }

  if (phase === "done") {
    return (
      <section className="brain-dump checkin-saved" aria-label="Morning Check-in saved">
        <p className="saved-confirmation" role="status" aria-live="polite">saved.</p>
        <div className="saved-actions" aria-label="Next steps">
          <button type="button" className="save-audio" onClick={onViewData}>View Data</button>
          <button type="button" className="stop-recording" onClick={() => void run()}>Play again</button>
        </div>
      </section>
    );
  }

  if (phase === "playing") {
    return (
      <section className="conversation-screen" aria-label="Morning Check-in conversation">
        <audio ref={audioRef} hidden />
        <div className="conversation-messages" ref={listRef}>
          {messages.map((message) => (
            <p key={message.id} className={message.role === "agent" ? "coach-bubble" : "member-bubble"}>{message.text}</p>
          ))}
          {listening ? <p className="coach-typing" aria-live="polite">Listening<span>···</span></p> : null}
        </div>
      </section>
    );
  }

  return (
    <section className="brain-dump" aria-label="Morning Check-in voice reflection">
      <button type="button" className="microphone" onClick={() => void run()} aria-label="Start Morning Check-in">
        <MicrophoneIcon size={35} weight="regular" />
      </button>
      <div className="checkin-checklist" aria-label="Morning Check-in guidance">
        <div><span className="checkin-checkmark"><CheckIcon width={14} height={14} /></span><span>Find a quiet space.</span></div>
        <div><span className="checkin-checkmark"><CheckIcon width={14} height={14} /></span><span>Talk for at least 30 seconds.</span></div>
        <div><span className="checkin-checkmark"><CheckIcon width={14} height={14} /></span><span>Tap the mic when you are ready.</span></div>
      </div>
      <footer className="checkin-footer">
        <p>Reminder set for 8:00 am · <span>Change</span></p>
      </footer>
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
