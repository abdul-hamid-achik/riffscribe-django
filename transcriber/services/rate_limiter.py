"""
Rate Limiting Service for OpenAI API and other external services
"""
import time
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from django.core.cache import cache
from django.conf import settings
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RateLimit:
    """Rate limit configuration"""
    requests_per_minute: int
    requests_per_hour: int
    requests_per_day: int
    cost_per_day: float
    cost_per_month: float


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded"""
    def __init__(self, limit_type: str, retry_after: int):
        self.limit_type = limit_type
        self.retry_after = retry_after
        super().__init__(f"{limit_type} rate limit exceeded. Retry after {retry_after} seconds")


class OpenAIRateLimiter:
    """Rate limiter specifically for OpenAI API requests"""
    
    CACHE_PREFIX = "rate_limit:openai:"
    
    def __init__(self):
        self.limits = RateLimit(
            requests_per_minute=getattr(settings, 'OPENAI_RATE_LIMIT_PER_MINUTE', 60),
            requests_per_hour=getattr(settings, 'OPENAI_RATE_LIMIT_PER_MINUTE', 60) * 60,
            requests_per_day=getattr(settings, 'OPENAI_RATE_LIMIT_PER_MINUTE', 60) * 60 * 24,
            cost_per_day=getattr(settings, 'OPENAI_MONTHLY_BUDGET_LIMIT', 100) / 30,  # Daily budget
            cost_per_month=getattr(settings, 'OPENAI_MONTHLY_BUDGET_LIMIT', 100)
        )
    
    def can_make_request(self, estimated_cost: float = 0.0) -> tuple[bool, Optional[int]]:
        """
        Check if a request can be made within rate limits
        
        Returns:
            (can_proceed, retry_after_seconds)
        """
        now = time.time()
        
        # Check request rate limits
        for period, limit in [
            ('minute', self.limits.requests_per_minute),
            ('hour', self.limits.requests_per_hour),
            ('day', self.limits.requests_per_day)
        ]:
            cache_key = f"{self.CACHE_PREFIX}requests:{period}"
            requests = cache.get(cache_key, [])
            
            # Remove old requests based on period
            cutoff_time = self._get_cutoff_time(now, period)
            requests = [req_time for req_time in requests if req_time > cutoff_time]
            
            if len(requests) >= limit:
                retry_after = int(min(requests) + self._get_period_seconds(period) - now) + 1
                logger.warning(f"OpenAI rate limit exceeded for {period}: {len(requests)}/{limit}")
                return False, retry_after
        
        # Check cost limits
        if estimated_cost > 0:
            for period, cost_limit in [
                ('day', self.limits.cost_per_day),
                ('month', self.limits.cost_per_month)
            ]:
                cache_key = f"{self.CACHE_PREFIX}cost:{period}"
                current_cost = cache.get(cache_key, 0.0)
                
                if current_cost + estimated_cost > cost_limit:
                    retry_after = self._get_cost_reset_time(period)
                    logger.warning(f"OpenAI cost limit would be exceeded for {period}: "
                                 f"${current_cost + estimated_cost:.2f} > ${cost_limit:.2f}")
                    return False, retry_after
        
        return True, None
    
    def record_request(self, cost: float = 0.0):
        """Record a successful request"""
        now = time.time()
        
        # Record request counts
        for period in ['minute', 'hour', 'day']:
            cache_key = f"{self.CACHE_PREFIX}requests:{period}"
            requests = cache.get(cache_key, [])
            
            # Clean old requests
            cutoff_time = self._get_cutoff_time(now, period)
            requests = [req_time for req_time in requests if req_time > cutoff_time]
            
            # Add current request
            requests.append(now)
            
            # Save with appropriate timeout
            timeout = self._get_period_seconds(period) + 60  # Extra buffer
            cache.set(cache_key, requests, timeout=timeout)
        
        # Record costs
        if cost > 0:
            for period in ['day', 'month']:
                cache_key = f"{self.CACHE_PREFIX}cost:{period}"
                current_cost = cache.get(cache_key, 0.0)
                new_cost = current_cost + cost
                
                timeout = self._get_period_seconds(period) + 3600  # Extra buffer
                cache.set(cache_key, new_cost, timeout=timeout)
        
        logger.debug(f"Recorded OpenAI request with cost ${cost:.4f}")
    
    def get_current_usage(self) -> Dict[str, Any]:
        """Get current usage statistics"""
        now = time.time()
        usage = {}
        
        # Request counts
        for period in ['minute', 'hour', 'day']:
            cache_key = f"{self.CACHE_PREFIX}requests:{period}"
            requests = cache.get(cache_key, [])
            
            # Clean old requests
            cutoff_time = self._get_cutoff_time(now, period)
            requests = [req_time for req_time in requests if req_time > cutoff_time]
            
            limit = getattr(self.limits, f'requests_per_{period}')
            usage[f'requests_{period}'] = {
                'current': len(requests),
                'limit': limit,
                'remaining': max(0, limit - len(requests)),
                'reset_at': self._get_next_reset_time(period)
            }
        
        # Cost tracking
        for period in ['day', 'month']:
            cache_key = f"{self.CACHE_PREFIX}cost:{period}"
            current_cost = cache.get(cache_key, 0.0)
            
            limit = getattr(self.limits, f'cost_per_{period}')
            usage[f'cost_{period}'] = {
                'current': current_cost,
                'limit': limit,
                'remaining': max(0, limit - current_cost),
                'reset_at': self._get_next_reset_time(period)
            }
        
        return usage
    
    def wait_for_rate_limit(self, estimated_cost: float = 0.0) -> bool:
        """
        Wait until rate limit allows a request
        
        Returns:
            True if request can proceed, False if should abort
        """
        max_wait_time = 300  # 5 minutes maximum wait
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            can_proceed, retry_after = self.can_make_request(estimated_cost)
            
            if can_proceed:
                return True
            
            if retry_after and retry_after < max_wait_time:
                logger.info(f"Rate limit hit, waiting {retry_after} seconds...")
                time.sleep(min(retry_after, 60))  # Wait max 1 minute at a time
            else:
                logger.error(f"Rate limit wait time too long: {retry_after}s")
                return False
        
        logger.error(f"Max wait time exceeded: {max_wait_time}s")
        return False
    
    def _get_cutoff_time(self, now: float, period: str) -> float:
        """Get cutoff time for a period"""
        return now - self._get_period_seconds(period)
    
    def _get_period_seconds(self, period: str) -> int:
        """Get seconds in a period"""
        return {
            'minute': 60,
            'hour': 3600,
            'day': 86400,
            'month': 86400 * 30
        }[period]
    
    def _get_next_reset_time(self, period: str) -> str:
        """Get next reset time as ISO string"""
        now = datetime.now()
        
        if period == 'minute':
            next_reset = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        elif period == 'hour':
            next_reset = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        elif period == 'day':
            next_reset = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        else:  # month
            if now.month == 12:
                next_reset = now.replace(year=now.year+1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                next_reset = now.replace(month=now.month+1, day=1, hour=0, minute=0, second=0, microsecond=0)
        
        return next_reset.isoformat()
    
    def _get_cost_reset_time(self, period: str) -> int:
        """Get seconds until cost limit resets"""
        now = datetime.now()
        
        if period == 'day':
            next_reset = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        else:  # month
            if now.month == 12:
                next_reset = now.replace(year=now.year+1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                next_reset = now.replace(month=now.month+1, day=1, hour=0, minute=0, second=0, microsecond=0)
        
        return int((next_reset - now).total_seconds())


class GeneralRateLimiter:
    """General purpose rate limiter for any service"""
    
    def __init__(self, service_name: str, requests_per_minute: int = 60):
        self.service_name = service_name
        self.requests_per_minute = requests_per_minute
        self.cache_prefix = f"rate_limit:{service_name}:"
    
    def can_make_request(self, identifier: str = "default") -> tuple[bool, Optional[int]]:
        """Check if request can be made"""
        now = time.time()
        cache_key = f"{self.cache_prefix}{identifier}"
        
        requests = cache.get(cache_key, [])
        cutoff_time = now - 60  # Last minute
        
        # Remove old requests
        requests = [req_time for req_time in requests if req_time > cutoff_time]
        
        if len(requests) >= self.requests_per_minute:
            retry_after = int(min(requests) + 60 - now) + 1
            return False, retry_after
        
        return True, None
    
    def record_request(self, identifier: str = "default"):
        """Record a request"""
        now = time.time()
        cache_key = f"{self.cache_prefix}{identifier}"
        
        requests = cache.get(cache_key, [])
        cutoff_time = now - 60
        
        # Clean and add current request
        requests = [req_time for req_time in requests if req_time > cutoff_time]
        requests.append(now)
        
        cache.set(cache_key, requests, timeout=120)  # 2 minute timeout


# Global instances
openai_limiter = OpenAIRateLimiter()


def check_openai_rate_limit(estimated_cost: float = 0.0) -> tuple[bool, Optional[int]]:
    """Convenience function to check OpenAI rate limit"""
    return openai_limiter.can_make_request(estimated_cost)


def record_openai_request(cost: float = 0.0):
    """Convenience function to record OpenAI request"""
    return openai_limiter.record_request(cost)


def wait_for_openai_rate_limit(estimated_cost: float = 0.0) -> bool:
    """Convenience function to wait for OpenAI rate limit"""
    return openai_limiter.wait_for_rate_limit(estimated_cost)
