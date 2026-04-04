from openai import OpenAI
import json
import os

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

def analyze_email(body):

    prompt = f"""
You are an AI assistant.

Extract:
1. Is this a meeting request?
2. Extract time if present

IMPORTANT:
- Even "3 April 3pm" is a meeting

Return ONLY JSON:

{{
  "intent": "meeting" or "other",
  "time": "time string or null"
}}

Email:
{body}
"""

    try:
        response = client.chat.completions.create(
        model="mixtral-8x7b-32768",
        messages=[{"role": "user", "content": prompt}]
)
        text = response.choices[0].message.content.strip()

        # 🔥 Extract JSON safely
        start = text.find("{")
        end = text.rfind("}") + 1
        json_text = text[start:end]

        return json.loads(json_text)

    except Exception as e:
        print("GROQ ERROR:", e)
        return {"intent": "other", "time": None}
    
    