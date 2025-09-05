from typing import Annotated, List, TypedDict, Dict, Any
from dataclasses import dataclass


@dataclass
class AgentOpinion:
    agent_name: str
    ticker: str
    action: str  # BUY/SELL/HOLD
    confidence: int  # 1-10
    reasoning: str


@dataclass
class AggregatedDecision:
    ticker: str
    final_action: str
    confidence_score: float
    agent_opinions: List[AgentOpinion]
    consensus_strength: float


@dataclass
class RiskAssessment:
    ticker: str
    risk_level: int  # 1-10
    risk_factors: List[str]
    recommendations: str


class State(TypedDict):
    messages: Annotated[List[str], "messages"]
    message_to_user: Annotated[str, "message_to_user"]
    message_from_user: Annotated[str, "message_from_user"]
    stage: Annotated[str, "stage"]
    user_data: Annotated[dict, "user_data"]
    news_data: Annotated[List[dict], "news_data"]
    agent_opinions: Annotated[List[AgentOpinion], "agent_opinions"]
    aggregated_decisions: Annotated[List[AggregatedDecision], "aggregated_decisions"]
    risk_assessments: Annotated[List[RiskAssessment], "risk_assessments"]
    final_recommendations: Annotated[str, "final_recommendations"]