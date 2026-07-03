"""
Streamlit web app for the LoL Jungle Coach.

Usage:
    streamlit run app/streamlit_app.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from llm_client import analyze_screenshot, ask_question
from pregame import ROLES, run_pregame, save_pregame

st.set_page_config(page_title="Jungle Coach AI", page_icon="🌿", layout="wide")

st.title("Jungle Coach AI")
st.caption("Send a screenshot or ask a question — get Diamond+ coaching advice")

# Session state for chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Sidebar
with st.sidebar:
    st.header("Settings")
    mode = st.radio("Mode", ["Screenshot Analysis", "Ask a Question", "Pre-Game Draft"])
    st.divider()
    st.markdown("**How to use:**")
    st.markdown("1. Take a screenshot in-game (F12 or PrintScreen)")
    st.markdown("2. Upload it here")
    st.markdown("3. Ask what you should do")
    st.divider()
    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.rerun()

# Pre-game mode has its own layout (no chat history)
if mode == "Pre-Game Draft":
    st.subheader("Pre-Game Draft Analysis")
    st.caption("Enter both drafts by role - get a one-glance game plan for loading screen")

    col_ours, col_enemy = st.columns(2)
    ours, enemy = [], []
    with col_ours:
        st.markdown("**Our team**")
        for role in ROLES:
            default = "Ekko" if role == "Jungle" else ""
            ours.append(st.text_input(f"{role} (ours)", value=default, key=f"our_{role}"))
    with col_enemy:
        st.markdown("**Enemy team**")
        for role in ROLES:
            enemy.append(st.text_input(f"{role} (enemy)", key=f"enemy_{role}"))

    notes = st.text_area("Notes (optional)", placeholder="e.g. enemy top is a one-trick, our mid wants to roam")

    if st.button("Generate Game Plan", type="primary"):
        if not all(c.strip() for c in ours + enemy):
            st.error("Fill in all 10 champions.")
        else:
            with st.spinner("Building game plan..."):
                card = run_pregame(ours, enemy, notes or None)
            st.session_state["pregame_card"] = card
            path = save_pregame(card, ours, enemy)
            st.caption(f"Saved to {path}")

    if st.session_state.get("pregame_card"):
        st.markdown("---")
        st.markdown(st.session_state["pregame_card"])
        st.download_button("Download game plan", st.session_state["pregame_card"],
                           file_name="game_plan.md")
    st.stop()

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg.get("image"):
            st.image(msg["image"], width=400)
        st.markdown(msg["content"])

# Input area
if mode == "Screenshot Analysis":
    uploaded = st.file_uploader(
        "Upload a game screenshot",
        type=["png", "jpg", "jpeg", "webp"],
        key="screenshot",
    )

    question = st.chat_input("What do you want to know? (default: 'What should I do here?')")

    if uploaded and question:
        image_bytes = uploaded.read()

        # Show user message
        st.session_state.messages.append({
            "role": "user",
            "content": question,
            "image": image_bytes,
        })
        with st.chat_message("user"):
            st.image(image_bytes, width=400)
            st.markdown(question)

        # Get coaching advice
        with st.chat_message("assistant"):
            with st.spinner("Analyzing game state..."):
                advice = analyze_screenshot(image_bytes, question)
            st.markdown(advice)

        st.session_state.messages.append({
            "role": "assistant",
            "content": advice,
        })

    elif uploaded and not question:
        st.info("Upload received. Type your question in the chat box below to get coaching advice.")

else:
    question = st.chat_input("Ask any jungle coaching question...")

    if question:
        st.session_state.messages.append({
            "role": "user",
            "content": question,
        })
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                advice = ask_question(question)
            st.markdown(advice)

        st.session_state.messages.append({
            "role": "assistant",
            "content": advice,
        })
