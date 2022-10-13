package ports

import "errors"

var ErrZeroFreePort = errors.New("no free ports")
