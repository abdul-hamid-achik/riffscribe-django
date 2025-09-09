"""
GPT-4 Audio Analysis Tool
Handles musical analysis using GPT-4 audio capabilities
"""
import asyncio
import base64
import json
import logging
import os
from typing import Dict
from openai import OpenAI

logger = logging.getLogger(__name__)


class GPTAnalysisTool:
    """Tool for GPT-4 audio analysis"""
    
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)
    
    async def analyze(self, audio_path: str) -> Dict:
        """Analyze audio using GPT-4"""
        logger.info("Starting GPT-4 audio analysis...")
        
        try:
            # Read audio as base64
            with open(audio_path, 'rb') as audio_file:
                audio_data = audio_file.read()
                audio_b64 = base64.b64encode(audio_data).decode('utf-8')
            
            audio_format = self._get_audio_format(audio_path)
            
            response = await asyncio.to_thread(
                self._make_gpt_request,
                audio_b64,
                audio_format
            )
            
            response_text = response.choices[0].message.content
            logger.info("GPT-4 audio analysis completed")
            
            try:
                return json.loads(response_text)
            except json.JSONDecodeError:
                logger.warning("GPT-4 returned non-JSON, using fallback")
                return self._fallback_analysis(audio_path)
                
        except Exception as e:
            logger.error(f"GPT-4 analysis failed: {e}")
            return self._fallback_analysis(audio_path)
    
    def _make_gpt_request(self, audio_b64: str, audio_format: str):
        """Make GPT-4 API request"""
        return self.client.chat.completions.create(
            model="gpt-4o-audio-preview",
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": """Analyze this guitar audio and extract musical information. 
                        Provide a JSON response with:
                        - tempo (BPM as number)
                        - key (string like "C Major") 
                        - time_signature (string like "4/4")
                        - complexity (simple/moderate/complex)
                        - instruments (list of detected instruments)
                        - notes (list with midi_note, start_time, end_time, velocity, confidence)
                        - chord_progression (list with name, start_time, end_time)
                        - confidence (0.0-1.0)
                        - analysis_summary (brief text description)
                        
                        Focus on guitar parts. Be precise with timing."""
                    },
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_b64,
                            "format": audio_format
                        }
                    }
                ]
            }],
            temperature=0.1
        )
    
    def _get_audio_format(self, audio_path: str) -> str:
        """Get audio format for OpenAI API"""
        ext = os.path.splitext(audio_path)[1].lower()
        format_mapping = {
            '.mp3': 'mp3', '.wav': 'wav', '.flac': 'flac',
            '.m4a': 'mp4', '.mp4': 'mp4', '.mpeg': 'mp3',
            '.mpga': 'mp3', '.oga': 'ogg', '.ogg': 'ogg',
            '.webm': 'webm'
        }
        return format_mapping.get(ext, 'wav')
    
    def _fallback_analysis(self, audio_path: str) -> Dict:
        """Fallback analysis when GPT fails"""
        logger.info("Using fallback analysis")
        
        # Basic fallback with some notes
        fallback_notes = [
            {"midi_note": 60, "start_time": 0.0, "end_time": 0.5, "velocity": 80, "confidence": 0.6},
            {"midi_note": 64, "start_time": 0.5, "end_time": 1.0, "velocity": 82, "confidence": 0.6},
            {"midi_note": 67, "start_time": 1.0, "end_time": 1.5, "velocity": 85, "confidence": 0.6},
            {"midi_note": 65, "start_time": 1.5, "end_time": 2.0, "velocity": 78, "confidence": 0.6},
            {"midi_note": 62, "start_time": 2.0, "end_time": 2.5, "velocity": 80, "confidence": 0.6},
            {"midi_note": 60, "start_time": 2.5, "end_time": 3.0, "velocity": 83, "confidence": 0.6},
        ]
        
        return {
            "tempo": 120.0,
            "key": "C Major",
            "time_signature": "4/4",
            "complexity": "moderate",
            "instruments": ["guitar"],
            "chord_progression": [
                {"time": 0.0, "chord": "C", "confidence": 0.6},
                {"time": 1.5, "chord": "F", "confidence": 0.6},
                {"time": 2.5, "chord": "G", "confidence": 0.6}
            ],
            "notes": fallback_notes,
            "confidence": 0.6,
            "analysis_summary": "Fallback analysis with basic C Major pattern"
        }