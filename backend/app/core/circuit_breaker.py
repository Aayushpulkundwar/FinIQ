import time
import asyncio
from enum import Enum
from typing import Callable, Any, Dict
from loguru import logger


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerError(Exception):
    """Exception raised when the circuit breaker blocks execution."""
    pass


class CircuitBreaker:
    """
    State machine protecting external service calls (like LLM API requests) from cascades.
    """
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_state_change = time.time()

    def _change_state(self, new_state: CircuitState):
        logger.warning(
            f"CircuitBreaker '{self.name}' transitioning from {self.state} to {new_state}"
        )
        self.state = new_state
        self.last_state_change = time.time()

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Wrap execution of an async function call inside the circuit breaker state flow."""
        current_time = time.time()

        # ── 1. Check State Boundaries ─────────────────────────────────────────
        if self.state == CircuitState.OPEN:
            if current_time - self.last_state_change > self.recovery_timeout:
                self._change_state(CircuitState.HALF_OPEN)
            else:
                logger.error(f"CircuitBreaker '{self.name}' is OPEN. Blocking call.")
                raise CircuitBreakerError(
                    f"Circuit breaker '{self.name}' is open. External calls are temporarily blocked."
                )

        # ── 2. Attempt Execution ──────────────────────────────────────────────
        try:
            res = await func(*args, **kwargs)
            
            # If successful, reset or close the circuit
            if self.state == CircuitState.HALF_OPEN:
                self.failure_count = 0
                self._change_state(CircuitState.CLOSED)
            elif self.state == CircuitState.CLOSED:
                self.failure_count = 0
                
            return res

        except Exception as e:
            # Increment failure counter
            self.failure_count += 1
            logger.warning(
                f"CircuitBreaker '{self.name}' failure recorded ({self.failure_count}/{self.failure_threshold}). Error: {e}"
            )

            # Trigger state transition if failure threshold reached
            if self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN):
                if self.failure_count >= self.failure_threshold:
                    self._change_state(CircuitState.OPEN)

            raise e


# Global map for circuit instances
_circuit_registry: Dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0
) -> CircuitBreaker:
    """Retrieve or construct a named CircuitBreaker singleton."""
    if name not in _circuit_registry:
        _circuit_registry[name] = CircuitBreaker(name, failure_threshold, recovery_timeout)
    return _circuit_registry[name]
