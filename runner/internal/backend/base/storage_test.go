package base

import (
	"bytes"
	"context"
	"github.com/stretchr/testify/assert"
	"io"
	"sync"
	"testing"
)

func TestEmptyRemote(t *testing.T) {
	storage := NewMockStorage([]StorageObject{})
	lister := NewMockLister([]StorageObject{
		{Key: "01"},
		{Key: "02"},
		{Key: "03"},
	})
	if err := uploadDir(context.TODO(), storage, "src/", "key/", true, false, lister, dummyFileUpload); err != nil {
		assert.Nil(t, err)
	}
	assert.ElementsMatch(t, []string{"key/01", "key/02", "key/03"}, storage.upload)
}

func TestEmptyLocal(t *testing.T) {
	storage := NewMockStorage([]StorageObject{
		{Key: "01"},
		{Key: "02"},
		{Key: "03"},
	})
	lister := NewMockLister([]StorageObject{})
	if err := uploadDir(context.TODO(), storage, "src/", "key/", true, false, lister, dummyFileUpload); err != nil {
		assert.Nil(t, err)
	}
	assert.ElementsMatch(t, []string{"key/01", "key/02", "key/03"}, storage.delete)
}

func TestOverlap(t *testing.T) {
	storage := NewMockStorage([]StorageObject{
		{Key: "01"},
		{Key: "02"},
		{Key: "03"},
	})
	lister := NewMockLister([]StorageObject{
		{Key: "02"},
		{Key: "03"},
		{Key: "04"},
	})
	if err := uploadDir(context.TODO(), storage, "src/", "key/", true, false, lister, dummyFileUpload); err != nil {
		assert.Nil(t, err)
	}
	assert.ElementsMatch(t, []string{"key/01"}, storage.delete)
	assert.ElementsMatch(t, []string{"key/04"}, storage.upload)
}

func TestOverlapWithChanges(t *testing.T) {
	storage := NewMockStorage([]StorageObject{
		{Key: "01"},
		{Key: "02"},
		{Key: "03"},
	})
	lister := NewMockLister([]StorageObject{
		{Key: "02", Size: 1},
		{Key: "03"},
		{Key: "04"},
	})
	if err := uploadDir(context.TODO(), storage, "src/", "key/", true, false, lister, dummyFileUpload); err != nil {
		assert.Nil(t, err)
	}
	assert.ElementsMatch(t, []string{"key/01"}, storage.delete)
	assert.ElementsMatch(t, []string{"key/02", "key/04"}, storage.upload)
}

// === Mocks ===

type pair struct{ old, new string }

type MockStorage struct {
	files    []StorageObject
	upload   []string
	delete   []string
	download []string
	rename   []pair
	symlink  []pair
	metadata []pair
	mu       sync.Mutex
}

func NewMockStorage(files []StorageObject) *MockStorage {
	return &MockStorage{
		files:    files,
		upload:   []string{},
		delete:   []string{},
		download: []string{},
		rename:   []pair{},
		symlink:  []pair{},
		metadata: []pair{},
	}
}

func (m *MockStorage) Download(ctx context.Context, key string, writer io.Writer) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.download = append(m.download, key)
	return nil
}

func (m *MockStorage) Upload(ctx context.Context, reader io.Reader, key string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.upload = append(m.upload, key)
	return nil
}

func (m *MockStorage) Delete(ctx context.Context, key string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.delete = append(m.delete, key)
	return nil
}

func (m *MockStorage) Rename(ctx context.Context, oldKey, newKey string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.rename = append(m.rename, pair{oldKey, newKey})
	return nil
}

func (m *MockStorage) CreateSymlink(ctx context.Context, key, symlink string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.symlink = append(m.symlink, pair{key, symlink})
	return nil
}

func (m *MockStorage) GetMetadata(ctx context.Context, key, tag string) (string, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.metadata = append(m.metadata, pair{key, tag})
	return "", nil
}

func (m *MockStorage) List(ctx context.Context, prefix string) (<-chan *StorageObject, <-chan error) {
	return chanFromSlice(m.files)
}

func chanFromSlice(objects []StorageObject) (<-chan *StorageObject, <-chan error) {
	ch := make(chan *StorageObject)
	errCh := make(chan error, 1)
	go func() {
		defer close(ch)
		defer close(errCh)
		for _, file := range objects {
			f := file
			ch <- &f
		}
	}()
	return ch, errCh
}

func dummyFileUpload(ctx context.Context, storage Storage, src, key string) error {
	return storage.Upload(ctx, bytes.NewReader(nil), key)
}

func NewMockLister(files []StorageObject) StorageLister {
	return func(ctx context.Context, src string) (<-chan *StorageObject, <-chan error) {
		return chanFromSlice(files)
	}
}
