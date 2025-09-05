"""
JSON utilities for handling numpy arrays and other non-serializable objects.
"""
import json
import numpy as np
from typing import Any, Dict, List, Union


def ensure_json_serializable(obj: Any) -> Any:
    """
    Convert numpy arrays and other non-serializable objects to JSON-serializable format.
    
    Args:
        obj: Any object that might contain numpy arrays
        
    Returns:
        JSON-serializable version of the object
    """
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, dict):
        return {key: ensure_json_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [ensure_json_serializable(item) for item in obj]
    else:
        return obj


def safe_json_dumps(obj: Any, **kwargs) -> str:
    """
    Safely dump object to JSON, converting numpy arrays first.
    
    Args:
        obj: Object to serialize
        **kwargs: Additional arguments to json.dumps
        
    Returns:
        JSON string
    """
    serializable_obj = ensure_json_serializable(obj)
    return json.dumps(serializable_obj, **kwargs)


def clean_analysis_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clean analysis result dictionary to ensure all values are JSON-serializable.
    Removes None values and empty collections.
    
    Args:
        result: Analysis result dictionary
        
    Returns:
        Cleaned dictionary with JSON-serializable values
    """
    if not result:
        return {}
    
    cleaned = ensure_json_serializable(result)
    
    # Remove None values and empty collections
    filtered = {}
    for key, value in cleaned.items():
        if value is not None and not (isinstance(value, (list, dict)) and not value):
            filtered[key] = value
    
    return filtered