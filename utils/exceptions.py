"""Application exception types."""


class TakeoffError(Exception):
    """Base exception for expected quantity takeoff application errors."""


class ConfigurationError(TakeoffError):
    """Raised when application configuration is invalid."""


class DrawingValidationError(TakeoffError):
    """Raised when an uploaded drawing does not meet input requirements."""


class DrawingProcessingError(TakeoffError):
    """Raised when a valid drawing cannot be processed."""


class MeasurementValidationError(TakeoffError):
    """Raised when scale or geometry input cannot produce a valid measurement."""


class BoqValidationError(TakeoffError):
    """Raised when a BoQ item or cost input is invalid."""


class MissingRateError(BoqValidationError):
    """Raised when a costed item has no usable rate."""


class VerificationValidationError(TakeoffError):
    """Raised when review state or geometry correction is invalid."""


class ReportValidationError(TakeoffError):
    """Raised when report snapshot or export data is incomplete."""
