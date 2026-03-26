"""
Agent Team Engine V2
====================
Multi-agent collaboration system with parallel execution, custom roles,
nicknames, inter-agent communication, and AI-generated execution plans.

Key improvements over V1:
- Parallel execution within phases
- AI-generated execution plans (Planner agent)
- Unlimited agents per team
- Custom roles and nicknames
- Inter-agent messaging
- Team templates
- Hybrid workflow modes
"""

import logging
import json
import asyncio
import time
import uuid
from typing import Dict, Any, List, Optional, Callable, Coroutine
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ─── Enums ──────────────────────────────────────────────────────────────────────

class WorkflowMode(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    HYBRID = "hybrid"


class MessageType(str, Enum):
    TASK = "task"
    QUESTION = "question"
    ANSWER = "answer"
    FEEDBACK = "feedback"
    REQUEST = "request"
    BROADCAST = "broadcast"
    SYNTHESIS = "synthesis"
    CRITIQUE = "critique"


class AgentStatus(str, Enum):
    IDLE = "idle"
    WAITING = "waiting"
    WORKING = "working"
    COMPLETE = "complete"
    FAILED = "failed"


# ─── Default Capabilities ───────────────────────────────────────────────────────

DEFAULT_CAPABILITIES = {
    "leader": ["plan", "coordinate", "delegate", "synthesize"],
    "researcher": ["research", "search", "gather", "cite"],
    "analyst": ["analyze", "calculate", "code", "visualize"],
    "critic": ["review", "challenge", "evaluate", "suggest"],
    "synthesizer": ["combine", "structure", "write", "summarize"],
    "coder": ["code", "debug", "test", "execute", "sandbox"],
    "writer": ["write", "edit", "proofread", "format"],
    "designer": ["design", "visualize", "layout", "style"],
    "translator": ["translate", "localize", "adapt"],
    "expert": ["advise", "consult", "specialize"],
}

# Default role descriptions (can be overridden)
DEFAULT_ROLE_DESCRIPTIONS = {
    "leader": (
        "You are the Team Leader. Your job is to: "
        "1) Break down the main task into subtasks "
        "2) Assign subtasks to appropriate team members "
        "3) Coordinate the team's work "
        "4) Ensure the final output meets quality standards. "
        "Be concise and directive. Ask other agents specific questions."
    ),
    "researcher": (
        "You are the Researcher. Your job is to: "
        "1) Gather information and data relevant to the task "
        "2) Use web search and knowledge bases when available "
        "3) Provide factual, well-sourced information "
        "4) Flag any gaps in available data. "
        "Be thorough but concise in your findings."
    ),
    "analyst": (
        "You are the Analyst. Your job is to: "
        "1) Analyze data and information provided by the Researcher "
        "2) Run calculations and code in the sandbox when needed "
        "3) Identify patterns, trends, and insights "
        "4) Provide quantitative analysis with numbers. "
        "Be precise and data-driven."
    ),
    "critic": (
        "You are the Critic. Your job is to: "
        "1) Review the team's work for errors and weaknesses "
        "2) Challenge assumptions and identify risks "
        "3) Suggest improvements and alternatives "
        "4) Ensure the final output is rigorous. "
        "Be constructive but thorough in your critique."
    ),
    "synthesizer": (
        "You are the Synthesizer. Your job is to: "
        "1) Combine findings from all team members "
        "2) Create a coherent, well-structured final output "
        "3) Resolve any conflicting information "
        "4) Present the results clearly. "
        "Be clear and comprehensive."
    ),
    "coder": (
        "You are the Coder. Your job is to: "
        "1) Write and execute code in the sandbox "
        "2) Perform data processing and analysis "
        "3) Generate visualizations and outputs "
        "4) Debug any code issues. "
        "Write clean, efficient code and explain what it does."
    ),
    "writer": (
        "You are the Writer. Your job is to: "
        "1) Create well-written content based on research and analysis "
        "2) Ensure clarity, coherence, and proper structure "
        "3) Adapt tone and style to the audience "
        "4) Edit and refine the final output."
    ),
    "designer": (
        "You are the Designer. Your job is to: "
        "1) Create visual concepts and layouts "
        "2) Ensure aesthetic consistency and appeal "
        "3) Provide design recommendations "
        "4) Optimize for user experience."
    ),
    "translator": (
        "You are the Translator. Your job is to: "
        "1) Translate content accurately between languages "
        "2) Preserve meaning and nuance "
        "3) Adapt cultural references appropriately "
        "4) Ensure natural, fluent output in the target language."
    ),
    "expert": (
        "You are the Subject Matter Expert. Your job is to: "
        "1) Provide deep domain expertise "
        "2) Validate technical accuracy "
        "3) Offer specialized insights "
        "4) Guide the team on best practices in your domain."
    ),
}

# Role colors for UI
ROLE_COLORS = {
    "leader": "#FEC00F",
    "researcher": "#3B82F6",
    "analyst": "#10B981",
    "critic": "#EF4444",
    "synthesizer": "#8B5CF6",
    "coder": "#06B6D4",
    "writer": "#F97316",
    "designer": "#EC4899",
    "translator": "#14B8A6",
    "expert": "#6366F1",
}


# ─── Data Classes ────────────────────────────────────────────────────────────────

@dataclass
class AgentConfig:
    """Configuration for a single agent in the team."""
    id: str = ""
    nickname: str = ""
    role: str = "researcher"
    model_id: str = "claude-sonnet-4-20250514"
    provider: str = "anthropic"
    custom_role_desc: str = ""
    instructions: str = ""
    color: str = "#3B82F6"
    capabilities: List[str] = field(default_factory=list)
    can_collaborate_with: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            self.id = f"agent_{uuid.uuid4().hex[:8]}"
        if not self.nickname:
            self.nickname = self.role.replace("_", " ").title()
        if not self.color:
            self.color = ROLE_COLORS.get(self.role, "#6B7280")
        if not self.capabilities:
            self.capabilities = DEFAULT_CAPABILITIES.get(self.role, ["general"])


@dataclass
class AgentMessage:
    """A message between agents or from/to user."""
    id: str = ""
    from_agent_id: str = ""
    to_agent_id: Optional[str] = None  # None = broadcast
    content: str = ""
    message_type: str = MessageType.ANSWER
    requires_response: bool = False
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"msg_{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()


@dataclass
class ExecutionPhase:
    """A phase in the execution plan where agents run in parallel."""
    phase_id: int
    agents: List[str]  # Agent IDs to run in this phase
    description: str = ""
    dependencies: List[int] = field(default_factory=list)
    timeout_seconds: int = 300


@dataclass
class ExecutionPlan:
    """Generated by the Planner agent or workflow mode."""
    phases: List[ExecutionPhase]
    reasoning: str = ""
    workflow_mode: str = WorkflowMode.HYBRID


@dataclass
class AgentResult:
    """Result from a single agent execution."""
    agent_id: str
    nickname: str
    role: str
    content: str
    error: Optional[str] = None
    model_id: str = ""
    provider: str = ""
    elapsed_seconds: float = 0.0
    messages_sent: int = 0
    messages_received: int = 0


# ─── Team Templates ──────────────────────────────────────────────────────────────

TEAM_TEMPLATES = {
    "research_team": {
        "name": "Research Team",
        "description": "A team specialized in deep research tasks",
        "workflow_mode": WorkflowMode.HYBRID,
        "agents": [
            AgentConfig(role="leader", nickname="Lead Researcher", model_id="claude-sonnet-4-20250514", provider="anthropic"),
            AgentConfig(role="researcher", nickname="Data Gatherer", model_id="gpt-4o", provider="openai"),
            AgentConfig(role="researcher", nickname="Source Finder", model_id="claude-sonnet-4-20250514", provider="anthropic"),
            AgentConfig(role="analyst", nickname="Data Analyst", model_id="gpt-4o", provider="openai"),
            AgentConfig(role="writer", nickname="Report Writer", model_id="claude-sonnet-4-20250514", provider="anthropic"),
        ],
    },
    "code_review": {
        "name": "Code Review Team",
        "description": "A team for reviewing and improving code",
        "workflow_mode": WorkflowMode.HYBRID,
        "agents": [
            AgentConfig(role="leader", nickname="Architect", model_id="claude-sonnet-4-20250514", provider="anthropic"),
            AgentConfig(role="coder", nickname="Implementation Expert", model_id="gpt-4o", provider="openai"),
            AgentConfig(role="critic", nickname="Code Reviewer", model_id="claude-sonnet-4-20250514", provider="anthropic"),
            AgentConfig(role="analyst", nickname="Performance Analyst", model_id="gpt-4o", provider="openai"),
        ],
    },
    "creative_team": {
        "name": "Creative Team",
        "description": "A team for content creation",
        "workflow_mode": WorkflowMode.HYBRID,
        "agents": [
            AgentConfig(role="leader", nickname="Creative Director", model_id="claude-sonnet-4-20250514", provider="anthropic"),
            AgentConfig(role="writer", nickname="Content Writer", model_id="gpt-4o", provider="openai"),
            AgentConfig(role="critic", nickname="Editor", model_id="claude-sonnet-4-20250514", provider="anthropic"),
            AgentConfig(role="designer", nickname="Visual Designer", model_id="gpt-4o", provider="openai"),
        ],
    },
    "analysis_team": {
        "name": "Analysis Team",
        "description": "A team for data analysis",
        "workflow_mode": WorkflowMode.PARALLEL,
        "agents": [
            AgentConfig(role="leader", nickname="Lead Analyst", model_id="claude-sonnet-4-20250514", provider="anthropic"),
            AgentConfig(role="analyst", nickname="Statistician", model_id="gpt-4o", provider="openai"),
            AgentConfig(role="analyst", nickname="Data Scientist", model_id="claude-sonnet-4-20250514", provider="anthropic"),
            AgentConfig(role="writer", nickname="Reporter", model_id="gpt-4o", provider="openai"),
        ],
    },
    "debate_team": {
        "name": "Debate Team",
        "description": "A team that explores multiple perspectives",
        "workflow_mode": WorkflowMode.PARALLEL,
        "agents": [
            AgentConfig(role="leader", nickname="Moderator", model_id="claude-sonnet-4-20250514", provider="anthropic"),
            AgentConfig(role="expert", nickname="Proponent", model_id="gpt-4o", provider="openai"),
            AgentConfig(role="critic", nickname="Opponent", model_id="claude-sonnet-4-20250514", provider="anthropic"),
            AgentConfig(role="synthesizer", nickname="Neutral Synthesizer", model_id="gpt-4o", provider="openai"),
        ],
    },
}


# ─── Agent Team V2 ───────────────────────────────────────────────────────────────

class AgentTeamV2:
    """
    Manages a team of AI agents working together on a task.
    Supports parallel execution, inter-agent messaging, and custom configurations.
    """

    def __init__(
        self,
        team_id: str,
        user_id: str,
        agents: List[AgentConfig],
        registry: Any,
        workflow_mode: str = WorkflowMode.HYBRID,
        allow_inter_agent_chat: bool = True,
    ):
        self.team_id = team_id
        self.user_id = user_id
        self.agents: Dict[str, AgentConfig] = {a.id: a for a in agents}
        self.registry = registry
        self.workflow_mode = workflow_mode
        self.allow_inter_agent_chat = allow_inter_agent_chat
        self.messages: List[AgentMessage] = []
        self.shared_context: Dict[str, Any] = {}
        self.agent_status: Dict[str, str] = {a.id: AgentStatus.IDLE for a in agents}
        self.agent_results: Dict[str, AgentResult] = {}
        self.status = "idle"

    def get_agent(self, agent_id: str) -> Optional[AgentConfig]:
        """Get an agent by ID."""
        return self.agents.get(agent_id)

    def get_agents_by_role(self, role: str) -> List[AgentConfig]:
        """Get all agents with a specific role."""
        return [a for a in self.agents.values() if a.role == role]

    def _build_messages_for_agent(
        self,
        agent: AgentConfig,
        task: str,
        phase_context: Dict[str, Any],
    ) -> tuple[List[Dict], str]:
        """Build the message history for a specific agent."""
        # Get role description
        if agent.custom_role_desc:
            role_desc = agent.custom_role_desc
        else:
            role_desc = DEFAULT_ROLE_DESCRIPTIONS.get(
                agent.role,
                f"You are a {agent.role} agent."
            )

        # Build system message with team context
        system_msg = f"You are {agent.nickname}, a {agent.role} on this team."
        
        # Add team roster so agents know who they're working with
        team_roster = "\n\nTeam members:\n"
        for a in self.agents.values():
            if a.id != agent.id:
                team_roster += f"- {a.nickname} ({a.role})\n"
        system_msg += team_roster
        
        system_msg += f"\n{role_desc}"
        
        if agent.instructions:
            system_msg += f"\n\nAdditional instructions: {agent.instructions}"

        # Add capabilities
        if agent.capabilities:
            system_msg += f"\n\nYour capabilities: {', '.join(agent.capabilities)}"
        
        # Add shared context if available
        if self.shared_context:
            system_msg += f"\n\nShared context: {json.dumps(self.shared_context, indent=2)}"

        # Build conversation context
        messages = []

        # Add task
        messages.append({
            "role": "user",
            "content": f"[TASK]: {task}"
        })

        # Add results from ALL previous phases (full context)
        if phase_context.get("previous_results"):
            for result in phase_context["previous_results"]:
                if result.agent_id != agent.id and not result.error:
                    # Truncate very long results to avoid token limits
                    content = result.content[:2000] + "..." if len(result.content) > 2000 else result.content
                    messages.append({
                        "role": "user",
                        "content": f"[{result.nickname} ({result.role})]: {content}"
                    })

        # Add inter-agent messages for this agent
        for msg in self.messages:
            if msg.to_agent_id == agent.id or msg.to_agent_id is None:
                if msg.from_agent_id != agent.id:
                    from_agent = self.get_agent(msg.from_agent_id)
                    from_name = from_agent.nickname if from_agent else msg.from_agent_id
                    messages.append({
                        "role": "user",
                        "content": f"[{from_name}]: {msg.content}"
                    })

        return messages, system_msg

    async def _call_agent(
        self,
        agent: AgentConfig,
        task: str,
        phase_context: Dict[str, Any],
        max_tokens: int = 4096,
        timeout: int = 120,
    ) -> AgentResult:
        """Call a single agent and get its response with timeout."""
        start_time = time.time()
        self.agent_status[agent.id] = AgentStatus.WORKING

        async def _do_call() -> AgentResult:
            provider_obj = self.registry.get_provider(agent.provider)
            if not provider_obj:
                try:
                    provider_obj = self.registry.get_provider_for_model(agent.model_id)
                except Exception:
                    pass

            if not provider_obj:
                return AgentResult(
                    agent_id=agent.id,
                    nickname=agent.nickname,
                    role=agent.role,
                    content="",
                    error=f"Provider '{agent.provider}' not available.",
                    model_id=agent.model_id,
                    provider=agent.provider,
                    elapsed_seconds=time.time() - start_time,
                )

            messages, system_msg = self._build_messages_for_agent(
                agent, task, phase_context
            )

            full_text = ""
            async for chunk in provider_obj.stream_chat(
                messages=messages,
                model=agent.model_id,
                system=system_msg,
                max_tokens=max_tokens,
            ):
                chunk_type = getattr(chunk, "type", "")
                if chunk_type == "text":
                    full_text += getattr(chunk, "content", "")

            return AgentResult(
                agent_id=agent.id,
                nickname=agent.nickname,
                role=agent.role,
                content=full_text.strip() or "No response generated.",
                error=None,
                model_id=agent.model_id,
                provider=agent.provider,
                elapsed_seconds=time.time() - start_time,
            )

        try:
            result = await asyncio.wait_for(_do_call(), timeout=timeout)
            self.agent_status[agent.id] = AgentStatus.COMPLETE
            self.agent_results[agent.id] = result
            return result

        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            self.agent_status[agent.id] = AgentStatus.FAILED
            logger.error(f"Agent {agent.nickname} timed out after {timeout}s")
            result = AgentResult(
                agent_id=agent.id,
                nickname=agent.nickname,
                role=agent.role,
                content="",
                error=f"Timed out after {timeout} seconds",
                model_id=agent.model_id,
                provider=agent.provider,
                elapsed_seconds=elapsed,
            )
            self.agent_results[agent.id] = result
            return result

        except Exception as e:
            elapsed = time.time() - start_time
            self.agent_status[agent.id] = AgentStatus.FAILED
            logger.error(f"Agent {agent.nickname} failed: {e}", exc_info=True)
            result = AgentResult(
                agent_id=agent.id,
                nickname=agent.nickname,
                role=agent.role,
                content="",
                error=str(e),
                model_id=agent.model_id,
                provider=agent.provider,
                elapsed_seconds=elapsed,
            )
            self.agent_results[agent.id] = result
            return result

    def send_inter_agent_message(
        self,
        from_agent_id: str,
        to_agent_id: Optional[str],
        content: str,
        message_type: str = MessageType.QUESTION,
        requires_response: bool = False,
    ) -> AgentMessage:
        """Send a message between agents."""
        msg = AgentMessage(
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            content=content,
            message_type=message_type,
            requires_response=requires_response,
        )
        self.messages.append(msg)
        return msg

    async def _create_execution_plan(self, task: str) -> ExecutionPlan:
        """Create an execution plan based on workflow mode."""
        agents_list = list(self.agents.values())

        if self.workflow_mode == WorkflowMode.SEQUENTIAL:
            # All agents run one after another
            phases = [
                ExecutionPhase(
                    phase_id=i,
                    agents=[agent.id],
                    description=f"{agent.nickname} working on {agent.role} tasks",
                    dependencies=[i - 1] if i > 0 else [],
                )
                for i, agent in enumerate(agents_list)
            ]
            return ExecutionPlan(
                phases=phases,
                reasoning="Sequential workflow: each agent works in order.",
                workflow_mode=WorkflowMode.SEQUENTIAL,
            )

        elif self.workflow_mode == WorkflowMode.PARALLEL:
            # All agents run at once
            return ExecutionPlan(
                phases=[
                    ExecutionPhase(
                        phase_id=0,
                        agents=[a.id for a in agents_list],
                        description="All agents working in parallel",
                        dependencies=[],
                    )
                ],
                reasoning="Parallel workflow: all agents work simultaneously.",
                workflow_mode=WorkflowMode.PARALLEL,
            )

        else:  # HYBRID
            # Group agents by role type for phased execution
            leaders = [a for a in agents_list if a.role == "leader"]
            researchers = [a for a in agents_list if a.role in ("researcher", "expert")]
            analysts = [a for a in agents_list if a.role in ("analyst", "coder")]
            critics = [a for a in agents_list if a.role == "critic"]
            synthesizers = [a for a in agents_list if a.role in ("synthesizer", "writer", "designer")]

            phases = []
            phase_id = 0

            # Phase 1: Leaders and researchers work in parallel
            if leaders or researchers:
                phases.append(ExecutionPhase(
                    phase_id=phase_id,
                    agents=[a.id for a in leaders + researchers],
                    description="Leaders and researchers working on initial analysis",
                    dependencies=[],
                ))
                phase_id += 1

            # Phase 2: Analysts work in parallel
            if analysts:
                phases.append(ExecutionPhase(
                    phase_id=phase_id,
                    agents=[a.id for a in analysts],
                    description="Analysts performing deep analysis",
                    dependencies=[phase_id - 1] if phase_id > 0 else [],
                ))
                phase_id += 1

            # Phase 3: Critics review
            if critics:
                phases.append(ExecutionPhase(
                    phase_id=phase_id,
                    agents=[a.id for a in critics],
                    description="Critics reviewing and providing feedback",
                    dependencies=[phase_id - 1] if phase_id > 0 else [],
                ))
                phase_id += 1

            # Phase 4: Synthesizers create final output
            if synthesizers:
                phases.append(ExecutionPhase(
                    phase_id=phase_id,
                    agents=[a.id for a in synthesizers],
                    description="Synthesizers creating final output",
                    dependencies=[phase_id - 1] if phase_id > 0 else [],
                ))

            # If no agents matched the patterns, just run everyone in parallel
            if not phases:
                phases.append(ExecutionPhase(
                    phase_id=0,
                    agents=[a.id for a in agents_list],
                    description="All agents working together",
                    dependencies=[],
                ))

            return ExecutionPlan(
                phases=phases,
                reasoning="Hybrid workflow: agents grouped by role type for phased parallel execution.",
                workflow_mode=WorkflowMode.HYBRID,
            )

    async def run_collaborative_task(
        self,
        task: str,
        callback: Optional[Callable] = None,
        max_rounds: int = 4,
    ) -> Dict[str, Any]:
        """
        Run a collaborative task with the agent team.

        Supports parallel execution within phases based on workflow mode.

        Args:
            task: The main task for the team
            callback: Async callback for streaming updates
            max_rounds: Maximum conversation rounds
        """
        self.status = "working"
        start_time = time.time()

        try:
            # Create execution plan
            plan = await self._create_execution_plan(task)

            if callback:
                await callback({
                    "type": "plan_created",
                    "plan": {
                        "phases": [
                            {
                                "phase_id": p.phase_id,
                                "agents": [self.agents[a_id].nickname for a_id in p.agents if a_id in self.agents],
                                "description": p.description,
                            }
                            for p in plan.phases
                        ],
                        "reasoning": plan.reasoning,
                        "workflow_mode": plan.workflow_mode,
                    },
                })

            all_results: List[AgentResult] = []
            phase_context: Dict[str, Any] = {"previous_results": []}

            # Execute phases
            for phase in plan.phases:
                phase_agents = [self.agents[a_id] for a_id in phase.agents if a_id in self.agents]

                if not phase_agents:
                    continue

                if callback:
                    await callback({
                        "type": "phase_start",
                        "phase_id": phase.phase_id,
                        "description": phase.description,
                        "agents": [a.nickname for a in phase_agents],
                    })

                # Run agents in parallel within this phase
                tasks = [
                    self._call_agent(agent, task, phase_context)
                    for agent in phase_agents
                ]

                # Execute in parallel
                phase_results = await asyncio.gather(*tasks)
                all_results.extend(phase_results)

                # Update context for next phase
                phase_context["previous_results"] = all_results

                # Send results via callback
                for result in phase_results:
                    if callback:
                        await callback({
                            "type": "agent_message",
                            "agent_id": result.agent_id,
                            "nickname": result.nickname,
                            "role": result.role,
                            "content": result.content,
                            "error": result.error,
                            "model_id": result.model_id,
                            "provider": result.provider,
                            "elapsed_seconds": result.elapsed_seconds,
                        })

                if callback:
                    await callback({
                        "type": "phase_complete",
                        "phase_id": phase.phase_id,
                    })

            # Find synthesis agent (or use the last agent if none)
            synthesis_agents = [a for a in self.agents.values() if a.role in ("synthesizer", "writer", "leader")]
            if synthesis_agents and synthesis_agents[0].id not in self.agent_results:
                # Run synthesis if not already done
                synthesis_agent = synthesis_agents[0]
                synthesis_result = await self._call_agent(
                    synthesis_agent,
                    task,
                    phase_context,
                )
                all_results.append(synthesis_result)
                if callback:
                    await callback({
                        "type": "agent_message",
                        "agent_id": synthesis_result.agent_id,
                        "nickname": synthesis_result.nickname,
                        "role": synthesis_result.role,
                        "content": synthesis_result.content,
                        "error": synthesis_result.error,
                        "model_id": synthesis_result.model_id,
                        "provider": synthesis_result.provider,
                        "elapsed_seconds": synthesis_result.elapsed_seconds,
                    })

            # Get final result
            final_result = None
            if synthesis_agents:
                final_result = self.agent_results.get(synthesis_agents[0].id)
            if not final_result and all_results:
                # Use the last successful result
                for r in reversed(all_results):
                    if not r.error:
                        final_result = r
                        break

            self.status = "completed"
            elapsed = round(time.time() - start_time, 2)

            result = {
                "success": True,
                "team_id": self.team_id,
                "task": task,
                "result": final_result.content if final_result else "No synthesis agent found.",
                "agent_results": [
                    {
                        "agent_id": r.agent_id,
                        "nickname": r.nickname,
                        "role": r.role,
                        "content": r.content,
                        "error": r.error,
                        "model_id": r.model_id,
                        "provider": r.provider,
                        "elapsed_seconds": r.elapsed_seconds,
                    }
                    for r in all_results
                ],
                "messages": [
                    {
                        "id": m.id,
                        "from_agent_id": m.from_agent_id,
                        "to_agent_id": m.to_agent_id,
                        "content": m.content,
                        "message_type": m.message_type,
                        "created_at": m.created_at,
                    }
                    for m in self.messages
                ],
                "agents_used": [a.nickname for a in self.agents.values()],
                "elapsed_seconds": elapsed,
                "execution_plan": {
                    "workflow_mode": plan.workflow_mode,
                    "phases": len(plan.phases),
                    "reasoning": plan.reasoning,
                },
            }

            if callback:
                await callback({
                    "type": "team_complete",
                    "result": result,
                })

            return result

        except Exception as e:
            self.status = "failed"
            logger.error(f"Team task failed: {e}", exc_info=True)
            return {
                "success": False,
                "team_id": self.team_id,
                "error": str(e),
                "agent_results": [
                    {
                        "agent_id": r.agent_id,
                        "nickname": r.nickname,
                        "role": r.role,
                        "content": r.content,
                        "error": r.error,
                    }
                    for r in self.agent_results.values()
                ],
            }


# ─── Helper Functions ─────────────────────────────────────────────────────────────

def create_default_team_config(
    model_id: str = "claude-sonnet-4-20250514",
    provider: str = "anthropic",
) -> List[AgentConfig]:
    """Create a default team configuration."""
    return [
        AgentConfig(role="leader", nickname="Team Lead", model_id=model_id, provider=provider),
        AgentConfig(role="researcher", nickname="Researcher", model_id=model_id, provider=provider),
        AgentConfig(role="analyst", nickname="Analyst", model_id=model_id, provider=provider),
        AgentConfig(role="critic", nickname="Critic", model_id=model_id, provider=provider),
        AgentConfig(role="synthesizer", nickname="Synthesizer", model_id=model_id, provider=provider),
    ]


def create_team_from_template(template_name: str) -> List[AgentConfig]:
    """Create a team from a template."""
    template = TEAM_TEMPLATES.get(template_name)
    if not template:
        return create_default_team_config()
    return [
        AgentConfig(
            role=a.role,
            nickname=a.nickname,
            model_id=a.model_id,
            provider=a.provider,
            custom_role_desc=a.custom_role_desc,
            instructions=a.instructions,
            color=a.color,
        )
        for a in template["agents"]
    ]


def list_available_templates() -> List[Dict[str, Any]]:
    """List all available team templates."""
    return [
        {
            "id": template_id,
            "name": template["name"],
            "description": template["description"],
            "workflow_mode": template["workflow_mode"],
            "agents": [
                {
                    "role": a.role,
                    "nickname": a.nickname,
                    "model_id": a.model_id,
                    "provider": a.provider,
                }
                for a in template["agents"]
            ],
        }
        for template_id, template in TEAM_TEMPLATES.items()
    ]