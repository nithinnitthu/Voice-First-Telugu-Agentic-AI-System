# Voice-First-Telugu-Agentic-AI-System
voice first telugu agentic AI system

# Voice-First Agentic AI for Government Scheme Discovery (Native Indian Language)

## 📌 Overview
This project implements a **voice-first, agentic AI system** that helps users **identify and apply for government or public welfare schemes** using a **native Indian language** (e.g., Telugu / Marathi / Tamil).

The system goes **beyond a chatbot** by demonstrating:
- Autonomous reasoning and planning
- Tool usage
- Multi-turn memory
- Failure handling and recovery
- End-to-end voice interaction

All interactions happen in **one non-English Indian language**, from **Speech-to-Text → LLM Agent → Tools → Text-to-Speech**.

---

## 🎯 Objective
Build a **Voice-Based Native Language Service Agent** that:
- Understands spoken user requests
- Determines scheme eligibility
- Assists in applying for schemes
- Handles missing, incorrect, or contradictory information
- Recovers gracefully from errors

---

## 🗣️ Supported Language
- **Telugu** (configurable to Marathi / Tamil / Bengali / Odia)

---

## 🧠 What Makes This Agentic (Not a Chatbot)

The system uses an explicit **Planner–Executor–Evaluator loop**:

1. **Planner**
   - Interprets user intent
   - Decides next action (ask details, call tools, recover from error)

2. **Executor**
   - Calls external tools (eligibility engine, scheme database, mock API)

3. **Evaluator**
   - Validates results
   - Detects failures or contradictions
   - Triggers recovery actions

This loop runs **autonomously across turns**, proving real decision-making.

---

## 🔧 Tools Used (Mandatory Requirement Met)

The agent uses **multiple tools**, including:

### 1️⃣ Scheme Retrieval Tool
- Fetches government schemes from a local dataset
- Filters by state, age, income, category, and occupation

### 2️⃣ Eligibility Engine
- Rule-based eligibility checks
- Determines if the user qualifies for a scheme

### 3️⃣ Mock Application API
- Simulates scheme application submission
- Returns success or missing-document errors

---

## 🧠 Conversation Memory
- Stores user profile details across turns:
  - Age
  - Income
  - State
  - Previous answers
- Detects contradictions (e.g., age mismatch)
- Requests clarification before proceeding

---

## 🚨 Failure Handling
The agent explicitly handles:

- ❌ Missing information  
- ❌ Speech-to-Text recognition errors  
- ❌ No eligible schemes found  
- ❌ Tool/API failures  
- ⚠ Contradictory user responses  

Each failure triggers a **recovery dialogue** in the native language.

---

## 🏗️ Architecture

### High-Level Flow
