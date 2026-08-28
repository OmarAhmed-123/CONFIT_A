import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, Callable
from backend.app.core.logging import logger


class BaseProvider(ABC):
    """Base class for all external provider integrations with retries, timeouts, and failure isolation."""

    def __init__(self, name: str, timeout_seconds: float = 8.0, max_retries: int = 2):
        self.name = name
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.failure_count = 0
        self.circuit_open_until = 0.0

    def is_healthy(self) -> bool:
        return time.time() > self.circuit_open_until

    async def execute_with_resilience(self, func: Callable, *args, **kwargs) -> Any:
        if not self.is_healthy():
            logger.warn(f"Circuit open for provider {self.name}. Routing to deterministic fallback.")
            return await self.fallback(*args, **kwargs)

        for attempt in range(1, self.max_retries + 1):
            try:
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=self.timeout_seconds)
                self.failure_count = 0
                return result
            except asyncio.TimeoutError:
                logger.warn(f"Provider {self.name} timed out on attempt {attempt}/{self.max_retries}")
            except Exception as exc:
                logger.error(f"Provider {self.name} failed on attempt {attempt}: {str(exc)}")

            if attempt < self.max_retries:
                await asyncio.sleep(0.3 * attempt)

        # Trips circuit breaker if multiple consecutive failures
        self.failure_count += 1
        if self.failure_count >= 3:
            self.circuit_open_until = time.time() + 60.0
            logger.error(f"Provider {self.name} tripped circuit breaker for 60s")

        logger.info(f"Using fallback implementation for {self.name}")
        return await self.fallback(*args, **kwargs)

    @abstractmethod
    async def fallback(self, *args, **kwargs) -> Any:
        pass
