# 20 Test Queries – Mixed Types

Use these in the chat UI (**http://127.0.0.1:5050**) or run all 20 in one go:

```bash
python run_20_queries.py
```

For **session-aware** queries (7–11, and 17), use the same session (same browser tab or the script above, which uses one session).

---

## 1. Very specific (6)

Single account, clear name and/or location.

| # | Query |
|---|--------|
| 1 | What is the status of Evergreen Public Services in Austin CO? |
| 2 | Tell me about Harborline Hotel Group Inc. |
| 3 | Who is the contact for Skyline Protective Services in North Carolina? |
| 4 | What's the status of Summerside Child Care in Houston Pennsylvania? |
| 5 | Give me the status of Lone Star Child Care Center in Colorado. |
| 6 | Tell me about Harborline Hotel Group in Austin Massachusetts. |

---

## 2. Session-aware (5)

Use **after** asking about a specific account in the same session. “That” = last account you asked about.

| # | Query | Use after |
|---|--------|-----------|
| 7 | From that company, who was the person of contact? | Any account question (e.g. 1 or 2) |
| 8 | What is the status of that one? | Any account question |
| 9 | Who was the contact for that? | Any account question |
| 10 | Tell me more about that account. | Any account question |
| 11 | What happened with that application? | Any account question |

---

## 3. List / filter / ambiguous (5)

Industry, status, or location filters; may return multiple accounts or a list.

| # | Query |
|---|--------|
| 12 | Which accounts are in Colorado? |
| 13 | List all public sector accounts. |
| 14 | Which accounts are awaiting documents? |
| 15 | Show me hospitality accounts that are policy bound. |
| 16 | Retail accounts which require documents. |

---

## 4. Conversational / vague (4)

Casual wording, “that” + location or type, or follow-up style.

| # | Query |
|---|--------|
| 17 | What happened to that childcare center in California? |
| 18 | Hey, what's going on with the hotel group in Austin? |
| 19 | Any updates on the public sector account we were looking at? |
| 20 | What about the defense contractor in Chicago? |

**Note:** 17 uses “that” and follows session focus (last account). 19 may resolve by industry and return a list. 18 and 20 resolve by industry + location. Query 3 may need an exact company name; query 4 may trigger disambiguation.

---

## Quick copy-paste (all 20)

```
What is the status of Evergreen Public Services in Austin CO?
Tell me about Harborline Hotel Group Inc.
Who is the contact for Skyline Protective Services in North Carolina?
What's the status of Summerside Child Care in Houston Pennsylvania?
Give me the status of Lone Star Child Care Center in Colorado.
Tell me about Harborline Hotel Group in Austin Massachusetts.
From that company, who was the person of contact?
What is the status of that one?
Who was the contact for that?
Tell me more about that account.
What happened with that application?
Which accounts are in Colorado?
List all public sector accounts.
Which accounts are awaiting documents?
Show me hospitality accounts that are policy bound.
Retail accounts which require documents.
What happened to that childcare center in California?
Hey, what's going on with the hotel group in Austin?
Any updates on the public sector account we were looking at?
What about the defense contractor in Chicago?
```
