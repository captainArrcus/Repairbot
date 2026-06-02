# Considerations regarding the agentic Framework we use: 


# Agentic Frameworks in 2026 — Conversation Summary

## 1. Framework Landscape Overview

### The Main Players (Python-embeddable)

| Framework | Status | Best For |
|---|---|---|
| **LangGraph** | Production leader, most active | Stateful, fault-tolerant, long-running workflows |
| **smolagents** | Solid, slower cadence (last release Jan 2026) | HuggingFace / local models, code-generating agents |
| **CrewAI** | Great for prototyping, ceiling in production | Fast multi-agent prototypes |
| **PydanticAI** | Rising, type-safe, no magic | Python-native teams wanting full control |
| **OpenAI Agents SDK** | Fastest release velocity | OpenAI ecosystem, handoff-based multi-agent |
| **AutoGen / AG2** | ⚠️ Stagnant (no release since Sep 2025) | Avoid for greenfield projects |
| **Google ADK** | Early-stage, Google Cloud native | Cross-framework A2A interoperability experiments |
| **DSPy** | Niche but unique | Eval-driven pipeline optimization |

### Key 2026 Meta-Trends
- **MCP** (Model Context Protocol) and **A2A** (Agent-to-Agent) are the new interoperability standards — most frameworks racing to support both
- smolagents' code-as-action philosophy (agents write Python instead of calling JSON tools) is increasingly validated by the broader ecosystem

---

## 2. MCP: The Token Cost Problem

### The Core Issue
MCP loads **all tool schemas into context on every turn**, not just when tools are used.

- A single Gmail tool = ~820 tokens
- GitHub MCP server (43 tools) = ~44,000 tokens — before any question is asked
- Multi-agent systems with 3 sub-agents easily exceed **72,000 tokens in schema overhead alone**

### Real Benchmarks
- CLI vs MCP for a simple task: **1,365 tokens (CLI) vs 44,026 tokens (MCP)**
- CLI reliability: **100%** vs MCP: **72%** (TCP timeout failures)
- CLI Token Efficiency Score: **202 vs 152** for MCP (33% efficiency advantage)

### The Root Cause
The problem is not MCP the protocol — it's the **LLM-as-router pattern**: injecting all schemas and letting the LLM decide which tool to call. This is both token-expensive and reliability-risky (wrong tool selection, fabricated parameters).

### Emerging Alternatives
- **UTCP** (Jul 2025): agents call tools directly via native endpoints (HTTP, gRPC, CLI) — no wrapper server. Claims 60% faster, 68% fewer tokens, 88% fewer round trips
- **MCP Gateways**: filter schemas per-task (~90% token reduction), pool connections, centralize auth — makes MCP viable for multi-tenant production

### Decision Framework
| Scenario | Recommendation |
|---|---|
| Internal tools, you are the user | Direct Python calls + 800-token skills doc |
| Customer-facing, multi-tenant | MCP with a gateway, never raw schema injection |
| Cross-framework agent interop | MCP/A2A for the bus, code execution for the action layer |

### The Anthropic-Recommended Pattern
Present MCP servers as **code APIs, not direct tool calls**. The agent writes code to interact with MCP — only loads tools it needs, intermediate results stay in the execution environment, never bloating the model context. This is essentially the smolagents philosophy applied to MCP.

---

## 3. Framework Recommendation for the Specific Profile

**Profile:** Long-running stateful workflows · Mix of cloud + local models · Priorities: Reliability > Token cost > Full control > Developer velocity

### Verdict: LangGraph as skeleton + own Python as muscles

**Use LangGraph for:**
- Built-in checkpointing (resume crashed workflows from exact failure point)
- Explicit graph = full visibility into every state transition
- Model-agnostic (Anthropic orchestrator + local HF model for cheap sub-tasks)
- Human-in-the-loop gates as first-class primitives

**Homebrew these — don't outsource to any framework:**
- **Tool layer** — plain Python functions, called directly from graph nodes. No MCP schema injection.
- **State schema** — typed Pydantic model. Own its shape entirely.
- **Retry/error policy** — write it explicitly; don't configure it in YAML
- **Observability** — pipe LangGraph's standard events to your own stack; avoid LangSmith lock-in

**Watch PydanticAI** if your workflows are more chain-shaped than graph-shaped — cleaner Python feel, strict type contracts, good dependency injection. Graph support is newer but maturing.

**Avoid CrewAI** for this profile — fast to start, hits its ceiling exactly when you need production-grade state control.

### The One-Line Summary
> Don't homebrew the orchestration skeleton (checkpointing is hard). Do homebrew everything that touches your domain logic and tools.

---

## Key Sources & Reading
- [CLI Tools vs MCP Benchmarks](https://jannikreinhard.com/2026/02/22/why-cli-tools-are-beating-mcp-for-ai-agents/) — Feb 2026
- [MCP vs CLI Scalekit Benchmark](https://www.scalekit.com/blog/mcp-vs-cli-use) — Mar 2026
- [MCP Is Not Dead, It's Being Misused](https://www.agora.software/en/mcp-is-not-dead-its-being-misused/) — Mar 2026
- [Code Execution with MCP — Anthropic Engineering](https://www.anthropic.com/engineering/code-execution-with-mcp)
- [MCP Token Overhead Analysis](https://docs.bswen.com/blog/2026-04-24-mcp-token-overhead/) — Apr 2026









# Considerations regarding the Product: 

Repair Bot Project — Consolidated Synthesis & Constitutional Foundation

Spec-Driven Development Brief | Stand: Mai 2026
1. The Core Thesis

We are not building a chatbot for experts, nor are we building a robot yet. We are building a competence bridge and a dataset factory simultaneously.

    For 2026: A smartphone-based assistant that enables non-expert maintenance staff in German SMEs to diagnose and repair industrial machines significantly faster than the current ad-hoc process.
    For 2030+: The structured, verified interaction traces from those repairs become the perceptual, cognitive, and procedural training corpus for an autonomous repair robot.

Every design decision must serve both masters: immediate technician trust and future embodied autonomy. If a feature does not generate a structured training signal, we do not build it in Phase 1.
2. Domain & User Context
The German Mittelstand Gap

    Market: German SME manufacturing (Mittelstand).
    Demographic Pressure: A generation of specialist technicians is retiring. The remaining staff have general technical competence but lack deep, machine-specific repair expertise.
    Current Baseline (The "Competition"): 
         Try to reach the one retired expert by phone.
         Rummage through filing cabinets for paper manuals from the 1980s–90s.
         Wait days for manufacturer support.
         Trial-and-error debugging with production downtime accruing by the hour.

The User Persona

A non-expert operator or junior technician standing in front of a broken machine. They are not stupid; they are under-informed. They need:

    Guided reasoning, not raw information dumps.
    Conversational diagnostics ("Check this first. What do you see?").
    Confidence to act safely without understanding every engineering detail.

Success Metric

Reduce time-to-fix by ≥40% for target repair scenarios compared to the current unsupported process. Success is measured on real machines with real users, not in a lab.
3. Architectural Principles (The "How")
3.1 Interface-First, Two-Repo Discipline

Your separation into RepairRöpiApp (frontend) and Repair_Logic_Agent (backend) is correct, but the API contract between them is the most critical specification we will write. 

    Backend Agnosticism: The frontend must not care if reasoning happens on an edge LLM (Llama/Mistral) or in the cloud (Claude/GPT-4V). It sends a standardized payload; it receives a standardized reasoning stream.
    Streaming Required: Because trust is existential for non-experts, the agent must expose its intermediate reasoning ("Checking manual for error E-221… Found three possible causes… Eliminating option A because you said there is no hydraulic leak"). The API must support streaming from day one. Retrofitting this is painful.

Canonical Payload Sketch:
json
 
     
 
 
1
2
3
4
5
6
7
8
9
10
11
12
13
⌄
⌄
⌄
{
  "session_id": "uuid",
  "machine_family": "CNC_LATHE_2018",
  "modality_input": {
    "image": "base64_or_url",
    "audio_transcript": "Es rattert beim Anfahren",
    "text": "optional freeform"
  },
  "telemetry": {
    "user_skill_level": "operator",
    "repair_context": "production_floor"
  }
}
 
 
3.2 Monolithic Agent Core with Tools (Not a Society)

All three perspectives converged on this. Your brainstorm proposed five specialized agents (Diagnose, Document, Parts, Escalation, Learning). For Phase 1, this is architectural over-engineering.

Consensus: A single Repair Reasoning Core with three tools:

     Vision Tool: Multimodal LLM call for part identification, damage assessment, error-code reading.
     RAG/Document Tool: Retrieves from manuals and service history.
     Action/Guidance Tool: Structures the step-by-step repair protocol.

We may refactor into a true multi-agent society later (orchestrated via message passing, potentially using Memgraph), but only when the single-core architecture provably hits a complexity ceiling. For now, frameworks like LangGraph or lightweight orchestration loops inside FastAPI are the right abstraction.
3.3 Vertical over Horizontal

"Industrial machines" is not a vertical; it is a continent. We must bless one machine family for Phase 1. This is non-negotiable for three reasons:

    Expertise Density: The agent needs to learn specific fault modes, not generic "machine broken."
    Data Moat: Verified repair traces for one machine class are infinitely more valuable for future robotics than shallow traces across ten classes.
    Documentation Sanity: German SMEs have heterogeneous fleets. We need to validate the documentation reality for one class before designing universal parsers.

The caveat: We do not yet know which machine family. This is is not a bug; it is our first research task.
4. Phase 1 MVP Definition (The "What")
In Scope

     Smartphone-First Frontend: PWA or cross-platform native (React Native/Flutter). Hard requirements: camera, microphone, hands-free-friendly UI. Desktop is secondary.
     Multimodal Input Stack:
        Voice: Local Whisper for speech-to-text (privacy, latency, noisy factory floors).
        Vision: Photo/video analysis for part ID, visible damage, and error code reading.
        Text: Freeform symptom description.
     Scoped Document Intelligence (RAG):
        Ingestion pipeline flexible enough for pristine PDFs, scanned paper copies, and eventually expert voice memos.
        IBM Docling as the parser of choice for complex industrial layouts (tables, schematics).
        Flat vector store (Qdrant, Chroma, or Milvus). Knowledge graphs are deferred.
     Guided Diagnostic Conversation: The agent asks clarifying questions and proposes ranked hypotheses. The UI is a dialogue, not a search results page.
     Verified Completion Loop: Technician marks steps complete. The system logs the final state (photo confirmation preferred). This creates the critical action-perception-reward trace.
     Escalation Telemetry: When confidence is low, route to human expert. Log why the agent failed.

Explicitly Out of Scope (Deferred to Phase 2+)

    OPC-UA / MQTT / PLC integration
    Knowledge graphs (Memgraph)
    Multi-agent orchestration
    AR overlays (RealWear, Vision Pro)
    Predictive maintenance / sensor fusion
    Full spare-parts ERP integration with automated ordering

5. The Documentation Risk: Knowledge Archaeology

The unanimous view across all advisors: The documentation situation is your biggest unmitigated risk.

German SME machinery is a nightmare of entropy:

    Machines from the 1980s–90s with paper manuals never digitized.
    Scanned PDFs that are effectively images.
    Proprietary PLC error codes with no public documentation.
    Knowledge that exists only in the head of a technician who retired last Tuesday.

Therefore: Phase 1 is not purely an engineering sprint. It contains a research work package to characterize the documentation baseline for the chosen machine family. We must answer:

    "What is the realistic corpus of retrievable knowledge for this machine, and what percentage of fault cases can be covered by it?"

The RAG system must be architected as a flexible ingestion pipeline, not a pristine vector database. It should handle:

    Good PDFs → Docling → structured chunks.
    Bad scans → OCR → loose text.
    Expert voice recordings → transcription → heuristic tagging.

If the answer is "20% of faults are documented, 80% are tribal knowledge," our product strategy shifts toward elicitation and capture (interviewing experts, structuring their speech) rather than pure retrieval.
6. Tech Stack Consensus

There is strong alignment across all viewpoints. Here is the consolidated stack:
Layer
	
Technology
	
Rationale
Frontend
	
React Native, Flutter, or Next.js PWA
	
Must maximize camera/mic access. Decision deferred pending prototype needs.
Backend API
	
Python + FastAPI
	
Industry standard, excellent async support for streaming
Agent Logic
	
LangGraph or lightweight FastAPI loop
	
Gives structure to reasoning without premature multi-agent complexity
Vision + Reasoning
	
Cloud multimodal LLM (Claude 3.5/4V, GPT-4o) + local fallback
	
Accuracy first; edge models for simple/sensitive cases
Speech
	
Whisper (local/edge)
	
Latency and privacy on factory floors
Document Parsing
	
Docling (IBM)
	
Purpose-built for complex industrial PDFs
Vector Store
	
Qdrant, Chroma, or Milvus
	
Fast, on-premise friendly for SME privacy concerns
Data Store
	
PostgreSQL + object storage (S3/minio)
	
Case traces, images, session logs
Orchestration
	
Docker Compose / k8s on Edge Server
	
Latency requirements rule out pure cloud for some deployments
 
  
 

Key architectural decision: Hybrid cloud/edge is accepted, but the default assumption for Phase 1 is cloud-first reasoning with local preprocessing (Whisper on device, image compression on device). We only move LLM inference to the edge if a specific SME customer demands it.
7. Data Strategy: The Bridge to Embodiment

Every solved case must generate a structured trace of this form:
 
     
 
 
1
2
3
4
5
6
Visual State (image) 
  → Symptom (text/voice) 
  → Agent Hypothesis (reasoning chain) 
  → Proposed Action (step sequence) 
  → Technician Verification (image/text confirmation) 
  → Outcome (success / escalation / failure)
 
 

This is not "logging." This is embodied pre-training data. The robot of 2030 will need to know:

    What does a cracked bearing look like?
    Given that visual state, what is the first motor action?
    How does the state change after that action?

We instrument for this from day one. The Learning Agent is not a separate microservice; it is a schema and a pipeline that transforms every session into a training example.
8. Implications for Our Three Spec Documents

This synthesis directly maps to our constitutional files:
Mission.md

    Anchors on the German SME competence bridge.
    Defines the dual-use mission: human utility today, robot training tomorrow.
    Locks the success metric: ≥40% time-to-fix reduction for non-experts.
    Frames Phase 1 as "Grounded Cognition" — reducing cognitive load for humans while capturing structured physical knowledge for machines.

Techstack.md

    Centralizes the API contract spec (payload schema, streaming protocol, versioning).
    Defines the monolithic core + tools architecture with clear interfaces.
    Details the chaos-tolerant ingestion pipeline for documentation.
    Justifies the hybrid cloud/edge stack and defers edge-only deployments.
    Specifies the data schema for training traces.

Roadmap.md

    Organized around validated learning milestones, not feature checklists.
    Phase 1 ends only when: A non-expert technician has used the system on a real fault, and time-to-fix was measurably reduced.
    Contains explicit "Do Not Build" gates to prevent scope creep.
    Maps the path: Grounded Cognition → Closed-Loop Verification → Embodied Transfer.

9. Unresolved Decisions (Action Required)

Before we draft the specs, we must lock the following:

     Machine Family Selection: Do we have a candidate? (e.g., CNC-Drehmaschinen, Verpackungsanlagen, Spritzgussmaschinen?) If not, what is the process to select one within the next 2–3 weeks?
     SME Access: Do we have a pilot SME or a machine owner willing to let us observe the current repair process? Even one session would anchor the UX narrative.
     Frontend Commitment: Are we leaning native (Flutter/React Native) or PWA? This affects camera API assumptions.
     Agent Framework Depth: LangGraph gives us graph-based reasoning traces (useful for debugging), but adds complexity. Are we committed to it, or do we prototype with pure FastAPI + instructor / outlines first?





# Further Considerations for the Project: 

- We do have a specific style of code in mind. 
    We want to consider pep8 and use ruff and black to enforce that
    Further we want to have minimalistic code, no unnecessary comments, that are not absolutely needed. And the definitions and initializations of the components should be as minimalistic, as possible. We want to have really pythonic code without bloatware. no unnecessary abstraction and defensive overenginering with try and catch blocks everywhere. 
    And no Docstrings for basic and self expanatory functions.

- 