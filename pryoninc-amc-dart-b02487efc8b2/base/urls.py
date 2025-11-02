from django.urls import path
from . import views
from django.contrib.auth.views import LoginView, LogoutView

urlpatterns = [
   path('login/', LoginView.as_view(template_name='registration/login.html'), name='login'),
   path('logout/', LogoutView.as_view(), name='logout'),

   path('', views.Home.as_view(), name='home'),
   path('event/', views.StartEvent.as_view(), name='start-event'),
   path('event/<int:pk>/', views.Event.as_view(), name='event'),
   path('event/<int:pk>/chat/', views.Chat.as_view(), name='chat'),
]
