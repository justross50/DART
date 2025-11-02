import ollama
import logging

logger = logging.getLogger(__name__)

class OllamaClient:
    """
    A client to interact with the Ollama API.
    """
    def __init__(self):
        try:
            self.client = ollama.Client()
            self.models = self._get_models()
        except Exception as e:
            logger.error(f"Failed to connect to Ollama. Please ensure it is running. Error: {e}")
            self.client = None
            self.models = []

    def _get_models(self):
        """Fetches the list of available models from Ollama."""
        if not self.client:
            return []
        try:
            models_data = self.client.list()
            # The Ollama API now returns 'models': [{'model': '...', 'modified_at': ...}, ...]
            return [model.get('model') or model.get('name') for model in models_data.get('models', [])]
        except Exception as e:
            logger.error(f"Failed to fetch Ollama models: {e}")
            return []

    def generate(self, model_name, prompt):
        """Generates a response from a given model and prompt."""
        if not self.client:
            return "Ollama client is not available. Please make sure Ollama is running."
        if not self.models:
             return "No Ollama models found. Please pull a model (e.g., 'ollama pull llama3')."
        if model_name not in self.models:
            logger.warning(f"Model '{model_name}' not found. Defaulting to {self.models[0]}.")
            model_name = self.models[0]
        
        try:
            response = self.client.generate(model=model_name, prompt=prompt, stream=False)
            return response.get('response', 'No response from model.')
        except Exception as e:
            logger.error(f"Error during Ollama generation: {e}")
            return "An error occurred while generating the response."
