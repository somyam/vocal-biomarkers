import { useEffect, useRef, useState, type PointerEvent } from "react";
import { MicrophoneIcon } from "@phosphor-icons/react";
import {
  ActivityLogIcon,
  BarChartIcon,
  CheckIcon,
  Cross1Icon,
  ChevronLeftIcon,
  CalendarIcon,
  MinusIcon,
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
import { BottomSheet, KeyboardInput, MobileScroll, useKeyboard, useKeyboardInsets } from "./mobile";

// `?live=1` (e.g. /?member=1&live=1) switches the Morning Check-in to the real
// mic + WebSocket + backend flow instead of the scripted presentation demo.
// Default (no param) stays the scripted demo untouched.
function isLiveMode() {
  return typeof window !== "undefined" && new URLSearchParams(window.location.search).has("live");
}

type Tab = "today" | "trends";
type Frequency = "Daily" | "Weekly" | "Custom" | "Once";

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

const frequencies: Frequency[] = ["Daily", "Weekly", "Custom", "Once"];

export default function Prototype() {
  const [tab, setTab] = useState<Tab>("today");
  const [completed, setCompleted] = useState<Set<string>>(() => new Set());
  const [brainOpen, setBrainOpen] = useState(false);
  const [savedCheckinId, setSavedCheckinId] = useState<string | null>(null);
  const [brainTranscript, setBrainTranscript] = useState<string | null>(null);
  const [conversationTranscript, setConversationTranscript] = useState<string | null>(null);
  const [addHabitOpen, setAddHabitOpen] = useState(false);
  const [customHabits, setCustomHabits] = useState<ScheduledHabit[]>(loadHabits);
  const [today, setToday] = useState(() => localDate());
  const [habitNotice, setHabitNotice] = useState("");
  const keyboard = useKeyboard();

  useEffect(() => {
    const update = () => setToday(localDate());
    const timer = window.setInterval(update, 60_000);
    window.addEventListener("focus", update);
    return () => { window.clearInterval(timer); window.removeEventListener("focus", update); };
  }, []);
  useEffect(() => { setCompleted(new Set()); }, [today]);

  function addHabit(habit: ScheduledHabit): string | null {
    const next = [...customHabits, habit];
    try { window.localStorage.setItem(HABITS_STORAGE_KEY, JSON.stringify(next)); }
    catch { return "This browser could not save your habit. Please try again."; }
    setCustomHabits(next);
    setHabitNotice(`${habit.name} added. ${scheduleSummary(habit.schedule)}`);
    keyboard.hide();
    setAddHabitOpen(false);
    return null;
  }

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
            today={today}
            customHabits={customHabits}
            habitNotice={habitNotice}
            addHabitOpen={addHabitOpen}
            onToggle={toggleHabit}
            onBrainToggle={() => setBrainOpen((value) => !value)}
            onAddHabit={() => { keyboard.hide(); setHabitNotice(""); setAddHabitOpen(true); }}
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
          savedCheckinId={savedCheckinId}
          onSaved={setSavedCheckinId}
          onViewData={() => {
            setBrainOpen(false);
            setConversationTranscript(null);
          }}
          transcript={brainTranscript}
          conversationTranscript={conversationTranscript}
          onConversationReady={setConversationTranscript}
          live={isLiveMode()}
        />
      ) : null}

      <HabitSheet open={addHabitOpen} onClose={() => { keyboard.hide(); setAddHabitOpen(false); }} onAdd={addHabit} today={today} />

      <nav className="bottom-nav" aria-label="Primary navigation">
        <button type="button" className={tab === "today" ? "nav-item is-active" : "nav-item"} onClick={() => setTab("today")} aria-current={tab === "today" ? "page" : undefined}>
          <SunIcon width={24} height={24} />
          <span>Today</span>
        </button>
      </nav>
    </div>
  );
}

function TodayScreen({ completed, brainOpen, today, customHabits, habitNotice, addHabitOpen, onToggle, onBrainToggle, onAddHabit }: {
  completed: Set<string>;
  brainOpen: boolean;
  today: string;
  customHabits: ScheduledHabit[];
  habitNotice: string;
  addHabitOpen: boolean;
  onToggle: (id: string) => void;
  onBrainToggle: () => void;
  onAddHabit: () => void;
}) {
  return (
    <>
      <header className="today-header">
        <p className="eyebrow"><span>{parseLocalDate(today).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" })}</span></p>
        <h1>Good morning, Maya</h1>
      </header>

      <section className="habit-list" aria-label="Daily habits">
        {[...habits, ...customHabits.filter((habit) => isHabitDue(habit.schedule, today)).map((habit) => ({
          id: habit.id, name: habit.name, detail: scheduleSummary(habit.schedule), Icon: CalendarIcon,
        }))].map((habit) => {
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

      <div className="add-habit-area">
        <p className="habit-notice" role="status">{habitNotice}</p>
        <button type="button" className="add-habit-trigger" onClick={onAddHabit} aria-expanded={addHabitOpen} aria-haspopup="dialog">
          <PlusIcon width={22} height={22} aria-hidden="true" />
          <span>Add habit</span>
        </button>
      </div>
    </>
  );
}

type HabitSchedule = {
  frequency: Frequency;
  customMode: "rule" | "dates";
  interval: number;
  unit: "days" | "weeks" | "months";
  weekdays: number[];
  start: string;
  end: string | null;
  dates: string[];
  once: string;
};
type ScheduledHabit = { id: string; name: string; schedule: HabitSchedule };
const HABITS_STORAGE_KEY = "vocal-biomarkers.habits.v1";
const weekdayNames = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const weekdayOrder = [1, 2, 3, 4, 5, 6, 0];

function localDate(date = new Date()): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
function parseLocalDate(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day, 12);
}
function displayDate(value: string): string {
  return parseLocalDate(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
function dayNumber(value: string): number {
  const date = parseLocalDate(value);
  return Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / 86_400_000;
}
function initialSchedule(today: string): HabitSchedule {
  return { frequency: "Daily", customMode: "rule", interval: 1, unit: "weeks",
    weekdays: [parseLocalDate(today).getDay()], start: today, end: null, dates: [], once: today };
}
function validDate(value: unknown): value is string {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && localDate(parseLocalDate(value)) === value;
}
function loadHabits(): ScheduledHabit[] {
  try {
    const stored: unknown = JSON.parse(window.localStorage.getItem(HABITS_STORAGE_KEY) || "[]");
    if (!Array.isArray(stored)) return [];
    return stored.filter((habit) => {
      const s = habit?.schedule;
      return typeof habit?.id === "string" && typeof habit?.name === "string" && habit.name.trim().length > 0 && habit.name.length <= 80 && s &&
        frequencies.includes(s.frequency) && ["rule", "dates"].includes(s.customMode) &&
        Number.isInteger(s.interval) && s.interval >= 1 && s.interval <= 99 && ["days", "weeks", "months"].includes(s.unit) &&
        Array.isArray(s.weekdays) && s.weekdays.every((day: unknown) => Number.isInteger(day) && Number(day) >= 0 && Number(day) <= 6) &&
        validDate(s.start) && validDate(s.once) && (s.end === null || (validDate(s.end) && s.end >= s.start)) &&
        Array.isArray(s.dates) && s.dates.every(validDate);
    });
  } catch { return []; }
}

export function isHabitDue(schedule: HabitSchedule, date: string): boolean {
  if (schedule.frequency === "Once") return date === schedule.once;
  if (schedule.frequency === "Custom" && schedule.customMode === "dates") return schedule.dates.includes(date);
  if (date < schedule.start || (schedule.end && date > schedule.end)) return false;
  if (schedule.frequency === "Daily") return true;
  const current = parseLocalDate(date), start = parseLocalDate(schedule.start);
  if (schedule.frequency === "Weekly") return schedule.weekdays.includes(current.getDay());
  if (schedule.unit === "days") return (dayNumber(date) - dayNumber(schedule.start)) % schedule.interval === 0;
  if (schedule.unit === "months") {
    const months = (current.getFullYear() - start.getFullYear()) * 12 + current.getMonth() - start.getMonth();
    return months % schedule.interval === 0 && current.getDate() === start.getDate();
  }
  const startMonday = dayNumber(schedule.start) - (start.getDay() + 6) % 7;
  const currentMonday = dayNumber(date) - (current.getDay() + 6) % 7;
  return ((currentMonday - startMonday) / 7) % schedule.interval === 0 && schedule.weekdays.includes(current.getDay());
}

function scheduleSummary(schedule: HabitSchedule): string {
  if (schedule.frequency === "Once") return `${displayDate(schedule.once)} · Does not repeat`;
  if (schedule.frequency === "Custom" && schedule.customMode === "dates") {
    return schedule.dates.length ? `${schedule.dates.length} ${schedule.dates.length === 1 ? "date" : "dates"} selected · ${[...schedule.dates].sort().map((date) => parseLocalDate(date).toLocaleDateString("en-US", { month: "short", day: "numeric" })).join(", ")}` : "Choose the dates you want.";
  }
  const days = weekdayOrder.filter((day) => schedule.weekdays.includes(day)).map((day) => weekdayNames[day].slice(0, 3)).join(", ");
  let summary = "Every day";
  if (schedule.frequency === "Weekly") summary = days ? `Every ${days}` : "Choose at least one weekday.";
  if (schedule.frequency === "Custom") {
    summary = `Every ${schedule.interval === 1 ? schedule.unit.slice(0, -1) : `${schedule.interval} ${schedule.unit}`}`;
    if (schedule.unit === "weeks") summary += days ? ` on ${days}` : " · Choose a weekday";
    if (schedule.unit === "months") summary += ` on day ${parseLocalDate(schedule.start).getDate()}`;
  }
  return `${summary}${schedule.end ? ` · Until ${displayDate(schedule.end)}` : ""}`;
}

function HabitCalendar({ selected, onSelect, minimum, initial, multiple = false }: {
  selected: string[]; onSelect: (date: string) => void; minimum: string; initial: string; multiple?: boolean;
}) {
  const [month, setMonth] = useState(() => { const date = parseLocalDate(initial); return new Date(date.getFullYear(), date.getMonth(), 1, 12); });
  const first = month.getDay();
  const count = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const monthName = month.toLocaleDateString("en-US", { month: "long", year: "numeric" });
  const previous = new Date(month.getFullYear(), month.getMonth(), 0, 12);
  return <section className="habit-calendar" aria-label={multiple ? "Choose calendar dates" : "Choose a calendar date"}>
    <div className="habit-calendar-header">
      <button type="button" aria-label="Previous month" disabled={localDate(previous) < minimum} onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1, 12))}><ChevronLeftIcon /></button>
      <strong aria-live="polite">{monthName}</strong>
      <button type="button" aria-label="Next month" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1, 12))}><ChevronRightIcon /></button>
    </div>
    <div className="habit-calendar-grid">
      {weekdayNames.map((day) => <span className="calendar-weekday" key={day} aria-label={day}>{day[0]}</span>)}
      {Array.from({ length: first }, (_, index) => <span key={`empty-${index}`} />)}
      {Array.from({ length: count }, (_, index) => {
        const date = localDate(new Date(month.getFullYear(), month.getMonth(), index + 1, 12));
        return <button key={date} type="button" aria-label={displayDate(date)} aria-pressed={selected.includes(date)} aria-current={date === localDate() ? "date" : undefined}
          disabled={date < minimum} className={selected.includes(date) ? "is-selected" : ""} onClick={() => onSelect(date)}>{index + 1}</button>;
      })}
    </div>
  </section>;
}

function HabitSheet({ open, onClose, onAdd, today }: { open: boolean; onClose: () => void; onAdd: (habit: ScheduledHabit) => string | null; today: string }) {
  // Keep the shared sheet mounted so its exit animation and focus management run.
  return <BottomSheet open={open} onOpenChange={(next) => { if (!next) onClose(); }} title="Add habit" description="Give your habit a name and choose when it happens." snap={0.9}>
    <HabitForm key={open ? "open" : "closed"} onClose={onClose} onAdd={onAdd} today={today} />
  </BottomSheet>;
}

function HabitForm({ onClose, onAdd, today }: { onClose: () => void; onAdd: (habit: ScheduledHabit) => string | null; today: string }) {
  const [name, setName] = useState("");
  const [schedule, setSchedule] = useState(() => initialSchedule(today));
  const [picker, setPicker] = useState<"start" | "end" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const keyboard = useKeyboard();
  const { isKeyboardVisible, bottomInset } = useKeyboardInsets();
  const customDates = schedule.frequency === "Custom" && schedule.customMode === "dates";
  const recurring = schedule.frequency !== "Once" && !customDates;
  const showWeekdays = schedule.frequency === "Weekly" || (schedule.frequency === "Custom" && !customDates && schedule.unit === "weeks");
  const valid = name.trim().length > 0 && (!showWeekdays || schedule.weekdays.length > 0) &&
    (!customDates || schedule.dates.length > 0) && (!recurring || !schedule.end || schedule.end >= schedule.start);
  function update(change: Partial<HabitSchedule>) { keyboard.hide(); setSchedule((current) => ({ ...current, ...change })); setError(null); }
  function submit() {
    if (!valid) return;
    keyboard.hide();
    setError(onAdd({ id: `habit-${crypto.randomUUID()}`, name: name.trim(), schedule }));
  }
  return <form className="habit-form" data-frequency={schedule.frequency} data-keyboard-open={isKeyboardVisible} onSubmit={(event) => { event.preventDefault(); submit(); }}>
    <button className="habit-sheet-close" type="button" aria-label="Close Add habit" onClick={onClose}><Cross1Icon width={22} height={22} /></button>
    <div className="habit-form-body">
      <MobileScroll className="habit-form-scroll">
        <div className="habit-field habit-name-field">
          <label htmlFor="new-habit-name">Habit name</label>
          <KeyboardInput id="new-habit-name" placeholder="e.g. Morning walk" value={name} maxLength={80} autoComplete="off" onBlur={(event) => { if (!event.currentTarget.form?.contains(event.relatedTarget as Node | null)) keyboard.hide(); }} onChange={(event) => { setName(event.target.value); setError(null); }} />
        </div>
        <div className="habit-field">
          <span className="habit-field-label" id="habit-repeat-label">Repeat</span>
          <div className="habit-repeat-options" role="group" aria-labelledby="habit-repeat-label">
            {frequencies.map((frequency) => <button type="button" key={frequency} aria-pressed={schedule.frequency === frequency} onClick={() => { update({ frequency }); setPicker(null); }}>{frequency}</button>)}
          </div>
        </div>
        {schedule.frequency === "Custom" && <div className="habit-custom-controls">
          <div className="habit-custom-tabs" role="group" aria-label="Custom schedule type">
            <button type="button" aria-pressed={!customDates} onClick={() => { update({ customMode: "rule" }); setPicker(null); }}>Repeat rule</button>
            <button type="button" aria-pressed={customDates} onClick={() => { update({ customMode: "dates" }); setPicker(null); }}>Choose dates</button>
          </div>
          {!customDates && <div className="habit-interval">
            <span>Every</span>
            <div className="habit-stepper">
              <button type="button" aria-label="Decrease repeat interval" disabled={schedule.interval <= 1} onClick={() => update({ interval: schedule.interval - 1 })}><MinusIcon /></button>
              <output aria-label="Repeat interval">{schedule.interval}</output>
              <button type="button" aria-label="Increase repeat interval" disabled={schedule.interval >= 99} onClick={() => update({ interval: schedule.interval + 1 })}><PlusIcon /></button>
            </div>
            <select aria-label="Repeat unit" value={schedule.unit} onChange={(event) => update({ unit: event.target.value as HabitSchedule["unit"] })}>
              <option value="days">days</option><option value="weeks">weeks</option><option value="months">months</option>
            </select>
          </div>}
        </div>}
        {showWeekdays && <div className="habit-field">
          <span className="habit-field-label" id="habit-days-label">{schedule.frequency === "Weekly" ? "Repeat on" : "On these days"}</span>
          <div className="habit-weekdays" role="group" aria-labelledby="habit-days-label">
            {weekdayOrder.map((day) => <button key={day} type="button" aria-label={weekdayNames[day]} aria-pressed={schedule.weekdays.includes(day)} onClick={() => update({ weekdays: schedule.weekdays.includes(day) ? schedule.weekdays.filter((value) => value !== day) : [...schedule.weekdays, day] })}>{weekdayNames[day][0]}</button>)}
          </div>
          {!schedule.weekdays.length && <p className="habit-validation">Choose at least one weekday.</p>}
        </div>}
        {(customDates || schedule.frequency === "Once") && <div className="habit-field habit-dates-field">
          <span className="habit-field-label">{customDates ? "Choose your dates" : "Choose a date"}</span>
          <HabitCalendar key={customDates ? "multiple" : "once"} selected={customDates ? schedule.dates : [schedule.once]} initial={customDates ? schedule.dates[0] || today : schedule.once} minimum={today} multiple={customDates}
            onSelect={(date) => update(customDates ? { dates: (schedule.dates.includes(date) ? schedule.dates.filter((value) => value !== date) : [...schedule.dates, date]).sort() } : { once: date })} />
        </div>}
        {recurring && <>
          <div className="habit-field">
            <span className="habit-field-label">Starts</span>
            <button className="habit-date-row" type="button" aria-label="Change start date" aria-expanded={picker === "start"} onClick={() => { keyboard.hide(); setPicker(picker === "start" ? null : "start"); }}><CalendarIcon width={22} height={22} /><span>{displayDate(schedule.start)}</span><ChevronRightIcon /></button>
            {picker === "start" && <HabitCalendar key="start" selected={[schedule.start]} initial={schedule.start} minimum={today} onSelect={(start) => { update({ start, ...(schedule.end && schedule.end < start ? { end: start } : {}) }); setPicker(null); }} />}
          </div>
          <div className="habit-field">
            <span className="habit-field-label">Ends</span>
            <button className="habit-date-row" type="button" aria-label="Change end date" aria-expanded={picker === "end"} onClick={() => { keyboard.hide(); setPicker(picker === "end" ? null : "end"); }}><span>{schedule.end ? displayDate(schedule.end) : "Never"}</span><ChevronRightIcon /></button>
            {picker === "end" && <>
              <div className="habit-end-options" role="group" aria-label="End schedule">
                <button type="button" aria-pressed={!schedule.end} onClick={() => { update({ end: null }); setPicker(null); }}>Never</button>
                <button type="button" aria-pressed={Boolean(schedule.end)} onClick={() => update({ end: schedule.end || schedule.start })}>On a date</button>
              </div>
              {schedule.end && <HabitCalendar key="end" selected={[schedule.end]} initial={schedule.end} minimum={schedule.start} onSelect={(end) => { update({ end }); setPicker(null); }} />}
            </>}
          </div>
          {schedule.frequency === "Custom" && schedule.unit === "months" && parseLocalDate(schedule.start).getDate() > 28 && <p className="habit-validation">Months without day {parseLocalDate(schedule.start).getDate()} are skipped.</p>}
        </>}
        <div className="habit-summary"><span className="habit-field-label">Summary</span><p aria-live="polite">{scheduleSummary(schedule)}</p></div>
      </MobileScroll>
    </div>
    <div className="habit-form-footer" style={{ paddingBottom: (isKeyboardVisible ? 0 : bottomInset) + 14 }}>
      {error && <p className="habit-validation" role="alert">{error}</p>}
      <button className="habit-save" type="submit" disabled={!valid}>Add habit</button>
    </div>
  </form>;
}

function MorningCheckInOverlay({ savedCheckinId, onSaved, onClose, onComplete, onViewData, transcript, conversationTranscript, onConversationReady, live }: { savedCheckinId: string | null; onSaved: (id: string) => void; onClose: () => void; onComplete: (transcript: string | null) => void; onViewData: () => void; transcript: string | null; conversationTranscript: string | null; onConversationReady: (transcript: string) => void; live: boolean }) {
  const keyboard = useKeyboard();
  const { bottomInset } = useKeyboardInsets();
  return (
    <section className="morning-checkin-overlay" aria-label="Morning Check-in" style={live && savedCheckinId ? { paddingBottom: bottomInset + 12 } : undefined}>
      <header className="checkin-header">
        <button type="button" className="close-checkin" onClick={() => { keyboard.hide(); onClose(); }} aria-label="Close Morning Check-in">
          <Cross1Icon width={22} height={22} />
        </button>
        <p className="eyebrow"><span>Morning Check-in</span></p>
        {live && savedCheckinId ? (
          <h1>Your conversation</h1>
        ) : conversationTranscript !== null ? (
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
      {live && savedCheckinId ? (
        <SavedConversation checkinId={savedCheckinId} />
      ) : conversationTranscript !== null ? (
        <ConversationScreen transcript={conversationTranscript} />
      ) : transcript === null ? (
        live ? (
          <LiveBrainDumpRecorder onSaved={onSaved} onComplete={onComplete} onViewData={onViewData} onConversationReady={onConversationReady} minimumSeconds={30} />
        ) : (
          <BrainDumpRecorder onComplete={onComplete} onViewData={onViewData} />
        )
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

type SavedMessage = { id: string; role: "user" | "assistant"; text: string; status: string; error?: string | null; request_id?: string };
type SavedCheckin = { checkin_id: string; completed_at: string | null; recording_completed_at: string | null; analysis_status: "pending" | "complete" | "failed" | "delayed"; conversation_messages: SavedMessage[] };
const liveApiBase = (import.meta.env.VITE_VOCAL_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
function liveHeaders() {
  return { "Content-Type": "application/json", Authorization: `Bearer ${import.meta.env.VITE_VOCAL_API_TOKEN ?? "development-token"}` };
}

function ConversationHistory({ messages, waiting = false }: { messages: SavedMessage[]; waiting?: boolean }) {
  const list = useRef<HTMLDivElement>(null);
  const contentKey = messages.map(message => `${message.id}:${message.text}`).join("|");
  useEffect(() => {
    const scroll = list.current?.querySelector<HTMLElement>(".mobile-scroll");
    if (scroll) scroll.scrollTop = scroll.scrollHeight;
  }, [contentKey, waiting]);
  return (
    <div className="saved-history" ref={list}>
      <MobileScroll className="conversation-messages">
        {messages.map(message => (
          <p key={message.id} className={message.role === "assistant" ? "coach-bubble" : "member-bubble"}>
            {message.text || (message.status === "transcription_failed" ? "This speech could not be transcribed. The audio recording is saved." : "No speech was transcribed.")}
          </p>
        ))}
        {waiting ? <p className="coach-typing" role="status">Coach is thinking…</p> : null}
      </MobileScroll>
    </div>
  );
}

function SavedConversation({ checkinId }: { checkinId: string }) {
  const [checkin, setCheckin] = useState<SavedCheckin | null>(null);
  const [draft, setDraft] = useState("");
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<{ request_id: string; text: string } | null>(null);
  const [reload, setReload] = useState(0);
  const busy = useRef(false);
  const mounted = useRef(true);
  const keyboard = useKeyboard();

  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const pendingRef = useRef(pending);
  const revision = useRef(0);
  pendingRef.current = pending;

  useEffect(() => {
    mounted.current = true;
    let cancelled = false;
    let failures = 0;
    let socket: WebSocket | undefined;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    function reconnect() {
      if (cancelled) return;
      setConnectionError("Updates disconnected. Reconnecting…");
      if (failures >= 5) {
        setConnectionError("Updates disconnected. Reconnect to get the latest conversation.");
        return;
      }
      timer = setTimeout(() => void connect(), Math.min(500 * 2 ** failures++, 8000));
    }
    async function connect() {
      try {
        const response = await fetch(`${liveApiBase}/v1/checkins/${checkinId}/events-ticket`, {
          method: "POST", headers: liveHeaders(), signal: controller.signal,
        });
        if (!response.ok) throw new Error("Cannot connect");
        const ticket = await response.json();
        if (cancelled) return;
        const url = new URL(ticket.events_path, liveApiBase);
        url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
        const current = new WebSocket(url.toString());
        socket = current;
        let sequence = -1;
        current.onmessage = event => {
          if (cancelled || socket !== current) return;
          const message = JSON.parse(event.data);
          if (message.type !== "checkin.snapshot" || message.sequence <= sequence) return;
          sequence = message.sequence;
          failures = 0;
          revision.current++;
          setConnectionError(null);
          const payload = message.checkin as SavedCheckin;
          const request = pendingRef.current;
          // Keep a just-sent message visible if a snapshot predates its DB insert.
          if (request && !payload.conversation_messages.some(item => item.request_id === request.request_id)) {
            payload.conversation_messages = [...payload.conversation_messages, {
              id: `${request.request_id}-user`, role: "user", text: request.text,
              status: "processing", request_id: request.request_id,
            }];
          }
          setCheckin(payload);
          const unfinished = payload.conversation_messages.find(item => item.request_id && item.status !== "done");
          const next = unfinished ? { request_id: unfinished.request_id!, text: unfinished.text } : null;
          pendingRef.current = next;
          setPending(next);
          setError(unfinished?.error ?? null);
          if (request && !unfinished) setDraft("");
        };
        current.onclose = () => { if (socket === current) reconnect(); };
        current.onerror = () => current.close();
      } catch {
        reconnect();
      }
    }
    void connect();
    return () => {
      cancelled = true;
      mounted.current = false;
      controller.abort();
      clearTimeout(timer);
      socket?.close();
    };
  }, [checkinId, reload]);

  async function checkAnalysis() {
    if (checking) return;
    setChecking(true);
    const version = revision.current;
    try {
      const response = await fetch(`${liveApiBase}/v1/checkins/${checkinId}/analysis/refresh`, { method: "POST", headers: liveHeaders() });
      if (!response.ok) throw new Error("Unable to check analysis.");
      const payload = await response.json();
      if (!mounted.current) return;
      if (version === revision.current) setCheckin(payload);
      setError(payload.analysis_refresh_errors ? "Some results could not be checked. You can try again." : null);
    } catch {
      if (mounted.current) setError("Unable to check analysis. You can try again.");
    } finally {
      if (mounted.current) setChecking(false);
    }
  }

  async function send() {
    if (busy.current || !checkin?.recording_completed_at) return;
    const request = pending ?? { request_id: crypto.randomUUID(), text: draft.trim() };
    if (!request.text) return;
    busy.current = true;
    setWaiting(true);
    pendingRef.current = request;
    setPending(request);
    const version = revision.current;
    setError(null);
    keyboard.hide();
    setCheckin(current => current ? { ...current, conversation_messages: current.conversation_messages.some(message => message.request_id === request.request_id)
      ? current.conversation_messages : [...current.conversation_messages, { id: `${request.request_id}-user`, role: "user", text: request.text, status: "processing", request_id: request.request_id }] } : current);
    try {
      const response = await fetch(`${liveApiBase}/v1/checkins/${checkinId}/messages`, { method: "POST", headers: liveHeaders(), body: JSON.stringify(request) });
      if (!response.ok) throw new Error("Your message could not be sent. Please retry.");
      const payload = await response.json() as SavedCheckin;
      if (!mounted.current) return;
      if (version === revision.current) setCheckin(payload);
      const turn = payload.conversation_messages.find(message => message.request_id === request.request_id);
      if (turn?.status !== "done") {
        setError(turn?.error || "The coach could not respond. Please retry.");
      } else {
        pendingRef.current = null;
        setPending(null);
        setDraft("");
      }
    } catch {
      if (mounted.current) {
        setError("Your message could not be sent. Please retry.");
        setCheckin(current => current ? { ...current, conversation_messages: current.conversation_messages.map(message =>
          message.request_id === request.request_id && message.status !== "done" ? { ...message, status: "failed" } : message) } : current);
      }
    } finally {
      busy.current = false;
      if (mounted.current) setWaiting(false);
    }
  }

  const processingMessage = checkin?.conversation_messages.some(message => message.request_id && message.status === "processing") ?? false;
  const responding = waiting || processingMessage;
  return (
    <section className="conversation-screen saved-conversation" aria-label="Saved conversation">
      {checkin ? <ConversationHistory messages={checkin.conversation_messages} waiting={responding} /> : <p role="status">Loading conversation…</p>}
      <p className="conversation-save-status" role="status">{checkin ? checkin.recording_completed_at ? "Conversation saved" : "Saving conversation…" : ""}</p>
      {error ? <p className="recording-error" role="alert">{error}</p> : null}
      {connectionError ? <p className="recording-error" role="status">{connectionError} <button type="button" onClick={() => setReload(value => value + 1)}>Reconnect</button></p> : null}
      {checkin?.recording_completed_at ? <p className="conversation-save-status" role="status">
        {checkin.analysis_status === "pending" ? "Audio analysis pending" : checkin.analysis_status === "delayed" ? "Audio analysis is taking longer than expected" : checkin.analysis_status === "failed" ? "Audio analysis failed" : "Audio analysis complete"}
        {checkin.analysis_status === "pending" || checkin.analysis_status === "delayed" ? <> · <button type="button" disabled={checking} onClick={() => void checkAnalysis()}>{checking ? "Checking…" : "Check analysis once"}</button></> : null}
      </p> : null}
      <form className="coach-composer" onSubmit={event => { event.preventDefault(); void send(); }}>
        <KeyboardInput value={pending?.text ?? draft} onChange={event => setDraft(event.target.value)} onBlur={() => keyboard.hide()}
          placeholder="Reply to your coach…" aria-label="Reply to your coach" maxLength={10000}
          disabled={responding || !!pending || !checkin?.recording_completed_at} />
        <button type="submit" onPointerDown={event => event.preventDefault()} disabled={responding || !checkin?.recording_completed_at || (!pending && !draft.trim())}>{pending && !responding ? "Retry" : "Send"}</button>
      </form>
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

type StepPhase = "connect" | "score" | "transcribe" | "done" | "error";
type ActivityStep = { id: number; text: string; phase: StepPhase; signals?: SignalResult[] };

// The real live-recording flow: actual mic capture, actual WebSocket to the backend,
// actual Amplifier scoring -- reachable via ?live=1, separate from the scripted
// BrainDumpRecorder above used for the presentation demo. Publishes the same
// publishLiveTrace/publishConversationMessage events, so presentation.html's trace
// panel shows genuine events instead of scripted ones when this path is used.
function LiveBrainDumpRecorder({ onSaved, onComplete, onViewData, onConversationReady, minimumSeconds }: { onSaved: (id: string) => void; onComplete: (transcript: string | null) => void; onViewData: () => void; onConversationReady: (transcript: string) => void; minimumSeconds: number }) {
  const [recording, setRecording] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [endingTurn, setEndingTurn] = useState(false);
  const [turnMessages, setTurnMessages] = useState<CoachMessage[]>([]);
  const [paused, setPaused] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [savedTranscript, setSavedTranscript] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);
  const [, setSteps] = useState<ActivityStep[]>([]);
  const [partialTranscript, setPartialTranscript] = useState("");
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
  const sentAudioRef = useRef(false);
  const captureActiveRef = useRef(false);
  const captureGenerationRef = useRef(0);
  const connectingRef = useRef(false);
  const mountedRef = useRef(true);
  const endingTurnRef = useRef(false);
  const hasTurnAudioRef = useRef(false);
  const continueConversationRef = useRef(false);

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
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      socketRef.current?.close();
      stopCapture();
    };
  }, []);

  function headers() {
    return { "Content-Type": "application/json", Authorization: `Bearer ${apiToken}` };
  }

  function addStep(text: string, phase: StepPhase = "done", signals?: SignalResult[]) {
    setSteps((current) => [...current, { id: stepIdRef.current++, text, phase, signals }]);
    publishLiveTrace(
      phase === "error" ? "error" : phase === "score" ? "model" : phase === "done" ? "result" : "stream",
      phase === "connect" ? "WebSocket stream" : phase === "score" ? "Pulse analysis" : phase === "transcribe" ? "Transcript" : phase === "done" ? "Check-in complete" : "Check-in update",
      text,
      signals,
    );
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
      publishLiveTrace("error", "Finish check-in", "No check-in ID was available.");
      return;
    }
    try {
      publishLiveTrace("request", "POST /v1/checkins/{id}/finish", "Finalizing the saved recording and derived results.");
      const finished = await fetch(`${apiBase}/v1/checkins/${checkinId}/finish`, { method: "POST", headers: headers() });
      if (!finished.ok) throw new Error("Could not save the recording.");
      const payload = await finished.json() as { transcript?: string | null };
      publishLiveTrace("result", "Check-in saved", "The backend returned the completed check-in.");
      setProcessing(false);
      setSaved(true);
      const transcript = payload.transcript ?? null;
      setSavedTranscript(transcript);
      onSaved(checkinId);
      onComplete(transcript);
      if (continueConversationRef.current) {
        const reflection = transcript?.trim() || "No transcript was captured for this check-in.";
        onConversationReady(reflection);
      }
    } catch {
      finishedRef.current = false;
      setProcessing(false);
      setPaused(true);
      setError("Your recording could not be saved. Please try again.");
      publishLiveTrace("error", "Finish check-in failed", "The backend could not finalize this check-in.");
    }
  }

  async function openStream(checkinId: string, ticket: string) {
    const streamUrl = new URL(`${apiBase}/v1/checkins/${checkinId}/stream`);
    streamUrl.protocol = streamUrl.protocol === "https:" ? "wss:" : "ws:";
    streamUrl.searchParams.set("ticket", ticket);
    publishLiveTrace("stream", "WS /v1/checkins/{id}/stream", "Opening the authenticated live PCM stream.");
    const socket = new WebSocket(streamUrl);
    socket.binaryType = "arraybuffer";
    await new Promise<void>((resolve, reject) => {
      socket.onopen = () => {
        publishLiveTrace("stream", "WebSocket connected", "The server is ready to receive 16 kHz PCM audio.");
        resolve();
      };
      socket.onerror = () => {
        publishLiveTrace("error", "WebSocket connection failed", "The secure audio stream could not be opened.");
        reject(new Error("Could not open the secure audio stream."));
      };
    });
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data) as {
        type?: string; message?: string; text?: string; code?: string; chunk?: number;
        turn_id?: string; transcript?: string; reply?: string; model?: string;
        usage?: { cache_read_input_tokens?: number; cache_creation_input_tokens?: number };
        job_id?: string; method?: string; path?: string; start_seconds?: number; end_seconds?: number; signals?: { name: string; level: string }[];
      };
      switch (message.type) {
        case "connected":
          addStep("Connected — ready to listen.", "connect");
          break;
        case "processing":
          addStep("Analyzing your check-in…", "score");
          break;
        case "analyzing":
          // One of these fires every 15s of captured audio, live, while you're
          // still talking -- the overlapping-window scoring, not a single end-of-call read.
          // The actual request, not a description of one.
          addStep(`chunk ${message.chunk} [${message.start_seconds}–${message.end_seconds}s] → ${message.method} ${message.path} → job ${message.job_id}`, "score");
          break;
        case "job_result":
          addStep(`chunk ${message.chunk} [${message.start_seconds}–${message.end_seconds}s] → job ${message.job_id} returned:`, "score", message.signals);
          break;
        case "transcribing":
          addStep("Transcribing what you said…", "transcribe");
          break;
        case "transcript_partial":
          if (captureActiveRef.current && message.text) {
            setPartialTranscript(message.text);
            addStep(`Heard so far: “${truncate(message.text, 70)}”`, "transcribe");
          }
          break;
        case "turn_processing":
          publishLiveTrace("request", "End Turn", "Preparing this turn's transcript for Sonnet.");
          break;
        case "turn_transcript":
          if (message.text) setPartialTranscript(message.text);
          break;
        case "turn_result":
          if (message.turn_id && message.transcript && message.reply) {
            const userMessage: CoachMessage = { id: `${message.turn_id}-user`, role: "user", text: message.transcript };
            const replyMessage: CoachMessage = { id: `${message.turn_id}-agent`, role: "agent", text: message.reply };
            setTurnMessages((current) => current.some((item) => item.id === userMessage.id) ? current : [...current, userMessage, replyMessage]);
            setPartialTranscript("");
            hasTurnAudioRef.current = false;
            publishConversationMessage("user", message.transcript);
            publishConversationMessage("agent", message.reply);
            publishLiveTrace("result", "Sonnet reply", `Received a reply from ${message.model ?? "Sonnet"}. Cache read: ${message.usage?.cache_read_input_tokens ?? 0} tokens; cache write: ${message.usage?.cache_creation_input_tokens ?? 0} tokens.`);
          }
          endingTurnRef.current = false;
          setEndingTurn(false);
          break;
        case "transcript":
          addStep(message.text ? `Heard: “${truncate(message.text, 70)}”` : "Transcript ready.", "transcribe");
          break;
        case "result":
          addStep("Saved to your trends.", "done");
          void finishRecording();
          break;
        case "error":
          // processing_timeout is terminal but not fatal: the backend gave up waiting on
          // this connection, not on the check-in itself, which keeps completing in the
          // background. pulse_processing_failed/transcription_failed are per-step and
          // non-fatal too -- the backend still finishes and will send "result". Anything
          // else (e.g. invalid_pcm_frame, mid-recording) is a real, blocking problem.
          if (message.code === "conversation_failed") {
            endingTurnRef.current = false;
            setEndingTurn(false);
            setError(message.message ?? "The coach could not respond. Try End Turn again.");
          } else if (message.code === "processing_timeout") {
            addStep("Taking longer than expected — finishing in the background.", "error");
            void finishRecording();
          } else if (message.code === "pulse_processing_failed" || message.code === "transcription_failed") {
            addStep(message.message ?? "One step had an issue, but your check-in is still being saved.", "error");
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
    captureActiveRef.current = false;
    captureGenerationRef.current += 1;
    if (processorRef.current) processorRef.current.port.onmessage = null;
    processorRef.current?.disconnect();
    sourceRef.current?.disconnect();
    void audioContextRef.current?.close();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    processorRef.current = null;
    sourceRef.current = null;
    audioContextRef.current = null;
    streamRef.current = null;
  }

  async function prepareMicrophone(socket: WebSocket) {
    if (!mountedRef.current) throw new Error("Capture cancelled.");
    const generation = ++captureGenerationRef.current;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    let context: AudioContext | null = null;
    try {
      if (generation !== captureGenerationRef.current) throw new Error("Capture cancelled.");
      context = new AudioContext();
      await context.audioWorklet.addModule("/pcm-processor.js");
      if (generation !== captureGenerationRef.current || socket.readyState !== WebSocket.OPEN) {
        throw new Error("Capture cancelled or stream disconnected.");
      }
      const source = context.createMediaStreamSource(stream);
      const processor = new AudioWorkletNode(context, "pcm-processor", { processorOptions: { targetRate: 16000 } });
      processor.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
        // This synchronous gate also drops frames queued before a pause or Save.
        if (!captureActiveRef.current || generation !== captureGenerationRef.current) return;
        if (socket.readyState === WebSocket.OPEN) {
          if (!sentAudioRef.current) {
            sentAudioRef.current = true;
            publishLiveTrace("audio", "PCM audio streaming", "16 kHz mono audio frames are now being sent over the live stream.");
          }
          hasTurnAudioRef.current = true;
          socket.send(event.data);
        }
      };
      source.connect(processor);
      processor.connect(context.destination);
      streamRef.current = stream;
      audioContextRef.current = context;
      sourceRef.current = source;
      processorRef.current = processor;
    } catch (error) {
      stream.getTracks().forEach((track) => track.stop());
      void context?.close();
      throw error;
    }
  }

  async function startRecording() {
    if (connectingRef.current) return;
    setError(null);
    setSaved(false);
    setSavedTranscript(null);
    setSteps([]);
    setPartialTranscript("");
    setTurnMessages([]);
    setEndingTurn(false);
    endingTurnRef.current = false;
    hasTurnAudioRef.current = false;
    sentAudioRef.current = false;
    continueConversationRef.current = false;

    if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode) {
      setError("Live audio recording is not available in this browser.");
      return;
    }

    connectingRef.current = true;
    setConnecting(true);
    try {
      publishLiveTrace("request", "POST /v1/checkins", "Creating a new Morning Check-in and one-use stream ticket.");
      const created = await fetch(`${apiBase}/v1/checkins`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ source: "morning-check-in" }),
      });
      if (!created.ok) throw new Error("Could not create a Morning Check-in.");
      const { checkin, stream_ticket: ticket } = await created.json() as { checkin: { checkin_id: string }; stream_ticket: string };
      publishLiveTrace("result", "Check-in created", `Check-in ${checkin.checkin_id.slice(0, 8)}… is ready to stream.`);
      if (!mountedRef.current) return;
      const socket = await openStream(checkin.checkin_id, ticket);
      await prepareMicrophone(socket);
      captureActiveRef.current = true;
      checkinIdRef.current = checkin.checkin_id;
      startedAtRef.current = Date.now();
      recordedMsRef.current = 0;
      setElapsed(0);
      setRecording(true);
    } catch (err) {
      console.error("startRecording failed:", err);
      stopCapture();
      socketRef.current?.close();
      setError("Microphone access and the private check-in service are needed to record.");
      publishLiveTrace("error", "Recording could not start", "Microphone access or the private check-in API was unavailable.");
    } finally {
      connectingRef.current = false;
      setConnecting(false);
    }
  }

  function pauseRecording() {
    if (!captureActiveRef.current) return;
    recordedMsRef.current += Date.now() - startedAtRef.current;
    setElapsed(Math.floor(recordedMsRef.current / 1000));
    stopCapture();
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ type: "checkin.pause" }));
    }
    publishLiveTrace("stream", "checkin.pause", "Microphone stopped; transcription and new analysis requests are paused.");
    setRecording(false);
    setPaused(true);
  }

  async function resumeRecording() {
    const socket = socketRef.current;
    if (!paused || connectingRef.current || endingTurnRef.current) return;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setError("The recording connection was lost. Save this check-in before starting another.");
      return;
    }
    connectingRef.current = true;
    setConnecting(true);
    setError(null);
    try {
      await prepareMicrophone(socket);
      socket.send(JSON.stringify({ type: "checkin.resume" }));
      startedAtRef.current = Date.now();
      captureActiveRef.current = true;
      publishLiveTrace("stream", "checkin.resume", "Audio capture and analysis have resumed.");
      setPaused(false);
      setRecording(true);
    } catch {
      stopCapture();
      setError("Microphone access is needed to resume recording. Your check-in is still paused.");
    } finally {
      connectingRef.current = false;
      setConnecting(false);
    }
  }

  function endTurn() {
    if (endingTurnRef.current || connectingRef.current || (!recording && !paused)) return;
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setError("The recording connection was lost. Start a new check-in to talk to the coach.");
      return;
    }
    if (!hasTurnAudioRef.current) {
      setError("Speak before ending your turn.");
      return;
    }
    if (recording) {
      recordedMsRef.current += Date.now() - startedAtRef.current;
      setElapsed(Math.floor(recordedMsRef.current / 1000));
    }
    stopCapture();
    setRecording(false);
    setPaused(true);
    setError(null);
    endingTurnRef.current = true;
    setEndingTurn(true);
    // Send the boundary on the audio WebSocket so all earlier PCM frames are
    // received before the server takes the authoritative transcript snapshot.
    socket.send(JSON.stringify({ type: "checkin.turn.end" }));
    publishLiveTrace("stream", "checkin.turn.end", "Microphone stopped. Sending this turn to Sonnet.");
  }

  function saveRecording(startConversation = false) {
    if (endingTurnRef.current || connectingRef.current) return;
    if ((!recording && !paused) || (!paused && elapsed < minimumSeconds) || !checkinIdRef.current) return;
    continueConversationRef.current = startConversation;
    captureActiveRef.current = false;
    if (recording) {
      recordedMsRef.current += Date.now() - startedAtRef.current;
      setElapsed(Math.floor(recordedMsRef.current / 1000));
      void audioContextRef.current?.suspend();
    }
    finishedRef.current = false;
    // Not clearing `steps` here -- the log now spans the whole session (connect
    // through result), not just the processing phase, so what already happened
    // during recording (e.g. live "analyzing" windows) stays visible.
    setProcessing(true);
    setRecording(false);
    setPaused(false);
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ type: "checkin.end" }));
    } else {
      void finishRecording();
    }
    publishLiveTrace("stream", "checkin.end", "Audio capture ended; waiting for processing and transcription.");
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
      <section className="conversation-screen saved-conversation" aria-label="Saving your conversation">
        <ConversationHistory messages={[
          { id: "opening", role: "assistant", text: "How are you feeling today?", status: "done" },
          ...turnMessages.map(message => ({ ...message, role: message.role === "agent" ? "assistant" as const : "user" as const, status: "done" })),
          ...(partialTranscript ? [{ id: "final-speech", role: "user" as const, text: partialTranscript, status: "processing" }] : []),
        ]} />
        <p className="conversation-save-status" role="status">Saving conversation…</p>
      </section>
    );
  }

  if (saved) {
    return (
      <section className="brain-dump checkin-saved" aria-label="Morning Check-in saved">
        <p className="saved-confirmation" role="status" aria-live="polite">saved.</p>
        <div className="saved-actions" aria-label="Next steps">
          <button type="button" className="save-audio" onClick={onViewData}>View Data</button>
          <button type="button" className="stop-recording" onClick={() => onConversationReady(savedTranscript?.trim() || "No transcript was captured for this check-in.")}>Continue conversation in chat</button>
        </div>
      </section>
    );
  }

  if (recording || paused) {
    return (
      <section className="brain-dump checkin-live" aria-label="Morning Check-in voice reflection">
        <div className="conversation-screen live-transcript" aria-label="Live conversation">
          <MobileScroll className="conversation-messages">
            <p className="coach-bubble">How are you feeling today?</p>
            {turnMessages.map((message) => (
              <p key={message.id} className={message.role === "agent" ? "coach-bubble" : "member-bubble"}>{message.text}</p>
            ))}
            {partialTranscript ? (
              <p className="member-bubble" aria-live="polite">{partialTranscript}</p>
            ) : (
              <p className="coach-typing" aria-live="polite">{endingTurn ? "Preparing your turn…" : paused ? "Paused" : <>Listening<span>···</span></>}</p>
            )}
            {endingTurn && partialTranscript ? <p className="coach-typing" role="status">Coach is thinking…</p> : null}
          </MobileScroll>
        </div>
        <div className="live-controls">
          <button type="button" className={recording ? "microphone is-listening" : "microphone is-paused"} onClick={recording ? pauseRecording : resumeRecording} disabled={connecting || endingTurn} aria-pressed={recording} aria-label={recording ? "Pause Morning Check-in recording" : "Resume Morning Check-in recording"}>
            {recording ? <PauseIcon width={20} height={20} /> : <PlayIcon width={20} height={20} />}
          </button>
          <strong className="recording-timer" aria-live="polite">{formattedTime}</strong>
        </div>
        {error ? <span className="recording-error" role="alert">{error}</span> : null}
        <div className="recorder-actions">
          <button type="button" className="save-audio" onClick={() => saveRecording()} disabled={saved || connecting || endingTurn || (!paused && elapsed < minimumSeconds)}>Save Conversation</button>
          <button type="button" className="stop-recording end-turn" onClick={endTurn} disabled={connecting || endingTurn}>End Turn</button>
        </div>
      </section>
    );
  }

  return (
    <section className="brain-dump" aria-label="Morning Check-in voice reflection">
      <button type="button" className="microphone" onClick={startRecording} disabled={connecting} aria-label="Start recording Morning Check-in">
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
      {error ? <span className="recording-error" role="alert">{error}</span> : null}
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
