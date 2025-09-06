"""
Forms for the transcriber app
"""
from django import forms
from captcha.fields import CaptchaField
from .models import Comment


class CommentForm(forms.ModelForm):
    """Form for adding comments to transcriptions"""
    
    class Meta:
        model = Comment
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={
                'rows': 4,
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-musical-gold focus:border-musical-gold transition-colors resize-none bg-white text-gray-900',
                'placeholder': 'Share your thoughts about this transcription...',
                'maxlength': '2000',
                'style': 'background-color: white !important; color: #111827 !important;'
            })
        }
        labels = {
            'content': ''
        }


class AnonymousCommentForm(forms.ModelForm):
    """Form for anonymous comments with captcha"""
    
    captcha = CaptchaField(
        label='Verification',
        help_text='Please complete the captcha to verify you are human',
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-musical-gold focus:border-musical-gold transition-colors bg-white text-gray-900',
            'placeholder': 'Enter the characters above',
            'style': 'background-color: white !important; color: #111827 !important;'
        })
    )
    
    class Meta:
        model = Comment
        fields = ['anonymous_name', 'content']
        widgets = {
            'anonymous_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-musical-gold focus:border-musical-gold transition-colors bg-white text-gray-900',
                'placeholder': 'Your name (optional)',
                'maxlength': '100',
                'style': 'background-color: white !important; color: #111827 !important;'
            }),
            'content': forms.Textarea(attrs={
                'rows': 4,
                'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-musical-gold focus:border-musical-gold transition-colors resize-none bg-white text-gray-900',
                'placeholder': 'Share your thoughts about this transcription...',
                'maxlength': '2000',
                'style': 'background-color: white !important; color: #111827 !important;'
            })
        }
        labels = {
            'anonymous_name': 'Name',
            'content': 'Comment'
        }