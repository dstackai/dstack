package ports

import (
	"testing"

	"github.com/docker/go-connections/nat"
	"github.com/stretchr/testify/assert"
)

func TestMgr_Register(t *testing.T) {
	ports := []string{
		"80",
	}
	m := New(20, 23)
	taskID, err := m.Register(1, ports)
	assert.Equal(t, err, nil)
	_, err = m.Register(0, []string{
		"80",
		"81",
		"82",
	})
	assert.Equal(t, err, ErrZeroFreePort)
	ports = m.Ports(taskID)
	assert.Equal(t, ports, []string{"20"})
	m.Unregister(taskID)
	ports = m.Ports(taskID)
	assert.Equal(t, ports, []string{})
	taskID, err = m.Register(1, []string{"80"})
	assert.Equal(t, err, nil)
	_, err = m.Register(0, []string{
		"80",
		"81",
		"82",
	})
	assert.Equal(t, err, ErrZeroFreePort)
	_, err = m.Register(0, []string{
		"81",
		"82",
	})
	assert.Equal(t, err, nil)
}
func TestMgr_RegisterSingle(t *testing.T) {
	ports := []string{
		"80",
	}
	m := NewSingle(20, 23)
	taskID, err := m.Register(0, ports)
	assert.Equal(t, err, nil)
	_, err = m.Register(0, []string{
		"80",
		"81",
		"82",
	})
	assert.Equal(t, err, ErrZeroFreePort)
	ports = m.Ports(taskID)
	assert.Equal(t, ports, []string{"20"})
	m.Unregister(taskID)
	ports = m.Ports(taskID)
	assert.Equal(t, ports, []string{})
	taskID, err = m.Register(0, []string{"80"})
	assert.Equal(t, err, nil)
	_, err = m.Register(0, []string{
		"80",
		"81",
		"82",
	})
	assert.Equal(t, err, ErrZeroFreePort)
	_, err = m.Register(0, []string{
		"81",
		"82",
	})
	assert.Equal(t, err, nil)
}

func TestMgr_ExposedPorts(t *testing.T) {
	ports := []string{
		"80",
	}
	m := New(20, 22)
	taskID, err := m.Register(0, ports)
	assert.Equal(t, err, nil)
	expose := m.ExposedPorts(taskID)
	assert.Equal(t, expose, nat.PortSet{"80/tcp": struct{}{}})
}

func TestMgr_BindPorts(t *testing.T) {
	ports := []string{
		"80",
	}
	m := New(20, 22)
	taskID, err := m.Register(0, ports)
	assert.Equal(t, err, nil)
	bind := m.BindPorts(taskID)
	assert.Equal(t, bind, nat.PortMap{"80/tcp": []nat.PortBinding{
		{
			HostIP:   "0.0.0.0",
			HostPort: "20",
		},
	}})

}

func TestSystem(t *testing.T) {
	m := NewSystem()
	taskID, err := m.Register(3, nil)
	assert.Equal(t, err, nil)
	listPost := m.Ports(taskID)
	assert.Equal(t, 3, len(listPost))
}
