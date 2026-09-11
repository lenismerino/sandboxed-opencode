"""Session lifecycle management and auto-rotation for long unattended tasks."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from harness.context import ContextManager


@dataclass
class MilestoneRecord:
    id: str
    title: str
    status: str  # 'pending', 'in_progress', 'completed', 'blocked'
    details: str = ""
    updated_at: float = field(default_factory=time.time)


@dataclass
class SessionState:
    session_id: str
    task_id: str
    goal: str
    session_index: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    milestones: List[Dict[str, Any]] = field(default_factory=list)
    modified_files: List[str] = field(default_factory=list)
    cumulative_prompt_tokens: int = 0
    cumulative_completion_tokens: int = 0
    cumulative_reasoning_tokens: int = 0
    handoff_summary: str = ""


class SessionManager:
    """Manages session persistence, checkpointing, and auto-rotation across long tasks.

    Allows the agent to work unattended for hours across context limits by automatically
    saving state, distilling key architectural knowledge into a structured handoff,
    and spinning up fresh sessions with full token headroom.
    """

    def __init__(
        self,
        project_dir: Optional[Path] = None,
        sessions_dir: Optional[Path] = None,
    ) -> None:
        self.project_dir = project_dir or Path(os.environ.get("PROJECTS_ROOT_PATH", "/home/agent/projects"))
        self.sessions_dir = sessions_dir or (self.project_dir / ".cache" / "sessions")
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.current_state: Optional[SessionState] = None

    def start_session(
        self,
        goal: str,
        task_id: Optional[str] = None,
        session_index: int = 1,
    ) -> SessionState:
        """Initialize a new task session."""
        t_id = task_id or f"task_{int(time.time())}"
        s_id = f"{t_id}_s{session_index:03d}"
        self.current_state = SessionState(
            session_id=s_id,
            task_id=t_id,
            goal=goal,
            session_index=session_index,
        )
        self.save_current_state()
        return self.current_state

    def save_current_state(self) -> Path:
        """Persist current session state to disk."""
        if not self.current_state:
            raise ValueError("No active session to save")
        self.current_state.updated_at = time.time()
        file_path = self.sessions_dir / f"{self.current_state.session_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(asdict(self.current_state), f, indent=2)
        return file_path

    def record_milestone(self, title: str, status: str, details: str = "") -> None:
        """Record or update a milestone in the current session."""
        if not self.current_state:
            return
        # Check if already present
        for m in self.current_state.milestones:
            if m["title"] == title:
                m["status"] = status
                m["details"] = details
                m["updated_at"] = time.time()
                self.save_current_state()
                return

        m_record = MilestoneRecord(
            id=f"m_{len(self.current_state.milestones) + 1}",
            title=title,
            status=status,
            details=details,
        )
        self.current_state.milestones.append(asdict(m_record))
        self.save_current_state()

    def record_modified_files(self, file_paths: List[str]) -> None:
        """Add files modified during the session."""
        if not self.current_state:
            return
        combined = set(self.current_state.modified_files) | set(file_paths)
        self.current_state.modified_files = sorted(combined)
        self.save_current_state()

    def synthesize_handoff(
        self,
        context: ContextManager,
        next_goal: Optional[str] = None,
    ) -> str:
        """Generate a concise, high-signal handoff document for the next session."""
        stats = context.get_stats()
        milestones = self.current_state.milestones if self.current_state else []
        modified_files = self.current_state.modified_files if self.current_state else []
        task_goal = self.current_state.goal if self.current_state else "Autonomous Engineering Task"

        # Format milestones
        completed = [m["title"] for m in milestones if m.get("status") == "completed"]
        in_progress = [m["title"] for m in milestones if m.get("status") == "in_progress"]
        pending = [m["title"] for m in milestones if m.get("status") == "pending"]

        completed_str = ", ".join(completed) if completed else "Discovery & setup initialized."
        in_progress_str = ", ".join(in_progress) if in_progress else "None currently active."
        pending_str = ", ".join(pending) if pending else "Remaining plan verification."
        files_str = ", ".join(modified_files[:10]) if modified_files else "Inspected codebase."

        handoff = (
            f"# Executive Session Handoff (Session {self.current_state.session_index if self.current_state else 1})\n"
            f"**Overarching Goal**: {task_goal}\n\n"
            f"### Accomplishments So Far\n"
            f"- **Completed Milestones**: {completed_str}\n"
            f"- **Key Files Modified**: {files_str}\n"
            f"- **Context Compacted at**: {stats['estimated_tokens']} tokens\n\n"
            f"### Current Working State\n"
            f"- **Active Task**: {in_progress_str}\n"
            f"- **Upcoming Milestones**: {pending_str}\n\n"
            f"### Directive for This Session\n"
            f"{next_goal or 'Proceed immediately with the next pending milestone without repeating completed work.'}"
        )
        return handoff

    def rotate_session(
        self,
        context: ContextManager,
        next_goal: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> ContextManager:
        """Archive current session and initialize a fresh ContextManager with handoff context.

        Args:
            context: The outgoing ContextManager.
            next_goal: Specific directives for the next phase.
            system_prompt: System prompt for the new session.

        Returns:
            A fresh ContextManager containing only system prompt, initial goal, and handoff.
        """
        if not self.current_state:
            self.start_session(goal="Autonomous Task")

        # 1. Synthesize handoff
        handoff_doc = self.synthesize_handoff(context, next_goal)
        assert self.current_state is not None
        self.current_state.handoff_summary = handoff_doc

        # 2. Persist checkpoint of outgoing session
        self.save_current_state()

        # 3. Increment session index
        new_index = self.current_state.session_index + 1
        new_state = SessionState(
            session_id=f"{self.current_state.task_id}_s{new_index:03d}",
            task_id=self.current_state.task_id,
            goal=self.current_state.goal,
            session_index=new_index,
            milestones=self.current_state.milestones,
            modified_files=self.current_state.modified_files,
            cumulative_prompt_tokens=self.current_state.cumulative_prompt_tokens,
            cumulative_completion_tokens=self.current_state.cumulative_completion_tokens,
            cumulative_reasoning_tokens=self.current_state.cumulative_reasoning_tokens,
        )
        self.current_state = new_state
        self.save_current_state()

        # 4. Initialize fresh ContextManager
        fresh_context = ContextManager(
            max_context_length=context.max_context_length,
            reserved_completion_tokens=context.reserved_completion_tokens,
            prune_threshold_tokens=context.prune_threshold_tokens,
            preserved_initial_turns=context.preserved_initial_turns,
            recent_turns_budget=context.recent_turns_budget,
        )

        sys_p = system_prompt or (
            context.messages[0]["content"] if context.messages else "You are an autonomous engineering agent."
        )
        fresh_context.add_message("system", sys_p)
        fresh_context.add_message(
            "user",
            f"Continuing unattended task execution.\n\n{handoff_doc}",
        )

        return fresh_context

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all saved sessions sorted by modification time."""
        results = []
        for p in self.sessions_dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    results.append(data)
            except Exception:
                continue
        results.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
        return results
