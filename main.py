"""
Customer Support AI Agent — Starter Code
==========================================
Your task is to complete this file by implementing all sections marked
with # TODO comments.

Reference the step-by-step solution files and INSTRUCTIONS.md for guidance.
Do NOT copy the solution directly — work through each section yourself.

Run locally (after filling in config values):
  uv run main.py '{"prompt": "Hello", "customer_id": "CUST-123", "session_id": "s1"}'

Deploy to AgentCore:
  agentcore deploy

Invoke deployed agent:
  agentcore invoke '{"prompt": "Hello", "customer_id": "CUST-123", "session_id": "s1"}'
"""

# ── Imports ───────────────────────────────────────────────────────────────────
# These imports are provided. Do not remove them.
from strands import Agent, tool
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.memory import MemoryClient
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamable_http_client
import argparse, json
import os, asyncio, boto3, re
from strands.hooks import (
    HookProvider, AfterInvocationEvent, HookRegistry, MessageAddedEvent,
)
import logging
import uuid
from typing import Dict
from bedrock_agentcore.tools.code_interpreter_client import code_session
from strands_tools.browser import AgentCoreBrowser


logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("CSAI_Agent")

# ── TODO 1 — App Initialisation ───────────────────────────────────────────────
# Create a BedrockAgentCoreApp instance.
# This registers the ASGI server for AgentCore deployment.
# There must be exactly one instance per deployment.
#
# Hint: app = BedrockAgentCoreApp()

app = BedrockAgentCoreApp()


# Suppress interactive tool-consent prompts (required in headless deployments).
os.environ["BYPASS_TOOL_CONSENT"] = "true"


# ── TODO 2 — Configuration ────────────────────────────────────────────────────
# Replace the placeholder strings with your actual AWS resource values.
# You collected these in Part 1 of the INSTRUCTIONS.
#
# GATEWAY_URL format: https://<alias>.gateway.bedrock-agentcore.<region>.amazonaws.com/mcp
# KB_ID       format: 10-character alphanumeric string from the KB console
# REGION:     your AWS region, e.g. "us-east-1"
# MEMORY_ID   format: shown in the AgentCore Memory console

GATEWAY_URL = "https://gateway-quick-start-fc827b-pkczfb8f8n.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"
KB_ID       = "JJWDU9V7ED"
REGION      = "us-east-1"
MEMORY_ID   = "memory_kca4b-vE8cBY90vg"


# ── TODO 3 — Model and Clients ────────────────────────────────────────────────
# Create:
#   1. A BedrockModel using model_id "global.amazon.nova-2-lite-v1:0"
#   2. A MemoryClient with region_name=REGION
#   3. A boto3 client for the "bedrock-agent-runtime" service in REGION
#
# Hint: model = BedrockModel(model_id=model_id)

model_id = "global.amazon.nova-2-lite-v1:0"

model = BedrockModel(model_id=model_id)
memory_client = MemoryClient(region_name=REGION)
_bedrock_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)


# ── TODO 4 — Namespace Helper ─────────────────────────────────────────────────
# Implement get_namespaces() to return a dict mapping strategy type to
# namespace template string.
#
# Steps:
#   1. Call mem_client.get_memory_strategies(memory_id) to get strategy list
#   2. Return a dict: { strategy["type"]: strategy["namespaces"][0] for each strategy }
#
# Example output:
#   { "SEMANTIC": "cs_agent/{actorId}/facts",
#     "USER_PREFERENCE": "cs_agent/{actorId}/preferences" }

def get_namespaces(mem_client: MemoryClient, memory_id: str) -> Dict:
    """Return a dict mapping strategy type → namespace template string."""
    if not memory_id or memory_id == "<mem_id>":
        return {
            "SEMANTIC": "cs_agent/{actorId}/facts",
            "USER_PREFERENCE": "cs_agent/{actorId}/preferences",
        }

    try:
        strategies_data = mem_client.get_memory_strategies(memory_id)
        if isinstance(strategies_data, dict):
            strategies = strategies_data.get("strategies") or strategies_data.get("memoryStrategies") or []
        elif isinstance(strategies_data, list):
            strategies = strategies_data
        else:
            strategies = []

        namespaces = {}
        for strategy in strategies:
            strategy_type = strategy.get("strategyType") or strategy.get("type")
            strategy_id = strategy.get("memoryStrategyId") or strategy.get("strategyId") or ""
            ns = None
            if "namespaceTemplates" in strategy and strategy["namespaceTemplates"]:
                ns = strategy["namespaceTemplates"][0]
            elif "namespaces" in strategy and strategy["namespaces"]:
                ns = strategy["namespaces"][0]

            if ns and strategy_id and "{memoryStrategyId}" in ns:
                ns = ns.replace("{memoryStrategyId}", strategy_id)

            if strategy_type and ns:
                namespaces[strategy_type] = ns

        if not namespaces:
            namespaces = {
                "SEMANTIC": "cs_agent/{actorId}/facts",
                "USER_PREFERENCE": "cs_agent/{actorId}/preferences",
            }
        return namespaces
    except Exception as e:
        logger.warning(f"Error fetching memory strategies: {e}")
        return {
            "SEMANTIC": "cs_agent/{actorId}/facts",
            "USER_PREFERENCE": "cs_agent/{actorId}/preferences",
        }


# ── TODO 5 — Memory Hook ──────────────────────────────────────────────────────
# Implement MemoryHook, a HookProvider subclass that adds long-term memory.
#
# The class needs:
#   __init__(self, actor_id, session_id, memory_client, memory_id)
#     — store all four as instance attributes
#     — call get_namespaces() and store the result as self.namespaces
#
#   retrieve_customer_context(self, event: MessageAddedEvent)
#     — only runs for plain-text user messages (not tool results)
#     — for each strategy namespace, call memory_client.retrieve_memories(
#          memory_id, namespace (formatted with actorId), query, top_k=5)
#     — collect non-empty memory texts tagged with their strategy type
#     — if any memories found, prepend them to the user message as:
#          "Customer Context:\n<memories>\n\n<original_message>"
#
#   save_support_interaction(self, event: AfterInvocationEvent)
#     — walk the message list backwards to find the last plain-text user
#       query and the last assistant response
#     — call memory_client.create_event(memory_id, actor_id, session_id,
#          messages=[(customer_query, "USER"), (agent_response, "ASSISTANT")])
#
#   register_hooks(self, registry: HookRegistry)
#     — register retrieve_customer_context on MessageAddedEvent
#     — register save_support_interaction on AfterInvocationEvent

class MemoryHook(HookProvider):
    """Long-term memory hook for the customer support agent."""

    def __init__(
        self,
        actor_id: str,
        session_id: str,
        memory_client: MemoryClient,
        memory_id: str,
    ):
        self.actor_id = actor_id
        self.session_id = session_id
        self.memory_client = memory_client
        self.memory_id = memory_id
        self.namespaces = get_namespaces(memory_client, memory_id)

    def retrieve_customer_context(self, event: MessageAddedEvent):
        """Retrieve relevant memories and prepend them to the user message."""
        try:
            agent = getattr(event, "agent", None)
            if not agent or not getattr(agent, "messages", None):
                return

            last_msg = agent.messages[-1]
            role = last_msg.get("role") if isinstance(last_msg, dict) else getattr(last_msg, "role", None)
            if role != "user":
                return

            content = last_msg.get("content") if isinstance(last_msg, dict) else getattr(last_msg, "content", None)

            # Skip tool results
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if "toolResult" in block or "tool_result" in block or "tool_use_id" in block:
                            return
                    elif hasattr(block, "tool_result") or hasattr(block, "toolResult"):
                        return

            user_text = ""
            if isinstance(content, str):
                user_text = content
            elif isinstance(content, list):
                text_blocks = []
                for b in content:
                    if isinstance(b, dict) and "text" in b:
                        text_blocks.append(b["text"])
                    elif hasattr(b, "text"):
                        text_blocks.append(getattr(b, "text"))
                user_text = "\n".join(text_blocks)

            if not user_text or user_text.startswith("Customer Context:\n"):
                return

            if not self.memory_id or self.memory_id == "<mem_id>":
                return

            collected_memories = []
            for strategy_type, ns_template in self.namespaces.items():
                try:
                    formatted_ns = ns_template.format(actorId=self.actor_id)
                    res = self.memory_client.retrieve_memories(
                        memory_id=self.memory_id,
                        namespace=formatted_ns,
                        query=user_text,
                        top_k=5,
                    )
                    memories_list = []
                    if isinstance(res, dict):
                        memories_list = res.get("memories") or res.get("records") or []
                    elif isinstance(res, list):
                        memories_list = res

                    for mem in memories_list:
                        mem_text = ""
                        if isinstance(mem, dict):
                            mem_text = mem.get("memoryText") or mem.get("text") or mem.get("content") or ""
                            if not mem_text and "record" in mem and isinstance(mem["record"], dict):
                                mem_text = mem["record"].get("text") or mem["record"].get("memoryText") or ""
                        elif hasattr(mem, "text"):
                            mem_text = getattr(mem, "text")

                        if mem_text:
                            collected_memories.append(f"[{strategy_type}] {mem_text}")
                except Exception as e:
                    logger.warning(f"Error retrieving memories for namespace {ns_template}: {e}")

            if collected_memories:
                memories_str = "\n".join(collected_memories)
                new_full_text = f"Customer Context:\n{memories_str}\n\n{user_text}"

                if isinstance(last_msg, dict):
                    if isinstance(last_msg.get("content"), str):
                        last_msg["content"] = new_full_text
                        return
                    elif isinstance(last_msg.get("content"), list):
                        updated = False
                        for b in last_msg["content"]:
                            if isinstance(b, dict) and "text" in b:
                                b["text"] = new_full_text
                                updated = True
                                break
                        if not updated:
                            last_msg["content"] = [{"text": new_full_text}]
                            return
                    else:
                        last_msg["content"] = new_full_text
                        return
                elif hasattr(last_msg, "content"):
                    setattr(last_msg, "content", new_full_text)
                    return
        except Exception as e:
            logger.warning(f"Failed in retrieve_customer_context: {e}")

    def save_support_interaction(self, event: AfterInvocationEvent):
        """Save the completed turn to memory after the agent responds."""
        try:
            agent = getattr(event, "agent", None)
            if not agent or not getattr(agent, "messages", None):
                return

            if not self.memory_id or self.memory_id == "<mem_id>":
                return

            messages = agent.messages
            user_query = None
            assistant_response = None

            for msg in reversed(messages):
                role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
                content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)

                msg_text = ""
                if isinstance(content, str):
                    msg_text = content
                elif isinstance(content, list):
                    text_blocks = []
                    for b in content:
                        if isinstance(b, dict):
                            if "text" in b:
                                text_blocks.append(b["text"])
                            elif "toolResult" in b or "tool_result" in b:
                                continue
                        elif hasattr(b, "text"):
                            text_blocks.append(getattr(b, "text"))
                    msg_text = "\n".join(text_blocks)

                if role == "assistant" and not assistant_response and msg_text:
                    assistant_response = msg_text
                elif role == "user" and not user_query and msg_text:
                    if msg_text.startswith("Customer Context:\n") and "\n\n" in msg_text:
                        msg_text = msg_text.split("\n\n", 1)[1]
                    user_query = msg_text

                if user_query and assistant_response:
                    break

            if user_query and assistant_response:
                self.memory_client.create_event(
                    memory_id=self.memory_id,
                    actor_id=self.actor_id,
                    session_id=self.session_id,
                    messages=[
                        (user_query, "USER"),
                        (assistant_response, "ASSISTANT"),
                    ],
                )
        except Exception as e:
            logger.warning(f"Failed in save_support_interaction: {e}")

    def register_hooks(self, registry: HookRegistry) -> None:  # type: ignore
        """Register both memory callbacks."""
        registry.add_callback(MessageAddedEvent, self.retrieve_customer_context)
        registry.add_callback(AfterInvocationEvent, self.save_support_interaction)


# ── TODO 6 — Knowledge Base Tool ─────────────────────────────────────────────
# Implement search_knowledge_base(query) using the @tool decorator.
#
# Steps:
#   1. Guard: if KB_ID is empty return "Knowledge base not configured."
#   2. Call _bedrock_runtime.retrieve(
#          knowledgeBaseId=KB_ID,
#          retrievalQuery={"text": query}
#      )
#   3. Extract resp["retrievalResults"]; return a message if empty
#   4. Join the text chunks with "\n---\n" and return the result
#
# The docstring is the tool description — the model uses it to decide when
# to call this tool, so keep it clear and accurate.

@tool
def search_knowledge_base(query: str) -> str:
    """
    Search the Amazon product catalog and support knowledge base.

    Call this tool whenever the customer inquires about product specifications,
    technical details, features, return and refund policies, warranty coverage,
    loyalty program tier benefits (Silver, Gold, Platinum), or order status definitions.

    Args:
        query: The specific search query or customer question to retrieve answers for.

    Returns:
        Joined text chunks containing relevant information retrieved from the knowledge base,
        or an informational status message if the knowledge base is unconfigured or has no matches.
    """
    kb_id = os.environ.get("KB_ID")
    if kb_id is None:
        kb_id = KB_ID

    if not kb_id or str(kb_id).strip() in ("", "<kbid>", "<kb_id>"):
        return "Knowledge base not configured."

    try:
        resp = _bedrock_runtime.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query}
        )
        results = resp.get("retrievalResults", [])
        if not results:
            return "No relevant information found in the knowledge base."

        chunks = []
        for item in results:
            text = item.get("content", {}).get("text", "")
            if text:
                chunks.append(text)

        if not chunks:
            return "No relevant information found in the knowledge base."

        return "\n---\n".join(chunks)
    except Exception as e:
        logger.error(f"Knowledge base search error: {e}")
        return f"Error searching knowledge base: {str(e)}"


# ── TODO 7 — Loyalty Discount Tool (Code Interpreter) ────────────────────────
# Implement calculate_loyalty_discount() using the @tool decorator.
#
# The tool must:
#   1. Build a self-contained Python code string that:
#        • Defines earn_rates: {"standard": 1, "device": 2, "fresh": 5}
#        • Defines tier_rates: {"Silver": 0.00, "Gold": 0.10, "Platinum": 0.15}
#        • Calculates points_redeemed (floor to nearest 500, cap at 50% of order)
#        • Calculates tier_discount (applied to subtotal after points)
#        • Calculates final_total, total_savings, points_earned, remaining_points
#        • Prints a JSON result dict
#   2. Execute the code with code_session(REGION).invoke("executeCode", {...})
#      using language="python" and clearContext=True
#   3. Return the first result event as a JSON string
#   4. Include a fallback that computes only the tier discount if the
#      Code Interpreter is unavailable

@tool
def calculate_loyalty_discount(
    loyalty_points: int,
    tier: str,
    order_total: float,
    product_category: str = "standard",
) -> str:
    """
    Calculate the loyalty discount for a customer order using the
    AgentCore Code Interpreter. Runs exact arithmetic in a secure sandbox.

    Args:
        loyalty_points:   Customer's current points balance
        tier:             Customer tier — Silver, Gold, or Platinum
        order_total:      Order total in USD
        product_category: standard, device, or fresh

    Returns:
        Full discount breakdown and final price
    """
    code = f'''
import json

earn_rates = {{"standard": 1, "device": 2, "fresh": 5}}
tier_rates = {{"Silver": 0.00, "Gold": 0.10, "Platinum": 0.15}}

loyalty_points = {loyalty_points}
tier = "{tier}"
order_total = {order_total}
product_category = "{product_category}"

available_points_redeemable = (loyalty_points // 500) * 500
max_points_by_cap = (int(order_total * 50) // 500) * 500
points_redeemed = max(0, min(available_points_redeemable, max_points_by_cap))

points_discount = round(points_redeemed * 0.01, 2)
subtotal_after_points = max(0.0, order_total - points_discount)

tier_rate = tier_rates.get(tier, 0.0)
tier_discount = round(subtotal_after_points * tier_rate, 2)

final_total = round(subtotal_after_points - tier_discount, 2)
total_savings = round(points_discount + tier_discount, 2)

earn_rate = earn_rates.get(product_category.lower(), 1)
points_earned = int(final_total * earn_rate)
remaining_points = loyalty_points - points_redeemed + points_earned

result = {{
    "original_order_total": order_total,
    "loyalty_points_balance": loyalty_points,
    "tier": tier,
    "product_category": product_category,
    "points_redeemed": points_redeemed,
    "points_discount_usd": points_discount,
    "subtotal_after_points": subtotal_after_points,
    "tier_discount_usd": tier_discount,
    "final_total": final_total,
    "total_savings": total_savings,
    "points_earned": points_earned,
    "remaining_points": remaining_points
}}

print(json.dumps(result))
'''

    region = os.environ.get("AWS_REGION", REGION)

    try:
        with code_session(region=region) as session:
            response = session.invoke(
                "executeCode",
                {
                    "code": code,
                    "language": "python",
                    "clearContext": True,
                },
            )

        result_str = None
        if isinstance(response, dict):
            if "stream" in response:
                for event in response["stream"]:
                    if "result" in event:
                        res_data = event["result"]
                        if isinstance(res_data, dict):
                            result_str = res_data.get("stdout") or res_data.get("result") or json.dumps(res_data)
                        else:
                            result_str = str(res_data)
                        break
                    elif "stdout" in event:
                        result_str = str(event["stdout"])
                        break
            if not result_str and "stdout" in response:
                result_str = str(response["stdout"])
            if not result_str and "result" in response:
                res_data = response["result"]
                if isinstance(res_data, dict):
                    result_str = json.dumps(res_data)
                else:
                    result_str = str(res_data)
        elif isinstance(response, (list, tuple)):
            for event in response:
                if isinstance(event, dict):
                    if "result" in event:
                        result_str = str(event["result"])
                        break
                    elif "stdout" in event:
                        result_str = str(event["stdout"])
                        break

        if result_str:
            return result_str.strip()
        return json.dumps(response)

    except Exception as e:
        logger.warning(f"Code Interpreter fallback triggered due to: {e}")
        earn_rates = {"standard": 1, "device": 2, "fresh": 5}
        tier_rates = {"Silver": 0.0, "Gold": 0.1, "Platinum": 0.15}

        available_points_redeemable = (loyalty_points // 500) * 500
        max_points_by_cap = (int(order_total * 50) // 500) * 500
        points_redeemed = max(0, min(available_points_redeemable, max_points_by_cap))

        points_discount = round(points_redeemed * 0.01, 2)
        subtotal_after_points = max(0.0, order_total - points_discount)

        tier_rate = tier_rates.get(tier, 0.0)
        tier_discount = round(subtotal_after_points * tier_rate, 2)

        final_total = round(subtotal_after_points - tier_discount, 2)
        total_savings = round(points_discount + tier_discount, 2)

        earn_rate = earn_rates.get(product_category.lower(), 1)
        points_earned = int(final_total * earn_rate)
        remaining_points = loyalty_points - points_redeemed + points_earned

        fallback_result = {
            "original_order_total": order_total,
            "loyalty_points_balance": loyalty_points,
            "tier": tier,
            "product_category": product_category,
            "points_redeemed": points_redeemed,
            "points_discount_usd": points_discount,
            "subtotal_after_points": subtotal_after_points,
            "tier_discount_usd": tier_discount,
            "final_total": final_total,
            "total_savings": total_savings,
            "points_earned": points_earned,
            "remaining_points": remaining_points,
        }
        return json.dumps(fallback_result)


SYSTEM_PROMPT = """You are a helpful, courteous AI Customer Support Assistant for an Amazon store.
Your goals are to assist customers with product inquiries, order tracking, returns & refunds, loyalty discounts, and web searches.

Tools & Guidelines:
- Use `search_knowledge_base` for questions about products, specs, return policies, warranties, and loyalty tier details.
- Use gateway tools for order status lookup and refund processing when order or customer IDs are provided.
- Use `calculate_loyalty_discount` for calculating points redemptions, tier discounts, and final totals.
- Use browser tools to navigate websites and retrieve live web content when requested.
- Pay attention to Customer Context provided at the start of queries to remember facts or customer preferences.
- Keep responses friendly, clear, concise, and helpful.
"""


# ── TODO 8 — Agent Entrypoint ─────────────────────────────────────────────────
# Implement the invoke() function decorated with @app.entrypoint.
#
# Steps:
#   1. Extract user_input, actor_id, and session_id from the payload
#      (generate a UUID if session_id is missing)
#   2. Instantiate MemoryHook for this actor/session
#   3. Instantiate AgentCoreBrowser(region=REGION)
#   4. Build the tools list: [search_knowledge_base, calculate_loyalty_discount,
#                              agent_core_browser.browser]
#   5. Connect to the Gateway via MCPClient, load gateway_tools, extend tools list
#   6. Create and invoke the Agent with all tools, hooks, and system_prompt
#   7. Return the text from the first content block of the response
#   8. Handle exceptions gracefully

@app.entrypoint
async def invoke(payload, context=None):
    """
    Main handler called by AgentCore for every incoming request.

    Expected payload keys:
      prompt      (str, required) — the customer's message
      customer_id (str, optional) — unique customer identifier
      session_id  (str, optional) — session identifier; generated if absent
    """
    try:
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {"prompt": payload}

        user_input = payload.get("prompt") or payload.get("user_input") or payload.get("input") or ""
        actor_id = payload.get("customer_id") or payload.get("actor_id") or "CUST-DEFAULT"
        session_id = payload.get("session_id") or str(uuid.uuid4())

        region = os.environ.get("AWS_REGION", REGION)
        mem_id = os.environ.get("MEMORY_ID", MEMORY_ID)
        gw_url = os.environ.get("GATEWAY_URL", GATEWAY_URL)

        memory_hook = MemoryHook(
            actor_id=actor_id,
            session_id=session_id,
            memory_client=memory_client,
            memory_id=mem_id,
        )

        agent_core_browser = AgentCoreBrowser(region=region)

        tools = [
            search_knowledge_base,
            calculate_loyalty_discount,
            agent_core_browser.browser,
        ]

        if gw_url and gw_url != "<gateway_url>" and gw_url.startswith("http"):
            try:
                mcp_client = MCPClient(lambda: streamable_http_client(gw_url))
                gateway_tools = await mcp_client.load_tools()
                for t in gateway_tools:
                    if hasattr(t, "mcp_tool") and hasattr(t.mcp_tool, "name"):
                        t._agent_tool_name = re.sub(r"[^a-zA-Z0-9_-]", "_", t.mcp_tool.name)
                tools.extend(gateway_tools)
            except Exception as e:
                logger.warning(f"Could not connect to MCP Gateway at {gw_url}: {e}")

        agent = Agent(
            model=model,
            tools=tools,
            hooks=[memory_hook],
            system_prompt=SYSTEM_PROMPT,
        )

        response = await agent.invoke_async(user_input)

        if hasattr(response, "message") and isinstance(response.message, dict):
            content = response.message.get("content", [])
            if isinstance(content, list) and content:
                for b in content:
                    if isinstance(b, dict) and "text" in b:
                        return b["text"]

        return str(response)

    except Exception as e:
        logger.error(f"Error in agent invocation: {e}", exc_info=True)
        return f"An error occurred while processing your request: {str(e)}"


# ── CLI entry point (do not modify) ──────────────────────────────────────────
def main():
    """Run one invocation from the command line for local testing."""
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", type=str)
    args = parser.parse_args()
    response = asyncio.run(invoke(json.loads(args.payload)))
    print(response)


if __name__ == "__main__":
    app.run()
    # Uncomment the line below and comment app.run() for local CLI testing:
    # main()
