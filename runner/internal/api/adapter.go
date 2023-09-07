package api

type ServerAdapter struct {
	jobStateCh chan<- string
	submitJob  <-chan SubmitBody
	// todo run job channel
}

func NewServerAdapter(jobStateCh chan<- string) *ServerAdapter {
	return &ServerAdapter{
		jobStateCh: jobStateCh,
	}
}

func (a *ServerAdapter) SetJobState(state string) {
	a.jobStateCh <- state
}

func (a *ServerAdapter) GetJob() <-chan SubmitBody {
	return a.submitJob
}
