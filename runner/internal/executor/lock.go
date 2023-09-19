package executor

func (ex *RunExecutor) Lock() {
	ex.mu.Lock()
}

func (ex *RunExecutor) Unlock() {
	ex.mu.Unlock()
}

func (ex *RunExecutor) RLock() {
	ex.mu.RLock()
}

func (ex *RunExecutor) RUnlock() {
	ex.mu.RUnlock()
}
