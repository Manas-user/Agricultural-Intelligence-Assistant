# src/rag_pipeline.py

from dotenv import load_dotenv
load_dotenv()  # ✅ Loads .env into os.environ

import os
import google.generativeai as genai
from src.retrieve import retriever

# Load Gemini API Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("❌ GEMINI_API_KEY is not set. Please check your .env file.")

genai.configure(api_key=GEMINI_API_KEY)

# Load the Gemini model
model = genai.GenerativeModel("models/gemini-2.0-flash")

def run_rag(query):
    docs = retriever.invoke(query)

    if not docs:
        return "⚠️ No relevant documents found for the query."

    context = "\n\n".join([doc.page_content for doc in docs])
    prompt = f"""
You are a financial analyst assistant AI. Only use the information provided in the context below to answer the user's question.
**Do not guess, hallucinate, or use external knowledge.**
If the context does not contain enough information to answer the question, respond with:
**"Insufficient information in the provided documents to answer the question."**

---

Context:
{context}

---

User Question:
{query}

---

Write a long-form, in-depth answer using only the context above. Your response should include detailed explanations, relevant financial figures, reasoning behind trends or statements, and should be presented in a formal tone suitable for an investor or analyst report. Aim for a thorough, multi-paragraph response:
"""


    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"❌ Gemini API error: {e}"
