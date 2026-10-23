import os

import streamlit as st
from dotenv import load_dotenv
from google import genai

from answer import answer_question, pick_model
from retrieval import Retriever

load_dotenv()

st.set_page_config(page_title="Nepal Birding Guide", page_icon="🐦", layout="centered")

MAX_QUESTIONS = 30  # per browser session, protects the free Gemini quota
EXAMPLES = [
    "How do I recognise a Verditer Flycatcher?",
    "What is the conservation status of the Pin-tailed Green Pigeon?",
    "Which birds are critically endangered in Nepal?",
    "What does the Collared Owlet sound like?",
    "Was the Spotted Dove split into separate species?",
]


def get_api_key():
    key = os.getenv("GEMINI_API_KEY")
    if key:
        return key
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        return None


@st.cache_resource(show_spinner="Loading the bird library...")
def load_retriever():
    return Retriever()


@st.cache_resource(show_spinner="Connecting to Gemini...")
def load_client(api_key):
    client = genai.Client(api_key=api_key)
    return client, pick_model(client)


st.title("🐦 Nepal Birding Guide")
st.caption("Ask about identification, voice and habitat, conservation status and taxonomy of the birds of Nepal.")

api_key = get_api_key()
if not api_key:
    st.error("No Gemini API key found. Add GEMINI_API_KEY to your .env file "
             "(or to the Streamlit secrets once the app is deployed).")
    st.stop()

retriever = load_retriever()
client, model = load_client(api_key)

if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.count = 0

with st.sidebar:
    st.header("About")
    st.write("Answers come from the official checklist of the birds of Nepal and two field guides. "
             "Please check important details in the original sources.")
    st.subheader("Try asking")
    for ex in EXAMPLES:
        if st.button(ex, use_container_width=True):
            st.session_state.example = ex
    show_debug = st.checkbox("Show technical details")
    if st.button("Clear chat"):
        st.session_state.messages = []
        st.session_state.count = 0
        st.rerun()

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m.get("sources"):
            with st.expander("Sources"):
                for s in m["sources"]:
                    st.write(s)

prompt = st.chat_input("Ask about a bird, its status or its sound...")
if "example" in st.session_state:
    prompt = st.session_state.pop("example")

if prompt:
    if st.session_state.count >= MAX_QUESTIONS:
        st.warning("You have reached the question limit for this session. Please come back later.")
    else:
        history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Looking through the sources..."):
                result = answer_question(retriever, client, model, history, prompt)
            st.markdown(result["text"])
            if result["sources"]:
                with st.expander("Sources"):
                    for s in result["sources"]:
                        st.write(s)
            if show_debug:
                st.caption(f"Technical details: {result['debug']}")
        st.session_state.messages.append(
            {"role": "assistant", "content": result["text"], "sources": result["sources"]})
        st.session_state.count += 1