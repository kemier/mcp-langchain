from typing import Optional, Dict

def get_fast_response(question: str, fast_responses: Dict[str, str]) -> Optional[str]:
    """Return a fast response if the question matches a known fast path."""
    return fast_responses.get(question.lower().strip())


def resolve_llm_config_id(llm_config_id: Optional[str], config_manager) -> Optional[str]:
    """Resolve the effective LLM config ID, falling back to default if needed."""
    if llm_config_id:
        config = config_manager.get_llm_config_by_id(llm_config_id)
        if config:
            return config.config_id
    default_cfg = config_manager.get_default_llm_config()
    if default_cfg:
        return default_cfg.config_id
    return None 