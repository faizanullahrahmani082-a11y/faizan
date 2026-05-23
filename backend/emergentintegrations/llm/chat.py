import os
import google.generativeai as genai


class UserMessage:
    def __init__(self, text: str):
        self.text = text


class LlmChat:
    def __init__(self, api_key: str = None, session_id: str = None, system_message: str = None):
        self._api_key = api_key
        self._session_id = session_id
        self._system_message = system_message
        self._model_name = "gemini-1.5-flash"
        self._history = []

    def with_model(self, provider: str, model: str):
        self._model_name = model
        return self

    async def send_message(self, message: UserMessage) -> str:
        if not self._api_key:
            return (
                "⚠️ AI service not configured. "
                "Add GOOGLE_API_KEY to backend/.env to enable the AI assistant."
            )
        try:
            genai.configure(api_key=self._api_key)
            model = genai.GenerativeModel(
                model_name=self._model_name,
                system_instruction=self._system_message,
            )
            chat = model.start_chat(history=self._history)
            response = await chat.send_message_async(message.text)
            self._history.append({"role": "user", "parts": [message.text]})
            self._history.append({"role": "model", "parts": [response.text]})
            return response.text
        except Exception as e:
            return f"AI service error: {str(e)}"
