# The Historical Court - System Architecture

## 1. Executive Summary

**The Historical Court** is an agentic workflow system built with the Google Agent Development Kit (ADK) that demonstrates key concepts in modern AI engineering:
- **Orchestration**: Centralized management of multiple AI agents in a coordinated state-machine workflow.
- **Parallelism (Optional)**: Concurrent execution of research agents using `asyncio.gather` when enabled.
- **State Management**: Centralized state with the `CourtState` dataclass, including content deduplication.
- **Tool Use**: Function calling for Wikipedia and DuckDuckGo search, and loop control via the Judge.
- **Multi-Provider Support**: Seamlessly switching between Gemini API and Vertex AI.

The system simulates a historical trial where two biased historians (The Admirer and The Critic) research a topic from opposing viewpoints, while an impartial Judge evaluates their findings to produce a balanced verdict.

---

## 2. System Overview Diagram

```mermaid
flowchart TD
    subgraph Input
        U[User Input] --> T[Topic Selection]
    end
    
    subgraph Initialization
        T --> S[CourtState Initialization]
        S --> |topic, round_count=0| P
    end
    
    subgraph Parallel_Execution[Research Phase (Optional Parallelism)]
        P{asyncio.gather (optional)}
        P --> A[Agent: Admirer]
        P --> B[Agent: Critic]
        A --> |search| WT[Wikipedia / DuckDuckGo]
        B --> |search| WT
        WT --> |Results| A
        WT --> |Results| B
        A --> |Evidence| SM[State Update & Deduplication]
        B --> |Evidence| SM
    end
    
    subgraph Trial_Phase[The Trial / Deliberation]
        SM --> J[Agent: Judge]
        J --> D{Decision}
        D --> |REJECT + suggested_queries| INC[Increment Round]
        INC --> RC{round_count >= MAX_ROUNDS?}
        RC --> |No| P
        RC --> |Yes| FT[Forced Termination]
        D --> |ACCEPT| EX[exit_loop Tool]
    end
    
    subgraph Output
        EX --> V[Generate Verdict File]
        FT --> V
        V --> F[verdict_*.txt saved to output/]
    end
```

---

## 3. Component Architecture

### 3.1 Project Structure

```
historical-court/
├── main.py              # Entry point - Centralized orchestration loop
├── agents/
│   ├── __init__.py
│   ├── admirer.py       # Biased Historian (Pros) - Optimistic queries
│   ├── critic.py        # Cynical Historian (Cons) - Critical queries
│   └── judge.py         # Impartial Arbiter - Evaluation and exit logic
├── utils/
│   ├── __init__.py
│   ├── adk_helpers.py   # ADK stream extraction utilities
│   ├── adk_model.py     # Gemini/Vertex AI model initialization
│   ├── config.py        # Env var management (python-dotenv)
│   ├── ddg_tool.py      # DuckDuckGo search implementation
│   ├── display.py       # Rich CLI presentation
│   ├── providers.py     # LLM provider abstractions
│   ├── search.py        # Search orchestration with Wikipedia and DDG fallback
│   ├── state.py         # CourtState management and TrialStatus enum
│   └── wiki_tool.py     # Wikipedia search with exclusion patterns & adaptive filtering
├── docs/
│   ├── ARCHITECTURE.md  # This document
│   └── AGENT_PROFILES.md
├── output/              # Final verdict storage (verdict_*.txt)
├── requirements.txt     # Dependencies (google-adk, langchain, rich, etc.)
└── README.md            # Quickstart and overview
```

### 3.2 Component Descriptions

| Component | File(s) | Responsibility |
|-----------|---------|----------------|
| **Orchestrator** | `main.py` | Implementation of the trial state machine and async task management. |
| **Admirer Agent** | `agents/admirer.py` | Research focused on achievements and positive legacy. |
| **Critic Agent** | `agents/critic.py` | Research focused on controversies and failures. |
| **Judge Agent** | `agents/judge.py` | Quality control, balance evaluation, and final verdict synthesis. |
| **State Manager** | `utils/state.py` | Tracks topic, evidence, rounds, and deduplicates content using MD5 hashes. |
| **Research Tools** | `utils/wiki_tool.py`, `utils/search.py` | Wikipedia primary search; Critic uses DuckDuckGo fallback. |
| **Display Engine** | `utils/display.py` | Rich-based CLI visualization with panels and spinners. |

---

## 4. State Machine

The system transitions through a defined set of states managed in the `main.py` loop and enforced by `CourtState` (`utils/state.py`):

1. **IDLE**: Initial state before creation.
2. **INITIALIZED**: Topic received, `CourtState` created.
3. **RESEARCHING**: Admirer and Critic gather evidence.
4. **DELIBERATING**: Judge reviews synthesized evidence.
5. **REJECTED**: Judge provides feedback and "Suggested Queries" for the next round.
6. **ACCEPTED**: Judge calls `exit_loop` tool with a final verdict.
7. **FORCED_TERMINATION**: Reached if `MAX_ROUNDS` (default 3) is hit without a consensus verdict.
8. **GENERATING_VERDICT**: Internal state while finalizing and saving the verdict file.
9. **COMPLETED**: Final terminal state once verdict is saved and displayed.

### 4.1 Flow Transitions
- `RESEARCHING` -> `DELIBERATING`
- `DELIBERATING` -> `ACCEPTED` | `REJECTED` | `FORCED_TERMINATION`
- `ACCEPTED` | `FORCED_TERMINATION` -> `GENERATING_VERDICT` -> `COMPLETED`

---

## 5. Data Management & Deduplication

### 5.1 CourtState
The `CourtState` dataclass (`utils/state.py`) is the source of truth, containing:
- `topic`: The historical subject.
- `pos_data` / `neg_data`: Evidence lists from Admirer and Critic.
- `evidence_hashes`: A set of MD5 hashes for content deduplication.
- `seen_titles_admirer` / `seen_titles_critic`: Per-agent title tracking to avoid redundant searches.
- `suggested_queries_admirer` / `suggested_queries_critic`: Targeted queries from the Judge.

### 5.2 Deduplication Logic
To maintain quality and reduce costs, the system employs a two-layer deduplication strategy in `main.py`:
- **Hash-based**: An MD5 hash of the evidence text (`_evidence_hash`) is stored in `evidence_hashes`. If a new finding generates a known hash, it is discarded.
- **Title-based**: `main.py` extracts the Wikipedia article title from the evidence (using the `Page: <Title>` format). Titles are stored in `seen_titles_admirer` or `seen_titles_critic`. If a title has been seen by the same agent in a previous round, the evidence is skipped even if the text content differs slightly.

### 5.3 Wikipedia Exclusion & Filtering
The `wiki_tool.py` implements advanced filtering to ensure historical relevance:
- **Exclusion Patterns**: Regex patterns filter out entertainment media (e.g., `(film)`, `(video game)`, `(fictional character)`).
- **Adaptive Filtering**: If a `focus_term` (the topic) is provided, results must contain the term in the title or summary.
- **Content Detection**: An "entertainment page" detector (`_is_entertainment_page`) scans summaries for phrases like "is a film" or "starring" to avoid false positives.

---

## 6. Tooling

### 6.1 Research Tools
- **Wikipedia**: Primary source via `utils/wiki_tool.py`.
- **DuckDuckGo**: Fallback used by the Critic when Wikipedia returns no results.

### 6.2 Orchestration Tools
- **exit_loop**: The Judge's mechanism to stop the trial. It returns a structured JSON payload with `verdict`, `confidence`, and optional `summary`.

---

## 7. Configuration & Multi-Provider Support

The configuration system is centralized in `utils/config.py` and `utils/providers.py`:
- **Env Var Management**: `get_env` and `require_env` utilities wrap `os.environ` access with optional stripping and defaults.
- **Providers**: The `AdkProvider` class handles agent and runner creation, defaulting to Gemini models.
- **Model Support**: Defaults to `gemini-2.5-flash` via `get_model_name()`.
- **Vertex AI**: Automatic detection via `GOOGLE_APPLICATION_CREDENTIALS` or explicit flags in `main.py`.

---

## 8. Technical Requirements

- **Python 3.10+**
- **google-adk**: For Agent/Tool framework.
- **langchain-community**: Powering the Wikipedia/DDG integrations.
- **rich**: For terminal UI.
- **python-dotenv**: For configuration.

---
