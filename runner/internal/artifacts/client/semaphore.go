package client

type semaphore chan struct{}

func (s semaphore) acquire(n int) {
	for i := 0; i < n; i++ {
		s <- struct{}{}
	}
}

func (s semaphore) release(n int) {
	for i := 0; i < n; i++ {
		<-s
	}
}
