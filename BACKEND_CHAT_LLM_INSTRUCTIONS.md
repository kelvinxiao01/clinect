# Backend LLM-Powered Chat Interface Instructions

## Overview

The frontend Smart Match page has been redesigned as an LLM-powered conversational chatbot. Users chat naturally with an AI assistant that:
- Extracts medical conditions, location, age, gender from conversation
- Asks progressive follow-up questions
- Calls Neo4j graph matching when enough information is gathered
- Explains match results in plain English
- Maintains conversation context

## What You Need to Do

### 1. Install Google Gemini SDK

We'll use **Google Gemini** (excellent for medical/conversational tasks with free tier).

```bash
uv add google-generativeai
```

### 2. Environment Variables

Add to your `.env` file:

```bash
# Google Gemini API Key (get from https://aistudio.google.com/app/apikey)
GEMINI_API_KEY=your_gemini_api_key_here

# LLM Configuration (optional)
GEMINI_MODEL=gemini-2.5-flash  # or gemini-2.5-pro for better quality
LLM_MAX_TOKENS=1024
LLM_TEMPERATURE=0.7
```

### 3. Create Chat Endpoint

Add `POST /api/chat` endpoint to handle conversational interaction:

```python
import google.generativeai as genai
import json
import os
from datetime import datetime

# Initialize Gemini client (at app startup)
genai.configure(api_key=os.environ.get('GEMINI_API_KEY'))

# System prompt for the chat assistant
SYSTEM_PROMPT = """You are a compassionate clinical trial matching assistant helping patients find relevant medical studies.

Your job:
1. Greet users warmly and ask about their medical conditions
2. Gather: conditions, location, age, gender
3. When you have enough information (at least conditions), use the smart_match_trials function
4. Explain results in plain English, highlighting match scores and why trials are relevant
5. Answer follow-up questions about specific trials

Guidelines:
- Be empathetic and supportive
- Use medical terminology accurately but explain complex terms
- Ask ONE question at a time (don't overwhelm users)
- Match scores: +10 per condition match, +5 for location proximity
- If user mentions symptoms, ask clarifying questions to identify conditions

Example conversation flow:
User: "I have diabetes"
You: "I understand you're looking for trials related to diabetes. To find the best matches, may I ask your location? This helps me find trials near you."
User: "Boston"
You: "Thank you! One more quick question - what's your age? Some trials have age requirements."
User: "45"
You: [Call smart_match_trials with conditions=["diabetes"], location="Boston", age=45]
You: "Great! I found 8 clinical trials for diabetes in the Boston area. Here are the top matches..."
"""

# Define function declaration for Gemini
smart_match_function = {
    "name": "smart_match_trials",
    "description": "Search for clinical trials using graph-based matching. Call this when you have gathered enough information from the user (at minimum: conditions). Returns trials with match scores.",
    "parameters": {
        "type": "object",
        "properties": {
            "conditions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Medical conditions to match (e.g., ['diabetes', 'hypertension'])"
            },
            "location": {
                "type": "string",
                "description": "User's location (city, state, or country)"
            },
            "age": {
                "type": "integer",
                "description": "User's age in years"
            },
            "gender": {
                "type": "string",
                "enum": ["MALE", "FEMALE", "ALL"],
                "description": "User's gender"
            },
            "maxDistance": {
                "type": "integer",
                "description": "Maximum distance in miles (default: 50)"
            }
        },
        "required": ["conditions"]
    }
}

@app.route('/api/chat', methods=['POST'])
def chat():
    """
    LLM-powered conversational chat endpoint
    Processes natural language and calls smart matching when ready
    """
    data = request.json
    user_message = data.get('message', '')
    conversation_history = data.get('conversationHistory', [])

    if not user_message:
        return jsonify({'success': False, 'error': 'Message required'}), 400

    try:
        # Initialize Gemini model with function calling
        model = genai.GenerativeModel(
            model_name=os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash'),
            tools=[smart_match_function],
            system_instruction=SYSTEM_PROMPT
        )

        # Build chat history for Gemini
        chat_history = []
        for msg in conversation_history:
            if msg['role'] == 'user':
                chat_history.append({
                    'role': 'user',
                    'parts': [msg['content']]
                })
            elif msg['role'] == 'assistant':
                chat_history.append({
                    'role': 'model',
                    'parts': [msg['content']]
                })

        # Start chat session with history
        chat = model.start_chat(history=chat_history)

        # Send user message
        response = chat.send_message(user_message)

        # Process response
        assistant_message = ""
        trials = None
        extracted_criteria = None

        # Check if Gemini wants to call a function
        if response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                # Handle text response
                if hasattr(part, 'text'):
                    assistant_message += part.text

                # Handle function call
                if hasattr(part, 'function_call'):
                    function_call = part.function_call
                    if function_call.name == 'smart_match_trials':
                        # Extract function arguments
                        extracted_criteria = dict(function_call.args)

                        # Call your existing smart match logic
                        match_result = call_smart_match_internal(extracted_criteria)
                        trials = match_result.get('matches', [])

                        # Send function response back to Gemini
                        function_response = {
                            'name': 'smart_match_trials',
                            'response': {
                                'totalMatches': len(trials),
                                'matches': trials[:10]  # Top 10
                            }
                        }

                        # Get Gemini's interpretation of the results
                        followup_response = chat.send_message(
                            genai.protos.Content(
                                parts=[genai.protos.Part(
                                    function_response=genai.protos.FunctionResponse(
                                        name=function_response['name'],
                                        response={'result': function_response['response']}
                                    )
                                )]
                            )
                        )

                        # Extract explanation text
                        if followup_response.candidates[0].content.parts:
                            for followup_part in followup_response.candidates[0].content.parts:
                                if hasattr(followup_part, 'text'):
                                    assistant_message += followup_part.text

        return jsonify({
            'success': True,
            'assistantMessage': assistant_message,
            'trials': trials,
            'extractedCriteria': extracted_criteria,
            'timestamp': datetime.utcnow().isoformat()
        })

    except Exception as e:
        print(f"Chat error: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to process chat message',
            'assistantMessage': "I'm sorry, I encountered an error. Could you try rephrasing your message?"
        }), 500

def call_smart_match_internal(criteria):
    """
    Internal wrapper for smart match logic
    Reuses your existing Neo4j graph matching code
    """
    # Parse conditions (may be list or comma-separated string)
    conditions = criteria.get('conditions', [])
    if isinstance(conditions, str):
        conditions = [c.strip() for c in conditions.split(',')]

    location = criteria.get('location')
    age = criteria.get('age')
    gender = criteria.get('gender')
    max_distance = criteria.get('maxDistance', 50)

    # Call your existing smart match function
    # This should use your Neo4j graph matching logic
    return smart_match_trials_neo4j(
        conditions=conditions,
        location=location,
        age=age,
        gender=gender,
        max_distance=max_distance
    )
```

### 4. Rate Limiting and Error Handling

Add rate limiting to prevent abuse:

```python
from functools import wraps
from time import time

# Simple in-memory rate limiter (use Redis in production)
chat_rate_limits = {}

def rate_limit_chat(max_requests=10, window_seconds=60):
    """Limit chat requests per user"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = session.get('user_id', 'anonymous')
            current_time = time()

            if user_id not in chat_rate_limits:
                chat_rate_limits[user_id] = []

            # Remove old timestamps
            chat_rate_limits[user_id] = [
                t for t in chat_rate_limits[user_id]
                if current_time - t < window_seconds
            ]

            if len(chat_rate_limits[user_id]) >= max_requests:
                return jsonify({
                    'success': False,
                    'error': 'Rate limit exceeded. Please wait a moment.',
                    'assistantMessage': 'I need to take a quick break. Please try again in a minute.'
                }), 429

            chat_rate_limits[user_id].append(current_time)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Apply to chat endpoint
@app.route('/api/chat', methods=['POST'])
@rate_limit_chat(max_requests=10, window_seconds=60)
def chat():
    # ... existing code
```

### 5. Testing

#### Test Basic Conversation:
```bash
curl -X POST http://localhost:5001/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I have diabetes",
    "conversationHistory": []
  }'
```

Expected: Assistant asks follow-up question about location or age

#### Test Smart Match Trigger:
```bash
curl -X POST http://localhost:5001/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "45 years old in Boston",
    "conversationHistory": [
      {"role": "assistant", "content": "What conditions are you dealing with?"},
      {"role": "user", "content": "diabetes"},
      {"role": "assistant", "content": "May I ask your location and age?"}
    ]
  }'
```

Expected: Returns trials array with match scores

### 6. Cost Management

**Great news**: Google Gemini has a generous FREE tier that should cover most development and small production use cases!

**Free Tier Limits:**
- **gemini-2.5-flash**: 15 requests/min, 1 million tokens/day (FREE)
- **gemini-2.5-pro**: 2 requests/min, 50 requests/day (FREE)

**Optimization tips:**
1. **Use Flash model by default** - fast and free for most queries
2. **Cache common responses** - store frequent questions/answers
3. **Limit conversation history** - only send last 10 messages to LLM
4. **Monitor usage** - log request counts per user

Example caching:
```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_cached_llm_response(user_message_hash):
    """Cache identical user messages"""
    pass
```

**When to upgrade:**
- If you exceed 15 requests/minute consistently
- If you need faster response times (paid tier has higher throughput)
- Production apps with high traffic should consider paid tier for SLA guarantees

### 7. Security Considerations

1. **Validate user input** - sanitize before sending to LLM
2. **Protect API keys** - never expose in logs or error messages
3. **Rate limit** - prevent abuse and cost overruns
4. **Session validation** - require authenticated users for chat
5. **Content filtering** - reject inappropriate medical advice requests

### 8. Monitoring and Logging

Add logging to track:
```python
import logging

logger = logging.getLogger(__name__)

@app.route('/api/chat', methods=['POST'])
def chat():
    user_id = session.get('user_id', 'anonymous')
    logger.info(f"Chat request from user {user_id}")

    try:
        # ... LLM call
        logger.info(f"LLM response generated, trials: {len(trials) if trials else 0}")
    except Exception as e:
        logger.error(f"Chat error for user {user_id}: {str(e)}")
```

## API Contract

### Request Format
```json
{
  "message": "I have type 2 diabetes and live in Boston",
  "conversationHistory": [
    {
      "role": "assistant",
      "content": "Hello! I'm here to help you find clinical trials...",
      "timestamp": "2024-01-15T10:30:00Z"
    },
    {
      "role": "user",
      "content": "Hi",
      "timestamp": "2024-01-15T10:30:05Z"
    }
  ]
}
```

### Response Format
```json
{
  "success": true,
  "assistantMessage": "Great! I found 8 clinical trials for type 2 diabetes in Boston. Here are the top matches based on your criteria...",
  "trials": [
    {
      "nctId": "NCT12345678",
      "title": "Study of New Diabetes Medication",
      "status": "RECRUITING",
      "phase": ["PHASE3"],
      "matchScore": 25
    }
  ],
  "extractedCriteria": {
    "conditions": ["type 2 diabetes"],
    "location": "Boston",
    "age": null,
    "gender": null
  },
  "timestamp": "2024-01-15T10:30:10Z"
}
```

## Example System Prompt Refinements

Customize the system prompt for better results:

```python
SYSTEM_PROMPT = """You are a compassionate clinical trial matching assistant named "TrialMatch Assistant".

Your capabilities:
- Help patients find relevant clinical trials
- Explain complex medical terminology
- Answer questions about trial eligibility
- Use graph-based matching that considers condition relationships

Your personality:
- Warm and empathetic
- Professional but not overly formal
- Patient-focused (never pushy)
- Clear and concise

Conversation guidelines:
1. Start with a warm greeting
2. Ask about medical conditions first
3. Gather location (city/state is enough)
4. Ask age if relevant
5. Call smart_match_trials when you have conditions
6. Explain match scores: higher = better match
7. Offer to answer questions about specific trials

Match scoring explained:
- +10 points per matching condition (including related conditions via graph)
- +5 points for trials in user's location
- 20+ points = excellent match
- 10-19 points = good match
- <10 points = potential match

Important:
- Never provide medical advice
- Always encourage users to consult their doctor
- Clarify that you're helping find trials, not recommending treatment
- If unsure about a medical term, ask for clarification
"""
```

## Troubleshooting

### "Gemini API key not found"
- Check `.env` file has `GEMINI_API_KEY=your_key_here`
- Get API key from [Google AI Studio](https://aistudio.google.com/app/apikey)
- Verify environment variable is loaded: `echo $GEMINI_API_KEY`

### "Rate limit exceeded" from Gemini API
- Free tier: 15 requests per minute, 1500 per day
- Implement request throttling
- Consider upgrading to paid tier for higher limits

### LLM not calling smart_match_trials function
- Check function declaration matches Gemini's expected format
- Make system instruction more explicit about when to use the function
- Verify user provided enough information (conditions minimum)
- Try using `gemini-2.5-pro` for better function calling accuracy

### Responses are too verbose
- Update system prompt: "Keep responses under 3 sentences unless explaining results"
- Use `gemini-2.5-flash` for more concise responses

### High API costs
- **Good news**: Gemini has a generous free tier!
  - gemini-2.5-flash: 15 RPM, 1 million tokens/day (FREE)
  - gemini-2.5-pro: 2 RPM, 50 requests/day (FREE)
- Implement response caching for common queries
- Limit conversation history sent to LLM (last 10 messages)
- Use Flash model for most queries, Pro only when needed

### "Function response format error"
- Ensure function response follows Gemini's format:
  ```python
  genai.protos.FunctionResponse(
      name='smart_match_trials',
      response={'result': your_data}
  )
  ```

## Questions?

Check documentation:
- [Google Gemini API Documentation](https://ai.google.dev/docs)
- [Gemini Function Calling Guide](https://ai.google.dev/docs/function_calling)
- [Flask Session Management](https://flask.palletsprojects.com/en/latest/quickstart/#sessions)
- [Get Gemini API Key](https://aistudio.google.com/app/apikey)
