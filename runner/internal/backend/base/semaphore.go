package base

type Semaphore chan struct{}

func (s Semaphore) Acquire(n int) {
	for i := 0; i < n; i++ {
		s <- struct{}{}
	}
}

func (s Semaphore) Release(n int) {
	for i := 0; i < n; i++ {
		<-s
	}
}
