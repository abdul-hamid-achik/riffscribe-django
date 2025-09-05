# RiffScribe Views Organization Guide

## Current Status

The views have been reorganized from a monolithic `views.py` (947 lines) into a modular package structure for better maintainability.

## File Structure

```
transcriber/
├── views/                    # New organized views package
│   ├── __init__.py           # Package exports
│   ├── core.py              # Core views (index, upload, library, dashboard, profile)
│   ├── transcription.py     # Transcription management
│   ├── export.py            # Export functionality (in progress)
│   ├── preview.py           # Preview views (pending)
│   ├── variants.py          # Variant management (pending)
│   ├── README.md            # Documentation
│   └── ORGANIZATION.md      # This file
│
├── views.py                 # Original monolithic file (947 lines) - TO BE DEPRECATED
├── views_cbv.py             # Class-based views (794 lines) - NOT CURRENTLY USED
├── views_preview.py         # Preview-specific views (375 lines) - TO BE INTEGRATED
└── urls.py                  # URL configuration (currently imports from views)
```

## Migration Plan

### Phase 1: Create Module Structure ✅
- Created `views/` package directory
- Created `__init__.py` with proper exports
- Created documentation files

### Phase 2: Extract Core Views ✅
- Created `core.py` with:
  - `index()` - Landing page
  - `upload()` - File upload
  - `library()` - Browse transcriptions
  - `dashboard()` - User dashboard
  - `profile()` - User profile

### Phase 3: Extract Transcription Views ✅
- Created `transcription.py` with:
  - `detail()` - Transcription details
  - `status()` - Processing status
  - `get_task_status()` - Celery task status
  - `toggle_favorite()` - Favorite management
  - `delete_transcription()` - Delete functionality

### Phase 4: Extract Export Views (IN PROGRESS)
- Create `export.py` with:
  - `export()` - Export selection page
  - `download()` - Download exported files
  - `export_musicxml()` - MusicXML export
  - `download_gp5()` - Guitar Pro export
  - `download_ascii_tab()` - ASCII tab export
  - `download_midi()` - MIDI export

### Phase 5: Extract Variant Views (PENDING)
- Create `variants.py` with:
  - `variants_list()` - List all variants
  - `select_variant()` - Select active variant
  - `variant_preview()` - Preview variant
  - `regenerate_variants()` - Generate new variants
  - `variant_stats()` - Show variant statistics
  - `export_variant()` - Export specific variant
  - `check_generation_status()` - Check generation status

### Phase 6: Extract Preview Views (PENDING)
- Create `preview.py` with:
  - `preview_tab()` - Tab preview with AlphaTab
  - Additional preview functionality from `views_preview.py`

### Phase 7: Update Imports (PENDING)
- Update `urls.py` to import from views package
- Test all URL patterns still work
- Update any other imports in the codebase

### Phase 8: Cleanup (PENDING)
- Mark `views.py` as deprecated
- Move any remaining utility functions to appropriate modules
- Consider integrating useful parts from `views_cbv.py`
- Archive or remove old view files

## Benefits of Reorganization

1. **Better Organization**: Views are grouped by functionality
2. **Easier Maintenance**: Smaller, focused files are easier to maintain
3. **Improved Testing**: Each module can be tested independently
4. **Clear Responsibilities**: Each module has a clear purpose
5. **Easier Navigation**: Finding specific views is much easier
6. **Reduced Conflicts**: Multiple developers can work on different modules

## Usage After Migration

```python
# Old way (monolithic)
from transcriber import views

# New way (modular) - but still works with old imports!
from transcriber.views import index, upload, detail

# Or import specific modules
from transcriber.views.core import dashboard, profile
from transcriber.views.export import export_musicxml
```

## Testing Checklist

After migration, verify:
- [ ] All URL patterns resolve correctly
- [ ] HTMX partial responses work
- [ ] Authentication/permission checks work
- [ ] File uploads process correctly
- [ ] Export functionality works
- [ ] Variant management works
- [ ] Preview functionality works
- [ ] No import errors in other parts of codebase

## Notes

- The `__init__.py` re-exports all views to maintain backwards compatibility
- Class-based views in `views_cbv.py` are not currently used but could be integrated
- Preview views in `views_preview.py` should be integrated into the new structure