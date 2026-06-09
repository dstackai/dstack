package capabilities

import (
	"strings"

	"kernel.org/pub/linux/libs/security/libcap/cap"
)

type Capability cap.Value

const (
	SETUID       = Capability(cap.SETUID)
	SETGID       = Capability(cap.SETGID)
	CHOWN        = Capability(cap.CHOWN)
	SYS_RESOURCE = Capability(cap.SYS_RESOURCE)
)

// String returns a text representation of the capability in the form used by container folks:
// UPPER_CASE, no CAP_ prefix: cap_sys_admin -> SYS_ADMIN
func (c Capability) String() string {
	return strings.ToUpper(cap.Value(c).String()[4:])
}

// Has returns true if the current process has the specified capability in its effective set
func Has(c Capability) (bool, error) {
	set, err := cap.GetPID(0)
	if err != nil {
		return false, err
	}
	return set.GetFlag(cap.Effective, cap.Value(c))
}

// Check checks and returns those capabilities that are _missing_ from the effective set
// of the current process
func Check(cs ...Capability) (missing []Capability, err error) {
	set, err := cap.GetPID(0)
	if err != nil {
		return nil, err
	}
	for _, c := range cs {
		ok, err := set.GetFlag(cap.Effective, cap.Value(c))
		if err != nil {
			return nil, err
		}
		if !ok {
			missing = append(missing, c)
		}
	}
	return missing, nil
}
