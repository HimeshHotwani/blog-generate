from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.conf import settings
import json
import yt_dlp
import assemblyai as aai
import openai
from .models import BlogPost
import os
import logging

# Set up logging
logger = logging.getLogger(__name__)

# Create your views here.
@login_required
def index(request):
    return render(request, 'index.html')

@csrf_exempt
def generate_blog(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            yt_link = data['link']
        except (KeyError, json.JSONDecodeError):
            return JsonResponse({'error': 'Invalid data sent'}, status=400)

        # Get YouTube title
        title = yt_title(yt_link)
        if not title:
            return JsonResponse({'error': 'Failed to get YouTube title'}, status=500)

        # Get transcript
        transcription = get_transcription(yt_link)
        if not transcription:
            return JsonResponse({'error': 'Failed to get transcript'}, status=500)

        # Use OpenAI to generate the blog
        blog_content = generate_blog_from_transcription(transcription)
        if not blog_content:
            return JsonResponse({'error': 'Failed to generate blog article'}, status=500)

        # Save blog article to database
        new_blog_article = BlogPost.objects.create(
            user=request.user,
            youtube_title=title,
            youtube_link=yt_link,
            generated_content=blog_content,
        )
        new_blog_article.save()

        # Return blog article as a response
        return JsonResponse({'content': blog_content})
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)

def yt_title(link):
    try:
        with yt_dlp.YoutubeDL() as ydl:
            info_dict = ydl.extract_info(link, download=False)
            title = info_dict.get('title', None)
            if title:
                return title
    except Exception as e:
        logger.error(f"Error retrieving title from YouTube: {e}")
        return None

def download_audio(link):
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(settings.MEDIA_ROOT, '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'ffmpeg_location': 'C:\\ffmpeg\\ffmpeg-master-latest-win64-gpl-shared\\bin'  # Replace this with the path to your ffmpeg executable
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(link, download=True)
            audio_file = ydl.prepare_filename(info_dict).replace('.webm', '.mp3').replace('.m4a', '.mp3')
            logger.info(f"Audio file downloaded: {audio_file}")
            return audio_file
    except Exception as e:
        logger.error(f"Error downloading audio with yt-dlp: {e}")
        return None

def get_transcription(link):
    audio_file = download_audio(link)
    if not audio_file:
        logger.error("No audio file returned from download_audio")
        return None

    aai.settings.api_key = ""  # Set your AssemblyAI API key here

    transcriber = aai.Transcriber()
    try:
        transcript = transcriber.transcribe(audio_file)
        return transcript.text
    except Exception as e:
        logger.error(f"Error transcribing audio with AssemblyAI: {e}")
        return None

def generate_blog_from_transcription(transcription):
    openai.api_key = ""  # Set your OpenAI API key here

    prompt = f"Based on the following transcript from a YouTube video, write a comprehensive blog article. The content should be based on the transcript but formatted as a proper blog article:\n\n{transcription}\n\nArticle:"

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # Change to "gpt-4" if you have access
            messages=[
                {"role": "system", "content": "You are a helpful assistant that writes blog articles."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000
        )
        generated_content = response.choices[0].message['content'].strip()
        return generated_content
    except Exception as e:
        logger.error(f"Error generating blog content with OpenAI: {e}")
        return None


def blog_list(request):
    blog_articles = BlogPost.objects.filter(user=request.user)
    return render(request, "all-blogs.html", {'blog_articles': blog_articles})

def blog_details(request, pk):
    blog_article_detail = BlogPost.objects.get(id=pk)
    if request.user == blog_article_detail.user:
        return render(request, 'blog-details.html', {'blog_article_detail': blog_article_detail})
    else:
        return redirect('/')

def user_login(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('/')
        else:
            error_message = "Invalid username or password"
            return render(request, 'login.html', {'error_message': error_message})

    return render(request, 'login.html')

def user_signup(request):
    if request.method == 'POST':
        username = request.POST['username']
        email = request.POST['email']
        password = request.POST['password']
        repeatPassword = request.POST['repeatPassword']

        if password == repeatPassword:
            try:
                user = User.objects.create_user(username, email, password)
                user.save()
                login(request, user)
                return redirect('/')
            except Exception as e:
                error_message = f'Error creating account: {e}'
                return render(request, 'signup.html', {'error_message': error_message})
        else:
            error_message = 'Passwords do not match'
            return render(request, 'signup.html', {'error_message': error_message})

    return render(request, 'signup.html')

def user_logout(request):
    logout(request)
    return redirect('/')
