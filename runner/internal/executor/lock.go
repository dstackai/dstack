package executor

func (ex *Executor) Lock() {
	ex.mu.Lock()
}

func (ex *Executor) Unlock() {
	ex.mu.Unlock()
}

func (ex *Executor) RLock() {
	ex.mu.RLock()
}

func (ex *Executor) RUnlock() {
	ex.mu.RUnlock()
}
