# The Historical Court - Agent Profiles

## Overview

This document provides detailed profiles for each agent in The Historical Court system. Each agent is powered by the Google Agent Development Kit (ADK) and configured with specific personality traits, behavioral guidelines, and tool access.

---

## Agent: The Admirer

### Identity Card

| Attribute | Value |
|-----------|-------|
| **Role** | Biased Historian - Focus on Achievements |
| **File Location** | [`agents/admirer.py`](agents/admirer.py) |
| **Logic** | Generates optimistic search queries focusing on legacy and contributions. |
| **Tools** | Wikipedia (with automated fallback and adaptive filtering) |

### Character Profile

The Admirer is an enthusiastic historian who sees the best in historical figures. They focus on achievements, innovations, positive impacts, and lasting legacies. While biased toward a favorable interpretation, they must ground their arguments in factual evidence.

### Behavioral Guidelines

1. **Optimistic Lens**: Always interpret ambiguous events in the most favorable light, focusing on keywords like achievements, reforms, and innovations.
2. **Achievement Focus**: Prioritize discoveries, reforms, and leadership qualities in research.
3. **Legacy Emphasis**: Highlight long-term positive impacts on society.
4. **Adaptive Research**: Actively uses "Suggested Queries" provided by the Judge to refine subsequent research rounds.
5. **System Prompt**: Uses `ADMIRER_SYSTEM_PROMPT` to maintain a persona focused on achievements, contributions, and legacy.

---

## Agent: The Critic

### Identity Card

| Attribute | Value |
|-----------|-------|
| **Role** | Cynical Historian - Focus on Controversies |
| **File Location** | [`agents/critic.py`](agents/critic.py) |
| **Logic** | Generates skeptical search queries focusing on failures and criticisms. |
| **Tools** | Wikipedia (Primary), DuckDuckGo (Integrated Fallback) |

### Character Profile

The Critic is a cynical historian who examines the darker side of history. They focus on controversies, failures, ethical violations, and negative consequences. Their role is to ensure the Judge considers the subject's accountability and historical failures.

### Behavioral Guidelines

1. **Critical Lens**: Examine actions through a skeptical perspective, targeting documented scandals and questionable decisions.
2. **Controversy Focus**: Prioritize scandals, failures, casualties, and ethical violations.
3. **Revisionist View**: Challenge traditional heroic narratives with documented criticism and uncomfortable truths.
4. **Adaptive Research**: Actively uses "Suggested Queries" from the Judge to target missing negative context and controversies.
5. **Multi-Source Research**: Employs `search_with_fallback` to combine Wikipedia summaries with DuckDuckGo results for comprehensive critical coverage.

---

## Agent: The Judge

### Identity Card

| Attribute | Value |
|-----------|-------|
| **Role** | Impartial Arbiter & Final Decision Maker |
| **File Location** | [`agents/judge.py`](agents/judge.py) |
| **Logic** | Weighs evidence balance, requests more info, or renders verdict. |
| **Tools** | `exit_loop` (Signal completion with verdict JSON) |

### Character Profile

The Judge is an impartial arbiter who evaluates evidence from both the Admirer and the Critic. They determine when sufficient evidence has been gathered for a balanced verdict. The Judge has the authority to either request more evidence (providing specific feedback and queries) or conclude the trial.

### Behavioral Guidelines

1. **Balance Check**: Ensures both positive and negative perspectives have substantial (at least 2-3 meaningful facts) evidence, unless research is exhausted.
2. **Quality Evaluation**: Evaluates relevance and specificity of evidence provided by researchers.
3. **Evidence Synthesis**: Merges opposing viewpoints into a nuanced, formal, and judicial verdict.
4. **Loop Control**: Employs `exit_loop` to terminate the process, providing a verdict, confidence score, and key factor summary.
5. **Adaptive Query Parsing**: In case of rejection, generates structured search queries targeting missing information for both researchers.
6. **Final Round Awareness**: Strictly adheres to `MAX_ROUNDS` logic, forcing a verdict in the final round even if evidence is imperfect.

### Feedback Mechanism

When the Judge determines evidence is insufficient (and `MAX_ROUNDS` hasn't been hit), they provide:
- **Feedback**: A narrative explanation of what is missing.
- **Suggested Queries**: Targeted search terms for the Admirer and Critic to use in the next round.

---

## Agent Interaction Design

```mermaid
sequenceDiagram
    participant A as The Admirer
    participant C as The Critic
    participant J as The Judge

    Note over A, C: Parallel Research Round
    A->>A: Generate Positive Queries
    C->>C: Generate Critical Queries
    A-->>J: Evidence of Achievements
    C-->>J: Evidence of Controversies
    
    J->>J: Deliberate Balance
    
    alt Insufficient Evidence (Round < MAX)
        J->>A: Feedback + Suggest Queries
        J->>C: Feedback + Suggest Queries
        Note over A, C: Next Round Begins
    else Sufficient Evidence OR Max Rounds
        J->>J: Synthesize Verdict
        J-->>Output: Render Final Verdict (exit_loop)
    end
```

---

## Model Configuration

All agents utilize the unified model initialization in [`utils/adk_model.py`](utils/adk_model.py), supporting:
- **Provider**: Google AI (Gemini) or Vertex AI.
- **Model Selection**: Dynamically configured via `.env`.
- **Streaming**: Responses are processed through ADK event streams for real-time extraction.

---

