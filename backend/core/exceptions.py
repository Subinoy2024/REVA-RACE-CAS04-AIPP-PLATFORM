"""Domain exceptions used across the AIPP backend."""


class AIPPError(Exception):
    """Base class for all AIPP-specific errors."""


class RepositoryAccessError(AIPPError):
    """Failed to authenticate with, or read from, a repository."""


class ToolNotConfiguredError(AIPPError):
    """An MCP adapter was invoked before its credentials were configured."""


class PipelineGenerationError(AIPPError):
    """Generic failure inside the pipeline-generation flow."""


class PipelineValidationError(AIPPError):
    """The generated pipeline failed one of the validators."""


class RCAError(AIPPError):
    """PipelineDoctor could not process the log file."""


class LLMError(AIPPError):
    """Something went wrong when calling the LLM."""
