from enum import IntEnum, StrEnum

class StageEnum(StrEnum):
    ROUTER_NODE = "router"
    USER_DATA_NODE= "user_data"
    NEWS_DATA_NODE = "news_data"
    DISCUSSION_NODE = "discussion"
    RISK_NODE = "risk"
    FINALIZER_NODE = "finalizer"
    FACT_NODE = "fact"
    OTHER_NODE = "other"
    BACKTEST_NODE = "backtest"
    END = "__end__"
