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

## 4. Written Reflection (Design Decisions & Production Considerations)

### Design Decision & Tool Selection
In building the Customer Support AI Agent, an essential architectural decision was integrating the **Amazon Bedrock AgentCore Code Interpreter** (`code_session`) for loyalty discount calculations rather than relying on direct LLM arithmetic. Large language models frequently suffer from calculation drift and rounding errors when evaluating multi-tiered business logic involving tiered percentages, floor-based point redemption (500-point increments), and order value caps. By executing calculation logic in an isolated, deterministic Python sandbox, the agent guarantees 100% mathematical precision and transparency for customer billing calculations while falling back gracefully to static tier discounts if the sandbox is unreachable.

### Challenge Encountered & Resolution
A concrete challenge arose when dynamically registering external tools from the **AgentCore Gateway** over Model Context Protocol (MCP). The AWS Bedrock Converse API enforces a strict regular expression pattern (`^[a-zA-Z0-9_-]+$`) on all registered tool names. Several dynamically generated tool identifiers from the Gateway and API Gateway targets included invalid characters and spaces, triggering schema validation rejections during agent invocation. To resolve this without breaking remote JSON-RPC routing, I modified the registration pipeline in `main.py` to decouple the agent-facing tool name from the underlying MCP wire name. I applied regex sanitization (`re.sub(r"[^a-zA-Z0-9_-]", "_", ...)`) to `_agent_tool_name` for Bedrock compatibility while keeping `mcp_tool.name` untouched so the Gateway could correctly route tool execution requests to the underlying `order-tracker` and `refund-processor` Lambda functions.

### Production Considerations: Security, Scalability & Cost
Transitioning this agent to an enterprise production environment introduces several vital operational requirements:
1. **Security & Governance**: The development AgentCore Gateway authorizer should be upgraded from `NONE` to OAuth2/IAM SigV4 token-based authentication. Additionally, Amazon Bedrock Guardrails should be configured to redact sensitive Personally Identifiable Information (PII) such as credit card details and enforce content moderation.
2. **Scalability & Persistence**: In-memory mock data within the Lambda functions must be replaced with Amazon DynamoDB using strong consistency and transaction locks to handle concurrent customer orders and refunds safely.
3. **Cost & Observability**: Cost is optimized by deploying the lightweight Amazon Nova Lite model and implementing semantic response caching to minimize redundant LLM calls. Real-time observability requires CloudWatch metric alarms for runtime error spikes and AWS X-Ray distributed tracing across AgentCore and downstream services.
