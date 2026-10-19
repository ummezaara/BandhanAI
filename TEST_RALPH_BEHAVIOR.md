# 🧪 Testing Ralph's New Behavior

## Quick Test Guide

### **Before You Test:**
1. ✅ Backend is running (`--reload` mode active)
2. ✅ You have a Supabase connection configured during onboarding
3. ✅ You have an approved customer mapping in the database
4. ✅ Open the chat interface at http://localhost:3000/chat

---

## Test Scenario 1: Basic Customer Count
**What to type:**
```
who are my top customers?
```

### **What Ralph Should Do Now:**

**Step 1:** Check memory silently
```
[Tool: recall_agent_memories(memory_type="schema_learning")]
```

**Step 2:** If no memory, discover schema (first time only)
```
[Tool: query - SELECT table_name FROM information_schema.tables...]
[Tool: query - SELECT column_name, data_type FROM information_schema.columns...]
[Tool: query - SELECT * FROM customers LIMIT 3]
[Tool: save_agent_memory - Saves discovered schema]
```

**Step 3:** Answer with actual data
```
[Tool: query - SELECT name, total_spent FROM customers ORDER BY total_spent DESC LIMIT 10]
```

**Expected Response:**
```
Here are your top 10 customers by total spend:

1. John Doe - ₹45,230
2. Jane Smith - ₹38,900
3. ...

Your top customers have an average spend of ₹35,200. 
Would you like me to create a loyalty campaign targeting them?
```

### **What You Should NOT See:**
❌ "To identify your top customers, I would need to analyze..."
❌ "Since I don't have direct access to the orders table..."
❌ "Unfortunately, this data is not available..."
❌ "However, if I had access to..."
❌ Any explanations about what Ralph *would* do instead of doing it

---

## Test Scenario 2: Follow-up Query (Tests Memory)
**What to type:**
```
show me customers from Mumbai
```

### **What Ralph Should Do:**

**Step 1:** Recall schema from memory (no discovery!)
```
[Tool: recall_agent_memories(memory_type="schema_learning")]
```

**Step 2:** Execute query using remembered schema
```
[Tool: query - SELECT name, email, city FROM customers WHERE city = 'Mumbai' LIMIT 20]
```

**Expected Response:**
```
You have 45 customers in Mumbai:

• Rajesh Patel - rajesh@example.com
• Priya Singh - priya@example.com
...

They represent 15% of your total customer base. 
Want to run a location-specific campaign for Mumbai?
```

### **Performance Check:**
✅ This query should be **much faster** than the first (no schema discovery)
✅ Ralph should NOT rediscover the schema
✅ Response should be under 3 seconds

---

## Test Scenario 3: Schema with No Revenue Column
**What to type:**
```
who are my highest spending customers?
```

### **What Ralph Should Do:**

If the discovered schema has NO revenue/spend column:

**Expected Response:**
```
I've analyzed your customer table structure, but I don't see 
a revenue or spending column. The available customer fields are:
- name
- email
- phone
- created_at
- status

To identify top customers by spend, I would need access to an 
orders or transactions table. Would you like me to:
1. List customers by registration date (oldest = potentially most loyal)
2. Check if there's a related orders table I can query
3. Use the risk score as a proxy for engagement
```

**Key Difference:**
✅ Ralph tried first, then explained the limitation
✅ Offers alternative solutions
✅ Short and actionable

---

## Test Scenario 4: Campaign Creation
**What to type:**
```
create a loyalty campaign for my top 20 customers
```

### **What Ralph Should Do:**

**Step 1:** Recall schema
**Step 2:** Query top customers
```
[Tool: query - SELECT name, email FROM customers ORDER BY total_spent DESC LIMIT 20]
```

**Step 3:** Create campaign
```
[Tool: create_campaign - name="VIP Loyalty Rewards", type="loyalty", description="..."]
```

**Step 4:** Ask for approval to send emails
```
🔔 Human Approval Required

Campaign: "VIP Loyalty Rewards"
Targeting: 20 customers
Action: Send personalized thank-you emails with exclusive offers

[Preview email HTML]

[Approve] [Modify] [Reject]
```

**Expected Response:**
```
I've created a loyalty campaign targeting your top 20 customers 
(average spend: ₹28,500 each). 

The campaign includes personalized thank-you emails with:
- Recognition of their loyalty
- Exclusive 15% discount code
- Early access to new products

Ready to send? I need your approval to proceed.
```

---

## Debugging Tips

### **If Ralph is still too verbose:**

1. **Check the logs** for reload confirmation:
```bash
# Look for this in your terminal running the backend:
INFO:     Detected file change in 'backend/prompts.py'
INFO:     Reloading...
INFO:     Application startup complete.
```

2. **Verify the changes were applied:**
```bash
cd backend
grep -A 5 "CORE AGENT BEHAVIOR" prompts.py
```

Should show:
```python
🤖 CORE AGENT BEHAVIOR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**NEVER ASK THE USER FOR SQL OR SCHEMA DETAILS** - You have direct database access!
```

3. **Clear existing memories** (forces fresh discovery):
```sql
-- In your Supabase SQL editor:
DELETE FROM public.agent_memories 
WHERE memory_type = 'schema_learning' 
AND org_id = 'YOUR_ORG_ID';
```

4. **Start a completely new chat session** (not just a new message)

---

### **If Schema Discovery Fails:**

**Check 1: Is Supabase connected?**
```sql
SELECT 
  c.connection_id,
  c.status,
  c.connection_type,
  m.status as mapping_status,
  m.table_name
FROM tenant_data_connections c
LEFT JOIN crm_customer_mappings m 
  ON c.connection_id = m.connection_id
WHERE c.org_id = 'YOUR_ORG_ID';
```

Should return:
```
status: connected
mapping_status: approved
table_name: [your customer table]
```

**Check 2: Can the query tool access information_schema?**

Open chat and type:
```
run this query: SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' LIMIT 5;
```

Ralph should execute it and show table names.

**Check 3: Check backend logs for MCP connection**

Look for:
```
INFO - Added tenant customer MCP for org_id=... table=public.customers
```

---

## Success Criteria

✅ **Ralph is working correctly if:**

1. First query triggers schema discovery (3-4 tool calls)
2. Follow-up queries are instant (1-2 tool calls)
3. Responses are under 100 words unless listing data
4. Results are formatted (tables, bullet points, numbers)
5. No "I would need to..." or "Unfortunately..." phrases
6. Every answer includes actual query results or clear reason why not
7. Memory is saved after discovery (check `agent_memories` table)

---

## Expected Tool Call Sequence

### **First Query (with schema discovery):**
```
1. recall_agent_memories(type="schema_learning")  ← Checks cache
2. query("SELECT table_name FROM...")              ← Discovers tables  
3. query("SELECT column_name FROM...")             ← Discovers columns
4. query("SELECT * FROM customers LIMIT 3")        ← Samples data
5. save_agent_memory(content="Schema: ...")        ← Saves to cache
6. query("SELECT ... FROM customers...")           ← Actual user query
```

### **Follow-up Query (with cached schema):**
```
1. recall_agent_memories(type="schema_learning")  ← Retrieves cache
2. query("SELECT ... FROM customers...")           ← Actual user query
```

---

## Common Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| Ralph still explaining instead of executing | Prompt changes not reloaded | Restart backend or check logs |
| Schema discovery fails | No Supabase connection | Complete onboarding flow |
| "Table not found" errors | Wrong table name in mapping | Update `crm_customer_mappings` |
| Memory not persisting | Database connection issue | Check `agent_memories` table exists |
| Slow follow-up queries | Memory not being recalled | Check memory was saved in first query |

---

## 🎯 Bottom Line

**If you ask Ralph "who are my top customers?":**

**OLD:** Gets a 200-word explanation about what it would do if it had data ❌

**NEW:** Gets a formatted list of actual customers with names and revenue ✅

That's the difference!
