# --- Streamlit App: E3 Company Hospital Receptionist Assistant ---

import streamlit as st
import requests
import io
import time
import base64
from audio_recorder_streamlit import audio_recorder
from streamlit_extras.stylable_container import stylable_container

# --- Theme and Logo ---
st.set_page_config(
    page_title="E3 Hospital Receptionist",
    page_icon="E3.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for E3 colors and style
st.markdown("""
    <style>
        body, .main, .block-container {
            background-color: #fff8f0 !important;
        }
        .stButton > button {
            background-color: #ff8800 !important;
            color: white !important;
            border-radius: 8px !important;
            border: none !important;
        }
        .stTextInput > div > input {
            border: 2px solid #ff8800 !important;
        }
        .stChatMessage {
            background-color: #fff8f0 !important;
            border-left: 4px solid #ff8800 !important;
        }
        .stSuccess {
            background-color: #ffe5cc !important;
            color: #ff8800 !important;
        }
        .stInfo {
            background-color: #fff8f0 !important;
            color: #ff8800 !important;
        }
        .stSidebar {
            background-color: #fff8f0 !important;
        }
    </style>
""", unsafe_allow_html=True)

# Display E3 logo and company info
with st.container():
    col1, col2 = st.columns([1, 8])
    with col1:
        st.image("E3.png", width=80)
    with col2:
        st.markdown("""
            <h1 style='color:#ff8800; font-size:2.5rem; margin-bottom:0;'>E3 AI Hospital Receptionist</h1>
            <div style='font-size:1.2rem; color:#333; margin-bottom:0.5rem;'>
                Welcome to E3 Company's smart hospital receptionist assistant.<br>
                Powered by E3 Corp. <a href="https://www.e3corp.net/" target="_blank" style="color:#ff8800; text-decoration:underline;">Visit our website</a>
            </div>
        """, unsafe_allow_html=True)

st.write("""
Our E3 virtual receptionist is here to help you with hospital appointments, doctor visits, and general inquiries.
Please record your message or upload an audio file, and our assistant will respond in a friendly, professional manner.
""")

if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []
if "conversation_active" not in st.session_state:
    st.session_state["conversation_active"] = False


# --- Helper Functions ---
def transcribe_with_assemblyai(audio_bytes, api_key):
    """Send audio to AssemblyAI for transcription. Returns transcript or error."""
    upload_url = "https://api.assemblyai.com/v2/upload"
    transcript_url = "https://api.assemblyai.com/v2/transcript"
    headers = {"authorization": api_key}

    # 1. Upload audio
    response = requests.post(upload_url, headers=headers, data=audio_bytes)
    if response.status_code != 200:
        return None, f"Upload failed: {response.text}"
    audio_url = response.json()["upload_url"]

    # 2. Request transcription
    json_data = {
        "audio_url": audio_url,
        "language_code": "en",
        "punctuate": True,
        "format_text": True
    }
    response = requests.post(transcript_url, headers=headers, json=json_data)
    if response.status_code != 200:
        return None, f"Transcription request failed: {response.text}"
    transcript_id = response.json()["id"]

    # 3. Poll for completion
    poll_url = f"{transcript_url}/{transcript_id}"
    for _ in range(60):  # ~60s max
        poll_resp = requests.get(poll_url, headers=headers)
        status = poll_resp.json().get("status")
        if status == "completed":
            return poll_resp.json().get("text", ""), None
        elif status == "failed":
            return None, f"Transcription failed: {poll_resp.json().get('error', 'Unknown error')}"
        time.sleep(1)
    return None, "Transcription timed out after 60 seconds. Please try again or use a shorter audio."

def tts_with_elevenlabs(text, api_key, voice_id="21m00Tcm4TlvDq8ikWAM"):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.7}
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.content, None
    else:
        return None, f"TTS error: {response.text}"

def get_ai_reply_with_cohere(prompt, api_key):
    url = "https://api.cohere.ai/v1/chat"
    headers = {
    }
    detailed_prompt = f'''
You are a friendly and professional hospital receptionist at E3 Company.
A patient said: "{prompt}"

Your job is to:
- Understand their request
- Politely respond in natural human-like language
- If the user didn't provide details (like doctor's name, date, or time), kindly ask for them
- If they mentioned a doctor or date, confirm the details and proceed as if helping them schedule
- Suggest visiting hours or common available slots (you can make up some for the demo)
- Do NOT output structured data or lists (no bullet points, no headings). Just a warm paragraph of text like a real receptionist would say in person.

Be clear, human, and helpful. Always mention E3 Company in your reply.
'''
    data = {
        "model": "command-r-plus",
        "message": detailed_prompt,
        "chat_history": [],
        "temperature": 0.7,
        "max_tokens": 300,
        "preamble": "You are a polite hospital receptionist."
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json().get("text", ""), None
    else:
        return None, f"Cohere API error: {response.text}"

# --- Conversation Controls ---
with st.sidebar:
    st.title("E3 Controls")
    st.markdown("<span style='color:#ff8800;'>Manage your conversation with E3 Receptionist</span>", unsafe_allow_html=True)
    if st.button("Start New Conversation"):
        st.session_state["chat_history"] = []
        st.session_state["conversation_active"] = True
        st.session_state["is_processing"] = False
        st.session_state["last_processed_audio"] = None
    if st.button("End Conversation"):
        st.session_state["conversation_active"] = False
        st.session_state["is_processing"] = False
        st.session_state["last_processed_audio"] = None
    if st.button("Clear History"):
        st.session_state["chat_history"] = []
        st.session_state["is_processing"] = False
        st.session_state["last_processed_audio"] = None

# --- Conversation Loop ---
if st.session_state["conversation_active"]:
    st.markdown("<b style='color:#ff8800;'>Hold the button to speak, release to send your message</b>", unsafe_allow_html=True)
    
    # Initialize processing state if not exists
    if "is_processing" not in st.session_state:
        st.session_state["is_processing"] = False
    if "last_processed_audio" not in st.session_state:
        st.session_state["last_processed_audio"] = None
    
    # Only show recorder if not currently processing
    if not st.session_state["is_processing"]:
        audio_bytes = audio_recorder(
            text="Hold to record",
            recording_color="#ff8800",
            neutral_color="#fff8f0",
            icon_name="microphone"
        )
        
        # Process new audio recording
        if audio_bytes and (audio_bytes != st.session_state["last_processed_audio"]):
            st.session_state["is_processing"] = True
            st.session_state["last_processed_audio"] = audio_bytes
            
            # Display recorded audio
            st.audio(audio_bytes, format='audio/wav')
            
            # --- Pipeline: STT, LLM, TTS ---
            with st.spinner("Processing your voice message..."):
                # Step 1: Transcribe audio
                transcript, err = transcribe_with_assemblyai(audio_bytes, st.secrets["ASSEMBLYAI_API_KEY"])
                
                if err:
                    st.error(f"Transcription error: {err}")
                    st.session_state["is_processing"] = False
                else:
                    # Display transcribed text
                    with st.chat_message("user", avatar="🧑‍⚕️"):
                        st.write(f"**You said:** {transcript}")
                    
                    # Add user message to chat history
                    if transcript:
                        st.session_state["chat_history"].append({"role": "USER", "message": transcript})
                    
                    # Prepare chat history for Cohere
                    cohere_history = [
                        {"role": "USER" if m["role"] == "USER" else "CHATBOT", "message": m["message"]}
                        for m in st.session_state["chat_history"][:-1]
                    ]
                    
                    # Step 2: Get AI response with context-aware prompt
                    # Build conversation context
                    context_summary = ""
                    if cohere_history:
                        context_summary = "\n\nPrevious conversation context:\n"
                        for msg in cohere_history[-6:]:  # Use last 6 messages for context
                            role_label = "Patient" if msg["role"] == "USER" else "You (Receptionist)"
                            context_summary += f"- {role_label}: {msg['message']}\n"
                        context_summary += "\nBased on this conversation history, respond appropriately to continue the flow.\n"
                    
                    detailed_prompt = f'''
You are a friendly and professional hospital receptionist at E3 Company. You have been having an ongoing conversation with this patient.

{context_summary}

Current patient message: "{transcript}"

Instructions:
- REMEMBER the conversation history above - don't ask for information the patient already provided
- If you previously asked for specific details (doctor name, date, time) and they're providing it now, acknowledge and proceed
- If you already have enough information to help them, move forward with the next logical step
- If this seems to be a new topic, treat it as such but maintain the conversational flow
- Respond naturally as if this is a continuation of your ongoing conversation
- Keep responses conversational and human-like (no bullet points or structured lists)
- Always maintain a warm, helpful tone and mention E3 Company appropriately

Respond as the E3 hospital receptionist:'''
                    data = {
                        "model": "command-r-plus",
                        "message": detailed_prompt,
                        "chat_history": cohere_history,
                        "temperature": 0.7,
                        "max_tokens": 300,
                        "preamble": "You are a professional hospital receptionist at E3 Company. You maintain conversation context and remember what patients have told you. You provide seamless, continuous service without repeating questions unnecessarily."
                    }
                    url = "https://api.cohere.ai/v1/chat"
                    headers = {
                        "Authorization": f"Bearer {st.secrets['COHERE_API_KEY']}" ,
                        "Content-Type": "application/json"
                    }
                    
                    response = requests.post(url, headers=headers, json=data)
                    if response.status_code == 200:
                        ai_reply = response.json().get("text", "")
                        
                        # Display AI response text
                        with st.chat_message("assistant", avatar="🏥"):
                            st.write(f"**E3 Receptionist:** {ai_reply}")
                        
                        # Add AI response to chat history
                        if ai_reply:
                            st.session_state["chat_history"].append({"role": "CHATBOT", "message": ai_reply})
                        
                        # Step 3: Generate and play TTS audio
                        with st.spinner("Generating voice response..."):
                            tts_audio_data, tts_error = tts_with_elevenlabs(ai_reply, st.secrets["ELEVENLABS_API_KEY"])
                            
                            if tts_audio_data:
                                st.success("🔊 **E3 Receptionist Response (Audio):**")
                                st.audio(tts_audio_data, format='audio/mpeg')
                                st.info("🎤 Ready for your next message! Use the record button above.")
                            else:
                                st.error(f"TTS Error: {tts_error}")
                    else:
                        st.error(f"AI Response Error: {response.text}")
                    
                    # Reset processing state to allow new recording
                    st.session_state["is_processing"] = False
    else:
        st.info("🔄 Processing your message... Please wait.")
    
    # Show conversation history in an expandable section
    if st.session_state["chat_history"]:
        with st.expander("📝 Conversation History", expanded=False):
            for i, msg in enumerate(st.session_state["chat_history"]):
                if msg["role"] == "USER":
                    st.write(f"**🧑‍⚕️ You ({i//2 + 1}):** {msg['message']}")
                else:
                    st.write(f"**🏥 E3 Receptionist ({i//2 + 1}):** {msg['message']}")
                st.write("---")

else:
    st.info("👋 Welcome! Click **'Start New Conversation'** in the sidebar to begin talking with our E3 AI Receptionist.")

