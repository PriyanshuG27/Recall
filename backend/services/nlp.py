import spacy

# Initialize the blank English sentencizer once.
# Blank model uses pure rules (no heavy model files or downloads), ensuring extreme speed and zero network calls.
nlp = spacy.blank("en")
nlp.add_pipe("sentencizer")

def get_spacy_sentencizer():
    """Returns the shared blank spaCy sentencizer instance."""
    return nlp
