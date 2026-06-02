from __future__ import annotations

from typing import Any, Optional


class StepRunner:
    """Run a smolagents MultiStepAgent one step at a time using streaming.

    Parameters
    ----------
    agent : Any
        A smolagents MultiStepAgent (e.g., CodeAgent, ToolCallingAgent).
    task : str
        The task/prompt to solve.
    reset : bool, optional
        Whether to reset the agent’s memory before starting, by default True.
    **kwargs : dict
        Additional arguments forwarded to `agent.run(...)` (e.g., images, additional_args).
    """

    def __init__(self, agent: Any, task: str, *, reset: bool = True, **kwargs: Any) -> None:
        # Create the generator that yields each step from the agent
        self._agent = agent
        self._gen = agent.run(task, stream=True, reset=reset, **kwargs)
        self.last: Optional[Any] = None
        self.done: bool = False

    def step(self) -> Optional[Any]:
        """Advance the agent by exactly one step.

        Returns
        -------
        Optional[Any]
            The yielded item for that step (e.g., ToolCall, ToolOutput/ActionOutput,
            ActionStep, FinalAnswerStep). Returns None if the run is finished.
        """
        if self.done:
            return None
        try:
            self.last = next(self._gen)
            return self.last
        except StopIteration:
            self.done = True
            return None

    def drain(self) -> None:
        """Advance until completion (no return value)."""
        while not self.done:
            if self.step() is None:
                break

    def close(self) -> None:
        """Close the underlying generator to avoid GeneratorExit warnings."""
        gen = getattr(self, "_gen", None)
        if gen is not None:
            try:
                gen.close()
            except Exception:
                pass
            finally:
                self._gen = None

    # Context manager helpers -------------------------------------------------
    def __enter__(self) -> "StepRunner":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.close()


# Convenience helpers ----------------------------------------------------------
def start_stepper(agent: Any, task: str, *, reset: bool = True, **kwargs: Any) -> StepRunner:
    """Create a StepRunner for the given agent and task."""
    return StepRunner(agent, task, reset=reset, **kwargs)


def step_once(runner: StepRunner) -> Optional[Any]:
    """Advance one step and return the yielded artifact (or None if finished)."""
    return runner.step()


def is_finished(runner: StepRunner) -> bool:
    """Return whether the runner has finished (final answer reached)."""
    return runner.done


def finish(runner: StepRunner) -> None:
    """Drain remaining steps and close the generator."""
    runner.drain()
    runner.close()


__all__ = [
    "StepRunner",
    "start_stepper",
    "step_once",
    "is_finished",
    "finish",
]

if __name__ == "__main__":  
    import argparse
    import os
    from smolagents import CodeAgent, LiteLLMModel  
    from dotenv import load_dotenv  
    load_dotenv()

    parser = argparse.ArgumentParser(description="Step-by-step runner demo for smolagents.")
    parser.add_argument("--task", default="What is 2**10?", help="Task/prompt to run.")
    parser.add_argument("--model-id", default="gemini/gemini-2.5-flash", help="LiteLLM model id.")
    parser.add_argument("--api-key-env", default="GOOGLE_API_KEY", help="Env var holding the API key.")
    args = parser.parse_args()

    api_key = os.getenv(args.api_key_env)
    if not api_key:
        raise RuntimeError(f"Missing API key in env var {args.api_key_env}")

    model = LiteLLMModel(model_id=args.model_id, api_key=api_key)
    agent = CodeAgent(tools=[], model=model)

    with StepRunner(agent, args.task, reset=True) as runner:
        while not runner.done:
            yielded = runner.step()
            print(type(yielded).__name__ if yielded is not None else "None")
