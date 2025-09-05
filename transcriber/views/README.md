# RiffScribe Views Organization

This directory contains the organized view modules for the RiffScribe transcriber application.

## Structure

```
views/
├── __init__.py       # Package initialization, exports all views
├── core.py           # Main application views (index, upload, library, dashboard, profile)
├── transcription.py  # Transcription detail and management views
├── export.py         # Export functionality views (MusicXML, GP5, PDF, ASCII)
├── preview.py        # Tab preview and visualization views
├── variants.py       # Fingering variant management views
├── api.py           # API endpoints for AJAX/HTMX interactions
└── mixins.py        # Shared mixins and utilities
```

## Module Breakdown

### core.py
- `index()` - Landing page
- `upload()` - File upload handling
- `library()` - Transcription library/browse
- `dashboard()` - User dashboard
- `profile()` - User profile management

### transcription.py
- `detail()` - Transcription detail page
- `status()` - Processing status updates (HTMX)
- `delete_transcription()` - Delete transcription
- `toggle_favorite()` - Add/remove from favorites
- `get_task_status()` - Celery task status

### export.py
- `export()` - Export selection page
- `download()` - Download exported file
- `export_musicxml()` - Generate MusicXML export
- `download_gp5()` - Generate Guitar Pro export
- `download_ascii_tab()` - Generate ASCII tab export
- `download_midi()` - Generate MIDI export

### preview.py
- `preview_tab()` - Interactive tab preview with AlphaTab

### variants.py
- `variants_list()` - List fingering variants
- `select_variant()` - Select active variant
- `variant_preview()` - Preview specific variant
- `regenerate_variants()` - Generate new variants
- `variant_stats()` - Variant statistics modal
- `export_variant()` - Export specific variant
- `check_generation_status()` - Check variant generation status

## Usage

All views are imported and re-exported in `__init__.py` to maintain backwards compatibility with existing URL configurations:

```python
from transcriber import views

# All views are available at the package level
urlpatterns = [
    path('', views.index, name='index'),
    path('upload/', views.upload, name='upload'),
    # etc...
]
```

## Migration from Monolithic views.py

The original `views.py` has been split into logical modules for better organization and maintainability. The following files contain legacy code that should be gradually migrated:

- `views.py` - Original monolithic view file (to be deprecated)
- `views_cbv.py` - Class-based view alternatives (not currently used in URLs)
- `views_preview.py` - Preview-specific views (to be integrated)

## Best Practices

1. **Keep views focused** - Each view should have a single responsibility
2. **Use mixins** - Share common functionality through mixins in `mixins.py`
3. **HTMX support** - Check for `HX-Request` header and return appropriate partials
4. **Error handling** - Always handle both HTMX and regular request errors
5. **Permissions** - Use appropriate decorators (`@login_required`, etc.)
6. **Type hints** - Add type hints for better code clarity

## Testing

Each module should have corresponding tests in `tests/views/`:
- `test_core.py`
- `test_transcription.py`
- `test_export.py`
- `test_preview.py`
- `test_variants.py`