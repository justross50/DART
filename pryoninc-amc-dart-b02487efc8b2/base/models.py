"""
Models for the DART application.

This module previously relied on external libraries such as `chromadb` for vector
storage and `sentence_transformers` for generating high‑dimensional embeddings.
The original hackathon prototype also attempted to call out to an Ollama
service for summarisation.  In our offline environment neither chroma nor the
large language model service is available.  To make the application work
without these optional dependencies the model implementations below use simple
Python built‑ins and heuristics:

* Comments are stored in the Django database only.  We no longer attempt to
  create or manage an external vector database.
* Instead of generating embeddings with `sentence_transformers` we use a very
  simple similarity function based on the difflib `SequenceMatcher`.  This
  allows us to rank comment relevance without any heavy dependencies.
* Sentiment is estimated with a naive rule based on counting positive and
  negative words.  If you require more accurate sentiment analysis you can
  integrate your own model here.
* Summaries fall back to a simple extraction of the first few sentences if
  an Ollama model cannot be reached.

The rest of the application (views, forms and templates) remains largely
unchanged.  These changes mean that the DART prototype can run on a vanilla
Python/Django install without any network connectivity.
"""

from django.db import models
from django.contrib.auth.models import User
import uuid
from .ollama_client import OllamaClient
import logging
from difflib import SequenceMatcher
import re

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

class Event(models.Model):
    """
    Represents a single decision event.  Events are created by a user and
    span a date range.  Invitees may add comments which are later surfaced in
    the chat interface.  A UUID is generated at creation time to uniquely
    identify the event – the original application used this key to name a
    Chroma collection.  We keep it here for backwards compatibility but no
    longer create an external vector database.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField()
    invitees = models.ManyToManyField(User, related_name='invited_events')
    summary = models.TextField(blank=True, null=True)
    vectordb_collection_key = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Basic positive and negative lexicons for naive sentiment analysis.
    POSITIVE_WORDS = {
        'good', 'great', 'excellent', 'amazing', 'awesome', 'fantastic',
        'positive', 'love', 'like', 'satisfied', 'happy', 'efficient', 'quick',
        'helpful', 'supportive', 'effective', 'successful'
    }
    NEGATIVE_WORDS = {
        'bad', 'terrible', 'horrible', 'awful', 'hate', 'negative', 'poor',
        'unsatisfied', 'sad', 'inefficient', 'slow', 'unhappy', 'problem',
        'issue', 'fail', 'failure', 'difficult'
    }

    def __init__(self, *args, **kwargs):
        """
        The constructor used to initialise external resources.  In the original
        version this would connect to a Chroma vector database and load a
        sentence embedding model.  To keep the project lightweight those
        dependencies have been removed.  We still generate the collection key
        but the `db_client` and `embedding_model` attributes are no longer
        created.
        """
        super().__init__(*args, **kwargs)
        # The following attributes are left for backwards compatibility but
        # intentionally set to None because we do not use Chroma or embedding
        # models any longer.
        self.db_client = None
        self.embedding_model = None

    def _generate_key(self) -> str:
        """Generate a unique UUID for this event."""
        return str(uuid.uuid4())

    def _create_collection(self) -> None:
        """
        Previously this method created a collection in the Chroma database and
        initialised a Chat record.  Since we are no longer using Chroma we
        simply ensure a Chat object exists for this event.
        """
        try:
            # Ensure a chat record exists for this event.  We associate the
            # creating user with the chat for auditing, though the user field
            # is optional in the simplified model.
            Chat.objects.get_or_create(event=self, defaults={'user': self.user})
        except Exception as e:
            logger.error(f"Error creating chat for event {self.id}: {e}")

    def _simple_summarise(self, text: str) -> str:
        """
        Very naive summarisation: take the first three sentences of the text.
        This function is used as a fallback when an Ollama server is not
        available or returns an error.
        """
        # Split on sentence boundaries using punctuation.  This is a crude
        # approach but avoids any heavy NLP dependencies.
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        if not sentences:
            return text.strip()
        return ' '.join(sentences[:3]).strip()

    def _summarize_texts(self, collection_name: str, model_name: str = 'llama3') -> str:
        """
        Create a summary of all comments associated with this event.  The
        `collection_name` argument is ignored but kept for API compatibility.

        If an Ollama server is reachable, it will be used to summarise the
        content.  Otherwise we fall back to a very simple extractive summary.
        """
        try:
            # Gather all comment text for this event.
            comment_qs = Comment.objects.filter(event=self)
            documents: list[str] = []
            for comment in comment_qs:
                parts = []
                if comment.observation:
                    parts.append(comment.observation)
                if comment.discussion:
                    parts.append(comment.discussion)
                if comment.recommendation:
                    parts.append(comment.recommendation)
                documents.append(' '.join(parts))
            if not documents:
                return "Not enough content to summarize."

            full_text = ' '.join(documents)
            max_length = 15000  # Ensure prompts do not become unmanageable
            truncated_text = full_text[:max_length]
            prompt = (
                "Please provide a concise, professional summary of the following comments:\n\n"
                f"{truncated_text}"
            )
            # Attempt to use Ollama if available.
            ollama_client = OllamaClient()
            summary = ollama_client.generate(model_name=model_name, prompt=prompt)
            # The Ollama client returns a string even when it fails.  Detect
            # failure messages and fall back to a local summary.
            fallback_msgs = [
                "Ollama client is not available",
                "No Ollama models found",
                "An error occurred while generating the response."
            ]
            if any(msg in summary for msg in fallback_msgs):
                return self._simple_summarise(truncated_text)
            return summary
        except Exception as e:
            logger.error(f"Error summarizing texts for event {self.id}: {e}")
            # Fall back to simple summary in case of unexpected error
            try:
                return self._simple_summarise(truncated_text)
            except Exception:
                return "An error occurred during summarization."

    def _upload_comments_to_collection(self, request, collection_name: str) -> None:
        """
        Upload a structured CSV file containing comments for this event.

        The expected CSV has headers `observation`, `discussion` and
        `recommendation`.  For each row a new `Comment` object is created
        associated with the uploading user and this event.  Fields are
        optional; missing values default to empty strings.  Additional
        columns in the CSV are ignored.
        """
        try:
            uploaded_file = request.FILES.get('comments_file')
            if not uploaded_file:
                logger.warning(f"No file provided for upload on event {self.id}.")
                return
            # Read and decode the uploaded CSV.  We assume UTF‑8; strip any
            # BOM if present using utf‑8‑sig.
            import csv
            import io
            file_data = uploaded_file.read().decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(file_data))
            count = 0
            for row in reader:
                observation = row.get('observation', '') or ''
                discussion = row.get('discussion', '') or ''
                recommendation = row.get('recommendation', '') or ''
                Comment.objects.create(
                    user=request.user,
                    event=self,
                    observation=observation,
                    discussion=discussion,
                    recommendation=recommendation
                )
                count += 1
            logger.info(f"Uploaded {count} comments for event {self.id} from CSV.")
        except Exception as e:
            logger.error(f"Error uploading comments for event {self.id}: {e}")

    def __str__(self) -> str:
        return self.name

class Comment(models.Model):
    """
    A comment attached to an event.  Comments comprise an observation,
    optional discussion and a recommendation.  In this simplified version
    comments are stored directly in the Django database and are not loaded
    into an external vector store.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    observation = models.TextField()
    discussion = models.TextField(blank=True, null=True)
    recommendation = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def _load_comment_to_collection(self, collection_name: str) -> None:
        """
        Placeholder method retained for API compatibility.  In the absence of
        a vector store this method does nothing but can be extended to
        perform any additional processing when a comment is created.
        """
        logger.info(
            f"_load_comment_to_collection called for comment {self.id}, but vector "
            f"operations are disabled in this version."
        )

    def __str__(self) -> str:
        return f'Comment by {self.user.username} on {self.event.name}'

class Chat(models.Model):
    """
    A chat session for an event.  Queries are stored in a JSON structure on
    this model.  The `_query_collection` method performs a naïve search over
    all comments associated with the event instead of querying a vector
    database.  Sentiment filtering and simple summarisation are supported.

    Fields such as `created_at`, `updated_at`, `user` and `summarize` are
    retained for compatibility with the original database schema but are not
    strictly required by the simplified logic.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    query_dict = models.JSONField(blank=True, default=dict, null=True)
    summarize = models.BooleanField(default=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)

    def _estimate_sentiment(self, text: str) -> str:
        """
        Classify text as Positive, Negative or Neutral based on a simple word
        overlap with predefined lexicons.  This method can be replaced with a
        more sophisticated sentiment analyser if desired.
        """
        words = re.findall(r"\b\w+\b", text.lower())
        pos_count = sum(1 for w in words if w in self.event.POSITIVE_WORDS)
        neg_count = sum(1 for w in words if w in self.event.NEGATIVE_WORDS)
        if pos_count > neg_count:
            return "Positive"
        if neg_count > pos_count:
            return "Negative"
        return "Neutral"

    def _similarity_score(self, query: str, text: str) -> float:
        """
        Compute a similarity score between the query and a document.  We use
        Python's difflib.SequenceMatcher which returns a ratio between 0 and 1.
        Higher values indicate a closer match.
        """
        try:
            return SequenceMatcher(None, query.lower(), text.lower()).ratio()
        except Exception:
            return 0.0

    def _query_collection(self, query: str, model_name: str = 'llama3') -> None:
        """
        Perform a search over all comments for this event, applying
        sentiment filtering and returning the top N results sorted by
        similarity.  The results are stored in `query_dict` for display in the
        chat interface.
        """
        try:
            sentiment_filter = self.query_dict.get('sentiment_filter', 'All')
            n_results = int(self.query_dict.get('n_results_filter', 4))
            # Retrieve all comments for this event
            comment_qs = Comment.objects.filter(event=self.event)
            scored = []
            for comment in comment_qs:
                parts = []
                if comment.observation:
                    parts.append(comment.observation)
                if comment.discussion:
                    parts.append(comment.discussion)
                if comment.recommendation:
                    parts.append(comment.recommendation)
                doc = ' '.join(parts)
                sentiment = self._estimate_sentiment(doc)
                if sentiment_filter != 'All' and sentiment != sentiment_filter:
                    continue
                score = self._similarity_score(query, doc)
                scored.append((doc, sentiment, score))
            # Sort by descending similarity
            scored.sort(key=lambda x: x[2], reverse=True)
            # Select top n_results
            top = scored[:n_results]
            responses = []
            for doc, sentiment, score in top:
                # Represent distance as (1 - score) to align with previous API
                responses.append((doc, sentiment, f"{(1 - score):.2f}"))
            # Optionally summarise the context
            summary = None
            if self.query_dict.get('summarize', False) and responses:
                context = ' '.join([doc for doc, _, _ in top])
                prompt = (
                    "Based on the following context, answer the user's question.\n\n"
                    f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"
                )
                ollama_client = OllamaClient()
                summary = ollama_client.generate(model_name=model_name, prompt=prompt)
                # Fallback to simple summary if necessary
                fallback_msgs = [
                    "Ollama client is not available",
                    "No Ollama models found",
                    "An error occurred while generating the response."
                ]
                if any(msg in summary for msg in fallback_msgs):
                    # Use the event summarisation fallback on the context
                    summary = self.event._simple_summarise(context)
            # Insert the query at the beginning of the history
            self.query_dict.setdefault('queries', [])
            self.query_dict['queries'].insert(0, {
                'query': query,
                'responses': responses,
                'summary': summary
            })
            self.save()
        except Exception as e:
            logger.error(f"Error querying comments for event {self.event.id}: {e}")
            self.query_dict.setdefault('queries', [])
            self.query_dict['queries'].insert(0, {
                'query': query,
                'responses': [("An error occurred while processing your query.", "Error", "N/A")],
                'summary': "Error processing request."
            })
            self.save()

    def __str__(self) -> str:
        return f'Chat for {self.event.name}'
