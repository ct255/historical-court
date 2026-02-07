
import time
from utils.display import TrialDisplay
from agents.judge import JudgeDecision

def test_display():
    print("Testing Rich Display...")
    display = TrialDisplay(show_steps=True)
    
    # 1. Header
    display.show_header("Napoleon Bonaparte", "gemini-2.0-flash-exp")
    time.sleep(0.5)
    
    # 2. Round Start
    display.show_round_start(1, 3)
    time.sleep(0.5)
    
    # 3. Agent Actions
    display.show_agent_action("Admirer", "Searching for victories...", is_loading=True)
    time.sleep(0.5)
    display.show_agent_action("Critic", "Searching for defeats...", is_loading=True)
    time.sleep(0.5)
    
    # 4. Evidence
    display.show_evidence("Admirer", "Battle of Austerlitz", "Napoleon won decisively against the Third Coalition.")
    display.show_evidence("Critic", "Invasion of Russia", "The Grande Armée was decimated by winter and scorched earth tactics.")
    time.sleep(0.5)
    
    # 5. Judge Deliberation
    display.show_judge_deliberation("Evidence is conflicting. Need more details on his domestic policies.")
    
    # 6. Verdict
    decision = JudgeDecision(
        accepted=True,
        verdict="Napoleon was a complex figure...",
        confidence="High",
        summary={"military": "genius", "politics": "autocratic"}
    )
    
    display.show_verdict("Napoleon Bonaparte", "Napoleon was a military genius but an autocratic ruler.", decision)

if __name__ == "__main__":
    test_display()
