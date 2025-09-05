"""
Management command to fix TabExport records with incorrect file paths.
"""
from django.core.management.base import BaseCommand
from django.core.files import File
from transcriber.models import TabExport
import os


class Command(BaseCommand):
    help = 'Fix TabExport records with file paths outside media directory'

    def handle(self, *args, **options):
        broken_exports = []
        fixed_exports = 0
        deleted_exports = 0
        
        for export in TabExport.objects.all():
            try:
                # Try to access the file
                if export.file:
                    file_path = export.file.path
                    
                    # Check if it's outside the media directory
                    if file_path.startswith('/tmp/'):
                        broken_exports.append(export)
                        self.stdout.write(
                            self.style.WARNING(
                                f'Found broken export {export.id}: {file_path}'
                            )
                        )
                        
                        # Try to fix if file still exists
                        if os.path.exists(file_path):
                            with open(file_path, 'rb') as f:
                                file_name = os.path.basename(file_path)
                                export.file.save(file_name, File(f), save=True)
                                fixed_exports += 1
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f'Fixed export {export.id}'
                                    )
                                )
                        else:
                            # File doesn't exist, delete the export record
                            export.delete()
                            deleted_exports += 1
                            self.stdout.write(
                                self.style.ERROR(
                                    f'Deleted export {export.id} - file not found'
                                )
                            )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'Error processing export {export.id}: {str(e)}'
                    )
                )
                # If we can't access the file at all, delete the record
                export.delete()
                deleted_exports += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\nSummary:\n'
                f'Found {len(broken_exports)} broken exports\n'
                f'Fixed {fixed_exports} exports\n'
                f'Deleted {deleted_exports} exports'
            )
        )