# Mission — RepairRöpi

> **One sentence:** We give CNC machine operators in German SMEs an AI diagnostic partner that thinks like a senior technician — asking the right questions, narrowing down faults collaboratively, and eliminating guesswork.

---

## The Problem

German manufacturing is bleeding expertise. **37% of the industrial workforce is over 50.** In Maschinenbau alone, an estimated 296,000 workers will retire by 2033 — taking decades of machine-specific repair knowledge with them.

The people left behind aren't incompetent. They're **under-informed.** A junior technician or retrained operator standing in front of a 20-year-old CNC lathe throwing error code `AL 309` has the hands to fix it — but not the knowledge to diagnose it.

Today, that technician's options are:

1. Call the one retired expert who might pick up the phone.
2. Dig through filing cabinets for a paper manual from 1998.
3. Wait 2–5 days for OEM support at 150+ €/hour.
4. Trial and error — while production bleeds **250–3,750 €/hour** in downtime.

**Diagnosis accounts for 50–70% of total repair time.** The machine isn't hard to fix. Figuring out *what's wrong* is the bottleneck.

---

## The User

**Primary persona:** A non-expert CNC machine operator or junior maintenance technician (Industriemechaniker, Mechatroniker, or angelernt) in a German SME with 10–500 employees.

They have:
- A smartphone (Android-dominant, often rugged devices)
- General technical competence
- Access to the machine and its symptoms

They lack:
- Deep, machine-specific fault diagnosis expertise
- Easy access to relevant documentation (scattered, outdated, sometimes only in Japanese)
- A senior colleague to ask

They need:
- **Guided reasoning**, not information dumps
- **Conversational diagnostics** — "Check this first. What do you see?"
- **Confidence to act safely** without understanding every engineering detail
- **Visual and multilingual support** — ~30% of the metalworking workforce has a migration background

---

## The Solution

**RepairRöpi** is a multimodal AI diagnostic partner. It doesn't just answer questions — it **investigates together with the technician**, like a senior colleague would: asking targeted questions, requesting specific observations, narrowing down hypotheses turn by turn, until the fault is identified.

### The Core Loop: Collaborative Diagnosis

The interaction is not single-shot. It's an iterative detective process:

```
1. INITIAL INPUT
   Technician shares what they have: a photo, an error code,
   a voice description — or all three.

2. HYPOTHESIS FORMATION
   Agent forms ranked hypotheses based on input +
   documentation + known fault patterns for this machine family.

3. DIRECTED INVESTIGATION  ← this is where the value lives
   Agent asks for specific evidence to discriminate between hypotheses:
   "Can you send a photo of the spindle chuck?"
   "What sound does it make when you jog the X-axis?"
   "Check the coolant level and tell me what you see."
   "Read me the value on parameter P1234."

4. NARROWING
   Each technician response eliminates hypotheses.
   Agent updates its reasoning and asks the next targeted question.
   Repeat 3–4 until confident.

5. DIAGNOSIS + GUIDANCE
   Once the fault is identified with sufficient confidence:
   Agent delivers the diagnosis with explanation,
   followed by actionable next steps (repair, escalate, or order parts).

6. VERIFICATION
   Technician confirms the fix (photo/text).
   The full diagnostic trace is captured.
```

> [!IMPORTANT]
> **Diagnosis is the product.** Repair steps are often simple once you know what's wrong ("replace bearing X", "adjust parameter Y"). The hard part — and 50–70% of actual downtime — is figuring out *what's wrong*. That's what we solve.

### What Makes This Different

- **Not a chatbot.** A guided diagnostic conversation that *drives the investigation* — asking the right questions in the right order, like a senior technician with 30 years of experience would.
- **Not single-shot.** One photo is rarely enough. The system actively requests additional evidence — more photos from different angles, measurements, sounds, parameter readings — to narrow down the fault.
- **Not a search engine.** The system reasons over documentation, not just retrieves it. It connects symptoms to causes to discriminating tests to actions.
- **Not just text.** Multimodal from day one — photos of damage, error codes on displays, voice descriptions on noisy factory floors. The technician's hands stay free, their eyes stay on the machine.

---

## Phase 1 Vertical: CNC Machines

CNC-Fräsen (40–45% of SME machine parks) and CNC-Drehen (30–35%) are our target. The dominant control systems are:

- **Siemens** (SINUMERIK)
- **Heidenhain** (TNC/iTNC)
- **Fanuc**

These three families define our initial error code universe, documentation corpus, and fault taxonomy.

> [!IMPORTANT]
> We do **not** attempt to cover "all industrial machines." Phase 1 is CNC only. Breadth comes from depth — a system that's excellent on one machine family earns the trust to expand.

### Vertical ≠ Architecture

The long-term product diagnoses **any machine the user points it at** — CNC lathe, conveyor, pump, or Arduino board. Phase 1 scopes the *knowledge*, not the *design*: everything machine-specific (error-code seeds, fault taxonomy, documentation corpus, prompt context, golden cases) lives in a swappable **machine knowledge pack**; the diagnostic loop, API contract, Data Bridge, and learning pipeline stay machine-agnostic. Adding vertical #2 must mean adding a knowledge pack — never touching the core. (Schema is already keyed by `machine_family`/`controller_family`; see Roadmap Feature 4.1.)

---

## Success Metric

> **Reduce diagnostic time by ≥40%** for non-expert technicians on CNC machine faults, compared to the current unsupported process (phone calls, paper manuals, trial and error).

Measured on real machines, with real users, in a real factory. Not in a lab.

Secondary metrics:
- First-time fix rate improvement
- Reduction in OEM service calls for diagnosable faults
- Technician confidence score (self-reported)

---

## Architectural Principle: The Data Bridge

Every solved repair case generates a structured trace:

```
Visual State (image)
  → Symptom (text/voice)
  → Agent Reasoning (hypothesis chain)
  → Proposed Action (step sequence)
  → Technician Verification (image/text confirmation)
  → Outcome (success / escalation / failure)
```

This is not "logging." This is **structured physical knowledge**. The system is designed so that every successful repair produces a training example for future autonomous repair systems. We instrument for this from day one — not as a feature, but as an architectural invariant.

> [!NOTE]
> The data bridge is an *engineering decision*, not a product promise. Users care about getting their machine running. The training traces are a consequence of doing that well.

### The Learning Loop

The Data Bridge records what happened. The agent backbone (an embedded [hermes-agent](https://github.com/nousresearch/hermes-agent)) goes one step further: it **learns** from what happened — creating reusable skills after complex diagnoses, building memory of each customer's machine park, and exporting training-ready trajectories.

**Everything the technician on the ground teaches the agent flows to our cloud:**

```
Field session (tenant)
  → trajectories  → training dataset for future repair models
  → skills        → curation gate → shared fleet skill base → every tenant benefits
  → memory        → stays tenant-scoped (better diagnosis for THAT customer)
```

One customer's solved fault pattern becomes — after curation — every customer's head start. Tenant data never crosses the boundary uncurated; the curation gate is a hard invariant (GDPR + competitive isolation).

---

## Future Core Competence: Visual Grounding

Proven in our earlier prototype [zurich_physical_hack](https://github.com/edavidk7/zurich_physical_hack) (Arduino-board diagnosis, IBM Docling Challenge): the system parses technical documentation — schematics, datasheets, SOPs — and **points to the exact spot in the physical world**, there via a camera-calibrated robot arm with a multimeter probe. In RepairRöpi the pointer is not a robot arm but the technician's smartphone camera:

1. **Understand the sketch** — parse schematics, exploded views, wiring diagrams from the manual (Docling — same parser the prototype used).
2. **Ground it in the photo** — match the diagram against the user's photo of the real machine (keypoint detection, pose estimation — ported from the prototype's vision pipeline).
3. **Point and augment** — return the technician's own image with guidance drawn on it: arrows, highlights, part outlines projected from the schematic onto reality. *"The bearing you need is HERE."*

Augmented images are language-agnostic guidance — a highlighted photo needs no translation (~30% of our users have a migration background). The capability phases in: simple photo annotations first (VisionAnalysisTool, Phase 2), full schematic-to-photo grounding later (Roadmap Phase 4).

---

## Explicit Non-Goals (Phase 1)

These are things we **will not build** in Phase 1, regardless of how tempting they are:

| Non-Goal | Why Not Now |
|---|---|
| OPC-UA / MQTT / PLC direct integration | Requires machine-specific adapters; zero-install smartphone is our advantage |
| Knowledge graphs (Memgraph) | Premature optimization; flat vector/document store is sufficient |
| Multi-agent orchestration | Single monolithic agent core with tools (hermes supports subagents — we don't use them); refactor when complexity demands it |
| Messaging channels (WhatsApp/Telegram via hermes gateway) | Validated option (relay-connector contract exists), deferred to Phase 3+; the app's structured evidence capture (typed hypotheses, camera control) is the product |
| AR overlays (RealWear, Vision Pro) | Hardware dependency; smartphone camera is universally available. Annotated still images (visual grounding, Phase 4) are **not** AR — no headset, no live tracking |
| Predictive maintenance / sensor fusion | Different product; we solve *reactive* repair first |
| Offline-first architecture | Modern factories have connectivity; validate online-first before engineering offline |
| CMMS/ERP integration | Integration work that doesn't prove the core thesis |
| Automated spare parts ordering | Requires ERP integration and procurement workflows |
| Full multilingual UI | Phase 1 is German + English; broader language support follows |

---

## The Two-Repo Discipline

> Reality check (Feature 1.0): this is one git repository with two top-level directories.
> The discipline is the *boundary* — the API contract — not the git split.

| Directory | Purpose |
|---|---|
| **Repair_Logic_Agent** | Backend: agent reasoning, tool execution, document retrieval, API |
| **RepairRöpiApp** | Frontend: mobile UI, camera/mic access, user interaction |

The API contract between them is the most critical specification. The frontend must not know or care whether reasoning happens on a cloud LLM or a local model. It sends a standardized payload; it receives a streaming reasoning response.

---

*Stand: Juli 2026 — updated for hermes-agent backbone (Techstack v3); strategic directions added 2026-07-18: machine-agnostic core, visual grounding, image augmentation*
