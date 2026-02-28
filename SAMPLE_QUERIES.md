# Sample Test Queries & Expected Outputs

Run the app with `python app.py`, then open **http://127.0.0.1:5050**. Or run all samples at once: `python run_sample_queries.py`.

---

## 1. Specific queries (no session)

| Query | What you get |
|-------|----------------|
| **What is the status of Evergreen Public Services in Austin CO?** | Single account (Evergreen), full evidence: profile, status, emails, calls. Status: `application_submitted`. |
| **Tell me about Harborline Hotel Group Inc.** | Single account (Harborline), profile + status + emails/calls. Status: `policy_bound`. |
| **Which accounts are in Colorado?** | List of account names in that state (no single account), e.g. *"Accounts matching: Evergreen Public Services Inc., Evergreen Public Services, Inc., Lone Star Child Care Center Inc., ..."* |

---

## 2. Session-aware flow: Company A → Company B → “from that”

Use the **same session** (same browser/tab; session is stored in a cookie). Ask in this order:

| Step | Query | Expected behavior |
|------|--------|-------------------|
| **[1] Company A** | *What is the status of Evergreen Public Services in Austin CO?* | Reply is about **Evergreen**. The agent’s “focus” is now Evergreen. |
| **[2] Company B (switch)** | *Tell me about Harborline Hotel Group Inc.* | Reply is about **Harborline**. Focus switches to Harborline. |
| **[3] Session: “from that”** | *From that company, who was the person of contact?* | Reply is about **Harborline** (the last focused company): *"Primary contact(s): Sam Samson, Alex Agent, Sam Agent."* plus account summary. |
| **[4] Session: “that one”** | *What is the status of that one?* | Still **Harborline**: status `policy_bound` and evidence. |
| **[5] Session: “contact for that”** | *Who was the contact for that?* | Again **Harborline** and its contacts. |

So “that” / “from that” / “that company” / “that one” always refer to the **last account you asked about** in that session.

---

## 3. Other session phrases that resolve to last account

- *From that company, who was the person of contact?*
- *What is the status of that one?*
- *Who was the contact for that?*
- *It* / *That account* / *This account* (exact phrases)

---

## 4. Disambiguation

If a name matches multiple accounts, the agent asks you to pick:

- **Query:** *What about Skyline Protective Services?*  
- **Reply:** *"Multiple accounts match. Which one do you mean? Skyline Protective Services, Skyline Protective Services, Inc., Skyline Protective Services LLC, ..."*

After you pick (e.g. by asking *Tell me about Skyline Protective Services LLC*), the next “from that” will refer to that chosen account.

---

## 5. Run all samples from the command line

```bash
python run_sample_queries.py
```

This uses a single session and prints each query and reply so you can see the exact outputs and the A → B → “from that” behavior.
