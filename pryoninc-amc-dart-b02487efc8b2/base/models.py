from django.db import models
from django.dispatch import receiver
from django.db.models.signals import post_save
import random, string, re
from chromadb.utils import embedding_functions
from chromadb import PersistentClient
from transformers import pipeline
from transformers import T5TokenizerFast, T5ForConditionalGeneration
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
import numpy as np
from io import TextIOWrapper
import csv

class Event(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    invitees = models.ManyToManyField('auth.User', related_name='invitees')
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    vectordb_collection_key = models.CharField(max_length=100)
    summary = models.TextField(null=True, blank=True)

    def _generate_key(self) -> str:
        def _is_valid_ipv4(token):
            parts = token.split('.')
            if len(parts) != 4:
                return False
            for part in parts:
                if not part.isdigit() or not 0 <= int(part) <= 255:
                    return False
            return True
        
        while True:
            length = random.randint(3, 63)
            token = ''.join(random.choices(string.ascii_letters + string.digits + '_-', k=length))
            conditions = [
                re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9_-]*[a-zA-Z0-9])?$', token),
                '..' not in token,
                not _is_valid_ipv4(token)
            ]
            if all(conditions):
                return token

    def _create_collection(
            self,
            clear: bool = False
            ) -> None:
        client = PersistentClient(path='chroma')
        embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="llm/models/all-MiniLM-L6-v2")
        name = self.vectordb_collection_key
        try:
            client.create_collection(name, embedding_function=embedding_function, metadata={"hnsw:space": "cosine"})
        except Exception as e:
            if clear:
                client.delete_collection(name)
                client.create_collection(name, embedding_function=embedding_function, metadata={"hnsw:space": "cosine"})
            else:
                print(f'{e}')

    def _summarize_texts(
            self,
            collection_name: str = None,
            texts: list[str] = None,
            ) -> str:
        local_model = "llm/models/LaMini-Flan-T5-783M"
        tokenizer = T5TokenizerFast.from_pretrained(local_model)
        model = T5ForConditionalGeneration.from_pretrained(local_model)
        if not texts and collection_name:
            client = PersistentClient(path='chroma')
            collection = client.get_collection(collection_name)
            texts = collection.get()['documents']
        if texts:
            if len(texts) == 1:
                num_clusters = 1
                max_length = 100
            elif len(texts) in range(2, 5):
                num_clusters = len(texts) - 1
                max_length = 200
            else:
                num_clusters = 5
                max_length = 300
            embeddings_model = SentenceTransformer("llm/models/all-MiniLM-L6-v2")
            embeddings = embeddings_model.encode(texts)
            kmeans = KMeans(n_clusters=num_clusters, random_state=42).fit(embeddings)
            closest_indices = []
            for i in range(num_clusters):
                distances = np.linalg.norm(embeddings - kmeans.cluster_centers_[i], axis=1)
                closest_index = np.argmin(distances)
                closest_indices.append(closest_index)
            selected_indices = sorted(closest_indices)
            selected_docs = [texts[i] for i in selected_indices]
            reviews_text = "\n".join(selected_docs)

            prompt = f"You are a helpful research assistant tasked with summarizing an event. These are the comments that the attendees made about the event: '{reviews_text}'. Given these comments, summarize the event."

            pipe_sum = pipeline(
                'summarization',
                model = model,
                tokenizer = tokenizer,
                max_length = max_length,
                # min_length = 30,
                )
            
            summary = pipe_sum(prompt)
            return summary[0]['summary_text']
        else:
            return "No comments to summarize."

    def _upload_comments_to_collection(
            self,
            request,
            collection_name: str,
        ) -> None:
        data_file = request.FILES['data-file']
        content = TextIOWrapper(data_file.file, encoding='utf-8-sig')
        csv_reader = csv.DictReader(content)
        cols = csv_reader.fieldnames
        conditions = [
            'observation' in cols,
            'discussion' in cols,
            'recommendation' in cols
        ]
        if all(conditions):
            for row in csv_reader:
                observation = row.get('observation') or None
                discussion = row.get('discussion') or ''
                recommendation = row.get('recommendation') or None
                if observation and recommendation:
                    new_comment = Comment.objects.create(
                        user=request.user,
                        event=self,
                        observation=observation,
                        discussion=discussion,
                        recommendation=recommendation
                    )
                    new_comment.save()
                    new_comment._load_comment_to_collection(
                        collection_name=collection_name,
                    )

class Comment(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    observation = models.TextField()
    discussion = models.TextField()
    recommendation = models.TextField()

    def _load_comment_to_collection(
            self,
            collection_name: str, 
            ) -> None:
        try:
            client = PersistentClient(path='chroma')
            sentiment_dict = {
                'POS': 'positive',
                'NEU': 'neutral',
                'NEG': 'negative'
            }
            sentiment_analysis = pipeline("sentiment-analysis", model="llm/models/bertweet-base-sentiment-analysis")
            results = sentiment_analysis(self.observation)
            for result in results:
                sentiment = sentiment_dict.get(result['label'])
            
            collection = client.get_collection(collection_name)
            collection.add(
                documents=[self.observation],
                metadatas=[{
                    'user': str(self.user) ,
                    'event_id': self.event.id, 
                    'comment_id': self.id, 
                    'sentiment': sentiment
                    }],
                ids=[str(self.id)]
            )
        except Exception as e:
            print(f'Error creating document in {collection_name}. {e}')

class Chat(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    query_dict = models.JSONField(default=dict, null=True, blank=True)
    summarize = models.BooleanField(default=False)

    @receiver(post_save, sender=Event)
    def create_chat(sender, instance, created, **kwargs):
        if created:
            chat = Chat.objects.create(event=instance, user=instance.user)
        else:
            chat = Chat.objects.filter(event=instance).first()
            if not chat:
                chat = Chat.objects.create(event=instance, user=instance.user)
        chat.query_dict['queries'] = []
        chat.query_dict['last_question'] = None
        chat.query_dict['sentiment_filter'] = 'all'
        chat.query_dict['n_results_filter'] = 4
        chat.query_dict['summarize'] = False
        chat.query_dict['sensitivity'] = 0.8
        chat.save()

    def _query_collection(
            self,
            query: str
            ) -> None:
        try:
            client = PersistentClient(path='chroma')
            collection = client.get_collection(self.event.vectordb_collection_key)
            if self.query_dict['sentiment_filter'] == 'all':
                results = collection.query(
                    query_texts=[query], 
                    n_results=self.query_dict['n_results_filter']
                    )
            else:
                results = collection.query(
                    query_texts=[query], 
                    n_results=self.query_dict['n_results_filter'],
                    where={'sentiment': self.query_dict['sentiment_filter']}
                    )
                
            result = {}
            for id_list, distance_list, metadata_list, document_list in zip(results['ids'][0], results['distances'][0], results['metadatas'][0], results['documents'][0]):
                result[int(id_list)] = {
                    'distance': distance_list,
                    'metadatas': metadata_list,
                    'document': document_list
                }
            filtered_data = {}
            for id_, values in result.items():
                if values['distance'] <= self.query_dict['sensitivity']:
                    filtered_data[id_] = values
            text_responses = [filtered_data[id_]['document'] for id_ in filtered_data]

            if text_responses:
                if self.query_dict['summarize']:
                    summary = self.event._summarize_texts(texts=text_responses)
                else:
                    summary = None

                sentiments = [filtered_data[id_]['metadatas']['sentiment'] for id_ in filtered_data]
                distances = [round(filtered_data[id_]['distance'],2) for id_ in filtered_data]
                self.query_dict['queries'].append({
                    'query': query, 
                    'responses': list(zip(text_responses, sentiments, distances)), 
                    'summary': summary
                    })
                self.save()
            else:
                self.query_dict['queries'].append({
                    'query': query, 
                    'responses': [('No results, try adjusting the senstivity.', 'NA', 'NA')],
                    'summary': None
                    })
                self.save()

        except Exception as e:
            print(f'Error querying {collection}. {e}')
            