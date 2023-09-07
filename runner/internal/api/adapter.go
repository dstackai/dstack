package api

type ServerAdapter struct {
	jobStateCh chan<- string
	jobCh      <-chan SubmitBody
	codeCh     <-chan string
	runCh      <-chan interface{}
}

func (a *ServerAdapter) SetJobState(state string) {
	a.jobStateCh <- state
}

func (a *ServerAdapter) GetJob() <-chan SubmitBody {
	return a.jobCh
}

func (a *ServerAdapter) GetCode() <-chan string {
	return a.codeCh
}

func (a *ServerAdapter) WaitRun() <-chan interface{} {
	return a.runCh
}
