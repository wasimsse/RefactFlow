import streamlit as st

def render_sidebar():
    st.sidebar.title("Settings")
    st.sidebar.subheader("LLM Configuration")
    st.sidebar.text_input("OpenRouter API Key", type="password", key="api_key")
    st.sidebar.selectbox("Model", ["GPT-4", "Claude", "Code Llama", "Mixtral"], key="llm_model")
    st.sidebar.markdown("---")
    st.sidebar.write(f"Current Model: {st.session_state.get('llm_model', 'GPT-4')}")
    st.sidebar.write(f"API Key Set: {'Yes' if st.session_state.get('api_key') else 'No'}") 