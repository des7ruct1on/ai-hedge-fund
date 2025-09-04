import os
from uuid import uuid4
from utils import create_initial_state


class Agent:

    def __init__(self, llm, graph):
        self.llm = llm
        self.graph = graph
        self.thread_id = os.getenv("THREAD_ID") or f"cli-session-{uuid4().hex[:8]}"

    def process_message(self, message: str, state: dict = None) -> str:
        print(f"Processing message: {message}")
        if not state:
            state = create_initial_state()


        print(f"State: {state}")
        state["message_from_user"] = message

        print("Invoking graph")
        result = self.graph.invoke(
            state,
            config={"configurable": {"thread_id": self.thread_id}}
        )

        print(f"Result: {result}")

        ai_message = result.get("message_to_user", "")
        
        return ai_message
