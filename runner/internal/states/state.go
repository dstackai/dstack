package states

type State string

const (
	Submitted   State = "submitted"
	Running           = "running"
	Done              = "done"
	Failed            = "failed"
	Stopping          = "stopping"
	Stopped           = "stopped"
	Aborting          = "aborting"
	Aborted           = "aborted"
	Downloading       = "downloading"
	Uploading         = "uploading"
)

func (s State) String() string {
	return string(s)
}
