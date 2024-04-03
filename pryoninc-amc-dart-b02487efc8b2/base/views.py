from django.shortcuts import render, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from . import models, forms
from datetime import datetime

class Home(LoginRequiredMixin, View):
    def get(self, request):
        if request.method == 'GET':
            user_events = models.Event.objects.filter(invitees=request.user).order_by('-updated_at')
            context = {'user_events': user_events}
            return render(request, 'base/home.html', context=context)

class StartEvent(LoginRequiredMixin, View):
    def get(self, request):
        if request.method == 'GET':
            form = forms.EventForm()
            context = {'form': form}
            return render(request, 'base/start-event.html', context=context)
    def post(self, request):
        if request.method == 'POST':
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
        if request.method == 'GET':
            event = models.Event.objects.get(pk=pk)
            comment_form = forms.CommentForm(instance=event)
            context = {'event': event, 'comment_form': comment_form}
        return render(request, 'base/event.html', context=context)
    def post(self, request, pk):
        event = models.Event.objects.get(pk=pk)
        if request.method == 'POST':
            if 'summarize-event' in request.POST:
                summary = event._summarize_texts(
                    collection_name=event.vectordb_collection_key
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
        if request.method == 'GET':            
            event = models.Event.objects.get(pk=pk)
            user_events = models.Event.objects.filter(invitees=request.user).order_by('-updated_at')
            queries = models.Chat.objects.filter(event=event).first().query_dict['queries']
            chat_object = models.Chat.objects.filter(event=event).first()

            try:
                sentiment_filter = models.Chat.objects.filter(event=event).first().query_dict.get('sentiment_filter')
                n_results_filter = models.Chat.objects.filter(event=event).first().query_dict.get('n_results_filter')
                sensitivity = models.Chat.objects.filter(event=event).first().query_dict.get('sensitivity')
                summarize = models.Chat.objects.filter(event=event).first().query_dict.get('summarize')
            except:
                models.Chat.objects.filter(event=event).first().query_dict['sentiment_filter'] = "All"
                sentiment_filter = models.Chat.objects.filter(event=event).first().query_dict['sentiment_filter']
                models.Chat.objects.filter(event=event).first().query_dict['n_results_filter'] = 4
                n_results_filter = models.Chat.objects.filter(event=event).first().query_dict['n_results_filter']
                models.Chat.objects.filter(event=event).first().query_dict['sensitivity'] = .8
                sensitivity = models.Chat.objects.filter(event=event).first().query_dict['sensitivity']
                models.Chat.objects.filter(event=event).first().query_dict['summarize'] = False
                models.Chat.objects.filter(event=event).first().save()
            context = {
                'event': event, 
                'user_events': user_events,
                'queries': queries,
                'sentiment_filter': sentiment_filter,
                'n_results_filter': n_results_filter,
                'sensitivity': sensitivity,
                'summarize': summarize,
                'chat_object': chat_object
                }
            return render(request, 'base/chat.html', context=context)
        
    def post(self, request, pk):
        if request.method == 'POST':
            event = models.Event.objects.get(pk=pk)
            if "query" in request.POST:
                chat_object = models.Chat.objects.filter(event=event).first()
                if chat_object:
                    query = request.POST['query']
                    chat_object._query_collection(query)
                    chat_object.query_dict['last_question'] = query
                    chat_object.save()
            
            elif "last-query" in request.POST:
                chat_object = models.Chat.objects.filter(event=event).first()
                if chat_object:
                    query = chat_object.query_dict['last_question']
                    chat_object._query_collection(query)
                    chat_object.query_dict['last_question'] = query
                    chat_object.save()

            elif "sentiment_filter" in request.POST:
                chat_object = models.Chat.objects.filter(event=event).first()
                if chat_object:
                    chat_object.query_dict['sentiment_filter'] = request.POST['sentiment_filter']
                    chat_object.save()

            elif "update-n-results" in request.POST:
                chat_object = models.Chat.objects.filter(event=event).first()
                if chat_object:
                    chat_object.query_dict['n_results_filter'] = int(request.POST['selected-n'])
                    chat_object.save()
            
            elif "update-sensitivity" in request.POST:
                chat_object = models.Chat.objects.filter(event=event).first()
                if chat_object:
                    chat_object.query_dict['sensitivity'] = float(request.POST['selected-sensitivity'])
                    chat_object.save()

            elif "clear-chat" in request.POST:
                chat_object = models.Chat.objects.filter(event=event).first()
                chat_object.query_dict['queries'] = []
                chat_object.save()

            elif "summarize" in request.POST:
                chat_object = models.Chat.objects.filter(event=event).first()
                chat_object.query_dict['summarize'] = not chat_object.query_dict['summarize']
                chat_object.save()

        return redirect('chat', event.id)