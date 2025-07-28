from google.adk.agents import Agent
from . import prompt

# Import your specialized JD agents
from ..Software_Development_Agent import software_agent
from ..IT_Services_Agent import it_services_agent
from ..Banking_Agent import banking_agent
from ..Healthcare_Agent import healthcare_agent
from ..Travel_Agent import travel_agent
from ..Real_Estate_Agent import real_estate_agent
from ..Insurance_Agent import insurance_agent


# --- Define the Coordinator Agent ---
sub_agent_coordinator = Agent(
    name="sub_agent_coordinator",
    description="A coordinator agent that delegates job description questions to specialized agents and handles other queries.",
    model="gemini-2.0-flash",
    instruction=prompt.SUB_AGENT_COORDINATOR_PROMPT,
    sub_agents=[
        it_services_agent,
        software_agent,
        real_estate_agent,
        insurance_agent,
        banking_agent,
        travel_agent,
        healthcare_agent,
    ],
)

