# Design QA — Longevity Today

## Comparison Target

- Source visual truth: `/Users/somya/.codex/generated_images/01a0bcf4-1b5d-7cd2-8f50-b98e5951cdd5/exec-92ec1ec6-d83d-4d72-9bcc-9f313b38c605.png`
- Implementation capture: `/private/tmp/longevity-today-final.png`
- Combined comparison capture: `/private/tmp/longevity-comparison-final.png`
- State: Today selected; Morning Check-in expanded; Add habit frequency choices visible; no habits completed.
- Browser viewport: 1400 × 1200 CSS px; the captured iPhone app screen measured 393 × 852 CSS px at device scale factor 1.
- Source dimensions: 853 × 1844 px. It was normalized to 393 × 852 px for the side-by-side comparison. The implementation capture is 394 × 852 px because of raster clip rounding; its measured CSS screen is 393 × 852 px.

## Findings

No actionable P0, P1, or P2 findings remain.

### Required Fidelity Surfaces

- **Fonts and typography:** The implementation uses the runtime system sans-serif stack, which retains the selected mock’s clean, rounded, high-legibility hierarchy. Greeting, date, habit labels, upper-case eyebrow, and small controls maintain distinct optical weights without truncation at the target viewport.
- **Spacing and layout rhythm:** Compact 51 px habit rows and the reduced voice surface preserve the mock’s dense daily-protocol rhythm. The runtime’s true status/home chrome occupies safe area that the generated source omitted; that is expected template-owned infrastructure. Add habit and its frequency choices now remain visible above the fixed tab bar at the initial scroll position.
- **Colors and visual tokens:** The app consistently applies ink black, deep espresso, burnished amber, honey gold, warm ivory, and smoky-tan secondary text. Completion and active-tab states use the brighter amber token without reducing contrast.
- **Image quality and assets:** No photographic, illustrated, logo, or decorative raster assets are present in the selected app-owned UI. The actual microphone and standard UI glyphs are rendered by maintained icon libraries, with no handwritten SVG or placeholder art.
- **Copy and content:** All requested habits appear exactly: Hydrate, Liposomal Glutathione, Morning Light, Morning Check-in, Meditation, Clinic Visit — Cold Plunge, and Workout. The required “Good morning, Maya,” September 27, 2026 date, “Find a quiet space,” and Daily/Weekly/Custom choices are present.

## Comparison History

1. **Initial comparison:** The prototype’s expanded Morning Check-in surface and vertically stacked frequency picker made the daily list meaningfully looser than the selected mock; frequency controls were below the initial viewport. This was a P2 layout-density mismatch.
2. **Fix:** Tightened the header, habit rows, and voice surface; kept the frequency choice visible by default; made the Add habit and frequency controls one compact inline surface; switched Morning Check-in to a real microphone icon.
3. **Post-fix evidence:** `/private/tmp/longevity-comparison-final.png` confirms the core screen now keeps the full requested protocol, expanded Morning Check-in state, Add habit, and frequency choices in the immediate mobile view. Remaining device bezel/status/home-indicator differences are explicitly template-owned and outside app-content fidelity scope.

## Interaction and Technical Checks

- Browser-rendered preview tested in the in-app browser.
- Today ↔ Trends navigation works.
- Trend ranges update their visible time description.
- Habit completion updates the completion count.
- Morning Check-in microphone toggles between ready and listening states.
- Frequency selection works, including Custom.
- Fresh browser-console check found no errors.
- `npm run check:runtime` passed.
- `npm run build` passed.

## Follow-up Polish

- P3: Add a dedicated detail view for the “View the pattern” action once there is a real health-data model behind the prototype.

final result: passed

---

## Morning Check-in Bubble Follow-up — September 20, 2026

### Follow-up Findings

No actionable P0, P1, or P2 findings remain.

- The timer is now the visual anchor beneath the microphone, at 42 px.
- The two instruction bubbles sit below it at an equal 272 px width: “Find a quiet space.” and “Talk for at least 30 seconds.”
- The full-screen check-in was rendered and visually inspected in the in-app mobile preview; `npm run check:runtime` and `npm run build` passed.

final result: passed

---

## Full-Screen Morning Check-in Follow-up — September 20, 2026

- Updated implementation capture: `/private/tmp/morning-checkin-fullscreen-final.png`
- State: Morning Check-in opened from its Today-row arrow; timer idle at `00:00`.
- Source truth: user-authored requirement that opening Morning Check-in fills the screen and displays “Find a quiet space and tell us how your morning is going. At least 30 seconds.”

### Follow-up Findings

No actionable P0, P1, or P2 findings remain.

- The entry route fills the app-owned phone screen and keeps the task-list UI behind a deliberate, dismissible recording surface.
- The requested prompt is visible verbatim, with a focused 30-second timer and an appropriately dominant microphone control.
- Safe-area fallback spacing keeps the title and close control clear of device chrome.
- `npm run check:runtime` and `npm run build` passed after the update.

final result: passed

---

## Recording Flow Follow-up — September 20, 2026

- Updated implementation capture: `/private/tmp/longevity-recorder-final.png`
- State: Today selected; Morning Check-in expanded; recorder idle at `00:00`.
- New source truth: user-authored interaction requirement to show “Find a quiet space and chat for at least 1 minute,” track elapsed time, save the audio in place, and complete Morning Check-in after saving.

### Follow-up Findings

No actionable P0, P1, or P2 findings remain.

- The recorder’s idle state displays the complete prompt and a legible tabular `00:00` timer in the existing amber voice surface.
- Starting a recording invokes browser microphone capture, updates the timer four times per second, and offers a stop control.
- A captured clip gets an inline audio preview. Saving remains disabled until 60 seconds, downloads the local `.webm` file when enabled, and then marks Morning Check-in complete.
- A fresh browser-console check found no errors. `npm run check:runtime` and `npm run build` passed after the change.

final result: passed
