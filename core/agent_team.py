"""
Agent Team Engine
=================
Multi-agent collaboration system where AI agents work together.

Agents can:
- Send messages to each other
- Execute sandbox code (Python/JavaScript)
- Share results in conversation
- Request clarification from other agents
- Synthesize findings into final output
"""

import logging
import json
import asyncio
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    LEADER = "leader"
    RESEARCHER = "researcher"
    ANALYST = "analyst"
    CRITIC = "critic"
    SYNTHESIZER = "synthesizer"
    CODER = "coder"


# Role descriptions for agent instructions
ROLE_DESCRIPTIONS = {
    AgentRole.LEADER: (
        "You are the Team Leader. Your job is to: "
        "1) Break down the main task into subtasks "
        "2) Assign subtasks to appropriate team members "
        "3) Coordinate the team's work "
        "4) Ensure the final output meets quality standards. "
        "Be concise and directive. Ask other agents specific questions."
    ),
    AgentRole.RESEARCHER: (
        "You are the Researcher. Your job is to: "
        "1) Gather information and data relevant to the task "
        "2) Use web search and knowledge bases when available "
        "3) Provide factual, well-sourced information "
        "4) Flag any gaps in available data. "
        "Be thorough but concise in your findings."
    ),
    AgentRole.ANALYST: (
        "You are the Analyst. Your job is to: "
        "1) Analyze data and information provided by the Researcher "
        "2) Run calculations and code in the sandbox when needed "
        "3) Identify patterns, trends, and insights "
        "4) Provide quantitative analysis with numbers. "
        "Be precise and data-driven."
    ),
    AgentRole.CRITIC: (
        "You are the Critic. Your job is to: "
        "1) Review the team's work for errors and weaknesses "
        "2) Challenge assumptions and identify risks "
        "3) Suggest improvements and alternatives "
        "4) Ensure the final output is rigorous. "
        "Be constructive but thorough in your critique."
    ),
    AgentRole.SYNTHESIZER: (
        "You are the Synthesizer. Your job is to: "
        "1) Combine findings from all team members "
        "2) Create a coherent, well-structured final output "
        "3) Resolve any conflicting information "
        "4) Present the results clearly. "
        "Be clear and comprehensive."
    ),
    AgentRole.CODER: (
        "You are the Coder. Your job is to: "
        "1) Write and execute code in the sandbox "
        "2) Perform data processing and analysis "
        "3) Generate visualizations and outputs "
        "4) Debug any code issues. "
        "Write clean, efficient code and explain what it does."
    ),
}

# Role colors for UI
ROLE_COLORS = {
    AgentRole.LEADER: "#FEC00F",
    AgentRole.RESEARCHER: "#3B82F6",
    AgentRole.ANALYST: "#10B981",
    AgentRole.CRITIC: "#EF4444",
    AgentRole.SYNTHESIZER: "#8B5CF6",
    AgentRole.CODER: "#06B6D4",
}


class AgentTeam:
    """
    Manages a team of AI agents working together on a task.
    """

    def __init__(
        self,
        team_id: str,
        user_id: str,
        members: List[Dict[str, Any]],
        registry: Any,
    ):
        self.team_id = team_id
        self.user_id = user_id
        self.members = members  # [{role, model_id, provider, instructions, color}]
        self.registry = registry
        self.conversation: List[Dict[str, Any]] = []
        self.shared_context: Dict[str, Any] = {}
        self.status = "idle"

    def _get_member(self, role: str) -> Optional[Dict[str, Any]]:
        """Get a team member by role."""
        for m in self.members:
            if m.get("role") == role:
                return m
        return None

    def _build_messages_for_agent(
        self,
        agent_role: str,
        task: str,
        conversation: List[Dict],
    ) -> List[Dict]:
        """Build the message history for a specific agent."""
        member = self._get_member(agent_role)
        role_desc = ROLE_DESCRIPTIONS.get(
            AgentRole(agent_role),
            f"You are a {agent_role} agent."
        )
        custom_instructions = member.get("instructions", "") if member else ""

        system_msg = role_desc
        if custom_instructions:
            system_msg += f"\n\nAdditional instructions: {custom_instructions}"

        # Build conversation context
        messages = []
        for msg in conversation:
            from_role = msg.get("from_role", "unknown")
            content = msg.get("content", "")
            msg_type = msg.get("message_type", "message")

            if msg_type == "task":
                messages.append({
                    "role": "user",
                    "content": f"[TASK FROM USER]: {content}"
                })
            elif from_role == agent_role:
                # This agent's previous messages
                messages.append({
                    "role": "assistant",
                    "content": content
                })
            else:
                # Message from another agent
                messages.append({
                    "role": "user",
                    "content": f"[{from_role.upper()}]: {content}"
                })

        # Add the current task if this is the first message
        if not messages:
            messages.append({
                "role": "user",
                "content": f"[TASK]: {task}"
            })

        return messages, system_msg

    async def _call_agent(
        self,
        agent_role: str,
        task: str,
        conversation: List[Dict],
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        """Call a single agent and get its response."""
        member = self._get_member(agent_role)
        if not member:
            return {
                "role": agent_role,
                "content": f"Error: Agent '{agent_role}' not found in team.",
                "error": True,
            }

        model_id = member.get("model_id", "")
        provider = member.get("provider", "anthropic")

        try:
            provider_obj = self.registry.get_provider(provider)
            if not provider_obj:
                try:
                    provider_obj = self.registry.get_provider_for_model(model_id)
                except Exception:
                    pass

            if not provider_obj:
                return {
                    "role": agent_role,
                    "content": f"Error: Provider '{provider}' not available.",
                    "error": True,
                }

            messages, system_msg = self._build_messages_for_agent(
                agent_role, task, conversation
            )

            full_text = ""
            async for chunk in provider_obj.stream_chat(
                messages=messages,
                model=model_id,
                system=system_msg,
                max_tokens=max_tokens,
            ):
                chunk_type = getattr(chunk, "type", "")
                if chunk_type == "text":
                    full_text += getattr(chunk, "content", "")

            return {
                "role": agent_role,
                "content": full_text.strip() or "No response generated.",
                "error": False,
                "model_id": model_id,
                "provider": provider,
            }

        except Exception as e:
            logger.error(f"Agent {agent_role} failed: {e}", exc_info=True)
            return {
                "role": agent_role,
                "content": f"Error: {str(e)}",
                "error": True,
            }

    async def run_collaborative_task(
        self,
        task: str,
        callback=None,
        max_rounds: int = 4,
    ) -> Dict[str, Any]:
        """
        Run a collaborative task with the agent team.

        Flow:
        1. Leader breaks down the task
        2. Researcher gathers information
        3. Analyst analyzes data (can use sandbox)
        4. Critic reviews and provides feedback
        5. Synthesizer creates final output

        Args:
            task: The main task for the team
            callback: Async callback for streaming updates
            max_rounds: Maximum conversation rounds
        """
        self.status = "working"
        start_time = time.time()

        try:
            # Round 1: Leader breaks down the task
            if callback:
                await callback({
                    "type": "agent_start",
                    "role": "leader",
                    "message": "Breaking down the task...",
                })

            leader_response = await self._call_agent("leader", task, [])
            self.conversation.append({
                "from_role": "leader",
                "to_role": None,  # broadcast
                "content": leader_response["content"],
                "message_type": "task",
                "created_at": datetime.utcnow().isoformat(),
            })

            if callback:
                await callback({
                    "type": "agent_message",
                    "role": "leader",
                    "content": leader_response["content"],
                })

            # Round 2: Researcher gathers information
            if callback:
                await callback({
                    "type": "agent_start",
                    "role": "researcher",
                    "message": "Researching the topic...",
                })

            researcher_response = await self._call_agent(
                "researcher", task, self.conversation
            )
            self.conversation.append({
                "from_role": "researcher",
                "to_role": "leader",
                "content": researcher_response["content"],
                "message_type": "answer",
                "created_at": datetime.utcnow().isoformat(),
            })

            if callback:
                await callback({
                    "type": "agent_message",
                    "role": "researcher",
                    "content": researcher_response["content"],
                })

            # Round 3: Analyst analyzes
            if callback:
                await callback({
                    "type": "agent_start",
                    "role": "analyst",
                    "message": "Analyzing the data...",
                })

            analyst_response = await self._call_agent(
                "analyst", task, self.conversation
            )
            self.conversation.append({
                "from_role": "analyst",
                "to_role": "leader",
                "content": analyst_response["content"],
                "message_type": "answer",
                "created_at": datetime.utcnow().isoformat(),
            })

            if callback:
                await callback({
                    "type": "agent_message",
                    "role": "analyst",
                    "content": analyst_response["content"],
                })

            # Round 4: Critic reviews
            if callback:
                await callback({
                    "type": "agent_start",
                    "role": "critic",
                    "message": "Reviewing the analysis...",
                })

            critic_response = await self._call_agent(
                "critic", task, self.conversation
            )
            self.conversation.append({
                "from_role": "critic",
                "to_role": "leader",
                "content": critic_response["content"],
                "message_type": "critique",
                "created_at": datetime.utcnow().isoformat(),
            })

            if callback:
                await callback({
                    "type": "agent_message",
                    "role": "critic",
                    "content": critic_response["content"],
                })

            # Round 5: Synthesizer creates final output
            if callback:
                await callback({
                    "type": "agent_start",
                    "role": "synthesizer",
                    "message": "Synthesizing final output...",
                })

            synthesizer_response = await self._call_agent(
                "synthesizer", task, self.conversation
            )
            self.conversation.append({
                "from_role": "synthesizer",
                "to_role": None,
                "content": synthesizer_response["content"],
                "message_type": "synthesis",
                "created_at": datetime.utcnow().isoformat(),
            })

            if callback:
                await callback({
                    "type": "agent_message",
                    "role": "synthesizer",
                    "content": synthesizer_response["content"],
                })

            # Final result
            self.status = "completed"
            elapsed = round(time.time() - start_time, 2)

            result = {
                "success": True,
                "team_id": self.team_id,
                "task": task,
                "result": synthesizer_response["content"],
                "conversation": self.conversation,
                "agents_used": [m.get("role") for m in self.members],
                "elapsed_seconds": elapsed,
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
                "conversation": self.conversation,
            }


def create_default_team_config(
    model_id: str = "claude-sonnet-4-20250514",
    provider: str = "anthropic",
) -> List[Dict[str, Any]]:
    """Create a default team configuration."""
    return [
        {
            "role": "leader",
            "model_id": model_id,
            "provider": provider,
            "instructions": "",
            "color": ROLE_COLORS[AgentRole.LEADER],
        },
        {
            "role": "researcher",
            "model_id": model_id,
            "provider": provider,
            "instructions": "",
            "color": ROLE_COLORS[AgentRole.RESEARCHER],
        },
        {
            "role": "analyst",
            "model_id": model_id,
            "provider": provider,
            "instructions": "",
            "color": ROLE_COLORS[AgentRole.ANALYST],
        },
        {
            "role": "critic",
            "model_id": model_id,
            "provider": provider,
            "instructions": "",
            "color": ROLE_COLORS[AgentRole.CRITIC],
        },
        {
            "role": "synthesizer",
            "model_id": model_id,
            "provider": provider,
            "instructions": "",
            "color": ROLE_COLORS[AgentRole.SYNTHESIZER],
        },
    ]