# ⚖️ The Historical Court

## Overview
**The Historical Court** is an agentic workflow system designed to evaluate historical figures and events through a multi-perspective lens. By employing biased AI historians and an impartial arbiter, the system simulates a trial to reach a balanced, evidence-based verdict on complex historical topics.

This project serves as a demonstration of modern AI engineering principles, specifically focusing on how to manage multi-agent systems with structured workflows and tool integration.

### Key AI Engineering Concepts
- **🎭 Orchestration**: Managing a stateful, multi-round loop between three specialized agents.
- **⚡ Parallelism**: Utilizing `asyncio.gather` to execute research tasks concurrently, significantly reducing latency.
- **💾 State Management**: Maintaining a centralized `CourtState` to track evidence, feedback, and trial progress.
 **🛠️ Tool Use (Function Calling)**: Empowering agents to interact with external APIs (Wikipedia) and control the workflow (loop termination) via Google ADK.

---

## 🏗️ Architecture
    - `google-adk`: Powering the LLM agents (Gemini) through ADK.
    - `aiohttp`: For factual research via Wikipedia API.
    - `asyncio`: For parallel execution.
flowchart TD
    subgraph Input
        U[User Input] --> T[Topic Selection]
    end
    
    subgraph Initialization
        T --> S[CourtState Initialization]
        S --> |topic, round_count=0| P
    end
    
    subgraph Parallel_Execution[Parallel Research Phase]
        P{asyncio.gather}
        P --> A[Agent A - Admirer]
        P --> B[Agent B - Critic]
        A --> |search_wikipedia| WA[Wiki Tool - Positive Query]
        B --> |search_wikipedia| WB[Wiki Tool - Critical Query]
        WA --> |pos_data| SM[State Merge]
        WB --> |neg_data| SM
    end
    
    subgraph Trial_Phase[The Trial]
        SM --> J[Agent C - Judge]
        J --> D{Decision}
        D --> |REJECT + feedback| INC[Increment Round]
        INC --> RC{round_count >= 3?}
        RC --> |No| P
        RC --> |Yes| FT[Forced Termination]
        D --> |ACCEPT| EX[exit_loop - verdict]
    end
    
    subgraph Output
        EX --> V[Generate Verdict File]
        FT --> V
        V --> F[verdict.txt saved to output/]
    end
```

---

## ✨ Features
- **Parallel Agent Execution**: Research tasks for both the Admirer and Critic are launched simultaneously using `asyncio.gather`, demonstrating efficient resource utilization.
- **Function Calling**: Agents use structured tool calls to search Wikipedia and the Judge uses a specific tool to signal trial completion with a structured verdict.
- **Structured State Management**: A centralized state object tracks the history of the trial, ensuring consistency across multiple rounds of investigation.
- **Wikipedia Integration**: Real-time factual grounding through a specialized Wikipedia API wrapper.

---

## 👥 Agent Profiles
The system consists of three distinct agents, each with a specialized role and persona:

| Agent | Role | Responsibility |
|-------|------|----------------|
| **⚖️ The Judge** | Impartial Arbiter | Evaluates evidence, provides feedback for refinement, and renders the final verdict. |
| **🎭 The Admirer** | Positive Historian | Focuses on achievements, innovations, and positive legacies using a favorable lens. |
| **📜 The Critic** | Critical Historian | Investigates controversies, failures, and negative impacts to ensure historical accountability. |

> For more details on prompts and agent configurations, see [AGENT_PROFILES.md](docs/AGENT_PROFILES.md).

---

## 🚀 Installation

```bash
# Clone the repository
git clone <repo-url>
cd historical-court

# Install dependencies
pip install -r requirements.txt

# Set API key
export GOOGLE_API_KEY='your-api-key'
```

---

## 📖 Usage
Run the main script with the name of a historical figure or event as a single argument:

```bash
python main.py "Napoleon Bonaparte"
python main.py "Julius Caesar"
python main.py "The French Revolution"
```

The system will execute the trial and save a detailed verdict report in the `output/` directory.

---

## 📝 Example Run Log
Below is a simulation of the system's output during a typical trial:

```text
=== Round 1 ===
INFO - Admirer: Researching achievements of Napoleon Bonaparte...
INFO - Critic: Researching controversies of Napoleon Bonaparte...
INFO - Judge: Evaluating evidence...
INFO - Trial REJECTED - Feedback: The Admirer needs more details on civil reforms (Napoleonic Code), and the Critic should investigate the reinstatement of slavery in colonies.

=== Round 2 ===
INFO - Admirer: Researching Napoleonic Code and legal reforms...
INFO - Critic: Researching 1802 reinstatement of slavery...
INFO - Judge: Evaluating evidence...
INFO - Trial ACCEPTED - Generating verdict

FINAL VERDICT
Napoleon Bonaparte is a figure of immense contradiction... [Summary of legal legacy vs. human cost]
Verdict saved to output/verdict_napoleon_bonaparte_20240203_192200.txt
```

---

## 🛠️ Technical Details
- **Python Version**: 3.10+
- **Core Dependencies**:
    - `google-adk`: Powering the LLM agents (Gemini) through ADK.
    - `aiohttp`: For factual research via Wikipedia API.
    - `asyncio`: For parallel execution.
- **Environment Variables**:
  - `GOOGLE_API_KEY`: Required for Gemini API access.

---

## 📂 Project Structure
- [`main.py`](main.py): The entry point and primary orchestrator of the trial loop.
- [`agents/`](agents/): Contains the logic, personas, and prompts for the three AI agents.
- [`utils/`](utils/): Core utilities including the Wikipedia tool and state management.
- [`docs/`](docs/): Detailed technical documentation and architecture diagrams.
- [`output/`](output/): Directory where final trial verdicts are stored as text files.
- [`requirements.txt`](requirements.txt): List of necessary Python packages.

---

## 📄 License & Credits
- **Educational Use**: This project is designed for educational purposes in the field of AI Engineering and Computer Engineering.
- **Authorship**: Created by Tanawat Sombatkamrai 663040117-7
