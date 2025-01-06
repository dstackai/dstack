package shim

import "errors"

/*
Definitions of common error types used throughout shim.
Errors should wrap these errors to simplify error classifications, e.g.:

	func cleanup(containerID string) {
		...
		return fmt.Errorf("%w: failed to remove container")
	}

	if err := cleanup(containerID); errors.Is(err, ErrInternal) {
		return ErrorResponse {
			Status: 500,
			Message: err.Error(),
		}
	} else if errors.Is(err, ErrNotFound) {
		return ErrorResponse {
			Status: 404,
			Message: err.Error(),
		}
	}
*/
var (
	// shim failed to process request due to internal error
	ErrInternal = errors.New("internal error")
	// shim rejected to process request, e.g., bad params, state conflict, etc.
	ErrRequest = errors.New("request error")
	// referenced object does not exist
	ErrNotFound = errors.New("not found")
)
