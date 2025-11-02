from django import forms
from .models import Event, Comment

class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['name', 'start_date', 'end_date']
        widgets = {
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'datetime-local'})
        }

class CommentForm(forms.ModelForm):
    observation = forms.CharField(required=True, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Enter your observation...'}))
    discussion = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Enter your discussion...\n(Optional)'}))
    recommendation = forms.CharField(required=True, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Enter your recommendation...'}))

    class Meta:
        model = Comment
        fields = ['observation', 'discussion', 'recommendation']
