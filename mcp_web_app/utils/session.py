from typing import Any, Dict, Optional, Union
from langchain_community.chat_message_histories import ChatMessageHistory

def needs_session_recreation(session: Optional[Dict[str, Any]], llm_config_id, tools_config, agent_mode, agent_data_source) -> bool:
    if session is None:
        return True
    return (
        (llm_config_id and session.get("llm_config_id_used") != llm_config_id) or
        (tools_config != session.get("tools_config_used")) or
        (agent_mode and session.get("agent_mode_used") != agent_mode) or
        (agent_data_source and session.get("agent_data_source_used") != agent_data_source)
    )

def create_new_session_dict(current_llm, effective_llm_config_id, tools_config, agent_mode, agent_data_source) -> Dict[str, Any]:
    return {
        "llm": current_llm,
        "agent_executor": None,
        "raw_agent_executor": None,
        "mcp_client": None,
        "memory_saver": ChatMessageHistory(),
        "chat_messages_for_log": [],
        "llm_config_id_used": effective_llm_config_id,
        "tools_config_used": tools_config,
        "agent_mode_used": agent_mode,
        "agent_data_source_used": agent_data_source
    } 