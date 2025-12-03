# Neo4j Quick Start Guide

## ✅ Current Status

- **Neo4j is running**: Container healthy at ports 7474 (Browser) and 7687 (Bolt)
- **Data synced**: 75 trials, 111 conditions, 1969 locations, 2 patients
- **API endpoints working**: Fixed the smart-match endpoint bug
- **Flask backend**: Running on port 5001

---

## 🔍 The 500 Error - FIXED!

### What was wrong:
The `find_matching_trials()` function in `graph_models.py` had a bug where:
- It tried to count variables (`c`, `l`) that didn't exist when no conditions/location were provided
- The Cypher query syntax was invalid when OPTIONAL MATCH clauses were followed by WHERE

### What was fixed:
✅ Rewrote the query to properly handle empty criteria
✅ Moved WHERE clause before OPTIONAL MATCH clauses
✅ Used dynamic scoring (`0` when no criteria provided)
✅ Now returns trials even with matchScore=0

---

## 🚀 How to Access Neo4j

### 1. **Neo4j Browser UI**
Open in your browser: http://localhost:7474

**Login credentials:**
- Username: `neo4j`
- Password: `clinect_neo4j_password`

### 2. **Test Queries in Browser**

Try these Cypher queries:

```cypher
// See all trials
MATCH (t:Trial) RETURN t LIMIT 10

// See trial-condition relationships
MATCH (t:Trial)-[:TREATS]->(c:Condition)
RETURN t.nctId, t.title, c.name
LIMIT 25

// Find diabetes trials
MATCH (t:Trial)-[:TREATS]->(c:Condition)
WHERE c.nameNormalized CONTAINS 'diabetes'
RETURN t.nctId, t.title, t.status, c.name
LIMIT 10

// See recruiting trials
MATCH (t:Trial)
WHERE t.status = 'RECRUITING'
RETURN t.nctId, t.title
LIMIT 10

// Visualize the graph
MATCH (t:Trial)-[:TREATS]->(c:Condition)
RETURN t, c
LIMIT 50
```

---

## 📡 How to Use the API from Frontend

### Step 1: Make sure you're authenticated

The `/api/trials/smart-match` endpoint requires authentication. You need to:

1. Log in with Firebase first
2. The backend will create a session cookie
3. Include `credentials: 'include'` in your fetch requests

### Step 2: Call the smart-match endpoint

**Example request:**

```typescript
const response = await fetch('http://localhost:5001/api/trials/smart-match', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  credentials: 'include',  // IMPORTANT: Include session cookie
  body: JSON.stringify({
    conditions: ['Diabetes Type 1'],  // Use exact condition names
    location: 'Boston, MA',            // Optional
    age: 45,                          // Optional (not used yet)
    gender: 'FEMALE',                 // Optional (not used yet)
    maxDistance: 50                   // Optional (not implemented yet)
  })
});

const data = await response.json();
console.log(data);
```

**Example response:**

```json
{
  "success": true,
  "matches": [
    {
      "nctId": "NCT06894784",
      "title": "Trial of Diabetes Type 1 Treatment",
      "status": "RECRUITING",
      "phase": ["PHASE3"],
      "matchScore": 10
    }
  ],
  "totalMatches": 1,
  "method": "graph"
}
```

---

## 🎯 Important Notes About Condition Matching

### Exact vs Partial Matching

The current implementation uses **exact matching** (with case-insensitive support):

**Works:**
- `"Diabetes Type 1"` → Matches exactly
- `"diabetes type 1"` → Matches (case-insensitive via nameNormalized)
- `"Diabetic Foot Ulcer"` → Matches exactly

**Doesn't work:**
- `"diabetes"` → Won't match "Diabetes Type 1" or "Diabetes Type 2"
- `"cancer"` → Won't match "Small Cell Lung Cancer"

### Why?

The query uses: `c.name IN $conditions OR c.nameNormalized IN $conditions_normalized`

This is exact matching, not partial matching (`CONTAINS`).

### Future Enhancement

To enable partial/fuzzy matching (recommended), we could change the query to:

```cypher
WHERE ANY(cond IN $conditions WHERE c.nameNormalized CONTAINS toLower(cond))
```

This would allow:
- `"diabetes"` to match `"Diabetes Type 1"`, `"Diabetic Foot Ulcer"`, etc.
- `"cancer"` to match `"Small Cell Lung Cancer"`, `"Breast Cancer"`, etc.

---

## 🧪 Testing the Endpoint

### Using curl (after logging in):

```bash
# 1. Login first (get session cookie)
curl -X POST http://localhost:5001/api/firebase-login \
  -H "Content-Type: application/json" \
  -d '{"idToken": "YOUR_FIREBASE_TOKEN"}' \
  -c cookies.txt

# 2. Use smart-match with session cookie
curl -X POST http://localhost:5001/api/trials/smart-match \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "conditions": ["Diabetes Type 1"],
    "location": "Boston, MA"
  }'
```

### Using Python:

```python
from graph_models import find_matching_trials

# Direct function call (bypasses auth)
results = find_matching_trials(
    conditions=['Diabetes Type 1'],
    location_id='Boston, MA',
    status='RECRUITING',
    limit=10
)

print(f"Found {len(results)} trials")
for trial in results:
    print(f"{trial['nctId']}: {trial['title']} (Score: {trial['matchScore']})")
```

---

## 🔧 Troubleshooting

### "500 Internal Server Error"

**Possible causes:**
1. ✅ **Fixed**: Query syntax error (already fixed in this session)
2. Neo4j container not running: `docker ps | grep neo4j`
3. No data in Neo4j: Run `uv run sync_to_graph.py`
4. Not authenticated: Make sure you're logged in

### "Not authenticated" error

You need to log in first! The endpoint requires `session['user_id']`.

**From frontend:**
```typescript
// Login first
await fetch('/api/firebase-login', {
  method: 'POST',
  body: JSON.stringify({ idToken: firebaseToken }),
  credentials: 'include'
});

// Then use smart-match
await fetch('/api/trials/smart-match', {
  method: 'POST',
  body: JSON.stringify({ conditions: ['diabetes'] }),
  credentials: 'include'  // Include session cookie
});
```

### Empty results (matchScore=0)

**Possible causes:**
1. Condition name doesn't exactly match database
2. No RECRUITING trials for that condition
3. Trials exist but with different status

**Check what conditions exist:**
```python
from neo4j_db import execute_query

results = execute_query(
    "MATCH (c:Condition) WHERE c.nameNormalized CONTAINS 'diabetes' RETURN c.name"
)
for r in results:
    print(r['c.name'])
```

---

## 📊 Current Database Stats

Run anytime:
```bash
uv run python -c "from neo4j_db import get_stats; print(get_stats())"
```

**Current data (as of this session):**
- Nodes: 2,157
- Relationships: 3,711
- Trials: 75
- Conditions: 111
- Locations: 1,969
- Patients: 2

**RECRUITING trials:** 4 out of 75

---

## 🎨 Frontend Integration

See [FRONTEND_NEO4J_INSTRUCTIONS.md](FRONTEND_NEO4J_INSTRUCTIONS.md) for:
- Complete API documentation
- TypeScript types
- React component examples
- UI/UX recommendations

---

## 🐛 Known Limitations

1. **Exact matching only** - Need to implement fuzzy/partial matching
2. **Limited RECRUITING trials** - Only 4 in current dataset
3. **Age/gender filtering** - Not implemented yet in graph queries
4. **Distance-based search** - maxDistance parameter not used yet
5. **Condition hierarchy** - Not populated yet (requires medical ontology)

---

## ✅ Next Steps

1. **Test from your Next.js frontend** with real Firebase auth
2. **Implement fuzzy condition matching** for better user experience
3. **Populate more trial data** - Run searches to cache more trials
4. **Add condition hierarchy** - Link related conditions (e.g., "Diabetes" → "Type 1 Diabetes")
5. **Implement age/gender filtering** in Neo4j queries

---

Need help? Check:
- Neo4j Browser: http://localhost:7474
- Flask backend logs
- `NEO4J_QUICK_START.md` (this file)
- `FRONTEND_NEO4J_INSTRUCTIONS.md`
