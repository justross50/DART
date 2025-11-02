from django.shortcuts import render, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from . import models, forms
from datetime import datetime
from .ollama_client import OllamaClient

class Home(LoginRequiredMixin, View):
    def get(self, request):
        user_events = models.Event.objects.filter(invitees=request.user).order_by('-updated_at')
        context = {'user_events': user_events}
        return render(request, 'base/home.html', context=context)

class StartEvent(LoginRequiredMixin, View):
    def get(self, request):
        form = forms.EventForm()
        context = {'form': form}
        return render(request, 'base/start-event.html', context=context)
    
    def post(self, request):
        if 'start-event' in request.POST:
            key = models.Event()._generate_key()
            name = request.POST['name']
            start = request.POST['start_date']
            original_start_date = datetime.strptime(start, "%Y-%m-%d")
            formatted_start_date_string = original_start_date.strftime("%Y-%m-%d")
            end = request.POST['end_date']
            original_end_date = datetime.strptime(end, "%Y-%m-%d")
            formatted_end_date_string = original_end_date.strftime("%Y-%m-%d")
            new_event = models.Event.objects.create(
                user=request.user,
                name=name,
                start_date=formatted_start_date_string,
                end_date=formatted_end_date_string,
                vectordb_collection_key=key
            )
            new_event.invitees.add(request.user)
            new_event.save()
            new_event._create_collection()

            return redirect('event', new_event.id)
        return redirect('start-event')
        
class Event(LoginRequiredMixin, View):
    def get(self, request, pk):
        event = models.Event.objects.get(pk=pk)
        comment_form = forms.CommentForm(instance=event)
        ollama_client = OllamaClient()
        context = {
            'event': event, 
            'comment_form': comment_form,
            'ollama_models': ollama_client.models
        }
        return render(request, 'base/event.html', context=context)

    def post(self, request, pk):
        event = models.Event.objects.get(pk=pk)
        if 'summarize-event' in request.POST:
            model_name = request.POST.get('ollama-model')
            summary = event._summarize_texts(
                collection_name=event.vectordb_collection_key,
                model_name=model_name
            )
            event.summary = summary
            event.save()

        elif 'submit-comments' in request.POST:
            new_comment = models.Comment.objects.create(
                user=request.user,
                event=event,
                observation=request.POST['observation'],
                discussion=request.POST['discussion'],
                recommendation=request.POST['recommendation']
            )
            new_comment.save()
            new_comment._load_comment_to_collection(
                collection_name=event.vectordb_collection_key,
            )
        
        elif 'upload-comments' in request.POST:
            event._upload_comments_to_collection(
                request=request,
                collection_name=event.vectordb_collection_key
            )

        return redirect('event', event.id)
    
class Chat(LoginRequiredMixin, View):
    def get(self, request, pk):
        event = models.Event.objects.get(pk=pk)
        user_events = models.Event.objects.filter(invitees=request.user).order_by('-updated_at')
        # Ensure a chat exists for this event.  Provide a default user when
        # creating to satisfy the non‑nullable `user` field on Chat.
        chat_object, _ = models.Chat.objects.get_or_create(event=event, defaults={'user': request.user})
        queries = chat_object.query_dict.get('queries', [])
        
        ollama_client = OllamaClient()

        # Set default values if they don't exist
        if 'sentiment_filter' not in chat_object.query_dict:
            chat_object.query_dict['sentiment_filter'] = "All"
        if 'n_results_filter' not in chat_object.query_dict:
            chat_object.query_dict['n_results_filter'] = 4
        if 'sensitivity' not in chat_object.query_dict:
            chat_object.query_dict['sensitivity'] = 0.8
        if 'summarize' not in chat_object.query_dict:
            chat_object.query_dict['summarize'] = False
        # Select a default model for chat.  Prefer gemma3n if it exists, otherwise
        # use the first available model.  Only set if none has been chosen.
        if 'selected_model' not in chat_object.query_dict and ollama_client.models:
            preferred = None
            for m in ollama_client.models:
                # normalise names to handle tags like gemma3n:latest
                if m.lower().startswith('gemma3n'):
                    preferred = m
                    break
            chat_object.query_dict['selected_model'] = preferred or ollama_client.models[0]
        
        chat_object.save()

        context = {
            'event': event, 
            'user_events': user_events,
            'queries': queries,
            'chat_object': chat_object,
            'ollama_models': ollama_client.models,
            'selected_model': chat_object.query_dict.get('selected_model'),
            'sentiment_filter': chat_object.query_dict.get('sentiment_filter'),
            'n_results_filter': chat_object.query_dict.get('n_results_filter'),
            'sensitivity': chat_object.query_dict.get('sensitivity'),
            'summarize': chat_object.query_dict.get('summarize'),
        }
        return render(request, 'base/chat.html', context=context)
        
    def post(self, request, pk):
        event = models.Event.objects.get(pk=pk)
        chat_object = models.Chat.objects.filter(event=event).first()

        if not chat_object:
            return redirect('chat', event.id)

        if "query" in request.POST and request.POST['query']:
            query = request.POST['query']
            model_name = chat_object.query_dict.get('selected_model')
            chat_object._query_collection(query, model_name=model_name)
            chat_object.query_dict['last_question'] = query
            chat_object.save()
        
        elif "last-query" in request.POST:
            if chat_object.query_dict.get('last_question'):
                query = chat_object.query_dict['last_question']
                model_name = chat_object.query_dict.get('selected_model')
                chat_object._query_collection(query, model_name=model_name)
                chat_object.save()

        elif "select-model" in request.POST:
            chat_object.query_dict['selected_model'] = request.POST.get('ollama-model')
            chat_object.save()

        elif "sentiment_filter" in request.POST:
            chat_object.query_dict['sentiment_filter'] = request.POST['sentiment_filter']
            chat_object.save()

        elif "update-n-results" in request.POST:
            chat_object.query_dict['n_results_filter'] = int(request.POST['selected-n'])
            chat_object.save()
        
        elif "update-sensitivity" in request.POST:
            chat_object.query_dict['sensitivity'] = float(request.POST['selected-sensitivity'])
            chat_object.save()

        elif "clear-chat" in request.POST:
            chat_object.query_dict['queries'] = []
            chat_object.save()

        elif "summarize" in request.POST:
            chat_object.query_dict['summarize'] = not chat_object.query_dict.get('summarize', False)
            chat_object.save()

        return redirect('chat', event.id)
