from django.core.management.base import BaseCommand
from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp
from django.conf import settings


class Command(BaseCommand):
    help = 'Set up OAuth providers for GitHub and Google'

    def handle(self, *args, **options):
        # Update site domain
        site = Site.objects.get(pk=settings.SITE_ID)
        site.domain = 'localhost:8000'  # Update this for production
        site.name = 'RiffScribe'
        site.save()
        self.stdout.write(self.style.SUCCESS(f'Updated site: {site.domain}'))

        # Set up GitHub OAuth (if credentials are provided)
        if settings.GITHUB_CLIENT_ID and settings.GITHUB_CLIENT_SECRET:
            github_app, created = SocialApp.objects.get_or_create(
                provider='github',
                defaults={
                    'name': 'GitHub',
                    'client_id': settings.GITHUB_CLIENT_ID,
                    'secret': settings.GITHUB_CLIENT_SECRET,
                }
            )
            if not created:
                github_app.client_id = settings.GITHUB_CLIENT_ID
                github_app.secret = settings.GITHUB_CLIENT_SECRET
                github_app.save()
            
            github_app.sites.add(site)
            self.stdout.write(self.style.SUCCESS(
                f'{"Created" if created else "Updated"} GitHub OAuth app'
            ))
        else:
            self.stdout.write(self.style.WARNING(
                'GitHub OAuth credentials not found. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in .env'
            ))

        # Set up Google OAuth (if credentials are provided)
        if settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
            google_app, created = SocialApp.objects.get_or_create(
                provider='google',
                defaults={
                    'name': 'Google',
                    'client_id': settings.GOOGLE_CLIENT_ID,
                    'secret': settings.GOOGLE_CLIENT_SECRET,
                }
            )
            if not created:
                google_app.client_id = settings.GOOGLE_CLIENT_ID
                google_app.secret = settings.GOOGLE_CLIENT_SECRET
                google_app.save()
            
            google_app.sites.add(site)
            self.stdout.write(self.style.SUCCESS(
                f'{"Created" if created else "Updated"} Google OAuth app'
            ))
        else:
            self.stdout.write(self.style.WARNING(
                'Google OAuth credentials not found. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env'
            ))

        self.stdout.write(self.style.SUCCESS(
            '\nTo complete OAuth setup:'
            '\n1. For GitHub: Add http://localhost:8000/accounts/github/login/callback/ as callback URL'
            '\n2. For Google: Add http://localhost:8000/accounts/google/login/callback/ as authorized redirect URI'
            '\n3. Add credentials to .env file'
        ))