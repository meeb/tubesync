import asyncio
import inspect
import logging
import queue
import sys
import threading
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar


T = TypeVar('T')

# =====================================================================
# ISOLATED PURE-PYTHON BASE EXTRACTION & VERIFICATION
# =====================================================================
def _get_pure_python_simple_queue() -> Any:
    """Safely reads, compiles, and verifies the pure Python SimpleQueue fallback.

    This function extracts the source file of the standard library queue module,
    executes it inside an isolated namespace, and instantiates a dummy object
    to verify that necessary internal attributes exist.

    Raises:
        ImportError: If the source code cannot be located.
        AttributeError: If the compiled class lacks the expected internal attributes.

    Returns:
        The verified class type object for the pure Python implementation.
    """
    queue_source_path = inspect.getsourcefile(queue)
    if queue_source_path is None:
        raise ImportError('Source file for queue module could not be located.')

    with open(queue_source_path, 'r', encoding='utf-8') as f:
        source_code = f.read()

    isolated_globals: dict[str, Any] = {}
    compiled_code = compile(source_code, queue_source_path, 'exec')
    exec(compiled_code, isolated_globals)

    if '_PySimpleQueue' in isolated_globals:
        extracted_class = isolated_globals['_PySimpleQueue']
    else:
        extracted_class = isolated_globals['SimpleQueue']

    # Verify internal structural layout on a dummy instance before returning
    dummy = extracted_class()
    if not (hasattr(dummy, '_queue') and hasattr(dummy, '_count')):
        raise AttributeError('Extracted SimpleQueue is missing expected internal structures.')

    return extracted_class

# Initialize default safe states upfront
_PureSimpleQueue = queue.SimpleQueue
_HAS_PURE_BASE = False

# Attempt to extract and verify the pure-Python implementation
logger = logging.getLogger(__name__)
try:
    _PureSimpleQueue = _get_pure_python_simple_queue()
except Exception:
    logger.exception('Failed to get the pure python simple queue implementation.')
    raise
else:
    _HAS_PURE_BASE = True


@dataclass(frozen=True)
class QueueContextConfig:
    """Immutable type configuration container for queue context execution blocks."""
    block: bool = True
    timeout: float | None = None


class PeekableSimpleQueueProtocol(Protocol[T]):
    """Structural type protocol ensuring static analysis tools recognize peek()."""
    def put(self, item: T, block: bool = True, timeout: float | None = None) -> None: ...
    def get(self, block: bool = True, timeout: float | None = None) -> T: ...
    def get_nowait(self) -> T: ...
    def peek(self, block: bool = True, timeout: float | None = None) -> T: ...
    def qsize(self) -> int: ...
    def empty(self) -> bool: ...


# =====================================================================
# PURE PYTHON PEEK IMPLEMENTATION
# =====================================================================
class PurePythonPeekQueue(_PureSimpleQueue[T]):
    """A thread-safe SimpleQueue that allows non-destructive peeking.

    This variant targets the pure Python fallback implementation. It secures a
    direct, constant-time reference lookup of index 0 within the internal
    deque structures, synchronization is using a coordinated Semaphore
    primitive to safely park threads at the OS level when the queue is empty.

    Coordinates synchronization internally via the __call__ context manager
    pattern to safely interlock peek, put, and parent get operations.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initializes the pure Python peekable queue instance."""
        super().__init__(*args, **kwargs)

        self._lock = threading.RLock()
        self._context_config = QueueContextConfig()

    def __call__(self, *, block: bool = True, timeout: float | None = None) -> 'PurePythonPeekQueue[T]':
        """Configures the execution context parameters and returns self."""
        if block and timeout is not None and 0 > timeout:
            raise ValueError('"timeout" must be a non-negative number')

        # Overwrite the current configuration object under our lock
        with self._lock:
            self._context_config = QueueContextConfig(block=block, timeout=timeout)
        return self

    def __enter__(self) -> 'PurePythonPeekQueue[T]':
        """Enters the execution context block, securing locks and tokens."""
        # Read the current configuration object under our lock
        with self._lock:
            cfg = self._context_config
        # Temporarily acquire the semaphore slot to guarantee an item exists
        # This matches the parent get() entry block for proper thread line-up
        acquired = self._count.acquire(blocking=cfg.block, timeout=cfg.timeout)
        if not acquired:
            raise queue.Empty

        self._lock.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exits the execution context block, releasing locks and restoring balances."""
        try:
            self._lock.release()
        finally:
            # Put the semaphore token back so a regular get() can consume the item
            self._count.release()

    def __repr__(self) -> str:
        """Returns a string representation of the pure Python queue.

        Returns:
            A string containing the class name and current size details.
        """
        size = self.qsize()
        return f'<{self.__class__.__name__} object at {hex(id(self))} {size=}>'

    def peek(self, block: bool = True, timeout: float | None = None) -> T:
        """Inspects the front item of the queue without removing it.

        Coordinates directly with the parent get using the __call__ context manager.

        Args:
            block: If True, blocks until an item arrives or timeout expires.
            timeout: Maximum number of seconds to wait before raising Empty.

        Raises:
            queue.Empty: If the queue is empty and the wait criteria lapses.
            ValueError: If a negative timeout float duration is supplied.

        Returns:
            The data item located at the head position of the queue.
        """
        with self(block=block, timeout=timeout):
            return self._queue.__getitem__(0)  # type: ignore[no-any-return]

    def qsize(self) -> int:
        """Return the approximate size of the queue safely under lock synchronization."""
        with self._lock:
            return super().qsize()


# =====================================================================
# C-EXTENSION INTERCEPTING PEEK IMPLEMENTATION (Native C Blocking)
# =====================================================================
class InterceptingCPeekQueue(queue.SimpleQueue[T]):
    """A thread-safe SimpleQueue that allows non-destructive peeking.

    This variant targets the fast C-accelerated standard library module layout.
    Because the C layer completely encapsulates internal structures, this class
    intercepts element consumer methods to route items through a single-item
    list cache whenever a peek event takes place.
    """

    def __init__(self) -> None:
        """Initializes the C-accelerated intercepting queue instance."""
        super().__init__()
        self._peeked: list[T] = []
        self._lock = threading.RLock()

    def __repr__(self) -> str:
        """Returns a string representation of the C intercepting queue.

        Returns:
            A string containing the class name, combined size, and cache state.
        """
        with self._lock:
            cached_flag = 1 == len(self._peeked)
            size = self.qsize()
        return f'<{self.__class__.__name__} object at {hex(id(self))} {size=} cached={cached_flag}>'

    def empty(self) -> bool:
        """Checks if the queue is logically completely empty of items.

        Returns:
            True if no elements remain in either storage layer, False otherwise.
        """
        with self._lock:
            if self._peeked:
                return False
            return super().empty()  # type: ignore[no-any-return]

    def get(self, block: bool = True, timeout: float | None = None) -> T:
        """Removes and returns an item from the queue, exhausting the cache first.

        Args:
            block: If True, blocks until an item arrives or timeout expires.
            timeout: Maximum number of seconds to wait before raising Empty.

        Returns:
            The data item located at the head position of the queue.
        """
        with self._lock:
            try:
                return self._peeked.pop(0)
            except IndexError:
                pass

            return super().get(block=block, timeout=timeout)  # type: ignore[no-any-return]

    def get_nowait(self) -> T:
        """Removes and returns an item immediately without blocking.

        Returns:
            The data item located at the head position of the queue.
        """
        return self.get(block=False)

    def peek(self, block: bool = True, timeout: float | None = None) -> T:
        """Inspects the front item of the queue without removing it.

        Args:
            block: If True, blocks until an item arrives or timeout expires.
            timeout: Maximum number of seconds to wait before raising Empty.

        Returns:
            The data item located at the head position of the queue.
        """
        with self._lock:
            try:
                return self._peeked.__getitem__(0)
            except IndexError:
                pass

            item: T = super().get(block=block, timeout=timeout)

            self._peeked.append(item)
            return item

    def qsize(self) -> int:
        """Computes the combined size count across the queue and local cache.

        Returns:
            An integer tracking total accumulated items waiting for extraction.
        """
        with self._lock:
            size = super().qsize()
            return len(self._peeked) + size  # type: ignore[no-any-return]


# =====================================================================
# UNIFIED AUTOMATED FACTORY
# =====================================================================
def PeekableSimpleQueue(
    *args: Any,
    force_pure_python: bool = False,
    **kwargs: Any
) -> PeekableSimpleQueueProtocol[Any]:
    """Factory builder selecting the ideal Peekable SimpleQueue instance.

    Args:
        *args: Variable positional parameters passed down to the base constructor.
        force_pure_python: Forces selection of the pure Python class variant
            regardless of C extension runtime presence.
        **kwargs: Variable keyword configuration parameters passed to the constructor.

    Returns:
        A subclass instance of SimpleQueue supporting the custom peek method.
    """
    has_c_extension = '_queue' in sys.modules

    if _HAS_PURE_BASE and (force_pure_python or not has_c_extension):
        return PurePythonPeekQueue(*args, **kwargs)

    return InterceptingCPeekQueue(*args, **kwargs)


# =====================================================================
# INTERCEPTING PEEK IMPLEMENTATION (Async)
# =====================================================================
class AsyncPeekableQueue(asyncio.Queue[T]):
    """An Asyncio Queue supporting non-destructive peeking while preserving FIFO.

    Coordinates synchronization internally via the __call__ context manager
    pattern to safely interlock peek, put, and get operations.
    """

    def __init__(self, maxsize: int = 0) -> None:
        """Initializes the asynchronous peekable queue."""
        super().__init__(maxsize=maxsize)

        # Local single-item cache mirroring our verified C-extension strategy
        self._peeked: list[T] = []
        self._timeout: float | None = None

    def __call__(self, *, timeout: float | None = None) -> 'AsyncPeekableQueue[T]':
        """Configures the execution context parameters and returns self.

        Args:
            timeout: Keyword-only parameter specifying max wait time.
        """
        if timeout is not None and 0 > timeout:
            raise ValueError('"timeout" must be a non-negative number')

        self._timeout = timeout
        return self

    async def __aenter__(self) -> 'AsyncPeekableQueue[T]':
        """Enters the execution context block, securing the front item."""
        if self._peeked:
            return self

        try:
            if self._timeout is None:
                item = await super().get()
            else:
                item = await asyncio.wait_for(super().get(), timeout=self._timeout)

            self._peeked.append(item)
        except (asyncio.TimeoutError, TimeoutError):
            raise asyncio.QueueEmpty

        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exits the async context block without modifying structural tokens."""
        pass

    async def get(self) -> T:
        """Removes and returns an item, exhausting the peek cache first."""
        if self._peeked:
            return self._peeked.pop(0)
        return await super().get()

    def get_nowait(self) -> T:
        """Removes and returns an item immediately from the cache or queue."""
        if self._peeked:
            return self._peeked.pop(0)
        return super().get_nowait()

    def qsize(self) -> int:
        """Computes the combined size count across the queue and local cache."""
        return super().qsize() + len(self._peeked)

    def empty(self) -> bool:
        """Checks if the queue is logically completely empty of items.

        Returns:
            True if no elements remain in either storage layer, False otherwise.
        """
        if self._peeked:
            return False
        return super().empty()

    async def peek(self, timeout: float | None = None) -> T:
        """Inspects the front item of the queue without removing it."""
        async with self(timeout=timeout):
            return self._peeked.__getitem__(0)


# =====================================================================
# VERIFICATION EXAMPLE BLOCK
# =====================================================================
async def async_tests() -> None:
    print(f'Active class engine: {AsyncPeekableQueue.__name__}')
    q: AsyncPeekableQueue[str] = AsyncPeekableQueue()

    # Test Initial State Sizing
    print(f'Initial empty status: {q.empty()} (Expected: True)')
    print(f'Initial qsize metric: {q.qsize()} (Expected: 0)')

    # Populate the Buffer array
    await q.put('Payload A')
    await q.put('Payload B')
    print(f'\nAfter 2 puts -> qsize: {q.qsize()} (Expected: 2)')
    print(f'After 2 puts -> empty: {q.empty()} (Expected: False)')

    # Test Non-Destructive Peeking
    peeked_1 = await q.peek()
    print(f'\nPeek 1: {peeked_1} (Expected: Payload A)')
    print(f'After Peek 1 -> qsize: {q.qsize()} (Expected: 2)')

    # Call again to confirm cache lookup stability
    peeked_2 = await q.peek()
    print(f'Peek 2: {peeked_2} (Expected: Payload A)')

    # Test Destructive Consumption Tracking (Strict FIFO)
    get_1 = await q.get()
    print(f'\nGet 1: {get_1} (Expected: Payload A)')
    print(f'After Get 1 -> qsize: {q.qsize()} (Expected: 1)')

    get_2 = q.get_nowait()
    print(f'Get 2: {get_2} (Expected: Payload B)')
    print(f'After Get 2 -> qsize: {q.qsize()} (Expected: 0)')
    print(f'After Get 2 -> empty: {q.empty()} (Expected: True)')

    # Test Keyword-Only Context Execution and Timeout Errors
    print('\nTesting context exception handling on empty queue...')
    try:
        # Enforces keyword-only block validation syntax matching your pattern
        async with q(timeout=0.1):
            pass
    except asyncio.QueueEmpty:
        print('Success: Caught expected asyncio.QueueEmpty error on empty timeout.')

    # Test Invalid Parameter Rejection
    try:
        q(timeout=-1.5)
    except ValueError as e:
        print(f'Success: Caught expected negative value boundary error: {e}')


if '__main__' == __name__:
    # Create the optimal queue type automatically via the factory function
    q: queue.SimpleQueue = PeekableSimpleQueue(force_pure_python=(1 < len(sys.argv)))
    print(f'Active class engine: {q.__class__.__name__}')

    # Add items to the queue state
    q.put('Payload A')
    q.put('Payload B')

    # Audit the custom safe string representation layout
    print(f'Current repr: {q!r}')

    # Execute a safe peek check without consumption mutations
    peeked_item: str = q.peek()  # type: ignore[attr-defined]
    print(f'Peek:  {peeked_item}')
    print(f'Current repr: {q!r}')

    # Process items out sequence normally
    print(f'Get 1: {q.get()}')
    print(f'Current repr: {q!r}')
    print(f'Get 2: {q.get()}')
    print(f'Current repr: {q!r}')

    asyncio.run(async_tests())
