# RAG Chatbot – ICICI Prudential Mutual Fund FAQ Assistant

## Overview

This project is a Retrieval-Augmented Generation (RAG) chatbot that answers frequently asked questions about ICICI Prudential Mutual Fund schemes using information from official sources.
The chatbot retrieves relevant information from a pre-built knowledge base and uses an LLM to generate a concise, grounded response.

## Features

- Answers mutual fund-related FAQs
- Uses Retrieval-Augmented Generation (RAG)
- Retrieves information from a curated knowledge base
- Provides source links with answers
- Designed to avoid unsupported investment recommendations
- Streamlit-based user interface
- Groq LLM integration

## Example Questions

- What is the expense ratio of ICICI Prudential Flexi Cap Fund?
- What is the lock-in period for an ELSS mutual fund?
- What is the minimum investment amount for an SIP?
- How can I download my capital gains statement?
- What is the difference between SIP and lump-sum investment?

## Tech Stack

- Python
- Streamlit
- ChromaDB
- Groq API
- RAG
- GitHub

## Project Structure

```text
RAG-Chatbot/
│
├── src/
│   ├── app.py
│   ├── pipeline.py
│   ├── retrieve.py
│   ├── generate.py
│   ├── store.py
│   ├── ingest.py
│   └── load.py
│
├── data/
│   └── chroma/
│
├── requirements.txt
├── requirements-ingest.txt
└── README.md
```

## How It Works

```text
User Question
      ↓
Streamlit Interface
      ↓
Retrieval Pipeline
      ↓
Knowledge Base
      ↓
Relevant Context
      ↓
Groq LLM
      ↓
Answer + Source
```

## Running Locally

Install the required dependencies:

```bash
pip install -r requirements.txt
```

Add your Groq API key as an environment variable:

```text
GROQ_API_KEY=your_api_key
```

Run the Streamlit application:

```bash
python -m streamlit run src/app.py
```

The application will open in your browser.

## Deployment

The application can be deployed as a Streamlit application using a cloud hosting service such as Render.

## Disclaimer

This chatbot is intended for informational purposes and should not be considered financial advice. Users should verify information with official mutual fund sources before making investment decisions.
