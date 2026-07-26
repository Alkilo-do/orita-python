"""
LangChain tool integration example.
Use Orita as a LangChain tool to give your LLM agent scheduling capabilities.
"""
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from orita import OritaClient
from datetime import date, timedelta

orita = OritaClient(api_key="orita_your_key_here")

# Get the first event type at startup
_event_types = orita.event_types()
EVENT_TYPE_ID = _event_types[0]["id"] if _event_types else None


@tool
def get_available_slots(date_str: str) -> str:
    """Get available appointment slots for a given date (YYYY-MM-DD format).
    Returns a list of available time slots."""
    slots = orita.slots(event_type_id=EVENT_TYPE_ID, date=date_str)
    if not slots:
        return f"No available slots on {date_str}"
    return "\n".join([f"- {s['label']} (value: {s['value']})" for s in slots])


@tool
def book_appointment(
    date_str: str,
    time_str: str,
    client_name: str,
    client_lastname: str,
    client_email: str,
) -> str:
    """Book an appointment for a client.
    
    Args:
        date_str: Date in YYYY-MM-DD format
        time_str: Time in HH:MM format
        client_name: Client's first name
        client_lastname: Client's last name
        client_email: Client's email address
    
    Returns a confirmation with booking ID.
    """
    booking = orita.book(
        event_type_id=EVENT_TYPE_ID,
        date=date_str,
        time=time_str,
        client_name=client_name,
        client_lastname=client_lastname,
        client_email=client_email,
    )
    return f"Booking confirmed! ID: {booking['id']}, Status: {booking['status']}"


@tool
def get_tomorrow_date() -> str:
    """Returns tomorrow's date in YYYY-MM-DD format."""
    return (date.today() + timedelta(days=1)).isoformat()


# Set up the LangChain agent
llm = ChatOpenAI(model="gpt-4o", temperature=0)
tools = [get_available_slots, book_appointment, get_tomorrow_date]

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful scheduling assistant. Help users book appointments using the available tools."),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

agent = create_openai_tools_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

# Example usage
if __name__ == "__main__":
    result = agent_executor.invoke({
        "input": "I need to book an appointment for tomorrow. My name is Carlos Martínez, email carlos@example.com. Pick the first available slot."
    })
    print(result["output"])
