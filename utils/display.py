from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.layout import Layout
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.theme import Theme
from rich.style import Style
from typing import Optional, List, Any
import time

# Custom theme for the court
court_theme = Theme({
    "admirer": "green",
    "critic": "red",
    "judge": "blue bold",
    "neutral": "white",
    "highlight": "cyan",
    "header": "bold magenta",
    "warning": "yellow",
    "step": "bold white on blue",
})

class TrialDisplay:
    """
    Handles rich console output for the Historical Court.
    """
    
    def __init__(self, show_steps: bool = True):
        self.console = Console(theme=court_theme)
        self.show_steps = show_steps
        
    def show_header(self, topic: str, model_name: str):
        """Display the initial trial header."""
        if not self.show_steps:
            return
            
        grid = Panel(
            Text.assemble(
                ("🏛️  THE HISTORICAL COURT  🏛️\n", "header"),
                (f"\nTopic: ", "neutral"), (topic, "highlight"),
                (f"\nModel: ", "neutral"), (model_name, "highlight"),
                justify="center"
            ),
            border_style="judge",
            padding=(1, 2)
        )
        self.console.print(grid)
        self.console.print()

    def show_round_start(self, round_num: int, max_rounds: int):
        """Display the start of a new round."""
        if not self.show_steps:
            return
            
        self.console.rule(f"[bold]Round {round_num} of {max_rounds}[/bold]")
        self.console.print()

    def show_agent_action(self, agent_name: str, action: str, is_loading: bool = False):
        """
        Display an agent's current action.
        
        Args:
            agent_name: 'Admirer', 'Critic', or 'Judge'
            action: Description of what they are doing
            is_loading: Whether to show a spinner (not implemented in simple print mode)
        """
        if not self.show_steps:
            return
            
        style = agent_name.lower()
        if style not in ["admirer", "critic", "judge"]:
            style = "neutral"
            
        icon = {
            "Admirer": "📢",
            "Critic": "🔍",
            "Judge": "⚖️"
        }.get(agent_name, "🤖")
        
        self.console.print(f"[{style}]{icon} {agent_name}:[/] {action}")

    def show_evidence(self, agent_name: str, query: str, findings: str):
        """Display evidence gathered by an agent."""
        if not self.show_steps:
            return

        style = "green" if agent_name == "Admirer" else "red"
        border_style = style
        
        # Truncate findings for display if too long
        display_findings = findings
        if len(display_findings) > 500:
            display_findings = display_findings[:497] + "..."

        content = Text.assemble(
            (f"Query: {query}\n\n", "bold"),
            (display_findings, "neutral")
        )

        panel = Panel(
            content,
            title=f"{agent_name}'s Evidence",
            border_style=border_style,
            expand=False
        )
        self.console.print(panel)

    def show_judge_deliberation(self, analysis: str):
        """Display the Judge's thought process."""
        if not self.show_steps:
            return
            
        self.console.print(Panel(
            analysis,
            title="⚖️ Judge's Deliberation",
            border_style="judge",
            style="italic"
        ))
        
    def show_verdict(self, topic: str, verdict: str, decision: Any):
        """
        Display the final verdict with full details.
        
        Args:
            topic: The trial topic
            verdict: The text verdict
            decision: The JudgeDecision object (typed as Any to avoid import cycles)
        """
        self.console.print()
        self.console.rule("[bold red]FINAL VERDICT[/bold red]")
        self.console.print()
        
        # Extract confidence and summary if available
        confidence = getattr(decision, 'confidence', 'N/A')
        summary_data = getattr(decision, 'summary', None)
        
        if isinstance(summary_data, dict):
            import json
            summary_str = json.dumps(summary_data, indent=2)
        else:
            summary_str = str(summary_data) if summary_data else "No summary provided."

        # Create a rich layout for the verdict
        verdict_text = Text(verdict, style="bold white")
        
        details_text = Text.assemble(
            ("Confidence Score: ", "bold cyan"), (f"{confidence}/10\n\n", "yellow"),
            ("Key Factors:\n", "bold cyan"), (summary_str, "white")
        )
        
        self.console.print(Panel(
            verdict_text,
            title=f"Verdict: {topic}",
            border_style="judge",
            padding=(1, 2)
        ))
        
        self.console.print(Panel(
            details_text,
            title="Judge's Rationale",
            border_style="blue",
            padding=(1, 2)
        ))
        
    def progress_spinner(self, description: str):
        """Context manager for a loading spinner."""
        if not self.show_steps:
            # Return a dummy context manager if steps are hidden
            class Dummy:
                def __enter__(self): return self
                def __exit__(self, *args): pass
            return Dummy()
            
        return self.console.status(description, spinner="dots")
