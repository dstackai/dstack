package queue

import "sync"

type Node struct {
	Next  *Node
	Value string
}

type Queue struct {
	mu     sync.Mutex
	root   *Node
	last   *Node
	length int
}

func New() *Queue {
	return new(Queue)
}

func (q *Queue) Len() int {
	q.mu.Lock()
	defer q.mu.Unlock()
	return q.length
}

func (q *Queue) IsEmpty() bool {
	q.mu.Lock()
	defer q.mu.Unlock()
	return q.root == nil
}

func (q *Queue) setRoot(node *Node) {
	q.root = node
	q.last = node
	q.length = 1
}

func (q *Queue) Push(s string) {
	node := &Node{
		Value: s,
	}
	if q.IsEmpty() {
		q.setRoot(node)
		return
	}
	q.mu.Lock()
	defer q.mu.Unlock()
	q.last.Next = node
	q.last = node
	q.length++
}

func (q *Queue) Pop() (string, bool) {
	if q.IsEmpty() {
		return "", false
	}
	q.mu.Lock()
	defer q.mu.Unlock()
	q.length--
	n := q.root
	q.root = q.root.Next
	return n.Value, true
}
