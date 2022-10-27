package states

type State string

const (
	Submitted   State = "submitted"
	Running           = "running"
	Done              = "done"
	Failed            = "failed"
	Stopped           = "stopped"
	Downloading       = "downloading"
	Uploading         = "uploading"
)

func (s State) String() string {
	return string(s)
}
