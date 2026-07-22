from typing import TypedDict, List, Dict, Any, Optional


class AgentState(TypedDict):
    """
    Shared graph state tracked during orchestrator execution.
    """
    user_query: str
    retrieved_chunks: List[Dict[str, Any]]
    company_details: Optional[Dict[str, Any]]
    company_id: Optional[str]
    document_metadata: List[Dict[str, Any]]
    execution_history: List[str]
    final_context: Dict[str, Any]
    session_id: Optional[str]
    conversation_history: List[Dict[str, str]]
