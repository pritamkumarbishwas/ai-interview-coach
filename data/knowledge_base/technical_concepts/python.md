---
topic: python
roles: backend, full-stack
---

## Async and Await

`async def` defines a coroutine; awaiting it suspends until it finishes, while the event loop keeps running other tasks. Async I/O wins when a request mostly waits on sockets, databases, or HTTP calls — thousands of in-flight requests on one thread. It gains little for CPU-bound work, and one blocking call (a synchronous file read, `time.sleep`, heavy regex) stalls the entire loop.

Practical interview points: `asyncio.gather` runs tasks concurrently and `return_exceptions=True` decides whether one failure cancels the rest; an un-awaited coroutine produces a "coroutine was never awaited" warning and silently does nothing; structured concurrency via `TaskGroup` (Python 3.11+) guarantees children finish or propagate errors; and blocking work should move to a thread (`asyncio.to_thread`) or a process pool.

## The GIL

The Global Interpreter Lock lets only one thread execute Python bytecode at a time, so threads do not give CPU parallelism in CPython — they help only with I/O overlap or C extensions that release the Gil. `multiprocessing` sidesteps it by running separate interpreters, at the cost of pickling overhead and memory. Python 3.13 offers an experimental free-threaded build removing the GIL; 3.12 and earlier need it.

Strong answers connect the GIL to real symptoms: a multi-threaded CPU-heavy service showing one saturated core, why async became the default pattern for I/O-bound APIs, and when a native extension (NumPy, cryptography) releasing the GIL changes the calculus.

## Error Handling and Dataclasses

EAFP (Easier to Ask Forgiveness than Permission) is idiomatic Python: try/except around the operation beats pre-checking, because it avoids race windows and reads cleanly. Catch specific exceptions; a bare `except:` swallows `KeyboardInterrupt`. `dataclasses` give value objects with generated `__init__`/`__repr__`/`__eq__`; `frozen=True` adds hashability for use as dict keys; `slots=True` (3.10+) cuts per-instance memory and speeds attribute access. For validation at the edges, Pydantic models parse JSON into typed, checked objects — dataclasses are for internal structure, Pydantic for untrusted input.
