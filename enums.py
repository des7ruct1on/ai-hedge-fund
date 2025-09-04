from enum import IntEnum, StrEnum

class StageEnum(StrEnum):
    USER_DATA_NODE= "user_data"
    NEWS_DATA_NODE = "news_data"
    DISCUSSION_NODE = "discussion"
    RISK_NODE = "risk"
    FINALIZER_NODE = "finalizer"
    END = "__end__"
