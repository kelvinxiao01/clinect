# Frontend Integration Instructions - Neo4j Graph-Based Matching

## Overview

The backend now uses **Neo4j graph database** for intelligent clinical trial matching. This enables relationship-based queries that go beyond simple text search, including:

- **Smart matching** based on medical condition relationships
- **Related trials** discovery through shared conditions/locations
- **Personalized recommendations** based on patient profiles
- **Condition hierarchies** for broader/narrower search

## New Backend API Endpoints

### 1. **POST /api/trials/smart-match** - Graph-Based Trial Matching

**Purpose:** Find trials using intelligent graph traversal instead of basic search

**Request:**
```typescript
POST /api/trials/smart-match
Content-Type: application/json

{
  "conditions": ["diabetes", "heart disease"],
  "location": "Boston, MA",
  "age": 45,
  "gender": "FEMALE",
  "maxDistance": 50  // kilometers, optional
}
```

**Response:**
```typescript
{
  "success": true,
  "matches": [
    {
      "nctId": "NCT12345678",
      "title": "Study of Diabetes Treatment",
      "status": "RECRUITING",
      "phase": ["PHASE3"],
      "matchScore": 35  // Higher = better match
    },
    // ... more matches
  ],
  "totalMatches": 15,
  "method": "graph"
}
```

**Match Score Calculation:**
- Condition match: +10 points per matched condition
- Location match: +5 points
- Trials are ranked by relevance

---

### 2. **GET /api/trials/:nctId/related** - Find Related Trials

**Purpose:** Discover trials related to a specific trial through graph relationships

**Request:**
```typescript
GET /api/trials/NCT12345678/related?limit=10
```

**Response:**
```typescript
{
  "success": true,
  "nctId": "NCT12345678",
  "relatedTrials": [
    {
      "nctId": "NCT87654321",
      "title": "Alternative Diabetes Study",
      "status": "RECRUITING",
      "phase": ["PHASE2"],
      "sharedConditions": ["Diabetes Mellitus", "Type 2 Diabetes"],
      "sharedLocations": ["Boston, MA"],
      "relationshipScore": 9  // Higher = stronger relationship
    },
    // ... more related trials
  ],
  "totalFound": 10
}
```

**Relationship Types:**
- Shared conditions (most important)
- Same geographic locations
- Similar trial phases

---

### 3. **GET /api/recommendations** - Personalized Recommendations

**Purpose:** Get trial recommendations based on user's medical history

**Request:**
```typescript
GET /api/recommendations?limit=10
```

**Response:**
```typescript
{
  "success": true,
  "recommendations": [
    {
      "nctId": "NCT11111111",
      "title": "Heart Disease Prevention Trial",
      "status": "RECRUITING",
      "phase": ["PHASE3"],
      "matchingConditions": ["heart disease", "hypertension"],
      "matchScore": 2  // Number of condition matches
    },
    // ... more recommendations
  ],
  "totalFound": 8
}
```

**How it works:**
- Uses patient's saved conditions from medical history
- Finds trials treating those conditions
- Excludes already-saved trials
- Ranks by number of matching conditions

---

### 4. **GET /api/conditions/hierarchy** - Condition Relationships

**Purpose:** Get parent/child relationships for medical conditions (future use)

**Request:**
```typescript
GET /api/conditions/hierarchy?condition=Type%202%20Diabetes
```

**Response:**
```typescript
{
  "success": true,
  "hierarchy": {
    "condition": "Type 2 Diabetes",
    "parents": ["Diabetes Mellitus", "Metabolic Disorders"],
    "children": ["Insulin-Resistant Diabetes"]
  }
}
```

---

## Frontend Implementation Guide

### TypeScript Types

Create `lib/types/graph.ts`:

```typescript
export interface SmartMatchRequest {
  conditions: string[];
  location?: string;
  age?: number;
  gender?: string;
  maxDistance?: number;
}

export interface MatchResult {
  nctId: string;
  title: string;
  status: string;
  phase: string[];
  matchScore: number;
}

export interface SmartMatchResponse {
  success: boolean;
  matches: MatchResult[];
  totalMatches: number;
  method: string;
}

export interface RelatedTrial {
  nctId: string;
  title: string;
  status: string;
  phase: string[];
  sharedConditions: string[];
  sharedLocations: string[];
  relationshipScore: number;
}

export interface RelatedTrialsResponse {
  success: boolean;
  nctId: string;
  relatedTrials: RelatedTrial[];
  totalFound: number;
}

export interface Recommendation {
  nctId: string;
  title: string;
  status: string;
  phase: string[];
  matchingConditions: string[];
  matchScore: number;
}

export interface RecommendationsResponse {
  success: boolean;
  recommendations: Recommendation[];
  totalFound: number;
}
```

### API Service Functions

Create `lib/api/graphMatching.ts`:

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001';

export async function smartMatch(criteria: SmartMatchRequest): Promise<SmartMatchResponse> {
  const response = await fetch(`${API_BASE}/api/trials/smart-match`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(criteria)
  });

  if (!response.ok) {
    throw new Error('Smart match failed');
  }

  return response.json();
}

export async function getRelatedTrials(nctId: string, limit = 10): Promise<RelatedTrialsResponse> {
  const response = await fetch(
    `${API_BASE}/api/trials/${nctId}/related?limit=${limit}`,
    { credentials: 'include' }
  );

  if (!response.ok) {
    throw new Error('Failed to fetch related trials');
  }

  return response.json();
}

export async function getRecommendations(limit = 10): Promise<RecommendationsResponse> {
  const response = await fetch(
    `${API_BASE}/api/recommendations?limit=${limit}`,
    { credentials: 'include' }
  );

  if (!response.ok) {
    throw new Error('Failed to fetch recommendations');
  }

  return response.json();
}
```

---

## Component Examples

### SmartMatchButton Component

Create `components/SmartMatchButton.tsx`:

```tsx
'use client';

import { useState } from 'react';
import { smartMatch } from '@/lib/api/graphMatching';
import type { SmartMatchRequest, MatchResult } from '@/lib/types/graph';

export function SmartMatchButton({ conditions, location }: SmartMatchRequest) {
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<MatchResult[]>([]);

  const handleSmartMatch = async () => {
    setLoading(true);
    try {
      const response = await smartMatch({ conditions, location });
      setResults(response.matches);
    } catch (error) {
      console.error('Smart match failed:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <button
        onClick={handleSmartMatch}
        disabled={loading}
        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
      >
        {loading ? 'Finding Matches...' : '🧠 Smart Match'}
      </button>

      {results.length > 0 && (
        <div className="mt-4">
          <h3 className="font-semibold">Found {results.length} matches:</h3>
          <ul className="space-y-2">
            {results.map((trial) => (
              <li key={trial.nctId} className="p-3 border rounded">
                <a href={`/trials/${trial.nctId}`} className="text-blue-600 hover:underline">
                  {trial.title}
                </a>
                <div className="text-sm text-gray-600">
                  Match Score: {trial.matchScore} | Status: {trial.status}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
```

### RelatedTrials Component

Create `components/RelatedTrials.tsx`:

```tsx
'use client';

import { useEffect, useState } from 'react';
import { getRelatedTrials } from '@/lib/api/graphMatching';
import type { RelatedTrial } from '@/lib/types/graph';

interface Props {
  nctId: string;
}

export function RelatedTrials({ nctId }: Props) {
  const [related, setRelated] = useState<RelatedTrial[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadRelated() {
      try {
        const response = await getRelatedTrials(nctId, 5);
        setRelated(response.relatedTrials);
      } catch (error) {
        console.error('Failed to load related trials:', error);
      } finally {
        setLoading(false);
      }
    }

    loadRelated();
  }, [nctId]);

  if (loading) return <div>Loading related trials...</div>;
  if (related.length === 0) return null;

  return (
    <div className="mt-6 border-t pt-6">
      <h2 className="text-xl font-bold mb-4">Related Trials</h2>
      <div className="space-y-3">
        {related.map((trial) => (
          <div key={trial.nctId} className="p-4 bg-gray-50 rounded-lg">
            <a
              href={`/trials/${trial.nctId}`}
              className="text-lg font-semibold text-blue-600 hover:underline"
            >
              {trial.title}
            </a>

            <div className="mt-2 text-sm text-gray-600">
              {trial.sharedConditions.length > 0 && (
                <div>
                  <span className="font-medium">Shared conditions:</span>{' '}
                  {trial.sharedConditions.join(', ')}
                </div>
              )}
              {trial.sharedLocations.length > 0 && (
                <div>
                  <span className="font-medium">Same locations:</span>{' '}
                  {trial.sharedLocations.join(', ')}
                </div>
              )}
            </div>

            <div className="mt-1 text-xs text-gray-500">
              Relationship Score: {trial.relationshipScore}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

### Recommendations Component

Create `components/Recommendations.tsx`:

```tsx
'use client';

import { useEffect, useState } from 'react';
import { getRecommendations } from '@/lib/api/graphMatching';
import type { Recommendation } from '@/lib/types/graph';

export function Recommendations() {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadRecommendations() {
      try {
        const response = await getRecommendations(5);
        setRecommendations(response.recommendations);
      } catch (error) {
        console.error('Failed to load recommendations:', error);
      } finally {
        setLoading(false);
      }
    }

    loadRecommendations();
  }, []);

  if (loading) return <div>Loading recommendations...</div>;
  if (recommendations.length === 0) return null;

  return (
    <div className="p-6 bg-blue-50 rounded-lg">
      <h2 className="text-xl font-bold mb-4">💡 Recommended for You</h2>
      <div className="space-y-3">
        {recommendations.map((rec) => (
          <div key={rec.nctId} className="p-4 bg-white rounded-lg shadow-sm">
            <a
              href={`/trials/${rec.nctId}`}
              className="text-lg font-semibold text-blue-600 hover:underline"
            >
              {rec.title}
            </a>

            <div className="mt-2 text-sm text-gray-600">
              Matches your conditions:{' '}
              <span className="font-medium">{rec.matchingConditions.join(', ')}</span>
            </div>

            <div className="mt-1 text-xs text-gray-500">
              Status: {rec.status} | Phase: {rec.phase.join(', ')}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

---

## Page Integration Examples

### Smart Match Page

Create `app/smart-match/page.tsx`:

```tsx
'use client';

import { useState } from 'react';
import { SmartMatchButton } from '@/components/SmartMatchButton';

export default function SmartMatchPage() {
  const [conditions, setConditions] = useState<string[]>([]);
  const [location, setLocation] = useState('');

  return (
    <div className="container mx-auto p-6">
      <h1 className="text-3xl font-bold mb-6">🧠 Smart Trial Matching</h1>

      <div className="space-y-4 mb-6">
        <div>
          <label className="block font-medium mb-2">Medical Conditions</label>
          <input
            type="text"
            placeholder="e.g., diabetes, heart disease"
            className="w-full p-2 border rounded"
            onChange={(e) => setConditions(e.target.value.split(',').map(c => c.trim()))}
          />
        </div>

        <div>
          <label className="block font-medium mb-2">Location</label>
          <input
            type="text"
            placeholder="e.g., Boston, MA"
            className="w-full p-2 border rounded"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
          />
        </div>
      </div>

      <SmartMatchButton conditions={conditions} location={location} />
    </div>
  );
}
```

### Trial Detail Page (Enhanced)

Update your existing trial detail page to include related trials:

```tsx
// In app/trials/[nctId]/page.tsx

import { RelatedTrials } from '@/components/RelatedTrials';

export default function TrialDetailPage({ params }: { params: { nctId: string } }) {
  return (
    <div className="container mx-auto p-6">
      {/* Existing trial details */}

      {/* Add related trials section */}
      <RelatedTrials nctId={params.nctId} />
    </div>
  );
}
```

### Dashboard (Enhanced)

Update your dashboard to include recommendations:

```tsx
// In app/dashboard/page.tsx

import { Recommendations } from '@/components/Recommendations';

export default function DashboardPage() {
  return (
    <div className="container mx-auto p-6">
      <h1 className="text-3xl font-bold mb-6">Dashboard</h1>

      {/* Existing dashboard content */}

      {/* Add recommendations */}
      <Recommendations />
    </div>
  );
}
```

---

## UI/UX Recommendations

### Match Score Visualization

Display match scores with visual indicators:

```tsx
function MatchScoreBadge({ score }: { score: number }) {
  const color = score > 20 ? 'bg-green-500' : score > 10 ? 'bg-yellow-500' : 'bg-gray-500';

  return (
    <span className={`px-2 py-1 ${color} text-white text-xs rounded-full`}>
      {score} pts
    </span>
  );
}
```

### Relationship Tags

Show why trials are related:

```tsx
function RelationshipTags({ trial }: { trial: RelatedTrial }) {
  return (
    <div className="flex gap-2 flex-wrap">
      {trial.sharedConditions.length > 0 && (
        <span className="px-2 py-1 bg-blue-100 text-blue-800 text-xs rounded">
          {trial.sharedConditions.length} shared condition(s)
        </span>
      )}
      {trial.sharedLocations.length > 0 && (
        <span className="px-2 py-1 bg-green-100 text-green-800 text-xs rounded">
          Same location
        </span>
      )}
    </div>
  );
}
```

### Loading States

Use skeleton loaders for better UX:

```tsx
function TrialCardSkeleton() {
  return (
    <div className="p-4 border rounded animate-pulse">
      <div className="h-6 bg-gray-200 rounded w-3/4 mb-2"></div>
      <div className="h-4 bg-gray-200 rounded w-1/2"></div>
    </div>
  );
}
```

---

## Testing

### Test Smart Matching

1. Go to `/smart-match` page
2. Enter conditions: "diabetes, hypertension"
3. Enter location: "Boston, MA"
4. Click "Smart Match"
5. Verify results are ranked by match score

### Test Related Trials

1. Go to any trial detail page
2. Scroll to "Related Trials" section
3. Verify trials with shared conditions appear
4. Click on a related trial to navigate

### Test Recommendations

1. Log in with a user that has medical history
2. Go to dashboard
3. Verify "Recommended for You" section appears
4. Verify recommendations match user's conditions

---

## Error Handling

Handle Neo4j connection errors gracefully:

```typescript
export async function smartMatch(criteria: SmartMatchRequest) {
  try {
    const response = await fetch(/* ... */);
    return await response.json();
  } catch (error) {
    // Fallback to regular search if graph matching fails
    console.warn('Graph matching unavailable, using regular search');
    return fallbackSearch(criteria);
  }
}
```

---

## Performance Notes

- **Graph queries are fast**: Neo4j can traverse millions of relationships in milliseconds
- **Cache results**: Consider caching recommendations on the frontend
- **Progressive enhancement**: Show regular search results first, then enhance with graph data
- **Pagination**: Use the `limit` parameter for large result sets

---

## Future Enhancements

Once the basic integration is working, consider:

1. **Graph Visualization**: Use D3.js or Vis.js to show trial/condition networks
2. **Advanced Filters**: Add age range, gender, trial phase filters to smart matching
3. **Similarity Clustering**: Group similar trials visually
4. **Condition Autocomplete**: Use condition hierarchy for smarter search suggestions
5. **Geographic Distance**: Show trials within X miles of user location

---

## Questions or Issues?

If you encounter any problems:

1. Check that Neo4j is running: `docker ps | grep neo4j`
2. Verify data is synced: Access http://localhost:7474 and run `MATCH (n) RETURN count(n)`
3. Check backend logs for errors
4. Ensure CORS is configured correctly (already done in backend)

Happy coding! 🚀
