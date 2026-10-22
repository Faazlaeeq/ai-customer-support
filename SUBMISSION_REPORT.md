# Customer Support AI Agent — Project Submission Report

**Course**: Udacity AWS AI Engineering Nanodegree  
**Project**: Building a Customer Support AI Agent with Amazon Bedrock AgentCore  
**Model**: Amazon Nova 2 Lite (`global.amazon.nova-2-lite-v1:0`)  
**AWS Region**: `us-east-1`  

---

## 1. System Architecture & Setup Overview

The AI Customer Support Agent is built on **Strands** and deployed using **Amazon Bedrock AgentCore**. It integrates multiple enterprise capabilities into a single conversational assistant:

- **Agent Framework & Core App**: Handled by `BedrockAgentCoreApp` in `main.py`.
- **Retrieval-Augmented Generation (RAG)**: Connects to a managed **Amazon Bedrock Knowledge Base** (`JJWDU9V7ED`) populated with `product_catalog.txt` to answer catalog, warranty, and policy inquiries.
- **REST API Tool Integration**: Uses **API Gateway REST API** (`OrderTrackerAPI`) proxying to the `order-tracker` AWS Lambda function to handle order and customer profile lookups.
- **Direct Lambda MCP Integration**: Connects to the `refund-processor` AWS Lambda function exposed through **AgentCore Gateway** (`https://gateway-quick-start-fc827b-pkczfb8f8n.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp`) for processing refunds.
- **Code Interpreter Sandbox**: Invokes `code_session()` for exact mathematical computations of loyalty points redemption, tier discounts (Silver, Gold, Platinum), and point balances.
- **Browser Automation**: Integrates `AgentCoreBrowser` to navigate live websites and extract page contents.
- **Long-Term Cross-Session Memory**: Implements a `MemoryHook` subclassing `HookProvider` that interfaces with **AgentCore Memory** (`memory_kca4b-vE8cBY90vg`) using `SEMANTIC` and `USER_PREFERENCE` strategies to recall user preferences across sessions.

---

## 2. Resource Configuration Summary

| Resource Type | Resource Identifier / Name | Description |
| :--- | :--- | :--- |
| **AWS Region** | `us-east-1` | N. Virginia Region |
| **Foundation Model** | `global.amazon.nova-2-lite-v1:0` | Amazon Nova 2 Lite Inference Profile |
| **AgentCore Gateway URL** | `https://gateway-quick-start-fc827b-pkczfb8f8n.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp` | AgentCore MCP Gateway (NONE Authorizer) |
| **Knowledge Base ID** | `JJWDU9V7ED` | `CustomerSupportKB` syncing `product_catalog.txt` |
| **Memory Resource ID** | `memory_kca4b-vE8cBY90vg` | `CustomerSupportMemory` (Semantic & Preferences) |
| **Order Tracker API** | `OrderTrackerAPI` (`prod` stage) | API Gateway REST API proxying `order-tracker` Lambda |
| **Refund Processor Lambda** | `refund-processor` | Direct Lambda target in AgentCore Gateway |

---

## 3. Functional Test Execution & Verification

All six required test scenarios were executed end-to-end and verified against the expected behavior.

### Test 1 — Order Tracking
- **Command**:
  ```powershell
  uv run agentcore invoke '{\"prompt\": \"Can you track order ORD-001?\", \"customer_id\": \"CUST-123\", \"session_id\": \"t1\"}' --dev
  ```
- **Tool Invoked**: `target-quick-start-5e0c73___Get_Orders_by_order_id` (API Gateway REST Target)
- **Verified Response**:
  ```text
  Your order ORD-001 has been successfully tracked:
  - Status: SHIPPED
  - Items: 1x Wireless Headphones Pro ($89.99)
  - Carrier: UPS
  - Tracking Number: TRK987654321
  - Estimated Delivery: September 27, 2026
  ```

---

### Test 2 — Refund Processing
- **Command**:
  ```powershell
  uv run agentcore invoke '{\"prompt\": \"I want to return my Kindle Paperwhite (ORD-002). Please initiate a refund.\", \"customer_id\": \"CUST-123\", \"session_id\": \"t2\"}' --dev
  ```
- **Tool Invoked**: `target-quick-start-odmfpw___initiate_refund` (Lambda Target)
- **Verified Response**:
  ```text
  Great news! Your refund for the Kindle Paperwhite (Order #ORD-002) has been successfully approved.
  - Refund ID: REF-WKDA0OC7
  - Status: APPROVED
  - Timeline: 3-5 business days
  ```

---

### Test 3 — Knowledge Base (RAG)
- **Command**:
  ```powershell
  uv run agentcore invoke '{\"prompt\": \"What are the benefits of the Platinum loyalty tier?\", \"customer_id\": \"CUST-123\", \"session_id\": \"t3\"}' --dev
  ```
- **Tool Invoked**: `search_knowledge_base`
- **Verified Response**:
  ```text
  The Platinum loyalty tier offers the following benefits:
  - Free same-day shipping on eligible orders
  - 15% discount on purchases (compared to Gold's 10%)
  - Priority customer support for faster assistance
  ```

---

### Test 4 — Memory (Cross-Session Recall)

- **Session A (Store Facts & Preferences)**:
  ```powershell
  uv run agentcore invoke '{\"prompt\": \"Hi, I am Jane. I prefer concise responses.\", \"customer_id\": \"CUST-123\", \"session_id\": \"s-A\"}' --dev
  ```
- *Wait 30 seconds for background semantic memory processing.*

- **Session B (New Session Verification)**:
  ```powershell
  uv run agentcore invoke '{\"prompt\": \"Do you remember my name and communication preference?\", \"customer_id\": \"CUST-123\", \"session_id\": \"s-B\"}' --dev
  ```
- **Verified Response**:
  ```text
  Hello Jane! Yes, I remember your name and communication preference. You prefer concise responses.
  How can I assist you today?
  ```

---

### Test 5 — Loyalty Discount Calculation
- **Command**:
  ```powershell
  uv run agentcore invoke '{\"prompt\": \"I am a Gold member with 4250 points. Calculate my discount on a $150 standard order.\", \"customer_id\": \"CUST-123\", \"session_id\": \"t5\"}' --dev
  ```
- **Tool Invoked**: `calculate_loyalty_discount` (Code Interpreter Sandbox)
- **Verified Response**:
  ```text
  Original Order Total: $150.00
  Loyalty Points Redeemed: 4,000 points ($40.00 discount)
  Subtotal After Points: $110.00
  Gold Tier Discount (10%): $11.00
  Final Total: $99.00
  Total Savings: $51.00
  Points Earned: 99 points
  Remaining Points Balance: 349 points
  ```

---

### Test 6 — Web Browser Tool
- **Command**:
  ```powershell
  uv run agentcore invoke '{\"prompt\": \"Go to https://www.udacity.com and tell me the page title.\", \"customer_id\": \"CUST-123\", \"session_id\": \"t6\"}' --dev
  ```
- **Tool Invoked**: `AgentCoreBrowser` (`browser`)
- **Verified Response**:
  ```text
  The page title for https://www.udacity.com is:
  "Learn the Latest Tech Skills; Advance Your Career | Udacity"
  ```

---

## 4. Written Reflection

### Design Decision
A key architectural decision was separating the **agent-facing tool name** from the **underlying MCP wire name** when registering tools dynamically from the AgentCore Gateway. The Bedrock Converse API enforces a strict regular expression constraint on tool names (`[a-zA-Z0-9_-]+`), rejecting spaces or special characters. To maintain compatibility without breaking the remote Gateway server's JSON-RPC dispatch, I updated `main.py` so that `t._agent_tool_name` is sanitized using regex substitution (`re.sub(r"[^a-zA-Z0-9_-]", "_", ...)`), while `t.mcp_tool.name` retains the exact wire string expected by the remote MCP Gateway target.

### Challenge & Solution
One challenge encountered during implementation was handling dynamic template variables in memory strategy namespaces. The AgentCore Memory service returned namespace templates containing `{memoryStrategyId}` and `{actorId}` (e.g., `/strategies/{memoryStrategyId}/actors/{actorId}/`). Calling `str.format(actorId=self.actor_id)` directly raised a `KeyError: 'memoryStrategyId'`. I solved this by extending `get_namespaces()` to extract `memoryStrategyId` from each strategy definition dictionary returned by `mem_client.get_memory_strategies()`, pre-populating `{memoryStrategyId}` before returning the template map to `MemoryHook`.

### Production Extensions
To transition this agent to a production enterprise environment, I would:
1. **Secure the Gateway with Authentication**: Upgrade the AgentCore Gateway from `NONE` authorizer to OAuth2 / IAM JWT authorization to ensure all tool invocations are authenticated.
2. **Replace Mock Databases**: Connect the `order-tracker` and `refund-processor` Lambda functions to persistent storage such as Amazon DynamoDB with transactional locks.
3. **Observability & Guardrails**: Add Amazon Bedrock Guardrails for PII redaction/content filtering and enable AWS X-Ray tracing across the AgentCore runtime and Lambda execution calls.
