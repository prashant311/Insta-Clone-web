# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from imgurpython import ImgurClient
from django.shortcuts import render, redirect
from forms import SignUpForm, LoginForm, PostForm, LikeForm, CommentForm, UpvoteForm
from models import UserModel, SessionToken, PostModel, LikeModel, CommentModel, UpvoteModel
from django.contrib.auth.hashers import make_password, check_password
from instaclone.settings import BASE_DIR
import sendgrid
from sendgrid.helpers.mail import *
from sg import apikey, my_email, imgur_id, secret, clarif_key
from datetime import timedelta
from django.utils import timezone
import clarifai
from clarifai.rest import ClarifaiApp

# Create your views here.


def signup_view(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            if len(username) > 6:
                # extra parameters for signup
                name = form.cleaned_data['name']
                email = form.cleaned_data['email']
                password = form.cleaned_data['password']
                if len(password) >= 8:
                    # password must be at least 8 characters long
                    user = UserModel(name=name, password=make_password(password), email=email, username=username)
                    user.save()
                    # sending a welcome mail to new user
                    sg = sendgrid.SendGridAPIClient(apikey=apikey)
                    from_email = Email(my_email)
                    to_email = Email(email)
                    subject = "Swacch Bharat"
                    content = Content("text/plain", "you are successfully signed up for Swacch Bharat")
                    mail = Mail(from_email, subject, to_email, content)
                    sg.client.mail.send.post(request_body=mail.get())

            return render(request, 'success.html')
    else:
        form = SignUpForm()
    return render(request, 'index.html', {'form': form})


def login_view(request):
    response_data = {}
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = UserModel.objects.filter(username=username).first()

            if user:
                if check_password(password, user.password):
                    token = SessionToken(user=user)
                    token.create_token()
                    token.save()
                    response = redirect('feed/')
                    response.set_cookie(key='session_token', value=token.session_token)
                    return response
                else:
                    response_data['message'] = 'Incorrect Password! Please try again!'

    elif request.method == 'GET':
        form = LoginForm()

    response_data['form'] = form
    return render(request, 'login.html', response_data)


# For validating the session
def check_validation(request):
    if request.COOKIES.get('session_token'):
        session = SessionToken.objects.filter(session_token=request.COOKIES.get('session_token')).first()
        if session:
            time_to_live = session.created_on + timedelta(days=1)
            if time_to_live > timezone.now():
                return session.user
    else:
        return None

    
def post_view(request):
    user = check_validation(request)
    if user:
        # import pdb; pdb.set_trace()
        if request.method == 'POST':
            form = PostForm(request.POST, request.FILES)
            if form.is_valid():
                image = form.cleaned_data.get('image')
                caption = form.cleaned_data.get('caption')
                post = PostModel(user=user, image=image, caption=caption)
                post.save()
                path = str(BASE_DIR + '/' + post.image.url)
                client = ImgurClient(imgur_id, secret)
                post.image_url = client.upload_from_path(path, anon=True)['link']
                # post.save()

                # classification of images

                app = ClarifaiApp(api_key=clarif_key)
                model = app.models.get('general-v1.3')
                response = model.predict_by_url(url=post.image_url)
                value = response['outputs'][0]['data']['concepts'][0]['value']
                if value > 0.9:  # if post is about garbage
                post.save()

                return redirect('/feed/')

        else:
            form = PostForm()
        return render(request, 'post.html', {'form': form})
    else:
        return redirect('/login/')


def feed_view(request):
    user = check_validation(request)
    if user:

        posts = PostModel.objects.all().order_by('created_on')

        for post in posts:
            existing_like = LikeModel.objects.filter(post_id=post.id, user=user).first()

            if existing_like:
                post.has_liked = True

            for comment in post.comments:
                upvoted = UpvoteModel.objects.filter(comment=comment.id, user=user).first()
                if upvoted:
                    comment.has_upvoted = True

        return render(request, 'feed.html', {'posts': posts})
    else:

        return redirect('/login/')


def like_view(request):
    user = check_validation(request)
    if user and request.method == 'POST':
        form = LikeForm(request.POST)
        if form.is_valid():
            post_id = form.cleaned_data.get('post').id
            existing_like = LikeModel.objects.filter(post_id=post_id, user=user).first()
            if not existing_like:
                LikeModel.objects.create(post_id=post_id, user=user)

                # mail to the user about the new like

                post = form.cleaned_data.get('post')
                email = post.user.email
                sg = sendgrid.SendGridAPIClient(apikey=apikey)
                from_email = Email(my_email)
                to_email = Email(email)
                subject = "Swacch Bharat"
                content = Content("text/plain", "you have a new like")
                mail = Mail(from_email, subject, to_email, content)
                sg.client.mail.send.post(request_body=mail.get())
            else:
                existing_like.delete()
            return redirect('/feed/')
    else:
        return redirect('/login/')


def comment_view(request):
    user = check_validation(request)
    if user and request.method == 'POST':
        form = CommentForm(request.POST)
        if form.is_valid():
            post_id = form.cleaned_data.get('post').id
            comment_text = form.cleaned_data.get('comment_text')
            comment = CommentModel.objects.create(user=user, post_id=post_id, comment_text=comment_text)
            comment.save()
            post = form.cleaned_data.get('post')
            email = post.user.email
            #print email

            # sending email to user who created the post about the comment
            sg = sendgrid.SendGridAPIClient(apikey=apikey)
            from_email = Email(my_email)
            to_email = Email(email)
            subject = "Swacch Bharat-new comment"
            content = Content("text/plain", "you have a new comment :" + comment_text)
            mail = Mail(from_email, subject, to_email, content)
            sg.client.mail.send.post(request_body=mail.get())

            return redirect('/feed/')
        else:
            return redirect('/feed/')
    else:
        return redirect('/login')


def logout_view(request):
    if request.method == 'GET':
        if request.COOKIES.get('session_token'):
            SessionToken.objects.filter(session_token = request.COOKIES.get('session_token')).first().delete()
        return redirect('/login/')
    else:
        return redirect('/feed/')


# method for upvoting comments
def Upvote_view(request):
    user = check_validation(request)
    if user and request.method == 'POST':

        form = UpvoteForm(request.POST)

        if form.is_valid():
            response_data = {}
            comment_id = form.cleaned_data.get('comment')
            upvoted = UpvoteModel.objects.filter(comment_id=comment_id, user=user).first()

            if not upvoted:
                UpvoteModel.objects.create(comment=comment_id, user=user)
                response_data['subject'] = 'Upvoted'
                response_data['content'] = 'Comment upvoted by :' + form.cleaned_data.get('comment').user.name

            else:
                upvoted.delete()
                response_data['subject'] = 'Downvoted'
                response_data['content'] = 'Comment downvoted by ' + form.cleaned_data.get('comment').user.name

            return redirect('/feed/')

    else:

        return redirect('/login/')

