# Source URL: https://github.com/pydantic/pydantic-ai/issues/1679

- How to ensure Agent retries MCP server tool calls with retries · Issue #1679 · pydantic/pydantic-ai



































































































Skip to content





























## Navigation Menu


Toggle navigation

























Sign in






Appearance settings


























Platform AI CODE CREATION GitHub Copilot Write better code with AI
- GitHub Spark Build and deploy intelligent apps
- GitHub Models Manage and compare prompts
- MCP Registry New Integrate external tools


- DEVELOPER WORKFLOWS Actions Automate any workflow
- Codespaces Instant dev environments
- Issues Plan and track work
- Code Review Manage code changes


- APPLICATION SECURITY GitHub Advanced Security Find and fix vulnerabilities
- Code security Secure your code as you build
- Secret protection Stop leaks before they start


- EXPLORE Why GitHub
- Documentation
- Blog
- Changelog
- Marketplace


View all features - Solutions BY COMPANY SIZE Enterprises
- Small and medium teams
- Startups
- Nonprofits


- BY USE CASE App Modernization
- DevSecOps
- DevOps
- CI/CD
- View all use cases


- BY INDUSTRY Healthcare
- Financial services
- Manufacturing
- Government
- View all industries


View all solutions

- Resources EXPLORE BY TOPIC AI
- Software Development
- DevOps
- Security
- View all topics


- EXPLORE BY TYPE Customer stories
- Events & webinars
- Ebooks & reports
- Business insights
- GitHub Skills


- SUPPORT & SERVICES Documentation
- Customer support
- Community forum
- Trust center
- Partners


View all resources

- Open Source COMMUNITY GitHub Sponsors Fund open source developers


- PROGRAMS Security Lab
- Maintainer Community
- Accelerator
- GitHub Stars
- Archive Program


- REPOSITORIES Topics
- Trending
- Collections




- Enterprise ENTERPRISE SOLUTIONS Enterprise platform AI-powered developer platform


- AVAILABLE ADD-ONS GitHub Advanced Security Enterprise-grade security features
- Copilot for Business Enterprise-grade AI features
- Premium Support Enterprise-grade 24/7 support




- Pricing
















Search or jump to...












# Search code, repositories, users, issues, pull requests...




-->



Search



















Clear







































































































































































































































Search syntax tips





















# Provide feedback















-->
We read every piece of feedback, and take your input very seriously.



Include my email address so I can be contacted



Cancel

Submit feedback












# Saved searches


## Use saved searches to filter your results more quickly





-->





Name







Query




To see all available qualifiers, see our documentation .









Cancel

Create saved search










Sign in




Sign up





Appearance settings



- Resetting focus















You signed in with another tab or window. Reload to refresh your session.
You signed out in another tab or window. Reload to refresh your session.
You switched accounts on another tab or window. Reload to refresh your session.




Dismiss alert




















{{ message }}

































pydantic

/

pydantic-ai


Public












Notifications
You must be signed in to change notification settings

- Fork
2.1k

- Star
17.3k












- Code

- Issues
377

- Pull requests
174

- Actions

- Security and quality
4

- Insights







Additional navigation options







- Code

- Issues

- Pull requests

- Actions

- Security and quality

- Insights





























- # How to ensure Agent retries MCP server tool calls with retries   #1679

New issue

Copy link

New issue

Copy link

Closed as not planned



Closed as not planned

How to ensure Agent retries MCP server tool calls with retries #1679



Copy link

Assignees





Labels

Stale question Further information is requested Further information is requested








## Description



xy3xy3

opened on May 9, 2025

Last edited by xy3xy3



Issue body actions

I'm using pydantic-ai with an MCPServerHTTP for a smart home assistant. I want the agent to perform a two-step process for control tasks:


First, call a tool to query/list available smart home devices.

- Then, use the information from step 1 (specifically the entity_id ) to call another tool to control the target device.


I've set retries=3 on the Agent , expecting that if any part of this process (especially the tool calls via MCP server) fails, it would be retried.

However, when I give a command like "Turn off the monitor light bar," the agent seems to skip the device listing/identification step and immediately asks me for the entity_ID . This suggests it's not attempting the desired two-step process or retrying the initial discovery phase.

If the user's query was just about device status (e.g., "Is the light on?"), I'd expect it to perform the query step but not necessarily proceed to a control step. The current issue is about the control scenario where discovery should precede action.

Code (Python):

import asyncio
import os
import sys
from pydantic_ai . mcp import MCPServerHTTP
from pydantic_ai import Agent
from pydantic_ai . models . openai import OpenAIModel
from pydantic_ai . providers . openai import OpenAIProvider
from typing import List # Removed Union as it wasn't used

# Dummy config values for reproducibility
class DummyConfig :
def get ( self , key ):
if key == 'ha_auth_token' :
return "DUMMY_HA_AUTH_TOKEN"
if key == 'ha_server_url' :
return "http://localhost:8123/api/" # Replace with your HA server URL
if key == 'sf_api_key' :
return "DUMMY_SF_API_KEY"
if key == 'sf_base_url' :
return "DUMMY_SF_BASE_URL" # Replace with your LLM provider base URL
return None

config = DummyConfig ()

headers = {
"Authorization" : f"Bearer { config . get ( 'ha_auth_token' ) } " ,
}
server = MCPServerHTTP ( url = config . get ( 'ha_server_url' ), headers = headers )

system_prompt_en = """You are a smart home assistant designed to help users control smart home devices.
When a user asks you to turn a device on or off:
1. First, call the tool to query the device list and entities to determine which device the user intends to control. You can judge based on name similarity.
2. When calling the interface to switch the device and passing arguments:
Prioritize using domain, device_class, and entity_id to locate the device, rather than name.
Correct example, using entity_id:
{
"domain": ["switch"],
"device_class": ["switch"],
"entity_id": "switch.monitor_light_bar_switch"
}
3. When the device switching interface returns "isError": false, it means the switch was successful.
"""

agent : Agent = Agent (
model = OpenAIModel (
model_name = "THUDM/GLM-4-9B-0414" , # Example model
provider = OpenAIProvider ( api_key = config . get ( 'sf_api_key' ), base_url = config . get ( 'sf_base_url' ))
),
mcp_servers = [ server ],
system_prompt = system_prompt_en ,
retries = 3 ,
output_retries = 3
)

async def main ():
async with agent . run_mcp_servers ():
result = await agent . run ( 'Turn off the monitor light bar.' )
print ( result )
print ( f"Agent Output: { result . output } " )

if __name__ == '__main__' :
asyncio . run ( main ())










Agent Output (Translated):

AgentRunResult(output='\nSorry, it seems there was a technical issue while trying to turn off the monitor light bar. To better assist you, please tell me the exact name or entity ID of the monitor light bar so I can assist you directly. If possible, you can find the relevant name in your smart home device list and provide it to me.')

Agent Output:
Sorry, it seems there was a technical issue while trying to turn off the monitor light bar. To better assist you, please tell me the exact name or entity ID of the monitor light bar so I can assist you directly. If possible, you can find the relevant name in your smart home device list and provide it to me.











Expected Behavior:

For a command like "Turn off the monitor light bar":


- Agent attempts to call a tool (via MCPServerHTTP ) to list/query devices to find the "monitor light bar".

- If this initial tool call fails or doesn't yield enough info, it should be retried (due to retries=3 ).

- Once the device is identified (e.g., entity_id: "switch.monitor_light_bar_switch" is found), the agent attempts a second tool call to control this specific entity_id .

- This second tool call should also be retried upon failure.

- The agent should only ask the user for an entity_id if the entire multi-step process (including retries for each tool call) genuinely fails to identify or control the device.



Here is an image for Agent to use tools twice in Cherry Studio.

Another example to ask the tempature,only use tool once.


Question:

How can I configure or guide the Agent to reliably attempt this multi-step tool usage (e.g., first list/query devices, then control a specific device by its ID)? Specifically, how do I ensure the retries parameter applies to each tool call within such a sequence made via the MCPServerHTTP before the agent gives up and asks the user for direct input like an entity_id ?

Thanks!




## Activity





xy3xy3

added question Further information is requested Further information is requested

on May 9, 2025







DouweM

self-assigned this

on May 12, 2025










### DouweM commented on May 12, 2025



DouweM

on May 12, 2025



Collaborator

More actions

@xy3xy3 Can you confirm you're on a PydanticAI v0.1.9 or later, so it includes #1618 for MCP error handling?

Your code and prompt seem to be properly set up to get the "Expected Behavior" you've described. It would be good to know what the LLM is actually doing instead, that's causing it to think "it seems there was a technical issue". Can you please add Logfire ( https://ai.pydantic.dev/logfire/ ) and share the chat conversation back-and-forth including any tool calls and (error) returns that happen before it tells you Sorry?








### github-actions commented on May 19, 2025



github-actions bot

on May 19, 2025 – with GitHub Actions



Contributor

More actions

This issue is stale, and will be closed in 3 days if no reply is received.







github-actions

added Stale

on May 19, 2025










### github-actions commented on May 23, 2025



github-actions bot

on May 23, 2025 – with GitHub Actions



Contributor

More actions

Closing this issue as it has been inactive for 10 days.









github-actions

closed this as not planned on May 23, 2025







Sign up for free to join this conversation on GitHub. Already have an account? Sign in to comment


## Metadata

## Metadata




### Assignees

- DouweM



### Labels

Stale question Further information is requested Further information is requested


### Type

No type


### Fields

Give feedback

No fields configured for issues without a type.


### Projects

No projects


### Milestone

No milestone






### Relationships

None yet


### Development

No branches or pull requests


### Participants



## Issue actions



























## Footer











© 2026 GitHub, Inc.





### Footer navigation



- Terms

- Privacy

- Security

- Status

- Community

- Docs

- Contact

- Manage cookies

- Do not share my personal information


















You can’t perform that action at this time.