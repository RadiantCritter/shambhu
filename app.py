import requests
import re
import openai
import os
import threading
import time
import tempfile
from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions, Microphone
import pygame
from dotenv import load_dotenv

load_dotenv()

DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

# Initialize clients
dg_client = DeepgramClient(api_key=DEEPGRAM_API_KEY)
openai.api_key = OPENAI_API_KEY
client = openai.OpenAI()

DEEPGRAM_TTS_URL = 'https://api.deepgram.com/v1/speak?model=aura-helios-en'
headers = {
    "Authorization": f"Token {DEEPGRAM_API_KEY}",
    "Content-Type": "application/json"
}

conversation_memory = []

# Global flag to control microphone state
mute_microphone = threading.Event()

prompt = """Majestic Estates AI - Buyer Inquiry Call Script

BACKGROUND INFO
Company Info: Majestic Estates is at the forefront of the real estate industry, delivering unparalleled buying experiences through expert market knowledge and advanced AI technology, tailoring services to each client’s unique home buying needs and desires.
Target Audience: Catering primarily to individuals and families in the home buying or renting arena, our services are designed to suit the needs of first-time buyers, relocating families, and investment buyers among others.
Value Proposition: With Majestic Estates, clients receive a highly personalized service that includes access to exclusive property listings, insightful market analysis, and dedicated support, aiming for a seamless and fulfilling home acquisition experience.

Agent Information:
Name: Paul
Role: AI Real Estate Assistant
Objective: To collect essential information from potential buyers or renters, assisting in pinpointing their ideal home based on specific needs and preferences.

Objection Handling

Address Market Timing Concerns:
Guide on the fluidity of the market and offer specialized market insights for preferred locations.

Navigate Budget Limitations:
Discuss financial comfort zones and explore available financing options within their budget range.

Attend to Unmet Preferences:
Offer to stay alert for properties that match their criteria should current listings not suffice. Ask for must-have features.

Manage Working with Other Agents:
Propose a second opinion or additional market information, highlighting our unique insights and personalized approach.

Clarify Mortgage Pre-approval:
Suggest connecting with trusted mortgage advisors to facilitate the pre-approval process.

Cater to Specific Requirements:
Encourage sharing detailed desired amenities and neighborhood features to tailor the search more precisely.

Call Script Instructions

Introduction and Inquiry Type:
Greet and identify the purpose of the call. Ascertain if the potential client is looking to buy or rent.

Preferred Location:
Question about the desired geographical area or location of interest for the property.

Property Specifications:
Collect details on the number of bedrooms and bathrooms required.

Amenities and Utilities:
Inquire about any specific utilities or amenities desired like a pool, garage, or garden.

Constraints and Must-Haves:
Ask about any non-negotiables including school districts, neighborhoods, or property types.

Budgetary Considerations:
Discuss the client's budget range for purchasing or renting.

Motivation for Moving:
Understand the client’s reasons and specific desires for the new property.

Current Agent Status:
Find out if they're already working with another agent or if this is their initial consultation.

Financing Plans:
Question about their method of financing the purchase (cash or mortgage) and if they have been pre-approved.

Additional Requirements:
Solicit any other preferences or needs not previously covered.

Information Summary and Accuracy:
Recap the information received and confirm its accuracy with the potential client.

Scheduling Follow-Up:
Enquire about a convenient time for an agent to follow up with curated property options.

Farewell and Transition:
Confirm the follow-up details and express gratitude for considering Majestic Estates, then conclude the call."""



def segment_text_by_sentence(text):
    sentence_boundaries = re.finditer(r'(?<=[.!?])\s+', text)
    boundaries_indices = [boundary.start() for boundary in sentence_boundaries]

    segments = []
    start = 0
    for boundary_index in boundaries_indices:
        segments.append(text[start:boundary_index + 1].strip())
        start = boundary_index + 1
    segments.append(text[start:].strip())

    return segments

def synthesize_audio(text):
    payload = {"text": text}
    with requests.post(DEEPGRAM_TTS_URL, stream=True, headers=headers, json=payload) as r:
        return r.content

def play_audio(file_path):
    pygame.mixer.init()
    pygame.mixer.music.load(file_path)
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)

    # Signal that playback is finished
    mute_microphone.clear()

def main():
    try:
        deepgram = DeepgramClient(DEEPGRAM_API_KEY)
        dg_connection = deepgram.listen.live.v("1")

        is_finals = []

        def on_open(self, open, **kwargs):
            print("Connection Open")

        def on_message(self, result, **kwargs):
            nonlocal is_finals
            if mute_microphone.is_set():
                return  # Ignore messages while microphone is muted
            
            sentence = result.channel.alternatives[0].transcript
            if len(sentence) == 0:
                return
            if result.is_final:
                is_finals.append(sentence)
                if result.speech_final:
                    utterance = " ".join(is_finals)
                    print(f"Speech Final: {utterance}")
                    is_finals = []
                    conversation_memory.append({"role": "user", "content": sentence.strip()})
                    messages = [{"role": "system", "content": prompt}]
                    messages.extend(conversation_memory)
                    chat_completion = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=messages
                    )
                    print(chat_completion)
                    processed_text = chat_completion.choices[0].message.content.strip()
                    text_segments = segment_text_by_sentence(processed_text)
                    with open(output_audio_file, "wb") as output_file:
                        for segment_text in text_segments:
                            audio_data = synthesize_audio(segment_text)
                            output_file.write(audio_data)
                    
                    # Mute the microphone and play the audio
                    mute_microphone.set()
                    microphone.mute()
                    play_audio(output_audio_file)
                    time.sleep(0.5)
                    microphone.unmute()

            else:
                print(f"Interim Results: {sentence}")

        def on_metadata(self, metadata, **kwargs):
            print(f"Metadata: {metadata}")

        def on_speech_started(self, speech_started, **kwargs):
            print("Speech Started")

        def on_utterance_end(self, utterance_end, **kwargs):
            print("Utterance End")
            nonlocal is_finals
            if len(is_finals) > 0:
                utterance = " ".join(is_finals)
                print(f"Utterance End: {utterance}")
                is_finals = []

        def on_close(self, close, **kwargs):
            print("Connection Closed")

        def on_error(self, error, **kwargs):
            print(f"Handled Error: {error}")

        def on_unhandled(self, unhandled, **kwargs):
            print(f"Unhandled Websocket Message: {unhandled}")

        dg_connection.on(LiveTranscriptionEvents.Open, on_open)
        dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
        dg_connection.on(LiveTranscriptionEvents.Metadata, on_metadata)
        dg_connection.on(LiveTranscriptionEvents.SpeechStarted, on_speech_started)
        dg_connection.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)
        dg_connection.on(LiveTranscriptionEvents.Close, on_close)
        dg_connection.on(LiveTranscriptionEvents.Error, on_error)
        dg_connection.on(LiveTranscriptionEvents.Unhandled, on_unhandled)

        options = LiveOptions(
            model="nova-2",
            language="en-US",
            smart_format=True,
            encoding="linear16",
            channels=1,
            sample_rate=16000,
            interim_results=True,
            utterance_end_ms="1000",
            vad_events=True,
            endpointing=500,
        )

        addons = {
            "no_delay": "true"
        }

        print("\n\nPress Enter to stop recording...\n\n")
        if not dg_connection.start(options, addons=addons):
            print("Failed to connect to Deepgram")
            return

        microphone = Microphone(dg_connection.send)
        microphone.start()

        input("")
        microphone.finish()
        dg_connection.finish()

        print("Finished")

    except Exception as e:
        print(f"Could not open socket: {e}")

if __name__ == "__main__":
    output_audio_file = 'output_audio.mp3'
    main()
